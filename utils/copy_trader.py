import streamlit as st
import requests
import time
from .config import TRADER
from .filters import is_crypto, get_up_down
from .shared import parse_usd


@st.cache_data(ttl=5)
def get_latest_trader_activity(address: str, limit: int = 10) -> list:
    """Poll for the trader's most recent BUY actions"""
    try:
        resp = requests.get(
            f"https://data-api.polymarket.com/activity?user={address}&limit={limit}",
            timeout=5
        )
        return [
            t for t in resp.json()
            if t.get('type') == 'TRADE' and t.get('side') == 'BUY'
        ]
    except Exception:
        return []


def detect_new_trades(current_trades: list) -> list:
    """Return only trades not seen in previous poll"""
    seen_hashes = st.session_state.get('seen_tx_hashes', set())
    new_trades = []

    for trade in current_trades:
        tx = str(trade.get('transactionHash', '')).lower()
        if tx and tx not in seen_hashes:
            new_trades.append(trade)
            seen_hashes.add(tx)

    st.session_state.seen_tx_hashes = seen_hashes
    return new_trades


def build_copy_signal(trade: dict, copy_ratio: float) -> dict | None:
    """
    Convert a raw trader trade into a copy signal.
    Returns None if trade doesn't meet copy criteria.
    """
    if not is_crypto(trade):
        return None

    trader_shares = float(trade.get('size') or 0)
    your_shares = round(trader_shares / copy_ratio, 1)

    if your_shares < 5:
        return None

    price = parse_usd(trade.get('price') or 0.50)
    your_cost = round(your_shares * price, 2)
    updown = get_up_down(trade)

    return {
        'market':        str(trade.get('title') or trade.get('question') or '')[:85],
        'asset_id':      trade.get('asset') or trade.get('assetId'),
        'outcome':       str(trade.get('outcome', '')).upper(),
        'updown':        updown,
        'trader_shares': trader_shares,
        'your_shares':   your_shares,
        'price':         price,
        'your_cost':     your_cost,
        'tx_hash':       trade.get('transactionHash'),
        'detected_at':   time.time(),
        'status':        'NEW',
    }
