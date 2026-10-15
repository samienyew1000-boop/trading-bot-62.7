import os
import MetaTrader5 as mt5
from dotenv import load_dotenv

load_dotenv()

# Telegram Credentials
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8798993394:AAGSxsOqztxRT-Js5GPtO72C9uB81p7hpfM")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5663531258")

# MT5 Account Credentials
MT5_LOGIN = int(os.getenv("MT5_LOGIN", "477570961"))
MT5_SERVER = os.getenv("MT5_SERVER", "Exness-MT5Trial9")
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "Sami123@")
MT5_PATH = os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")

# Multi-Asset Strategy Settings
SYMBOLS = ["XAUUSD", "BTCUSD", "USTEC"]

# Strategy Indicators Configuration
RSI_PERIOD = 2
EMA_FAST = 5
EMA_MID1 = 20
EMA_MID2 = 50
EMA_MACRO = 200
ATR_PERIOD = 14

ASSET_CONFIG = {
    "XAUUSD": {
        "name": "Gold",
        "symbol": "XAUUSD",
        "icon": "🥇",
        "timeframe": mt5.TIMEFRAME_H1,
        "timeframe_name": "1H",
        # Engine Control
        "enable_runner": True,
        "enable_sniper": True,
        "runner_magic": 888101,
        "sniper_magic": 888201,
        # Engine 1: Institutional Trend Runner
        "rr_ratio": 2.0,           # 1:2.0 Risk-to-Reward
        "session_start_utc": 7,     # 07:00 UTC (10:00 AM Ethiopia)
        "session_end_utc": 16,      # 16:00 UTC (07:00 PM Ethiopia)
        "sl_buffer_atr": 0.3,
        "min_risk": 2.0,
        "max_risk": 30.0,
        # Engine 2: AI Sniper Mean Reversion (84.6% Win Rate)
        "sniper_sl_atr": 2.5,
        "sniper_rsi_buy": 10,
        "sniper_rsi_sell": 90,
        "default_lot": 0.01
    },
    "BTCUSD": {
        "name": "Bitcoin",
        "symbol": "BTCUSD",
        "icon": "🪙",
        "timeframe": mt5.TIMEFRAME_H1,
        "timeframe_name": "1H",
        # Engine Control
        "enable_runner": True,
        "enable_sniper": True,
        "runner_magic": 888103,
        "sniper_magic": 888203,
        # Engine 1: Institutional Trend Runner
        "rr_ratio": 2.0,           # 1:2.0 Risk-to-Reward
        "session_start_utc": 7,     # 07:00 UTC (10:00 AM Ethiopia)
        "session_end_utc": 20,      # 20:00 UTC (11:00 PM Ethiopia)
        "sl_buffer_atr": 0.3,
        "min_risk": 100.0,
        "max_risk": 3000.0,
        # Engine 2: AI Sniper Mean Reversion (86.6% Win Rate)
        "sniper_sl_atr": 2.5,
        "sniper_rsi_buy": 10,
        "sniper_rsi_sell": 90,
        "default_lot": 0.01
    },
    "USTEC": {
        "name": "US Tech 100",
        "symbol": "USTEC",
        "icon": "💻",
        "timeframe": mt5.TIMEFRAME_H1,
        "timeframe_name": "1H",
        # Engine Control
        "enable_runner": False,     # Disabled to prevent trend chop drawdown
        "enable_sniper": True,      # AI Sniper yields 79.5% - 81.8% Win Rate!
        "runner_magic": 888102,
        "sniper_magic": 888202,
        # Engine 1: Trend Runner Settings
        "rr_ratio": 2.0,
        "session_start_utc": 12,    # 12:00 UTC (03:00 PM Ethiopia)
        "session_end_utc": 20,      # 20:00 UTC (11:00 PM Ethiopia)
        "sl_buffer_atr": 0.3,
        "min_risk": 30.0,
        "max_risk": 400.0,
        # Engine 2: AI Sniper Mean Reversion (79.5% Win Rate)
        "sniper_sl_atr": 2.5,
        "sniper_rsi_buy": 10,
        "sniper_rsi_sell": 90,
        "default_lot": 0.05         # Exness min volume for USTEC is 0.05
    }
}

# Scan Polling Interval in seconds
POLL_INTERVAL = 15
