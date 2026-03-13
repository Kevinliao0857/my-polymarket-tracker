import re
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any
from .data import get_market_enddate
from .config import EST, MONTHS_MAP


# Compiled once at module load — avoids recompiling per call
_RANGE_RE = re.compile(r'(\d{1,2}:?\d{2}?[ap]m)\s*-\s*(\d{1,2}:?\d{2}?[ap]m)')

_DATE_TIME_RE = re.compile(
    r'(?P<month>\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|'
    r'jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b)'
    r'[^\d]*?(?P<day>\d{1,2})(?:st|nd|rd|th|\.|,)?[^\d]*?(?P<time>\d{1,2}(?::?\d{2})?[ap]m)'
)

# Implicit 1hr: has month + time but day is not required (kept separate for +1hr logic)
_IMPLICIT_RE = re.compile(
    r'(?P<month>\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|'
    r'jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b)'
    r'[^\d]*?(?P<start_time>\d{1,2}(?::?\d{2})?[ap]m)'
)

_SINGLE_TIME_RE = re.compile(r'(\d{1,2}:?\d{2}?[ap]m)')
_DURATION_RE = re.compile(r'(\d+)\s*(h|hr|m|min)')


def get_status_hybrid(item: Dict[str, Any], now_ts: int) -> str:
    if isinstance(item, str):
        item = {'conditionId': item, 'marketId': item}

    now_est = datetime.fromtimestamp(now_ts, EST)
    now_decimal = now_est.hour + now_est.minute / 60.0

    # 1. API enddate — most authoritative source
    condition_id = str(item.get('conditionId') or item.get('marketId') or '')
    end_str = get_market_enddate(condition_id, str(item.get('slug') or ''))
    if end_str:
        try:
            end_dt = pd.to_datetime(end_str).tz_convert(EST)
            if now_est < end_dt:
                return f"🟢 ACTIVE (til {end_dt.strftime('%b %d %I:%M %p ET')})"
            return "⚫ EXPIRED"
        except Exception:
            pass

    title = str(item.get('title') or item.get('question') or '').lower()

    # 2. Range: "6pm - 7pm"
    range_match = _RANGE_RE.search(title)
    if range_match:
        start_h = parse_time_to_decimal(range_match.group(1))
        end_h = parse_time_to_decimal(range_match.group(2))
        if start_h is not None and end_h is not None:
            if start_h <= now_decimal < end_h:
                return f"🟢 ACTIVE (til ~{format_display_time(end_h)})"
            return "⚫ EXPIRED"

    # 3. Date + time: "Mar 12 6pm" — try FULL date match FIRST (has day group)
    date_match = _DATE_TIME_RE.search(title)
    if date_match:
        mon = MONTHS_MAP.get(date_match.group('month').lower())
        day_str = date_match.group('day')
        time_str = date_match.group('time')

        if mon and day_str.isdigit():
            day = int(day_str)
            event_hour = parse_time_to_decimal(time_str)
            if event_hour is not None:
                # ✅ Handle year boundary: if month already passed this year, try next year
                year = now_est.year
                try:
                    event_dt = now_est.replace(
                        year=year, month=mon, day=day,
                        hour=int(event_hour),
                        minute=int((event_hour % 1) * 60),
                        second=0, microsecond=0
                    )
                    # If the date is in the past by more than 1 day, try next year
                    if (now_est - event_dt).days > 1:
                        event_dt = event_dt.replace(year=year + 1)
                except ValueError:
                    pass
                else:
                    if now_est < event_dt:
                        return f"🟢 ACTIVE (til {event_dt.strftime('%b %d %I:%M %p ET')})"
                    return "⚫ EXPIRED"

    # 4. Implicit 1hr: "Mar 6pm" (month + time, no day) — fallback after date_match
    implicit_match = _IMPLICIT_RE.search(title)
    if implicit_match:
        start_h = parse_time_to_decimal(implicit_match.group('start_time'))
        if start_h is not None:
            end_h = start_h + 1.0
            if start_h <= now_decimal < end_h:
                return f"🟢 ACTIVE (til ~{format_display_time(end_h)})"
            return "⚫ EXPIRED"

    # 5. Single time — only valid if it hasn't expired today
    time_match = _SINGLE_TIME_RE.search(title)
    if time_match:
        event_hour = parse_time_to_decimal(time_match.group(1))
        if event_hour is not None:
            today_event = now_est.replace(
                hour=int(event_hour),
                minute=int((event_hour % 1) * 60),
                second=0, microsecond=0
            )
            # ✅ Don't wrap to tomorrow — if it's past, it's expired
            if now_est < today_event:
                return f"🟢 ACTIVE (til {today_event.strftime('%b %d %I:%M %p')})"
            return "⚫ EXPIRED"

    # 6. Duration: "30min", "2hr"
    dur_match = _DURATION_RE.search(title)
    if dur_match:
        val = int(dur_match.group(1))
        unit = dur_match.group(2).lower()
        expiry_h = now_decimal + (val if unit.startswith('h') else val / 60.0)
        if now_decimal < expiry_h:
            return f"🟢 ACTIVE (til ~{format_display_time(expiry_h)})"
        return "⚫ EXPIRED"

    # 7. Last resort fallback
    next_hour = int(now_decimal) + 1
    disp_h = int(next_hour % 12) or 12
    ampm = 'PM' if next_hour >= 12 else 'AM'
    return f"🟢 ACTIVE (til ~{disp_h} {ampm})"


def parse_time_to_decimal(time_str: str) -> float | None:
    """'6PM' or '6:15PM' → decimal hour (18.25)"""
    time_str = time_str.lower().replace('et', '').strip()
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
