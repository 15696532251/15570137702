"""实盘交易主循环：每天收盘后检查信号，决定是否买卖。"""

import time
import logging
import pandas as pd
import numpy as np
from .cex_broker import CEXBroker
from .example_strategy import DualMACrossover
from .signals import TechnicalIndicators as TI

log = logging.getLogger(__name__)


class CEXLiveTrader:
    """连接 Binance 的趋势跟随实盘机器人。

    工作流程（每个检查周期）：
    1. 从交易所拉取最新K线
    2. 计算均线信号
    3. 信号变化时自动买入/卖出
    4. 记录每次操作
    """

    def __init__(
        self,
        broker: CEXBroker,
        symbol: str = "BTC/USDT",
        strategy=None,
        trade_usdt: float = 100.0,   # 每次买入金额（USDT）
        check_interval_sec: int = 3600,  # 每小时检查一次（日线策略可设86400）
        timeframe: str = "1d",
        min_bars: int = 60,
    ):
        self.broker = broker
        self.symbol = symbol
        self.strategy = strategy or DualMACrossover()
        self.trade_usdt = trade_usdt
        self.check_interval_sec = check_interval_sec
        self.timeframe = timeframe
        self.min_bars = min_bars
        self._position_qty: float = 0.0   # 当前持仓数量
        self._last_signal: int = 0
        self._running = False
        self.trade_log: list = []

    def _fetch_data(self) -> pd.DataFrame:
        """拉取K线，转为 DataFrame。"""
        ohlcv = self.broker.get_ohlcv(self.symbol, self.timeframe, limit=300)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    def _get_signal(self, df: pd.DataFrame) -> int:
        """计算当前信号：+1 买，-1 卖，0 不动。"""
        signals = self.strategy.generate_signals(df)
        return int(signals.iloc[-2])  # 用倒数第二根K线（已确认）

    def _check_and_trade(self) -> None:
        """核心逻辑：拉数据 → 计算信号 → 执行操作。"""
        try:
            df = self._fetch_data()
            if len(df) < self.min_bars:
                log.info("K线数量不足 (%d/%d)，等待更多数据", len(df), self.min_bars)
                return

            signal = self._get_signal(df)
            price = self.broker.get_price(self.symbol)
            balance = self.broker.get_balance("USDT")

            log.info("当前价格: %.2f USDT | 信号: %+d | 持仓: %.6f | 余额: %.2f USDT",
                     price, signal, self._position_qty, balance)

            if signal == 1 and self._last_signal != 1 and self._position_qty == 0:
                # 出现买入信号且当前没有持仓
                usdt_to_use = min(self.trade_usdt, balance * 0.95)  # 最多用95%余额
                if usdt_to_use < 10:
                    log.warning("USDT余额不足10U，跳过买入")
                    return
                order = self.broker.market_buy(self.symbol, usdt_to_use)
                if order.status == "filled":
                    self._position_qty = order.filled_qty
                    self._last_signal = 1
                    self._log_trade("买入", price, order.filled_qty, usdt_to_use)

            elif signal == -1 and self._last_signal == 1 and self._position_qty > 0:
                # 出现卖出信号且有持仓
                order = self.broker.market_sell(self.symbol, self._position_qty)
                if order.status == "filled":
                    proceeds = self._position_qty * price
                    self._log_trade("卖出", price, self._position_qty, proceeds)
                    self._position_qty = 0.0
                    self._last_signal = -1

        except Exception as e:
            log.error("检查周期出错: %s", e)

    def _log_trade(self, action: str, price: float, qty: float, value: float) -> None:
        entry = {
            "时间": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
            "操作": action,
            "价格": f"${price:,.2f}",
            "数量": f"{qty:.6f}",
            "金额": f"${value:,.2f}",
        }
        self.trade_log.append(entry)
        log.info("✓ %s | 价格 %.2f | 数量 %.6f | 金额 %.2f", action, price, qty, value)

    def run_once(self) -> None:
        """只执行一次检查（用于手动触发或定时任务）。"""
        self._check_and_trade()

    def run_loop(self) -> None:
        """持续运行，每 check_interval_sec 秒检查一次。Ctrl+C 停止。"""
        self._running = True
        log.info("=" * 50)
        log.info("实盘机器人启动")
        log.info("交易对: %s | 策略: %s | 每次金额: %.0f USDT",
                 self.symbol, self.strategy.name(), self.trade_usdt)
        log.info("检查间隔: %d 秒 | 模拟模式: %s",
                 self.check_interval_sec, self.broker.dry_run)
        log.info("=" * 50)

        while self._running:
            self._check_and_trade()
            log.info("下次检查: %d 秒后", self.check_interval_sec)
            try:
                time.sleep(self.check_interval_sec)
            except KeyboardInterrupt:
                log.info("用户停止机器人")
                self._running = False

    def stop(self) -> None:
        self._running = False

    def print_summary(self) -> None:
        if not self.trade_log:
            print("暂无交易记录")
            return
        print("\n" + "=" * 50)
        print("  交易记录")
        print("=" * 50)
        for t in self.trade_log:
            print(f"  {t['时间']}  {t['操作']:4}  {t['价格']:>12}  金额: {t['金额']}")
        print("=" * 50)
