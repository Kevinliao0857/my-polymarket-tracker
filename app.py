import streamlit as st
import requests
import pandas as pd
from datetime import datetime

st.set_page_config(layout="wide", page_title="Polymarket Tracker")

st.title("🔥 Polymarket Trader Tracker")
st.caption("Live data • Top 15 positions • 5min refresh")

# Sidebar
st.sidebar.header("Search")
trader = st.sidebar.text_input("Wallet or Username", value="nanoin123")
if st.sidebar.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()

@st.cache_data(ttl=300)
def get_data(search):
    positions = []
    trades = []
    
    # Data API endpoints (public)
    apis = [
        f"https://data-api.polymarket.com/positions?proxyWallet={search}",
        f"https://data-api.polymarket.com/trades?user={search}",
        f"https://gamma.api.polymarket.com/positions?username={search}"
    ]
    
    for url in apis:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    positions.extend(data[:10])
        except:
            continue
    
    if positions:
        df = pd.DataFrame(positions)
        if not df.empty:
            df['time'] = datetime.now().strftime('%H:%M:%S')
            return df[['title', 'outcome', 'size', 'cashPnl']].tail(15)
    
    return pd.DataFrame({
        'Message': ['No positions found. Try: nanoin123, beachboy4'],
        'Tip': ['Check leaderboard: polymarket.com/leaderboard']
    })

df = get_data(trader)

col1, col2 = st.columns(2)
col1.metric("Trader", trader)
col2.metric("Last Update", datetime.now().strftime('%H:%M'))

st.subheader("📊 Active Positions (Top 15)")
st.dataframe(df, use_container_width=True, hide_index=True)

st.caption("✅ Data from Polymarket API [web:136] | No private keys")
