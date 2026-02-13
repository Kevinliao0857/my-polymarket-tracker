import re
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any
from .data import get_market_enddate
from .config import EST, MONTHS_MAP


def get_status_hybrid(item: Dict[str, Any], now_ts: int) -> str:
    now_est = datetime.fromtimestamp(now_ts, EST)
    now_decimal = now_est.hour + now_est.minute / 60.0
    
    # 1. API enddate (full date)
    condition_id = str(item.get('conditionId') or item.get('marketId') or '')
    end_str = get_market_enddate(condition_id, str(item.get('slug') or ''))
    if end_str:
        try:
            end_dt = pd.to_datetime(end_str).tz_convert(EST)
            if now_est < end_dt:
                return f"🟢 ACTIVE (til {end_dt.strftime('%b %d %I:%M %p ET')})"
            return "⚫ EXPIRED"
        except: pass
    
    title = str(item.get('title') or item.get('question') or '').lower()
    
    # 2. RANGE: "6PM-7PM"
    range_match = re.search(r'(\d{1,2}:?\d{2}?[ap]m)\s*-\s*(\d{1,2}:?\d{2}?[ap]m)', title)
    if range_match:
        start_str, end_str = range_match.groups()
        start_h = parse_time_to_decimal(start_str)
        end_h = parse_time_to_decimal(end_str)
        if start_h and end_h:
            if now_decimal >= start_h and now_decimal < end_h:
                return f"🟢 ACTIVE (til ~{format_display_time(end_h)})"
            return "⚫ EXPIRED"
    
    # 2.5 DATE + TIME: "Feb 12 3AM" / "February 12 3AM"
    date_match = re.search(
        r'\b('
        r'jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|'
        r'jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?'
        r')\s+(\d{1,2})\s+(\d{1,2}(?::?\d{2})?[ap]m)',
        title
    )
    if date_match:
        mon_str = date_match.group(1).lower()
        day_str = date_match.group(2)
        time_str = date_match.group(3)
        
        mon = MONTHS_MAP.get(mon_str)
        if mon is not None and day_str and time_str:
            day = int(day_str)
            event_hour = parse_time_to_decimal(time_str)
            if event_hour is not None:
                event_dt = now_est.replace(
                    month=mon, day=day,
                    hour=int(event_hour),
                    minute=int((event_hour % 1) * 60),
                    second=0, microsecond=0
                )
                
                if now_est < event_dt:
                    return f"🟢 ACTIVE (til {event_dt.strftime('%b %d %I:%M %p ET')})"
                return "⚫ EXPIRED"
    
    # 3. SINGLE TIME → Next occurrence
    time_match = re.search(r'(\d{1,2}:?\d{2}?[ap]m)', title)
    if time_match:
        event_hour = parse_time_to_decimal(time_match.group(1))
        if event_hour is not None:
            today_event = now_est.replace(hour=int(event_hour), 
                                        minute=int((event_hour%1)*60), 
                                        second=0, microsecond=0)
            if now_est > today_event:
                today_event += timedelta(days=1)
            if now_est < today_event:
                return f"🟢 ACTIVE (til {today_event.strftime('%b %d %I:%M %p')})"
            return "⚫ EXPIRED"
    
    # 4. Duration fallback
    dur_match = re.search(r'(\d+)\s*(h|hr|m|min)', title)
    if dur_match:
        val = int(dur_match.group(1))
        unit = dur_match.group(2).lower()
        expiry_h = now_decimal + (val if unit.startswith('h') else val/60.0)
        if now_decimal < expiry_h:
            return f"🟢 ACTIVE (til ~{format_display_time(expiry_h)})"
        return "⚫ EXPIRED"
    
    # 5. Next hour fallback
    next_hour = int(now_decimal + 1)
    disp_h = int(next_hour % 12) or 12
    ampm = 'PM' if next_hour >= 12 else 'AM'
    return f"🟢 ACTIVE (til ~{disp_h} {ampm})"


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
