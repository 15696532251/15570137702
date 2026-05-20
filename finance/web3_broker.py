"""Web3 trade execution: swap tokens on Uniswap v2/v3 with full lifecycle management."""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from web3 import Web3

from .execution import Order
from .web3_wallet import Web3Wallet
from .web3_config import (
    CHAINS, ERC20_ABI,
    UNISWAP_V2_ROUTER_ABI, UNISWAP_V3_ROUTER_ABI,
    V3_FEE_MEDIUM,
)

log = logging.getLogger(__name__)


@dataclass
class SwapResult:
    order_id: str
    tx_hash: str
    status: str               # "confirmed" | "reverted" | "pending"
    amount_in: float
    amount_out: float
    token_in: str
    token_out: str
    gas_used: int = 0
    gas_cost_eth: float = 0.0
    receipt: dict = field(default_factory=dict)


class Web3Broker:
    """Execute token swaps on Uniswap v2 or v3.

    Implements the same submit/process_bar interface as PaperBroker so it
    can be swapped in as the execution layer with no changes to BacktestEngine.
    For live trading, use execute_swap() directly.

    Security requirements:
    - Private key must come from Web3Wallet (env var or keystore), never hardcoded
    - Always set slippage_bps to prevent sandwich attacks
    - Deadline prevents pending transactions from executing at stale prices
    """

    def __init__(
        self,
        wallet: Web3Wallet,
        chain_id: int = 1,
        dex: str = "v3",              # "v2" | "v3"
        fee_tier: int = V3_FEE_MEDIUM,
        slippage_bps: int = 50,       # 0.5% default slippage tolerance
        deadline_seconds: int = 300,  # 5 minutes
        dry_run: bool = False,        # True = build tx but don't broadcast
    ):
        self.wallet = wallet
        self.chain_id = chain_id
        self.dex = dex
        self.fee_tier = fee_tier
        self.slippage_bps = slippage_bps
        self.deadline_seconds = deadline_seconds
        self.dry_run = dry_run
        self._cfg = CHAINS[chain_id]
        self._swap_log: list = []

    # ── Core swap execution ───────────────────────────────────────────────────

    def execute_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in_human: float,
        decimals_in: int = 18,
        decimals_out: int = 18,
        min_amount_out_human: Optional[float] = None,
        is_native_in: bool = False,
    ) -> SwapResult:
        """Execute a token swap.

        Args:
            token_in:          Address of input token (ignored if is_native_in=True)
            token_out:         Address of output token
            amount_in_human:   Amount in human-readable units (e.g. 1.5 ETH, not wei)
            decimals_in:       Decimals of input token
            decimals_out:      Decimals of output token
            min_amount_out_human: Minimum acceptable output (sets slippage floor)
            is_native_in:      True when spending native ETH/BNB directly
        """
        amount_in_wei = int(amount_in_human * 10 ** decimals_in)

        # Approve input token if needed (not needed for native ETH)
        if not is_native_in:
            router = self._cfg[f"uniswap_{self.dex}_router"]
            self.wallet.approve_token(token_in, router, amount_in_wei, ERC20_ABI)

        if self.dex == "v3":
            return self._swap_v3(
                token_in, token_out, amount_in_wei, decimals_out,
                min_amount_out_human, is_native_in,
            )
        else:
            return self._swap_v2(
                token_in, token_out, amount_in_wei, decimals_out,
                min_amount_out_human, is_native_in,
            )

    def _min_out_wei(
        self, amount_in_wei: int, token_in: str, token_out: str,
        decimals_out: int, override: Optional[float],
    ) -> int:
        """Compute minimum acceptable output in wei."""
        if override is not None:
            return int(override * 10 ** decimals_out)
        # Quote expected output and apply slippage tolerance
        try:
            from .web3_data import OnChainPriceFeed
            feed = OnChainPriceFeed(self.wallet.w3, self.chain_id)
            if self.dex == "v3":
                expected = feed.v3_quote(token_in, token_out, amount_in_wei, self.fee_tier)
            else:
                router = self._cfg["uniswap_v2_router"]
                expected = feed.v2_quote(router, amount_in_wei, [
                    Web3.to_checksum_address(token_in),
                    Web3.to_checksum_address(token_out),
                ])
            return int(expected * (1 - self.slippage_bps / 10_000))
        except Exception:
            return 0  # no minimum — use only when quoting fails & you accept the risk

    def _deadline(self) -> int:
        return int(time.time()) + self.deadline_seconds

    def _swap_v3(
        self,
        token_in: str,
        token_out: str,
        amount_in_wei: int,
        decimals_out: int,
        min_out_human: Optional[float],
        is_native_in: bool,
    ) -> SwapResult:
        router_addr = self._cfg["uniswap_v3_router"]
        router = self.wallet.w3.eth.contract(
            address=Web3.to_checksum_address(router_addr),
            abi=UNISWAP_V3_ROUTER_ABI,
        )
        weth = self._cfg["wrapped_native"]
        token_in_addr = Web3.to_checksum_address(weth if is_native_in else token_in)
        token_out_addr = Web3.to_checksum_address(token_out)

        min_out = self._min_out_wei(amount_in_wei, token_in_addr, token_out_addr, decimals_out, min_out_human)

        params = {
            "tokenIn":           token_in_addr,
            "tokenOut":          token_out_addr,
            "fee":               self.fee_tier,
            "recipient":         self.wallet.address,
            "deadline":          self._deadline(),
            "amountIn":          amount_in_wei,
            "amountOutMinimum":  min_out,
            "sqrtPriceLimitX96": 0,
        }

        data = router.encodeABI("exactInputSingle", args=[params])
        tx = self.wallet.build_tx(
            to=router_addr,
            data=data,
            value=amount_in_wei if is_native_in else 0,
        )

        return self._send_tx(tx, token_in_addr, token_out_addr, amount_in_wei, min_out, decimals_out)

    def _swap_v2(
        self,
        token_in: str,
        token_out: str,
        amount_in_wei: int,
        decimals_out: int,
        min_out_human: Optional[float],
        is_native_in: bool,
    ) -> SwapResult:
        router_addr = self._cfg["uniswap_v2_router"]
        router = self.wallet.w3.eth.contract(
            address=Web3.to_checksum_address(router_addr),
            abi=UNISWAP_V2_ROUTER_ABI,
        )
        weth = Web3.to_checksum_address(self._cfg["wrapped_native"])
        token_out_addr = Web3.to_checksum_address(token_out)
        token_in_addr  = Web3.to_checksum_address(token_in if not is_native_in else weth)

        min_out = self._min_out_wei(amount_in_wei, token_in_addr, token_out_addr, decimals_out, min_out_human)
        deadline = self._deadline()
        path = [token_in_addr, token_out_addr]

        if is_native_in:
            data = router.encodeABI("swapExactETHForTokens", args=[
                min_out, path, self.wallet.address, deadline
            ])
        elif token_out_addr == weth:
            data = router.encodeABI("swapExactTokensForETH", args=[
                amount_in_wei, min_out, path, self.wallet.address, deadline
            ])
        else:
            data = router.encodeABI("swapExactTokensForTokens", args=[
                amount_in_wei, min_out, path, self.wallet.address, deadline
            ])

        tx = self.wallet.build_tx(
            to=router_addr,
            data=data,
            value=amount_in_wei if is_native_in else 0,
        )
        return self._send_tx(tx, token_in_addr, token_out_addr, amount_in_wei, min_out, decimals_out)

    def _send_tx(
        self,
        tx: dict,
        token_in: str,
        token_out: str,
        amount_in_wei: int,
        min_out_wei: int,
        decimals_out: int,
    ) -> SwapResult:
        import uuid
        order_id = str(uuid.uuid4())[:8]

        if self.dry_run:
            log.info("[DRY RUN] tx would be: %s", tx)
            result = SwapResult(
                order_id=order_id,
                tx_hash="0x" + "0" * 64,
                status="dry_run",
                amount_in=amount_in_wei,
                amount_out=min_out_wei / 10 ** decimals_out,
                token_in=token_in,
                token_out=token_out,
            )
            self._swap_log.append(result)
            return result

        try:
            receipt = self.wallet.send_and_wait(tx)
            gas_price = tx.get("gasPrice") or tx.get("maxFeePerGas", 0)
            gas_cost = receipt.get("gasUsed", 0) * gas_price / 1e18
            result = SwapResult(
                order_id=order_id,
                tx_hash=receipt["transactionHash"].hex(),
                status="confirmed",
                amount_in=amount_in_wei / 1e18,
                amount_out=0.0,  # parse from receipt logs for precision
                token_in=token_in,
                token_out=token_out,
                gas_used=receipt.get("gasUsed", 0),
                gas_cost_eth=gas_cost,
                receipt=receipt,
            )
        except Exception as e:
            log.error("Swap failed: %s", e)
            result = SwapResult(
                order_id=order_id,
                tx_hash="",
                status="reverted",
                amount_in=amount_in_wei / 1e18,
                amount_out=0.0,
                token_in=token_in,
                token_out=token_out,
            )
        self._swap_log.append(result)
        return result

    # ── PaperBroker-compatible interface (for live trading loop) ─────────────

    def submit(self, order: Order) -> str:
        """Accept an Order (from BacktestEngine/LiveLoop) — no-op, returns id.

        Actual execution happens in process_bar() when price data arrives.
        """
        return order.order_id

    def process_bar(self, bar: dict) -> list:
        """PaperBroker-compatible stub. Live orders are executed immediately
        via execute_swap() in Web3LiveTrader, not deferred to bar processing."""
        return []

    @property
    def swap_history(self) -> list:
        return list(self._swap_log)


class Web3LiveTrader:
    """Live trading loop: polls on-chain prices, applies strategy, executes swaps.

    This replaces BacktestEngine for live trading. It uses the same Strategy,
    RiskManager, and Portfolio objects from the existing system.
    """

    def __init__(
        self,
        strategy,
        broker: Web3Broker,
        bar_builder,          # BarBuilder from web3_data.py
        portfolio,            # Portfolio from portfolio.py
        risk_manager,         # RiskManager from risk.py
        token_in: str,        # e.g. WETH address (what you sell to buy target)
        token_out: str,       # target token address
        decimals_in: int = 18,
        decimals_out: int = 18,
        trade_size_usd: float = 1000.0,
        poll_seconds: float = 30.0,
    ):
        self.strategy = strategy
        self.broker = broker
        self.bar_builder = bar_builder
        self.portfolio = portfolio
        self.risk_manager = risk_manager
        self.token_in = token_in
        self.token_out = token_out
        self.decimals_in = decimals_in
        self.decimals_out = decimals_out
        self.trade_size_usd = trade_size_usd
        self.poll_seconds = poll_seconds
        self._last_signal: int = 0
        self._running = False

    def start(self) -> None:
        """Start the bar builder and enter the live trading loop."""
        self.bar_builder.start()
        self._running = True
        log.info("Live trader started. Token: %s → %s", self.token_in, self.token_out)
        try:
            self._loop()
        except KeyboardInterrupt:
            log.info("Live trader stopped by user.")
        finally:
            self.bar_builder.stop()

    def _loop(self) -> None:
        while self._running:
            df = self.bar_builder.get_dataframe()
            if len(df) < 30:
                log.info("Waiting for enough bars (%d/30)...", len(df))
                time.sleep(self.poll_seconds)
                continue

            signals = self.strategy.generate_signals(df)
            latest_signal = int(signals.iloc[-1]) if len(signals) else 0

            if latest_signal != self._last_signal:
                self._on_signal_change(latest_signal, df)
                self._last_signal = latest_signal

            time.sleep(self.poll_seconds)

    def _on_signal_change(self, signal: int, df) -> None:
        price = self.bar_builder.latest_close() or df["Close"].iloc[-1]
        held = self.portfolio.positions.get("TOKEN", 0)

        if signal == 1 and held == 0:
            # Buy: spend trade_size_usd worth of token_in
            amount_in = self.trade_size_usd / price  # approximate ETH amount
            log.info("BUY signal — swapping %.4f ETH → token", amount_in)
            result = self.broker.execute_swap(
                token_in=self.token_in,
                token_out=self.token_out,
                amount_in_human=amount_in,
                decimals_in=self.decimals_in,
                decimals_out=self.decimals_out,
                is_native_in=True,
            )
            log.info("Swap result: %s tx=%s", result.status, result.tx_hash)

        elif signal == -1 and held > 0:
            # Sell all held tokens back
            log.info("SELL signal — swapping %d tokens → ETH", held)
            result = self.broker.execute_swap(
                token_in=self.token_out,
                token_out=self.token_in,
                amount_in_human=held / 10 ** self.decimals_out,
                decimals_in=self.decimals_out,
                decimals_out=self.decimals_in,
            )
            log.info("Swap result: %s tx=%s", result.status, result.tx_hash)
