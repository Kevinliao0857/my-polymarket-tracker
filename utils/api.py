import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time
import json
import re  # 🆕 ADDED explicit import
from typing import List, Dict, Any

from .config import EST, TRADER
from .filters import is_crypto, get_up_down

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
                    end_dt = pd.to_datetime(end_iso).tz_convert(EST)
                    return end_dt.strftime('%I:%M %p ET')
    except:
        pass
    return None

def get_status_hybrid(item: Dict[str, Any], now_ts: int) -> str:
    """🟢 Hybrid: API first → Regex fallback."""
    # 1. Try API exact time
    condition_id = str(item.get('conditionId') or item.get('marketId') or item.get('market', {}).get('conditionId') or '')
    slug = str(item.get('slug') or item.get('market', {}).get('slug') or '')
    
    end_str = get_market_enddate(condition_id, slug)
    now_est = datetime.fromtimestamp(now_ts, EST)
    
    if end_str:
        try:
            end_dt = datetime.strptime(end_str, '%I:%M %p ET').replace(tzinfo=EST)
            if now_est >= end_dt:
                return "⚫ EXPIRED"
            return f"🟢 ACTIVE (til {end_str}) 🟢"
        except:
            pass
    
    # 2. Regex fallback 🆕 FIXED: Safe str() everywhere
    title_safe = str(item.get('title') or item.get('question') or '').lower()
    now_decimal = now_est.hour + (now_est.minute / 60.0) + (now_est.second / 3600.0)
    
    time_pattern = r'(\d{1,2})(?::(\d{2}))?([ap]m|et)'
    matches = re.findall(time_pattern, title_safe)
    title_times = []
    
    for h_str, m_str, suffix in matches:
        try:
            hour = int(h_str)
            minute = int(m_str) if m_str else 0
            suffix_lower = str(suffix).lower()
            if 'pm' in suffix_lower or 'p' in suffix_lower: 
                hour = (hour % 12) + 12
            elif 'am' in suffix_lower or 'a' in suffix_lower: 
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

@st.cache_data(ttl=5)
def track_0x8dxd(minutes_back: int) -> pd.DataFrame:
    now_ts = int(time.time())
    ago_ts = now_ts - (minutes_back * 60)
    
    all_raw = []
    offset = 0
    while len(all_raw) < 2000:
        url = f"https://data-api.polymarket.com/trades?user={TRADER}&limit=500&offset={offset}"
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
        if proxy != TRADER and user_field != TRADER: continue
        
        ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt')
        try:
            ts = int(float(ts_field)) if ts_field else now_ts
        except (ValueError, TypeError):
            continue
        
        if ts < ago_ts: continue
        
        if is_crypto(item):
            filtered_data.append(item)
    
    st.sidebar.success(f"✅ {len(filtered_data)} crypto trades | {minutes_back}min")
    
    if not filtered_data:
        return pd.DataFrame()
    
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
        update_str = datetime.fromtimestamp(ts, EST).strftime('%I:%M:%S %p ET')
        
        status_str = get_status_hybrid(item, now_ts)
        age_sec = now_ts - ts
        
        df_data.append({
            'Market': short_title, 'UP/DOWN': updown, 'Size': f"${size_val:.0f}",
            'Price': price_val, 'Status': status_str, 'Updated': update_str, 'age_sec': age_sec
        })
    
    df = pd.DataFrame(df_data)
    if df.empty: return df
    
    df = df.sort_values('age_sec')  # Newest first
    return df
