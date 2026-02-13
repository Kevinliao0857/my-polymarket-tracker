import streamlit as st
import requests

from typing import Dict
from .config import TICKERS, FULL_NAMES  # 👈 PERFECT: All crypto names

@st.cache_data(ttl=10)
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
            if (trade.get('status') == 'settled' and 
                trade.get('pnl') is not None):  # 👈 Safe check
                
                title = str(trade.get('title', '')).lower()  # 👈 Crypto filter
                pnl = float(trade.get('pnl', 0))
                
                # 👈 BULLETPROOF: Short + full names
                if (pnl != 0 and 
                    any(ticker in title for ticker in TICKERS + FULL_NAMES)):
                    total_profit += pnl
                    crypto_count += 1

        return {
            'total': total_profit,
            'crypto_count': crypto_count
        }
    except:
        pass
    return {'total': 0, 'crypto_count': 0}  # 👈 Always returns keys
