import sys
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
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

class EngineState:
    def __init__(self, name: str, magic: int):
        self.name = name
        self.magic = magic
        self.in_position = False
        self.ticket = None
        self.position_type = None
        self.last_candle_time = None

class AssetHybridState:
    def __init__(self, symbol: str, default_lot: float = 0.01):
        self.symbol = symbol
        self.current_trend = "NEUTRAL"
        self.fixed_lot = default_lot
        self.runner = EngineState("RUNNER", config.ASSET_CONFIG[symbol]["runner_magic"])
        self.sniper = EngineState("SNIPER", config.ASSET_CONFIG[symbol]["sniper_magic"])

class MultiBotState:
    def __init__(self):
        self.symbols = {
            s: AssetHybridState(s, config.ASSET_CONFIG[s]["default_lot"])
            for s in config.SYMBOLS
        }
        self.risk_mode = "PERCENT"  # "PERCENT" or "FIXED"
        self.risk_percent = 1.0     # 1.0%, 2.0%, 3.0%, 5.0%
        self.auto_trade_enabled = True
        self.last_log_time = 0

state = MultiBotState()

def calculate_order_lot(symbol: str, sl_distance: float) -> float:
    """Calculate lot size based on dynamic risk % and asset contract size."""
    sym_state = state.symbols[symbol]
    sym_cfg = config.ASSET_CONFIG[symbol]
    
    sym_info = mt5.symbol_info(symbol)
    vol_min = sym_info.volume_min if sym_info else sym_cfg["default_lot"]
    vol_max = sym_info.volume_max if sym_info else 100.0
    vol_step = sym_info.volume_step if sym_info else 0.01
    contract_size = sym_info.trade_contract_size if sym_info else 1.0

    if state.risk_mode == "FIXED":
        return max(vol_min, sym_state.fixed_lot)

    acc = mt5.account_info()
    equity = acc.equity if acc else 500.0
    risk_dollars = equity * (state.risk_percent / 100.0)

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

def check_open_position(symbol: str, magic: int):
    """Check if there is an active trade for this symbol and magic number."""
    positions = mt5.positions_get(symbol=symbol)
    if positions:
        for p in positions:
            if p.magic == magic:
                return p
    return None

def close_position_market(ticket: int):
    """Close an active position at market price (used for AI Sniper fast EMA exit)."""
    positions = mt5.positions_get()
    if not positions:
        return None
    pos = None
    for p in positions:
        if p.ticket == ticket:
            pos = p
            break
    if not pos:
        return None

    sym_info = mt5.symbol_info(pos.symbol)
    if not sym_info:
        return None

    filling = get_filling_mode(sym_info)
    order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(pos.symbol)
    if not tick:
        return None

    price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": pos.ticket,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": order_type,
        "price": price,
        "deviation": 25,
        "magic": pos.magic,
        "comment": f"Sniper_Exit_{pos.symbol}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling
    }
    res = mt5.order_send(req)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[EXIT SUCCESS] Closed position #{ticket} for {pos.symbol} at {price}")
    else:
        err = res.comment if res else mt5.last_error()
        print(f"[EXIT ERROR] Failed to close #{ticket}: {err}")
    return res

def open_market_trade(symbol: str, engine: str, trade_type: str, lot: float, sl: float, tp: float):
    """Execute Market Order on MT5 for the designated engine."""
    sym_cfg = config.ASSET_CONFIG[symbol]
    magic = sym_cfg["runner_magic"] if engine == "RUNNER" else sym_cfg["sniper_magic"]

    sym_info = mt5.symbol_info(symbol)
    if not sym_info:
        print(f"[ERROR] Symbol {symbol} info not found")
        return None

    if not sym_info.visible:
        mt5.symbol_select(symbol, True)

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print(f"[ERROR] Could not get tick for {symbol}")
        return None

    order_type = mt5.ORDER_TYPE_BUY if trade_type == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if trade_type == "BUY" else tick.bid
    filling = get_filling_mode(sym_info)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 25,
        "magic": magic,
        "comment": f"Hybrid_{engine}_{symbol}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    if not state.auto_trade_enabled:
        print(f"[ALERT ONLY] [{engine}] Simulated {trade_type} {lot} {symbol} @ {price}")
        return None

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[SUCCESS] [{engine}] Order opened #{result.order}: {trade_type} {lot} {symbol} @ {price}")
        record_trade_entry(result.order, symbol, trade_type, lot, price, sl, tp, engine=engine)
        return result
    else:
        err = result.comment if result else mt5.last_error()
        print(f"[FAILED] [{engine}] Order failed for {symbol}: {err}")
        return None

def compute_indicators(rates):
    """Compute all quantitative technical indicators for 1H rates."""
    df = pd.DataFrame(rates)
    df['time_dt'] = pd.to_datetime(df['time'], unit='s')

    # EMAs
    df['ema5'] = df['close'].ewm(span=config.EMA_FAST).mean()
    df['ema20'] = df['close'].ewm(span=config.EMA_MID1).mean()
    df['ema50'] = df['close'].ewm(span=config.EMA_MID2).mean()
    df['ema200'] = df['close'].ewm(span=config.EMA_MACRO).mean()

    # RSI-2 (Larry Connors Fast Momentum)
    delta = df['close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=config.RSI_PERIOD - 1, adjust=False).mean()
    ema_down = down.ewm(com=config.RSI_PERIOD - 1, adjust=False).mean()
    rs = ema_up / ema_down
    df['rsi2'] = 100 - (100 / (1 + rs))

    # ATR
    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift()).abs()
    lc = (df['low'] - df['close'].shift()).abs()
    df['atr'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(config.ATR_PERIOD).mean().bfill()

    return df

def monitor_positions():
    """Monitor position status, manage Sniper exits, and log completed trades."""
    for symbol in config.SYMBOLS:
        sym_state = state.symbols[symbol]
        sym_cfg = config.ASSET_CONFIG[symbol]

        # Check Runner and Sniper positions separately
        for eng_obj in [sym_state.runner, sym_state.sniper]:
            pos = check_open_position(symbol, eng_obj.magic)

            if pos:
                eng_obj.in_position = True
                eng_obj.ticket = pos.ticket
                eng_obj.position_type = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
            else:
                if eng_obj.in_position and eng_obj.ticket:
                    # Trade closed! Fetch deal history
                    ticket = eng_obj.ticket
                    deals = mt5.history_deals_get(position=ticket)
                    exit_price = 0.0
                    profit = 0.0
                    if deals:
                        for d in deals:
                            if d.entry == mt5.DEAL_ENTRY_OUT:
                                exit_price = d.price
                                profit += d.profit + d.swap + d.commission

                    record_trade_exit(ticket, exit_price, profit)
                    eng_obj.in_position = False
                    eng_obj.ticket = None

                    res_icon = "🟢 WIN" if profit > 0 else "🔴 LOSS"
                    engine_tag = "🎯 [AI SNIPER]" if eng_obj.name == "SNIPER" else "🚀 [AI RUNNER]"
                    send_telegram_message(
                        f"{res_icon} <b>{engine_tag} TRADE CLOSED!</b>\n\n"
                        f"🎫 <b>Ticket:</b> <code>#{ticket}</code>\n"
                        f"📊 <b>Symbol:</b> <code>{symbol} ({sym_cfg['name']})</code>\n"
                        f"💰 <b>Realized PnL:</b> <b>{profit:+.2f} USD</b>\n"
                        f"📍 <b>Exit Price:</b> <code>{exit_price:.3f}</code>"
                    )

def scan_runner_engine(symbol: str, df: pd.DataFrame):
    """Engine 1: Institutional Trend Runner (1:2 R:R Pullback Strategy)."""
    sym_cfg = config.ASSET_CONFIG[symbol]
    if not sym_cfg.get("enable_runner", False):
        return

    sym_state = state.symbols[symbol]
    eng = sym_state.runner

    if check_open_position(symbol, eng.magic):
        return

    closed_candle = df.iloc[-2]
    prior_candle = df.iloc[-3]
    latest_candle = df.iloc[-1]

    if eng.last_candle_time == closed_candle['time']:
        return

    candle_hour = closed_candle['time_dt'].hour
    is_active_session = (sym_cfg["session_start_utc"] <= candle_hour <= sym_cfg["session_end_utc"])
    if not is_active_session:
        return

    atr = closed_candle['atr']
    sl_buf = sym_cfg["sl_buffer_atr"]
    min_r = sym_cfg["min_risk"]
    max_r = sym_cfg["max_risk"]
    rr = sym_cfg["rr_ratio"]

    # BULLISH SETUP (BUY)
    if sym_state.current_trend == "BULLISH (UPTREND)":
        if prior_candle['low'] <= prior_candle['ema20'] and closed_candle['close'] > prior_candle['high'] and closed_candle['close'] > closed_candle['open']:
            entry_p = latest_candle['open']
            sl_p = prior_candle['low'] - (atr * sl_buf)
            risk = entry_p - sl_p
            if min_r <= risk <= max_r:
                tp_p = entry_p + (risk * rr)
                eng.last_candle_time = closed_candle['time']
                order_lot = calculate_order_lot(symbol, risk)

                print(f"[RUNNER TRIGGER] BUY on {symbol}! Entry: {entry_p}, SL: {sl_p}, TP: {tp_p}, Lot: {order_lot}")
                res = open_market_trade(symbol, "RUNNER", "BUY", order_lot, sl_p, tp_p)
                ticket_str = str(res.order) if res else ("Alert Mode" if not state.auto_trade_enabled else "Simulation")

                chart_file = f"chart_{symbol.lower()}_runner.png"
                chart_path = generate_candlestick_chart(df, symbol, sym_cfg["timeframe_name"], sl=sl_p, tp=tp_p, output_path=chart_file)
                caption = (
                    f"🚀 <b>[AI RUNNER - 1:2 R:R] {sym_cfg['icon']} {symbol} BUY TRIGGERED!</b>\n\n"
                    f"🎫 <b>Ticket:</b> <code>{ticket_str}</code>\n"
                    f"📊 <b>Asset:</b> <code>{sym_cfg['name']} ({symbol})</code>\n"
                    f"📦 <b>Lot Size:</b> <code>{order_lot}</code>\n"
                    f"📍 <b>Entry:</b> <code>{entry_p:.3f}</code>\n"
                    f"🛑 <b>Stop Loss:</b> <code>{sl_p:.3f}</code>\n"
                    f"🎯 <b>Take Profit (1:{rr}):</b> <code>{tp_p:.3f}</code>\n"
                    f"💼 <b>Balance:</b> <code>{mt5.account_info().balance:.2f} USD</code>\n\n"
                    f"<i>🎯 Engine: Institutional Trend Runner (Targeting Maximum R-Multiple)</i>"
                )
                if chart_path:
                    send_telegram_photo(chart_path, caption=caption)
                else:
                    send_telegram_message(caption)

                if res:
                    eng.in_position = True
                    eng.ticket = res.order

    # BEARISH SETUP (SELL)
    elif sym_state.current_trend == "BEARISH (DOWNTREND)":
        if prior_candle['high'] >= prior_candle['ema20'] and closed_candle['close'] < prior_candle['low'] and closed_candle['close'] < closed_candle['open']:
            entry_p = latest_candle['open']
            sl_p = prior_candle['high'] + (atr * sl_buf)
            risk = sl_p - entry_p
            if min_r <= risk <= max_r:
                tp_p = entry_p - (risk * rr)
                eng.last_candle_time = closed_candle['time']
                order_lot = calculate_order_lot(symbol, risk)

                print(f"[RUNNER TRIGGER] SELL on {symbol}! Entry: {entry_p}, SL: {sl_p}, TP: {tp_p}, Lot: {order_lot}")
                res = open_market_trade(symbol, "RUNNER", "SELL", order_lot, sl_p, tp_p)
                ticket_str = str(res.order) if res else ("Alert Mode" if not state.auto_trade_enabled else "Simulation")

                chart_file = f"chart_{symbol.lower()}_runner.png"
                chart_path = generate_candlestick_chart(df, symbol, sym_cfg["timeframe_name"], sl=sl_p, tp=tp_p, output_path=chart_file)
                caption = (
                    f"🔻 <b>[AI RUNNER - 1:2 R:R] {sym_cfg['icon']} {symbol} SELL TRIGGERED!</b>\n\n"
                    f"🎫 <b>Ticket:</b> <code>{ticket_str}</code>\n"
                    f"📊 <b>Asset:</b> <code>{sym_cfg['name']} ({symbol})</code>\n"
                    f"📦 <b>Lot Size:</b> <code>{order_lot}</code>\n"
                    f"📍 <b>Entry:</b> <code>{entry_p:.3f}</code>\n"
                    f"🛑 <b>Stop Loss:</b> <code>{sl_p:.3f}</code>\n"
                    f"🎯 <b>Take Profit (1:{rr}):</b> <code>{tp_p:.3f}</code>\n"
                    f"💼 <b>Balance:</b> <code>{mt5.account_info().balance:.2f} USD</code>\n\n"
                    f"<i>🎯 Engine: Institutional Trend Runner (Targeting Maximum R-Multiple)</i>"
                )
                if chart_path:
                    send_telegram_photo(chart_path, caption=caption)
                else:
                    send_telegram_message(caption)

                if res:
                    eng.in_position = True
                    eng.ticket = res.order

def scan_sniper_engine(symbol: str, df: pd.DataFrame):
    """Engine 2: AI Sniper Mean Reversion (80% - 86% Win Rate Larry Connors Model)."""
    sym_cfg = config.ASSET_CONFIG[symbol]
    if not sym_cfg.get("enable_sniper", False):
        return

    sym_state = state.symbols[symbol]
    eng = sym_state.sniper

    pos = check_open_position(symbol, eng.magic)
    closed_candle = df.iloc[-2]
    latest_candle = df.iloc[-1]

    # Active Position Management: Check for Fast 5-EMA Mean Reversion Exit
    if pos:
        if pos.type == mt5.ORDER_TYPE_BUY and closed_candle['close'] >= closed_candle['ema5']:
            print(f"[SNIPER EXIT] {symbol} BUY reached EMA(5) mean! Securing profit...")
            close_position_market(pos.ticket)
            return
        elif pos.type == mt5.ORDER_TYPE_SELL and closed_candle['close'] <= closed_candle['ema5']:
            print(f"[SNIPER EXIT] {symbol} SELL reached EMA(5) mean! Securing profit...")
            close_position_market(pos.ticket)
            return
        return

    if eng.last_candle_time == closed_candle['time']:
        return

    atr = closed_candle['atr']
    sl_mult = sym_cfg.get("sniper_sl_atr", 2.5)
    rsi_buy = sym_cfg.get("sniper_rsi_buy", 10)
    rsi_sell = sym_cfg.get("sniper_rsi_sell", 90)

    # BUY SETUP: Macro Uptrend (Price > EMA200) + Deep Oversold Pullback (RSI2 <= 10)
    if closed_candle['close'] > closed_candle['ema200'] and closed_candle['rsi2'] <= rsi_buy:
        entry_p = latest_candle['open']
        sl_p = entry_p - (atr * sl_mult)
        tp_p = entry_p + (atr * 1.5)  # Safety ceiling target
        risk = entry_p - sl_p
        eng.last_candle_time = closed_candle['time']
        order_lot = calculate_order_lot(symbol, risk)

        print(f"[SNIPER TRIGGER] BUY on {symbol}! RSI(2)={closed_candle['rsi2']:.1f}, Entry: {entry_p}, SL: {sl_p}")
        res = open_market_trade(symbol, "SNIPER", "BUY", order_lot, sl_p, tp_p)
        ticket_str = str(res.order) if res else ("Alert Mode" if not state.auto_trade_enabled else "Simulation")

        chart_file = f"chart_{symbol.lower()}_sniper.png"
        chart_path = generate_candlestick_chart(df, symbol, sym_cfg["timeframe_name"], sl=sl_p, tp=tp_p, output_path=chart_file)
        caption = (
            f"🎯 <b>[AI SNIPER - 85% WIN RATE] {sym_cfg['icon']} {symbol} BUY TRIGGERED!</b>\n\n"
            f"🎫 <b>Ticket:</b> <code>{ticket_str}</code>\n"
            f"📊 <b>Asset:</b> <code>{sym_cfg['name']} ({symbol})</code>\n"
            f"⚡ <b>RSI(2):</b> <code>{closed_candle['rsi2']:.1f} (Extremely Oversold)</code>\n"
            f"📦 <b>Lot Size:</b> <code>{order_lot}</code>\n"
            f"📍 <b>Entry:</b> <code>{entry_p:.3f}</code>\n"
            f"🛑 <b>Stop Loss:</b> <code>{sl_p:.3f}</code>\n"
            f"🎯 <b>Target:</b> <code>EMA(5) Fast Mean Reversion</code>\n"
            f"💼 <b>Balance:</b> <code>{mt5.account_info().balance:.2f} USD</code>\n\n"
            f"<i>🎯 Engine: AI Mean Reversion (Mathematical High Probability Sniper)</i>"
        )
        if chart_path:
            send_telegram_photo(chart_path, caption=caption)
        else:
            send_telegram_message(caption)

        if res:
            eng.in_position = True
            eng.ticket = res.order

    # SELL SETUP: Macro Downtrend (Price < EMA200) + Deep Overbought Pullback (RSI2 >= 90)
    elif closed_candle['close'] < closed_candle['ema200'] and closed_candle['rsi2'] >= rsi_sell:
        entry_p = latest_candle['open']
        sl_p = entry_p + (atr * sl_mult)
        tp_p = entry_p - (atr * 1.5)  # Safety ceiling target
        risk = sl_p - entry_p
        eng.last_candle_time = closed_candle['time']
        order_lot = calculate_order_lot(symbol, risk)

        print(f"[SNIPER TRIGGER] SELL on {symbol}! RSI(2)={closed_candle['rsi2']:.1f}, Entry: {entry_p}, SL: {sl_p}")
        res = open_market_trade(symbol, "SNIPER", "SELL", order_lot, sl_p, tp_p)
        ticket_str = str(res.order) if res else ("Alert Mode" if not state.auto_trade_enabled else "Simulation")

        chart_file = f"chart_{symbol.lower()}_sniper.png"
        chart_path = generate_candlestick_chart(df, symbol, sym_cfg["timeframe_name"], sl=sl_p, tp=tp_p, output_path=chart_file)
        caption = (
            f"🎯 <b>[AI SNIPER - 85% WIN RATE] {sym_cfg['icon']} {symbol} SELL TRIGGERED!</b>\n\n"
            f"🎫 <b>Ticket:</b> <code>{ticket_str}</code>\n"
            f"📊 <b>Asset:</b> <code>{sym_cfg['name']} ({symbol})</code>\n"
            f"⚡ <b>RSI(2):</b> <code>{closed_candle['rsi2']:.1f} (Extremely Overbought)</code>\n"
            f"📦 <b>Lot Size:</b> <code>{order_lot}</code>\n"
            f"📍 <b>Entry:</b> <code>{entry_p:.3f}</code>\n"
            f"🛑 <b>Stop Loss:</b> <code>{sl_p:.3f}</code>\n"
            f"🎯 <b>Target:</b> <code>EMA(5) Fast Mean Reversion</code>\n"
            f"💼 <b>Balance:</b> <code>{mt5.account_info().balance:.2f} USD</code>\n\n"
            f"<i>🎯 Engine: AI Mean Reversion (Mathematical High Probability Sniper)</i>"
        )
        if chart_path:
            send_telegram_photo(chart_path, caption=caption)
        else:
            send_telegram_message(caption)

        if res:
            eng.in_position = True
            eng.ticket = res.order

def scan_symbol(symbol: str):
    """Scan both Hybrid Engines for a single asset."""
    sym_state = state.symbols[symbol]
    sym_cfg = config.ASSET_CONFIG[symbol]

    rates = mt5.copy_rates_from_pos(symbol, sym_cfg["timeframe"], 0, 250)
    if rates is None or len(rates) < 200:
        return

    df = compute_indicators(rates)
    closed_candle = df.iloc[-2]

    # Update Macro Trend classification
    if closed_candle['ema20'] > closed_candle['ema50'] and closed_candle['ema50'] > closed_candle['ema200']:
        sym_state.current_trend = "BULLISH (UPTREND)"
    elif closed_candle['ema20'] < closed_candle['ema50'] and closed_candle['ema50'] < closed_candle['ema200']:
        sym_state.current_trend = "BEARISH (DOWNTREND)"
    else:
        sym_state.current_trend = "RANGING / CHOP"

    # 1. Run Institutional Trend Runner Engine
    scan_runner_engine(symbol, df)

    # 2. Run AI Sniper Mean Reversion Engine
    scan_sniper_engine(symbol, df)

def analyze_and_trade():
    """Main scanning cycle across all configured assets."""
    monitor_positions()
    for symbol in config.SYMBOLS:
        try:
            scan_symbol(symbol)
        except Exception as e:
            print(f"[ERROR] Scan error for {symbol}: {e}")

    # Periodic heartbeat log (every 60 seconds)
    now = time.time()
    if now - state.last_log_time >= 60:
        state.last_log_time = now
        acc = mt5.account_info()
        eq_val = acc.equity if acc else 0.0
        log_parts = []
        for s in config.SYMBOLS:
            tick = mt5.symbol_info_tick(s)
            p = tick.bid if tick else 0.0
            r_pos = "R:OPEN" if state.symbols[s].runner.in_position else "R:IDLE"
            s_pos = "S:OPEN" if state.symbols[s].sniper.in_position else "S:IDLE"
            log_parts.append(f"{s}:{p:.2f} ({r_pos}|{s_pos})")
        print(f"[HYBRID SCAN {datetime.now().strftime('%H:%M:%S')}] {' | '.join(log_parts)} | Eq: {eq_val:.2f}$")

# --- TELEGRAM ADMIN DASHBOARD HANDLERS ---

def get_admin_dashboard_markup():
    """Build the Hybrid AI Multi-Asset Admin Dashboard."""
    acc = mt5.account_info()
    bal_str = f"{acc.balance:.2f} USD" if acc else "N/A"
    eq_str = f"{acc.equity:.2f} USD" if acc else "N/A"
    trade_status = "🟢 Active (Auto-Trade)" if state.auto_trade_enabled else "⏸️ Paused (Alerts Only)"
    risk_disp = f"Dynamic {state.risk_percent}%" if state.risk_mode == "PERCENT" else "Fixed Lots"

    lines = [
        "👑 <b>HYBRID AI MULTI-ASSET TRADING BOT</b>",
        "<i>(Dual Engine: AI Sniper 85% WR + Trend Runner 1:2 R:R)</i>\n",
        "<b>📊 የቀጥታ ገበያ እና የኢንጂኖች ሁኔታ (Live Status)፦</b>"
    ]

    for s in config.SYMBOLS:
        cfg = config.ASSET_CONFIG[s]
        tick = mt5.symbol_info_tick(s)
        p = tick.bid if tick else 0.0

        r_pos = check_open_position(s, cfg["runner_magic"])
        s_pos = check_open_position(s, cfg["sniper_magic"])

        r_str = f"<b>{r_pos.volume} lot ({r_pos.profit:+.2f}$)</b>" if r_pos else ("<i>Off</i>" if not cfg["enable_runner"] else "<i>Idle</i>")
        s_str = f"<b>{s_pos.volume} lot ({s_pos.profit:+.2f}$)</b>" if s_pos else "<i>Idle</i>"

        lines.append(
            f"{cfg['icon']} <b>{cfg['name']} ({s})፦</b>\n"
            f"   • Price: <code>{p:.2f}</code> | Trend: <b>{state.symbols[s].current_trend}</b>\n"
            f"   • 🚀 Runner (1:2 R:R): {r_str}\n"
            f"   • 🎯 Sniper (85% WR): {s_str}"
        )

    lines.append(
        f"\n🛡 <b>Risk Setting:</b> <code>{risk_disp}</code>\n"
        f"⚡ <b>Auto-Trading:</b> {trade_status}\n"
        f"💼 <b>Balance:</b> <code>{bal_str}</code> | 💎 <b>Equity:</b> <code>{eq_str}</code>\n\n"
        f"<i>ከዚህ በታች ያሉትን ቁልፎች በመጫን ቦቱን መቆጣጠር ይችላሉ፦</i>"
    )

    text = "\n".join(lines)
    buttons = [
        [
            {"text": "📊 Win/Loss & Engine Report", "callback_data": "menu_trades"},
            {"text": "⚙️ Set Risk % / Lot", "callback_data": "menu_risk"}
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
    """Build performance statistics page with Engine & Symbol breakdown."""
    summary = get_performance_summary()
    tot = summary["total"]
    w = summary["wins"]
    l = summary["losses"]
    wr = summary["win_rate"]
    pnl = summary["net_profit"]
    pf = summary["profit_factor"]

    eb = summary.get("engine_breakdown", {})
    sn_tot = eb.get("SNIPER", {}).get("total", 0)
    sn_wr = eb.get("SNIPER", {}).get("win_rate", 0.0)
    sn_pnl = eb.get("SNIPER", {}).get("pnl", 0.0)

    rn_tot = eb.get("RUNNER", {}).get("total", 0)
    rn_wr = eb.get("RUNNER", {}).get("win_rate", 0.0)
    rn_pnl = eb.get("RUNNER", {}).get("pnl", 0.0)

    lines = [
        "📊 <b>HYBRID BOT PERFORMANCE & WIN/LOSS REPORT</b>\n",
        f"📈 <b>Total Closed:</b> <b>{tot}</b> | 🏆 <b>Wins:</b> <b>{w}</b> | 🛑 <b>Losses:</b> <b>{l}</b>",
        f"🎯 <b>Overall Win Rate:</b> <b>{wr:.1f}%</b> | 💰 <b>Net PnL:</b> <b>{pnl:+.2f} USD</b> | ⚖️ <b>PF:</b> <b>{pf:.2f}</b>\n",
        "<b>⚙️ የሁለቱ ኢንጂኖች ውጤት (Engine Breakdown)፦</b>",
        f"• 🎯 <b>AI Sniper (Mean Reversion):</b> {sn_tot} trades | WR: <b>{sn_wr:.1f}%</b> | PnL: <b>{sn_pnl:+.2f}$</b>",
        f"• 🚀 <b>Trend Runner (1:2 R:R):</b> {rn_tot} trades | WR: <b>{rn_wr:.1f}%</b> | PnL: <b>{rn_pnl:+.2f}$</b>\n",
        "<b>📦 በአሴት የተከፋፈለ ውጤት (By Asset)፦</b>"
    ]

    for s in config.SYMBOLS:
        cfg = config.ASSET_CONFIG[s]
        sb = summary["sym_breakdown"].get(s, {})
        s_tot = sb.get("total", 0)
        s_wr = sb.get("win_rate", 0.0)
        s_pnl = sb.get("pnl", 0.0)
        lines.append(f"• {cfg['icon']} <b>{s} ({cfg['name']}):</b> {s_tot} trades | WR: <b>{s_wr:.1f}%</b> | PnL: <b>{s_pnl:+.2f}$</b>")

    lines.append("\n<b>📋 የመጨረሻዎቹ 5 ትሬዶች፦</b>")
    if not summary["recent_trades"]:
        lines.append("<i>ገና የተዘጋ ትሬድ የለም። ትሬዶች ሲዘጉ እዚህ በዝርዝር ይታያሉ!</i>")
    else:
        for t in summary["recent_trades"]:
            icon = "🟢 WIN" if t["pnl"] >= 0 else "🔴 LOSS"
            eng_label = "🎯" if t.get("engine") == "SNIPER" else "🚀"
            lines.append(f"• #{t['ticket']} | {eng_label} {t['symbol']} {t['type']} {t['lot']} | {icon} <b>{t['pnl']:+.2f}$</b>")

    buttons = [
        [{"text": "🔙 Back to Admin Menu", "callback_data": "menu_main"}]
    ]
    return "\n".join(lines), buttons

def get_risk_markup():
    """Build the risk level setting page."""
    acc = mt5.account_info()
    eq = acc.equity if acc else 500.0

    if state.risk_mode == "PERCENT":
        current_setting = f"<b>Dynamic {state.risk_percent}% Risk</b> per trade"
        risk_cash = eq * (state.risk_percent / 100.0)
        detail = (
            f"• አሁን ባለው Equity (${eq:.2f})፦ <b>~${risk_cash:.2f} USD</b> ስጋት በየአሴቱ\n"
            f"• ቦቱ ለእያንዳንዱ አሴት ኮንትራት መጠን ራሱ አስልቶ ሎት ይከፍታል"
        )
    else:
        current_setting = "<b>Fixed Lot Mode</b>"
        detail = "• ለእያንዳንዱ አሴት በቋሚ ዝቅተኛ ሎት (0.01 / 0.05) ይከፍታል"

    text = (
        f"⚙️ <b>SET RISK LEVEL & POSITION SIZING</b>\n\n"
        f"📊 <b>የአሁኑ አቀማመጥ፦</b> {current_setting}\n"
        f"{detail}\n\n"
        f"<b>🎯 በአካውንት ፐርሰንት (Dynamic Risk %)፦</b>\n"
        f"<i>(አካውንትዎ ሲያድግ የሎት መጠኑ በራሱ አብሮ ያድጋል)</i>\n"
        f"• <b>1% Risk</b>: በጣም ደህንነቱ የተጠበቀ (Recommended)\n"
        f"• <b>2% Risk</b>: መደበኛ እና የተመጣጠነ እድገት\n"
        f"• <b>3% Risk</b>: ፈጣን እድገት\n"
        f"• <b>5% Risk</b>: ከፍተኛ እድገት\n"
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
            {"text": "✅ Fixed Lots" if state.risk_mode == "FIXED" else "Fixed Lots", "callback_data": "set_fixed_mode"},
            {"text": "🔙 Back to Menu", "callback_data": "menu_main"}
        ]
    ]
    return text, buttons

def get_account_markup():
    """Build account details page."""
    acc = mt5.account_info()
    if not acc:
        text = "⚠️ <b>MT5 Account info is currently unavailable. Please try again in a few moments.</b>"
    else:
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
    try:
        initial_updates = get_telegram_updates()
        if initial_updates:
            last_id = initial_updates[-1].get("update_id", 0)
    except Exception:
        pass

    while True:
        try:
            updates = get_telegram_updates(offset=last_id + 1)
            for upd in updates:
                last_id = upd.get("update_id", last_id)

                # 1. Handle Inline Button Clicks
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

                    elif data == "set_fixed_mode":
                        state.risk_mode = "FIXED"
                        txt, btn = get_risk_markup()
                        edit_telegram_message(msg_id, txt, btn)
                        answer_callback_query(cq_id, "Switched to Fixed Lots mode!")

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

                    if text in ["/admin", "/menu", "admin", "menu", "/start", "/status", "status"]:
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

        except Exception as e:
            print(f"[ERROR] Telegram handler error: {e}")
        time.sleep(2)

def main():
    print("==============================================================")
    print(" 🚀 HYBRID AI MULTI-ASSET BOT (XAUUSD, USTEC, BTCUSD)")
    print("    • Engine 1: Institutional Trend Runner (1:2 R:R)")
    print("    • Engine 2: AI Sniper Mean Reversion (85% Win Rate)")
    print("==============================================================")

    init_kwargs = {}
    if config.MT5_PATH:
        init_kwargs["path"] = config.MT5_PATH
        init_kwargs["portable"] = True
        init_kwargs["timeout"] = 60000
    if config.MT5_LOGIN and config.MT5_PASSWORD and config.MT5_SERVER:
        init_kwargs["login"] = config.MT5_LOGIN
        init_kwargs["password"] = config.MT5_PASSWORD
        init_kwargs["server"] = config.MT5_SERVER

    init_success = mt5.initialize(**init_kwargs) if init_kwargs else mt5.initialize()

    if not init_success:
        print(f"[FATAL] MT5 initialization failed: {mt5.last_error()}")
        return

    term = mt5.terminal_info()
    acc = mt5.account_info()
    print(f"[INFO] Connected to MT5 Account: {acc.login} ({acc.server})")
    print(f"[INFO] Balance: {acc.balance} USD | Equity: {acc.equity} USD")
    print(f"[INFO] Terminal Trade Allowed (Algo Trading): {term.trade_allowed}")

    # Add all symbols to Market Watch
    for sym in config.SYMBOLS:
        if not mt5.symbol_select(sym, True):
            print(f"[WARNING] Could not select {sym} in Market Watch: {mt5.last_error()}")
        else:
            print(f"[INFO] Successfully selected {sym} in Market Watch.")

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
