import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime
import pytz
import re

est = pytz.timezone('US/Eastern')

@st.cache_data(ttl=3)
def safe_fetch(url):
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return data[:100]
    except:
        pass
    return []

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
    
    # Better time parsing - handles multiple times
    time_pattern = r'(\d{1,2})(?::\d{2})?\s*(?:am|pm|a\.?m\.?|p\.?m\.?)'
    matches = re.findall(time_pattern, title, re.IGNORECASE)
    title_hours = []
    
    for hour_str, period in matches:
        hour = int(hour_str)
        if 'pm' in period.lower():
            hour = (hour % 12) + 12
        else:
            hour = hour % 12 or 12
        title_hours.append(hour)
    
    # Fallback standalone hours (1-12 → trader PM bias)
    if not title_hours:
        hour_pattern = r'(?<!\d)(\d{1,2})(?!\d)(?!\s*(am|pm))'
        hours = re.findall(hour_pattern, title)
        for h in hours:
            hour = int(h)
            if 1 <= hour <= 12:
                title_hours.append(hour + 12 if hour >= 8 else hour)
    
    if not title_hours:
        return "🟢 ACTIVE (no timer)"
    
    expiry_hour = max(title_hours)
    if now_hour >= expiry_hour:
        return "⚫ EXPIRED"
    
    display_hour = expiry_hour % 12 or 12
    ampm = 'PM' if expiry_hour >= 12 else 'AM'
    return f"🟢 ACTIVE (til ~{display_hour} {ampm} ET)"


def track_0x8dxd():
    trader = "0x8dxd"
    now_ts = int(time.time())
    fifteen_min_ago = now_ts - 900
    
    urls = [
        f"https://data-api.polymarket.com/trades?user={trader}&limit=100",
        f"https://data-api.polymarket.com/positions?user={trader}"
    ]
    
    all_data = []
    seen = set()
    for url in urls:
        raw_data = safe_fetch(url)
        for item in raw_data:
            ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt')
            ts = int(float(ts_field)) if ts_field else now_ts
            if ts >= fifteen_min_ago and is_crypto(item):
                key = str(item.get('title') or item.get('question') or '-')[:100]
                if key not in seen and len(all_data) < 25:
                    seen.add(key)
                    all_data.append(item)
    
    if not all_data:
        return pd.DataFrame()
    
    df_data = []
    for item in all_data:
        updown = get_up_down(item)
        title = str(item.get('title') or item.get('question') or '-')
        short_title = (title[:85] + '...') if len(title) > 90 else title
        
        size_val = float(item.get('size', 0))
        price_val = item.get('curPrice', item.get('price', '-'))
        if isinstance(price_val, (int, float)):
            price_val = f"${price_val:.2f}"
        
        ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt') or now_ts
        ts = int(float(ts_field)) if ts_field else now_ts
        update_str = datetime.fromtimestamp(ts, est).strftime('%I:%M:%S %p ET')
        status_str = get_status(item, now_ts)
        
        row = {
            'Market': short_title,
            'UP/DOWN': updown,
            'Size': f"${size_val:.0f}",
            'Price': price_val,
            'Status': status_str,
            'Updated': update_str
        }
        df_data.append(row)
    
    df = pd.DataFrame(df_data)
    df = df[df['Market'].str.lower().str.contains('btc|eth|sol|xrp|ada|doge|bitcoin|ethereum|solana', na=False, regex=True)]
    
    if df.empty:
        return pd.DataFrame()
    
    return df.sort_values('Updated', ascending=False)
