import streamlit as st


@st.cache_data(ttl=10)
def get_closed_trades_pnl(address: str) -> dict:
    """
    NOTE: Polymarket /trades endpoint returns individual trade legs,
    not matched positions — true PnL requires buy/sell pairing which
    isn't available here. Returning 0 intentionally; PnL is calculated
    locally via calculate_simulated_realized() in utils/simulator.py.
    TODO: Implement proper buy/sell leg pairing if API support improves.
    """
    return {'total': 0, 'crypto_count': 0}