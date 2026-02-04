import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time
import pytz  # pip install pytz

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Tracker - Last 15 Min")

st.info("🟢 Live crypto-only | Last 15min trades/closes | Responsive refresh")

# Live PST clock
pst = pytz.timezone('US/Pacific')
now_pst = datetime.now(pst)
st.caption(f"🕐 Current: {now_pst.strftime('%Y-%m-%d %H:%M:%S %Z')} | Auto 5s + Force 🔄")

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

def is_crypto(market_title):
    title_lower = market_title.lower()
    crypto_symbols = ['btc', 'eth', 'sol', 'xrp', 'ada', 'doge', 'shib', 'link', 'avax', 'matic', 'dot', 'uni']
    return any(sym in title_lower for sym in crypto_symbols) or 'bitcoin' in title_lower or 'ethereum' in title_lower or 'solana' in title_lower

def get_up_down(item):
    outcome = str(item.get('outcome', '')).lower()
    side = str(item.get('side', '')).lower()
    title = str(item.get('title', item.get('question', ''))).lower()
    
    if 'yes' in outcome:
        return "🟢 UP"
    if 'no' in outcome:
        return "🔴 DOWN"
    
    if 'buy' in side:
        return "🟢 UP"
    if 'sell' in side:
        return "🔴 DOWN"
    
    if any(word in title for word in ['1h', 'hour', '15m']):
        if any(word in title for word in ['above']):
            return "🟢 UP"
        if any(word in title for word in ['below']):
            return "🔴 DOWN"
    
    if any(word in title for word in ['yes', 'will', 'above', 'up']):
        return "🟢 UP"
    if any(word in title for word in ['no', 'below', 'down']):
        return "🔴 DOWN"
    
    return "➖ ?"

def track_0x8dxd():
    trader = "0x8dxd"
    now_ts = int(time.time())
    fifteen_min_ago = now_ts - 900  # 15 minutes = 900s
    
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
            ts = int(float(ts_field)) if ts_field else now_ts
            if ts >= fifteen_min_ago:  # Last 15 min
                title = str(item.get('title') or item.get('question') or '-')
                if is_crypto(title):
                    key = title[:100]
                    if key not in seen and len(all_data) < 25:
                        seen.add(key)
                        all_data.append(item)
    
    if not all_data:
        st.info("No crypto activity in last 15 min | Bot quiet?")
        return
    
    df_data = []
    min_ts = now_ts
    for item in all_data:
        updown = get_up_down(item)
        title = str(item.get('title') or item.get('question') or '-')
        short_title = (title[:55] + '...') if len(title) > 60 else title
        
        size_val = float(item.get('size', 0))
        pnl_val = float(item.get('cashPnl', item.get('pnl', 0)))
        price_val = item.get('curPrice', item.get('price', '-'))
        if isinstance(price_val, (int, float)):
            price_val = f"${price_val:.2f}"
        
        ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt') or now_ts
        ts = int(float(ts_field)) if ts_field else now_ts
        min_ts = min(min_ts, ts)
        update_str = datetime.fromtimestamp(ts, pst).strftime('%H:%M:%S')
        
        row = {
            'Market': short_title,
            'UP/DOWN': updown,
            'Size': f"${size_val:.0f}",
            'PnL': f"${pnl_val:.0f}",
            'Price': price_val,
            'Updated': update_str
        }
        df_data.append(row)
    
    df = pd.DataFrame(df_data)
    df = df.sort_values('Updated', ascending=False)
    
    st.success(f"✅ {len(df)} unique crypto bets (last 15min)")
    st.dataframe(df, use_container_width=True, height=400)
    
    up_bets = len(df[df['UP/DOWN'] == '🟢 UP'])
    st.metric("🟢 UP Bets", up_bets)
    st.metric("🔴 DOWN Bets", len(df) - up_bets)
    
    pnl = pd.to_numeric(df['PnL'].str.replace('$',''), errors='coerce').sum()
    st.metric("Total PnL (15m)", f"${pnl:.0f}")
    
    span_min = int((now_ts - min_ts) / 60)
    st.metric("Newest Activity", f"{span_min} min ago")

if st.button("🔄 Force Refresh Now"):
    st.rerun()

# Bulletproof refresh
placeholder = st.empty()
refresh_count = 0
while True:
    refresh_count += 1
    now_pst = datetime.now(pst)
    with placeholder.container():
        track_0x8dxd()
        st.caption(f"🕐 {now_pst.strftime('%H:%M:%S %Z')} | Refresh #{refresh_count} | 5s auto")
    time.sleep(5)
    st.rerun()
