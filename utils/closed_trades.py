import streamlit as st
import requests

from .config import TRADER


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
