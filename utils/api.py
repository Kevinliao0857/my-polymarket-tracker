import streamlit as st
import pandas as pd
import requests
import threading
import time
from datetime import datetime
from typing import Any, List

from .config import EST, TRADER
from .filters import is_crypto, get_up_down
from .data import safe_fetch
from .status import get_status_hybrid
from .websocket import rtds_listener, live_trades

# WS startup (unchanged)
if 'ws_started' not in st.session_state:
    threading.Thread(target=rtds_listener, daemon=True).start()
    st.session_state.ws_started = True

@st.cache_data(ttl=30)
def get_latest_bets(address: str, limit: int = 200) -> List[dict]:
    """Get trader's latest BUY trades from /activity endpoint"""
    try:
        url = f"https://data-api.polymarket.com/activity?user={address}&limit={limit}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            activities = response.json()
            # Filter TRADE + BUY only (copy-trading focus)
            buy_trades = [a for a in activities 
                         if a.get("type") == "TRADE" and a.get("side") == "BUY"]
            return buy_trades
    except:
        pass
    return []

@st.cache_data(ttl=10)  # Live data - short cache
def track_0x8dxd(minutes_back: int) -> pd.DataFrame:
    now_ts = int(time.time())
    ago_ts = now_ts - (minutes_back * 60)
    
    # 1. Live WS (unchanged)
    recent_live = [t for t in live_trades if (t.get('timestamp') or 0) >= ago_ts]
    ws_count = len(recent_live)
    
    if ws_count > 0:
        st.sidebar.success(f"🚀 LIVE TRADES: {ws_count} (WS working!)")
    else:
        st.sidebar.warning("⚠️ No live trades yet—WS warming up...")
    
    # 2. NEW: Activity endpoint (much better than /trades)
    latest_bets = get_latest_bets(TRADER, limit=500)  # Single call, no pagination needed
    rest_recent = []
    for item in latest_bets:
        ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt')
        try:
            ts = int(float(ts_field)) if ts_field else now_ts
        except (ValueError, TypeError):
            continue
        
        if ts >= ago_ts:
            rest_recent.append(item)
    
    # 3. Combine + dedupe (unchanged)
    combined = recent_live + rest_recent
    seen_tx = set()
    unique_combined = []
    for item in combined:
        tx_hash = str(item.get('transactionHash', '')).lower()
        if tx_hash not in seen_tx:
            seen_tx.add(tx_hash)
            unique_combined.append(item)
    
    unique_combined.sort(key=lambda x: x.get('timestamp', 0) or x.get('updatedAt', 0) or 0, reverse=True)
    max_items = max(200, minutes_back * 15)
    filtered_data = [item for item in unique_combined if is_crypto(item)][:max_items]
    
    rest_count = len(latest_bets)
    st.sidebar.info(f"📊 REST: {rest_count} total | WS: {ws_count} live")
    st.sidebar.success(f"✅ {len(filtered_data)} crypto trades | {minutes_back}min")
    
    if not filtered_data:
        return pd.DataFrame()
    
    # 4. Build DF (unchanged - your logic works great)
    df_data = []
    for item in filtered_data:
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
            'Market': short_title, 'UP/DOWN': updown, 'Size': f"${size_val:.2f}",
            'Price': price_val, 'Status': status_str, 'Updated': update_str, 'age_sec': age_sec
        })
    
    df = pd.DataFrame(df_data)
    if df.empty: 
        return df
    
    df = df.sort_values('age_sec')  # Newest first
    return df

@st.cache_data(ttl=300)
def get_profile_name(address: str) -> str:
    """Get trader profile name from Gamma API"""
    try:
        url = f"https://gamma-api.polymarket.com/public-profile?address={address}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            profile = response.json()
            return profile.get("name") or profile.get("pseudonym") or f"{address[:10]}..."
    except:
        pass
    return f"{address[:10]}..."
