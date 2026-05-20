"""Financial secondary market investment closed-loop system.

Layers (data flows top to bottom):
  1. data.py        – MarketDataFeed (OHLCV ingestion + caching)
  2. signals.py     – TechnicalIndicators + SignalEngine
  3. strategy.py    – Strategy base class
  4. risk.py        – RiskManager (sizing, stops, drawdown halt)
  5. execution.py   – PaperBroker (order simulation)
  6. portfolio.py   – Portfolio (state, P&L)
  7. backtest.py    – BacktestEngine (event loop)
  8. report.py      – PerformanceReport (metrics, plots)
  9. optimizer.py   – ParameterOptimizer (feedback loop)
"""

from .data import MarketDataFeed
from .signals import TechnicalIndicators, SignalEngine
from .strategy import Strategy
from .risk import RiskManager
from .execution import Order, PaperBroker
from .portfolio import Portfolio
from .backtest import BacktestEngine, BacktestResult
from .report import PerformanceReport
from .optimizer import ParameterOptimizer, OptimizationResult
from .example_strategy import (
    DualMACrossover,
    MACDStrategy,
    BollingerMeanReversion,
    RSIMomentum,
)
from .web3_config import CHAINS, V3_FEE_LOW, V3_FEE_MEDIUM, V3_FEE_HIGH
from .web3_wallet import Web3Wallet
from .web3_data import OnChainPriceFeed, BarBuilder
from .web3_broker import Web3Broker, Web3LiveTrader, SwapResult

__all__ = [
    "MarketDataFeed",
    "TechnicalIndicators",
    "SignalEngine",
    "Strategy",
    "RiskManager",
    "Order",
    "PaperBroker",
    "Portfolio",
    "BacktestEngine",
    "BacktestResult",
    "PerformanceReport",
    "ParameterOptimizer",
    "OptimizationResult",
    "DualMACrossover",
    "MACDStrategy",
    "BollingerMeanReversion",
    "RSIMomentum",
    # Web3
    "CHAINS",
    "V3_FEE_LOW",
    "V3_FEE_MEDIUM",
    "V3_FEE_HIGH",
    "Web3Wallet",
    "OnChainPriceFeed",
    "BarBuilder",
    "Web3Broker",
    "Web3LiveTrader",
    "SwapResult",
]
