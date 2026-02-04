import streamlit as st
import requests
import pandas as pd
from datetime import datetime, time
import time
import pytz
import re

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Tracker - Last 15 Min")

st.info("🟢 Live crypto-only | UP/DOWN focus | Last 15min")

# Live EST clock
est = pytz.timezone('US/Eastern')

@st.cache_data(ttl=1)  # Ultra-fresh 1s cache
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
    text = ' '.join(str(item.get(f, '')).lower() for f in fields)
    title = str(item.get('title', item.get('question', ''))).lower()
    
    if 'yes' in text or 'buy' in text or 'long' in text:
        return "🟢 UP"
    if 'no' in text or 'sell' in text or 'short' in text:
        return "🔴 DOWN"
    
    if any(word in title for word in ['above', 'higher', 'rise', 'up']):
        return "🟢 UP"
    if any(word in title for word in ['below', 'lower', 'drop', 'down']):
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
        return "🔴 DOWN"
    
    return "➖ ?"

def get_status(item, now_ts):
    title = str(item.get('title') or item.get('question') or '')
    now_dt = datetime.fromtimestamp(now_ts, est)
    now_hour = now_dt.hour
    
    # Enhanced regex patterns for dates and times
    date_patterns = [
        r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?)',  # 2/4 or 2/4/26
        r'(\d{1,2}-\d{1,2}(?:-\d{2,4})?)',  # 2-4 or 2-4-26
        r'(\d{4}-\d{1,2}-\d{1,2})',         # 2026-02-04
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?',  # Feb 4, Dec 31st
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?',  # Full months
    ]
    time_patterns = [
        r'(\d{1,2}):?(\d{2})\s*(am?|pm?)',  # 3:45pm, 15:30
        r'(\d{1,2})\s*(am?|pm?)',           # 3pm
        r'at\s+(\d{1,2})(?::(\d{2}))?\s*(am?|pm?)',
    ]
    
    # Extract components
    dates = []
    hours = []
    minutes_list = []
    ampm = []
    
    # Dates
    for pattern in date_patterns:
        dates.extend(re.findall(pattern, title, re.I))
    
    # Times
    for pattern in time_patterns:
        matches = re.findall(pattern, title, re.I)
        for match in matches:
            if len(match) >= 1:
                h = int(match[0])
                hours.append(h)
            if len(match) >= 2 and match[1]:
                m = int(match[1])
                minutes_list.append(m)
            if len(match) >= 3 and match[2]:
                ampm.append(match[2].lower())
    
    # Fallback hour extraction (1-2 digits)
    if not hours:
        hour_matches = re.findall(r'\b(\d{1,2})\b', title)
        for hour_str in hour_matches:
            hour = int(hour_str)
            if 1 <= hour <= 12:
                hours.append(hour)
    
    if not hours:
        return "🟢 ACTIVE (no timer)"
    
    # Use latest hour as deadline
    max_hour = max(hours)
    deadline_hour = max_hour
    deadline_min = 59  # End of hour
    
    # AM/PM normalization
    if ampm:
        if any('pm' in p for p in ampm) and max_hour < 12:
            deadline_hour += 12
        elif any('am' in p for p in ampm) and max_hour == 12:
            deadline_hour = 0
    
    # Parse date
    parsed_date = None
    for date_str in dates:
        # Month names
        month_match = re.match(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?', date_str, re.I)
        if month_match:
            month_abbr = month_match.group(1).lower()
            day = int(month_match.group(2))
            month_map = {'jan':1, 'feb':2, 'mar':3, 'apr':4, 'may':5, 'jun':6,
                         'jul':7, 'aug':8, 'sep':9, 'oct':10, 'nov':11, 'dec':12}
            month_num = month_map.get(month_abbr)
            if month_num:
                try:
                    parsed_date = now_dt.date().replace(month=month_num, day=day)
                    break
                except ValueError:
                    continue
        
        # Numeric formats
        for fmt in ['%m/%d/%Y', '%m/%d/%y', '%m-%d-%Y', '%m-%d-%y', '%Y-%m-%d']:
            try:
                temp_date = datetime.strptime(date_str, fmt).date()
                if temp_date.year < 100:  # Two-digit year
                    temp_date = temp_date.replace(year=now_dt.year)
                parsed_date = temp_date
                break
            except:
                pass
    
    # Build deadline datetime
    if parsed_date:
        if parsed_date < now_dt.date():
            return "⚫ EXPIRED (past date)"
        deadline_dt = datetime.combine(parsed_date, time(deadline_hour, deadline_min))
    else:
        deadline_dt = now_dt.replace(hour=deadline_hour, minute=deadline_min, second=0)
    
    if now_dt > deadline_dt:
        return "⚫ EXPIRED"
    
    return f"🟢 ACTIVE (til ~{deadline_hour:02d}:{deadline_min:02d} ET)"

@st.cache_data(ttl=1)
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
        price_val = item.get('curPrice', item.get('price', '-'))
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

# ULTRA-FAST 3s refresh loop
placeholder = st.empty()
refresh_count = 0
while True:
    refresh_count += 1
    now_est = datetime.now(est)
    with placeholder.container():
        track_0x8dxd()
        st.caption(f"🕐 {now_est.strftime('%H:%M:%S ET')} | Live ##{refresh_count}")
    time.sleep(3)
    st.rerun()
