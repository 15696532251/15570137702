# ============================================================
#  策略配置文件 —— 你只需要修改这里，不需要懂代码
# ============================================================

# 【第一步】交易所 API 配置
# 到 Binance 官网 → 账户 → API管理 → 创建API
# 权限只勾选「现货交易」，不要勾选「提币」！
EXCHANGE     = "binance"         # binance / okx / bybit
API_KEY      = "在这里填你的API_KEY"
API_SECRET   = "在这里填你的API_SECRET"
OKX_PASSWORD = ""               # 只有OKX需要填，其他留空

# 【第二步】交易参数
SYMBOL       = "BTC/USDT"       # 交易对（BTC/USDT ETH/USDT SOL/USDT 等）
TRADE_USDT   = 500              # 每次买入金额（USDT），建议从小额开始

# 【第三步】策略参数（回测中表现最好的参数）
FAST_MA      = 20               # 短期均线天数
SLOW_MA      = 60               # 长期均线天数
MA_TYPE      = "ema"            # ema（指数均线）或 sma（简单均线）
RSI_CAP      = 75               # RSI超过此值不追涨

# 【第四步】风控参数
MAX_DRAWDOWN_HALT = 0.30        # 总亏损超过30%自动停止
STOP_LOSS_PCT     = 0.12        # 单笔亏损超过12%止损

# 【第五步】运行模式
DRY_RUN      = True             # True=模拟，不真实下单；改成 False 才真实交易
TIMEFRAME    = "1d"             # K线周期：1d=日线 4h=4小时线
CHECK_HOURS  = 24               # 多少小时检查一次信号（日线策略建议24）
USE_TESTNET  = False            # True=使用交易所模拟盘（需要单独注册）
