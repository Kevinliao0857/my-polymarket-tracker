import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time
import pytz  # pip install pytz
import re  # NEW: For time parsing

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

def is_crypto(item):  # Scans entire item for crypto
    text = str(item).lower()
    crypto_symbols = ['btc', 'eth', 'sol', 'xrp', 'ada', 'doge', 'shib', 'link', 'avax', 'matic', 'dot', 'uni']
    return any(sym in text for sym in crypto_symbols) or 'bitcoin' in text or 'ethereum' in text or 'solana' in text

def get_up_down(item):
    # Check all common fields for direction
    fields = ['outcome', 'side', 'answer', 'choice', 'direction']
    text = ' '.join(str(item.get(f, '')).lower() for f in fields)
    title = str(item.get('title', item.get('question', ''))).lower()
    
    # Priority 1: Explicit outcome/side
    if 'yes' in text or 'buy' in text or 'long' in text:
        return "🟢 UP"
    if 'no' in text or 'sell' in text or 'short' in text:
        return "🔴 DOWN"
    
    # Priority 2: Price direction in title
    if any(word in title for word in ['above', 'higher', 'rise', 'up', 'moon']):
        return "🟢 UP"
    if any(word in title for word in ['below', 'lower', 'drop', 'down', 'crash']):
        return "🔴 DOWN"
    
    # Priority 3: Price thresholds (above=UP, below=DOWN)
    price_words = ['$', 'usd', 'price']
    if any(p in title for p in price_words):
        if '>' in title or '>=' in title:
            return "🟢 UP"
        if '<' in title or '<=' in title:
            return "🔴 DOWN"
    
    # Priority 4: Timeframe bets (will reach = direction in title)
    if any(word in title for word in ['1h', 'hour', '15m', 'will']):
        if any(word in title for word in ['yes', 'will', 'reach']):
            return "🟢 UP"
        else:
            return "🔴 DOWN"
    
    return "➖ ?"

def get_status(item, now_ts):
    title = str(item.get('title') or item.get('question') or '').lower()
    
    # Parse common timeframe patterns: "6AM ET", "6am", "6PM", etc.
    time_match = re.search(r'(\d{1,2})(am|pm|am et|pm et)', title)
    if time_match:
        hour = int(time_match.group(1))
        ampm = time_match.group(2).replace(' et', '')
        
        # Convert 12h to 24h
        if 'pm' in ampm and hour != 12:
            hour += 12
        elif 'am' in ampm and hour == 12:
            hour = 0
        
        # Today's date in EST
        today_str = datetime.fromtimestamp(now_ts, est).strftime('%Y-%m-%d')
        try:
            bet_time = est.localize(datetime.strptime(f"{today_str} {hour:02d}:00:00", '%Y-%m-%d %H:%M:%S'))
            bet_unix = int(bet_time.timestamp())
            
            if bet_unix < now_ts:
                return "⚫ EXPIRED"
            return f"🟢 ACTIVE ({bet_time.strftime('%H:%M ET')})"
        except:
            pass
    
    return "🟢 ACTIVE"  # Fallback

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
