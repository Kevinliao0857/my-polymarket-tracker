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
    
    # 2. Smart Regex - Ignores "1h", "30min", etc.
    title_safe = str(item.get('title') or item.get('question') or '').lower()
    now_decimal = now_est.hour + (now_est.minute / 60.0) + (now_est.second / 3600.0)
    
    # 👇 FIX: Remove duration patterns first
    title_clean = re.sub(r'\b\d+[hms]?\b', '', title_safe)  # Removes "1h", "30m", "2hr"
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
    
    if not title_times: 
        return "🟢 ACTIVE (no timer)"
    
    max_h = max(title_times)
    if now_decimal >= max_h: 
        return "⚫ EXPIRED"
    
    disp_h = int(max_h % 12) or 12
    disp_m = f":{int((max_h % 1)*60):02d}" if (max_h % 1) > 0.1 else ""
    ampm = 'PM' if max_h >= 12 else 'AM'
    return f"🟢 ACTIVE (til ~{disp_h}{disp_m} {ampm})"
