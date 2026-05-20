"""
Web3 trading demo — shows how to wire up the full on-chain closed loop.

NEVER run this with real funds until you've tested on a testnet.
Set DRY_RUN=true (default) to simulate without broadcasting transactions.

Environment variables required:
  PRIVATE_KEY      Your wallet private key (0x...)
  WEB3_RPC_URL     RPC endpoint (optional, uses public endpoints by default)
  DRY_RUN          Set to "false" to actually broadcast transactions

Usage:
  export PRIVATE_KEY=0x...
  python -m finance.web3_demo
"""

import os
import sys
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ── Token registry (Base chain) ───────────────────────────────────────────────
BASE_TOKENS = {
    "WETH":  {"address": "0x4200000000000000000000000000000000000006", "decimals": 18},
    "USDC":  {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "decimals": 6},
    "cbBTC": {"address": "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf", "decimals": 8},
}


def demo_price_feeds(chain_id: int = 8453):
    """Read live prices from Chainlink and Uniswap v3 pools."""
    from web3 import Web3
    from finance.web3_config import CHAINS
    from finance.web3_data import OnChainPriceFeed

    rpc = os.environ.get("WEB3_RPC_URL", CHAINS[chain_id]["rpc"])
    w3 = Web3(Web3.HTTPProvider(rpc))

    if not w3.is_connected():
        log.error("Cannot connect to RPC: %s", rpc)
        return

    log.info("Connected to %s (block %d)", CHAINS[chain_id]["name"], w3.eth.block_number)

    feed = OnChainPriceFeed(w3, chain_id)

    # ETH/USD from Chainlink
    eth_usd = feed.native_usd_price()
    log.info("ETH/USD (Chainlink): $%.2f", eth_usd)

    # Token prices via Uniswap v3 → Chainlink
    snapshot = feed.prices_snapshot(BASE_TOKENS)
    for symbol, price in snapshot.items():
        if price is not None:
            log.info("  %s: $%.4f", symbol, price)
        else:
            log.warning("  %s: price unavailable", symbol)

    return snapshot


def demo_wallet_info(chain_id: int = 8453):
    """Show wallet balances without sending any transactions."""
    from web3 import Web3
    from finance.web3_config import CHAINS, ERC20_ABI
    from finance.web3_wallet import Web3Wallet

    pk = os.environ.get("PRIVATE_KEY")
    if not pk:
        log.warning("PRIVATE_KEY not set — skipping wallet demo")
        return

    rpc = os.environ.get("WEB3_RPC_URL", CHAINS[chain_id]["rpc"])
    w3 = Web3(Web3.HTTPProvider(rpc))
    wallet = Web3Wallet(pk, w3)

    log.info("Wallet address: %s", wallet.address)
    log.info("ETH balance: %.6f ETH", wallet.native_balance())

    for symbol, cfg in BASE_TOKENS.items():
        try:
            balance, decimals = wallet.token_balance(cfg["address"], ERC20_ABI)
            log.info("  %s balance: %.6f", symbol, balance)
        except Exception as e:
            log.warning("  %s balance error: %s", symbol, e)


def demo_dry_run_swap(chain_id: int = 8453):
    """Build a swap transaction and log it — no broadcast."""
    from web3 import Web3
    from finance.web3_config import CHAINS, V3_FEE_MEDIUM
    from finance.web3_wallet import Web3Wallet
    from finance.web3_broker import Web3Broker

    pk = os.environ.get("PRIVATE_KEY")
    if not pk:
        log.warning("PRIVATE_KEY not set — skipping swap demo")
        return

    rpc = os.environ.get("WEB3_RPC_URL", CHAINS[chain_id]["rpc"])
    w3 = Web3(Web3.HTTPProvider(rpc))
    wallet = Web3Wallet(pk, w3)

    dry_run = os.environ.get("DRY_RUN", "true").lower() != "false"
    broker = Web3Broker(
        wallet=wallet,
        chain_id=chain_id,
        dex="v3",
        fee_tier=V3_FEE_MEDIUM,
        slippage_bps=50,
        dry_run=dry_run,
    )

    log.info("Executing %s swap: 0.001 ETH → USDC", "DRY RUN" if dry_run else "LIVE")
    result = broker.execute_swap(
        token_in=BASE_TOKENS["WETH"]["address"],
        token_out=BASE_TOKENS["USDC"]["address"],
        amount_in_human=0.001,
        decimals_in=18,
        decimals_out=6,
        is_native_in=True,
    )
    log.info("Result: status=%s tx=%s gas_cost=%.6f ETH",
             result.status, result.tx_hash, result.gas_cost_eth)
    return result


def demo_live_strategy(chain_id: int = 8453):
    """Full closed loop: on-chain prices → strategy → live swap.

    This is the actual production loop. Only runs when DRY_RUN=false.
    """
    from web3 import Web3
    from finance.web3_config import CHAINS, V3_FEE_MEDIUM
    from finance.web3_wallet import Web3Wallet
    from finance.web3_broker import Web3Broker, Web3LiveTrader
    from finance.web3_data import OnChainPriceFeed, BarBuilder
    from finance.example_strategy import DualMACrossover
    from finance.risk import RiskManager
    from finance.portfolio import Portfolio

    pk = os.environ.get("PRIVATE_KEY")
    if not pk:
        log.warning("PRIVATE_KEY not set — cannot run live strategy")
        return

    rpc = os.environ.get("WEB3_RPC_URL", CHAINS[chain_id]["rpc"])
    w3 = Web3(Web3.HTTPProvider(rpc))
    wallet = Web3Wallet(pk, w3)

    dry_run = os.environ.get("DRY_RUN", "true").lower() != "false"
    if dry_run:
        log.info("DRY_RUN=true — transactions will be simulated, not broadcast")

    price_feed = OnChainPriceFeed(w3, chain_id)
    bar_builder = BarBuilder(
        price_feed=price_feed,
        token_address=BASE_TOKENS["WETH"]["address"],
        token_decimals=18,
        bar_seconds=60,      # 1-minute bars
        poll_interval=5.0,
        history_bars=500,
    )

    strategy = DualMACrossover()
    strategy.params.update({"fast_ma": 10, "slow_ma": 30})

    broker = Web3Broker(
        wallet=wallet,
        chain_id=chain_id,
        dex="v3",
        fee_tier=V3_FEE_MEDIUM,
        slippage_bps=50,
        dry_run=dry_run,
    )

    trader = Web3LiveTrader(
        strategy=strategy,
        broker=broker,
        bar_builder=bar_builder,
        portfolio=Portfolio(initial_cash=0),  # tracks on-chain positions
        risk_manager=RiskManager(),
        token_in=BASE_TOKENS["WETH"]["address"],
        token_out=BASE_TOKENS["USDC"]["address"],
        decimals_in=18,
        decimals_out=6,
        trade_size_usd=100.0,
        poll_seconds=30.0,
    )

    log.info("Starting live trader on %s...", CHAINS[chain_id]["name"])
    trader.start()  # blocks until Ctrl+C


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Web3 trading demo")
    parser.add_argument("--mode", choices=["prices", "wallet", "swap", "live"],
                        default="prices", help="Demo mode")
    parser.add_argument("--chain", type=int, default=8453, help="Chain ID (default: Base=8453)")
    args = parser.parse_args()

    if args.mode == "prices":
        demo_price_feeds(args.chain)
    elif args.mode == "wallet":
        demo_wallet_info(args.chain)
    elif args.mode == "swap":
        demo_dry_run_swap(args.chain)
    elif args.mode == "live":
        demo_live_strategy(args.chain)
