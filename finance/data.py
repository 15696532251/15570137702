"""Layer 1 – Market data ingestion with local Parquet caching."""

import os
import pandas as pd


_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache", "finance")


class MarketDataFeed:
    """Download and cache OHLCV data for a list of symbols."""

    def __init__(
        self,
        symbols: list,
        start: str,
        end: str,
        interval: str = "1d",
        cache_dir: str = _CACHE_DIR,
    ):
        self.symbols = [symbols] if isinstance(symbols, str) else list(symbols)
        self.start = start
        self.end = end
        self.interval = interval
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._cache: dict = {}

    def _cache_path(self, symbol: str) -> str:
        safe = symbol.replace("/", "_").replace("^", "")
        return os.path.join(
            self.cache_dir, f"{safe}_{self.start}_{self.end}_{self.interval}.parquet"
        )

    def _fetch_one(self, symbol: str) -> pd.DataFrame:
        key = (symbol, self.start, self.end, self.interval)
        if key in self._cache:
            return self._cache[key]

        path = self._cache_path(symbol)
        if os.path.exists(path):
            df = pd.read_parquet(path)
            self._cache[key] = df
            return df

        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("yfinance is required: pip install yfinance")

        ticker = yf.Ticker(symbol)
        df = ticker.history(start=self.start, end=self.end, interval=self.interval)
        if df.empty:
            raise ValueError(f"No data returned for {symbol}")

        # Normalize columns
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.sort_index(inplace=True)

        df.to_parquet(path)
        self._cache[key] = df
        return df

    def fetch(self) -> dict:
        """Return {symbol: OHLCV DataFrame}."""
        return {sym: self._fetch_one(sym) for sym in self.symbols}

    def fetch_one(self, symbol: str) -> pd.DataFrame:
        return self._fetch_one(symbol)

    @staticmethod
    def align(data: dict) -> pd.DataFrame:
        """Inner-join all symbol DataFrames on DatetimeIndex.

        Returns a MultiLevel column DataFrame: (symbol, field).
        """
        frames = {}
        for sym, df in data.items():
            frames[sym] = df
        return pd.concat(frames, axis=1).dropna()

    def add_fundamentals(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Attach basic fundamental columns if available (best-effort)."""
        try:
            import yfinance as yf
            info = yf.Ticker(symbol).info
            df = df.copy()
            for field in ("trailingPE", "marketCap", "dividendYield"):
                df[field] = info.get(field)
        except Exception:
            pass
        return df
