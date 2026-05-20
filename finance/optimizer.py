"""Layer 8 – Parameter optimizer: grid search + walk-forward (the feedback loop)."""

import copy
import itertools
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

from .strategy import Strategy
from .data import MarketDataFeed
from .risk import RiskManager
from .execution import PaperBroker
from .portfolio import Portfolio
from .backtest import BacktestEngine
from .report import PerformanceReport


@dataclass
class OptimizationResult:
    params: dict
    train_metrics: dict
    val_metrics: Optional[dict] = None
    objective_value: float = 0.0
    fold: int = 0


class ParameterOptimizer:
    """Grid search and walk-forward optimization — the feedback loop.

    Trains on historical data, validates out-of-sample to prevent overfitting.
    Best params are fed back into the live strategy.
    """

    OBJECTIVES = {"sharpe", "calmar", "profit_factor", "total_return", "cagr"}

    def __init__(
        self,
        strategy_class: type,
        symbol: str,
        data_feed: MarketDataFeed,
        param_grid: dict,
        objective: str = "sharpe",
        initial_cash: float = 100_000.0,
        risk_params: Optional[dict] = None,
    ):
        if objective not in self.OBJECTIVES:
            raise ValueError(f"objective must be one of {self.OBJECTIVES}")
        self.strategy_class = strategy_class
        self.symbol = symbol
        self.data_feed = data_feed
        self.param_grid = param_grid
        self.objective = objective
        self.initial_cash = initial_cash
        self.risk_params = risk_params or {}
        self._results: list = []

    def _param_combinations(self) -> list:
        keys = list(self.param_grid.keys())
        values = list(self.param_grid.values())
        return [dict(zip(keys, combo)) for combo in itertools.product(*values)]

    def _run_one(self, params: dict, data_feed: MarketDataFeed) -> dict:
        """Instantiate strategy with params and run a full backtest."""
        strategy = self.strategy_class()
        strategy.params = copy.deepcopy(params)

        risk_mgr = RiskManager(**self.risk_params)
        broker = PaperBroker()
        portfolio = Portfolio(self.initial_cash)

        engine = BacktestEngine(
            strategy=strategy,
            symbol=self.symbol,
            data_feed=data_feed,
            risk_manager=risk_mgr,
            broker=broker,
            portfolio=portfolio,
        )
        result = engine.run()
        report = PerformanceReport(result)
        return report.compute_metrics()

    def grid_search(self) -> list:
        """Exhaustive grid search. Returns list of OptimizationResult."""
        combos = self._param_combinations()
        results = []
        for params in combos:
            try:
                metrics = self._run_one(params, self.data_feed)
                obj = metrics.get(self.objective, 0.0)
                results.append(OptimizationResult(
                    params=params,
                    train_metrics=metrics,
                    objective_value=float(obj) if obj is not None and str(obj) != "inf" else 0.0,
                ))
            except Exception:
                pass

        results.sort(key=lambda r: r.objective_value, reverse=True)
        self._results = results
        return results

    def walk_forward(
        self, n_splits: int = 5, train_ratio: float = 0.7
    ) -> list:
        """Walk-forward optimization: train on past, validate on future.

        Returns one OptimizationResult per fold containing both
        in-sample (train_metrics) and out-of-sample (val_metrics).
        """
        all_data = self.data_feed.fetch_one(self.symbol)
        dates = all_data.index
        n = len(dates)
        fold_size = n // n_splits
        wf_results = []

        for fold in range(n_splits):
            start_idx = fold * fold_size
            end_idx = start_idx + fold_size

            split_idx = int(start_idx + (end_idx - start_idx) * train_ratio)
            train_start = str(dates[start_idx].date())
            train_end = str(dates[split_idx].date())
            val_end = str(dates[min(end_idx - 1, n - 1)].date())

            if train_start >= train_end:
                continue

            train_feed = MarketDataFeed(
                symbols=self.symbol,
                start=train_start,
                end=train_end,
                interval=self.data_feed.interval,
                cache_dir=self.data_feed.cache_dir,
            )
            val_feed = MarketDataFeed(
                symbols=self.symbol,
                start=train_end,
                end=val_end,
                interval=self.data_feed.interval,
                cache_dir=self.data_feed.cache_dir,
            )

            # Find best params on training window
            train_optimizer = ParameterOptimizer(
                strategy_class=self.strategy_class,
                symbol=self.symbol,
                data_feed=train_feed,
                param_grid=self.param_grid,
                objective=self.objective,
                initial_cash=self.initial_cash,
                risk_params=self.risk_params,
            )
            train_results = train_optimizer.grid_search()
            if not train_results:
                continue

            best = train_results[0]

            # Validate on out-of-sample window
            try:
                val_metrics = self._run_one(best.params, val_feed)
            except Exception:
                val_metrics = {}

            wf_results.append(OptimizationResult(
                params=best.params,
                train_metrics=best.train_metrics,
                val_metrics=val_metrics,
                objective_value=val_metrics.get(self.objective, 0.0) if val_metrics else 0.0,
                fold=fold + 1,
            ))

        self._results = wf_results
        return wf_results

    def best_params(self) -> dict:
        """Return params with highest objective from last search."""
        if not self._results:
            raise RuntimeError("Run grid_search() or walk_forward() first.")
        return max(self._results, key=lambda r: r.objective_value).params

    def summary(self) -> str:
        if not self._results:
            return "No results. Run grid_search() or walk_forward() first."
        lines = [
            f"{'Rank':<5} {'Objective':>10} {'Params'}",
            "-" * 70,
        ]
        for i, r in enumerate(self._results[:10], 1):
            param_str = ", ".join(f"{k}={v}" for k, v in r.params.items())
            lines.append(f"{i:<5} {r.objective_value:>10.4f}  {param_str}")
        return "\n".join(lines)
