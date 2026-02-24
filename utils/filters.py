from typing import Dict, Any
from .config import TICKERS, FULL_NAMES
import re


def is_crypto(item: Dict[str, Any]) -> bool:
    title = str(item.get('title') or item.get('question') or '').lower()
    return any(t in title for t in TICKERS) or any(f in title for f in FULL_NAMES)


def get_up_down(item: Dict[str, Any]) -> str:
    # Precise Polymarket logic first (outcome + side → true bet direction)
    outcome = str(item.get('outcome', '')).lower()
    side = str(item.get('side', '')).lower()
    
    if outcome == 'up' and side == 'buy':
        return "🟢 UP"  # Betting up
    elif outcome == 'down' and side == 'buy':
        return "🔴 DOWN"  # Betting down
    elif outcome == 'up' and side == 'sell':
        return "🔴 DOWN"  # Betting down (selling Up shares)
    elif outcome == 'down' and side == 'sell':
        return "🟢 UP"  # Betting up (selling Down shares)
    
    # Fallback: Original heuristics for other sources/markets
    fields = ['outcome', 'side', 'answer', 'choice', 'direction']
    text = ' '.join(str(item.get(f, '')).lower() for f in fields)
    title = str(item.get('title', item.get('question', ''))).lower()
    
    if 'yes' in text or 'buy' in text or 'long' in text: return "🟢 UP"
    if 'no' in text or 'sell' in text or 'short' in text: return "🔴 DOWN"
    
    if any(word in title for word in ['above', 'higher', 'rise', 'up', 'moon']): return "🟢 UP"
    if any(word in title for word in ['below', 'lower', 'drop', 'down', 'crash']): return "🔴 DOWN"
    
    price_words = ['$', 'usd', 'price']
    if any(p in title for p in price_words):
        if '>' in title or '>=' in title: return "🟢 UP"
        if '<' in title or '<=' in title: return "🔴 DOWN"
    
    if any(word in title for word in ['1h', 'hour', '15m', 'will']):
        if any(word in title for word in ['yes', 'will', 'reach']): return "🟢 UP"
        else: return "🔴 DOWN"
    
    return "➖ ?"

# NEW: pattern like "5:40AM-5:45AM" or "5:40 AM - 5:45 AM"
_TIME_RANGE_PATTERN = re.compile(
    r'(\d{1,2}:\d{2}\s?(?:AM|PM))\s*[-–]\s*(\d{1,2}:\d{2}\s?(?:AM|PM))',
    re.IGNORECASE,
)


def extract_time_range_minutes(title: str) -> int | None:
    """
    Parse a 'HH:MM AM - HH:MM AM' (or PM) style window from the title and
    return its duration in minutes. Returns None if not present or parse fails.
    """
    if not title:
        return None

    m = _TIME_RANGE_PATTERN.search(title)
    if not m:
        return None

    start_str, end_str = m.group(1).upper(), m.group(2).upper()
    fmt = "%I:%M %p"

    try:
        today = datetime.now(EST).date()
        start_dt = datetime.strptime(start_str, fmt).replace(
            year=today.year, month=today.month, day=today.day, tzinfo=EST
        )
        end_dt = datetime.strptime(end_str, fmt).replace(
            year=today.year, month=today.month, day=today.day, tzinfo=EST
        )
        # handle wrap around, e.g. 11:55PM-12:00AM
        if end_dt < start_dt:
            end_dt = end_dt + timedelta(days=1)
        return int((end_dt - start_dt).total_seconds() // 60)
    except Exception:
        return None


def is_5m_market(title: str, cutoff: int = 5) -> bool:
    """
    Return True if the market title looks like a <=5-minute window market.
    """
    dur = extract_time_range_minutes(title or "")
    return dur is not None and dur <= cutoff