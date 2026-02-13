import streamlit as st
import requests
from typing import Dict
from .config import TICKERS, FULL_NAMES

@st.cache_data(ttl=2)
def get_closed_trades_pnl(address: str) -> dict:
    """Sum P&L from closed SETTLED crypto trades"""
    try:
        trades = requests.get(
            f"https://data-api.polymarket.com/trades?user={address}&limit=1000",
            timeout=10
        ).json()
        
        # 👈 DEBUG:
        st.write(f"🔍 trades={len(trades)} settled={settled_count} crypto={crypto_count}")
        
        total_profit = 0
        crypto_count = 0
        settled_count = 0
        
        for trade in trades:
            status = trade.get('status')
            pnl_val = trade.get('pnl')
            
            if status == 'settled' and pnl_val is not None:
                settled_count += 1
                title = str(trade.get('title', '')).lower()
                pnl = float(pnl_val)
                
                if pnl != 0 and any(ticker in title for ticker in TICKERS + FULL_NAMES):
                    total_profit += pnl
                    crypto_count += 1
        
        return {
            'total': total_profit,
            'crypto_count': crypto_count
        }
    except Exception as e:
        st.error(f"Closed trades error: {e}")
        return {'total': 0, 'crypto_count': 0}
