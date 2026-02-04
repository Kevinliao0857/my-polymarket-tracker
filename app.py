import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Tracker - Last 1 Hour")

st.info("🟢 Live crypto-only | Last 1h trades/closes | Enhanced UP/DOWN")

@st.cache_data(ttl=5)
def safe_fetch(url):
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return data[:100]  # More for filtering
    except:
        pass
    return []

def is_crypto(market_title):
    title_lower = market_title.lower()
    crypto_symbols = ['btc', 'eth', 'sol', 'xrp', 'ada', 'doge', 'shib', 'link', 'avax', 'matic', 'dot', 'uni']
    return any(sym in title_lower for sym in crypto_symbols) or any(phrase in title_lower for phrase in ['bitcoin', 'ethereum', 'solana'])

def get_up_down(item):
    outcome = str(item.get('outcome', '')).lower()
    side = str(item.get('side', '')).lower()
    title = str(item.get('title', item.get('question', ''))).lower()
    
    # Outcome first (positions)
    if 'yes' in outcome:
        return "🟢 UP"
    if 'no' in outcome:
        return "🔴 DOWN"
    
    # Side + context (trades)
    if 'buy' in side:
        if any(word in title for word in ['above', 'up']):
            return "🟢 UP"
        return "🟢 UP"  # Default bullish
    if 'sell' in side:
        if any(word in title for word in ['below', 'down']):
            return "🔴 DOWN"
        return "🔴 DOWN"  # Default bearish
    
    # Title fallback
    if any(word in title for word in ['yes', 'will', 'above', 'up']):
        return "🟢 UP"
    if any(word in title for word in ['no', 'below', 'down']):
        return "🔴 DOWN"
    
    return "➖ ?"

def track_0x8dxd():
    trader = "0x8dxd"
    now_ts = int(time.time())
    hour_ago = now_ts - 3600  # 1 hour
    
    urls = [
        f"https://data-api.polymarket.com/trades?user={trader}&limit=100",
        f"https://data-api.polymarket.com/closed-positions?user={trader}&limit=50",
        f"https://data-api.polymarket.com/positions?user={trader}"
    ]
    
    all_data = []
    seen = set()
    for url in urls:
        raw_data = safe_fetch(url)
        for item in raw_data:
            ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt')
            ts = int(ts_field) if ts_field and isinstance(ts_field, (str, int, float)) else 0
            if ts >= hour_ago:
                title = str(item.get('title') or item.get('question') or '-')
                if is_crypto(title):
                    key = f"{title[:80]}_{ts}"
                    if key not in seen:
                        seen.add(key)
                        all_data.append(item)
    
    if not all_data:
        st.info("No crypto trades/positions in last hour | Check later")
        return
    
    df_data = []
    min_ts = now_ts
    for item in all_data:
        updown = get_up_down(item)
        title = str(item.get('title') or item.get('question') or '-')
        short_title = (title[:57] + '...') if len(title) > 60 else title
        
        size_val = float(item.get('size', 0))
        pnl_val = float(item.get('cashPnl', item.get('pnl', 0)))
        price_val = item.get('curPrice', item.get('price', '-'))
        if isinstance(price_val, (int, float)):
            price_val = f"${price_val:.2f}"
        
        ts_field = item.get('timestamp') or item.get('updatedAt') or now_ts
        ts = int(ts_field) if ts_field else now_ts
        min_ts = min(min_ts, ts)
        
        row = {
            'Market': short_title,
            'UP/DOWN': updown,
            'Size': f"${size_val:.0f}",
            'PnL': f"${pnl_val:.0f}",
            'Price': price_val,
            'Updated': datetime.fromtimestamp(ts).strftime('%H:%M:%S')
        }
        df_data.append(row)
    
    df = pd.DataFrame(df_data)
    df = df.sort_values('Updated', ascending=False)
    
    st.success(f"✅ {len(df)} unique crypto bets (last 1h)")
    st.dataframe(df, use_container_width=True)
    
    up_bets = len(df[df['UP/DOWN'] == '🟢 UP'])
    st.metric("🟢 UP Bets", up_bets)
    st.metric("🔴 DOWN Bets", len(df) - up_bets)
    
    pnl = pd.to_numeric(df['PnL'].str.replace('$',''), errors='coerce').sum()
    st.metric("Total PnL (1h)", f"${pnl:.0f}")
    
    span_min = int((now_ts - min_ts) / 60)
    st.metric("Activity Span", f"{span_min} min ago")

# Refresh loop
placeholder = st.empty()
while True:
    with placeholder.container():
        track_0x8dxd()
        st.caption("5s refresh | Last 1h crypto trades/closes")
    time.sleep(5)
    st.rerun()
