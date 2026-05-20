"""Layer 6 – Backtesting engine: bar-by-bar event loop wiring all layers together."""

from dataclasses import dataclass, field
import pandas as pd
import numpy as np

from .strategy import Strategy
from .data import MarketDataFeed
from .risk import RiskManager
from .execution import PaperBroker, Order
from .portfolio import Portfolio
from .signals import TechnicalIndicators


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trade_log: pd.DataFrame
    portfolio: Portfolio
    metrics: dict = field(default_factory=dict)
    signals: pd.Series = field(default_factory=pd.Series)


class BacktestEngine:
    """Single-symbol backtester.

    Fill-before-signal ordering prevents look-ahead bias:
    - Bar t: process fills from previous bar's orders
    - Bar t: generate new orders from signal[t-1] (shifted)
    """

    def __init__(
        self,
        strategy: Strategy,
        symbol: str,
        data_feed: MarketDataFeed,
        risk_manager: RiskManager,
        broker: PaperBroker,
        portfolio: Portfolio,
        atr_window: int = 14,
    ):
        self.strategy = strategy
        self.symbol = symbol
        self.data_feed = data_feed
        self.risk_manager = risk_manager
        self.broker = broker
        self.portfolio = portfolio
        self.atr_window = atr_window

    def run(self) -> BacktestResult:
        # Fetch data
        df = self.data_feed.fetch_one(self.symbol)

        # Compute signals (vectorized — no look-ahead)
        raw_signals = self.strategy.generate_signals(df)
        # Shift by 1: today's signal acts on tomorrow's open
        signals = raw_signals.shift(1).fillna(0).astype(int)

        # Precompute ATR for position sizing
        atr_series = TechnicalIndicators.atr(
            df["High"], df["Low"], df["Close"], window=self.atr_window
        )

        # Build a close-price Series for equity curve reconstruction
        close_prices = df["Close"].rename(self.symbol)

        equity_history: list = []
        equity_index: list = []

        self.broker.reset()
        self.portfolio.reset()

        for i, (date, row) in enumerate(df.iterrows()):
            bar = {
                "Open": row["Open"],
                "High": row["High"],
                "Low": row["Low"],
                "Close": row["Close"],
                "Volume": row["Volume"],
                "timestamp": date,
            }

            # 1. Fill pending orders first (uses current bar's open)
            filled_orders = self.broker.process_bar(bar)
            for order in filled_orders:
                try:
                    self.portfolio.apply_fill(order)
                except ValueError:
                    pass  # skip if insufficient cash (shouldn't happen with proper sizing)

            # 2. Current equity for risk checks
            prices = {self.symbol: row["Close"]}
            current_equity = self.portfolio.market_value(prices)
            equity_history.append(current_equity)
            equity_index.append(date)

            # 3. Generate order from signal (look-ahead-free: shifted above)
            sig = signals.iloc[i]
            atr = atr_series.iloc[i] if i < len(atr_series) else np.nan

            if pd.isna(atr) or atr <= 0:
                continue

            equity_so_far = pd.Series(equity_history, index=equity_index)
            dd = self.risk_manager.current_drawdown(equity_so_far)
            if self.risk_manager.check_portfolio_halt(dd):
                continue

            held = self.portfolio.positions.get(self.symbol, 0)

            if sig == 1 and held == 0:
                # Enter long
                size = self.risk_manager.position_size(
                    sig, row["Close"], atr, current_equity
                )
                if size > 0:
                    order = Order(
                        symbol=self.symbol,
                        side="buy",
                        qty=size,
                        order_type="market",
                        timestamp=date,
                    )
                    self.broker.submit(order)

            elif sig == -1 and held > 0:
                # Exit long
                order = Order(
                    symbol=self.symbol,
                    side="sell",
                    qty=held,
                    order_type="market",
                    timestamp=date,
                )
                self.broker.submit(order)

        equity_curve = pd.Series(equity_history, index=equity_index, name="equity")

        return BacktestResult(
            equity_curve=equity_curve,
            trade_log=self.portfolio.to_dataframe(),
            portfolio=self.portfolio,
            signals=signals,
        )
