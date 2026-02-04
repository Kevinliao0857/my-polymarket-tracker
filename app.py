import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time

st.set_page_config(layout="wide")
st.markdown("# 🚀 0x8dxd Live Signals")

st.sidebar.header("Wallet")
wallet = st.sidebar.text_input("", value="0x63ce342161250d705dc0b16df89036c8e5f9ba9a")

@st.cache_data(ttl=5)
def fetch_all(wallet):
    try:
        resp = requests.get(f"https://data-api.polymarket.com/positions?proxyWallet={wallet}", timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            return data[:15] if isinstance(data, list) else []
        resp = requests.get(f"https://data-api.polymarket.com/trades?user={wallet}", timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            return data[:15] if isinstance(data, list) else []
    except:
        pass
    return []

def direction(item):
    side = str(item.get('side') or item.get('outcome') or '').lower()
    if 'long' in side or 'yes' in side:
        return "🟢 UP"
    if 'short' in side or 'no' in side:
        return "🔴 DOWN"
    return "➖"

bets = fetch_all(wallet)
col1, col2 = st.columns(2)
col1.metric("Live Bets", len(bets))
col2.metric("Updated", datetime.now().strftime('%H:%M:%S'))

if bets:
    rows = []
    for bet in bets:
        dir = direction(bet)
        rows.append({
            'Direction': dir,
            'Market': str(bet.get('title') or bet.get('question') or '-')[:60],
            'Size': f"${float(bet.get('size', 0)):.0f}",
            'Updated': datetime.now().strftime('%H:%M:%S')
        })
    
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
else:
    st.info("No active bets | Try leaderboard whales")

st.caption("5s live")
time.sleep(5)
st.rerun()
