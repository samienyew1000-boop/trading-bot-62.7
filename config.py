import os
import MetaTrader5 as mt5
from dotenv import load_dotenv

load_dotenv()

# Telegram Credentials
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8965440827:AAHLTk_jTMR1_fxw2xX9VfeSbTKvGWwdURM")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5663531258")

# Trading Symbols to Monitor
SYMBOLS = ["EURUSD", "XAUUSD", "USDCAD"]

# Timeframes
# Higher Timeframe (Structure & Main Leg OB): H1 (or M15)
HTF = mt5.TIMEFRAME_H1
HTF_NAME = "1H"

# Lower Timeframe (Reaction & Entry Confirmation): M5
LTF = mt5.TIMEFRAME_M5
LTF_NAME = "5M"

# Swing Detection Sensitivity (Bars to left and right)
SWING_BARS = 3

# Number of candles to fetch for analysis
CANDLE_COUNT_HTF = 200
CANDLE_COUNT_LTF = 200

# Bot polling interval in seconds
POLL_INTERVAL = 15
