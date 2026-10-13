import os
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

def generate_candlestick_chart(df: pd.DataFrame, symbol: str, timeframe: str, 
                               ob=None, sl: float = None, tp: float = None, 
                               output_path: str = "chart.png") -> str:
    """
    Generate a sleek TradingView-style dark candlestick chart with highlighted OB, SL, and TP.
    Uses Pillow (fast, lightweight, 0 dependencies).
    """
    candles = df.tail(45).reset_index(drop=True)
    n = len(candles)
    if n < 5:
        return ""

    width = 900
    height = 550
    margin_top = 60
    margin_bottom = 50
    margin_left = 30
    margin_right = 90

    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    # Min/Max prices with padding
    min_p = candles['low'].min()
    max_p = candles['high'].max()
    if ob:
        min_p = min(min_p, ob.low)
        max_p = max(max_p, ob.high)
    if sl:
        min_p = min(min_p, sl)
        max_p = max(max_p, sl)
    if tp:
        min_p = min(min_p, tp)
        max_p = max(max_p, tp)

    pad = (max_p - min_p) * 0.1
    if pad == 0:
        pad = 0.001
    min_p -= pad
    max_p += pad

    def price_to_y(p):
        return margin_top + plot_h - ((p - min_p) / (max_p - min_p)) * plot_h

    # Create dark TradingView style canvas
    img = Image.new("RGBA", (width, height), (19, 23, 34, 255))
    draw = ImageDraw.Draw(img)

    # Grid lines & Price axis
    num_grids = 6
    for i in range(num_grids + 1):
        price_val = min_p + i * (max_p - min_p) / num_grids
        y = price_to_y(price_val)
        draw.line([(margin_left, y), (width - margin_right, y)], fill=(34, 43, 60, 255), width=1)
        draw.text((width - margin_right + 8, y - 6), f"{price_val:.5f}", fill=(130, 140, 160, 255))

    # Candle spacing
    candle_w = max(4, int(plot_w / n * 0.65))
    step = plot_w / n

    # Draw Highlighted Order Block Box if present
    if ob:
        y_top = price_to_y(ob.high)
        y_bottom = price_to_y(ob.low)
        # Create an overlay for transparency
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        box_color = (38, 166, 154, 70) if ob.ob_type == "BULLISH" else (239, 83, 80, 70)
        border_color = (38, 166, 154, 200) if ob.ob_type == "BULLISH" else (239, 83, 80, 200)
        draw_ov.rectangle([(margin_left, y_top), (width - margin_right, y_bottom)], fill=box_color, outline=border_color, width=2)
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)
        draw.text((margin_left + 15, y_top + 4), f"Valid {ob.ob_type} OB", fill=(220, 220, 230, 255))

    # Draw SL and TP lines
    if sl:
        y_sl = price_to_y(sl)
        draw.line([(margin_left, y_sl), (width - margin_right, y_sl)], fill=(255, 75, 75, 230), width=2)
        draw.text((width - margin_right + 8, y_sl - 7), f"SL {sl:.5f}", fill=(255, 80, 80, 255))
    if tp:
        y_tp = price_to_y(tp)
        draw.line([(margin_left, y_tp), (width - margin_right, y_tp)], fill=(40, 200, 120, 230), width=2)
        draw.text((width - margin_right + 8, y_tp - 7), f"TP {tp:.5f}", fill=(50, 220, 130, 255))

    # Draw Candlesticks
    for i in range(n):
        c = candles.iloc[i]
        x_center = margin_left + i * step + step / 2
        y_open = price_to_y(c['open'])
        y_close = price_to_y(c['close'])
        y_high = price_to_y(c['high'])
        y_low = price_to_y(c['low'])

        is_bullish = c['close'] >= c['open']
        color = (38, 166, 154, 255) if is_bullish else (239, 83, 80, 255)

        # Draw Wick
        draw.line([(x_center, y_high), (x_center, y_low)], fill=color, width=1)

        # Draw Body
        y_box_top = min(y_open, y_close)
        y_box_bottom = max(y_open, y_close)
        if y_box_bottom - y_box_top < 1:
            y_box_bottom = y_box_top + 1
        draw.rectangle([(x_center - candle_w / 2, y_box_top), (x_center + candle_w / 2, y_box_bottom)], fill=color)

    # Title header
    draw.text((margin_left, 18), f"{symbol} • {timeframe} • SMC PRICE ACTION SETUP", fill=(240, 240, 245, 255))
    draw.text((width - margin_right - 140, 18), "Trading Bot Alert", fill=(120, 130, 150, 255))

    # Save to file
    img = img.convert("RGB")
    img.save(output_path, "PNG")
    return output_path
