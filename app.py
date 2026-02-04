import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Tracker")

st.info("🟢 Live tracking | UP/DOWN from API + market names")

@st.cache_data(ttl=5)
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

def get_up_down(item):
    # API side/outcome
    side = item.get('side', item.get('outcome', ''))
    title = str(item.get('title', item.get('question', ''))).lower()
    
    # Direct matches
    if side in ['long', 'yes', 'buy', 1, '1']:
        return "🟢 UP"
    if side in ['short', 'no', 'sell', 0, '0']:
        return "🔴 DOWN"
    
    # Market title clues
    if any(word in title for word in ['yes', 'will', 'above', 'up']):
        return "🟢 UP"
    if any(word in title for word in ['no', 'below', 'down']):
        return "🔴 DOWN"
    
    return "➖ ?"

def track_0x8dxd():
    trader = "0x8dxd"
    urls = [
        f"https://data-api.polymarket.com/positions?user={trader}",
        f"https://data-api.polymarket.com/trades?user={trader}"
    ]
    
    all_data = []
    for url in urls:
        all_data.extend(safe_fetch(url))
    
    if all_data:
        df_data = []
        for item in all_data:
            updown = get_up_down(item)
            row = {
                'Market': str(item.get('title') or item.get('question') or '- ')[:60],
                'UP/DOWN': updown,
                'Size': f"${float(item.get('size', 0)):.0f}",
                'PnL': f"${float(item.get('cashPnl', item.get('pnl', 0))):.0f}",
                'Price': item.get('curPrice', item.get('price', '-')),
                'Updated': datetime.now().strftime('%H:%M:%S')
            }
            df_data.append(row)
        
        df = pd.DataFrame(df_data)
        st.success(f"✅ {len(df)} bets | Auto UP/DOWN detected")
        st.dataframe(df, use_container_width=True)
        
        up_bets = len(df[df['UP/DOWN'] == '🟢 UP'])
        st.metric("🟢 UP Bets", up_bets)
        st.metric("🔴 DOWN Bets", len(df) - up_bets)
        
        pnl = pd.to_numeric(df['PnL'].str.replace('$',''), errors='coerce').sum()
        st.metric("Total PnL", f"${pnl:.0f}")
    else:
        st.info("No active bets | [0x8dxd](https://polymarket.com/@0x8dxd)")

track_0x8dxd()
st.caption("5s refresh [web:166]")
time.sleep(5)
st.rerun()
