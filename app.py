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
    data = []
    try:
        resp = requests.get(f"https://data-api.polymarket.com/positions?proxyWallet={wallet}", timeout=8)
        if resp.status_code == 200:
            data = resp.json()
    except:
        pass
    return data[:15] if isinstance(data, list) else []

def get_direction(title, side=None):
    text = (str(title) + str(side or '')).lower()
    if any(word in text for word in ['long', 'yes', 'above', 'will', 'rises']):
        return "🟢 UP"
    if any(word in text for word in ['short', 'no', 'below', 'falls']):
        return "🔴 DOWN"
    return "➖"

bets = fetch_all(wallet)
col1, col2 = st.columns(2)
col1.metric("Live Bets", len(bets))
col2.metric("Updated", datetime.now().strftime('%H:%M:%S'))

if bets:
    rows = []
    for bet in bets:
        title = bet.get('title') or bet.get('question') or ''
        direction = get_direction(title, bet.get('side'))
        rows.append({
            'Direction': direction,
            'Market': str(title)[:60],
            'Size': f"${float(bet.get('size', 0)):.0f}",
            'Updated': datetime.now().strftime('%H:%M:%S')
        })
    
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
else:
    st.info("No bets | [Leaderboard](https://polymarket.com/leaderboard)")

st.caption("5s live")
time.sleep(5)
st.rerun()
