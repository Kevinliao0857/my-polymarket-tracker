import streamlit as st
import requests
import pandas as pd
from datetime import datetime

st.set_page_config(layout="wide")
st.markdown("# 🔥 Polymarket Live Trader Tracker")

st.sidebar.header("👤 Track Trader")
trader = st.sidebar.text_input("Username/Wallet", value="nanoin123")
st.sidebar.caption("nanoin123 • beachboy4 • leaderboard")

@st.cache_data(ttl=300, show_spinner=False)
def fetch_live():
    try:
        resp = requests.get(f"https://data-api.polymarket.com/positions?proxyWallet=nanoin123", timeout=10)
        if resp.status_code == 200 and resp.json():
            return pd.DataFrame(resp.json()[:15])
    except:
        pass
    return pd.DataFrame({'Status': ['Live data loading... Check leaderboard for whales']})

df = fetch_live()

if not df.empty:
    col1, col2, col3 = st.columns(3)
    col1.metric("Active Trades", len(df))
    col2.metric("Last Update", datetime.now().strftime('%H:%M'))
    
    st.subheader("📊 Live Positions")
    st.dataframe(df[['title', 'side', 'size', 'cashPnl', 'percentPnl']], use_container_width=True)
else:
    st.info("👆 Try leaderboard wallets from [polymarket.com/leaderboard](https://polymarket.com/leaderboard)")
