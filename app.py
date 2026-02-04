import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time

st.set_page_config(layout="wide")
st.markdown("# 🚀 0x8dxd Crypto Signals")

st.sidebar.header("Wallet")
wallet = st.sidebar.text_input("", value="0x63ce342161250d705dc0b16df89036c8e5f9ba9a")
st.sidebar.caption("0x8dxd crypto bot")

@st.cache_data(ttl=5)
def fetch_bets(wallet):
    try:
        resp = requests.get(f"https://data-api.polymarket.com/positions?proxyWallet={wallet}", timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data[:10]
    except:
        pass
    return []

def direction(side):
    if side in ['long', 'yes', 1]:
        return "🟢 UP"
    if side in ['short', 'no', 0]:
        return "🔴 DOWN"
    return "➖"

bets = fetch_bets(wallet)
col1, col2 = st.columns(2)
col1.metric("Live Bets", len(bets))
col2.metric("Last Update", datetime.now().strftime('%H:%M:%S'))

if bets:
    rows = []
    for bet in bets:
        title = str(bet.get('title') or '-')
        if any(crypto in title.lower() for crypto in ['btc', 'eth', 'sol']):
            rows.append({
                'Signal': direction(bet.get('side')),
                'Market': title[:60],
                'Size': f"${float(bet.get('size', 0)):.0f}",
                'Updated': datetime.now().strftime('%H:%M:%S')
            })
    
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No crypto bets active")
else:
    st.info("🔄 Fetching...")

st.caption("5s live | Copy 0x8dxd signals")
time.sleep(5)
st.rerun()
