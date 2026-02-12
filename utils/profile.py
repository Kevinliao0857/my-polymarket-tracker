import streamlit as st
import requests
from datetime import datetime
from typing import dict

from .config import EST, TRADER


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
