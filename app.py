import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time
import pytz
import re
import json
from typing import List, Dict, Any

# ✅ AUTO-REFRESH (add "streamlit-autorefresh" to requirements.txt)
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=5000, limit=None, key="crypto_bot")  # 5s infinite
except ImportError:
    st.warning("🔄 Add `streamlit-autorefresh` to requirements.txt for auto-refresh")

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Tracker - Last 15 Min")
st.info("🟢 Live crypto-only | UP/DOWN focus | Last 15min")

if 'refresh_count' not in st.session_state:
    st.session_state.refresh_count = 0
st.session_state.refresh_count += 1

# Live EST clock
est = pytz.timezone('US/Eastern')
now_est = datetime.now(est)
time_24 = now_est.strftime('%H:%M:%S')
time_12 = now_est.strftime('%I:%M:%S %p')
st.caption(f"🕐 Current EST: {now_est.strftime('%Y-%m-%d')} {time_24} ({time_12}) ET | Auto 5s ✓ #{st.session_state.refresh_count}")

st.sidebar.title("⚙️ Settings")
MINUTES_BACK = st.sidebar.slider("⏰ Minutes back", 15, 120, 30, 5)
now_ts = int(time.time())
st.sidebar.caption(f"From: {datetime.fromtimestamp(now_ts - MINUTES_BACK*60, est).strftime('%H:%M %p ET')}")

@st.cache_data(ttl=2)
def safe_fetch(url: str) -> List[Dict[str, Any]]:
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return data[:500]
    except json.JSONDecodeError:
        pass
    except Exception:
        pass
    return []

def is_crypto(item: Dict[str, Any]) -> bool:
    title = str(item.get('title') or item.get('question') or '').lower()
    tickers = ['btc', 'eth', 'sol', 'xrp', 'ada', 'doge', 'shib', 'link', 'avax', 'matic', 'dot', 'uni', 'bnb', 'usdt', 'usdc']
    full_names = ['bitcoin', 'ethereum', 'solana', 'ripple', 'xrp', 'cardano', 'dogecoin', 'shiba', 'chainlink', 'avalanche', 'polygon', 'polkadot', 'uniswap', 'binance coin']
    return any(t in title for t in tickers) or any(f in title for f in full_names)

def get_up_down(item: Dict[str, Any]) -> str:
    fields = ['outcome', 'side', 'answer', 'choice', 'direction']
    text = ' '.join(str(item.get(f, '')).lower() for f in fields)
    title = str(item.get('title', item.get('question', ''))).lower()
    
    if 'yes' in text or 'buy' in text or 'long' in text: return "🟢 UP"
    if 'no' in text or 'sell' in text or 'short' in text: return "🔴 DOWN"
    
    if any(word in title for word in ['above', 'higher', 'rise', 'up', 'moon']): return "🟢 UP"
    if any(word in title for word in ['below', 'lower', 'drop', 'down', 'crash']): return "🔴 DOWN"
    
    price_words = ['$', 'usd', 'price']
    if any(p in title for p in price_words):
        if '>' in title or '>=' in title: return "🟢 UP"
        if '<' in title or '<=' in title: return "🔴 DOWN"
    
    if any(word in title for word in ['1h', 'hour', '15m', 'will']):
        if any(word in title for word in ['yes', 'will', 'reach']): return "🟢 UP"
        else: return "🔴 DOWN"
    
    return "➖ ?"

def get_status(item: Dict[str, Any], now_ts: int) -> str:
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
            
            if 'pm' in suffix.lower() or 'p' in suffix.lower(): hour = (hour % 12) + 12
            elif 'am' in suffix.lower() or 'a' in suffix.lower(): hour = hour % 12
            
            if 0 <= hour <= 23 and 0 <= minute < 60:
                decimal_h = hour + (minute / 60.0)
                title_times.append(decimal_h)
        except ValueError:
            continue
    
    if not title_times: return "🟢 ACTIVE (no timer)"
    
    max_h = max(title_times)
    if now_decimal >= max_h: return "⚫ EXPIRED"
    
    disp_h = int(max_h % 12) or 12
    disp_m = f":{int((max_h % 1)*60):02d}" if (max_h % 1) > 0.1 else ""
    ampm = 'PM' if max_h >= 12 else 'AM'
    return f"🟢 ACTIVE (til ~{disp_h}{disp_m} {ampm} ET)"

@st.cache_data(ttl=30)
def track_0x8dxd():
    trader = "0x63ce342161250d705dc0b16df89036c8e5f9ba9a".lower()
    now_ts = int(time.time())
    ago_ts = now_ts - (MINUTES_BACK * 60)
    
    all_raw = []
    offset = 0
    while len(all_raw) < 2000:
        url = f"https://data-api.polymarket.com/trades?user={trader}&limit=500&offset={offset}"
        batch = safe_fetch(url)
        if not batch: break
        all_raw.extend(batch)
        offset += 500
        if len(batch) < 500: break
    
    st.sidebar.info(f"📊 API: {len(all_raw)} total trades")
    
    filtered_data = []
    for item in all_raw:
        proxy = str(item.get("proxyWallet", "")).lower()
        user_field = str(item.get("user", "")).lower()
        if proxy != trader and user_field != trader: continue
        
        ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt')
        try:
            ts = int(float(ts_field)) if ts_field else now_ts
        except (ValueError, TypeError):
            continue
        
        if ts < ago_ts: continue
        
        if is_crypto(item):
            filtered_data.append(item)
    
    st.sidebar.success(f"✅ {len(filtered_data)} crypto trades | {MINUTES_BACK}min")
    
    if not filtered_data:
        st.info("No crypto trades found")
        return
    
    df_data = []
    for item in filtered_data[-200:]:
        updown = get_up_down(item)
        title = str(item.get('title') or item.get('question') or '-')
        short_title = (title[:85] + '...') if len(title) > 90 else title
        
        size_raw = item.get('size', 0)
        try:
            size_val = float(str(size_raw).replace('$', '').replace(',', ''))
        except (ValueError, TypeError):
            size_val = 0.0
        
        price_raw = item.get('curPrice', item.get('price', '-'))
        if isinstance(price_raw, (int, float)):
            price_val = f"${price_raw:.2f}"
        else:
            price_val = str(price_raw)
        
        ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt') or now_ts
        try:
            ts = int(float(ts_field))
        except (ValueError, TypeError):
            ts = now_ts
        update_str = datetime.fromtimestamp(ts, est).strftime('%I:%M:%S %p ET')
        status_str = get_status(item, now_ts)
        age_sec = now_ts - ts
        
        df_data.append({
            'Market': short_title, 'UP/DOWN': updown, 'Size': f"${size_val:.0f}",
            'Price': price_val, 'Status': status_str, 'Updated': update_str, 'age_sec': age_sec
        })
    
    df = pd.DataFrame(df_data)
    if df.empty: return
    
    def status_priority(x): 
        x_lower = str(x).lower()
        if 'expired' in x_lower: return 1
        elif 'no timer' in x_lower: return 2
        return 0
    
    df['priority'] = df['Status'].apply(status_priority)
    df['parsed_updated'] = pd.to_datetime(df['Updated'], format='%I:%M:%S %p ET', errors='coerce')
    df = df.sort_values(['priority', 'parsed_updated'], ascending=[True, False]).drop(['priority', 'parsed_updated'], axis=1)
    
    st.success(f"✅ {len(df)} LIVE crypto bets ({MINUTES_BACK}min window)")
    st.caption(f"📈 Filtered from sidebar: {len(filtered_data)} raw trades")

    col1, col2 = st.columns(2)
    col1.metric("⏰ Window", f"{MINUTES_BACK}min")
    col2.metric("📊 Raw Trades", f"{len(filtered_data)}")
    
    recent_mask = df['age_sec'] <= 30
    def highlight_recent(row):
        idx = row.name
        if idx < len(recent_mask) and recent_mask.iloc[idx]:
            return ['background-color: rgba(0, 255, 0, 0.15)'] * len(row)
        return [''] * len(row)
    
    visible_cols = ['Market', 'UP/DOWN', 'Size', 'Price', 'Status', 'Updated']
    styled_df = df[visible_cols].style.apply(highlight_recent, axis=1)
    
    st.dataframe(styled_df, use_container_width=True, height=500, hide_index=True,
                column_config={"Market": st.column_config.TextColumn(width="medium"),
                              "Status": st.column_config.TextColumn(width="medium")})
    
    newest_sec = df['age_sec'].min()
    newest_str = f"{int(newest_sec)//60}m {int(newest_sec)%60}s ago"
    span_sec = df['age_sec'].max()
    span_str = f"{int(span_sec)//60}m {int(span_sec)%60}s"
    
    up_bets = len(df[df['UP/DOWN'] == '🟢 UP'])
    
    bet_col1, bet_col2, bet_col3, bet_col4 = st.columns(4)
    bet_col1.metric("🟢 UP Bets", up_bets)
    bet_col2.metric("🔴 DOWN Bets", len(df) - up_bets)
    bet_col3.metric("🟢 Newest", newest_str)
    bet_col4.metric("📊 Span", span_str)

if st.button("🔄 Force Refresh NOW", use_container_width=True):
    st.rerun()

track_0x8dxd()
