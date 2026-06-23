"""CEX交易执行层：通过 ccxt 连接 Binance/OKX/Bybit 下单。

支持的交易所: binance, okx, bybit, gate
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class LiveOrder:
    order_id: str
    symbol: str
    side: str           # "buy" | "sell"
    qty: float
    price: float
    status: str         # "open" | "filled" | "cancelled" | "failed"
    fee: float = 0.0
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    timestamp: str = ""
    raw: dict = field(default_factory=dict)


class CEXBroker:
    """通过 ccxt 在中心化交易所执行交易。

    安全原则：
    - API Key 只开「现货交易」权限，不开提币权限
    - dry_run=True 时只模拟下单，不真实执行
    """

    def __init__(
        self,
        exchange_id: str = "binance",   # binance / okx / bybit / gate
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",           # OKX 需要
        dry_run: bool = True,
        testnet: bool = False,          # 使用交易所模拟盘
    ):
        self.exchange_id = exchange_id
        self.dry_run = dry_run
        self.testnet = testnet
        self._exchange = self._init_exchange(exchange_id, api_key, api_secret, passphrase, testnet)
        self._order_log: list = []

    def _init_exchange(self, exchange_id, api_key, api_secret, passphrase, testnet):
        try:
            import ccxt
        except ImportError:
            raise ImportError("请安装 ccxt: pip install ccxt")

        cls = getattr(ccxt, exchange_id)
        params = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        }
        if passphrase:
            params["password"] = passphrase

        exchange = cls(params)

        if testnet:
            if hasattr(exchange, "set_sandbox_mode"):
                exchange.set_sandbox_mode(True)
            elif "test" in exchange.urls:
                exchange.urls["api"] = exchange.urls["test"]

        return exchange

    # ── 行情 ──────────────────────────────────────────────────────────────────

    def get_price(self, symbol: str) -> float:
        """获取最新成交价，例如 symbol='BTC/USDT'"""
        ticker = self._exchange.fetch_ticker(symbol)
        return float(ticker["last"])

    def get_balance(self, currency: str = "USDT") -> float:
        """获取账户可用余额"""
        balance = self._exchange.fetch_balance()
        return float(balance.get(currency, {}).get("free", 0))

    def get_ohlcv(self, symbol: str, timeframe: str = "1d", limit: int = 300) -> list:
        """拉取K线数据，返回 [[timestamp, O, H, L, C, V], ...]"""
        return self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    # ── 下单 ──────────────────────────────────────────────────────────────────

    def market_buy(
        self,
        symbol: str,
        usdt_amount: float,
        slippage_pct: float = 0.5,
    ) -> LiveOrder:
        """用 USDT 金额市价买入。例如用100U买BTC。"""
        price = self.get_price(symbol)
        qty = usdt_amount / price

        if self.dry_run:
            log.info("[模拟] 市价买入 %.6f %s @ %.2f USDT", qty, symbol, price)
            order = LiveOrder(
                order_id="DRY-" + str(int(time.time())),
                symbol=symbol, side="buy", qty=qty,
                price=price, status="filled",
                filled_qty=qty, avg_fill_price=price,
            )
            self._order_log.append(order)
            return order

        try:
            # 大多数交易所用"数量"下单，部分支持"金额"下单
            raw = self._exchange.create_market_buy_order(symbol, qty)
            order = self._parse_order(raw)
            self._order_log.append(order)
            log.info("买入成功: %s 数量=%.6f 价格=%.2f", symbol, qty, price)
            return order
        except Exception as e:
            log.error("买入失败: %s", e)
            return LiveOrder(order_id="", symbol=symbol, side="buy",
                             qty=qty, price=price, status="failed")

    def market_sell(
        self,
        symbol: str,
        qty: float,
    ) -> LiveOrder:
        """市价卖出指定数量。"""
        price = self.get_price(symbol)

        if self.dry_run:
            log.info("[模拟] 市价卖出 %.6f %s @ %.2f USDT", qty, symbol, price)
            order = LiveOrder(
                order_id="DRY-" + str(int(time.time())),
                symbol=symbol, side="sell", qty=qty,
                price=price, status="filled",
                filled_qty=qty, avg_fill_price=price,
            )
            self._order_log.append(order)
            return order

        try:
            raw = self._exchange.create_market_sell_order(symbol, qty)
            order = self._parse_order(raw)
            self._order_log.append(order)
            log.info("卖出成功: %s 数量=%.6f 价格=%.2f", symbol, qty, price)
            return order
        except Exception as e:
            log.error("卖出失败: %s", e)
            return LiveOrder(order_id="", symbol=symbol, side="sell",
                             qty=qty, price=price, status="failed")

    def _parse_order(self, raw: dict) -> LiveOrder:
        return LiveOrder(
            order_id=str(raw.get("id", "")),
            symbol=raw.get("symbol", ""),
            side=raw.get("side", ""),
            qty=float(raw.get("amount", 0)),
            price=float(raw.get("price") or raw.get("average") or 0),
            status=raw.get("status", ""),
            fee=float((raw.get("fee") or {}).get("cost", 0)),
            filled_qty=float(raw.get("filled", 0)),
            avg_fill_price=float(raw.get("average") or 0),
            timestamp=str(raw.get("datetime", "")),
            raw=raw,
        )

    @property
    def order_history(self) -> list:
        return list(self._order_log)
