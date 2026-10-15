import os
import json
import time
from datetime import datetime

TRADES_FILE = "trades.json"

def load_trades():
    if not os.path.exists(TRADES_FILE):
        return []
    try:
        with open(TRADES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_trades(trades):
    try:
        with open(TRADES_FILE, "w", encoding="utf-8") as f:
            json.dump(trades, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ERROR] Failed to save trades: {e}")

def record_trade_entry(ticket: int, symbol: str, trade_type: str, lot: float, entry: float, sl: float, tp: float):
    trades = load_trades()
    trade = {
        "ticket": ticket,
        "symbol": symbol,
        "type": trade_type,
        "lot": lot,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "open_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "OPEN",
        "close_time": None,
        "exit_price": None,
        "pnl": 0.0,
        "result": None
    }
    trades.append(trade)
    save_trades(trades)

def record_trade_exit(ticket: int, exit_price: float, pnl: float):
    trades = load_trades()
    for t in trades:
        if t["ticket"] == ticket and t["status"] == "OPEN":
            t["status"] = "CLOSED"
            t["close_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            t["exit_price"] = exit_price
            t["pnl"] = round(pnl, 2)
            t["result"] = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BE")
            break
    save_trades(trades)

def get_performance_summary():
    trades = load_trades()
    closed = [t for t in trades if t["status"] == "CLOSED"]
    
    total = len(closed)
    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] < 0]
    
    total_win_amt = sum(t["pnl"] for t in wins)
    total_loss_amt = abs(sum(t["pnl"] for t in losses))
    net_profit = sum(t["pnl"] for t in closed)
    
    win_rate = (len(wins) / total * 100) if total > 0 else 0.0
    profit_factor = (total_win_amt / total_loss_amt) if total_loss_amt > 0 else (99.0 if total_win_amt > 0 else 0.0)

    recent = closed[-5:] if len(closed) >= 5 else closed
    recent.reverse()

    return {
        "total": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "net_profit": net_profit,
        "profit_factor": profit_factor,
        "recent_trades": recent
    }
