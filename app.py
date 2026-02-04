import streamlit as st
import requests
import pandas as pd
from datetime import datetime

st.set_page_config(layout="wide")

# Real Polymarket API
@st.cache_data(ttl=300)
def get_positions(wallet):
    try:
        resp = requests.get(f"https://data-api.polymarket.com/positions?proxyWallet={wallet}", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                df = pd.DataFrame(data[:15])
                df['updated'] = datetime.now().strftime('%H:%M')
                return df[['title', 'outcome', 'size', 'cashPnl', 'percentPnl', 'curPrice', 'updated']]
    except:
        pass
    return pd.DataFrame()

st.title("🔥 Live Polymarket Positions Tracker")
wallet = st.sidebar.text_input("Wallet Address", value="0x56687bf447db6ffa42ffe2204a05edaa20f55839")  # Example whale

df = get_positions(wallet)
if not df.empty:
    st.metric("Positions", len(df))
    st.dataframe(df, use_container_width=True)
    st.metric("Total PnL", f"${df['cashPnl'].sum():.0f}")
else:
    st.info("Enter wallet (0x...) or use leaderboard: polymarket.com/leaderboard")

st.caption("Refreshes every 5 mins [web:136]")
