#!/usr/bin/env python3
"""
Demo: Full closed-loop backtest with DualMACrossover on AAPL.

Run: python -m finance.demo
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from finance import (
    MarketDataFeed,
    DualMACrossover,
    MACDStrategy,
    BollingerMeanReversion,
    RiskManager,
    PaperBroker,
    Portfolio,
    BacktestEngine,
    PerformanceReport,
    ParameterOptimizer,
)


def run_single_backtest(symbol: str = "AAPL", start: str = "2020-01-01", end: str = "2024-01-01"):
    print(f"\n{'='*60}")
    print(f"  Single Backtest: DualMACrossover on {symbol}")
    print(f"  Period: {start} → {end}")
    print(f"{'='*60}")

    feed = MarketDataFeed([symbol], start=start, end=end)
    strategy = DualMACrossover()
    strategy.params.update({"fast_ma": 10, "slow_ma": 30, "rsi_window": 14})

    engine = BacktestEngine(
        strategy=strategy,
        symbol=symbol,
        data_feed=feed,
        risk_manager=RiskManager(
            max_position_pct=0.15,
            risk_per_trade_pct=0.02,
            stop_loss_atr_multiple=2.0,
            max_drawdown_halt=0.25,
        ),
        broker=PaperBroker(commission_per_share=0.005, slippage_bps=5),
        portfolio=Portfolio(initial_cash=100_000),
    )

    result = engine.run()
    report = PerformanceReport(result, risk_free_rate=0.04)
    print(report.summary())

    # Save chart
    output = f"backtest_{symbol}_{start[:4]}_{end[:4]}.png"
    report.plot(output)
    print(f"\n  Chart saved: {output}")

    return result, report


def run_strategy_comparison(symbol: str = "SPY", start: str = "2018-01-01", end: str = "2024-01-01"):
    print(f"\n{'='*60}")
    print(f"  Strategy Comparison on {symbol}")
    print(f"{'='*60}")

    strategies = {
        "DualMA (SMA 10/30)": DualMACrossover(),
        "MACD (12/26/9)": MACDStrategy(),
        "Bollinger MR": BollingerMeanReversion(),
    }

    feed = MarketDataFeed([symbol], start=start, end=end)

    for name, strategy in strategies.items():
        engine = BacktestEngine(
            strategy=strategy,
            symbol=symbol,
            data_feed=feed,
            risk_manager=RiskManager(),
            broker=PaperBroker(),
            portfolio=Portfolio(initial_cash=100_000),
        )
        result = engine.run()
        report = PerformanceReport(result)
        m = report.compute_metrics()
        print(
            f"  {name:<22} | "
            f"Return: {m['total_return']:>6.1%} | "
            f"Sharpe: {m['sharpe']:>5.2f} | "
            f"MaxDD: {m['max_drawdown']:>6.1%} | "
            f"WinRate: {m['win_rate']:>5.1%} | "
            f"Trades: {m['total_trades']:>3d}"
        )


def run_parameter_optimization(symbol: str = "AAPL", start: str = "2018-01-01", end: str = "2024-01-01"):
    print(f"\n{'='*60}")
    print(f"  Walk-Forward Optimization on {symbol}")
    print(f"{'='*60}")

    feed = MarketDataFeed([symbol], start=start, end=end)

    opt = ParameterOptimizer(
        strategy_class=DualMACrossover,
        symbol=symbol,
        data_feed=feed,
        param_grid={
            "fast_ma": [5, 10, 20],
            "slow_ma": [30, 50, 100],
            "rsi_overbought": [65, 70, 75],
        },
        objective="sharpe",
        initial_cash=100_000,
    )

    print("  Running grid search...")
    gs_results = opt.grid_search()
    print(f"\n  Top 5 by Sharpe Ratio:")
    print(opt.summary())

    best = opt.best_params()
    print(f"\n  Best params: {best}")

    return opt


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    # 1. Single backtest
    result, report = run_single_backtest(symbol)

    # 2. Strategy comparison
    run_strategy_comparison("SPY" if symbol == "AAPL" else symbol)

    # 3. Parameter optimization (grid search)
    run_parameter_optimization(symbol)
