import sys
sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

def discover_gold_edge():
    if not mt5.initialize():
        print("MT5 Failed")
        return

    # Fetch 1H candles (gives long history: 5000 hours ~ 10 months)
    rates = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_H1, 0, 5000)
    mt5.shutdown()
    if rates is None:
        return

    df = pd.DataFrame(rates)
    df['time_dt'] = pd.to_datetime(df['time'], unit='s')
    df['hour'] = df['time_dt'].dt.hour
    
    # Technicals
    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift()).abs()
    lc = (df['low'] - df['close'].shift()).abs()
    df['atr'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean().bfill()
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()

    # Model 1: 1H Trend Continuation via EMA 20 Bounce with FVG
    results = []
    for rr in [1.2, 1.5, 2.0]:
        trades = []
        for i in range(200, len(df) - 20):
            c = df.iloc[i]
            prev = df.iloc[i-1]
            atr = c['atr']
            
            # BULLISH TREND: EMA20 > EMA50 > EMA200
            if c['ema20'] > c['ema50'] and c['ema50'] > c['ema200']:
                # Pullback touched EMA20 or EMA50 and closed bullish above prior high
                if prev['low'] <= prev['ema20'] and c['close'] > prev['high'] and c['close'] > c['open']:
                    entry = c['close']
                    sl = prev['low'] - (atr * 0.3)
                    risk = entry - sl
                    if 2.0 <= risk <= 30.0:
                        tp = entry + (risk * rr)
                        out = "TIMEOUT"
                        for k in range(i+1, min(i+25, len(df))):
                            fc = df.iloc[k]
                            if fc['low'] <= sl:
                                out = "LOSS"
                                break
                            if fc['high'] >= tp:
                                out = "WIN"
                                break
                        if out in ["WIN", "LOSS"]:
                            trades.append(out)

            # BEARISH TREND: EMA20 < EMA50 < EMA200
            elif c['ema20'] < c['ema50'] and c['ema50'] < c['ema200']:
                if prev['high'] >= prev['ema20'] and c['close'] < prev['low'] and c['close'] < c['open']:
                    entry = c['close']
                    sl = prev['high'] + (atr * 0.3)
                    risk = sl - entry
                    if 2.0 <= risk <= 30.0:
                        tp = entry - (risk * rr)
                        out = "TIMEOUT"
                        for k in range(i+1, min(i+25, len(df))):
                            fc = df.iloc[k]
                            if fc['high'] >= sl:
                                out = "LOSS"
                                break
                            if fc['low'] <= tp:
                                out = "WIN"
                                break
                        if out in ["WIN", "LOSS"]:
                            trades.append(out)

        w = trades.count("WIN")
        l = trades.count("LOSS")
        tot = w + l
        wr = (w / tot * 100) if tot > 0 else 0
        net_r = (w * rr) - l
        pf = (w * rr) / l if l > 0 else 0
        results.append({"model": "1H Trend Pullback Bounce", "rr": rr, "trades": tot, "wins": w, "losses": l, "win_rate": wr, "net_r": net_r, "pf": pf})

    print("=========================================================================")
    print(" 🔍 QUANT RESEARCH FINDINGS ON XAUUSD (Last 5000 1H Candles)")
    print("=========================================================================")
    for r in results:
        print(f" RR 1:{r['rr']} | Trades: {r['trades']} | Win Rate: {r['win_rate']:.1f}% | Wins: {r['wins']} | Losses: {r['losses']} | Net: +{r['net_r']:.1f}R | Profit Factor: {r['pf']:.2f}")
    print("=========================================================================")

if __name__ == "__main__":
    discover_gold_edge()
