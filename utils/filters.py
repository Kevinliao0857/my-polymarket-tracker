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
