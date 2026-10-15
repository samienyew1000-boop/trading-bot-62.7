import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message: str) -> bool:
    """Send an HTML-formatted message to the Telegram chat."""
    if not BOT_TOKEN or not CHAT_ID:
        print("[ERROR] Missing Telegram Token or Chat ID")
        return False
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        if data.get("ok"):
            return True
        else:
            print(f"[ERROR] Telegram API error: {data.get('description')}")
            return False
    except Exception as e:
        print(f"[ERROR] Telegram request failed: {e}")
        return False

def send_telegram_menu(message: str, buttons: list) -> bool:
    """Send an HTML message with inline buttons."""
    if not BOT_TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": buttons}
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.json().get("ok", False)
    except Exception as e:
        print(f"[ERROR] Failed to send menu: {e}")
        return False

def edit_telegram_message(message_id: int, text: str, buttons: list = None) -> bool:
    """Edit an existing message and its inline buttons."""
    if not BOT_TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": CHAT_ID,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if buttons is not None:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.json().get("ok", False)
    except Exception:
        return False

def answer_callback_query(query_id: str, text: str = None) -> bool:
    """Acknowledge Telegram callback query from button clicks."""
    if not BOT_TOKEN:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": query_id}
    if text:
        payload["text"] = text
    try:
        requests.post(url, json=payload, timeout=5)
        return True
    except Exception:
        return False

def get_telegram_updates(offset=None):
    """Fetch user messages/commands from Telegram."""
    if not BOT_TOKEN:
        return []
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 2}
    if offset:
        params["offset"] = offset
    try:
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            return res.json().get("result", [])
    except Exception:
        pass
    return []

def send_telegram_photo(photo_path: str, caption: str = "") -> bool:
    """Send an image / chart screenshot to the Telegram chat."""
    if not BOT_TOKEN or not CHAT_ID:
        print("[ERROR] Missing Telegram Token or Chat ID")
        return False
    if not os.path.exists(photo_path):
        print(f"[ERROR] Photo path not found: {photo_path}")
        return False
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"}
            res = requests.post(url, files=files, data=data, timeout=15)
            return res.json().get("ok", False)
    except Exception as e:
        print(f"[ERROR] Failed to send photo: {e}")
        return False


# Specific Notification Handlers matching user strategy:

def notify_bos(symbol: str, timeframe: str, direction: str, broken_level: float, current_price: float):
    icon = "🟢" if direction == "BULLISH" else "🔴"
    msg = (
        f"{icon} <b>BOS ተደርጓል (Break of Structure)!</b>\n\n"
        f"📊 <b>Symbol:</b> <code>{symbol}</code>\n"
        f"⏱ <b>Timeframe:</b> {timeframe}\n"
        f"📈 <b>Direction:</b> <b>{direction}</b>\n"
        f"💥 <b>Broken Level:</b> <code>{broken_level:.5f}</code> (Body Close)\n"
        f"💵 <b>Current Price:</b> <code>{current_price:.5f}</code>\n"
        f"ℹ️ <i>ገበያው አዲስ {direction} BOS ፈጥሯል። አሁን ተከታይ pullback እና OB እንጠብቃለን።</i>"
    )
    return send_telegram_message(msg)

def notify_direction_change(symbol: str, timeframe: str, new_direction: str, reason: str):
    icon = "🔄"
    arrow = "↗️ BULLISH (BUY)" if new_direction == "BULLISH" else "↘️ BEARISH (SELL)"
    msg = (
        f"{icon} <b>የገበያ አቅጣጫ ተቀይሯል (Market Direction Shift)!</b>\n\n"
        f"📊 <b>Symbol:</b> <code>{symbol}</code>\n"
        f"⏱ <b>Timeframe:</b> {timeframe}\n"
        f"🎯 <b>አዲሱ አቅጣጫ:</b> <b>{arrow}</b>\n"
        f"📝 <b>ምክንያት:</b> {reason}\n"
        f"ℹ️ <i>ከዚህ በኋላ የምንፈልገው የ{new_direction} ሴትአፖችን ብቻ ነው!</i>"
    )
    return send_telegram_message(msg)

def notify_ob_mitigated(symbol: str, timeframe: str, ob_type: str, ob_high: float, ob_low: float, current_price: float):
    arrow = "🟩 BULLISH OB (BUY Zone)" if ob_type == "BULLISH" else "🟥 BEARISH OB (SELL Zone)"
    msg = (
        f"📍 <b>OB Mitigate ተደርጓል (Price Tapped Order Block)!</b>\n\n"
        f"📊 <b>Symbol:</b> <code>{symbol}</code>\n"
        f"⏱ <b>Timeframe:</b> {timeframe}\n"
        f"🧱 <b>Zone:</b> {arrow}\n"
        f"📏 <b>OB Range:</b> <code>{ob_low:.5f} - {ob_high:.5f}</code>\n"
        f"💵 <b>Current Price:</b> <code>{current_price:.5f}</code>\n\n"
        f"👀 <i>ዋጋው ወደ HTF OB ገብቷል! አሁን በ 5M Timeframe ላይ Reaction እንጠብቃለን...</i>"
    )
    return send_telegram_message(msg)

def notify_reaction(symbol: str, ltf_name: str, direction: str, reaction_price: float):
    msg = (
        f"⚡ <b>Reaction ሰጥቷል (LTF Rejection Detected)!</b>\n\n"
        f"📊 <b>Symbol:</b> <code>{symbol}</code>\n"
        f"⏱ <b>Timeframe:</b> {ltf_name}\n"
        f"🎯 <b>Expected Move:</b> <b>{direction}</b>\n"
        f"💵 <b>Reaction Price:</b> <code>{reaction_price:.5f}</code>\n\n"
        f"⏳ <i>ገበያው ከ HTF OB ጥሩ Reaction አሳይቷል። አሁን ወደ LTF OB ሲመለስ Entry ይሰጠናል!</i>"
    )
    return send_telegram_message(msg)

def notify_entry(symbol: str, direction: str, entry_price: float, sl_price: float, tp_price: float, rr: float):
    icon = "🚀 BUY" if direction == "BUY" else "🔻 SELL"
    msg = (
        f"🎯 <b>ተመልሷል ENTRY! (Setup Confirmed)</b>\n\n"
        f"📊 <b>Symbol:</b> <code>{symbol}</code>\n"
        f"🚦 <b>Signal:</b> <b>{icon}</b>\n"
        f"📍 <b>Entry Price:</b> <code>{entry_price:.5f}</code>\n"
        f"🛑 <b>Stop Loss (SL):</b> <code>{sl_price:.5f}</code>\n"
        f"🎯 <b>Take Profit (TP):</b> <code>{tp_price:.5f}</code>\n"
        f"⚖️ <b>Risk to Reward:</b> <code>1:{rr:.1f}</code>\n\n"
        f"✅ <i>ዋጋው ወደ OB ተመልሶ ማረጋገጫ (Confirmation candle) ሰጥቷል!</i>"
    )
    return send_telegram_message(msg)

def notify_ob_failed(symbol: str, timeframe: str, ob_type: str, break_price: float):
    msg = (
        f"❌ <b>Fail አድርጓል (OB Invalidated)!</b>\n\n"
        f"📊 <b>Symbol:</b> <code>{symbol}</code>\n"
        f"⏱ <b>Timeframe:</b> {timeframe}\n"
        f"🧱 <b>Invalidated OB:</b> {ob_type}\n"
        f"⚠️ <b>Break Price:</b> <code>{break_price:.5f}</code> (Body Close)\n\n"
        f"ℹ️ <i>ሻማው በ Body ስለሰበረው OBው Fail አድርጓል። (Wick አይደለም - Body Close ነው)።</i>"
    )
    return send_telegram_message(msg)
