"""Layer 4 – Paper trading broker: order simulation with slippage and commission."""

import uuid
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class Order:
    symbol: str
    side: str               # "buy" | "sell"
    qty: int
    order_type: str         # "market" | "limit"
    timestamp: pd.Timestamp
    limit_price: Optional[float] = None
    status: str = "pending" # -> "filled" | "rejected" | "cancelled"
    fill_price: Optional[float] = None
    fill_time: Optional[pd.Timestamp] = None
    order_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    commission: float = 0.0


class PaperBroker:
    """Simulates order execution with slippage, commission and fill delay."""

    def __init__(
        self,
        commission_per_share: float = 0.005,
        slippage_bps: int = 5,
        fill_delay_bars: int = 1,
    ):
        self.commission_per_share = commission_per_share
        self.slippage_bps = slippage_bps
        self.fill_delay_bars = fill_delay_bars
        self._pending: dict = {}   # order_id -> (Order, bars_remaining)
        self._all_orders: list = []

    def submit(self, order: Order) -> str:
        """Queue an order. Returns order_id."""
        if order.qty <= 0:
            order.status = "rejected"
            self._all_orders.append(order)
            return order.order_id
        self._pending[order.order_id] = [order, self.fill_delay_bars]
        self._all_orders.append(order)
        return order.order_id

    def process_bar(self, bar: dict) -> list:
        """Attempt to fill pending orders against the current bar's OHLC.

        Returns list of newly filled Order objects.
        """
        filled = []
        to_remove = []

        for oid, (order, delay) in self._pending.items():
            if delay > 0:
                self._pending[oid][1] -= 1
                continue

            open_px = bar.get("Open", bar.get("open"))
            high_px = bar.get("High", bar.get("high"))
            low_px  = bar.get("Low",  bar.get("low"))

            if open_px is None:
                continue

            fill_px = None
            slip = self.slippage_bps / 10_000

            if order.order_type == "market":
                if order.side == "buy":
                    fill_px = open_px * (1 + slip)
                else:
                    fill_px = open_px * (1 - slip)

            elif order.order_type == "limit" and order.limit_price is not None:
                if order.side == "buy" and low_px is not None and low_px <= order.limit_price:
                    fill_px = min(order.limit_price, open_px)
                elif order.side == "sell" and high_px is not None and high_px >= order.limit_price:
                    fill_px = max(order.limit_price, open_px)

            if fill_px is not None:
                order.fill_price = round(fill_px, 4)
                order.fill_time = bar.get("timestamp", bar.get("Timestamp"))
                order.commission = round(self.commission_per_share * order.qty, 4)
                order.status = "filled"
                filled.append(order)
                to_remove.append(oid)

        for oid in to_remove:
            del self._pending[oid]

        return filled

    def cancel(self, order_id: str) -> bool:
        if order_id in self._pending:
            self._pending[order_id][0].status = "cancelled"
            del self._pending[order_id]
            return True
        return False

    @property
    def open_orders(self) -> list:
        return [entry[0] for entry in self._pending.values()]

    @property
    def all_orders(self) -> list:
        return list(self._all_orders)

    def reset(self) -> None:
        self._pending.clear()
        self._all_orders.clear()
