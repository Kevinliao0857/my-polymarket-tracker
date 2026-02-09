import re
import pandas as pd
from datetime import datetime
from typing import Dict, Any
from .data import get_market_enddate
from .config import EST

def get_status_hybrid(item: Dict[str, Any], now_ts: int) -> str:
    """🟢 Hybrid: API → Range parsing → Single time → Duration fallback"""
    # 1. API first (unchanged)
    condition_id = str(item.get('conditionId') or item.get('marketId') or '')
    slug = str(item.get('slug') or '')
    end_str = get_market_enddate(condition_id, slug)
    now_est = datetime.fromtimestamp(now_ts, EST)
    now_decimal = now_est.hour + (now_est.minute / 60.0)
    
    if end_str:
        try:
            end_dt = pd.to_datetime(end_str).tz_convert(EST)
            if now_est >= end_dt:
                return "⚫ EXPIRED"
            return f"🟢 ACTIVE (til {end_dt.strftime('%I:%M %p ET')}) 🟢"
        except:
            pass
    
    title = str(item.get('title') or item.get('question') or '').lower()
    
    # 2. 👇 RANGE PARSING FIRST: "6:00PM-6:15PM" or "6PM-7PM"
    range_match = re.search(r'(\d{1,2}:?\d{2}?[ap]m)\s*-\s*(\d{1,2}:?\d{2}?[ap]m)', title)
    if range_match:
        start_str, end_str = range_match.groups()
        start_h = parse_time_to_decimal(start_str)
        end_h = parse_time_to_decimal(end_str)
        if start_h is not None and end_h is not None:
            if now_decimal >= start_h and now_decimal < end_h:
                return f"🟢 ACTIVE (til ~{format_display_time(end_h)})"
            return "⚫ EXPIRED"
    
    # 3. Single time → implicit 1h window: "6PM ET" = 6-7PM
    time_match = re.search(r'(\d{1,2}:?\d{2}?[ap]m)', title)
    if time_match:
        start_h = parse_time_to_decimal(time_match.group(1))
        if start_h is not None:
            end_h = start_h + 1.0  # 1 hour window
            if now_decimal >= start_h and now_decimal < end_h:
                return f"🟢 ACTIVE (til ~{format_display_time(end_h)})"
            return "⚫ EXPIRED"
    
    # 4. Duration fallback (1h, 30m)
    dur_match = re.search(r'(\d+)\s*(h|hr|m|min)', title)
    if dur_match:
        val = int(dur_match.group(1))
        unit = dur_match.group(2).lower()
        expiry_h = now_decimal + (val if unit.startswith('h') else val/60.0)
        if now_decimal < expiry_h:
            return f"🟢 ACTIVE (til ~{format_display_time(expiry_h)})"
        return "⚫ EXPIRED"
    
    return "🟢 ACTIVE (no timer)"

def parse_time_to_decimal(time_str: str) -> float | None:
    """Convert '6PM' or '6:15PM' → decimal hour (18.25)"""
    time_str = time_str.lower().replace('et', '')
    match = re.match(r'(\d{1,2})(?::(\d{2}))?([ap]m)', time_str)
    if not match:
        return None
    
    h_str, m_str, ampm = match.groups()
    hour = int(h_str)
    minute = int(m_str) if m_str else 0
    
    if 'pm' in ampm and hour != 12:
        hour += 12
    elif 'am' in ampm and hour == 12:
        hour = 0
    
    return hour + (minute / 60.0)

def format_display_time(decimal_h: float) -> str:
    """16.25 → '4:15 PM'"""
    hour = int(decimal_h % 12) or 12
    minute = int((decimal_h % 1) * 60)
    ampm = 'PM' if decimal_h >= 12 else 'AM'
    return f"{hour}:{minute:02d} {ampm}" if minute else f"{hour} {ampm}"
