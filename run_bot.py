#!/usr/bin/env python3
"""
启动脚本 —— 直接运行这个文件就可以启动机器人

使用方法:
  python run_bot.py          # 启动持续运行（按 Ctrl+C 停止）
  python run_bot.py --once   # 只检查一次信号（测试用）
  python run_bot.py --backtest  # 先回测再启动
"""

import sys
import logging
import argparse

# 配置日志（同时输出到终端和文件）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)

sys.path.insert(0, ".")
import config as cfg
from finance.cex_broker import CEXBroker
from finance.live_trader import CEXLiveTrader
from finance.example_strategy import DualMACrossover


def build_strategy():
    s = DualMACrossover()
    s.params.update({
        "fast_ma":       cfg.FAST_MA,
        "slow_ma":       cfg.SLOW_MA,
        "ma_type":       cfg.MA_TYPE,
        "rsi_overbought": cfg.RSI_CAP,
    })
    return s


def run_backtest():
    """先用历史数据验证当前参数，再决定是否开启实盘。"""
    import pandas as pd
    from finance.data import MarketDataFeed
    from finance.risk import RiskManager
    from finance.execution import PaperBroker
    from finance.portfolio import Portfolio
    from finance.backtest import BacktestEngine
    from finance.report import PerformanceReport

    print("\n正在回测当前参数配置，请稍候...\n")

    # 用 ccxt 拉历史数据
    broker = CEXBroker(
        exchange_id=cfg.EXCHANGE,
        api_key=cfg.API_KEY,
        api_secret=cfg.API_SECRET,
        dry_run=True,
    )

    try:
        ohlcv = broker.get_ohlcv(cfg.SYMBOL, cfg.TIMEFRAME, limit=500)
        df = pd.DataFrame(ohlcv, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms")
        df.set_index("ts", inplace=True)
    except Exception as e:
        print(f"获取数据失败（可能是API Key未填写）: {e}")
        print("使用内置模拟数据演示回测...")
        df = _generate_demo_data()

    # 直连数据
    class DirectFeed:
        def __init__(self, df, sym): self._df = df; self.symbol = sym; self.interval = "1d"; self.cache_dir = "/tmp"
        def fetch_one(self, s): return self._df
        def fetch(self): return {self.symbol: self._df}

    sym = cfg.SYMBOL.replace("/", "-")
    engine = BacktestEngine(
        strategy=build_strategy(),
        symbol=sym,
        data_feed=DirectFeed(df, sym),
        risk_manager=RiskManager(max_drawdown_halt=cfg.MAX_DRAWDOWN_HALT),
        broker=PaperBroker(slippage_bps=10),
        portfolio=Portfolio(initial_cash=10_000),
    )
    result = engine.run()
    report = PerformanceReport(result)
    print(report.summary())

    m = report.compute_metrics()
    if m["sharpe"] < 0.5:
        print("⚠️  警告：当前参数Sharpe低于0.5，建议调整策略参数再实盘")
    elif m["max_drawdown"] < -0.25:
        print("⚠️  警告：最大回撤超过25%，建议降低单次交易金额")
    else:
        print("✓ 回测结果良好，可以考虑开启实盘（先用小资金测试）")

    return result


def _generate_demo_data():
    """没有网络时用模拟数据演示。"""
    import numpy as np, pandas as pd
    np.random.seed(42)
    dates = pd.date_range("2022-01-01", "2025-06-01", freq="D")
    n = len(dates)
    anchors = pd.Series(
        [47000, 16000, 17000, 42000, 69000, 95000, 103000],
        index=pd.to_datetime(["2022-01-01","2022-11-10","2023-01-01","2023-12-31","2024-11-01","2025-01-01","2025-06-01"])
    ).reindex(dates).interpolate()
    close = anchors.values * (1 + np.random.normal(0, 0.03, n))
    return pd.DataFrame({
        "Open": close * (1 + np.random.normal(0, 0.005, n)),
        "High": close * (1 + np.abs(np.random.normal(0, 0.015, n))),
        "Low":  close * (1 - np.abs(np.random.normal(0, 0.015, n))),
        "Close": close,
        "Volume": np.random.lognormal(21, 0.5, n),
    }, index=dates)


def main():
    parser = argparse.ArgumentParser(description="趋势跟随交易机器人")
    parser.add_argument("--once",      action="store_true", help="只检查一次信号")
    parser.add_argument("--backtest",  action="store_true", help="先回测再启动")
    args = parser.parse_args()

    # 启动前检查
    if cfg.API_KEY == "在这里填你的API_KEY":
        print("\n⚠️  请先编辑 config.py，填写你的 API Key！\n")
        print("  config.py 在项目根目录，用记事本或任意文本编辑器打开")
        if not args.backtest:
            return

    if cfg.DRY_RUN:
        print("\n" + "="*50)
        print("  当前是【模拟模式】，不会真实下单")
        print("  确认策略正常后，把 config.py 里 DRY_RUN 改为 False")
        print("="*50 + "\n")

    # 可选：先回测
    if args.backtest:
        run_backtest()
        ans = input("\n是否继续启动实盘机器人？(y/n): ").strip().lower()
        if ans != "y":
            print("已退出")
            return

    # 初始化交易所连接
    broker = CEXBroker(
        exchange_id=cfg.EXCHANGE,
        api_key=cfg.API_KEY,
        api_secret=cfg.API_SECRET,
        passphrase=cfg.OKX_PASSWORD,
        dry_run=cfg.DRY_RUN,
        testnet=cfg.USE_TESTNET,
    )

    # 初始化交易机器人
    trader = CEXLiveTrader(
        broker=broker,
        symbol=cfg.SYMBOL,
        strategy=build_strategy(),
        trade_usdt=cfg.TRADE_USDT,
        check_interval_sec=cfg.CHECK_HOURS * 3600,
        timeframe=cfg.TIMEFRAME,
    )

    if args.once:
        trader.run_once()
        trader.print_summary()
    else:
        trader.run_loop()


if __name__ == "__main__":
    main()
