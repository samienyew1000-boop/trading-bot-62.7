import sys
sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from smc_engine import identify_swings, get_market_structure, detect_valid_order_blocks

def test_gold_smc_with_be(count=4000, target_rr=2.0, be_trigger=1.0):
    mt5.initialize()
    rates = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_H1, 0, count)
    mt5.shutdown()
    
    if rates is None:
        return
        
    df = pd.DataFrame(rates)
    trades = []
    
    for i in range(100, len(df) - 30):
        sub_df = df.iloc[:i]
        curr = df.iloc[i]
        
        swings = identify_swings(sub_df.iloc[:-1], swing_bars=3)
        trend, last_h, last_l = get_market_structure(sub_df.iloc[:-1], swings)
        
        if trend == "NEUTRAL":
            continue
            
        obs = detect_valid_order_blocks(sub_df, trend)
        target_type = "BEARISH" if trend == "BEARISH" else "BULLISH"
        valid_obs = [o for o in obs if o.ob_type == target_type and not o.is_failed]
        
        if not valid_obs:
            continue
            
        candidate_ob = valid_obs[-1]
        tapped = False
        if target_type == "BEARISH" and curr['high'] >= candidate_ob.low and curr['low'] <= candidate_ob.high:
            tapped = True
        elif target_type == "BULLISH" and curr['low'] <= candidate_ob.high and curr['high'] >= candidate_ob.low:
            tapped = True
            
        if tapped:
            entry_c = df.iloc[i + 1]
            if target_type == "BULLISH" and entry_c['close'] > entry_c['open']:
                entry = entry_c['close']
                sl = candidate_ob.low - (candidate_ob.high - candidate_ob.low) * 0.2
                risk = entry - sl
                if risk <= 1.0 or risk > 30.0:
                    continue
                be_price = entry + (risk * be_trigger)
                tp = entry + (risk * target_rr)
                
                outcome = "TIMEOUT"
                hit_be = False
                for k in range(i + 2, min(i + 60, len(df))):
                    fc = df.iloc[k]
                    # Check BE trigger
                    if fc['high'] >= be_price:
                        hit_be = True
                        sl = entry  # Move SL to breakeven
                    # Check SL
                    if fc['low'] <= sl:
                        outcome = "BE" if hit_be else "LOSS"
                        break
                    # Check TP
                    if fc['high'] >= tp:
                        outcome = "WIN"
                        break
                trades.append({"type": "BUY", "outcome": outcome})

            elif target_type == "BEARISH" and entry_c['close'] < entry_c['open']:
                entry = entry_c['close']
                sl = candidate_ob.high + (candidate_ob.high - candidate_ob.low) * 0.2
                risk = sl - entry
                if risk <= 1.0 or risk > 30.0:
                    continue
                be_price = entry - (risk * be_trigger)
                tp = entry - (risk * target_rr)
                
                outcome = "TIMEOUT"
                hit_be = False
                for k in range(i + 2, min(i + 60, len(df))):
                    fc = df.iloc[k]
                    if fc['low'] <= be_price:
                        hit_be = True
                        sl = entry
                    if fc['high'] >= sl:
                        outcome = "BE" if hit_be else "LOSS"
                        break
                    if fc['low'] <= tp:
                        outcome = "WIN"
                        break
                trades.append({"type": "SELL", "outcome": outcome})

    df_t = pd.DataFrame(trades)
    wins = len(df_t[df_t['outcome'] == 'WIN'])
    losses = len(df_t[df_t['outcome'] == 'LOSS'])
    bes = len(df_t[df_t['outcome'] == 'BE'])
    total = wins + losses + bes
    net_r = (wins * target_rr) - losses
    print("==================================================================")
    print(f" 🏆 GOLD SMC + 1R BREAKEVEN MANAGEMENT (TP: 1:{target_rr} RR)")
    print("==================================================================")
    print(f" Total Trades:    {total}")
    print(f" Wins (Hit TP):   {wins}")
    print(f" Losses (Hit SL): {losses}")
    print(f" Breakeven (0$):  {bes} trades saved by Breakeven!")
    print(f" Win Rate:        {(wins/total*100):.1f}%")
    print(f" Loss Rate:       {(losses/total*100):.1f}% (Only {losses} actual losses!)")
    print(f" Net Profit:      +{net_r:.1f} R")
    print("==================================================================")

if __name__ == "__main__":
    test_gold_smc_with_be(count=4000, target_rr=2.0, be_trigger=1.0)
