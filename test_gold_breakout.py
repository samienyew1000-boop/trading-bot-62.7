import sys
sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

def test_gold_london_breakout():
    mt5.initialize()
    # Fetch 5000 M15 candles
    rates = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_M15, 0, 5000)
    mt5.shutdown()
    if rates is None:
        return

    df = pd.DataFrame(rates)
    df['time_dt'] = pd.to_datetime(df['time'], unit='s')
    df['hour'] = df['time_dt'].dt.hour
    df['date'] = df['time_dt'].dt.date
    
    # 200 EMA on M15 to establish trend bias
    df['ema200'] = df['close'].ewm(span=200).mean()
    
    # Group by date
    dates = df['date'].unique()
    trades = []
    
    for d in dates:
        day_df = df[df['date'] == d]
        # Asian range: 00:00 - 06:45 UTC
        asian = day_df[day_df['hour'] < 7]
        if len(asian) < 15:
            continue
            
        asian_high = asian['high'].max()
        asian_low = asian['low'].min()
        asian_range = asian_high - asian_low
        
        # Filter out extreme chop or huge volatility days
        if asian_range < 3.0 or asian_range > 35.0:
            continue
            
        # London Session: 07:00 - 11:00 UTC
        london = day_df[(day_df['hour'] >= 7) & (day_df['hour'] <= 11)]
        if len(london) == 0:
            continue
            
        trade_taken = False
        for idx in range(len(london)):
            if trade_taken:
                break
            c = london.iloc[idx]
            
            # BULLISH BREAKOUT:
            # Price closes above Asian High, and is above 200 EMA
            if c['close'] > asian_high and c['close'] > c['ema200'] and c['close'] > c['open']:
                entry = c['close']
                sl = asian_high - (asian_range * 0.4)  # SL just back inside range
                risk = entry - sl
                tp = entry + (risk * 1.5)
                
                # Forward simulate rest of day
                remaining = day_df[day_df['time'] > c['time']]
                outcome = "TIMEOUT"
                for _, fc in remaining.iterrows():
                    if fc['low'] <= sl:
                        outcome = "LOSS"
                        break
                    if fc['high'] >= tp:
                        outcome = "WIN"
                        break
                if outcome in ["WIN", "LOSS"]:
                    trades.append({"date": str(d), "type": "BUY", "outcome": outcome})
                    trade_taken = True
                    
            # BEARISH BREAKOUT:
            # Price closes below Asian Low, and is below 200 EMA
            elif c['close'] < asian_low and c['close'] < c['ema200'] and c['close'] < c['open']:
                entry = c['close']
                sl = asian_low + (asian_range * 0.4)
                risk = sl - entry
                tp = entry - (risk * 1.5)
                
                remaining = day_df[day_df['time'] > c['time']]
                outcome = "TIMEOUT"
                for _, fc in remaining.iterrows():
                    if fc['high'] >= sl:
                        outcome = "LOSS"
                        break
                    if fc['low'] <= tp:
                        outcome = "WIN"
                        break
                if outcome in ["WIN", "LOSS"]:
                    trades.append({"date": str(d), "type": "SELL", "outcome": outcome})
                    trade_taken = True

    df_t = pd.DataFrame(trades)
    if not df_t.empty:
        w = len(df_t[df_t['outcome'] == 'WIN'])
        l = len(df_t[df_t['outcome'] == 'LOSS'])
        tot = len(df_t)
        net_r = (w * 1.5) - l
        pf = (w * 1.5) / l if l > 0 else 0
        print(f"Total: {tot} | Wins: {w} | Losses: {l} | Win Rate: {(w/tot*100):.1f}% | Net R: +{net_r:.1f}R | Profit Factor: {pf:.2f}")

if __name__ == "__main__":
    test_gold_london_breakout()
