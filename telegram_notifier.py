import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message: str) -> bool:
    """Send an HTML-formatted message to the Telegram chat."""
    if not BOT_TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    for _ in range(2):
        try:
            response = requests.post(url, json=payload, timeout=25)
            if response.status_code == 200:
                return response.json().get("ok", False)
        except Exception as e:
            print(f"[WARNING] Telegram send attempt failed: {e}")
    return False

def send_telegram_photo(photo_path: str, caption: str = "") -> bool:
    """Send a generated chart photo with HTML caption."""
    if not BOT_TOKEN or not CHAT_ID or not os.path.exists(photo_path):
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    for _ in range(2):
        try:
            with open(photo_path, "rb") as f:
                files = {"photo": f}
                data = {"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"}
                res = requests.post(url, files=files, data=data, timeout=30)
                if res.status_code == 200:
                    return res.json().get("ok", False)
        except Exception as e:
            print(f"[WARNING] Failed to send photo attempt: {e}")
    return False

def send_telegram_menu(message: str, buttons: list) -> bool:
    """Send an HTML message with inline interactive buttons."""
    if not BOT_TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": buttons}
    }
    for _ in range(2):
        try:
            res = requests.post(url, json=payload, timeout=25)
            if res.status_code == 200:
                return res.json().get("ok", False)
        except Exception as e:
            print(f"[WARNING] Failed to send menu attempt: {e}")
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
        res = requests.post(url, json=payload, timeout=20)
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
        requests.post(url, json=payload, timeout=10)
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
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            return res.json().get("result", [])
    except Exception:
        pass
    return []
