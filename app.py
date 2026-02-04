import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time as time_module  # Avoid conflict with datetime.time
import pytz
import re

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Tracker - Last 15 Min")

st.info("🟢 Live crypto-only | UP/DOWN focus | Last 15min")

# Live EST clock
est = pytz.timezone('US/Eastern')

@st.cache_data(ttl=1)
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

def is_crypto(item):
    text = str(item).lower()
    crypto_symbols = ['btc', 'eth', 'sol', 'xrp', 'ada', 'doge', 'shib', 'link', 'avax', 'matic', 'dot', 'uni']
    return any(sym in text for sym in crypto_symbols) or 'bitcoin' in text or 'ethereum' in text or 'solana' in text

def get_up_down(item):
    fields = ['outcome', 'side', 'answer', 'choice', 'direction']
    text = ' '.join(str(item.get(f, '')) for f in fields).lower()
    title = str(item.get('title', item.get('question', ''))).lower()
    
    if any(word in text for word in ['yes', 'buy', 'long']):
        return "🟢 UP"
    if any(word in text for word in ['no', 'sell', 'short']):
        return "🔴 DOWN"
    
    if any(word in title for word in ['above', 'higher', 'rise', 'up']):
        return "🟢 UP"
    if any(word in title for word in ['below', 'lower', 'drop', 'down']):
        return "🔴 DOWN"
    
    price_words = ['$', 'usd', 'price']
    if any(p in title for p in price_words):
        if any(op in title for op in ['>', '>=']):
            return "🟢 UP"
        if any(op in title for op in ['<', '<=']):
            return "🔴 DOWN"
    
    time_words = ['1h', 'hour', '15m', 'will']
    if any(word in title for word in time_words):
        if any(word in title for word in ['yes', 'will', 'reach']):
            return "🟢 UP"
        return "🔴 DOWN"
    
    return "➖ ?"

def get_status(item, now_ts):
    title = str(item.get('title') or item.get('question') or '')
    now_dt = datetime.fromtimestamp(now_ts, est)
    
    # Date patterns
    date_patterns = [
        r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?)',
        r'(\d{1,2}-\d{1,2}(?:-\d{2,4})?)',
        r'(\d{4}-\d{1,2}-\d{1,2})',
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?',
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?',
    ]
    time_patterns = [
        r'(\d{1,2}):?(\d{2})\s*(am?|pm?)',
        r'(\d{1,2})\s*(am?|pm?)',
        r'at\s+(\d{1,2})(?::(\d{2}))?\s*(am?|pm?)',
    ]
    
    dates = []
    hours = []
    ampm = []
    
    for pattern in date_patterns:
        dates.extend(re.findall(pattern, title, re.I))
    
    for pattern in time_patterns:
        matches = re.findall(pattern, title, re.I)
        for match in matches:
            if match[0]:
                hours.append(int(match[0]))
            if len(match) > 2 and match[2]:
                ampm.append(match[2].lower())
    
    if not hours:
        hour_matches = re.findall(r'\b(\d{1,2})\b', title)
        for h_str in hour_matches:
            h = int(h_str)
            if 1 <= h <= 12:
                hours.append(h)
    
    if not hours:
        return "🟢 ACTIVE (no timer)"
    
    deadline_hour = max(hours)
    deadline_min = 59
    
    if ampm:
        if any('pm' in p for p in ampm) and deadline_hour < 12:
            deadline_hour += 12
        elif any('am' in p for p in ampm) and deadline_hour == 12:
            deadline_hour = 0
    
    # Parse date
    parsed_date = None
    for date_str in dates:
        month_match = re.match(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?', date_str, re.I)
        if month_match:
            month_abbr = month_match.group(1).lower()
            day = int(month_match.group(2))
            month_map = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
            if month_abbr in month_map:
                try:
                    parsed_date = now_dt.date().replace(month=month_map[month_abbr], day=day)
                    break
                except:
                    pass
        
        for fmt in ['%m/%d/%Y', '%m/%d/%y', '%m-%d-%Y', '%m-%d-%y', '%Y-%m-%d']:
            try:
                temp_date = datetime.strptime(date_str, fmt).date()
                if temp_date.year < 1900:
                    temp_date = temp_date.replace(year=now_dt.year)
                parsed_date = temp_date
                break
            except ValueError:
                pass
    
    if parsed_date:
        if parsed_date < now_dt.date():
            return "⚫ EXPIRED (past date)"
        deadline_dt = datetime.combine(parsed_date, datetime.time(deadline_hour, deadline_min))
    else:
        deadline_dt = now_dt.replace(hour=deadline_hour, minute=deadline_min, second=0, microsecond=0)
    
    if now_dt > deadline_dt:
        return "⚫ EXPIRED"
    
    return f"🟢 ACTIVE (til ~{deadline_hour:02d}:{deadline_min:02d} ET)"

@st.cache_data(ttl=1)
def track_0x8dxd():
    trader = "0x8dxd"
    now_ts = int(time_module.time())
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
            if ts >= fifteen_min_ago and is_crypto(item):
                key = str(item.get('title') or item.get('question') or '-')[:100]
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
        short_title = (title[:85] + '...') if len(title) > 90 else title
        
        size_val = float(item.get('size', 0))
        price_val = item.get('curPrice') or item.get('price', '-')
        if isinstance(price_val, (int, float)):
            price_val = f"${price_val:.2f}"
        
        ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt') or now_ts
        ts = int(float(ts_field)) if ts_field else now_ts
        min_ts = min(min_ts, ts)
        update_str = datetime.fromtimestamp(ts, est).strftime('%H:%M:%S ET')
        status_str = get_status(item, now_ts)
        
        row = {
            'Market': short_title,
            'UP/DOWN': updown,
            'Size': f"${size_val:.0f}",
            'Price': price_val,
            'Status': status_str,
            'Updated': update_str
        }
        df_data.append(row)
    
    df = pd.DataFrame(df_data)
    df = df.sort_values('Updated', ascending=False)
    
    st.success(f"✅ {len(df)} crypto bets (15min ET)")
    st.dataframe(df, use_container_width=True, height=500, column_config={
        "Market": st.column_config.TextColumn("Market", width="medium"),
        "Status": st.column_config.TextColumn("Status", width="small")
    })
    
    up_bets = len(df[df['UP/DOWN'] == '🟢 UP'])
    col1, col2, col3 = st.columns(3)
    col1.metric("🟢 UP Bets", up_bets)
    col2.metric("🔴 DOWN Bets", len(df) - up_bets)
    span_min = int((now_ts - min_ts) / 60)
    col3.metric("Newest", f"{span_min} min ago (ET)")

if st.button("🔄 Force Refresh"):
    st.rerun()

# 3s refresh loop
placeholder = st.empty()
refresh_count = 0
while True:
    refresh_count += 1
    now_est = datetime.now(est)
    with placeholder.container():
        track_0x8dxd()
        st.caption(f"🕐 {now_est.strftime('%H:%M:%S ET')} | Live ##{refresh_count}")
    time_module.sleep(3)
    st.rerun()
