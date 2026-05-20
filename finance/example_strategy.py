"""Example strategies demonstrating the framework's signal generation interface."""

import pandas as pd
import numpy as np
from .strategy import Strategy
from .signals import TechnicalIndicators as TI


class DualMACrossover(Strategy):
    """Long when fast MA crosses above slow MA (with RSI filter).

    Exit when fast MA crosses below slow MA.
    No shorting — long-only.
    """

    params = {
        "fast_ma": 10,
        "slow_ma": 30,
        "rsi_window": 14,
        "rsi_overbought": 70,
        "ma_type": "sma",   # "sma" | "ema"
    }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["Close"]
        p = self.params

        if p.get("ma_type") == "ema":
            fast = TI.ema(close, p["fast_ma"])
            slow = TI.ema(close, p["slow_ma"])
        else:
            fast = TI.sma(close, p["fast_ma"])
            slow = TI.sma(close, p["slow_ma"])

        rsi = TI.rsi(close, p["rsi_window"])

        cross_up = (fast > slow) & (fast.shift(1) <= slow.shift(1))
        cross_down = (fast < slow) & (fast.shift(1) >= slow.shift(1))

        signal = pd.Series(0, index=data.index)
        signal[cross_up & (rsi < p["rsi_overbought"])] = 1
        signal[cross_down] = -1
        return signal


class MACDStrategy(Strategy):
    """Trade MACD histogram crossovers with ATR-based trend filter."""

    params = {
        "fast": 12,
        "slow": 26,
        "signal": 9,
        "atr_window": 14,
        "atr_trend_multiplier": 1.0,
    }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["Close"]
        p = self.params

        macd_line, sig_line, histogram = TI.macd(close, p["fast"], p["slow"], p["signal"])
        atr = TI.atr(data["High"], data["Low"], close, p["atr_window"])

        cross_up = (histogram > 0) & (histogram.shift(1) <= 0)
        cross_down = (histogram < 0) & (histogram.shift(1) >= 0)

        # Only trade when price movement > ATR threshold (filters low-volatility noise)
        price_move = close.diff().abs()
        volatile_enough = price_move > atr * p["atr_trend_multiplier"]

        signal = pd.Series(0, index=data.index)
        signal[cross_up & volatile_enough] = 1
        signal[cross_down] = -1
        return signal


class BollingerMeanReversion(Strategy):
    """Mean-reversion: buy lower band touch, sell upper band touch or middle."""

    params = {
        "bb_window": 20,
        "bb_std": 2.0,
        "rsi_window": 14,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
    }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["Close"]
        p = self.params

        upper, mid, lower = TI.bollinger(close, p["bb_window"], p["bb_std"])
        rsi = TI.rsi(close, p["rsi_window"])

        # Enter when price touches lower band AND RSI is oversold
        enter = (close <= lower) & (rsi < p["rsi_oversold"])
        # Exit when price reaches middle band OR RSI is overbought
        exit_ = (close >= mid) | (rsi > p["rsi_overbought"])

        signal = pd.Series(0, index=data.index)
        signal[enter] = 1
        signal[exit_] = -1
        return signal


class RSIMomentum(Strategy):
    """Simple RSI momentum: long above 50, exit below 50."""

    params = {
        "rsi_window": 14,
        "rsi_enter": 55,
        "rsi_exit": 45,
        "sma_trend_window": 200,
    }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["Close"]
        p = self.params

        rsi = TI.rsi(close, p["rsi_window"])
        trend_filter = TI.sma(close, p["sma_trend_window"])

        above_trend = close > trend_filter
        signal = pd.Series(0, index=data.index)
        signal[(rsi > p["rsi_enter"]) & above_trend] = 1
        signal[rsi < p["rsi_exit"]] = -1
        return signal
