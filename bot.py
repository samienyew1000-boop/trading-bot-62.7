import time
import threading
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import config
from smc_engine import (
    identify_swings,
    get_market_structure,
    detect_valid_order_blocks,
    OrderBlock
)
from chart_generator import generate_candlestick_chart
from telegram_notifier import (
    send_telegram_message,
    send_telegram_photo,
    get_telegram_updates,
    notify_bos,
    notify_direction_change,
    notify_ob_mitigated,
    notify_reaction,
    notify_entry,
    notify_ob_failed
)

class SymbolTracker:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.direction = "NEUTRAL"
        self.last_bos_time = None
        self.active_htf_ob: OrderBlock = None
        self.state = "IDLE"  # IDLE -> OB_MITIGATED -> REACTION_SEEN -> ENTRY_TRIGGERED
        self.active_ltf_ob: OrderBlock = None
        self.last_closed_htf_time = None
        self.last_price = 0.0

def get_candles(symbol: str, timeframe, count: int) -> pd.DataFrame:
    """Fetch candles from MetaTrader 5 as a pandas DataFrame."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    return pd.DataFrame(rates)

def analyze_symbol(tracker: SymbolTracker):
    symbol = tracker.symbol
    
    # 1. Fetch HTF Candles (1H)
    df_htf = get_candles(symbol, config.HTF, config.CANDLE_COUNT_HTF)
    if df_htf.empty or len(df_htf) < 20:
        return

    latest_htf = df_htf.iloc[-1]           # Live forming candle
    closed_htf = df_htf.iloc[-2]           # Fully closed candle
    tracker.last_price = latest_htf['close']
    current_price = latest_htf['close']

    # 2. Check Market Structure & Swings on HTF (using closed candles)
    swings_htf = identify_swings(df_htf.iloc[:-1], swing_bars=config.SWING_BARS)
    current_direction, last_h, last_l = get_market_structure(df_htf.iloc[:-1], swings_htf)

    # Check for BOS on closed candle (Candle Body Close beyond recent swing)
    if last_h and last_l and tracker.last_closed_htf_time != closed_htf['time']:
        # Bullish BOS: candle body closes above previous swing high
        if closed_htf['close'] > last_h.price and closed_htf['open'] <= last_h.price:
            if tracker.last_bos_time != closed_htf['time']:
                tracker.last_bos_time = closed_htf['time']
                notify_bos(symbol, config.HTF_NAME, "BULLISH", last_h.price, current_price)
                if tracker.direction != "BULLISH":
                    notify_direction_change(symbol, config.HTF_NAME, "BULLISH", f"Swing High {last_h.price:.5f} በ Body Close ተሰብሯል")
                    tracker.direction = "BULLISH"
                    tracker.active_htf_ob = None
                    tracker.state = "IDLE"

        # Bearish BOS: candle body closes below previous swing low
        elif closed_htf['close'] < last_l.price and closed_htf['open'] >= last_l.price:
            if tracker.last_bos_time != closed_htf['time']:
                tracker.last_bos_time = closed_htf['time']
                notify_bos(symbol, config.HTF_NAME, "BEARISH", last_l.price, current_price)
                if tracker.direction != "BEARISH":
                    notify_direction_change(symbol, config.HTF_NAME, "BEARISH", f"Swing Low {last_l.price:.5f} በ Body Close ተሰብሯል")
                    tracker.direction = "BEARISH"
                    tracker.active_htf_ob = None
                    tracker.state = "IDLE"

    if tracker.direction == "NEUTRAL" and current_direction != "NEUTRAL":
        tracker.direction = current_direction
        notify_direction_change(symbol, config.HTF_NAME, current_direction, "የመጀመሪያው የገበያ አቅጣጫ ተለይቷል")

    # 3. Detect HTF Valid Order Blocks aligned with Direction
    obs = detect_valid_order_blocks(df_htf, tracker.direction)
    target_ob_type = "BEARISH" if tracker.direction == "BEARISH" else "BULLISH"
    valid_obs = [ob for ob in obs if ob.ob_type == target_ob_type and not ob.is_failed]

    # Check Active OB for Failure (Broken by closed candle Body Close ONLY)
    if tracker.active_htf_ob:
        # Bearish OB fails ONLY if candle body closes above ob.high
        if tracker.active_htf_ob.ob_type == "BEARISH":
            body_top = max(closed_htf['open'], closed_htf['close'])
            if body_top > tracker.active_htf_ob.high:
                notify_ob_failed(symbol, config.HTF_NAME, "BEARISH OB", current_price)
                tracker.active_htf_ob = None
                tracker.state = "IDLE"
        # Bullish OB fails ONLY if candle body closes below ob.low
        elif tracker.active_htf_ob.ob_type == "BULLISH":
            body_bottom = min(closed_htf['open'], closed_htf['close'])
            if body_bottom < tracker.active_htf_ob.low:
                notify_ob_failed(symbol, config.HTF_NAME, "BULLISH OB", current_price)
                tracker.active_htf_ob = None
                tracker.state = "IDLE"

    # Step 1: Check for HTF OB Mitigation (Price taps into fresh valid OB)
    if tracker.state == "IDLE" and valid_obs:
        for ob in reversed(valid_obs):
            # Price touches the OB
            if ob.ob_type == "BEARISH" and latest_htf['high'] >= ob.low and latest_htf['low'] <= ob.high:
                tracker.active_htf_ob = ob
                tracker.state = "OB_MITIGATED"
                notify_ob_mitigated(symbol, config.HTF_NAME, "BEARISH", ob.high, ob.low, current_price)
                chart_file = generate_candlestick_chart(df_htf, symbol, config.HTF_NAME, ob=ob, output_path=f"{symbol}_htf_ob.png")
                if chart_file:
                    send_telegram_photo(chart_file, caption=f"📸 <b>{symbol} {config.HTF_NAME} Bearish OB Zone</b>")
                break
            elif ob.ob_type == "BULLISH" and latest_htf['low'] <= ob.high and latest_htf['high'] >= ob.low:
                tracker.active_htf_ob = ob
                tracker.state = "OB_MITIGATED"
                notify_ob_mitigated(symbol, config.HTF_NAME, "BULLISH", ob.high, ob.low, current_price)
                chart_file = generate_candlestick_chart(df_htf, symbol, config.HTF_NAME, ob=ob, output_path=f"{symbol}_htf_ob.png")
                if chart_file:
                    send_telegram_photo(chart_file, caption=f"📸 <b>{symbol} {config.HTF_NAME} Bullish OB Zone</b>")
                break

    # 4. Lower Timeframe (5M) Monitoring if OB is Mitigated
    if tracker.state in ["OB_MITIGATED", "REACTION_SEEN"]:
        df_ltf = get_candles(symbol, config.LTF, config.CANDLE_COUNT_LTF)
        if df_ltf.empty or len(df_ltf) < 10:
            return

        ltf_latest = df_ltf.iloc[-1]
        ltf_prev = df_ltf.iloc[-2]
        ltf_price = ltf_latest['close']

        # Step 2: Check for Reaction
        if tracker.state == "OB_MITIGATED":
            ltf_obs = detect_valid_order_blocks(df_ltf, tracker.direction)
            if tracker.direction == "BEARISH":
                # Reaction: Bearish rejection candle + formation of LTF Bearish OB
                is_rejection = ltf_prev['close'] < ltf_prev['open'] and (ltf_prev['high'] - max(ltf_prev['open'], ltf_prev['close'])) > (abs(ltf_prev['close'] - ltf_prev['open']) * 0.4)
                bearish_ltf_obs = [o for o in ltf_obs if o.ob_type == "BEARISH" and not o.is_failed]
                if is_rejection or len(bearish_ltf_obs) > 0:
                    tracker.state = "REACTION_SEEN"
                    tracker.active_ltf_ob = bearish_ltf_obs[-1] if bearish_ltf_obs else None
                    notify_reaction(symbol, config.LTF_NAME, "SELL (BEARISH)", ltf_price)

            elif tracker.direction == "BULLISH":
                # Reaction: Bullish rejection candle + formation of LTF Bullish OB
                is_rejection = ltf_prev['close'] > ltf_prev['open'] and (min(ltf_prev['open'], ltf_prev['close']) - ltf_prev['low']) > (abs(ltf_prev['close'] - ltf_prev['open']) * 0.4)
                bullish_ltf_obs = [o for o in ltf_obs if o.ob_type == "BULLISH" and not o.is_failed]
                if is_rejection or len(bullish_ltf_obs) > 0:
                    tracker.state = "REACTION_SEEN"
                    tracker.active_ltf_ob = bullish_ltf_obs[-1] if bullish_ltf_obs else None
                    notify_reaction(symbol, config.LTF_NAME, "BUY (BULLISH)", ltf_price)

        # Step 3: Check for Return to LTF OB & Entry Confirmation
        elif tracker.state == "REACTION_SEEN":
            if tracker.active_ltf_ob:
                # Retest condition + Confirmation candle closed in direction
                if tracker.direction == "BEARISH":
                    tapped = ltf_latest['high'] >= tracker.active_ltf_ob.low
                    confirmed_bearish = ltf_prev['close'] < ltf_prev['open']
                    if tapped and confirmed_bearish:
                        sl = tracker.active_ltf_ob.high + (tracker.active_ltf_ob.high - tracker.active_ltf_ob.low) * 0.2
                        risk = abs(ltf_price - sl)
                        tp = ltf_price - (risk * 3.0)  # 1:3 RR
                        rr = 3.0
                        notify_entry(symbol, "SELL", ltf_price, sl, tp, rr)
                        chart_file = generate_candlestick_chart(df_ltf, symbol, config.LTF_NAME, ob=tracker.active_ltf_ob, sl=sl, tp=tp, output_path=f"{symbol}_sell_entry.png")
                        if chart_file:
                            send_telegram_photo(chart_file, caption=f"🎯 <b>{symbol} SELL Entry Chart</b>\nSL: <code>{sl:.5f}</code> | TP: <code>{tp:.5f}</code>")
                        tracker.state = "ENTRY_TRIGGERED"

                elif tracker.direction == "BULLISH":
                    tapped = ltf_latest['low'] <= tracker.active_ltf_ob.high
                    confirmed_bullish = ltf_prev['close'] > ltf_prev['open']
                    if tapped and confirmed_bullish:
                        sl = tracker.active_ltf_ob.low - (tracker.active_ltf_ob.high - tracker.active_ltf_ob.low) * 0.2
                        risk = abs(sl - ltf_price)
                        tp = ltf_price + (risk * 3.0)  # 1:3 RR
                        rr = 3.0
                        notify_entry(symbol, "BUY", ltf_price, sl, tp, rr)
                        chart_file = generate_candlestick_chart(df_ltf, symbol, config.LTF_NAME, ob=tracker.active_ltf_ob, sl=sl, tp=tp, output_path=f"{symbol}_buy_entry.png")
                        if chart_file:
                            send_telegram_photo(chart_file, caption=f"🎯 <b>{symbol} BUY Entry Chart</b>\nSL: <code>{sl:.5f}</code> | TP: <code>{tp:.5f}</code>")
                        tracker.state = "ENTRY_TRIGGERED"

    tracker.last_closed_htf_time = closed_htf['time']

def handle_telegram_commands(trackers):
    """Background listener for user commands sent to the Telegram bot."""
    last_update_id = 0
    while True:
        try:
            updates = get_telegram_updates(offset=last_update_id + 1)
            for upd in updates:
                last_update_id = upd.get("update_id", last_update_id)
                msg = upd.get("message", {})
                text = msg.get("text", "").strip()
                chat_id = str(msg.get("chat", {}).get("id", ""))
                
                if chat_id != str(config.TELEGRAM_CHAT_ID):
                    continue

                if text in ["/status", "status", "/Status"]:
                    status_text = "📊 <b>የገበያ ወቅታዊ ሁኔታ (Live Status Report):</b>\n\n"
                    for sym, tr in trackers.items():
                        dir_icon = "🟢" if tr.direction == "BULLISH" else ("🔴" if tr.direction == "BEARISH" else "⚪")
                        ob_info = f"<code>{tr.active_htf_ob.low:.5f} - {tr.active_htf_ob.high:.5f}</code>" if tr.active_htf_ob else "None"
                        status_text += (
                            f"{dir_icon} <b>{sym}</b>\n"
                            f"  • Price: <code>{tr.last_price:.5f}</code>\n"
                            f"  • Structure: <b>{tr.direction}</b>\n"
                            f"  • State: <code>{tr.state}</code>\n"
                            f"  • Active OB: {ob_info}\n\n"
                        )
                    status_text += "⏱ <i>ቦቱ 24/7 እየተከታተለ ሴትአፕ ሲገኝ ኖቲፊኬሽን ይልካል።</i>"
                    send_telegram_message(status_text)
                    
                elif text in ["/help", "help", "/start"]:
                    help_text = (
                        "🤖 <b>SMC Trading Bot Commands:</b>\n\n"
                        "👉 <code>/status</code> — የሁሉንም Pairs (EURUSD, XAUUSD, USDCAD) ወቅታዊ ሁኔታ፣ ዋጋ እና አቅጣጫ ያሳያል\n"
                        "👉 <code>/help</code> — ይህንን የትዕዛዝ መመሪያ ያሳያል\n\n"
                        "<i>ቦቱ በራሱ ሴትአፕ ሲያገኝ (BOS, OB Mitigation, Reaction, Entry) ያሳውቅዎታል።</i>"
                    )
                    send_telegram_message(help_text)
        except Exception:
            pass
        time.sleep(3)

def main():
    print("==================================================")
    print(" 🚀 SMC PRICE ACTION TRADING BOT IS STARTING...")
    print("==================================================")
    
    if not mt5.initialize():
        print(f"[FATAL] MT5 initialization failed: {mt5.last_error()}")
        return
        
    account = mt5.account_info()
    print(f"[INFO] Connected to MT5 Account: {account.login} ({account.server})")
    print(f"[INFO] Monitoring Symbols: {', '.join(config.SYMBOLS)}")
    print(f"[INFO] HTF: {config.HTF_NAME} | LTF: {config.LTF_NAME}")
    
    trackers = {sym: SymbolTracker(sym) for sym in config.SYMBOLS}
    
    # Start Telegram Command Listener Thread
    cmd_thread = threading.Thread(target=handle_telegram_commands, args=(trackers,), daemon=True)
    cmd_thread.start()
    print("[INFO] Telegram command listener thread started.")
    
    # Startup Notification to Telegram
    startup_msg = (
        f"🤖 <b>የ SMC የትሬዲንግ ቦት ስራ ጀምሯል!</b>\n\n"
        f"📊 <b>Symbols:</b> {', '.join(config.SYMBOLS)}\n"
        f"⏱ <b>Higher Timeframe:</b> {config.HTF_NAME}\n"
        f"⏱ <b>Entry Timeframe:</b> {config.LTF_NAME}\n"
        f"💼 <b>MT5 Account:</b> <code>{account.login}</code>\n\n"
        f"💡 <i>በማንኛውም ሰዓት <code>/status</code> ብለው በመላክ የገበያውን ወቅታዊ ሁኔታ ማየት ይችላሉ!</i>"
    )
    send_telegram_message(startup_msg)
    
    try:
        while True:
            for symbol, tracker in trackers.items():
                try:
                    analyze_symbol(tracker)
                except Exception as e:
                    print(f"[ERROR] Error analyzing {symbol}: {e}")
            time.sleep(config.POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n[INFO] Bot stopped by user.")
    finally:
        mt5.shutdown()
        print("[INFO] MT5 connection closed.")

if __name__ == "__main__":
    main()
