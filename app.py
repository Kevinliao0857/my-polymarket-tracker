import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time
import pytz  # pip install pytz
import re  # For time parsing
# pip install streamlit-autorefresh
from streamlit_autorefresh import st_autorefresh

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Tracker - Last 15 Min")

st.info("🟢 Live crypto-only | UP/DOWN focus | Last 15min")

# Live EST clock (trader uses EST)
est = pytz.timezone('US/Eastern')
now_est = datetime.now(est)
time_24 = now_est.strftime('%H:%M:%S')
time_12 = now_est.strftime('%I:%M:%S %p')
st.caption(f"🕐 Current EST: {now_est.strftime('%Y-%m-%d')} {time_24} ({time_12}) ET | Auto 5s")

# AUTO-REFRESH EVERY 5s (replaces manual session_state + button)
st_autorefresh(interval=5000, limit=None, key="crypto_refresh")

@st.cache_data(ttl=2)  # Short TTL for live data
def safe_fetch(url):
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return data[:500]
    except:
        pass
    return []

def is_crypto(item):
    title = str(item.get('title') or item.get('question') or '').lower()
    tickers = ['btc', 'eth', 'sol', 'xrp', 'ada', 'doge', 'shib', 'link', 'avax', 'matic', 'dot', 'uni', 'bnb', 'usdt', 'usdc']
    full_names = ['bitcoin', 'ethereum', 'solana', 'ripple', 'xrp', 'cardano', 'dogecoin', 'shiba', 'chainlink', 'avalanche', 'polygon', 'polkadot', 'uniswap', 'binance coin']
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
    
    now_dt = datetime.fromtimestamp(now_ts, est)
    now_decimal = now_dt.hour + (now_dt.minute / 60.0) + (now_dt.second / 3600.0)
    
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

def fetch_crypto_data():
    trader = "0x63ce342161250d705dc0b16df89036c8e5f9ba9a".lower()
    now_ts = int(time.time())
    fifteen_min_ago = now_ts - 900
    
    urls = [f"https://data-api.polymarket.com/trades?user={trader}&limit=500&offset=0"]
    
    all_data = []
    for url in urls:
        raw_data = safe_fetch(url)
        
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
            if ts >= fifteen_min_ago and is_crypto(item):
                all_data.append(item)
    
    all_data = all_data[-200:]
    
    if not all_data:
        return pd.DataFrame()
    
    df_data = []
    min_ts = now_ts
    max_ts = 0
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
        max_ts = max(max_ts, ts)
        update_str = datetime.fromtimestamp(ts, est).strftime('%I:%M:%S %p ET')
        status_str = get_status(item, now_ts)
        
        row = {
            'Market': short_title,
            'UP/DOWN': updown,
            'Size': f"${size_val:.0f}",
            'Price': price_val,
            'Status': status_str,
            'Updated': update_str,
            'ts_raw': ts,
            'global_min_ts': min_ts,
            'global_max_ts': max_ts
        }
        df_data.append(row)
    
    df = pd.DataFrame(df_data)
    if df.empty:
        return df
    
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
    
    return df

# FETCH DATA EVERY RUN (auto-refresh handles timing)
current_df = fetch_crypto_data()

def display_data(df, now_ts):
    st.success(f"✅ {len(df)} crypto bets (15min ET)")
    
    def highlight_recent(row, threshold=30):
        if row.get('ts_raw', 9999) >= (now_ts - threshold):
            return ['background-color: rgba(0, 255, 0, 0.15)'] * len(row)
        return [''] * len(row)
    
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
    
    # PYTHON-ONLY LIVE TIMERS (tick every 5s auto-refresh)
    if not df.empty:
        max_ts = df['global_max_ts'].iloc[0]
        min_ts = df['global_min_ts'].iloc[0]
        
        newest_sec = now_ts - max_ts
        newest_min = newest_sec // 60
        newest_str = f"{newest_min}m {newest_sec % 60}s ago"
        
        span_sec = now_ts - min_ts
        span_min = span_sec // 60
        span_str = f"{span_min}m {span_sec % 60}s"
        
        col1, col2, col3, col4 = st.columns(4)
        up_count = len(df[df['UP/DOWN'] == '🟢 UP'])
        with col1:
            st.metric("🟢 UP Bets", up_count)
        with col2:
            st.metric("🔴 DOWN Bets", len(df) - up_count)
        with col3:
            st.metric("🟢 Newest", newest_str)
        with col4:
            st.metric("📊 Span", span_str)
        
        # Extra live ticker line
        st.markdown(f"**🔄 Live: Newest {newest_str} | Span {span_str} | Refresh #{st_autorefresh.count()}**")

if not current_df.empty:
    now_ts = int(time.time())
    display_data(current_df, now_ts)
    now_est = datetime.now(est)
    time_24 = now_est.strftime('%H:%M:%S')
    time_12 = now_est.strftime('%I:%M:%S %p')
    st.caption(f"🕐 {time_24} ({time_12}) ET | Auto every 5s")
else:
    st.info("No crypto activity in last 15 min")
