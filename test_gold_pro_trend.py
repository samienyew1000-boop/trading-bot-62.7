import sys
sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

def test_gold_pro_trend(count=10000):
    mt5.initialize()
    rates = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_M15, 0, count)
    mt5.shutdown()
    
    if rates is None:
        return
        
    df = pd.DataFrame(rates)
    df['time_dt'] = pd.to_datetime(df['time'], unit='s')
    
    # 1. Macro Trend: 50 EMA and 200 EMA
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean().fillna(1.0)
    
    # RSI for pullback oversold/overbought
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    trades = []
    
    for i in range(200, len(df) - 30):
        c = df.iloc[i]
        prev = df.iloc[i - 1]
        atr = c['atr']
        
        # BULLISH SETUP:
        # Macro Bullish: EMA 50 > EMA 200, price above EMA 200
        # Pullback: Price touches or dips to EMA 50, RSI pulls back (< 45)
        # Trigger: Bullish reversal candle closing above previous high
        if c['ema50'] > c['ema200'] and prev['low'] <= prev['ema50'] and c['close'] > c['open'] and prev['rsi'] < 48:
            if c['close'] > prev['high']:
                entry = c['close']
                sl = prev['low'] - (atr * 0.5)
                risk = entry - sl
                if risk < 1.0 or risk > 25.0:
                    continue
                tp = entry + (risk * 2.0)
                
                # Forward simulate
                outcome = "TIMEOUT"
                for k in range(i + 1, min(i + 50, len(df))):
                    fc = df.iloc[k]
                    if fc['low'] <= sl:
                        outcome = "LOSS"
                        break
                    if fc['high'] >= tp:
                        outcome = "WIN"
                        break
                if outcome in ["WIN", "LOSS"]:
                    trades.append({"type": "BUY", "outcome": outcome, "r": 2.0 if outcome == "WIN" else -1.0})

        # BEARISH SETUP:
        # Macro Bearish: EMA 50 < EMA 200, price below EMA 200
        # Pullback: Price touches or rallies to EMA 50, RSI rallies (> 55)
        # Trigger: Bearish reversal candle closing below previous low
        elif c['ema50'] < c['ema200'] and prev['high'] >= prev['ema50'] and c['close'] < c['open'] and prev['rsi'] > 52:
            if c['close'] < prev['low']:
                entry = c['close']
                sl = prev['high'] + (atr * 0.5)
                risk = sl - entry
                if risk < 1.0 or risk > 25.0:
                    continue
                tp = entry - (risk * 2.0)
                
                outcome = "TIMEOUT"
                for k in range(i + 1, min(i + 50, len(df))):
                    fc = df.iloc[k]
                    if fc['high'] >= sl:
                        outcome = "LOSS"
                        break
                    if fc['low'] <= tp:
                        outcome = "WIN"
                        break
                if outcome in ["WIN", "LOSS"]:
                    trades.append({"type": "SELL", "outcome": outcome, "r": 2.0 if outcome == "WIN" else -1.0})

    df_res = pd.DataFrame(trades)
    if df_res.empty:
        print("No trades")
        return
    wins = len(df_res[df_res['outcome'] == 'WIN'])
    losses = len(df_res[df_res['outcome'] == 'LOSS'])
    total = len(df_res)
    win_rate = (wins / total) * 100
    net_r = df_res['r'].sum()
    pf = (wins * 2.0) / losses if losses > 0 else 0
    print("==================================================================")
    print(" 🏆 XAUUSD (GOLD) PRO-TREND PULLBACK STRATEGY (15M)")
    print("==================================================================")
    print(f" Total Trades:    {total}")
    print(f" Wins (Hit TP):   {wins}")
    print(f" Losses (Hit SL): {losses}")
    print(f" Win Rate:        {win_rate:.1f}%")
    print(f" Net Profit:      +{net_r:.1f} R")
    print(f" Profit Factor:   {pf:.2f}")
    print("==================================================================")

if __name__ == "__main__":
    test_gold_pro_trend(count=10000)
