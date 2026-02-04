import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time

st.set_page_config(layout="wide")
st.title("₿ Crypto Bets Live Tracker")

st.sidebar.header("Crypto Trader")
wallet = st.sidebar.text_input("Wallet Address", value="PASTE_CRYPTO_TRADER_WALLET_HERE")
st.sidebar.caption("Find on polymarket.com/crypto or leaderboard")

@st.cache_data(ttl=5)
def fetch_crypto_positions(wallet):
    urls = [
        f"https://data-api.polymarket.com/positions?proxyWallet={wallet}",
        f"https://data-api.polymarket.com/trades?user={wallet}"
    ]
    all_data = []
    for url in urls:
        try:
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    # Filter CRYPTO bets
                    for item in data:
                        title = str(item.get('title', '')).lower()
                        if any(crypto in title for crypto in ['btc', 'bitcoin', 'eth', 'ethereum', 'sol', 'price']):
                            all_data.append(item)
        except: pass
    return all_data[:10]

positions = fetch_crypto_positions(wallet)

col1, col2 = st.columns(2)
col1.metric("Crypto Bets", len(positions))
col2.metric("Last Check", datetime.now().strftime('%H:%M:%S'))

if positions:
    df_data = []
    for pos in positions:
        row = {
            'Market': pos.get('title', '-')[:80],
            'Side': pos.get('side', '-'),
            'Size': f"${float(pos.get('size', 0)):.0f}",
            'PnL': f"${float(pos.get('cashPnl', 0)):.0f}",
            'Price': pos.get('curPrice', '-')
        }
        df_data.append(row)
    
    df = pd.DataFrame(df_data)
    st.success("✅ Crypto bets found!")
    st.dataframe(df, use_container_width=True)
    
    total_pnl = sum(float(p.get('cashPnl', 0)) for p in positions)
    st.metric("Net Crypto PnL", f"${total_pnl:.0f}")
else:
    st.info("""
    🔍 Paste crypto trader wallet 
    
    **Example markets tracked**:
    • BTC $100k Dec 31?
    • ETH $5k EOY?
    • SOL $500?
    
    [Crypto Markets](https://polymarket.com/crypto)
    """)

st.caption("₿ Auto 5s | Polymarket API [web:136]")
time.sleep(5)
st.rerun()
