import sys
sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

def run_gold_quant_research():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    # Fetch 5000 M15 candles for Gold
    rates_m15 = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_M15, 0, 5000)
    mt5.shutdown()

    if rates_m15 is None or len(rates_m15) == 0:
        print("No rates found for XAUUSD")
        return

    df = pd.DataFrame(rates_m15)
    df['time_dt'] = pd.to_datetime(df['time'], unit='s')
    df['hour'] = df['time_dt'].dt.hour
    df['date'] = df['time_dt'].dt.date

    # ATR (Average True Range)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean().bfill()

    # EMAs
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()

    print(f"Loaded {len(df)} M15 candles from {df['time_dt'].iloc[0]} to {df['time_dt'].iloc[-1]}")

    # -------------------------------------------------------------
    # STRATEGY 1: Gold Institutional Liquidity Sweep + Rejection (Judas Swing)
    # Rules:
    # 1. Trading Session: London (07:00 - 11:00 UTC) or NY (12:00 - 16:00 UTC)
    # 2. Key High/Low: Prior 20 candles High/Low swept by wick
    # 3. Candle Closes back inside with strong rejection
    # 4. SL: Beyond the wick + 0.3*ATR buffer
    # 5. TP: 1:2 RR, Move to Breakeven at 1R
    # -------------------------------------------------------------
    trades_s1 = []
    for i in range(30, len(df) - 40):
        c = df.iloc[i]
        prev = df.iloc[i-1]
        prior_window = df.iloc[i-20:i]
        prior_high = prior_window['high'].max()
        prior_low = prior_window['low'].min()
        atr = c['atr']

        # Session filter: Active trading hours (07:00 to 16:00 UTC)
        if c['hour'] < 7 or c['hour'] > 16:
            continue

        # BEARISH SWEEP:
        # Wick swept prior_high, but candle closed below prior_high and bearish
        if c['high'] > prior_high and c['close'] < prior_high and c['close'] < c['open']:
            # Rejection wick on top must be at least 35% of total candle range
            candle_range = c['high'] - c['low']
            upper_wick = c['high'] - max(c['open'], c['close'])
            if candle_range > 0 and (upper_wick / candle_range) >= 0.35:
                entry = c['close']
                sl = c['high'] + (atr * 0.3)
                risk = sl - entry
                if 1.0 <= risk <= 20.0:
                    tp = entry - (risk * 2.0)
                    be_trigger = entry - risk
                    
                    outcome = "TIMEOUT"
                    hit_be = False
                    for k in range(i + 1, min(i + 40, len(df))):
                        future = df.iloc[k]
                        if future['low'] <= be_trigger:
                            hit_be = True
                            sl = entry  # Moved to BE
                        if future['high'] >= sl:
                            outcome = "BE" if hit_be else "LOSS"
                            break
                        if future['low'] <= tp:
                            outcome = "WIN"
                            break
                    trades_s1.append({"type": "SELL", "outcome": outcome, "time": c['time_dt']})

        # BULLISH SWEEP:
        # Wick swept prior_low, but candle closed above prior_low and bullish
        elif c['low'] < prior_low and c['close'] > prior_low and c['close'] > c['open']:
            candle_range = c['high'] - c['low']
            lower_wick = min(c['open'], c['close']) - c['low']
            if candle_range > 0 and (lower_wick / candle_range) >= 0.35:
                entry = c['close']
                sl = c['low'] - (atr * 0.3)
                risk = entry - sl
                if 1.0 <= risk <= 20.0:
                    tp = entry + (risk * 2.0)
                    be_trigger = entry + risk
                    
                    outcome = "TIMEOUT"
                    hit_be = False
                    for k in range(i + 1, min(i + 40, len(df))):
                        future = df.iloc[k]
                        if future['high'] >= be_trigger:
                            hit_be = True
                            sl = entry  # Moved to BE
                        if future['low'] <= sl:
                            outcome = "BE" if hit_be else "LOSS"
                            break
                        if future['high'] >= tp:
                            outcome = "WIN"
                            break
                    trades_s1.append({"type": "BUY", "outcome": outcome, "time": c['time_dt']})

    df1 = pd.DataFrame(trades_s1)
    if not df1.empty:
        wins1 = len(df1[df1['outcome'] == 'WIN'])
        losses1 = len(df1[df1['outcome'] == 'LOSS'])
        bes1 = len(df1[df1['outcome'] == 'BE'])
        tot1 = len(df1[df1['outcome'].isin(['WIN', 'LOSS', 'BE'])])
        net_r1 = (wins1 * 2.0) - losses1
        print("\n=======================================================")
        print(" 🥇 MODEL 1: GOLD SESSION LIQUIDITY SWEEP + BREAKEVEN")
        print("=======================================================")
        print(f" Total Trades:    {tot1}")
        print(f" Wins (Hit 2R):   {wins1} ({(wins1/tot1*100):.1f}%)")
        print(f" Breakeven (0$):  {bes1} ({(bes1/tot1*100):.1f}%) [Saved Trades]")
        print(f" Losses (Hit SL): {losses1} ({(losses1/tot1*100):.1f}%)")
        print(f" Win Rate:        {(wins1/(wins1+losses1)*100):.1f}% (excluding BE)")
        print(f" Net Profit:      +{net_r1:.1f} R")
        print(f" Profit Factor:   {(wins1*2.0)/losses1 if losses1>0 else 99:.2f}")

    # -------------------------------------------------------------
    # STRATEGY 2: Gold Trend-Continuation FVG / Order Block
    # -------------------------------------------------------------
    trades_s2 = []
    for i in range(200, len(df) - 40):
        c = df.iloc[i]
        prev = df.iloc[i-1]
        atr = c['atr']
        
        # Session Filter
        if c['hour'] < 7 or c['hour'] > 17:
            continue

        # Bullish Trend: Close > EMA50 > EMA200
        if c['close'] > c['ema50'] and c['ema50'] > c['ema200']:
            # Pullback to EMA20 / 50 with rejection
            if prev['low'] <= c['ema20'] and c['close'] > prev['high'] and c['close'] > c['open']:
                entry = c['close']
                sl = prev['low'] - (atr * 0.4)
                risk = entry - sl
                if 1.0 <= risk <= 20.0:
                    tp = entry + (risk * 2.0)
                    be_trigger = entry + (risk * 1.0)
                    outcome = "TIMEOUT"
                    hit_be = False
                    for k in range(i + 1, min(i + 40, len(df))):
                        future = df.iloc[k]
                        if future['high'] >= be_trigger:
                            hit_be = True
                            sl = entry
                        if future['low'] <= sl:
                            outcome = "BE" if hit_be else "LOSS"
                            break
                        if future['high'] >= tp:
                            outcome = "WIN"
                            break
                    trades_s2.append({"type": "BUY", "outcome": outcome})

        # Bearish Trend: Close < EMA50 < EMA200
        elif c['close'] < c['ema50'] and c['ema50'] < c['ema200']:
            if prev['high'] >= c['ema20'] and c['close'] < prev['low'] and c['close'] < c['open']:
                entry = c['close']
                sl = prev['high'] + (atr * 0.4)
                risk = sl - entry
                if 1.0 <= risk <= 20.0:
                    tp = entry - (risk * 2.0)
                    be_trigger = entry - (risk * 1.0)
                    outcome = "TIMEOUT"
                    hit_be = False
                    for k in range(i + 1, min(i + 40, len(df))):
                        future = df.iloc[k]
                        if future['low'] <= be_trigger:
                            hit_be = True
                            sl = entry
                        if future['high'] >= sl:
                            outcome = "BE" if hit_be else "LOSS"
                            break
                        if future['low'] <= tp:
                            outcome = "WIN"
                            break
                    trades_s2.append({"type": "SELL", "outcome": outcome})

    df2 = pd.DataFrame(trades_s2)
    if not df2.empty:
        wins2 = len(df2[df2['outcome'] == 'WIN'])
        losses2 = len(df2[df2['outcome'] == 'LOSS'])
        bes2 = len(df2[df2['outcome'] == 'BE'])
        tot2 = len(df2[df2['outcome'].isin(['WIN', 'LOSS', 'BE'])])
        net_r2 = (wins2 * 2.0) - losses2
        print("\n=======================================================")
        print(" 🥈 MODEL 2: GOLD TREND PULLBACK + DYNAMIC BREAKEVEN")
        print("=======================================================")
        print(f" Total Trades:    {tot2}")
        print(f" Wins (Hit 2R):   {wins2} ({(wins2/tot2*100):.1f}%)")
        print(f" Breakeven (0$):  {bes2} ({(bes2/tot2*100):.1f}%)")
        print(f" Losses (Hit SL): {losses2} ({(losses2/tot2*100):.1f}%)")
        print(f" Win Rate:        {(wins2/(wins2+losses2)*100):.1f}% (excluding BE)")
        print(f" Net Profit:      +{net_r2:.1f} R")
        print(f" Profit Factor:   {(wins2*2.0)/losses2 if losses2>0 else 99:.2f}")
        print("=======================================================\n")

if __name__ == "__main__":
    run_gold_quant_research()
