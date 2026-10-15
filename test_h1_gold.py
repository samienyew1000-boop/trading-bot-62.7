import sys
sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

def test_h1_gold_models():
    mt5.initialize()
    rates = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_H1, 0, 5000)
    mt5.shutdown()
    
    if rates is None:
        return
        
    df = pd.DataFrame(rates)
    df['time_dt'] = pd.to_datetime(df['time'], unit='s')
    df['hour'] = df['time_dt'].dt.hour
    
    # ATR
    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift()).abs()
    lc = (df['low'] - df['close'].shift()).abs()
    df['atr'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean().bfill()
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()

    # Model: London/NY Momentum Expansion
    # Gold has strong session volume expansion
    # Test London Open (07:00 or 08:00 UTC) direction candle
    trades = []
    for i in range(50, len(df) - 24):
        c = df.iloc[i]
        prev = df.iloc[i-1]
        
        # Trigger at London open (07:00 UTC) or NY open (13:00 UTC)
        if c['hour'] in [7, 13]:
            # Strong momentum candle
            body = abs(c['close'] - c['open'])
            range_c = c['high'] - c['low']
            atr = c['atr']
            
            # Strong Bullish expansion candle
            if c['close'] > c['open'] and (body / range_c) > 0.6 and body > (atr * 0.8):
                if c['close'] > df['high'].iloc[i-5:i].max():
                    entry = c['close']
                    sl = c['low'] - (atr * 0.2)
                    risk = entry - sl
                    tp = entry + (risk * 1.5)
                    be_level = entry + risk
                    
                    outcome = "TIMEOUT"
                    hit_be = False
                    for k in range(i+1, min(i+16, len(df))):
                        fc = df.iloc[k]
                        if fc['high'] >= be_level:
                            hit_be = True
                            sl = entry
                        if fc['low'] <= sl:
                            outcome = "BE" if hit_be else "LOSS"
                            break
                        if fc['high'] >= tp:
                            outcome = "WIN"
                            break
                    trades.append({"type": "BUY", "outcome": outcome})

            # Strong Bearish expansion candle
            elif c['close'] < c['open'] and (body / range_c) > 0.6 and body > (atr * 0.8):
                if c['close'] < df['low'].iloc[i-5:i].min():
                    entry = c['close']
                    sl = c['high'] + (atr * 0.2)
                    risk = sl - entry
                    tp = entry - (risk * 1.5)
                    be_level = entry - risk
                    
                    outcome = "TIMEOUT"
                    hit_be = False
                    for k in range(i+1, min(i+16, len(df))):
                        fc = df.iloc[k]
                        if fc['low'] <= be_level:
                            hit_be = True
                            sl = entry
                        if fc['high'] >= sl:
                            outcome = "BE" if hit_be else "LOSS"
                            break
                        if fc['low'] <= tp:
                            outcome = "WIN"
                            break
                    trades.append({"type": "SELL", "outcome": outcome})

    df_res = pd.DataFrame(trades)
    if not df_res.empty:
        closed = df_res[df_res['outcome'].isin(['WIN', 'LOSS', 'BE'])]
        w = len(closed[closed['outcome'] == 'WIN'])
        l = len(closed[closed['outcome'] == 'LOSS'])
        be = len(closed[closed['outcome'] == 'BE'])
        tot = len(closed)
        net_r = (w * 1.5) - l
        pf = (w * 1.5) / l if l > 0 else 0
        print(f"Total: {tot} | Wins: {w} | Losses: {l} | BE: {be} | Win Rate (excl BE): {(w/(w+l)*100):.1f}% | Net R: +{net_r:.1f}R | PF: {pf:.2f}")

if __name__ == "__main__":
    test_h1_gold_models()
