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

# ✅ FIXED IMPORTS - Everything you need
from utils import track_0x8dxd
from utils.config import EST, TRADER
from utils.api import get_profile_name, get_trader_pnl, get_closed_trades_pnl
from utils.simulator import simulate_combined, simulate_historical_pnl, simulate_hedge

# WS auto-starts INSIDE track_0x8dxd() - NO manual thread needed!

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

# 👇 ADD P&L TRACKER
pnl_data = get_trader_pnl(TRADER)
closed_pnl = get_closed_trades_pnl(TRADER)

col1, col2, col3 = st.columns(3)
with col1:
    pnl_color = "🟢" if pnl_data['total_pnl'] >= 0 else "🔴"
    st.metric(
        "Crypto P&L", 
        f"{pnl_color}${abs(pnl_data['total_pnl']):,.0f}", 
        delta=pnl_data['total_pnl']
    )
with col2:
    st.metric("Crypto Positions", pnl_data['crypto_count'])
with col3:
    st.metric("Total Size", f"${pnl_data['total_size']:.0f}")

# CLOSED P&L TRACKER
closed_pnl = get_closed_trades_pnl(TRADER)
col4, col5 = st.columns(2)
with col4:
    pnl_color = "🟢" if closed_pnl['total'] >= 0 else "🔴"
    st.metric("Closed P&L", f"{pnl_color}${abs(closed_pnl['total']):,.0f}")
with col5:
    st.metric("Settled Trades", closed_pnl['crypto_count'])

# SIDEBAR ⚙️
st.sidebar.title("⚙️ Settings")

# 👤 TRADER PROFILE - Added here
try:
    profile_name = get_profile_name(TRADER)
    st.sidebar.markdown(f"**👤 Tracking:** `{profile_name}`")
except:
    st.sidebar.markdown(f"**👤 Tracking:** `{TRADER[:10]}...`")

MINUTES_BACK = st.sidebar.slider("⏰ Minutes back", 15, 120, 30, 5)
now_ts = int(time.time())
st.sidebar.caption(f"From: {datetime.fromtimestamp(now_ts - MINUTES_BACK*60, EST).strftime('%H:%M %p ET')}")

if st.sidebar.button("🔄 Force Refresh", type="primary"):
    st.rerun()

if st.sidebar.button("🧪 Test New Status API"):
    st.session_state.test_api = True
    st.rerun()

# Load data - AUTO-STARTS WS! 🚀
df = track_0x8dxd(MINUTES_BACK)

if df.empty:
    st.info("No crypto trades found")
else:
    # TEST BUTTON RESULT
    if 'test_api' in st.session_state:
        del st.session_state.test_api
    
    newest_sec = df['age_sec'].min()
    newest_str = f"{int(newest_sec)//60}m {int(newest_sec)%60}s ago"
    span_sec = df['age_sec'].max()
    span_str = f"{int(span_sec)//60}m {int(span_sec)%60}s"
    up_bets = len(df[df['UP/DOWN'] == '🟢 UP'])

    st.info(f"✅ {len(df)} LIVE crypto bets ({MINUTES_BACK}min window)")
    
    recent_mask = df['age_sec'] <= 30
    def highlight_recent(row):
        if recent_mask.iloc[row.name]:
            return ['background-color: rgba(0, 255, 0, 0.15)'] * 7  # 👈 6→7
        return [''] * 7
    
    visible_cols = ['Market', 'UP/DOWN', 'Shares', 'Price', 'Amount', 'Status', 'Updated']
    styled_df = df[visible_cols].style.apply(highlight_recent, axis=1)
    
    st.markdown("""
    <div style='display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 10px;'>
        <span><b>🟢 UP:</b> {}</span>
        <span><b>🔴 DOWN:</b> {}</span>
        <span>Newest: {}</span>
        <span>Span: {}</span>
    </div>
    """.format(up_bets, len(df)-up_bets, newest_str, span_str), unsafe_allow_html=True)

    st.dataframe(styled_df, height=400, hide_index=True,
                 column_config={
                    "Market": st.column_config.TextColumn(width="medium"),
                    "Shares": st.column_config.NumberColumn(format="%.1f", width="small"),
                    "Price": st.column_config.TextColumn(width="small"), 
                    "Amount": st.column_config.NumberColumn(format="$%.2f", width="small"), 
                    "Status": st.column_config.TextColumn(width="medium")
                 })

# DRY RUN SIMULATOR - TRUE 1:200
if "show_dry_run" not in st.session_state:
    st.session_state.show_dry_run = False

st.sidebar.markdown("### 🤖 Copy Trader 1:200")
your_bankroll = st.sidebar.number_input("💰 Your Bankroll", value=1000.0, step=100.0)
copy_ratio = st.sidebar.number_input("⚖️ Copy Ratio", value=200, step=50, min_value=0)
hedge_ratio = st.sidebar.number_input("Hedge Ratio", value=200, step=50)

if st.sidebar.button("🔍 Analyze Hedge", type="secondary"):
    simulate_hedge(hedge_wallet, hedge_minutes, hedge_ratio)


# 👇 Watcher IMMEDIATELY after (looks "inside" the section)
if 'last_bankroll' not in st.session_state:
    st.session_state.last_bankroll = your_bankroll
if 'last_ratio' not in st.session_state:
    st.session_state.last_ratio = copy_ratio

if st.session_state.last_bankroll != your_bankroll or st.session_state.last_ratio != copy_ratio:
    st.session_state.last_bankroll = your_bankroll
    st.session_state.last_ratio = copy_ratio
    st.rerun()

if st.sidebar.button("🚀 Simulate Combined", type="primary"):
    st.session_state.show_combined = True

# 👇 COMBINED RESULTS
if st.session_state.get('show_combined', False) and not df.empty:
    st.markdown("---")
    simulate_combined(df, your_bankroll, TRADER, copy_ratio, hedge_minutes, hedge_ratio)
    
    if st.button("❌ Hide Combined"):
        st.session_state.show_combined = False
        st.rerun()


