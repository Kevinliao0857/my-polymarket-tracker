import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time
import pytz  # pip install pytz
import re  # For time parsing

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Tracker - Last 15 Min")

st.info("🟢 Live crypto-only | UP/DOWN focus | Last 15min")

# Live EST clock (trader uses EST)
est = pytz.timezone('US/Eastern')
now_est = datetime.now(est)
st.caption(f"🕐 Current EST: {now_est.strftime('%Y-%m-%d %H:%M:%S %Z')} | Auto 5s + Force 🔄")

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
    title = str(item.get('title') or item.get('question') or '').lower()  # TITLE ONLY
    tickers = ['btc', 'eth', 'sol', 'xrp', 'ada', 'doge', 'shib', 'link', 'avax', 'matic', 'dot', 'uni', 'bnb', 'usdt', 'usdc']
    full_names = ['bitcoin', 'ethereum', 'solana', 'ripple', 'xrp', 'cardano', 'dogecoin', 'shiba', 'chainlink', 'avalanche', 'polygon', 'polkadot', 'uniswap', 'binance coin']
    
    # STRICT: Must contain ticker OR full name in TITLE (no 'crypto' wildcard, no full item text)
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
    now_hour = datetime.fromtimestamp(now_ts, est).hour  # 0-23 EST
    
    # Improved regex: handles "5pm", "5:30pm", "5:30PM-5:45PM ET"
    time_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(a\.?m?\.?|p\.?m?\.?)'
    explicit_matches = re.findall(time_pattern, title)
    title_times = []  # Store (hour, minute) tuples
    
    for h_str, m_str, period in explicit_matches:
        hour = int(h_str)
        minute = int(m_str) if m_str else 0
        period = period.replace('.', '').lower()
        
        if period in ['am', 'a.m']:
            hour = hour % 12
            if hour == 0: hour = 12  # 12AM = 0, but rare for trades
        elif period in ['pm', 'p.m']:
            hour = (hour % 12) + 12
        else:
            continue  # Skip invalid periods
        
        # Convert to decimal hour for precision (e.g., 17.5 for 5:30PM)
        decimal_hour = hour + (minute / 60.0)
        title_times.append(decimal_hour)
    
    if not title_times:
        # Tighter fallback: only 1-12 near time words, no prices/symbols
        fallback_pattern = r'\b(\d{1,2})\s*(?:pm|am|et)\b'
        fallback_matches = re.findall(fallback_pattern, title)
        for h_str in fallback_matches:
            hour = int(h_str)
            if 1 <= hour <= 12:
                # Assume PM for trader hours (post-8AM)
                title_times.append(hour + 12 if hour >= 8 else hour)
    
    if not title_times:
        return "🟢 ACTIVE (no timer)"
    
    # Use MAX (latest end time) for expiration check
    max_decimal = max(title_times)
    max_hour = int(max_decimal)  # Floor for hour-only compare
    
    if now_hour >= max_hour:
        return "⚫ EXPIRED"
    
    # Display latest time in 12h format
    display_hour = int(max_decimal % 12) or 12
    display_min = int((max_decimal % 1) * 60)
    min_str = f":{display_min:02d}" if display_min > 0 else ""
    ampm = 'AM' if max_decimal < 12 else 'PM'
    return f"🟢 ACTIVE (til ~{display_hour}{min_str} {ampm} ET)"


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
        st.info("No crypto activity in last 15 min")
        return
    
    df_data = []
    min_ts = now_ts
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
        min_ts = min(min_ts, ts)
        update_str = datetime.fromtimestamp(ts, est).strftime('%I:%M:%S %p ET')  # 12h format
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
    
    # STRICT FINAL FILTER: Only perfect crypto titles
    df = df[df['Market'].str.lower().str.contains('btc|eth|sol|xrp|ada|doge|bitcoin|ethereum|solana', na=False, regex=True)]
    
    if df.empty:
        st.info("No qualifying crypto bets in last 15 min")
        return
    
    df = df.sort_values('Updated', ascending=False)
    
    st.success(f"✅ {len(df)} crypto bets (15min ET)")
    st.dataframe(df, use_container_width=True, height=500, column_config={
        "Market": st.column_config.TextColumn("Market", width="medium"),
        "Status": st.column_config.TextColumn("Status", width="medium")
    })
    
    up_bets = len(df[df['UP/DOWN'] == '🟢 UP'])
    st.metric("🟢 UP Bets", up_bets)
    st.metric("🔴 DOWN Bets", len(df) - up_bets)
    
    span_min = int((now_ts - min_ts) / 60)
    st.metric("Newest", f"{span_min} min ago (ET)")

if st.button("🔄 Force Refresh"):
    st.rerun()

# Refresh loop
placeholder = st.empty()
refresh_count = 0
while True:
    refresh_count += 1
    now_est = datetime.now(est)
    with placeholder.container():
        track_0x8dxd()
        st.caption(f"🕐 {now_est.strftime('%H:%M:%S ET')} | #{refresh_count}")
    time.sleep(5)
    st.rerun()