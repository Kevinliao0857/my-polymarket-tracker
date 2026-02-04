import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Tracker")

st.info("🟢 Live tracking | Crypto-only | Enhanced UP/DOWN from API + titles")

@st.cache_data(ttl=5)
def safe_fetch(url):
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return data[:20]  # Slightly more for dedup
    except:
        pass
    return []

def is_crypto(market_title):
    title_lower = market_title.lower()
    crypto_symbols = ['btc', 'eth', 'sol', 'xrp', 'ada', 'doge', 'shib', 'link', 'avax', 'matic', 'dot', 'uni']
    # Hourly/crypto price bets like "BTC above $95k next hour?"
    return any(sym in title_lower for sym in crypto_symbols) or any(phrase in title_lower for phrase in ['bitcoin', 'ethereum', 'solana'])

def get_up_down(item):
    outcome = item.get('outcome', '').lower()
    side = item.get('side', '').lower()
    title = str(item.get('title', item.get('question', ''))).lower()
    
    # Positions: outcome strongest signal
    if 'yes' in outcome or outcome == 'yes':
        return "🟢 UP"
    if 'no' in outcome or outcome == 'no':
        return "🔴 DOWN"
    
    # Trades: side + price context
    if 'buy' in side:
        if any(word in title for word in ['above', 'up']):
            return "🟢 UP"
        return "🟢 UP"  # Default buy as bullish
    if 'sell' in side:
        if any(word in title for word in ['below', 'down']):
            return "🔴 DOWN"
        return "🔴 DOWN"  # Default sell as bearish
    
    # Title fallback
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
    seen_markets = set()
    for url in urls:
        all_data.extend(safe_fetch(url))
    
    df_data = []
    for item in all_data:
        title = str(item.get('title') or item.get('question') or '-')
        if not is_crypto(title):
            continue  # Skip non-crypto
        
        market_key = title[:100]  # Dedup similar
        if market_key in seen_markets:
            continue
        seen_markets.add(market_key)
        
        updown = get_up_down(item)
        short_title = (title[:57] + '...') if len(title) > 60 else title
        
        size_val = float(item.get('size', 0))
        pnl_val = float(item.get('cashPnl', item.get('pnl', 0)))
        price_val = item.get('curPrice', item.get('price', '-'))
        if isinstance(price_val, (int, float)):
            price_val = f"${price_val:.2f}"
        
        row = {
            'Market': short_title,
            'UP/DOWN': updown,
            'Size': f"${size_val:.0f}",
            'PnL': f"${pnl_val:.0f}",
            'Price': price_val,
            'Updated': datetime.now().strftime('%H:%M:%S')
        }
        df_data.append(row)
    
    if df_data:
        df = pd.DataFrame(df_data)
        df = df.sort_values('Updated', ascending=False)
        
        st.success(f"✅ {len(df)} crypto bets | Enhanced UP/DOWN detected")
        st.dataframe(df, use_container_width=True)
        
        up_bets = len(df[df['UP/DOWN'] == '🟢 UP'])
        st.metric("🟢 UP Bets", up_bets)
        st.metric("🔴 DOWN Bets", len(df) - up_bets)
        
        pnl = pd.to_numeric(df['PnL'].str.replace('$',''), errors='coerce').sum()
        st.metric("Total PnL", f"${pnl:.0f}")
    else:
        st.info("No active crypto bets | [0x8dxd](https://polymarket.com/@0x8dxd)")

# Refresh loop
placeholder = st.empty()
while True:
    with placeholder.container():
        track_0x8dxd()
        st.caption("5s refresh | Crypto-only tracking")
    time.sleep(5)
    st.rerun()
