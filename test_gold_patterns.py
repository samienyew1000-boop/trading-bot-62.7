import sys
sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

def analyze_gold_session_sweeps(candles_count=10000, target_rr=2.0):
    if not mt5.initialize():
        print("MT5 Init failed")
        return

    rates = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_M5, 0, candles_count)
    mt5.shutdown()
    
    if rates is None or len(rates) == 0:
        print("No rates returned")
        return

    df = pd.DataFrame(rates)
    df['time_dt'] = pd.to_datetime(df['time'], unit='s')
    df['hour'] = df['time_dt'].dt.hour
    df['date'] = df['time_dt'].dt.date

    # ATR calculation for dynamic buffer
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean().fillna(1.0)

    trades = []
    
    # Group by date to extract Asian session (00:00 to 06:00 UTC) High & Low
    dates = df['date'].unique()
    
    for d in dates:
        day_df = df[df['date'] == d]
        asian = day_df[(day_df['hour'] >= 0) & (day_df['hour'] < 6)]
        
        if len(asian) < 20:
            continue
            
        asian_high = asian['high'].max()
        asian_low = asian['low'].min()
        asian_range = asian_high - asian_low
        
        # We want active London and NY hours: 07:00 to 16:00 UTC
        trading_hours = day_df[(day_df['hour'] >= 7) & (day_df['hour'] <= 16)]
        
        trade_taken_today = False
        
        for idx in range(len(trading_hours) - 15):
            if trade_taken_today:
                break
                
            curr = trading_hours.iloc[idx]
            prev = trading_hours.iloc[idx - 1]
            atr = curr['atr']
            
            # 1. BEARISH SETUP: Price swept Asian High, then closed back below with displacement
            if prev['high'] > asian_high and curr['close'] < asian_high and curr['close'] < curr['open']:
                # Reversal candle confirmed
                sweep_peak = max(prev['high'], curr['high'])
                entry = curr['close']
                sl = sweep_peak + (atr * 0.5)
                risk = sl - entry
                if risk <= 0.3 or risk > 15.0:  # Sensible gold risk filter (between 30 cents and $15)
                    continue
                    
                tp = entry - (risk * target_rr)
                
                # Check forward result
                future = trading_hours.iloc[idx + 1: idx + 60]
                outcome = "TIMEOUT"
                for _, f_candle in future.iterrows():
                    if f_candle['high'] >= sl:
                        outcome = "LOSS"
                        break
                    if f_candle['low'] <= tp:
                        outcome = "WIN"
                        break
                        
                if outcome in ["WIN", "LOSS"]:
                    trades.append({
                        "date": str(d),
                        "type": "SELL",
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                        "outcome": outcome,
                        "r": target_rr if outcome == "WIN" else -1.0
                    })
                    trade_taken_today = True

            # 2. BULLISH SETUP: Price swept Asian Low, then closed back above with displacement
            elif prev['low'] < asian_low and curr['close'] > asian_low and curr['close'] > curr['open']:
                sweep_trough = min(prev['low'], curr['low'])
                entry = curr['close']
                sl = sweep_trough - (atr * 0.5)
                risk = entry - sl
                if risk <= 0.3 or risk > 15.0:
                    continue
                    
                tp = entry + (risk * target_rr)
                
                # Check forward result
                future = trading_hours.iloc[idx + 1: idx + 60]
                outcome = "TIMEOUT"
                for _, f_candle in future.iterrows():
                    if f_candle['low'] <= sl:
                        outcome = "LOSS"
                        break
                    if f_candle['high'] >= tp:
                        outcome = "WIN"
                        break
                        
                if outcome in ["WIN", "LOSS"]:
                    trades.append({
                        "date": str(d),
                        "type": "BUY",
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                        "outcome": outcome,
                        "r": target_rr if outcome == "WIN" else -1.0
                    })
                    trade_taken_today = True

    df_res = pd.DataFrame(trades)
    if df_res.empty:
        print("No trades triggered.")
        return

    wins = len(df_res[df_res['outcome'] == 'WIN'])
    losses = len(df_res[df_res['outcome'] == 'LOSS'])
    total = len(df_res)
    win_rate = (wins / total) * 100
    net_r = df_res['r'].sum()
    profit_factor = (wins * target_rr) / losses if losses > 0 else float('inf')

    print("==================================================================")
    print(f" 🏆 XAUUSD (GOLD) RECURRING PATTERN RESULTS (Target RR: 1:{target_rr})")
    print("==================================================================")
    print(f" Total Trades:    {total}")
    print(f" Wins (Hit TP):   {wins}")
    print(f" Losses (Hit SL): {losses}")
    print(f" Win Rate:        {win_rate:.1f}%")
    print(f" Net Profit:      +{net_r:.1f} R")
    print(f" Profit Factor:   {profit_factor:.2f}")
    print("==================================================================")

if __name__ == "__main__":
    analyze_gold_session_sweeps(candles_count=10000, target_rr=1.5)
    analyze_gold_session_sweeps(candles_count=10000, target_rr=2.0)
