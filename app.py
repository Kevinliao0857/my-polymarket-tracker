import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time
import pytz

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Tracker")

st.info("🟢 UP/DOWN bets live | Real PnL from API | PST Vancouver")

pst = pytz.timezone('US/Pacific')
now_pst = datetime.now(pst)

@st.cache_data(ttl=2)
def safe_fetch(url):
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return []

def get_data():
    trader = "0x8dxd"
    
    # Live bets (trades + positions)
    trades = safe_fetch(f"https://data-api.polymarket.com/trades?user={trader}&limit=50") or []
    positions = safe_fetch(f"https://data-api.polymarket.com/positions?user={trader}") or []
    
    bets = []
    for item in trades + positions:
        title = str(item.get('title', ''))
        if any(sym in title.lower() for sym in ['btc', 'eth', 'sol']):
            bets.append({
                'title': title[:55] + '...' if len(title) > 55 else title,
                'updown': "🟢 UP" if 'buy' in str(item.get('side', '')).lower() or 'yes' in str(item.get('outcome', '')).lower() else "🔴 DOWN",
                'updated': datetime.fromtimestamp(item.get('timestamp', time.time()), pst).strftime('%H:%M')
            })
    
    # Real PnL sum from positions
    total_pnl = 0
    for pos in positions:
        total_pnl += float(pos.get('cashPnl', 0))
    
    return pd.DataFrame(bets[:12]), total_pnl

col1, col2 = st.columns([3, 1])

with col1:
    df, pnl = get_data()
    if not df.empty:
        st.success(f"✅ {len(df)} live crypto bets")
        st.dataframe(df[['title', 'updown', 'updated']], use_container_width=True)
    else:
        st.info("Scanning bets...")

with col2:
    st.markdown("### 💰 Real PnL")
    st.metric("Open PnL", f"${pnl:.0f}")
    st.metric("Total Bets", len(df))
    st.caption("From /positions API[web:2]")

if st.button("🔄 Update"):
    st.rerun()

st.caption(f"Live {now_pst.strftime('%H:%M:%S %Z')} | Vancouver PST")
