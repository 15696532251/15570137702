"""Layer 7 – Performance reporting: metrics computation and visualization."""

import pandas as pd
import numpy as np
from .backtest import BacktestResult


class PerformanceReport:
    """Compute standard trading metrics and generate a visual report."""

    TRADING_DAYS = 252

    def __init__(self, result: BacktestResult, risk_free_rate: float = 0.04):
        self.result = result
        self.rf = risk_free_rate
        self._metrics: dict = {}

    def compute_metrics(self) -> dict:
        ec = self.result.equity_curve
        returns = ec.pct_change().dropna()

        self._metrics = {
            "total_return": self._total_return(ec),
            "cagr": self.cagr(ec),
            "sharpe": self.sharpe_ratio(returns),
            "sortino": self.sortino_ratio(returns),
            "max_drawdown": self.max_drawdown(ec),
            "calmar": self.calmar_ratio(ec),
            "win_rate": self.win_rate(),
            "profit_factor": self.profit_factor(),
            "total_trades": self._total_trades(),
            "avg_trade_return": self._avg_trade_return(),
        }
        self.result.metrics = self._metrics
        return self._metrics

    # ── Individual metrics ────────────────────────────────────────────────

    def _total_return(self, ec: pd.Series) -> float:
        if ec.empty or ec.iloc[0] == 0:
            return 0.0
        return (ec.iloc[-1] / ec.iloc[0]) - 1

    def cagr(self, ec: pd.Series = None) -> float:
        ec = ec if ec is not None else self.result.equity_curve
        if ec.empty or ec.iloc[0] == 0:
            return 0.0
        years = len(ec) / self.TRADING_DAYS
        if years <= 0:
            return 0.0
        return (ec.iloc[-1] / ec.iloc[0]) ** (1 / years) - 1

    def sharpe_ratio(self, returns: pd.Series = None) -> float:
        returns = returns if returns is not None else self.result.equity_curve.pct_change().dropna()
        if returns.std() == 0:
            return 0.0
        daily_rf = self.rf / self.TRADING_DAYS
        excess = returns - daily_rf
        return float(excess.mean() / excess.std() * np.sqrt(self.TRADING_DAYS))

    def sortino_ratio(self, returns: pd.Series = None) -> float:
        returns = returns if returns is not None else self.result.equity_curve.pct_change().dropna()
        daily_rf = self.rf / self.TRADING_DAYS
        excess = returns - daily_rf
        downside = returns[returns < 0]
        if downside.empty or downside.std() == 0:
            return 0.0
        return float(excess.mean() / downside.std() * np.sqrt(self.TRADING_DAYS))

    def max_drawdown(self, ec: pd.Series = None) -> float:
        ec = ec if ec is not None else self.result.equity_curve
        if ec.empty:
            return 0.0
        rolling_max = ec.cummax()
        drawdown = (ec - rolling_max) / rolling_max.replace(0, np.nan)
        return float(drawdown.min())

    def calmar_ratio(self, ec: pd.Series = None) -> float:
        ec = ec if ec is not None else self.result.equity_curve
        mdd = abs(self.max_drawdown(ec))
        if mdd == 0:
            return 0.0
        return self.cagr(ec) / mdd

    def win_rate(self) -> float:
        trades = self._closed_trades()
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if t["pnl"] > 0)
        return wins / len(trades)

    def profit_factor(self) -> float:
        trades = self._closed_trades()
        gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    def _total_trades(self) -> int:
        return len(self._closed_trades())

    def _avg_trade_return(self) -> float:
        trades = self._closed_trades()
        if not trades:
            return 0.0
        return float(np.mean([t["pnl_pct"] for t in trades]))

    def _closed_trades(self) -> list:
        """Pair buy/sell rows from trade_log to compute per-trade P&L."""
        df = self.result.trade_log
        if df.empty:
            return []
        trades = []
        opens: dict = {}
        for _, row in df.iterrows():
            sym = row["symbol"]
            if row["side"] == "buy":
                opens[sym] = {"price": row["price"], "qty": row["qty"]}
            elif row["side"] == "sell" and sym in opens:
                entry = opens.pop(sym)
                cost = entry["price"]
                exit_px = row["price"]
                qty = min(entry["qty"], row["qty"])
                pnl = qty * (exit_px - cost) - row["commission"]
                pnl_pct = (exit_px - cost) / cost if cost else 0.0
                trades.append({"symbol": sym, "pnl": pnl, "pnl_pct": pnl_pct, "qty": qty})
        return trades

    # ── Visualization ────────────────────────────────────────────────────

    def plot(self, output_path: str = "backtest_report.png") -> str:
        """Generate a 2×2 performance report and save to output_path."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.gridspec as gridspec
        except ImportError:
            raise ImportError("matplotlib is required: pip install matplotlib")

        ec = self.result.equity_curve
        returns = ec.pct_change().dropna()

        fig = plt.figure(figsize=(16, 10))
        fig.suptitle("Backtest Performance Report", fontsize=14, fontweight="bold")
        gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35)

        # ── Top-left: Equity curve + drawdown ────────────────────────────
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.plot(ec.index, ec.values, color="#2563eb", linewidth=1.5, label="Portfolio")
        ax1.set_title("Equity Curve")
        ax1.set_ylabel("Value ($)")
        ax1.legend(loc="upper left", fontsize=8)
        ax1.tick_params(axis="x", rotation=30)

        ax1b = ax1.twinx()
        dd = (ec - ec.cummax()) / ec.cummax().replace(0, float("nan"))
        ax1b.fill_between(ec.index, dd.values, 0, alpha=0.25, color="#dc2626", label="Drawdown")
        ax1b.set_ylabel("Drawdown", color="#dc2626")
        ax1b.tick_params(axis="y", labelcolor="#dc2626")

        # ── Top-right: Monthly returns heatmap ───────────────────────────
        ax2 = fig.add_subplot(gs[0, 1])
        if len(returns) >= 20:
            monthly = returns.resample("ME").apply(lambda x: (1 + x).prod() - 1)
            monthly_df = pd.DataFrame({"year": monthly.index.year, "month": monthly.index.month, "ret": monthly.values})
            pivot = monthly_df.pivot_table(index="year", columns="month", values="ret", aggfunc="sum").fillna(0)
            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            vmax = max(abs(pivot.values).max(), 0.01)
            im = ax2.imshow(pivot.values, cmap="RdYlGn", aspect="auto", vmin=-vmax, vmax=vmax)
            ax2.set_xticks(range(len(pivot.columns)))
            ax2.set_xticklabels([month_names[m - 1] for m in pivot.columns], fontsize=7)
            ax2.set_yticks(range(len(pivot.index)))
            ax2.set_yticklabels(pivot.index.astype(str), fontsize=7)
            for r in range(pivot.shape[0]):
                for c in range(pivot.shape[1]):
                    ax2.text(c, r, f"{pivot.values[r, c]:.1%}", ha="center", va="center", fontsize=6)
            plt.colorbar(im, ax=ax2, label="Monthly Return")
        ax2.set_title("Monthly Returns")

        # ── Bottom-left: Trade P&L distribution ─────────────────────────
        ax3 = fig.add_subplot(gs[1, 0])
        trades = self._closed_trades()
        if trades:
            pnls = [t["pnl"] for t in trades]
            colors = ["#16a34a" if p > 0 else "#dc2626" for p in pnls]
            ax3.bar(range(len(pnls)), pnls, color=colors, edgecolor="none")
            ax3.axhline(0, color="black", linewidth=0.8)
        ax3.set_title(f"Trade P&L ({len(trades)} trades)")
        ax3.set_xlabel("Trade #")
        ax3.set_ylabel("P&L ($)")

        # ── Bottom-right: Rolling 63-day Sharpe ──────────────────────────
        ax4 = fig.add_subplot(gs[1, 1])
        if len(returns) >= 63:
            daily_rf = self.rf / self.TRADING_DAYS
            excess = returns - daily_rf
            rolling_sharpe = excess.rolling(63).mean() / excess.rolling(63).std() * np.sqrt(self.TRADING_DAYS)
            ax4.plot(rolling_sharpe.index, rolling_sharpe.values, color="#7c3aed", linewidth=1.2)
            ax4.axhline(0, color="black", linewidth=0.8, linestyle="--")
        ax4.set_title("Rolling 63-day Sharpe")
        ax4.set_ylabel("Sharpe")
        ax4.tick_params(axis="x", rotation=30)

        # ── Metrics text box ─────────────────────────────────────────────
        if self._metrics:
            m = self._metrics
            txt = (
                f"Total Return: {m.get('total_return', 0):.1%}   "
                f"CAGR: {m.get('cagr', 0):.1%}   "
                f"Sharpe: {m.get('sharpe', 0):.2f}   "
                f"Max DD: {m.get('max_drawdown', 0):.1%}   "
                f"Win Rate: {m.get('win_rate', 0):.1%}   "
                f"Profit Factor: {m.get('profit_factor', 0):.2f}"
            )
            fig.text(0.5, 0.02, txt, ha="center", fontsize=9, style="italic",
                     bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.4))

        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return output_path

    def summary(self) -> str:
        m = self._metrics or self.compute_metrics()
        lines = [
            "=" * 52,
            "  BACKTEST PERFORMANCE SUMMARY",
            "=" * 52,
            f"  Total Return    : {m['total_return']:>10.2%}",
            f"  CAGR            : {m['cagr']:>10.2%}",
            f"  Sharpe Ratio    : {m['sharpe']:>10.2f}",
            f"  Sortino Ratio   : {m['sortino']:>10.2f}",
            f"  Max Drawdown    : {m['max_drawdown']:>10.2%}",
            f"  Calmar Ratio    : {m['calmar']:>10.2f}",
            f"  Win Rate        : {m['win_rate']:>10.2%}",
            f"  Profit Factor   : {m['profit_factor']:>10.2f}",
            f"  Total Trades    : {m['total_trades']:>10d}",
            f"  Avg Trade Return: {m['avg_trade_return']:>10.2%}",
            "=" * 52,
        ]
        return "\n".join(lines)
