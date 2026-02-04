import re
from datetime import datetime
import pytz

est = pytz.timezone('US/Eastern')

def is_crypto(item):
    title = str(item.get('title') or item.get('question') or '').lower()
    tickers = ['btc', 'eth', 'sol', 'xrp', 'ada', 'doge', 'shib', 'link', 'avax', 'matic', 'dot', 'uni', 'bnb', 'usdt', 'usdc']
    full_names = ['bitcoin', 'ethereum', 'solana', 'ripple', 'xrp', 'cardano', 'dogecoin', 'shiba', 'chainlink', 'avalanche', 'polygon', 'polkadot', 'uniswap', 'binance coin']
    return any(t in title for t in tickers) or any(f in title for f in full_names)

def get_up_down(item):
    fields = ['outcome', 'side', 'answer', 'choice', 'direction']
    text = ' '.join(str(item.get(f, '')).lower() for f in fields)
    title = str(item.get('title', item.get('question', ''))).lower()
    
    if 'yes' in text or 'buy' in text or 'long' in text:
        return "🟢 UP"
    if 'no' in text or 'sell' in text or 'short' in text:
        return "🔴 DOWN"
    
    if any(word in title for word in ['above', 'higher', 'rise', 'up', 'moon']):
        return "🟢 UP"
    if any(word in title for word in ['below', 'lower', 'drop', 'down', 'crash']):
        return "🔴 DOWN"
    
    price_words = ['$', 'usd', 'price']
    if any(p in title for p in price_words):
        if '>' in title or '>=' in title:
            return "🟢 UP"
        if '<' in title or '<=' in title:
            return "🔴 DOWN"
    
    if any(word in title for word in ['1h', 'hour', '15m', 'will']):
        if any(word in title for word in ['yes', 'will', 'reach']):
            return "🟢 UP"
        else:
            return "🔴 DOWN"
    
    return "➖ ?"

def get_status(item, now_ts):
    title = str(item.get('title') or item.get('question') or '').lower()
    now_hour = datetime.fromtimestamp(now_ts, est).hour
    
    time_pattern = r'(\d{1,2})(?::\d{2})?\s*(am|pm|a\.?m\.?|p\.?m\.?)'
    explicit_matches = re.findall(time_pattern, title)
    title_hours = []
    
    for hour_str, period in explicit_matches:
        hour = int(hour_str)
        if period.lower() in ['pm', 'p.m.', 'p.m']:
            hour = hour % 12 + 12
        else:
            hour = hour % 12 or 12
        if 0 <= hour <= 23:
            title_hours.append(hour)
    
    if not title_hours:
        hour_matches = re.findall(r'\b(\d{1,2})\b', title)
        for hour_str in hour_matches:
            hour = int(hour_str)
            if 1 <= hour <= 12:
                assumed_hour = hour + 12 if hour >= 8 else hour
                title_hours.append(assumed_hour)
    
    if not title_hours:
        return "🟢 ACTIVE (no timer)"
    
    max_title_hour = max(title_hours)
    if now_hour >= max_title_hour:
        return "⚫ EXPIRED"
    
    display_hour = max_title_hour % 12 or 12
    ampm = 'AM' if max_title_hour < 12 else 'PM'
    return f"🟢 ACTIVE (til ~{display_hour} {ampm} ET)"
