import os
import MetaTrader5 as mt5
from dotenv import load_dotenv

load_dotenv()

# Telegram Credentials
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8965440827:AAHLTk_jTMR1_fxw2xX9VfeSbTKvGWwdURM")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5663531258")

# Asset & Timeframe (Gold 62.7% Win Rate Strategy)
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_H1
TIMEFRAME_NAME = "1H"

# Risk & Order Management
DEFAULT_LOT_SIZE = 0.01  # Safe micro lot for Demo / Small balance
RISK_REWARD_RATIO = 2.0  # 1:2.0 Risk-to-Reward
MAGIC_NUMBER = 8882026

# Session Volume Filter (London & New York Active Hours)
SESSION_START_UTC = 7   # 07:00 UTC (10:00 AM Ethiopian Time)
SESSION_END_UTC = 16    # 16:00 UTC (07:00 PM Ethiopian Time)

# Scan Polling Interval in seconds
POLL_INTERVAL = 15
