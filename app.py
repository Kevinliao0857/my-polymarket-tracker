import streamlit as st

# ✅ Must be FIRST Streamlit call — before any other st.* or autorefresh
st.set_page_config(layout="wide", page_title="0x8dxd Tracker")

import time
import pandas as pd
from datetime import datetime

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=5000, limit=None, key="crypto_bot")
except ImportError:
    st.warning("🔄 Add `streamlit-autorefresh` to requirements.txt for auto-refresh")

from utils.api import get_open_positions, track_0x8dxd, get_profile_name, get_trader_pnl, get_closed_trades_pnl
from utils.config import EST, TRADER

# ✅ Explicit page imports — avoids shadowing utils.websocket
from pages.trades import show_trades
from pages.positions import show_positions
from pages.simulator import show_simulator
from pages.websocket import show_websocket_status

if 'refresh_count' not in st.session_state:
    st.session_state.refresh_count = 0
st.session_state.refresh_count += 1

st.markdown("# ₿ 0x8dxd Crypto Bot Tracker")

now_est = datetime.now(EST)
st.caption(
    f"🕐 {now_est.strftime('%Y-%m-%d %H:%M:%S')} "
    f"({now_est.strftime('%I:%M:%S %p')}) ET | "
    f"Auto 5s ✓ #{st.session_state.refresh_count}🔄"
)

# ✅ Fetch once, reuse — avoids duplicate network calls
pnl_data = get_trader_pnl(TRADER)
closed_pnl = get_closed_trades_pnl(TRADER)

col1, col2, col3 = st.columns(3)
with col1:
    pnl_val = pnl_data['total_pnl']
    pnl_color = "🟢" if pnl_val >= 0 else "🔴"
    st.metric(
        "Crypto P&L",
        f"{pnl_color}${pnl_val:+,.2f}",
        delta=f"{pnl_val:+,.2f}"
    )
with col2:
    st.metric("Crypto Positions", pnl_data['crypto_count'])
with col3:
    st.metric("Total Size", f"${pnl_data['total_size']:.0f}")

col4, col5 = st.columns(2)
with col4:
    pnl_color = "🟢" if closed_pnl['total'] >= 0 else "🔴"
    st.metric("Closed P&L", f"{pnl_color}${abs(closed_pnl['total']):,.0f}")
with col5:
    st.metric("Settled Trades", closed_pnl['crypto_count'])

# Sidebar
st.sidebar.title("⚙️ Settings")
show_websocket_status()
st.sidebar.markdown("---")

if 'include_5m' not in st.session_state:
    st.session_state.include_5m = True

st.sidebar.checkbox(
    "🔄 Include 5-minute markets",
    value=st.session_state.include_5m,
    key="include_5m",
    help="Unchecked = skip 5-minute crypto window trades"
)
st.sidebar.markdown("---")

try:
    profile_name = get_profile_name(TRADER)
    st.sidebar.markdown(f"**👤 Tracking:** `{profile_name}`")
except Exception:
    st.sidebar.markdown(f"**👤 Tracking:** `{TRADER[:10]}...`")

MINUTES_BACK = st.sidebar.slider("⏰ Minutes back", 15, 120, 30, 5, key='minutes_back_slider')
now_ts = int(time.time())
st.sidebar.caption(
    f"From: {datetime.fromtimestamp(now_ts - MINUTES_BACK * 60, EST).strftime('%H:%M %p ET')}"
)

if st.sidebar.button("🔄 Force Refresh", type="primary"):
    st.rerun()

st.sidebar.markdown("---")

# Main content
show_trades(MINUTES_BACK, include_5m=st.session_state.include_5m)
show_positions(TRADER)
show_simulator()
