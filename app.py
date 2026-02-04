import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Live Tracker")

st.info("🟢 $313 → $438k | 98% winrate | BTC/ETH/SOL UP/DOWN bets")

@st.cache_data(ttl=5)
def safe_fetch(url):
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return [item for item in data if any(word in str(item.get('title', '')).lower() 
                    for word in ['btc', 'eth', 'sol', 'price'])]
    except:
        pass
    return []

def get_direction(side):
    if side in ['long', 'yes', 'buy']:
        return "🟢 UP"
    elif side in ['short', 'no', 'sell']:
        return "🔴 DOWN"
    return "➖"

def track_0x8dxd():
    trader = "0x8dxd"
    urls = [
        f"https://data-api.polymarket.com/positions?user={trader}",
        f"https://data-api.polymarket.com/trades?user={trader}",
        f"https://gamma.api.polymarket.com/positions?username={trader}"
    ]
    
    all_data = []
    for url in urls:
        all_data.extend(safe_fetch(url))
    
    if all_data:
        df_data = []
        for item in all_data[:15]:
            direction = get_direction(item.get('side') or item.get('outcome'))
            row = {
                'Market': str(item.get('title') or item.get('question', '-'))[:60],
                'UP/DOWN': direction,
                'Size': f"${float(item.get('size', 0)):.0f}",
                'PnL': f"${float(item.get('cashPnl', 0)):.0f}",
                'Price': f"{item.get('curPrice', '-')}",
                'Updated': datetime.now().strftime('%H:%M:%S')
            }
            df_data.append(row)
        
        df = pd.DataFrame(df_data)
        st.success(f"✅ Tracking {len(df)} crypto bets")
        st.dataframe(df, use_container_width=True)
        
        pnl = pd.to_numeric(df['PnL'].str.replace('$','').str.replace(',',''), errors='coerce').sum()
        st.metric("Net PnL", f"${pnl:.0f}")
        up_count = len(df[df['UP/DOWN'] == '🟢 UP'])
        st.metric("UP Bets", up_count)
        st.metric("DOWN Bets", len(df) - up_count)
    else:
        st.info("🔄 No active crypto bets | [0x8dxd Profile](https://polymarket.com/@0x8dxd)")

track_0x8dxd()
st.caption("5s auto‑refresh | [web:167]")
time.sleep(5)
st.rerun()
