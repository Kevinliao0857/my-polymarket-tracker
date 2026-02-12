import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import time

from .config import EST, TRADER
from .status import get_status_hybrid


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
