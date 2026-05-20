"""Layer 2 – Technical indicators (pure functions) and composite signal engine."""

import pandas as pd
import numpy as np


class TechnicalIndicators:
    """Namespace of stateless indicator functions. All return pd.Series."""

    @staticmethod
    def sma(close: pd.Series, window: int) -> pd.Series:
        return close.rolling(window).mean()

    @staticmethod
    def ema(close: pd.Series, span: int) -> pd.Series:
        return close.ewm(span=span, adjust=False).mean()

    @staticmethod
    def rsi(close: pd.Series, window: int = 14) -> pd.Series:
        """Wilder-smoothed RSI (matches most charting platforms)."""
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        # Wilder smoothing = EWM with alpha = 1/window
        avg_gain = gain.ewm(alpha=1.0 / window, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / window, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(
        close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> tuple:
        """Returns (macd_line, signal_line, histogram)."""
        fast_ema = close.ewm(span=fast, adjust=False).mean()
        slow_ema = close.ewm(span=slow, adjust=False).mean()
        macd_line = fast_ema - slow_ema
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def bollinger(
        close: pd.Series, window: int = 20, num_std: float = 2.0
    ) -> tuple:
        """Returns (upper_band, middle_band, lower_band)."""
        mid = close.rolling(window).mean()
        std = close.rolling(window).std(ddof=0)
        return mid + num_std * std, mid, mid - num_std * std

    @staticmethod
    def atr(
        high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14
    ) -> pd.Series:
        """Average True Range — used by RiskManager for volatility-based stops."""
        prev_close = close.shift(1)
        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return tr.ewm(alpha=1.0 / window, adjust=False).mean()

    @staticmethod
    def stochastic(
        high: pd.Series, low: pd.Series, close: pd.Series,
        k_window: int = 14, d_window: int = 3
    ) -> tuple:
        """Returns (%K, %D)."""
        lowest_low = low.rolling(k_window).min()
        highest_high = high.rolling(k_window).max()
        k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
        d = k.rolling(d_window).mean()
        return k, d

    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        """On-Balance Volume."""
        direction = np.sign(close.diff()).fillna(0)
        return (direction * volume).cumsum()


class SignalEngine:
    """Combines multiple rule functions into a composite {-1, 0, 1} signal."""

    def __init__(self, rules: list):
        """Each rule is callable(df: pd.DataFrame) -> pd.Series of {-1, 0, 1}."""
        self.rules = rules

    def compute(self, df: pd.DataFrame) -> pd.Series:
        """Vote across all rules; final signal = sign(sum)."""
        if not self.rules:
            return pd.Series(0, index=df.index, name="signal")
        votes = sum(rule(df) for rule in self.rules)
        return np.sign(votes).rename("signal").astype(int)
