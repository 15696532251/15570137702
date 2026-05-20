"""Layer 5 – Portfolio state: cash, positions, P&L tracking."""

import pandas as pd
from .execution import Order


class Portfolio:
    """Tracks cash, positions, cost basis and trade history."""

    def __init__(self, initial_cash: float = 100_000.0):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: dict = {}    # symbol -> shares (int)
        self.cost_basis: dict = {}   # symbol -> avg cost per share (float)
        self.trade_log: list = []

    def apply_fill(self, order: Order) -> None:
        """Update state from a filled order. Raises on insufficient cash."""
        if order.status != "filled" or order.fill_price is None:
            return

        symbol = order.symbol
        qty = order.qty
        price = order.fill_price
        commission = order.commission

        if order.side == "buy":
            cost = qty * price + commission
            if cost > self.cash + 1e-6:
                raise ValueError(
                    f"Insufficient cash: need {cost:.2f}, have {self.cash:.2f}"
                )
            self.cash -= cost
            prev_qty = self.positions.get(symbol, 0)
            prev_basis = self.cost_basis.get(symbol, 0.0)
            new_qty = prev_qty + qty
            # FIFO average cost update
            if new_qty > 0:
                self.cost_basis[symbol] = (
                    (prev_qty * prev_basis + qty * price) / new_qty
                )
            self.positions[symbol] = new_qty

        elif order.side == "sell":
            held = self.positions.get(symbol, 0)
            actual_qty = min(qty, held)
            if actual_qty <= 0:
                return
            proceeds = actual_qty * price - commission
            self.cash += proceeds
            self.positions[symbol] = held - actual_qty
            if self.positions[symbol] == 0:
                del self.positions[symbol]
                del self.cost_basis[symbol]

        self.trade_log.append(
            {
                "timestamp": order.fill_time,
                "symbol": symbol,
                "side": order.side,
                "qty": qty,
                "price": price,
                "commission": commission,
                "cash_after": round(self.cash, 4),
            }
        )

    def market_value(self, prices: dict) -> float:
        """Total portfolio value: cash + sum(qty * price)."""
        equity = self.cash
        for sym, qty in self.positions.items():
            equity += qty * prices.get(sym, 0.0)
        return equity

    def unrealized_pnl(self, prices: dict) -> dict:
        result = {}
        for sym, qty in self.positions.items():
            current_price = prices.get(sym, 0.0)
            basis = self.cost_basis.get(sym, current_price)
            result[sym] = qty * (current_price - basis)
        return result

    def realized_pnl(self) -> float:
        """Realized P&L from closed trades (FIFO)."""
        pnl = 0.0
        for trade in self.trade_log:
            if trade["side"] == "sell":
                # Approximate: use recorded price vs cost basis at time of sale
                pnl += trade["price"] * trade["qty"] - trade["commission"]
        return pnl

    def equity_curve(self, price_history: pd.DataFrame) -> pd.Series:
        """Reconstruct daily portfolio value from trade_log + price history.

        price_history: DataFrame with symbol columns and DatetimeIndex.
        """
        cash = self.initial_cash
        positions: dict = {}
        cost_basis: dict = {}
        daily_values = []

        trade_df = pd.DataFrame(self.trade_log) if self.trade_log else pd.DataFrame()
        if not trade_df.empty:
            trade_df["timestamp"] = pd.to_datetime(trade_df["timestamp"])
            trade_df = trade_df.sort_values("timestamp")

        for date in price_history.index:
            if not trade_df.empty:
                day_trades = trade_df[trade_df["timestamp"].dt.normalize() == date]
                for _, t in day_trades.iterrows():
                    sym, side, qty, price, comm = (
                        t["symbol"], t["side"], t["qty"], t["price"], t["commission"]
                    )
                    if side == "buy":
                        cash -= qty * price + comm
                        prev = positions.get(sym, 0)
                        new_qty = prev + qty
                        prev_basis = cost_basis.get(sym, price)
                        cost_basis[sym] = (prev * prev_basis + qty * price) / new_qty if new_qty else price
                        positions[sym] = new_qty
                    else:
                        cash += qty * price - comm
                        positions[sym] = max(positions.get(sym, 0) - qty, 0)

            equity = cash
            for sym, qty in positions.items():
                if sym in price_history.columns:
                    px = price_history.loc[date, sym]
                    if pd.notna(px):
                        equity += qty * px
                elif hasattr(price_history.columns, "levels"):
                    try:
                        px = price_history.loc[date, (sym, "Close")]
                        if pd.notna(px):
                            equity += qty * px
                    except KeyError:
                        pass
            daily_values.append(equity)

        return pd.Series(daily_values, index=price_history.index, name="equity")

    def to_dataframe(self) -> pd.DataFrame:
        if not self.trade_log:
            return pd.DataFrame(
                columns=["timestamp", "symbol", "side", "qty", "price", "commission", "cash_after"]
            )
        return pd.DataFrame(self.trade_log)

    def reset(self) -> None:
        self.cash = self.initial_cash
        self.positions.clear()
        self.cost_basis.clear()
        self.trade_log.clear()
