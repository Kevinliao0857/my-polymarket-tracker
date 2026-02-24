import time
import streamlit as st
import pandas as pd
from datetime import datetime

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=5000, limit=None, key="crypto_bot")  # 5s infinite
except ImportError:
    st.warning("🔄 Add `streamlit-autorefresh` to requirements.txt for auto-refresh")

st.set_page_config(layout="wide")

# ✅ CLEAN IMPORTS
from utils.api import get_open_positions, track_0x8dxd, get_profile_name, get_trader_pnl, get_closed_trades_pnl 
from utils.config import EST, TRADER
from pages import trades, positions, simulator, websocket

if 'refresh_count' not in st.session_state:
    st.session_state.refresh_count = 0
st.session_state.refresh_count += 1

# MAIN TITLE
st.markdown(f"# ₿ 0x8dxd Crypto Bot Tracker")

# Live EST clock
now_est = datetime.now(EST)
time_24 = now_est.strftime('%H:%M:%S')
time_12 = now_est.strftime('%I:%M:%S %p')
st.caption(f"🕐 Current EST: {now_est.strftime('%Y-%m-%d')} {time_24} ({time_12}) ET | Auto 5s ✓ #{st.session_state.refresh_count}🔄")

# P&L TRACKER
pnl_data = get_trader_pnl(TRADER)
closed_pnl = get_closed_trades_pnl(TRADER)

col1, col2, col3 = st.columns(3)
with col1:
    pnl_color = "🟢" if pnl_data['total_pnl'] >= 0 else "🔴"
    st.metric("Crypto P&L", f"{pnl_color}${abs(pnl_data['total_pnl']):,.0f}", delta=pnl_data['total_pnl'])
with col2:
    st.metric("Crypto Positions", pnl_data['crypto_count'])
with col3:
    st.metric("Total Size", f"${pnl_data['total_size']:.0f}")

# CLOSED P&L TRACKER
col4, col5 = st.columns(2)
with col4:
    pnl_color = "🟢" if closed_pnl['total'] >= 0 else "🔴"
    st.metric("Closed P&L", f"{pnl_color}${abs(closed_pnl['total']):,.0f}")
with col5:
    st.metric("Settled Trades", closed_pnl['crypto_count'])

# CLEAN SIDEBAR (all controls)
st.sidebar.title("⚙️ Settings")

# 👈 WS CONTROLS (top priority)
websocket.show_websocket_status()

st.sidebar.markdown("---")

if 'include_5m' not in st.session_state:
    st.session_state.include_5m = False

st.sidebar.checkbox(
    "🔄 Include 5-minute markets",
    value=st.session_state.include_5m,
    key="include_5m",
    help="Unchecked = skip 5-minute crypto window trades"
)

st.sidebar.markdown("---")

# 👤 TRADER PROFILE
try:
    profile_name = get_profile_name(TRADER)
    st.sidebar.markdown(f"**👤 Tracking:** `{profile_name}`")
except:
    st.sidebar.markdown(f"**👤 Tracking:** `{TRADER[:10]}...`")

MINUTES_BACK = st.sidebar.slider("⏰ Minutes back", 15, 120, 30, 5, key='minutes_back_slider')
now_ts = int(time.time())
st.sidebar.caption(f"From: {datetime.fromtimestamp(now_ts - MINUTES_BACK*60, EST).strftime('%H:%M %p ET')}")

if st.sidebar.button("🔄 Force Refresh", type="primary"):
    st.rerun()

st.sidebar.markdown("---")

# 👈 MAIN CONTENT PAGES (default MINUTES_BACK)
trades.show_trades(MINUTES_BACK, include_5m=st.session_state.include_5m)
positions.show_positions(TRADER)
simulator.show_simulator()

# 02/23/2026 in working state