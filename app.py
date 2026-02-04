import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time
import pytz  # pip install pytz

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Tracker - Last 15 Min")

st.info("🟢 Live crypto-only | UP/DOWN focus | Last 15min")

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
    fifteen_min_ago = now_ts - 900
    
    # 1. LIVE BETS TABLE (your original logic)
    urls_bets = [
        f"https://data-api.polymarket.com/trades?user={trader}&limit=100",
        f"https://data-api.polymarket.com/positions?user={trader}"
    ]
    
    all_bets = []
    seen_bets = set()
    for url in urls_bets:
        raw_data = safe_fetch(url)
        for item in raw_data:
            ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt')
            ts = int(float(ts_field)) if ts_field else now_ts
            if ts >= fifteen_min_ago:
                title = str(item.get('title') or item.get('question') or '-')
                if is_crypto(title):
                    key = title[:100]
                    if key not in seen_bets and len(all_bets) < 20:
                        seen_bets.add(key)
                        all_bets.append(item)
    
    # Live bets DF
    bet_df_data = []
    for item in all_bets:
        updown = get_up_down(item)
        title = str(item.get('title') or item.get('question') or '-')
        short_title = (title[:55] + '...') if len(title) > 60 else title
        size_val = float(item.get('size', 0))
        price_val = item.get('curPrice', item.get('price', '-'))
        if isinstance(price_val, (int, float)):
            price_val = f"${price_val:.2f}"
        ts = int(float(item.get('timestamp') or item.get('updatedAt') or now_ts))
        update_str = datetime.fromtimestamp(ts, pst).strftime('%H:%M:%S')
        
        bet_df_data.append({
            'Market': short_title,
            'UP/DOWN': updown,
            'Size': f"${size_val:.0f}",
            'Price': price_val,
            'Updated': update_str
        })
    
    bet_df = pd.DataFrame(bet_df_data).sort_values('Updated', ascending=False)
    
    # 2. CLOSED PN L TABLE (NEW)
    closed_raw = safe_fetch(f"https://data-api.polymarket.com/closed-positions?user={trader}&limit=30")
    closed_data = []
    total_pnl = 0
    for item in closed_raw:
        ts_field = item.get('timestamp') or item.get('updatedAt')
        ts = int(float(ts_field)) if ts_field else 0
        if ts >= fifteen_min_ago and is_crypto(str(item.get('title', ''))):
            pnl = float(item.get('realizedPnl', item.get('pnl', 0)))
            total_pnl += pnl
            closed_data.append({
                'Market': str(item.get('title', ''))[:50] + '...',
                'Realized PnL': f"${pnl:.0f}",
                'Outcome': item.get('outcome', '?'),
                'Closed': datetime.fromtimestamp(ts, pst).strftime('%H:%M')
            })
    
    pnl_df = pd.DataFrame(closed_data)
    
    # DISPLAY
    st.success(f"✅ {len(bet_df)} live bets | 💰 {len(pnl_df)} closed PnL (15min)")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🎯 Live Bets")
        if not bet_df.empty:
            st.dataframe(bet_df, use_container_width=True, height=350)
    
    with col2:
        st.subheader("💰 Closed PnL")
        if not pnl_df.empty:
            st.dataframe(pnl_df, use_container_width=True, height=350)
            st.metric("15min Realized Total", f"${total_pnl:.0f}")
        else:
            st.info("No recent closes")
    
    if not bet_df.empty:
        up_bets = len(bet_df[bet_df['UP/DOWN'] == '🟢 UP'])
        st.metric("🟢 UP Bets", up_bets)
        st.metric("🔴 DOWN Bets", len(bet_df) - up_bets)
    
    if not pnl_df.empty:
        st.metric("Win Rate (Closes)", f"{len(pnl_df[pnl_df['Realized PnL'].str.contains('+', na=False)])/len(pnl_df):.0%}")

if st.button("🔄 Force Refresh"):
    st.rerun()

# Refresh loop
placeholder = st.empty()
refresh_count = 0
while True:
    refresh_count += 1
    now_pst = datetime.now(pst)
    with placeholder.container():
        track_0x8dxd()
        st.caption(f"🕐 {now_pst.strftime('%H:%M:%S %Z')} | #{refresh_count}")
    time.sleep(5)
    st.rerun()
