import streamlit as st
import pandas as pd
import requests
import threading
import time
from datetime import datetime
from typing import Any, List

from .config import EST, TRADER, ALLOW_5M_MARKETS, DISABLE_WS_LIVE
from .filters import is_crypto, get_up_down, is_5m_market
from .data import safe_fetch
from .status import get_status_hybrid
from .shared import parse_usd

# 🛡️ CLOUD-SAFE WS (restarts if dead)
def ensure_live_ws():
    if DISABLE_WS_LIVE:
        return
    ws_threads = [t for t in threading.enumerate() 
                  if 'rtds_listener' in str(t.name).lower()]
    if not ws_threads:
        t = threading.Thread(target=rtds_listener, name='rtds_listener', daemon=True)
        t.start()
        print("🔌 WS RESTARTED")
        time.sleep(1)

# ensure_live_ws()

def normalize_trade_item(item: Any, now_ts: int) -> str:
    if isinstance(item, str) or (isinstance(item, dict) and 'asset_id' in item):
        asset = item if isinstance(item, str) else item.get('asset_id', '')
        if asset:
            item = {'conditionId': asset, 'marketId': asset, 'title': str(item.get('title', ''))}
    return get_status_hybrid(item, now_ts)

@st.cache_data(ttl=30)
def get_latest_bets(address: str, limit: int = 200) -> List[dict]:
    try:
        url = f"https://data-api.polymarket.com/activity?user={address}&limit={limit}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            activities = response.json()
            buy_trades = [a for a in activities 
                         if a.get("type") == "TRADE" and a.get("side") == "BUY"]
            return buy_trades
    except:
        pass
    return []

@st.cache_data(ttl=10)
def track_0x8dxd(minutes_back: int, include_5m: bool | None = None) -> pd.DataFrame:
    if include_5m is None:
        include_5m = ALLOW_5M_MARKETS

    now_ts = int(time.time())
    ago_ts = now_ts - (minutes_back * 60)

    # 🔍 DEBUG MODE - REST ONLY (no WS crashes)
    st.sidebar.info("🔍 DEBUG: REST trades + 5m filter testing")

    # 2. Activity endpoint (REST)
    latest_bets = get_latest_bets(TRADER, limit=500)
    rest_recent = []
    for item in latest_bets:
        ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt')
        try:
            ts = int(float(ts_field)) if ts_field else now_ts
        except (ValueError, TypeError):
            continue
        if ts >= ago_ts:
            rest_recent.append(item)

    # 3. REST only - NO WS DEPENDENCIES
    combined = rest_recent
    seen_tx = set()
    unique_combined = []
    for item in combined:
        tx_hash = str(item.get('transactionHash', '')).lower()
        if tx_hash not in seen_tx:
            seen_tx.add(tx_hash)
            unique_combined.append(item)

    unique_combined.sort(
        key=lambda x: x.get('timestamp', 0) or x.get('updatedAt', 0) or 0,
        reverse=True,
    )
    max_items = max(200, minutes_back * 15)

    # 4. Filter: crypto + 5-minute toggle ★ DEBUG ACTIVE ★
    filtered_data = []
    five_min_count = 0
    total_crypto_count = 0

    for item in unique_combined:
        if not is_crypto(item):
            continue
        total_crypto_count += 1

        title_for_filter = str(item.get('title') or item.get('question') or '')
        
        # ULTRA DEBUG
        if is_5m_market(title_for_filter):
            five_min_count += 1
            print(f"🚫 5M DETECTED #{five_min_count}: '{title_for_filter[:60]}...' | include_5m={include_5m}")
        
        if not include_5m and is_5m_market(title_for_filter):
            print(f"DEBUG: FILTERED OUT: {title_for_filter}")
            continue

        # Normalize REST data
        if item.get('type') == 'TRADE':
            item['event_type'] = 'trade'
            item['asset_id'] = item.get('asset', item.get('assetId', 'N/A'))

        filtered_data.append(item)
        if len(filtered_data) >= max_items:
            break

    if not filtered_data:
        return pd.DataFrame()

    # 5. Build DataFrame
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

        price_raw = item.get('price') or item.get('curPrice', '-')
        price_num = parse_usd(price_raw) or 0.50

        if isinstance(price_raw, (int, float)):
            price_val = f"${price_raw:.2f}"
            avg_price_str = f"@ ${price_num:.2f}"
        else:
            price_val = str(price_raw)
            avg_price_str = ""

        updown_price = f"{updown} {avg_price_str}".strip()
        amount = size_val * price_num

        ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt') or now_ts
        try:
            ts = int(float(ts_field))
        except (ValueError, TypeError):
            ts = now_ts
        update_str = datetime.fromtimestamp(ts, EST).strftime('%I:%M:%S %p ET')

        status_str = normalize_trade_item(item, now_ts)
        age_sec = now_ts - ts

        df_data.append({
            'Market': short_title,
            'UP/DOWN': updown_price,
            'Shares': f"{size_val:.1f}",
            'Price': price_val,
            'Amount': f"${amount:.2f}",
            'Status': status_str,
            'Updated': update_str,
            'age_sec': age_sec,
            'price_num': price_num,
        })

    df = pd.DataFrame(df_data)
    if df.empty:
        return df

    # 🔍 FINAL DEBUG OUTPUT
    print(f"🔍 FINAL STATS: {len(filtered_data)} trades | {five_min_count} 5m detected | {total_crypto_count} total crypto | include_5m={include_5m}")
    if not df.empty and five_min_count > 0:
        print("FIRST 3 TITLES:")
        for i, row in df.head(3).iterrows():
            print(f"  📋 '{row['Market']}'")

    df = df.sort_values('age_sec')
    return df
