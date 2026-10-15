import sys
sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
import config
from smc_engine import identify_swings, get_market_structure, detect_valid_order_blocks, OrderBlock

def run_backtest(symbol: str, count: int = 3000, rr: float = 3.0):
    """
    Backtest the SMC Price Action strategy on historical MT5 data.
    Computes Win Rate, Profit Factor, Total Return (in R), and trade details.
    """
    print(f"\n=======================================================")
    print(f" 📊 BACKTESTING: {symbol} (Last {count} 1H Candles)")
    print(f"=======================================================")
    
    rates = mt5.copy_rates_from_pos(symbol, config.HTF, 0, count)
    if rates is None or len(rates) < 100:
        print(f"[ERROR] Could not fetch data for {symbol}")
        return None

    df = pd.DataFrame(rates)
    df['time_dt'] = pd.to_datetime(df['time'], unit='s')

    trades = []
    active_ob: OrderBlock = None
    
    # We step through historical candles after initial warmup (e.g. 100 candles)
    warmup = 100
    for i in range(warmup, len(df) - 10):
        sub_df = df.iloc[:i]
        curr_candle = df.iloc[i]
        
        # 1. Swings & Structure
        swings = identify_swings(sub_df.iloc[:-1], swing_bars=config.SWING_BARS)
        trend, last_h, last_l = get_market_structure(sub_df.iloc[:-1], swings)
        
        if trend == "NEUTRAL":
            continue

        # 2. Valid OBs
        obs = detect_valid_order_blocks(sub_df, trend)
        target_type = "BEARISH" if trend == "BEARISH" else "BULLISH"
        valid_obs = [o for o in obs if o.ob_type == target_type and not o.is_failed]

        if not valid_obs:
            continue

        # 3. Check for OB Mitigation
        candidate_ob = valid_obs[-1]
        
        # Check if current candle taps candidate OB
        tapped = False
        if target_type == "BEARISH" and curr_candle['high'] >= candidate_ob.low and curr_candle['low'] <= candidate_ob.high:
            tapped = True
        elif target_type == "BULLISH" and curr_candle['low'] <= candidate_ob.high and curr_candle['high'] >= candidate_ob.low:
            tapped = True

        if tapped:
            # Check confirmation entry on next bar
            entry_candle = df.iloc[i + 1]
            if target_type == "BEARISH" and entry_candle['close'] < entry_candle['open']:
                # SELL Entry
                entry_p = entry_candle['close']
                sl_p = candidate_ob.high + (candidate_ob.high - candidate_ob.low) * 0.2
                risk = sl_p - entry_p
                if risk <= 0:
                    continue
                tp_p = entry_p - (risk * rr)
                
                # Forward-simulate trade outcome
                outcome = "OPEN"
                bars_held = 0
                for k in range(i + 2, min(i + 60, len(df))):
                    future_c = df.iloc[k]
                    bars_held += 1
                    # Check SL hit
                    if future_c['high'] >= sl_p:
                        outcome = "LOSS"
                        break
                    # Check TP hit
                    if future_c['low'] <= tp_p:
                        outcome = "WIN"
                        break

                trades.append({
                    "symbol": symbol,
                    "type": "SELL",
                    "time": str(entry_candle['time_dt']),
                    "entry": entry_p,
                    "sl": sl_p,
                    "tp": tp_p,
                    "outcome": outcome,
                    "rr": rr if outcome == "WIN" else (-1.0 if outcome == "LOSS" else 0.0),
                    "bars": bars_held
                })

            elif target_type == "BULLISH" and entry_candle['close'] > entry_candle['open']:
                # BUY Entry
                entry_p = entry_candle['close']
                sl_p = candidate_ob.low - (candidate_ob.high - candidate_ob.low) * 0.2
                risk = entry_p - sl_p
                if risk <= 0:
                    continue
                tp_p = entry_p + (risk * rr)
                
                # Forward-simulate trade outcome
                outcome = "OPEN"
                bars_held = 0
                for k in range(i + 2, min(i + 60, len(df))):
                    future_c = df.iloc[k]
                    bars_held += 1
                    # Check SL hit
                    if future_c['low'] <= sl_p:
                        outcome = "LOSS"
                        break
                    # Check TP hit
                    if future_c['high'] >= tp_p:
                        outcome = "WIN"
                        break

                trades.append({
                    "symbol": symbol,
                    "type": "BUY",
                    "time": str(entry_candle['time_dt']),
                    "entry": entry_p,
                    "sl": sl_p,
                    "tp": tp_p,
                    "outcome": outcome,
                    "rr": rr if outcome == "WIN" else (-1.0 if outcome == "LOSS" else 0.0),
                    "bars": bars_held
                })

    df_trades = pd.DataFrame(trades)
    if df_trades.empty:
        print("[INFO] No trades generated in sample period.")
        return None

    # Filter closed trades
    closed = df_trades[df_trades['outcome'].isin(['WIN', 'LOSS'])]
    total_trades = len(closed)
    wins = len(closed[closed['outcome'] == 'WIN'])
    losses = len(closed[closed['outcome'] == 'LOSS'])
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    total_r = closed['rr'].sum()
    profit_factor = (wins * rr) / losses if losses > 0 else float('inf')

    print(f"📈 Total Closed Trades: {total_trades}")
    print(f"🏆 Wins (Hit TP):       {wins}")
    print(f"🛑 Losses (Hit SL):     {losses}")
    print(f"🎯 Win Rate:            {win_rate:.1f}%")
    print(f"⚖️ Risk:Reward:         1:{rr}")
    print(f"💰 Total Profit (in R): +{total_r:.1f}R")
    print(f"📊 Profit Factor:       {profit_factor:.2f}")

    return {
        "symbol": symbol,
        "total": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_r": total_r,
        "profit_factor": profit_factor
    }

def main():
    if not mt5.initialize():
        print(f"[ERROR] MT5 Init failed: {mt5.last_error()}")
        return

    results = []
    for sym in config.SYMBOLS:
        res = run_backtest(sym, count=2000, rr=3.0)
        if res:
            results.append(res)

    print("\n=======================================================")
    print(" 📋 OVERALL SUMMARY TABLE across all pairs:")
    print("=======================================================")
    for r in results:
        print(f" {r['symbol']:<8} | Win Rate: {r['win_rate']:>5.1f}% | Wins: {r['wins']} | Losses: {r['losses']} | Net: +{r['total_r']:.1f}R | PF: {r['profit_factor']:.2f}")
    print("=======================================================\n")
    
    mt5.shutdown()

if __name__ == "__main__":
    main()
