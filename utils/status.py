import re
import pandas as pd
from datetime import datetime
from typing import Dict, Any
from .data import get_market_enddate
from .config import EST

def get_status_hybrid(item: Dict[str, Any], now_ts: int) -> str:
    """🟢 Hybrid: API first → Smart regex fallback"""
    # 1. API first (unchanged)
    condition_id = str(item.get('conditionId') or item.get('marketId') or '')
    slug = str(item.get('slug') or '')
    end_str = get_market_enddate(condition_id, slug)
    now_est = datetime.fromtimestamp(now_ts, EST)
    
    if end_str:
        try:
            end_dt = pd.to_datetime(end_str).tz_convert(EST)
            if now_est >= end_dt:
                return "⚫ EXPIRED"
            return f"🟢 ACTIVE (til {end_dt.strftime('%I:%M %p ET')}) 🟢"
        except:
            pass
    
    # 2. Smart Regex - Enhanced for 1h/30m durations
    title_safe = str(item.get('title') or item.get('question') or '').lower()
    now_decimal = now_est.hour + (now_est.minute / 60.0) + (now_est.second / 3600.0)
    
    # Remove explicit duration patterns BEFORE time parsing
    title_clean = re.sub(r'\b\d+[hms]?\b', '', title_safe)
    time_pattern = r'(\d{1,2})(?::(\d{2}))?([ap]m|et)'
    matches = re.findall(time_pattern, title_clean)
    
    title_times = []
    for h_str, m_str, suffix in matches:
        try:
            hour = int(h_str)
            minute = int(m_str) if m_str else 0
            suffix_lower = str(suffix).lower()
            if 'pm' in suffix_lower: 
                hour = (hour % 12) + 12
            elif 'am' in suffix_lower: 
                hour = hour % 12
            if 0 <= hour <= 23 and 0 <= minute < 60:
                decimal_h = hour + (minute / 60.0)
                title_times.append(decimal_h)
        except:
            continue
    
    # 👇 NEW: Handle duration-only titles like "1h", "30m"
    if title_times:
        max_h = max(title_times)
    else:
        # Detect duration in original title_safe
        dur_match = re.search(r'(\d+)\s*(h|hr|hrs|m|min)', title_safe)
        if dur_match:
            val = int(dur_match.group(1))
            unit = dur_match.group(2).lower()
            if unit.startswith('h'):
                max_h = now_decimal + val  # e.g., "1h" → now + 1 hour
            elif unit.startswith('m'):
                max_h = now_decimal + (val / 60.0)  # e.g., "30m" → now + 30 min
            else:
                return "🟢 ACTIVE (no timer)"
        else:
            return "🟢 ACTIVE (no timer)"
    
    if now_decimal >= max_h: 
        return "⚫ EXPIRED"
    
    # Format display time from expiry horizon
    disp_h = int(max_h % 12) or 12
    disp_m = f":{int((max_h % 1)*60):02d}" if (max_h % 1) > 0.1 else ""
    ampm = 'PM' if max_h >= 12 else 'AM'
    return f"🟢 ACTIVE (til ~{disp_h}{disp_m} {ampm})"
