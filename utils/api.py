import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time
import json
import re
from typing import List, Dict, Any
import websocket  # 🆕 For RTDS WebSocket
import threading
from collections import deque


from .config import EST, TRADER
from .filters import is_crypto, get_up_down


# 🆕 Global live trades cache (thread-safe deque)
live_trades: deque = deque(maxlen=2000)

def rtds_listener():
    """🆕 Background WebSocket listener for ~1s live trades with reconnect."""
    reconnect_delay = 1  # Start with 1s
    
    while True:  # Outer reconnect loop
        # 🆕 Dynamic assets from trader's recent trades
        recent_trades = safe_fetch(f"https://data-api.polymarket.com/trades?user={TRADER}&limit=200")
        assets = list(set(item.get('asset') for item in recent_trades if item.get('asset')))[:100]
        
        def on_message(ws, msg):
            try:
                data = json.loads(msg)
                print(f"🧑‍💻 WS MSG TYPE: {data.get('event_type', 'unknown')}")
                print(f"🧑‍💻 WS FIELDS: {list(data.keys())}")
                print(f"🧑‍💻 SIZE: {data.get('size', 'N/A')}, TIMESTAMP: {data.get('timestamp', 'N/A')}")
                print("---")  # Separator

                # Try broader filter for trades
                if (data.get('event_type') == 'last_trade_price' or 
                    data.get('event_type') == 'trade' or
                    data.get('size', 0) > 0):
                    data['proxyWallet'] = TRADER  # Inject for compatibility
                    data['title'] = data.get('question', 'Market Trade')  # Add for display
                    ts = data.get('timestamp') or time.time()
                    if ts:
                        live_trades.append(data)
                        print(f"✅ ADDED TRADE #{len(live_trades)}")
            except Exception as e:
                print(f"Parse error: {e}")

        
        def on_open(ws):
            if assets:
                ws.send(json.dumps({
                    "type": "market",
                    "assets_ids": assets
                }))
                print(f"✅ WS Subscribed to {len(assets)} assets for {TRADER}")
            else:
                print(f"⚠️ No recent assets for {TRADER}—REST fallback only")
        
        def on_error(ws, error):
            nonlocal reconnect_delay
            print(f"WS Error: {error}, reconnecting in {reconnect_delay}s")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)
        
        def on_close(ws, close_status_code, close_msg):
            print("WS Closed, reconnecting...")
        
        ws = websocket.WebSocketApp("wss://ws-subscriptions-clob.polymarket.com/ws/market",
                                    on_message=on_message,
                                    on_open=on_open,
                                    on_error=on_error,
                                    on_close=on_close)
        try:
            ws.run_forever()
        except Exception:
            pass  # Loop restarts


# 🆕 Start WS listener once (daemon thread)
threading.Thread(target=rtds_listener, daemon=True).start()


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
    
    # 2. Regex fallback
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
        user_field = str(item.get("user", "")).lower()
        if proxy != TRADER and user_field != TRADER: continue
        
        ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt')
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
    
    filtered_data = [item for item in unique_combined if is_crypto(item)]
    
    st.sidebar.info(f"📊 REST: {len(all_raw)} total | WS: {ws_count} live")
    st.sidebar.success(f"✅ {len(filtered_data)} crypto trades | {minutes_back}min")
    
    if not filtered_data:
        return pd.DataFrame()
    
    df_data = []
    for item in filtered_data[-200:]:  # Latest 200
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
