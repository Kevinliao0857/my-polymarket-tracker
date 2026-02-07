import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time
import json
import re
from typing import List, Dict, Any
import websocket
import threading
from collections import deque


from .config import EST, TRADER
from .filters import is_crypto, get_up_down


# 🆕 Global live trades cache (thread-safe deque)
live_trades: deque = deque(maxlen=2000)



@st.cache_data(ttl=5)
def track_0x8dxd(minutes_back: int) -> pd.DataFrame:
    now_ts = int(time.time())
    ago_ts = now_ts - (minutes_back * 60)
  
    # 🆕 PRIORITY 1: Live WS trades (1s fresh)
    recent_live = [t for t in live_trades if (t.get('timestamp') or 0) >= ago_ts]
    ws_count = len(recent_live)
  
    if ws_count > 0:
        st.sidebar.success(f"🚀 LIVE TRADES: {ws_count} (WS working!)")
    else:
        st.sidebar.warning("⚠️ No live trades yet—WS warming up...")

    # PRIORITY 2: REST fallback (historical)
    all_raw = []
    offset = 0
    while len(all_raw) < 2000:
        url = f"https://data-api.polymarket.com/trades?user={TRADER}&limit=500&offset={offset}"
        batch = safe_fetch(url)
        if not batch: break
        all_raw.extend(batch)
        offset += 500
        if len(batch) < 500: break
  
    # Filter REST for recent + our trader
    rest_recent = []
    for item in all_raw:
        proxy = str(item.get("proxyWallet", "")).lower()
        if proxy != TRADER.lower(): continue
        
        ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt') or item.get('ts')
        try:
            ts = int(float(ts_field)) if ts_field else now_ts
        except (ValueError, TypeError):
            continue
        
        if ts >= ago_ts:
            rest_recent.append(item)
  
    # 🆕 Combine: live + recent REST (dedupe by tx hash)
    combined = recent_live + rest_recent
    seen_tx = set()
    unique_combined = []
    for item in combined:
        tx_hash = str(item.get('transactionHash', '')).lower()
        if tx_hash not in seen_tx:
            seen_tx.add(tx_hash)
            unique_combined.append(item)
    
    # 🆕 Sort by timestamp DESC, then filter crypto, take 200
    unique_combined.sort(key=lambda x: x.get('timestamp', 0) or x.get('updatedAt', 0) or 0, reverse=True)
    filtered_data = [item for item in unique_combined if is_crypto(item)][:200]
  
    st.sidebar.info(f"📊 REST: {len(all_raw)} total | WS: {ws_count} live")
    st.sidebar.success(f"✅ {len(filtered_data)} crypto trades | {minutes_back}min")
  
    if not filtered_data:
        return pd.DataFrame()
  
    df_data = []
    for item in filtered_data:  # Latest 200 already
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
