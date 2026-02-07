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


def rtds_listener():
    """🆕 Fixed WS listener with pings, server pongs, and real asset IDs."""
    reconnect_delay = 1
    ping_interval = 10  # Seconds
    ws_base_url = "wss://ws-subscriptions-clob.polymarket.com"

    while True:  # Reconnect loop
        # 🆕 Extract unique asset IDs from recent trades (REST uses 'asset')
        recent_trades = safe_fetch(f"https://data-api.polymarket.com/trades?user={TRADER}&limit=200")
        assets = list(set(item.get('asset') for item in recent_trades if item.get('asset')))[:20]
        
        # 🆕 Fallback: Fetch active crypto markets if no trader assets
        if not assets:
            print("⚠️ No trader assets—fetching popular crypto...")
            popular = safe_fetch("https://gamma-api.polymarket.com/markets?active=true&category=crypto&limit=20")
            assets = []
            for m in popular:
                tokens = m.get('tokens', [])
                if tokens:
                    assets.append(tokens[0].get('id') or tokens[0].get('token_id'))
            assets = assets[:20]
        
        print(f"🚀 ASSETS ({len(assets)}): {assets[:3] if assets else 'NONE'}...")

        if not assets:
            print("⚠️ No assets—retry in 30s")
            time.sleep(30)
            continue

        def on_message(ws, msg):
            if msg.strip() == "ping":
                ws.send("PING")
                print("🏓 PONG")
                return
            
            try:
                data = json.loads(msg)
                event_type = data.get('event_type', 'unknown')
                asset_id = data.get('asset_id') or data.get('asset') or 'N/A'
                size = (data.get('size') or 
                        data.get('price', {}).get('value', 0) or 
                        data.get('price', 0) or 0)
                print(f"🧑‍💻 EVENT: {event_type} | Asset: {asset_id} | Size/Price: {size}")
                
                # 🆕 Handle only trades/last_trade_price + robust size
                if event_type not in ('trade', 'last_trade_price'):
                    return
                
                trade_data = data
                trade_data['proxyWallet'] = TRADER
                trade_data['title'] = data.get('question', data.get('market', {}).get('question', 'Market Trade'))
                ts = trade_data.get('timestamp') or time.time()
                live_trades.append(trade_data)
                print(f"✅ ADDED #{len(live_trades)}")
            except Exception as e:
                print(f"❌ Parse: {e}")
        
        def on_open(ws):
            ws.send(json.dumps({"type": "market", "assets_ids": assets}))
            print(f"📡 SUBSCRIBED to {len(assets)} assets")
            # 🆕 Ping thread (sends "PING")
            def ping_loop():
                while ws.sock and ws.sock.connected:
                    try:
                        ws.send("PING")
                        print("🏓 PING")
                    except:
                        break
                    time.sleep(ping_interval)
            threading.Thread(target=ping_loop, daemon=True).start()

        def on_error(ws, error):
            nonlocal reconnect_delay
            print(f"❌ ERROR: {error} (retry in {reconnect_delay}s)")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60)

        def on_close(ws, code, reason):
            print(f"🔌 CLOSED: {code} - {reason}")

        ws_url = f"{ws_base_url}/ws/market"
        ws = websocket.WebSocketApp(ws_url, 
                                    on_message=on_message, 
                                    on_open=on_open,
                                    on_error=on_error, 
                                    on_close=on_close)
        try:
            ws.run_forever(ping_interval=0, ping_timeout=None)  # 🆕 No auto-ping
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Run error: {e}")
            time.sleep(reconnect_delay)


def get_status_hybrid(item: Dict[str, Any], now_ts: int) -> str:
    """🟢 Hybrid: API first → Regex fallback."""
    # 1. Try API exact time
    condition_id = str(item.get('conditionId') or item.get('marketId') or item.get('market', {}).get('conditionId') or '')
    slug = str(item.get('slug') or item.get('market', {}).get('slug') or '')
  
    end_str = get_market_enddate(condition_id, slug)
    now_est = datetime.fromtimestamp(now_ts, EST)
  
    if end_str:
        try:
            end_dt = pd.to_datetime(end_str).tz_convert(EST)
            if now_est >= end_dt:
                return "⚫ EXPIRED"
            return f"🟢 ACTIVE (til {end_dt.strftime('%I:%M %p ET')}) 🟢"
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
