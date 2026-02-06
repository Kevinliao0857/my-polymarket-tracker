import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time
import pytz  # pip install pytz
import re  # For time parsing

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Tracker - Last 15 Min")

st.info("🟢 Live crypto-only | UP/DOWN focus | Last 15min")

# Live EST clock (trader uses EST)
est = pytz.timezone('US/Eastern')
now_est = datetime.now(est)
time_24 = now_est.strftime('%H:%M:%S')
time_12 = now_est.strftime('%I:%M:%S %p')
st.caption(f"🕐 Current EST: {now_est.strftime('%Y-%m-%d')} {time_24} ({time_12}) ET | Auto 5s + Force 🔄")
st.sidebar.title("⚙️ Settings")
MINUTES_BACK = st.sidebar.slider("⏰ Minutes back", 15, 120, 30, 5)
now_ts = int(time.time())
st.sidebar.caption(f"From: {datetime.fromtimestamp(now_ts - MINUTES_BACK*60, est).strftime('%H:%M %p ET')}")

# AUTO REFRESHER
if 'last_auto_refresh' not in st.session_state:
    st.session_state.last_auto_refresh = 0
now_ts = int(time.time())
if now_ts - st.session_state.last_auto_refresh >= 5:
    st.session_state.last_auto_refresh = now_ts
    st.rerun()

st.sidebar.caption(f"🔄 Auto-refresh active | Next: ~{5 - (now_ts - st.session_state.last_auto_refresh)}s")

@st.cache_data(ttl=3)
def safe_fetch(url):
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return data[:500]  # Increased limit
    except:
        pass
    return []

def is_crypto(item):
    title = str(item.get('title') or item.get('question') or '').lower()  # TITLE ONLY
    tickers = ['btc', 'eth', 'sol', 'xrp', 'ada', 'doge', 'shib', 'link', 'avax', 'matic', 'dot', 'uni', 'bnb', 'usdt', 'usdc']
    full_names = ['bitcoin', 'ethereum', 'solana', 'ripple', 'xrp', 'cardano', 'dogecoin', 'shiba', 'chainlink', 'avalanche', 'polygon', 'polkadot', 'uniswap', 'binance coin']
    
    # STRICT: Must contain ticker OR full name in TITLE (no 'crypto' wildcard, no full item text)
    return any(t in title for t in tickers) or any(f in title for f in full_names)

def get_up_down(item):
    fields = ['outcome', 'side', 'answer', 'choice', 'direction']
    text = ' '.join(str(item.get(f, '')).lower() for f in fields)
    title = str(item.get('title', item.get('question', ''))).lower()
    
    if 'yes' in text or 'buy' in text or 'long' in text:
        return "🟢 UP"
    if 'no' in text or 'sell' in text or 'short' in text:
        return "🔴 DOWN"
    
    if any(word in title for word in ['above', 'higher', 'rise', 'up', 'moon']):
        return "🟢 UP"
    if any(word in title for word in ['below', 'lower', 'drop', 'down', 'crash']):
        return "🔴 DOWN"
    
    price_words = ['$', 'usd', 'price']
    if any(p in title for p in price_words):
        if '>' in title or '>=' in title:
            return "🟢 UP"
        if '<' in title or '<=' in title:
            return "🔴 DOWN"
    
    if any(word in title for word in ['1h', 'hour', '15m', 'will']):
        if any(word in title for word in ['yes', 'will', 'reach']):
            return "🟢 UP"
        else:
            return "🔴 DOWN"
    
    return "➖ ?"

def get_status(item, now_ts):
    title = str(item.get('title') or item.get('question') or '').lower()
    
    # FULL DECIMAL NOW - Precise minute/second comparison
    now_dt = datetime.fromtimestamp(now_ts, est)
    now_decimal = now_dt.hour + (now_dt.minute / 60.0) + (now_dt.second / 3600.0)
    
    # Regex for times
    time_pattern = r'(\d{1,2})(?::(\d{1,2}))?([ap]m|et)'
    matches = re.findall(time_pattern, title)
    title_times = []
    
    for h_str, m_str, suffix in matches:
        try:
            hour = int(h_str)
            minute = int(m_str) if m_str else 0
            
            if 'pm' in suffix or 'p' in suffix:
                hour = (hour % 12) + 12
            elif 'am' in suffix or 'a' in suffix:
                hour = hour % 12
            
            if 0 <= hour <= 23 and 0 <= minute < 60:
                decimal_h = hour + (minute / 60.0)
                title_times.append(decimal_h)
        except:
            continue
    
    if not title_times:
        return "🟢 ACTIVE (no timer)"
    
    max_h = max(title_times)
    if now_decimal >= max_h:
        return "⚫ EXPIRED"
    
    disp_h = int(max_h % 12) or 12
    disp_m = f":{int((max_h % 1)*60):02d}" if (max_h % 1) > 0.1 else ""
    ampm = 'PM' if max_h >= 12 else 'AM'
    return f"🟢 ACTIVE (til ~{disp_h}{disp_m} {ampm} ET)"

def track_0x8dxd():
    trader = "0x63ce342161250d705dc0b16df89036c8e5f9ba9a".lower()  # Target wallet
    display_name = "0x8dxd"
    now_ts = int(time.time())
    ago_ts = now_ts - (MINUTES_BACK * 60)  # Dynamic!

    
    urls = [
        f"https://data-api.polymarket.com/trades?user={trader}&limit=500&offset=0"
    ]
    
    all_data = []
    for url in urls:
        raw_data = safe_fetch(url)
        
        # GUARD: Only keep trades for our target wallet
        filtered_data = []
        for item in raw_data:
            proxy = str(item.get("proxyWallet", "")).lower()
            user_field = str(item.get("user", "")).lower()
            if proxy == trader or user_field == trader:
                filtered_data.append(item)
        raw_data = filtered_data
        
        for item in raw_data:
            ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt')
            ts = int(float(ts_field)) if ts_field else now_ts
            if ts >= ago_ts and is_crypto(item):  # ✅ Use dynamic slider value
                all_data.append(item)
    
    all_data = all_data[-200:]
    
    if not all_data:
        st.info("No crypto activity in last 15 min")
        return
    
    # st.info(f"DEBUG: Fetched {len(all_data)} recent crypto trades for {display_name}")
    
    df_data = []
    min_ts = now_ts
    for item in all_data:
        updown = get_up_down(item)
        title = str(item.get('title') or item.get('question') or '-')
        short_title = (title[:85] + '...') if len(title) > 90 else title
        
        size_val = float(item.get('size', 0))
        price_val = item.get('curPrice', item.get('price', '-'))
        if isinstance(price_val, (int, float)):
            price_val = f"${price_val:.2f}"
        
        ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt') or now_ts
        ts = int(float(ts_field)) if ts_field else now_ts
        min_ts = min(min_ts, ts)
        update_str = datetime.fromtimestamp(ts, est).strftime('%I:%M:%S %p ET')
        status_str = get_status(item, now_ts)
        
        row = {
            'Market': short_title,
            'UP/DOWN': updown,
            'Size': f"${size_val:.0f}",
            'Price': price_val,
            'Status': status_str,
            'Updated': update_str,
            'ts_raw': ts  # NEW: For highlighting recent trades
        }
        df_data.append(row)
    
    df = pd.DataFrame(df_data)
    df['age_sec'] = now_ts - df['ts_raw']  # NEW: Age in seconds
    
    if df.empty:
        st.info("No qualifying crypto bets in last 15 min")
        return
    
    # Custom sort (unchanged)
    def status_priority(x):
        x_lower = str(x).lower()
        if 'expired' in x_lower:
            return 1
        elif 'no timer' in x_lower:
            return 2
        else:
            return 0
    
    df['priority'] = df['Status'].apply(status_priority)
    df['parsed_updated'] = pd.to_datetime(df['Updated'], format='%I:%M:%S %p ET')
    df = df.sort_values(['priority', 'parsed_updated'], ascending=[True, False])
    df = df.drop(['priority', 'parsed_updated'], axis=1)
    
    st.success(f"✅ {len(df)} crypto bets (15min ET)")
    
    # NEW: Styling function for recent rows
    def highlight_recent(row, threshold=30):  # 30 seconds = "recent"
        if row.get('age_sec', 9999) <= threshold:
            return ['background-color: rgba(0, 255, 0, 0.15)'] * len(row)
        return [''] * len(row)
    
    # NEW: Styled dataframe (only visible columns)
    visible_cols = ['Market', 'UP/DOWN', 'Size', 'Price', 'Status', 'Updated']
    styled_df = df[visible_cols].style.apply(highlight_recent, axis=1)
    
    st.dataframe(
        styled_df,
        use_container_width=True,
        height=500,
        hide_index=True,
        column_config={
            "Market": st.column_config.TextColumn("Market", width="medium"),
            "Status": st.column_config.TextColumn("Status", width="medium")
        }
    )
    
    # Fixed: Track max_ts for true "Newest"
    max_ts = 0
    for _, row in df.iterrows():  # Use df since ts_raw available
        max_ts = max(max_ts, row['ts_raw'])
    
    up_bets = len(df[df['UP/DOWN'] == '🟢 UP'])
    newest_sec = now_ts - max_ts
    newest_min = newest_sec // 60
    newest_secs = newest_sec % 60
    newest_str = f"{newest_min}m {newest_secs}s" if newest_min > 0 else f"{newest_secs}s"   

    window_sec = now_ts - min_ts
    window_min = window_sec // 60
    window_secs = window_sec % 60
    window_str = f"{window_min}m {window_secs}s" if window_min > 0 else f"{window_secs}s"
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🟢 UP Bets", up_bets)
    with col2:
        st.metric("🔴 DOWN Bets", len(df) - up_bets)
    with col3:
        st.metric("🟢 Newest", newest_str + " ago")
    with col4:
        st.metric("📊 Span", window_str)

track_0x8dxd()

if st.button("🔄 Force Refresh"):
    st.rerun()
