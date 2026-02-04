import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time

st.set_page_config(layout="wide")
st.title("🚀 Polymarket Live Tracker")

# Sidebar
st.sidebar.header("Trader Search")
trader = st.sidebar.text_input("Username/Wallet", value="nanoin123")
if st.sidebar.button("🔄 Refresh Now"):
    st.rerun()

@st.cache_data(ttl=300)
def safe_fetch(url):
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return data[:15]
    except:
        pass
    return []

def display_data(trader):
    urls = [
        f"https://data-api.polymarket.com/positions?proxyWallet={trader}",
        f"https://data-api.polymarket.com/trades?user={trader}"
    ]
    
    all_data = []
    for url in urls:
        all_data.extend(safe_fetch(url))
    
    if all_data:
        # Flexible columns
        cols = ['title', 'question', 'market', 'outcome', 'side', 'size', 'cashPnl', 'pnl']
        df_data = []
        for item in all_data:
            row = {col: item.get(col, '-') for col in cols}
            row['time'] = datetime.now().strftime('%H:%M')
            df_data.append(row)
        
        df = pd.DataFrame(df_data)
        st.success(f"✅ Found {len(df)} positions/trades")
        st.dataframe(df[['title', 'side', 'size', 'cashPnl', 'time']], use_container_width=True)
        
        total_pnl = df['cashPnl'].sum()
        st.metric("Total PnL", f"${total_pnl:.0f}" if pd.notna(total_pnl) else "$0")
    else:
        st.info(f"""
        🔍 No data for "{trader}" 
        
        **Try these active traders**:
        • nanoin123 (leaderboard #1)
        • beachboy4
        • Wallet: 0x56687bf447db6ffa42ffe2204a05edaa20f55839
        
        [Live Leaderboard](https://polymarket.com/leaderboard)
        """)

display_data(trader)
st.caption("Live from Polymarket API | Refreshes every 5 mins [web:136]")
