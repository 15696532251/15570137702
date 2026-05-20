"""Chain configurations, contract addresses, and minimal ABIs for Web3 trading."""

# ── Chain RPC endpoints (override via env var WEB3_RPC_URL) ──────────────────
CHAINS = {
    1: {
        "name": "Ethereum Mainnet",
        "rpc": "https://eth.llamarpc.com",
        "wrapped_native": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
        "uniswap_v2_router": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
        "uniswap_v3_router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        "uniswap_v3_quoter": "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
        "chainlink_eth_usd": "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",
    },
    8453: {
        "name": "Base",
        "rpc": "https://mainnet.base.org",
        "wrapped_native": "0x4200000000000000000000000000000000000006",  # WETH on Base
        "uniswap_v2_router": "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24",
        "uniswap_v3_router": "0x2626664c2603336E57B271c5C0b26F421741e481",
        "uniswap_v3_quoter": "0x3d4e44Eb1374240CE5F1B136041f3b3c95700AB6",
        "chainlink_eth_usd": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
    },
    42161: {
        "name": "Arbitrum One",
        "rpc": "https://arb1.arbitrum.io/rpc",
        "wrapped_native": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",  # WETH on Arb
        "uniswap_v2_router": "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24",
        "uniswap_v3_router": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        "uniswap_v3_quoter": "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
        "chainlink_eth_usd": "0x639Fe6ab55C921f74e7fac1ee960C0B6293ba612",
    },
    56: {
        "name": "BNB Chain",
        "rpc": "https://bsc-dataseed.binance.org",
        "wrapped_native": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
        "uniswap_v2_router": "0x10ED43C718714eb63d5aA57B78B54704E256024E",  # PancakeSwap v2
        "uniswap_v3_router": "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",  # PancakeSwap v3
        "uniswap_v3_quoter": "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997",
        "chainlink_eth_usd": "0x0567F2323251f0Aab15c8dFb1967E4e8A7D42aeE",  # BNB/USD
    },
}

# ── Minimal ABIs ──────────────────────────────────────────────────────────────

ERC20_ABI = [
    {"name": "balanceOf",  "type": "function", "stateMutability": "view",
     "inputs": [{"name": "account", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "decimals",   "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint8"}]},
    {"name": "symbol",     "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "string"}]},
    {"name": "allowance",  "type": "function", "stateMutability": "view",
     "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "approve",    "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "outputs": [{"name": "", "type": "bool"}]},
]

UNISWAP_V2_ROUTER_ABI = [
    {"name": "getAmountsOut", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "amountIn", "type": "uint256"}, {"name": "path", "type": "address[]"}],
     "outputs": [{"name": "amounts", "type": "uint256[]"}]},
    {"name": "swapExactETHForTokens", "type": "function", "stateMutability": "payable",
     "inputs": [
         {"name": "amountOutMin", "type": "uint256"},
         {"name": "path",         "type": "address[]"},
         {"name": "to",           "type": "address"},
         {"name": "deadline",     "type": "uint256"},
     ], "outputs": [{"name": "amounts", "type": "uint256[]"}]},
    {"name": "swapExactTokensForETH", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "amountIn",     "type": "uint256"},
         {"name": "amountOutMin", "type": "uint256"},
         {"name": "path",         "type": "address[]"},
         {"name": "to",           "type": "address"},
         {"name": "deadline",     "type": "uint256"},
     ], "outputs": [{"name": "amounts", "type": "uint256[]"}]},
    {"name": "swapExactTokensForTokens", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "amountIn",     "type": "uint256"},
         {"name": "amountOutMin", "type": "uint256"},
         {"name": "path",         "type": "address[]"},
         {"name": "to",           "type": "address"},
         {"name": "deadline",     "type": "uint256"},
     ], "outputs": [{"name": "amounts", "type": "uint256[]"}]},
]

UNISWAP_V2_PAIR_ABI = [
    {"name": "getReserves", "type": "function", "stateMutability": "view",
     "inputs": [],
     "outputs": [
         {"name": "reserve0", "type": "uint112"},
         {"name": "reserve1", "type": "uint112"},
         {"name": "blockTimestampLast", "type": "uint32"},
     ]},
    {"name": "token0", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "address"}]},
    {"name": "token1", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "address"}]},
]

UNISWAP_V3_ROUTER_ABI = [
    {"name": "exactInputSingle", "type": "function", "stateMutability": "payable",
     "inputs": [{"name": "params", "type": "tuple",
                 "components": [
                     {"name": "tokenIn",           "type": "address"},
                     {"name": "tokenOut",          "type": "address"},
                     {"name": "fee",               "type": "uint24"},
                     {"name": "recipient",         "type": "address"},
                     {"name": "deadline",          "type": "uint256"},
                     {"name": "amountIn",          "type": "uint256"},
                     {"name": "amountOutMinimum",  "type": "uint256"},
                     {"name": "sqrtPriceLimitX96", "type": "uint160"},
                 ]}],
     "outputs": [{"name": "amountOut", "type": "uint256"}]},
]

UNISWAP_V3_QUOTER_ABI = [
    {"name": "quoteExactInputSingle", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "tokenIn",  "type": "address"},
         {"name": "tokenOut", "type": "address"},
         {"name": "fee",      "type": "uint24"},
         {"name": "amountIn", "type": "uint256"},
         {"name": "sqrtPriceLimitX96", "type": "uint160"},
     ],
     "outputs": [{"name": "amountOut", "type": "uint256"}]},
]

CHAINLINK_ABI = [
    {"name": "latestRoundData", "type": "function", "stateMutability": "view",
     "inputs": [],
     "outputs": [
         {"name": "roundId",         "type": "uint80"},
         {"name": "answer",          "type": "int256"},
         {"name": "startedAt",       "type": "uint256"},
         {"name": "updatedAt",       "type": "uint256"},
         {"name": "answeredInRound", "type": "uint80"},
     ]},
    {"name": "decimals", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint8"}]},
]

# Common fee tiers for Uniswap v3
V3_FEE_LOW    = 500    # 0.05% — stablecoin pairs
V3_FEE_MEDIUM = 3000   # 0.30% — most pairs
V3_FEE_HIGH   = 10000  # 1.00% — exotic pairs
