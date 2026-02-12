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
from .simulator import parse_usd  # 👈 Reuse your function!

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
    
    # 4. 👇 IMPROVED: Build DF with avg price in UP/DOWN + price_num for grouping
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
        
        price_raw = item.get('price') or item.get('curPrice', '-')  # 👈 Prefer 'price' for activity
        price_num = parse_usd(price_raw) or 0.50
        
        if isinstance(price_raw, (int, float)):
            price_val = f"${price_raw:.2f}"
            avg_price_str = f"@ ${price_num:.2f}"
        else:
            price_val = str(price_raw)
            avg_price_str = ""
        
        updown_price = f"{updown} {avg_price_str}".strip()  # 👈 "🟢 UP @ $0.52"
        amount = size_val * price_num

        ts_field = item.get('timestamp') or item.get('updatedAt') or item.get('createdAt') or now_ts
        try:
            ts = int(float(ts_field))
        except (ValueError, TypeError):
            ts = now_ts
        update_str = datetime.fromtimestamp(ts, EST).strftime('%I:%M:%S %p ET')
        
        status_str = get_status_hybrid(item, now_ts)
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
            'price_num': price_num  # 👈 For future grouping
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


@st.cache_data(ttl=30)
def get_trader_pnl(address: str) -> dict:
    """Get trader's total P&L from open positions"""
    try:
        url = f"https://data-api.polymarket.com/positions?user={address}&sizeThreshold=0"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            positions = response.json()
            
            total_pnl = 0
            total_size = 0
            crypto_positions = 0
            
            for pos in positions:
                # Only crypto positions
                title = str(pos.get('title', '')).lower()
                if any(ticker in title for ticker in ['btc', 'eth', 'sol', 'doge']):
                    pnl = pos.get('cashPnl', 0)
                    size = pos.get('size', 0)
                    total_pnl += pnl
                    total_size += size
                    crypto_positions += 1
            
            return {
                'total_pnl': total_pnl,
                'total_size': total_size,
                'crypto_count': crypto_positions,
                'all_positions': len(positions)
            }
    except:
        pass
    return {'total_pnl': 0, 'total_size': 0, 'crypto_count': 0, 'all_positions': 0}


@st.cache_data(ttl=30)  # 👈 NEW: Open positions table with avgPrice!
def get_open_positions(address: str) -> pd.DataFrame:
    """📈 Trader's OPEN positions → true avgPrice per market/outcome"""
    try:
        url = f"https://data-api.polymarket.com/positions?user={address}&sizeThreshold=0"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            positions = response.json()
            
            df_data = []
            now_ts = int(time.time())
            for pos in positions:
                title = str(pos.get('title', '')).lower()
                # Crypto filter (your tickers)
                if not any(ticker in title for ticker in ['btc', 'eth', 'sol', 'doge']):
                    continue
                
                outcome = str(pos.get('outcome', '')).upper()
                size = abs(pos.get('size', 0))  # Always positive shares
                avg_price = pos.get('avgPrice', 0) or 0.50
                cur_price = pos.get('curPrice', avg_price)
                
                updown = "🟢 UP" if "UP" in outcome else "🔴 DOWN"
                updown_price = f"{updown} @ ${avg_price:.2f}"  # 👈 Official avg!
                
                ts_field = pos.get('timestamp') or now_ts
                try:
                    ts = int(float(ts_field))
                except:
                    ts = now_ts
                update_str = datetime.fromtimestamp(ts, EST).strftime('%I:%M:%S %p ET')
                status_str = get_status_hybrid(pos, now_ts)
                age_sec = now_ts - ts
                
                df_data.append({
                    'Market': (pos.get('title') or '-')[:85] + ('...' if len(pos.get('title', '')) > 85 else ''),
                    'UP/DOWN': updown_price,
                    'Shares': f"{size:.1f}",
                    'AvgPrice': f"${avg_price:.2f}",
                    'CurPrice': f"${cur_price:.2f}",
                    'Amount': f"${size * avg_price:.2f}",
                    'PnL': f"${pos.get('cashPnl', 0):.2f}",
                    'Status': status_str,
                    'Updated': update_str,
                    'age_sec': age_sec
                })
            
            df = pd.DataFrame(df_data)
            if not df.empty:
                df = df.sort_values('age_sec')
            return df
    except:
        pass
    return pd.DataFrame()


@st.cache_data(ttl=60)
def get_closed_trades_pnl(address: str) -> dict:
    """Sum P&L from closed SETTLED crypto trades"""
    try:
        trades = requests.get(
            f"https://data-api.polymarket.com/trades?user={address}&limit=1000",
            timeout=10
        ).json()
        total_profit = 0
        crypto_count = 0
        for trade in trades:
            # Check if crypto AND settled
            if (trade.get('status') == 'settled' and 
                trade.get('pnl') is not None):  # 👈 Safe check
                # Skip is_crypto check - just count settled with PNL
                pnl = float(trade.get('pnl', 0))
                if pnl != 0:  # Only count trades with P&L
                    total_profit += pnl
                    crypto_count += 1
        return {
            'total': total_profit,
            'crypto_count': crypto_count
        }
    except:
        pass
    return {'total': 0, 'crypto_count': 0}  # 👈 Always returns keys
