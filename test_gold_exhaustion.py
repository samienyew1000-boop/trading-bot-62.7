import sys
sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

def test_gold_exhaustion_sweep():
    mt5.initialize()
    rates = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_M15, 0, 5000)
    mt5.shutdown()
    if rates is None:
        return

    df = pd.DataFrame(rates)
    df['time_dt'] = pd.to_datetime(df['time'], unit='s')
    
    # 20 SMA & Bollinger Bands
    df['sma20'] = df['close'].rolling(20).mean()
    df['std20'] = df['close'].rolling(20).std()
    df['upper_bb'] = df['sma20'] + (df['std20'] * 2.0)
    df['lower_bb'] = df['sma20'] - (df['std20'] * 2.0)
    
    # Fast RSI (7)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(7).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(7).mean()
    rs = gain / loss
    df['rsi7'] = 100 - (100 / (1 + rs))

    # ATR
    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift()).abs()
    lc = (df['low'] - df['close'].shift()).abs()
    df['atr'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean().bfill()

    trades = []
    
    for i in range(25, len(df) - 30):
        c = df.iloc[i]
        prev = df.iloc[i-1]
        atr = c['atr']
        
        # BEARISH EXHAUSTION (SELL):
        # 1. Price pierced above Upper Bollinger Band
        # 2. RSI7 was Overbought (> 75)
        # 3. Candle closed back inside BB with bearish body
        if prev['high'] > prev['upper_bb'] and prev['rsi7'] > 75 and c['close'] < c['upper_bb'] and c['close'] < c['open']:
            entry = c['close']
            sl = max(prev['high'], c['high']) + (atr * 0.2)
            risk = sl - entry
            if 0.8 <= risk <= 15.0:
                tp = entry - (risk * 1.5)
                
                outcome = "TIMEOUT"
                for k in range(i+1, min(i+35, len(df))):
                    fc = df.iloc[k]
                    if fc['high'] >= sl:
                        outcome = "LOSS"
                        break
                    if fc['low'] <= tp:
                        outcome = "WIN"
                        break
                if outcome in ["WIN", "LOSS"]:
                    trades.append({"type": "SELL", "outcome": outcome})

        # BULLISH EXHAUSTION (BUY):
        # 1. Price pierced below Lower Bollinger Band
        # 2. RSI7 was Oversold (< 25)
        # 3. Candle closed back inside BB with bullish body
        elif prev['low'] < prev['lower_bb'] and prev['rsi7'] < 25 and c['close'] > c['lower_bb'] and c['close'] > c['open']:
            entry = c['close']
            sl = min(prev['low'], c['low']) - (atr * 0.2)
            risk = entry - sl
            if 0.8 <= risk <= 15.0:
                tp = entry + (risk * 1.5)
                
                outcome = "TIMEOUT"
                for k in range(i+1, min(i+35, len(df))):
                    fc = df.iloc[k]
                    if fc['low'] <= sl:
                        outcome = "LOSS"
                        break
                    if fc['high'] >= tp:
                        outcome = "WIN"
                        break
                if outcome in ["WIN", "LOSS"]:
                    trades.append({"type": "BUY", "outcome": outcome})

    df_t = pd.DataFrame(trades)
    if not df_t.empty:
        w = len(df_t[df_t['outcome'] == 'WIN'])
        l = len(df_t[df_t['outcome'] == 'LOSS'])
        tot = len(df_t)
        net_r = (w * 1.5) - l
        pf = (w * 1.5) / l if l > 0 else 0
        print("==================================================================")
        print(f" 🏆 GOLD EXHAUSTION + LIQUIDITY GRAB (M15 Data: 5000 candles)")
        print("==================================================================")
        print(f" Total Trades:    {tot}")
        print(f" Wins (Hit 1.5R): {w}")
        print(f" Losses (Hit SL): {l}")
        print(f" Win Rate:        {(w/tot*100):.1f}%")
        print(f" Net Profit:      +{net_r:.1f} R")
        print(f" Profit Factor:   {pf:.2f}")
        print("==================================================================")

if __name__ == "__main__":
    test_gold_exhaustion_sweep()
