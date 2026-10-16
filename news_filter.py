import os
import time
import requests
from datetime import datetime, timezone

class NewsShield:
    """
    Dual-Layer Institutional News & Volatility Shield:
    1. Layer 1: Scheduled High-Impact Red-Folder Economic Calendar (Forex Factory API).
       Pauses new entries 30 mins BEFORE and 30 mins AFTER high-impact USD events.
    2. Layer 2: Unscheduled Flash Volatility & Spread Spike Guard (Geopolitical/Breaking News).
       Detects abnormal spread blowouts or 2.5x ATR candle spikes and freezes new entries for 15 mins.
    """
    def __init__(self, pre_mins: int = 30, post_mins: int = 30, shock_mult: float = 2.5):
        self.pre_mins = pre_mins
        self.post_mins = post_mins
        self.shock_mult = shock_mult
        
        self.events = []
        self.last_fetch_time = 0
        self.shock_until = 0
        self.shock_reason = ""
        self.last_alert_msg = ""
        self.last_alert_time = 0

    def fetch_calendar(self):
        """Fetch weekly calendar from Forex Factory once every hour."""
        now = time.time()
        if now - self.last_fetch_time < 3600 and self.events:
            return
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                self.events = r.json()
                self.last_fetch_time = now
        except Exception as e:
            print(f"[WARNING] News calendar fetch failed: {e}")

    def check_scheduled_news(self):
        """Check if currently within the +/- 30 min window of high-impact USD news."""
        self.fetch_calendar()
        if not self.events:
            return False, ""

        now = datetime.now(timezone.utc)
        for e in self.events:
            if e.get("country") == "USD" and e.get("impact") == "High":
                dt_str = e.get("date")
                if not dt_str:
                    continue
                try:
                    event_dt = datetime.fromisoformat(dt_str)
                    diff_mins = (event_dt - now).total_seconds() / 60.0
                    title = e.get("title", "High-Impact USD News")

                    if -self.post_mins <= diff_mins <= self.pre_mins:
                        if diff_mins > 0:
                            return True, f"High-Impact News in {int(diff_mins)}m: [{title}]"
                        else:
                            return True, f"Recent High-Impact News ({int(abs(diff_mins))}m ago): [{title}]"
                except Exception:
                    pass
        return False, ""

    def check_unexpected_shock(self, symbol: str = "XAUUSD", candle_range: float = 0.0, atr: float = 0.0, spread_cash: float = 0.0):
        """Check for unscheduled breaking news, spread blowouts, or flash volatility spikes."""
        now = time.time()
        if now < self.shock_until:
            rem_mins = max(1, int((self.shock_until - now) / 60))
            return True, f"Flash Volatility Shield Active ({rem_mins}m remaining): {self.shock_reason}"

        # 1. Spread blowout thresholds in dollars
        max_spreads = {
            "XAUUSD": 0.50,   # $0.50 (normal is ~$0.17)
            "BTCUSD": 15.0,   # $15.0 (normal is ~$4.50)
            "USTEC": 3.0      # $3.0 (normal is ~$0.78)
        }
        max_allowed = max_spreads.get(symbol, 0.50)
        if spread_cash > max_allowed:
            self.shock_until = now + (15 * 60)
            self.shock_reason = f"Abnormal Broker Spread Spike (${spread_cash:.2f} > ${max_allowed:.2f})"
            return True, self.shock_reason

        # 2. Violent candle range expansion (2.5x ATR)
        if atr > 0 and (candle_range / atr) >= self.shock_mult:
            self.shock_until = now + (15 * 60)
            self.shock_reason = f"Sudden Volatility Spike ({candle_range / atr:.1f}x ATR)"
            return True, self.shock_reason

        return False, ""

    def is_safe_to_trade(self, symbol: str = "XAUUSD", candle_range: float = 0.0, atr: float = 0.0, spread_cash: float = 0.0):
        """
        Main gatekeeper: Returns (is_safe: bool, status_message: str).
        Blocks new entries if scheduled red-folder news or unexpected volatility shock is active.
        """
        # 1. Check Scheduled News
        is_news, news_msg = self.check_scheduled_news()
        if is_news:
            return False, news_msg

        # 2. Check Unexpected Shock
        is_shock, shock_msg = self.check_unexpected_shock(symbol, candle_range, atr, spread_cash)
        if is_shock:
            return False, shock_msg

        return True, "Market Clear (Safe)"

    def should_send_alert(self, reason: str) -> bool:
        """Throttle Telegram alert to avoid spamming every cycle."""
        now = time.time()
        if reason != self.last_alert_msg or (now - self.last_alert_time) > 900:
            self.last_alert_msg = reason
            self.last_alert_time = now
            return True
        return False
