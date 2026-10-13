import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass
class SwingPoint:
    index: int
    time: int
    price: float
    point_type: str  # 'HIGH' or 'LOW'

@dataclass
class OrderBlock:
    index: int
    time: int
    ob_type: str     # 'BULLISH' or 'BEARISH'
    high: float
    low: float
    open_p: float
    close_p: float
    is_mitigated: bool = False
    is_failed: bool = False

def identify_swings(df: pd.DataFrame, swing_bars: int = 3) -> List[SwingPoint]:
    """Identify swing highs and swing lows using swing_bars to left and right."""
    swings = []
    n = len(df)
    for i in range(swing_bars, n - swing_bars):
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]
        
        # Check swing high
        is_high = True
        for j in range(1, swing_bars + 1):
            if df['high'].iloc[i - j] >= current_high or df['high'].iloc[i + j] >= current_high:
                is_high = False
                break
        if is_high:
            swings.append(SwingPoint(i, df['time'].iloc[i], current_high, 'HIGH'))
            
        # Check swing low
        is_low = True
        for j in range(1, swing_bars + 1):
            if df['low'].iloc[i - j] <= current_low or df['low'].iloc[i + j] <= current_low:
                is_low = False
                break
        if is_low:
            swings.append(SwingPoint(i, df['time'].iloc[i], current_low, 'LOW'))
            
    return swings

def get_market_structure(df: pd.DataFrame, swings: List[SwingPoint]) -> Tuple[str, Optional[SwingPoint], Optional[SwingPoint]]:
    """
    Determine Market Structure (Bullish or Bearish) from swings.
    Bullish: HH + HL
    Bearish: LL + LH
    """
    if len(swings) < 4:
        return "NEUTRAL", None, None
        
    highs = [s for s in swings if s.point_type == 'HIGH']
    lows = [s for s in swings if s.point_type == 'LOW']
    
    if len(highs) < 2 or len(lows) < 2:
        return "NEUTRAL", None, None
        
    last_h, prev_h = highs[-1], highs[-2]
    last_l, prev_l = lows[-1], lows[-2]
    
    if last_h.price > prev_h.price and last_l.price > prev_l.price:
        return "BULLISH", last_h, last_l
    elif last_h.price < prev_h.price and last_l.price < prev_l.price:
        return "BEARISH", last_h, last_l
    elif last_h.price > prev_h.price:
        return "BULLISH", last_h, last_l
    elif last_l.price < prev_l.price:
        return "BEARISH", last_h, last_l
        
    return "NEUTRAL", last_h, last_l

def detect_valid_order_blocks(df: pd.DataFrame, trend: str) -> List[OrderBlock]:
    """
    Detect Valid Order Blocks based on:
    1. Liquidity Sweep of previous candle (wick sweep)
    2. Followed by Imbalance (FVG)
    3. Status check: Mitigated vs Failed (failed ONLY on body close)
    """
    obs = []
    n = len(df)
    
    for i in range(1, n - 2):
        prev_candle = df.iloc[i - 1]
        ob_candle = df.iloc[i]
        next_candle_1 = df.iloc[i + 1]
        next_candle_2 = df.iloc[i + 2]
        
        # BEARISH OB (for Bearish trend or SELL setups)
        # 1. Swept previous candle high
        if ob_candle['high'] > prev_candle['high']:
            # 2. Imbalance (FVG below the OB): gap between OB low (or candle 1 low) and candle 2 high
            has_imbalance = ob_candle['low'] > next_candle_2['high'] or next_candle_1['low'] > next_candle_2['high']
            if has_imbalance:
                ob = OrderBlock(
                    index=i,
                    time=ob_candle['time'],
                    ob_type='BEARISH',
                    high=ob_candle['high'],
                    low=ob_candle['low'],
                    open_p=ob_candle['open'],
                    close_p=ob_candle['close']
                )
                
                # Check status in subsequent candles up to the latest closed candle
                for k in range(i + 2, n):
                    c = df.iloc[k]
                    # Body close ABOVE ob.high -> Failed!
                    body_max = max(c['open'], c['close'])
                    if body_max > ob.high:
                        ob.is_failed = True
                        break
                    # Tapped into OB zone -> Mitigated
                    if c['high'] >= ob.low and not ob.is_failed:
                        ob.is_mitigated = True
                        
                obs.append(ob)
                
        # BULLISH OB (for Bullish trend or BUY setups)
        # 1. Swept previous candle low
        if ob_candle['low'] < prev_candle['low']:
            # 2. Imbalance (FVG above the OB): gap between OB high and candle 2 low
            has_imbalance = ob_candle['high'] < next_candle_2['low'] or next_candle_1['high'] < next_candle_2['low']
            if has_imbalance:
                ob = OrderBlock(
                    index=i,
                    time=ob_candle['time'],
                    ob_type='BULLISH',
                    high=ob_candle['high'],
                    low=ob_candle['low'],
                    open_p=ob_candle['open'],
                    close_p=ob_candle['close']
                )
                
                # Check status in subsequent candles
                for k in range(i + 2, n):
                    c = df.iloc[k]
                    # Body close BELOW ob.low -> Failed!
                    body_min = min(c['open'], c['close'])
                    if body_min < ob.low:
                        ob.is_failed = True
                        break
                    # Tapped into OB zone -> Mitigated
                    if c['low'] <= ob.high and not ob.is_failed:
                        ob.is_mitigated = True
                        
                obs.append(ob)
                
    return obs
