"""Layer 3 – Risk management: position sizing, stops, drawdown halts."""

import pandas as pd
import numpy as np


class RiskManager:
    """Controls position sizing and portfolio-level risk gates."""

    def __init__(
        self,
        max_position_pct: float = 0.10,
        risk_per_trade_pct: float = 0.02,
        stop_loss_atr_multiple: float = 2.0,
        max_drawdown_halt: float = 0.20,
    ):
        self.max_position_pct = max_position_pct
        self.risk_per_trade_pct = risk_per_trade_pct
        self.stop_loss_atr_multiple = stop_loss_atr_multiple
        self.max_drawdown_halt = max_drawdown_halt

    def position_size(
        self,
        signal: int,
        price: float,
        atr: float,
        equity: float,
    ) -> int:
        """ATR-based fixed-fractional position sizing.

        Risk amount = equity * risk_per_trade_pct
        Stop distance = atr * stop_loss_atr_multiple
        Shares = risk_amount / stop_distance, clipped to max_position_pct of equity.
        """
        if signal == 0 or price <= 0 or atr <= 0 or equity <= 0:
            return 0

        stop_distance = atr * self.stop_loss_atr_multiple
        risk_amount = equity * self.risk_per_trade_pct
        shares = int(risk_amount / stop_distance)

        max_shares = int(equity * self.max_position_pct / price)
        shares = min(shares, max_shares)
        return max(shares, 0)

    def stop_price(self, entry_price: float, atr: float, direction: int) -> float:
        """Hard stop level: entry ± atr_multiple * atr."""
        return entry_price - direction * self.stop_loss_atr_multiple * atr

    def check_portfolio_halt(self, current_drawdown: float) -> bool:
        """Return True (halt trading) when drawdown exceeds the limit."""
        return abs(current_drawdown) >= self.max_drawdown_halt

    def current_drawdown(self, equity_series: pd.Series) -> float:
        """Current peak-to-trough drawdown as a negative fraction."""
        if equity_series.empty:
            return 0.0
        peak = equity_series.cummax().iloc[-1]
        current = equity_series.iloc[-1]
        if peak == 0:
            return 0.0
        return (current - peak) / peak

    def filter_signals(
        self,
        signals: pd.Series,
        equity_series: pd.Series,
    ) -> pd.Series:
        """Zero out signals when drawdown halt is triggered."""
        signals = signals.copy()
        dd = self.current_drawdown(equity_series)
        if self.check_portfolio_halt(dd):
            signals[:] = 0
        return signals
