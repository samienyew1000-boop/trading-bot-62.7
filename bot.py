import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
import time
import threading
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import config
from chart_generator import generate_candlestick_chart
from telegram_notifier import (
    send_telegram_message,
    send_telegram_photo,
    send_telegram_menu,
    edit_telegram_message,
    answer_callback_query,
    get_telegram_updates
)
from trade_logger import (
    record_trade_entry,
    record_trade_exit,
    get_performance_summary
)

class GoldBotState:
    def __init__(self):
        self.last_candle_time = None
        self.current_trend = "NEUTRAL"
        self.in_position = False
        self.position_ticket = None
        self.position_type = None
        self.risk_mode = "PERCENT"  # "PERCENT" or "FIXED"
        self.risk_percent = 1.0     # 1.0%, 2.0%, 3.0%, 5.0%
        self.fixed_lot = 0.01       # 0.01, 0.02, 0.05
        self.auto_trade_enabled = True

state = GoldBotState()

def calculate_order_lot(sl_distance: float) -> float:
    """Calculate the lot size based on dynamic risk percent or fixed lot."""
    if state.risk_mode == "FIXED":
        return state.fixed_lot
        
    acc = mt5.account_info()
    equity = acc.equity if acc else 500.0
    risk_dollars = equity * (state.risk_percent / 100.0)
    
    sym_info = mt5.symbol_info(config.SYMBOL)
    vol_min = sym_info.volume_min if sym_info else 0.01
    vol_max = sym_info.volume_max if sym_info else 100.0
    vol_step = sym_info.volume_step if sym_info else 0.01
    contract_size = sym_info.trade_contract_size if sym_info else 100.0
    
    if sl_distance <= 0:
        return vol_min

    raw_lot = risk_dollars / (sl_distance * contract_size)
    steps = round(raw_lot / vol_step)
    lot = steps * vol_step
    lot = max(vol_min, min(vol_max, lot))
    return round(lot, 2)

def get_filling_mode(symbol_info):
    """Determine the valid execution filling mode for the broker."""
    if symbol_info.filling_mode & 1:
        return mt5.ORDER_FILLING_FOK
    elif symbol_info.filling_mode & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN

def check_open_positions():
    """Check if an open position already exists on XAUUSD."""
    positions = mt5.positions_get(symbol=config.SYMBOL)
    if positions is None:
        return None
    for pos in positions:
        if pos.magic == config.MAGIC_NUMBER or pos.symbol == config.SYMBOL:
            return pos
    return None

def open_market_trade(trade_type: str, lot: float, sl: float, tp: float):
    """Execute a market order directly on the MetaTrader 5 account."""
    if not state.auto_trade_enabled:
        print("[INFO] Auto-Trade is currently PAUSED. Skipping execution.")
        return None

    sym_info = mt5.symbol_info(config.SYMBOL)
    if not sym_info:
        print(f"[ERROR] Symbol {config.SYMBOL} not found in MT5")
        return None

    if not sym_info.visible:
        mt5.symbol_select(config.SYMBOL, True)

    tick = mt5.symbol_info_tick(config.SYMBOL)
    if not tick:
        print(f"[ERROR] Failed to get live tick for {config.SYMBOL}")
        return None

    price = tick.ask if trade_type == "BUY" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if trade_type == "BUY" else mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": config.SYMBOL,
        "volume": float(lot),
        "type": order_type,
        "price": float(round(price, sym_info.digits)),
        "sl": float(round(sl, sym_info.digits)),
        "tp": float(round(tp, sym_info.digits)),
        "deviation": 20,
        "magic": config.MAGIC_NUMBER,
        "comment": "Gold 62.7% Bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(sym_info),
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[ERROR] Trade failed: retcode={result.retcode}, comment={result.comment}")
        return None

    print(f"[SUCCESS] {trade_type} Order Executed! Ticket: {result.order}")
    record_trade_entry(result.order, config.SYMBOL, trade_type, lot, price, sl, tp)
    return result

def monitor_position_closure():
    """Detect when the open trade closes and report profit/loss to Telegram."""
    global state
    if not state.in_position or not state.position_ticket:
        return

    positions = mt5.positions_get(ticket=state.position_ticket)
    if not positions or len(positions) == 0:
        deals = mt5.history_deals_get(position=state.position_ticket)
        pnl = 0.0
        close_price = 0.0
        if deals and len(deals) > 1:
            exit_deal = deals[-1]
            pnl = exit_deal.profit
            close_price = exit_deal.price

        record_trade_exit(state.position_ticket, close_price, pnl)

        icon = "🎉 WIN (Take Profit Hit!)" if pnl >= 0 else "🛑 LOSS (Stop Loss Hit)"
        msg = (
            f"<b>{icon}</b>\n\n"
            f"📊 <b>Symbol:</b> <code>{config.SYMBOL}</code>\n"
            f"🎫 <b>Ticket:</b> <code>{state.position_ticket}</code>\n"
            f"💵 <b>Exit Price:</b> <code>{close_price:.3f}</code>\n"
            f"💰 <b>Net PnL:</b> <b>{pnl:+.2f} USD</b>\n"
            f"💼 <b>Account Equity:</b> <code>{mt5.account_info().equity:.2f} USD</code>"
        )
        send_telegram_message(msg)
        state.in_position = False
        state.position_ticket = None

def analyze_and_trade():
    """Institutional 62.7% Win Rate Strategy Analyzer & Auto-Trader for XAUUSD."""
    global state

    # 1. Manage active position if any
    existing_pos = check_open_positions()
    if existing_pos:
        state.in_position = True
        state.position_ticket = existing_pos.ticket
        state.position_type = "BUY" if existing_pos.type == mt5.ORDER_TYPE_BUY else "SELL"
        monitor_position_closure()
        return
    else:
        if state.in_position:
            monitor_position_closure()

    # 2. Fetch last 250 1H candles
    rates = mt5.copy_rates_from_pos(config.SYMBOL, config.TIMEFRAME, 0, 250)
    if rates is None or len(rates) < 200:
        return

    df = pd.DataFrame(rates)
    df['time_dt'] = pd.to_datetime(df['time'], unit='s')

    # Indicators
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()

    # ATR
    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift()).abs()
    lc = (df['low'] - df['close'].shift()).abs()
    df['atr'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean().bfill()

    closed_candle = df.iloc[-2]
    prior_candle = df.iloc[-3]
    latest_candle = df.iloc[-1]

    if state.last_candle_time == closed_candle['time']:
        return

    candle_hour = closed_candle['time_dt'].hour
    is_active_session = (config.SESSION_START_UTC <= candle_hour <= config.SESSION_END_UTC)
    atr = closed_candle['atr']

    if closed_candle['ema20'] > closed_candle['ema50'] and closed_candle['ema50'] > closed_candle['ema200']:
        state.current_trend = "BULLISH (UPTREND)"
    elif closed_candle['ema20'] < closed_candle['ema50'] and closed_candle['ema50'] < closed_candle['ema200']:
        state.current_trend = "BEARISH (DOWNTREND)"
    else:
        state.current_trend = "RANGING / CHOP"

    if not is_active_session:
        return

    # 3. BULLISH SETUP (BUY)
    if state.current_trend == "BULLISH (UPTREND)":
        if prior_candle['low'] <= prior_candle['ema20'] and closed_candle['close'] > prior_candle['high'] and closed_candle['close'] > closed_candle['open']:
            entry_p = latest_candle['open']
            sl_p = prior_candle['low'] - (atr * 0.3)
            risk = entry_p - sl_p
            if 1.5 <= risk <= 30.0:
                tp_p = entry_p + (risk * config.RISK_REWARD_RATIO)
                state.last_candle_time = closed_candle['time']
                order_lot = calculate_order_lot(risk)

                print(f"[TRIGGER] BUY Signal on XAUUSD! Entry: {entry_p}, SL: {sl_p}, TP: {tp_p}, Lot: {order_lot}")
                res = open_market_trade("BUY", order_lot, sl_p, tp_p)
                ticket_str = str(res.order) if res else ("Alert Mode (Paused)" if not state.auto_trade_enabled else "Simulation")

                chart_path = generate_candlestick_chart(df, config.SYMBOL, config.TIMEFRAME_NAME, sl=sl_p, tp=tp_p, output_path="gold_trade.png")
                caption = (
                    f"🚀 <b>XAUUSD BUY ORDER TRIGGERED!</b>\n\n"
                    f"🎫 <b>Ticket:</b> <code>{ticket_str}</code>\n"
                    f"📊 <b>Symbol:</b> <code>{config.SYMBOL}</code>\n"
                    f"📦 <b>Lot Size:</b> <code>{order_lot}</code>\n"
                    f"📍 <b>Entry:</b> <code>{entry_p:.3f}</code>\n"
                    f"🛑 <b>Stop Loss:</b> <code>{sl_p:.3f}</code>\n"
                    f"🎯 <b>Take Profit (1:2):</b> <code>{tp_p:.3f}</code>\n"
                    f"💼 <b>Balance:</b> <code>{mt5.account_info().balance:.2f} USD</code>\n\n"
                    f"<i>🎯 Strategy: Gold London/NY Pro-Trend 62.7% Edge</i>"
                )
                if chart_path:
                    send_telegram_photo(chart_path, caption=caption)
                else:
                    send_telegram_message(caption)

                if res:
                    state.in_position = True
                    state.position_ticket = res.order

    # 4. BEARISH SETUP (SELL)
    elif state.current_trend == "BEARISH (DOWNTREND)":
        if prior_candle['high'] >= prior_candle['ema20'] and closed_candle['close'] < prior_candle['low'] and closed_candle['close'] < closed_candle['open']:
            entry_p = latest_candle['open']
            sl_p = prior_candle['high'] + (atr * 0.3)
            risk = sl_p - entry_p
            if 1.5 <= risk <= 30.0:
                tp_p = entry_p - (risk * config.RISK_REWARD_RATIO)
                state.last_candle_time = closed_candle['time']
                order_lot = calculate_order_lot(risk)

                print(f"[TRIGGER] SELL Signal on XAUUSD! Entry: {entry_p}, SL: {sl_p}, TP: {tp_p}, Lot: {order_lot}")
                res = open_market_trade("SELL", order_lot, sl_p, tp_p)
                ticket_str = str(res.order) if res else ("Alert Mode (Paused)" if not state.auto_trade_enabled else "Simulation")

                chart_path = generate_candlestick_chart(df, config.SYMBOL, config.TIMEFRAME_NAME, sl=sl_p, tp=tp_p, output_path="gold_trade.png")
                caption = (
                    f"🔻 <b>XAUUSD SELL ORDER TRIGGERED!</b>\n\n"
                    f"🎫 <b>Ticket:</b> <code>{ticket_str}</code>\n"
                    f"📊 <b>Symbol:</b> <code>{config.SYMBOL}</code>\n"
                    f"📦 <b>Lot Size:</b> <code>{order_lot}</code>\n"
                    f"📍 <b>Entry:</b> <code>{entry_p:.3f}</code>\n"
                    f"🛑 <b>Stop Loss:</b> <code>{sl_p:.3f}</code>\n"
                    f"🎯 <b>Take Profit (1:2):</b> <code>{tp_p:.3f}</code>\n"
                    f"💼 <b>Balance:</b> <code>{mt5.account_info().balance:.2f} USD</code>\n\n"
                    f"<i>🎯 Strategy: Gold London/NY Pro-Trend 62.7% Edge</i>"
                )
                if chart_path:
                    send_telegram_photo(chart_path, caption=caption)
                else:
                    send_telegram_message(caption)

                if res:
                    state.in_position = True
                    state.position_ticket = res.order

# --- TELEGRAM ADMIN DASHBOARD HANDLERS ---

def get_admin_dashboard_markup():
    """Build the main admin dashboard text and interactive inline keyboard."""
    acc = mt5.account_info()
    tick = mt5.symbol_info_tick(config.SYMBOL)
    curr_p = tick.bid if tick else 0.0
    pos = check_open_positions()
    pos_str = f"<b>{pos.volume} lot</b> ({pos.profit:+.2f}$)" if pos else "None"

    trade_status = "🟢 Active (Auto-Execute)" if state.auto_trade_enabled else "⏸️ Paused (Alerts Only)"
    risk_disp = f"Dynamic {state.risk_percent}%" if state.risk_mode == "PERCENT" else f"Fixed {state.fixed_lot} Lot"

    text = (
        f"👑 <b>XAUUSD BOT ADMIN DASHBOARD</b>\n\n"
        f"💵 <b>Current Gold Price:</b> <code>{curr_p:.3f}</code>\n"
        f"📈 <b>1H Trend:</b> <b>{state.current_trend}</b>\n"
        f"🛡 <b>Risk Setting:</b> <code>{risk_disp}</code>\n"
        f"⚡ <b>Auto-Trading:</b> {trade_status}\n"
        f"🎫 <b>Open Position:</b> {pos_str}\n"
        f"💼 <b>Balance:</b> <code>{acc.balance:.2f} USD</code>\n"
        f"💎 <b>Equity:</b> <code>{acc.equity:.2f} USD</code>\n\n"
        f"<i>ከዚህ በታች ያሉትን ቁልፎች በመጫን ቦቱን መቆጣጠር ይችላሉ፦</i>"
    )

    buttons = [
        [
            {"text": "📊 Past Trades (Win/Loss)", "callback_data": "menu_trades"},
            {"text": "⚙️ Set Risk % / Lot Size", "callback_data": "menu_risk"}
        ],
        [
            {"text": "⏸️ Pause Trading" if state.auto_trade_enabled else "▶️ Resume Trading", "callback_data": "toggle_autotrade"},
            {"text": "💼 Account Details", "callback_data": "menu_account"}
        ],
        [
            {"text": "🔄 Refresh Dashboard", "callback_data": "menu_main"}
        ]
    ]
    return text, buttons

def get_trades_markup():
    """Build the past trades statistics page."""
    summary = get_performance_summary()
    tot = summary["total"]
    w = summary["wins"]
    l = summary["losses"]
    wr = summary["win_rate"]
    pnl = summary["net_profit"]
    pf = summary["profit_factor"]

    text = (
        f"📊 <b>PAST TRADES & WIN/LOSS REPORT</b>\n\n"
        f"📈 <b>Total Closed Trades:</b> <b>{tot}</b>\n"
        f"🏆 <b>Wins:</b> <b>{w}</b>\n"
        f"🛑 <b>Losses:</b> <b>{l}</b>\n"
        f"🎯 <b>Win Rate:</b> <b>{wr:.1f}%</b>\n"
        f"💰 <b>Net Profit:</b> <b>{pnl:+.2f} USD</b>\n"
        f"⚖️ <b>Profit Factor:</b> <b>{pf:.2f}</b>\n\n"
        f"<b>📋 የመጨረሻዎቹ 5 ትሬዶች፦</b>\n"
    )

    if not summary["recent_trades"]:
        text += "<i>ገና የተዘጋ ትሬድ የለም። ትሬዶች ሲዘጉ እዚህ ይዘረዘራሉ!</i>\n"
    else:
        for t in summary["recent_trades"]:
            icon = "🟢 WIN" if t["pnl"] >= 0 else "🔴 LOSS"
            text += f"• #{t['ticket']} | {t['type']} {t['lot']} | {icon} <b>{t['pnl']:+.2f}$</b> ({t['close_time']})\n"

    buttons = [
        [{"text": "🔙 Back to Admin Menu", "callback_data": "menu_main"}]
    ]
    return text, buttons

def get_risk_markup():
    """Build the lot size & risk percent setting page."""
    acc = mt5.account_info()
    eq = acc.equity if acc else 500.0
    
    if state.risk_mode == "PERCENT":
        current_setting = f"<b>Dynamic {state.risk_percent}% Risk</b> per trade"
        risk_cash = eq * (state.risk_percent / 100.0)
        est_lot = calculate_order_lot(18.24)
        detail = f"• አሁን ባለው Equity (${eq:.2f})፦ <b>~${risk_cash:.2f} USD</b> ስጋት\n• ለአማካይ SL (180 pips) የሚሰላው Lot፦ <b>{est_lot} Lot</b>"
    else:
        current_setting = f"<b>Fixed {state.fixed_lot} Lot</b>"
        detail = f"• በቋሚነት ለእያንዳንዱ ትሬድ <b>{state.fixed_lot} Lot</b> ይከፍታል"

    text = (
        f"⚙️ <b>SET RISK LEVEL & POSITION SIZING</b>\n\n"
        f"📊 <b>የአሁኑ አቀማመጥ፦</b> {current_setting}\n"
        f"{detail}\n\n"
        f"<b>🎯 1. በአካውንት ፐርሰንት (Dynamic Risk %)፦</b>\n"
        f"<i>(አካውንትዎ ሲያድግ የሎት መጠኑ በራሱ አብሮ ያድጋል)</i>\n"
        f"• <b>1% Risk</b>: በጣም ደህንነቱ የተጠበቀ (Recommended)\n"
        f"• <b>2% Risk</b>: መደበኛ እና የተመጣጠነ እድገት\n"
        f"• <b>3% Risk</b>: ፈጣን እድገት\n"
        f"• <b>5% Risk</b>: ከፍተኛ እድገት\n\n"
        f"<b>📦 2. በቋሚ የ Lot መጠን (Fixed Lot)፦</b>\n"
    )

    buttons = [
        [
            {"text": "✅ 1% Risk (Safe)" if (state.risk_mode == "PERCENT" and state.risk_percent == 1.0) else "1% Risk (Safe)", "callback_data": "set_risk_1"},
            {"text": "✅ 2% Risk" if (state.risk_mode == "PERCENT" and state.risk_percent == 2.0) else "2% Risk", "callback_data": "set_risk_2"}
        ],
        [
            {"text": "✅ 3% Risk" if (state.risk_mode == "PERCENT" and state.risk_percent == 3.0) else "3% Risk", "callback_data": "set_risk_3"},
            {"text": "✅ 5% Risk" if (state.risk_mode == "PERCENT" and state.risk_percent == 5.0) else "5% Risk", "callback_data": "set_risk_5"}
        ],
        [
            {"text": "✅ 0.01 Fixed" if (state.risk_mode == "FIXED" and state.fixed_lot == 0.01) else "0.01 Fixed", "callback_data": "set_fixed_0.01"},
            {"text": "✅ 0.02 Fixed" if (state.risk_mode == "FIXED" and state.fixed_lot == 0.02) else "0.02 Fixed", "callback_data": "set_fixed_0.02"}
        ],
        [
            {"text": "🔙 Back to Admin Menu", "callback_data": "menu_main"}
        ]
    ]
    return text, buttons

def get_account_markup():
    """Build account details page."""
    acc = mt5.account_info()
    text = (
        f"💼 <b>MT5 ACCOUNT DETAILS:</b>\n\n"
        f"👤 <b>Account Login:</b> <code>{acc.login}</code>\n"
        f"🏢 <b>Server:</b> <code>{acc.server}</code>\n"
        f"💵 <b>Balance:</b> <code>{acc.balance:.2f} USD</code>\n"
        f"💎 <b>Equity:</b> <code>{acc.equity:.2f} USD</code>\n"
        f"🔒 <b>Margin:</b> <code>{acc.margin:.2f} USD</code>\n"
        f"🆓 <b>Free Margin:</b> <code>{acc.margin_free:.2f} USD</code>\n"
        f"⚡ <b>Leverage:</b> <code>1:{acc.leverage}</code>\n"
        f"🛡 <b>Trade Allowed:</b> <code>{acc.trade_allowed}</code>"
    )
    buttons = [
        [{"text": "🔙 Back to Admin Menu", "callback_data": "menu_main"}]
    ]
    return text, buttons

def handle_telegram_interactive():
    """Background listener for user commands & inline button clicks."""
    last_id = 0
    while True:
        try:
            updates = get_telegram_updates(offset=last_id + 1)
            for upd in updates:
                last_id = upd.get("update_id", last_id)

                # 1. Handle Inline Button Clicks (Callback Queries)
                if "callback_query" in upd:
                    cq = upd["callback_query"]
                    cq_id = cq["id"]
                    data = cq.get("data", "")
                    msg_id = cq.get("message", {}).get("message_id")

                    if data == "menu_main":
                        txt, btn = get_admin_dashboard_markup()
                        edit_telegram_message(msg_id, txt, btn)
                        answer_callback_query(cq_id, "Dashboard Refreshed")

                    elif data == "menu_trades":
                        txt, btn = get_trades_markup()
                        edit_telegram_message(msg_id, txt, btn)
                        answer_callback_query(cq_id)

                    elif data == "menu_risk":
                        txt, btn = get_risk_markup()
                        edit_telegram_message(msg_id, txt, btn)
                        answer_callback_query(cq_id)

                    elif data.startswith("set_risk_"):
                        val = float(data.replace("set_risk_", ""))
                        state.risk_mode = "PERCENT"
                        state.risk_percent = val
                        txt, btn = get_risk_markup()
                        edit_telegram_message(msg_id, txt, btn)
                        answer_callback_query(cq_id, f"Risk set to {val}% per trade!")

                    elif data.startswith("set_fixed_"):
                        val = float(data.replace("set_fixed_", ""))
                        state.risk_mode = "FIXED"
                        state.fixed_lot = val
                        txt, btn = get_risk_markup()
                        edit_telegram_message(msg_id, txt, btn)
                        answer_callback_query(cq_id, f"Fixed Lot set to {val} Lot!")

                    elif data == "toggle_autotrade":
                        state.auto_trade_enabled = not state.auto_trade_enabled
                        txt, btn = get_admin_dashboard_markup()
                        edit_telegram_message(msg_id, txt, btn)
                        status_str = "Auto-Trading Activated 🟢" if state.auto_trade_enabled else "Auto-Trading Paused ⏸️"
                        answer_callback_query(cq_id, status_str)

                    elif data == "menu_account":
                        txt, btn = get_account_markup()
                        edit_telegram_message(msg_id, txt, btn)
                        answer_callback_query(cq_id)

                # 2. Handle Text Commands
                elif "message" in upd:
                    msg = upd["message"]
                    text = msg.get("text", "").strip()
                    chat_id = str(msg.get("chat", {}).get("id", ""))

                    if chat_id != str(config.TELEGRAM_CHAT_ID):
                        continue

                    if text in ["/admin", "/menu", "admin", "menu", "/start"]:
                        txt, btn = get_admin_dashboard_markup()
                        send_telegram_menu(txt, btn)

                    elif text in ["/trades", "trades"]:
                        txt, btn = get_trades_markup()
                        send_telegram_menu(txt, btn)

                    elif text in ["/risk", "risk"]:
                        txt, btn = get_risk_markup()
                        send_telegram_menu(txt, btn)

                    elif text.startswith("/risk"):
                        parts = text.split()
                        if len(parts) > 1:
                            try:
                                val = float(parts[1])
                                if 0.5 <= val <= 10.0:
                                    state.risk_mode = "PERCENT"
                                    state.risk_percent = val
                                    send_telegram_message(f"✅ <b>Risk set to {val}% per trade!</b>")
                            except ValueError:
                                pass

                    elif text.startswith("/setlot"):
                        parts = text.split()
                        if len(parts) > 1:
                            try:
                                val = float(parts[1])
                                if 0.01 <= val <= 2.0:
                                    state.risk_mode = "FIXED"
                                    state.fixed_lot = val
                                    send_telegram_message(f"✅ <b>Fixed Lot set to {val} Lot!</b>")
                            except ValueError:
                                pass

                    elif text in ["/status", "status"]:
                        txt, btn = get_admin_dashboard_markup()
                        send_telegram_menu(txt, btn)
                        answer_callback_query(cq_id)

                # 2. Handle Text Commands
                elif "message" in upd:
                    msg = upd["message"]
                    text = msg.get("text", "").strip()
                    chat_id = str(msg.get("chat", {}).get("id", ""))

                    if chat_id != str(config.TELEGRAM_CHAT_ID):
                        continue

                    if text in ["/admin", "/menu", "admin", "menu", "/start"]:
                        txt, btn = get_admin_dashboard_markup()
                        send_telegram_menu(txt, btn)

                    elif text in ["/trades", "trades"]:
                        txt, btn = get_trades_markup()
                        send_telegram_menu(txt, btn)

                    elif text in ["/risk", "risk"]:
                        txt, btn = get_risk_markup()
                        send_telegram_menu(txt, btn)

                    elif text.startswith("/setlot"):
                        parts = text.split()
                        if len(parts) > 1:
                            try:
                                val = float(parts[1])
                                if 0.01 <= val <= 1.0:
                                    state.lot_size = val
                                    send_telegram_message(f"✅ <b>Lot size updated to {val} Lot!</b>")
                            except ValueError:
                                pass

                    elif text in ["/status", "status"]:
                        txt, btn = get_admin_dashboard_markup()
                        send_telegram_menu(txt, btn)

        except Exception as e:
            print(f"[ERROR] Telegram handler error: {e}")
        time.sleep(2)

def main():
    print("==============================================================")
    print(" 🚀 XAUUSD INSTITUTIONAL AUTO-TRADING BOT (62.7% WIN RATE)")
    print("==============================================================")

    mt5_login = int(os.getenv("MT5_LOGIN", "0"))
    mt5_password = os.getenv("MT5_PASSWORD", "")
    mt5_server = os.getenv("MT5_SERVER", "")
    mt5_path = os.getenv("MT5_PATH", "")

    init_kwargs = {}
    if mt5_path:
        init_kwargs["path"] = mt5_path
    if mt5_login and mt5_password and mt5_server:
        init_kwargs["login"] = mt5_login
        init_kwargs["password"] = mt5_password
        init_kwargs["server"] = mt5_server

    init_success = mt5.initialize(**init_kwargs) if init_kwargs else mt5.initialize()

    if not init_success:
        print(f"[FATAL] MT5 initialization failed: {mt5.last_error()}")
        return

    term = mt5.terminal_info()
    acc = mt5.account_info()
    print(f"[INFO] Connected to MT5 Account: {acc.login} ({acc.server})")
    print(f"[INFO] Balance: {acc.balance} USD | Equity: {acc.equity} USD")
    print(f"[INFO] Terminal Trade Allowed (Algo Trading): {term.trade_allowed}")

    # Start Telegram Listener Thread
    cmd_thread = threading.Thread(target=handle_telegram_interactive, daemon=True)
    cmd_thread.start()
    print("[INFO] Telegram interactive Admin listener started.")

    # Send Startup Admin Dashboard directly to Telegram
    txt, btn = get_admin_dashboard_markup()
    send_telegram_menu(txt, btn)

    try:
        while True:
            try:
                analyze_and_trade()
            except Exception as e:
                print(f"[ERROR] Cycle error: {e}")
            time.sleep(config.POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n[INFO] Bot stopped by user.")
    finally:
        mt5.shutdown()
        print("[INFO] MT5 connection closed.")

if __name__ == "__main__":
    main()
