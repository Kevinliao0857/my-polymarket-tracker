import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time
import pytz
import re
from streamlit_autorefresh import st_autorefresh  # NEW: Perfect live refresh

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Tracker - Last 15 Min")

st.info("🟢 Live crypto-only | UP/DOWN focus | Last 15min")

# Live EST clock
est = pytz.timezone('US/Eastern')

# AUTO-REFRESH EVERY 3s (ticks visibly!)
count = st_autorefresh(interval=3000, limit=None, key="live_tracker")  # Infinite 3s ticks!

@st.cache_data(ttl=1)
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
    text = str(item).lower()
    crypto_symbols = ['btc', 'eth', 'sol', 'xrp', 'ada', 'doge', 'shib', 'link', 'avax', 'matic', 'dot', 'uni', 'bnb', 'trx']
    return any(sym in text for sym in crypto_symbols) or 'bitcoin' in text or 'ethereum' in text or 'solana' in text

def get_up_down(item):
    fields = ['outcome', 'side', 'answer', 'choice', 'direction']
    text = ' '.join(str(item.get(f, '')).lower() for f in fields)
    title = str(item.get('title', item.get('question', ''))).lower()
    
    if 'yes' in text or 'buy' in text or 'long' in text:
        return "🟢 UP"
    if 'no' in text or 'sell' in text or 'short' in text:
        return "🔴 DOWN"
    
    if any(word in title for word in ['above', 'higher', 'rise', 'up']):
        return "🟢 UP"
    if any(word in title for word in ['below', 'lower', 'drop', 'down']):
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
        return "🔴 DOWN"
    
    return "➖ ?"

def get_status(item, now_ts):
    title = str(item.get('title') or item.get('question') or '')
    now_hour = datetime.fromtimestamp(now_ts, est).hour
    
    hour_matches = re.findall(r'\b(\d{1,2})\b', title)  # FIXED REGEX
    title_hours = []
    
    for hour_str in hour_matches:
        hour = int(hour_str)
        if 1 <= hour <= 12:
            if hour <= 6:
                title_hours.append(hour)
            else:
                title_hours.append(hour + 12 if hour != 12 else 12)
    
    if not title_hours:
        return "🟢 ACTIVE (no timer)"
    
    max_title_hour = max(title_hours)
    if now_hour > max_title_hour:
        return "⚫ EXPIRED"
    
    return f"🟢 ACTIVE (til ~{max(title_hours):02d}:00 ET)"

@st.cache_data(ttl=3)
def track_0x8dxd():
    trader = "0x8dxd"
    now_ts = int(time.time())
    fifteen_min_ago = now_ts - 900
    
    urls = [
        f"https://data-api.polymarket.com/trades?user={trader}&limit=50&from={fifteen_min_ago}",
        f"https://data-api.polymarket.com/positions?user={trader}&limit=50&from={fifteen_min_ago}"
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
        st.metric("Refresh Count", f"#{count}")
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
        update_str = datetime.fromtimestamp(ts, est).strftime('%H:%M:%S ET')
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
    df = df.sort_values('Updated', ascending=False)
    
    st.success(f"✅ {len(df)} crypto bets (15min ET)")
    st.dataframe(df, use_container_width=True, height=500, column_config={
        "Market": st.column_config.TextColumn("Market", width="medium"),
        "Status": st.column_config.TextColumn("Status", width="small")
    })
    
    up_bets = len(df[df['UP/DOWN'] == '🟢 UP'])
    col1, col2, col3 = st.columns(3)
    col1.metric("🟢 UP Bets", up_bets)
    col2.metric("🔴 DOWN Bets", len(df) - up_bets)
    span_min = int((now_ts - min_ts) / 60)
    col3.metric("Refresh", f"#{count}")

now_est = datetime.now(est)
st.caption(f"🕐 {now_est.strftime('%H:%M:%S ET')} | Auto-refresh: 3s | PST+3h | All fixes applied")
