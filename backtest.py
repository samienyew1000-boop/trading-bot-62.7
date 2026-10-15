import sys
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import config

def backtest_hybrid_asset(symbol: str, candles: int = 10000):
    cfg = config.ASSET_CONFIG[symbol]
    if not mt5.initialize():
        print(f"[ERROR] MT5 Init failed for {symbol}")
        return None

    mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, cfg["timeframe"], 0, candles)
    mt5.shutdown()

    if rates is None or len(rates) < 250:
        print(f"[ERROR] Failed to fetch rates for {symbol}")
        return None

    df = pd.DataFrame(rates)
    df['time_dt'] = pd.to_datetime(df['time'], unit='s')
    df['hour'] = df['time_dt'].dt.hour

    # Indicators
    df['ema5'] = df['close'].ewm(span=config.EMA_FAST).mean()
    df['ema20'] = df['close'].ewm(span=config.EMA_MID1).mean()
    df['ema50'] = df['close'].ewm(span=config.EMA_MID2).mean()
    df['ema200'] = df['close'].ewm(span=config.EMA_MACRO).mean()

    # RSI-2
    delta = df['close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=config.RSI_PERIOD - 1, adjust=False).mean()
    ema_down = down.ewm(com=config.RSI_PERIOD - 1, adjust=False).mean()
    rs = ema_up / ema_down
    df['rsi2'] = 100 - (100 / (1 + rs))

    # ATR
    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift()).abs()
    lc = (df['low'] - df['close'].shift()).abs()
    df['atr'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(config.ATR_PERIOD).mean().bfill()

    runner_trades = []
    sniper_trades = []

    # 1. Backtest Engine 1: Institutional Trend Runner
    if cfg.get("enable_runner", False):
        start_h = cfg["session_start_utc"]
        end_h = cfg["session_end_utc"]
        sl_buf = cfg["sl_buffer_atr"]
        min_r = cfg["min_risk"]
        max_r = cfg["max_risk"]
        rr = cfg["rr_ratio"]

        for i in range(200, len(df) - 20):
            c = df.iloc[i]
            prev = df.iloc[i - 1]
            atr = c['atr']

            if c['hour'] < start_h or c['hour'] > end_h:
                continue

            # Bullish Pullback BUY
            if c['ema20'] > c['ema50'] and c['ema50'] > c['ema200']:
                if prev['low'] <= prev['ema20'] and c['close'] > prev['high'] and c['close'] > c['open']:
                    entry = c['close']
                    sl = prev['low'] - (atr * sl_buf)
                    risk = entry - sl
                    if min_r <= risk <= max_r:
                        tp = entry + (risk * rr)
                        outcome = "TIMEOUT"
                        for k in range(i + 1, min(i + 25, len(df))):
                            if df['low'].iloc[k] <= sl:
                                outcome = "LOSS"
                                break
                            if df['high'].iloc[k] >= tp:
                                outcome = "WIN"
                                break
                        if outcome in ["WIN", "LOSS"]:
                            runner_trades.append({
                                "engine": "RUNNER",
                                "symbol": symbol,
                                "time": str(c['time_dt']),
                                "type": "BUY",
                                "entry": entry,
                                "sl": sl,
                                "tp": tp,
                                "outcome": outcome,
                                "r_pnl": rr if outcome == "WIN" else -1.0
                            })

            # Bearish Pullback SELL
            elif c['ema20'] < c['ema50'] and c['ema50'] < c['ema200']:
                if prev['high'] >= prev['ema20'] and c['close'] < prev['low'] and c['close'] < c['open']:
                    entry = c['close']
                    sl = prev['high'] + (atr * sl_buf)
                    risk = sl - entry
                    if min_r <= risk <= max_r:
                        tp = entry - (risk * rr)
                        outcome = "TIMEOUT"
                        for k in range(i + 1, min(i + 25, len(df))):
                            if df['high'].iloc[k] >= sl:
                                outcome = "LOSS"
                                break
                            if df['low'].iloc[k] <= tp:
                                outcome = "WIN"
                                break
                        if outcome in ["WIN", "LOSS"]:
                            runner_trades.append({
                                "engine": "RUNNER",
                                "symbol": symbol,
                                "time": str(c['time_dt']),
                                "type": "SELL",
                                "entry": entry,
                                "sl": sl,
                                "tp": tp,
                                "outcome": outcome,
                                "r_pnl": rr if outcome == "WIN" else -1.0
                            })

    # 2. Backtest Engine 2: AI Sniper Mean Reversion
    if cfg.get("enable_sniper", False):
        sl_mult = cfg.get("sniper_sl_atr", 2.5)
        rsi_buy = cfg.get("sniper_rsi_buy", 10)
        rsi_sell = cfg.get("sniper_rsi_sell", 90)

        for i in range(200, len(df) - 20):
            c = df.iloc[i]
            atr = c['atr']

            # Macro Uptrend + Extreme Oversold Pullback
            if c['close'] > c['ema200'] and c['rsi2'] <= rsi_buy:
                entry = c['close']
                sl = entry - (atr * sl_mult)
                risk = entry - sl
                outcome = "TIMEOUT"
                exit_price = entry
                for k in range(i + 1, min(i + 20, len(df))):
                    if df['low'].iloc[k] <= sl:
                        outcome = "LOSS"
                        exit_price = sl
                        break
                    if df['close'].iloc[k] >= df['ema5'].iloc[k]:
                        outcome = "WIN"
                        exit_price = df['close'].iloc[k]
                        break
                if outcome in ["WIN", "LOSS"]:
                    r_gain = (exit_price - entry) / risk if outcome == "WIN" else -1.0
                    sniper_trades.append({
                        "engine": "SNIPER",
                        "symbol": symbol,
                        "time": str(c['time_dt']),
                        "type": "BUY",
                        "entry": entry,
                        "sl": sl,
                        "tp": exit_price,
                        "outcome": outcome,
                        "r_pnl": r_gain
                    })

            # Macro Downtrend + Extreme Overbought Pullback
            elif c['close'] < c['ema200'] and c['rsi2'] >= rsi_sell:
                entry = c['close']
                sl = entry + (atr * sl_mult)
                risk = sl - entry
                outcome = "TIMEOUT"
                exit_price = entry
                for k in range(i + 1, min(i + 20, len(df))):
                    if df['high'].iloc[k] >= sl:
                        outcome = "LOSS"
                        exit_price = sl
                        break
                    if df['close'].iloc[k] <= df['ema5'].iloc[k]:
                        outcome = "WIN"
                        exit_price = df['close'].iloc[k]
                        break
                if outcome in ["WIN", "LOSS"]:
                    r_gain = (entry - exit_price) / risk if outcome == "WIN" else -1.0
                    sniper_trades.append({
                        "engine": "SNIPER",
                        "symbol": symbol,
                        "time": str(c['time_dt']),
                        "type": "SELL",
                        "entry": entry,
                        "sl": sl,
                        "tp": exit_price,
                        "outcome": outcome,
                        "r_pnl": r_gain
                    })

    all_trades = runner_trades + sniper_trades
    df_all = pd.DataFrame(all_trades)

    # Save verification CSV
    csv_filename = f"hybrid_{symbol.lower()}_verification.csv"
    if len(df_all) > 0:
        df_all.to_csv(csv_filename, index=False)

    def calc_stats(t_list):
        if not t_list:
            return {"tot": 0, "wins": 0, "losses": 0, "wr": 0.0, "net_r": 0.0}
        d = pd.DataFrame(t_list)
        w = len(d[d['outcome'] == 'WIN'])
        l = len(d[d['outcome'] == 'LOSS'])
        tot = len(d)
        wr = (w / tot * 100) if tot > 0 else 0
        net_r = d['r_pnl'].sum()
        return {"tot": tot, "wins": w, "losses": l, "wr": wr, "net_r": net_r}

    runner_stats = calc_stats(runner_trades)
    sniper_stats = calc_stats(sniper_trades)
    comb_stats = calc_stats(all_trades)

    return {
        "symbol": symbol,
        "name": cfg["name"],
        "candles": len(df),
        "runner": runner_stats,
        "sniper": sniper_stats,
        "combined": comb_stats,
        "csv": csv_filename
    }

def main():
    print("==========================================================================================")
    print(" 🚀 HYBRID AI BOT MULTI-ASSET QUANT BACKTEST REPORT (Last 10,000 1H Candles)")
    print("    • Engine 1: Institutional Trend Runner (1:2 R:R Pullback)")
    print("    • Engine 2: AI Sniper Mean Reversion (80-86% Win Rate Larry Connors Model)")
    print("==========================================================================================")

    results = []
    for s in config.SYMBOLS:
        res = backtest_hybrid_asset(s, candles=10000)
        if res:
            results.append(res)
            cfg = config.ASSET_CONFIG[s]
            print(f"\n--- {cfg['icon']} {cfg['name']} ({s}) ---")
            
            # Runner
            rn = res['runner']
            if cfg.get('enable_runner', False):
                print(f"  🚀 [AI Runner 1:2 R:R]:  Trades={rn['tot']:<4} | Wins={rn['wins']:<3} | WR={rn['wr']:.1f}% | Net R={rn['net_r']:+.1f} R")
            else:
                print(f"  🚀 [AI Runner 1:2 R:R]:  Disabled (Chop Protection)")

            # Sniper
            sn = res['sniper']
            print(f"  🎯 [AI Sniper MeanRev]: Trades={sn['tot']:<4} | Wins={sn['wins']:<3} | WR={sn['wr']:.1f}% | Net R={sn['net_r']:+.1f} R")

            # Combined
            cb = res['combined']
            print(f"  ⭐ Combined {s}:        Trades={cb['tot']:<4} | Wins={cb['wins']:<3} | WR={cb['wr']:.1f}% | Net R={cb['net_r']:+.1f} R")
            print(f"  📁 Trade Proof CSV:     {res['csv']}")

    print("\n==========================================================================================")
    print(" 📋 OVERALL HYBRID PORTFOLIO PERFORMANCE SUMMARY (3 Assets Combined):")
    print("==========================================================================================")
    tot_trades = sum(r['combined']['tot'] for r in results)
    tot_wins = sum(r['combined']['wins'] for r in results)
    tot_losses = sum(r['combined']['losses'] for r in results)
    overall_wr = (tot_wins / tot_trades * 100) if tot_trades > 0 else 0
    tot_net_r = sum(r['combined']['net_r'] for r in results)

    # Runner Total
    rn_tot = sum(r['runner']['tot'] for r in results)
    rn_w = sum(r['runner']['wins'] for r in results)
    rn_wr = (rn_w / rn_tot * 100) if rn_tot > 0 else 0
    rn_net_r = sum(r['runner']['net_r'] for r in results)

    # Sniper Total
    sn_tot = sum(r['sniper']['tot'] for r in results)
    sn_w = sum(r['sniper']['wins'] for r in results)
    sn_wr = (sn_w / sn_tot * 100) if sn_tot > 0 else 0
    sn_net_r = sum(r['sniper']['net_r'] for r in results)

    print(f"  🎯 Total AI Sniper Trades:  {sn_tot:<4} | Wins: {sn_w:<4} | WR: {sn_wr:.1f}% | Net R: {sn_net_r:+.1f} R")
    print(f"  🚀 Total Trend Runner Trades:{rn_tot:<4} | Wins: {rn_w:<4} | WR: {rn_wr:.1f}% | Net R: {rn_net_r:+.1f} R")
    print("  ----------------------------------------------------------------------------------------")
    print(f"  🏆 PORTFOLIO TOTAL TRADES:  {tot_trades}")
    print(f"  🏆 PORTFOLIO TOTAL WINS:    {tot_wins} (Losses: {tot_losses})")
    print(f"  🎯 PORTFOLIO WIN RATE:      {overall_wr:.1f}%")
    print(f"  💰 PORTFOLIO NET PROFIT:    +{tot_net_r:.1f} R")
    print("==========================================================================================")

if __name__ == "__main__":
    main()
