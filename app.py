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

if 'refresh_count' not in st.session_state:
    st.session_state.refresh_count = 0
st.session_state.refresh_count += 1

# MAIN TITLE
st.markdown(f"# ₿ 0x8dxd Crypto Bot Tracker")

# Live EST clock
est = pytz.timezone('US/Eastern')
now_est = datetime.now(est)
time_24 = now_est.strftime('%H:%M:%S')
time_12 = now_est.strftime('%I:%M:%S %p')
st.caption(f"🕐 Current EST: {now_est.strftime('%Y-%m-%d')} {time_24} ({time_12}) ET | Auto 5s ✓ #{st.session_state.refresh_count}🔄")

# SIDEBAR LOCATION
st.sidebar.title("⚙️ Settings")
MINUTES_BACK = st.sidebar.slider("⏰ Minutes back", 15, 120, 30, 5)
now_ts = int(time.time())
st.sidebar.caption(f"From: {datetime.fromtimestamp(now_ts - MINUTES_BACK*60, est).strftime('%H:%M %p ET')}")

if st.sidebar.button("🔄 Force Refresh", use_container_width=True):
    st.rerun()

if st.sidebar.button("🧪 Test New Status API"):
    st.session_state.test_api = True  # 🆕 ADDED THIS LINE
    st.rerun()

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


# 🆕 NEW API FUNCTIONS - EXACT END TIMES
@st.cache_data(ttl=60)
def get_market_enddate(condition_id: str, slug: str = None) -> str:
    """Get exact end time from Polymarket Gamma API."""
    try:
        if condition_id:
            url = f"https://gamma-api.polymarket.com/markets?conditionIds={condition_id}"
        elif slug:
            url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
        else:
            return None
            
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            markets = resp.json()
            if markets:
                end_iso = markets[0].get('endDateIso')
                if end_iso:
                    end_dt = pd.to_datetime(end_iso).tz_convert('US/Eastern')
                    return end_dt.strftime('%I:%M %p ET')
    except:
        pass
    return None


def get_status_hybrid(item: Dict[str, Any], now_ts: int) -> str:
    """🟢 Hybrid: API first → Regex fallback."""
    # 1. Try API exact time
    condition_id = item.get('conditionId') or item.get('marketId') or item.get('market', {}).get('conditionId')
    slug = item.get('slug') or item.get('market', {}).get('slug')
    
    end_str = get_market_enddate(condition_id, slug)
    now_est = datetime.fromtimestamp(now_ts, est)
    
    if end_str:
        try:
            end_dt = datetime.strptime(end_str, '%I:%M %p ET').replace(tzinfo=est)
            if now_est >= end_dt:
                return "⚫ EXPIRED"
            return f"🟢 ACTIVE (til {end_str}) 🟢"  # 🟢 = API win!
        except:
            pass
    
    # 2. Regex fallback
    title = str(item.get('title') or item.get('question') or '').lower()
    now_decimal = now_est.hour + (now_est.minute / 60.0) + (now_est.second / 3600.0)
    
    time_pattern = r'(\d{1,2})(?::(\d{1,2}))?([ap]m|et)'
    matches = re.findall(time_pattern, title)
    title_times = []
    
    for h_str, m_str, suffix in matches:
        try:
            hour = int(h_str)
            minute = int(m_str) if m_str else 0
            if 'pm' in suffix.lower() or 'p' in suffix.lower(): 
                hour = (hour % 12) + 12
            elif 'am' in suffix.lower() or 'a' in suffix.lower(): 
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
    return f"🟢 ACTIVE (til ~{disp_h}{disp_m} {ampm})"

def get_pnl_result(item: Dict[str, Any]) -> str:
    """🟢 +$47  🔴 -$12  ➖ Pending"""
    status = str(item.get('status', '')).lower()
    if 'expired' not in status and 'resolved' not in status:
        return "➖ Pending"
    
    # Try direct PnL fields from trades API
    realized_pnl = item.get('realizedPnl') or item.get('pnl')
    if realized_pnl:
        pnl_str = f"${float(realized_pnl):.0f}"
        return f"🟢 {pnl_str}" if float(realized_pnl) >= 0 else f"🔴 {pnl_str}"
    
    # Fallback: simple buy price → $1/$0 on resolution
    size = float(str(item.get('size', 0)).replace('$', '').replace(',', ''))
    price_paid = float(item.get('price', 0) or item.get('curPrice', 0))
    if size > 0 and price_paid > 0:
        # UP bet won → $1 - price_paid per share
        up_bet = "🟢 up" in str(item.get('side', '')).lower()
        outcome = item.get('outcome', '').lower()
        if up_bet and 'yes' in outcome:
            profit = size * (1.0 - price_paid)
        elif not up_bet and 'no' in outcome:
            profit = size * (1.0 - price_paid)
        else:
            profit = -size * price_paid  # Lost investment
        
        pnl_str = f"${profit:.0f}"
        return f"🟢 {pnl_str}" if profit >= 0 else f"🔴 {pnl_str}"
    
    return "➖ Resolved?"

@st.cache_data(ttl=5)
def track_0x8dxd(minutes_back):  # Receives slider value
    trader = "0x63ce342161250d705dc0b16df89036c8e5f9ba9a".lower()
    now_ts = int(time.time())
    ago_ts = now_ts - (minutes_back * 60)
    
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
    
    # 🆕 TEST BUTTON RESULT
    if 'test_api' in st.session_state:
        sample = filtered_data[0]
        end = get_market_enddate(sample.get('conditionId'), sample.get('slug'))
        st.sidebar.success(f"✅ Test: Sample ends {end or 'No data'}")
        del st.session_state.test_api
    
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
        
        # 🆕 CHANGED: Use API status (exact end times!)
        status_str = get_status_hybrid(item, now_ts)  # NEW HYBRID
        age_sec = now_ts - ts
        
        df_data.append({
            'Market': short_title, 'UP/DOWN': updown, 'Size': f"${size_val:.0f}",
            'Price': price_val, 'Status': status_str, 'PnL': get_pnl_result(item), 'Updated': update_str, 'age_sec': age_sec
        })
    
    df = pd.DataFrame(df_data)
    if df.empty: return
    
    def status_priority(x): 
        x_lower = str(x).lower()
        if 'expired' in x_lower: return 1
        elif 'no enddate' in x_lower: return 2
        return 0
    
    df = df.sort_values('age_sec')  # Newest first (smallest age_sec)

    newest_sec = df['age_sec'].min()
    newest_str = f"{int(newest_sec)//60}m {int(newest_sec)%60}s ago"
    span_sec = df['age_sec'].max()
    span_str = f"{int(span_sec)//60}m {int(span_sec)%60}s"
    up_bets = len(df[df['UP/DOWN'] == '🟢 UP'])


    st.info(f"✅ {len(df)} LIVE crypto bets ({MINUTES_BACK}min window)")
    st.caption(f"📈 Filtered from sidebar: {len(filtered_data)} raw trades")
    
    recent_mask = df['age_sec'] <= 30
    def highlight_recent(row):
        if recent_mask.iloc[row.name]:  # Use global mask + row index
            return ['background-color: rgba(0, 255, 0, 0.15)'] * 6  # 6 visible cols
        return [''] * 6
    
    visible_cols = ['Market', 'UP/DOWN', 'Size', 'Price', 'Status', 'PnL', 'Updated']  # ✅ ADD 'PnL'
    styled_df = df[visible_cols].style.apply(highlight_recent, axis=1)

    # Update highlight (7 columns now)
    def highlight_recent(row):
        if recent_mask.iloc[row.name]:
            return ['background-color: rgba(0, 255, 0, 0.15)'] * 7  # 7 cols
        return [''] * 7
    
    st.markdown("""
    <div style='display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 10px;'>
        <span><b>🟢 UP:</b> {}</span>
        <span><b>🔴 DOWN:</b> {}</span>
        <span>Newest: {}</span>
        <span>Span: {}</span>
    </div>
    """.format(up_bets, len(df)-up_bets, newest_str, span_str), unsafe_allow_html=True)

    st.dataframe(styled_df, use_container_width=True, height=400, hide_index=True,
                column_config={"Market": st.column_config.TextColumn(width="medium"),
                              "Status": st.column_config.TextColumn(width="medium"), 
                              "PnL": st.column_config.TextColumn(width="small")})  

track_0x8dxd(MINUTES_BACK)

