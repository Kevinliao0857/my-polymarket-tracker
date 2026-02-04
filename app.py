import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time
import pytz  # pip install pytz

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Tracker - Last 15 Min")

st.info("🟢 Live crypto-only | UP/DOWN focus | Last 15min")

# Live PST clock
pst = pytz.timezone('US/Pacific')
now_pst = datetime.now(pst)
st.caption(f"🕐 Current: {now_pst.strftime('%Y-%m-%d %H:%M:%S %Z')} | Auto 5s + Force 🔄")

@st.cache_data(ttl=3)
def safe_fetch(url):
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return data[:100]
    except:
        pass
    return []

@st.cache_data(ttl=60)
def get_trader_pnl(trader):
    try:
        url = f"https://polymarket.com/@{trader}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            html = resp.text
            # Extract PnL from data attributes/JSON blobs (matches chart)
            import re
            # Total PnL (look for data-pnl-total pattern)
            total_match = re.search(r'"totalPnL":\s*([\d.-]+)', html)
            realized_match = re.search(r'"realizedPnL":\s*([\d.-]+)', html)
            unrealized_match = re.search(r'"unrealizedPnL":\s*([\d.-]+)', html)
            
            if total_match:
                return {
                    'total': float(total_match.group(1)),
                    'realized': float(realized_match.group(1)) if realized_match else 0,
                    'unrealized': float(unrealized_match.group(1)) if unrealized_match else 0,
                    'chart_7d': []  # Chart scraping complex, skip for now
                }
    except:
        pass
    return None


def is_crypto(market_title):
    title_lower = market_title.lower()
    crypto_symbols = ['btc', 'eth', 'sol', 'xrp', 'ada', 'doge', 'shib', 'link', 'avax', 'matic', 'dot', 'uni']
    return any(sym in title_lower for sym in crypto_symbols) or 'bitcoin' in title_lower or 'ethereum' in title_lower or 'solana' in title_lower

def get_up_down(item):
    outcome = str(item.get('outcome', '')).lower()
    side = str(item.get('side', '')).lower()
    title = str(item.get('title', item.get('question', ''))).lower()
    
    if 'yes' in outcome:
        return "🟢 UP"
    if 'no' in outcome:
        return "🔴 DOWN"
    
    if 'buy' in side:
        return "🟢 UP"
    if 'sell' in side:
        return "🔴 DOWN"
    
    if any(word in title for word in ['1h', 'hour', '15m']):
        if any(word in title for word in ['above']):
            return "🟢 UP"
        if any(word in title for word in ['below']):
            return "🔴 DOWN"
    
    if any(word in title for word in ['yes', 'will', 'above', 'up']):
        return "🟢 UP"
    if any(word in title for word in ['no', 'below', 'down']):
        return "🔴 DOWN"
    
    return "➖ ?"

def track_0x8dxd():
    trader = "0x8dxd"
    now_ts = int(time.time())
    fifteen_min_ago = now_ts - 900
    
    urls = [
        f"https://data-api.polymarket.com/trades?user={trader}&limit=100",
        f"https://data-api.polymarket.com/positions?user={trader}"
    ]
    
    all_data = []
    seen = set()
    for url in urls:
        raw_data = safe_fetch(url)
        for item in raw_data:
            ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt')
            ts = int(float(ts_field)) if ts_field else now_ts
            if ts >= fifteen_min_ago:
                title = str(item.get('title') or item.get('question') or '-')
                if is_crypto(title):
                    key = title[:100]
                    if key not in seen and len(all_data) < 25:
                        seen.add(key)
                        all_data.append(item)
    
    if not all_data:
        st.info("No crypto activity in last 15 min")
        return
    
    df_data = []
    min_ts = now_ts
    for item in all_data:
        updown = get_up_down(item)
        title = str(item.get('title') or item.get('question') or '-')
        short_title = (title[:55] + '...') if len(title) > 60 else title
        
        size_val = float(item.get('size', 0))
        price_val = item.get('curPrice', item.get('price', '-'))
        if isinstance(price_val, (int, float)):
            price_val = f"${price_val:.2f}"
        
        ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt') or now_ts
        ts = int(float(ts_field)) if ts_field else now_ts
        min_ts = min(min_ts, ts)
        update_str = datetime.fromtimestamp(ts, pst).strftime('%H:%M:%S')
        
        row = {
            'Market': short_title,
            'UP/DOWN': updown,
            'Size': f"${size_val:.0f}",
            'Price': price_val,
            'Updated': update_str
        }
        df_data.append(row)
    
    df = pd.DataFrame(df_data)
    df = df.sort_values('Updated', ascending=False)
    
    st.success(f"✅ {len(df)} crypto bets (15min)")
    st.dataframe(df, use_container_width=True, height=400)
    
    up_bets = len(df[df['UP/DOWN'] == '🟢 UP'])
    st.metric("🟢 UP Bets", up_bets)
    st.metric("🔴 DOWN Bets", len(df) - up_bets)
    
    span_min = int((now_ts - min_ts) / 60)
    st.metric("Newest", f"{span_min} min ago")
    
    # LIVE TOTAL OPEN PNL (Data API)
    positions = safe_fetch(f"https://data-api.polymarket.com/positions?user={trader}")
    live_pnl = sum(float(p.get('cashPnl', 0)) for p in positions) if positions else 0
    st.metric("Open PnL (API)", f"${live_pnl:.0f}")
    
    # OFFICIAL PNL FROM POLYMARKET CHART (TheGraph)
    with st.spinner("Fetching official PnL..."):
        pnl_data = get_trader_pnl(trader)
    if pnl_data:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total PnL", f"${pnl_data['total']:.0f}")
        col2.metric("Realized PnL", f"${pnl_data['realized']:.0f}")
        col3.metric("Unrealized PnL", f"${pnl_data['unrealized']:.0f}")
        
        # 7-Day PnL Chart (matches screenshot!)
        if pnl_data['chart_7d']:
            chart_df = pd.DataFrame(pnl_data['chart_7d'])
            if not chart_df.empty:
                st.subheader("📈 7-Day PnL Chart")
                st.line_chart(chart_df.set_index('timestamp')['pnl'], use_container_width=True)
    else:
        st.warning("PnL data unavailable (GraphQL timeout)")

if st.button("🔄 Force Refresh"):
    st.rerun()

# Refresh loop
placeholder = st.empty()
refresh_count = 0
while True:
    refresh_count += 1
    now_pst = datetime.now(pst)
    with placeholder.container():
        track_0x8dxd()
        st.caption(f"🕐 {now_pst.strftime('%H:%M:%S %Z')} | #{refresh_count}")
    time.sleep(5)
    st.rerun()
