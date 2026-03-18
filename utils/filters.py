import re
import pandas as pd
from typing import Dict, Any
from datetime import datetime, timedelta
from .config import TICKERS, FULL_NAMES, EST  # ✅ Added EST


def is_crypto(item: Dict[str, Any]) -> bool:
    title = str(item.get('title') or item.get('question') or '').lower()
    return any(t in title for t in TICKERS) or any(f in title for f in FULL_NAMES)


def get_up_down(item: Dict[str, Any]) -> str:
    outcome = str(item.get('outcome', '')).lower()
    side = str(item.get('side', '')).lower()

    # Precise Polymarket outcome+side logic
    if outcome and side:
        if outcome == 'up' and side == 'buy':   return "🟢 UP"
        if outcome == 'down' and side == 'buy': return "🔴 DOWN"
        if outcome == 'up' and side == 'sell':  return "🔴 DOWN"
        if outcome == 'down' and side == 'sell':return "🟢 UP"

    # Fallback heuristics — order matters: title keywords before generic yes/buy
    title = str(item.get('title') or item.get('question', '')).lower()
    fields = ['outcome', 'side', 'answer', 'choice', 'direction']
    text = ' '.join(str(item.get(f, '')).lower() for f in fields)

    # Title directional words (checked FIRST — more specific)
    if any(w in title for w in ['above', 'higher', 'rise', 'moon']): return "🟢 UP"
    if any(w in title for w in ['below', 'lower', 'drop', 'crash']): return "🔴 DOWN"

    # Price comparison operators
    if any(p in title for p in ['$', 'usd', 'price']):
        if '>' in title or '>=' in title: return "🟢 UP"
        if '<' in title or '<=' in title: return "🔴 DOWN"

    # Generic field keywords (less specific, checked last)
    if 'yes' in text or 'long' in text:  return "🟢 UP"
    if 'no' in text or 'short' in text:  return "🔴 DOWN"

    # 'up'/'down' as standalone words in title (avoid false match on "setup", "output")
    if re.search(r'\bup\b', title):   return "🟢 UP"
    if re.search(r'\bdown\b', title): return "🔴 DOWN"

    return "➖ ?"


# ✅ Single canonical time-range regex — used by both functions below
_TIME_RANGE_RE = re.compile(
    r'(\d{1,2}:\d{2}\s*[AP]M)\s*[-–]\s*(\d{1,2}:\d{2}\s*[AP]M)',
    re.IGNORECASE
)


def _parse_time_range_minutes(title: str) -> int | None:
    if not title:
        return None

    m = _TIME_RANGE_RE.search(title)
    if not m:
        return None

    # ✅ Strip all spaces before parsing so "10:30 PM" and "10:30PM" both work
    start_str = m.group(1).replace(' ', '').upper()
    end_str = m.group(2).replace(' ', '').upper()

    fmt = "%I:%M%p"
    try:
        start_t = datetime.strptime(start_str, fmt).time()
        end_t = datetime.strptime(end_str, fmt).time()
    except ValueError:
        return None

    start_min = start_t.hour * 60 + start_t.minute
    end_min = end_t.hour * 60 + end_t.minute
    duration = end_min - start_min
    if duration < 0:
        duration += 24 * 60

    return duration

def extract_time_range_minutes(title: str) -> int | None:
    """Public API: returns window duration in minutes, or None."""
    return _parse_time_range_minutes(title)


def is_5m_market(title: str, cutoff: int = 5) -> bool:
    """True if the market's time window is <= cutoff minutes (default 5)."""
    duration = _parse_time_range_minutes(title or "")
    return duration is not None and duration <= cutoff

def filter_5m_markets(pos_df: pd.DataFrame, cutoff: int = 5) -> pd.DataFrame:
    """Remove markets with a 5-minute or less time window."""
    mask = pos_df['Market'].apply(lambda title: is_5m_market(str(title), cutoff=cutoff))
    return pos_df[~mask]