"""On-chain price feeds: Uniswap v2/v3 pool prices, Chainlink oracles, OHLCV bars."""

import time
import threading
from collections import deque
from typing import Optional
import pandas as pd
from web3 import Web3

from .web3_config import (
    CHAINS, ERC20_ABI, UNISWAP_V2_PAIR_ABI,
    UNISWAP_V3_QUOTER_ABI, CHAINLINK_ABI,
    V3_FEE_MEDIUM,
)


class OnChainPriceFeed:
    """Fetch spot prices from Uniswap v2/v3 pools and Chainlink oracles.

    Prices are always returned in USD terms where possible, otherwise
    in the quote-token denomination.
    """

    def __init__(self, w3: Web3, chain_id: int = 1):
        self.w3 = w3
        self.chain_id = chain_id
        self._cfg = CHAINS.get(chain_id, {})

    # ── Chainlink ─────────────────────────────────────────────────────────────

    def chainlink_price(self, feed_address: str) -> float:
        """Read latest price from any Chainlink price feed. Returns float."""
        contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(feed_address),
            abi=CHAINLINK_ABI,
        )
        _, answer, _, updated_at, _ = contract.functions.latestRoundData().call()
        decimals = contract.functions.decimals().call()
        # Staleness check: warn if older than 1 hour
        age = int(time.time()) - updated_at
        if age > 3600:
            import warnings
            warnings.warn(f"Chainlink feed {feed_address} data is {age}s old")
        return answer / (10 ** decimals)

    def native_usd_price(self) -> float:
        """ETH/BNB/etc price in USD via Chainlink."""
        feed = self._cfg.get("chainlink_eth_usd")
        if not feed:
            raise ValueError(f"No Chainlink feed configured for chain {self.chain_id}")
        return self.chainlink_price(feed)

    # ── Uniswap v2 ────────────────────────────────────────────────────────────

    def v2_pool_price(
        self,
        pair_address: str,
        token_in: str,
        decimals_in: int = 18,
        decimals_out: int = 18,
    ) -> float:
        """Spot price from a Uniswap v2 pair's reserves.

        Returns price of token_in denominated in token_out units.
        """
        pair = self.w3.eth.contract(
            address=Web3.to_checksum_address(pair_address),
            abi=UNISWAP_V2_PAIR_ABI,
        )
        r0, r1, _ = pair.functions.getReserves().call()
        t0 = pair.functions.token0().call().lower()

        token_in_lc = Web3.to_checksum_address(token_in).lower()
        if t0 == token_in_lc:
            # token_in is token0, token_out is token1
            price = (r1 / 10 ** decimals_out) / (r0 / 10 ** decimals_in)
        else:
            price = (r0 / 10 ** decimals_in) / (r1 / 10 ** decimals_out)
        return price

    def v2_quote(
        self,
        router_address: str,
        amount_in_wei: int,
        path: list,
    ) -> int:
        """Get expected output from Uniswap v2 router getAmountsOut."""
        from .web3_config import UNISWAP_V2_ROUTER_ABI
        router = self.w3.eth.contract(
            address=Web3.to_checksum_address(router_address),
            abi=UNISWAP_V2_ROUTER_ABI,
        )
        amounts = router.functions.getAmountsOut(amount_in_wei, path).call()
        return amounts[-1]

    # ── Uniswap v3 ────────────────────────────────────────────────────────────

    def v3_quote(
        self,
        token_in: str,
        token_out: str,
        amount_in_wei: int,
        fee: int = V3_FEE_MEDIUM,
        quoter_address: Optional[str] = None,
    ) -> int:
        """Quote exact output for a v3 swap using the Quoter contract."""
        quoter_addr = quoter_address or self._cfg.get("uniswap_v3_quoter")
        if not quoter_addr:
            raise ValueError("No v3 quoter address configured")
        quoter = self.w3.eth.contract(
            address=Web3.to_checksum_address(quoter_addr),
            abi=UNISWAP_V3_QUOTER_ABI,
        )
        return quoter.functions.quoteExactInputSingle(
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(token_out),
            fee,
            amount_in_wei,
            0,  # no price limit
        ).call()

    def token_price_in_usd(
        self,
        token_address: str,
        token_decimals: int = 18,
        amount_token: float = 1.0,
        fee: int = V3_FEE_MEDIUM,
        use_v3: bool = True,
    ) -> float:
        """Price of one token unit in USD, routing through WETH → Chainlink.

        token → WETH (v3 quote) → USD (Chainlink)
        """
        weth = self._cfg.get("wrapped_native")
        if not weth:
            raise ValueError(f"No WETH address configured for chain {self.chain_id}")

        amount_in_wei = int(amount_token * 10 ** token_decimals)

        if use_v3:
            weth_out_wei = self.v3_quote(token_address, weth, amount_in_wei, fee)
        else:
            router = self._cfg.get("uniswap_v2_router")
            path = [
                Web3.to_checksum_address(token_address),
                Web3.to_checksum_address(weth),
            ]
            weth_out_wei = self.v2_quote(router, amount_in_wei, path)

        weth_out = weth_out_wei / 1e18
        eth_usd = self.native_usd_price()
        return weth_out * eth_usd

    # ── Multi-token snapshot ──────────────────────────────────────────────────

    def prices_snapshot(self, tokens: dict) -> dict:
        """Fetch USD prices for multiple tokens.

        tokens = {"USDC": {"address": "0x...", "decimals": 6}, ...}
        Returns {"USDC": 1.0002, "WBTC": 67432.5, ...}
        """
        prices = {}
        for symbol, cfg in tokens.items():
            try:
                prices[symbol] = self.token_price_in_usd(
                    cfg["address"], cfg.get("decimals", 18)
                )
            except Exception as e:
                prices[symbol] = None
        return prices


class BarBuilder:
    """Aggregate on-chain price ticks into OHLCV bars for strategy consumption.

    Polls OnChainPriceFeed at `poll_interval` seconds and builds bars
    of `bar_seconds` duration. Thread-safe.
    """

    def __init__(
        self,
        price_feed: OnChainPriceFeed,
        token_address: str,
        token_decimals: int = 18,
        bar_seconds: int = 60,
        poll_interval: float = 5.0,
        history_bars: int = 500,
    ):
        self.feed = price_feed
        self.token_address = token_address
        self.token_decimals = token_decimals
        self.bar_seconds = bar_seconds
        self.poll_interval = poll_interval
        self._bars: deque = deque(maxlen=history_bars)
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._current_bar: Optional[dict] = None
        self._bar_start: float = 0.0

    def _fetch_price(self) -> float:
        return self.feed.token_price_in_usd(self.token_address, self.token_decimals)

    def _tick(self, price: float) -> None:
        now = time.time()
        with self._lock:
            if self._current_bar is None or now - self._bar_start >= self.bar_seconds:
                # Close current bar and start new one
                if self._current_bar is not None:
                    self._bars.append(self._current_bar)
                ts = pd.Timestamp.utcnow().floor(f"{self.bar_seconds}s")
                self._current_bar = {
                    "timestamp": ts,
                    "Open": price,
                    "High": price,
                    "Low": price,
                    "Close": price,
                    "Volume": 0.0,
                }
                self._bar_start = now
            else:
                b = self._current_bar
                b["High"] = max(b["High"], price)
                b["Low"]  = min(b["Low"],  price)
                b["Close"] = price

    def _run_loop(self) -> None:
        while self._running:
            try:
                price = self._fetch_price()
                self._tick(price)
            except Exception:
                pass
            time.sleep(self.poll_interval)

    def start(self) -> None:
        """Start background polling thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def get_dataframe(self) -> pd.DataFrame:
        """Return completed bars as OHLCV DataFrame."""
        with self._lock:
            bars = list(self._bars)
        if not bars:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        df = pd.DataFrame(bars).set_index("timestamp")
        df.index = pd.to_datetime(df.index)
        return df

    def latest_close(self) -> Optional[float]:
        with self._lock:
            if self._current_bar:
                return self._current_bar["Close"]
            if self._bars:
                return self._bars[-1]["Close"]
        return None
