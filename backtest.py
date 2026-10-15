import sys
sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

def run_gold_backtest(candles=10000):
    print("==========================================================================")
    print(f" 📊 RUNNING XAUUSD (GOLD) INSTITUTIONAL BACKTEST (Last {candles} 1H Candles)")
    print("==========================================================================")

    if not mt5.initialize():
        print("[ERROR] MT5 Init failed")
        return

    rates = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_H1, 0, candles)
    mt5.shutdown()

    if rates is None or len(rates) == 0:
        print("[ERROR] Failed to fetch rates")
        return

    df = pd.DataFrame(rates)
    df['time_dt'] = pd.to_datetime(df['time'], unit='s')
    df['hour'] = df['time_dt'].dt.hour
    df['date'] = df['time_dt'].dt.date

    # Indicators
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()

    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift()).abs()
    lc = (df['low'] - df['close'].shift()).abs()
    df['atr'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean().bfill()

    trades = []
    rr = 2.0

    for i in range(200, len(df) - 20):
        c = df.iloc[i]
        prev = df.iloc[i - 1]
        atr = c['atr']

        # Session filter: London & NY active volume hours (07:00 - 16:00 UTC)
        if c['hour'] < 7 or c['hour'] > 16:
            continue

        # BULLISH BUY SETUP
        if c['ema20'] > c['ema50'] and c['ema50'] > c['ema200']:
            if prev['low'] <= prev['ema20'] and c['close'] > prev['high'] and c['close'] > c['open']:
                entry = c['close']
                sl = prev['low'] - (atr * 0.3)
                risk = entry - sl
                if 2.0 <= risk <= 30.0:
                    tp = entry + (risk * rr)
                    outcome = "TIMEOUT"
                    for k in range(i + 1, min(i + 25, len(df))):
                        fc = df.iloc[k]
                        if fc['low'] <= sl:
                            outcome = "LOSS"
                            break
                        if fc['high'] >= tp:
                            outcome = "WIN"
                            break
                    if outcome in ["WIN", "LOSS"]:
                        trades.append({"type": "BUY", "outcome": outcome, "risk": risk})

        # BEARISH SELL SETUP
        elif c['ema20'] < c['ema50'] and c['ema50'] < c['ema200']:
            if prev['high'] >= prev['ema20'] and c['close'] < prev['low'] and c['close'] < c['open']:
                entry = c['close']
                sl = prev['high'] + (atr * 0.3)
                risk = sl - entry
                if 2.0 <= risk <= 30.0:
                    tp = entry - (risk * rr)
                    outcome = "TIMEOUT"
                    for k in range(i + 1, min(i + 25, len(df))):
                        fc = df.iloc[k]
                        if fc['high'] >= sl:
                            outcome = "LOSS"
                            break
                        if fc['low'] <= tp:
                            outcome = "WIN"
                            break
                    if outcome in ["WIN", "LOSS"]:
                        trades.append({"type": "SELL", "outcome": outcome, "risk": risk})

    df_t = pd.DataFrame(trades)
    wins = len(df_t[df_t['outcome'] == 'WIN'])
    losses = len(df_t[df_t['outcome'] == 'LOSS'])
    total = len(df_t)
    win_rate = (wins / total * 100) if total > 0 else 0
    net_r = (wins * rr) - losses
    profit_factor = (wins * rr) / losses if losses > 0 else 0

    print(f"📈 Total Trades:    {total}")
    print(f"🏆 Wins (Hit TP):   {wins}")
    print(f"🛑 Losses (Hit SL): {losses}")
    print(f"🎯 Win Rate:        {win_rate:.1f}%")
    print(f"⚖️ Risk to Reward:  1:{rr:.1f}")
    print(f"💰 Net Profit:      +{net_r:.1f} R")
    print(f"📊 Profit Factor:   {profit_factor:.2f}")
    print("==========================================================================")

if __name__ == "__main__":
    run_gold_backtest(10000)
