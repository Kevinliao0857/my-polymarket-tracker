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

# ✅ CLEAN IMPORTS - only what we need
from utils.api import get_open_positions, track_0x8dxd, get_profile_name, get_trader_pnl, get_closed_trades_pnl 
from utils.config import EST, TRADER

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
col4, col5 = st.columns(2)
with col4:
    pnl_color = "🟢" if closed_pnl['total'] >= 0 else "🔴"
    st.metric("Closed P&L", f"{pnl_color}${abs(closed_pnl['total']):,.0f}")
with col5:
    st.metric("Settled Trades", closed_pnl['crypto_count'])

# CLEAN SIDEBAR
st.sidebar.title("⚙️ Settings")

# 👤 TRADER PROFILE
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

st.sidebar.markdown("---")
if st.sidebar.button("🚀 Simulate Combined", type="primary"):
    st.session_state.show_combined = True

# Load data - AUTO-STARTS WS! 🚀
df = track_0x8dxd(MINUTES_BACK)

if df.empty:
    st.info("No crypto trades found")
else:
    newest_sec = df['age_sec'].min()
    newest_str = f"{int(newest_sec)//60}m {int(newest_sec)%60}s ago"
    span_sec = df['age_sec'].max()
    span_str = f"{int(span_sec)//60}m {int(span_sec)%60}s"
    up_bets = len(df[df['UP/DOWN'].str.contains('🟢 UP', na=False)])

    st.info(f"✅ {len(df)} LIVE crypto bets ({MINUTES_BACK}min window)")
    
    recent_mask = df['age_sec'] <= 30
    def highlight_recent(row):
        if recent_mask.iloc[row.name]:
            return ['background-color: rgba(0, 255, 0, 0.15)'] * 7
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
            "UP/DOWN": st.column_config.TextColumn(width="medium"),
            "Shares": st.column_config.NumberColumn(format="%.1f", width="small"),
            "Price": st.column_config.TextColumn(width="small"), 
            "Amount": st.column_config.NumberColumn(format="$%.2f", width="small"), 
            "Status": st.column_config.TextColumn(width="medium")
         })

    # 👇 OPEN POSITIONS TABLE
    pos_df = get_open_positions(TRADER)
    if not pos_df.empty:
        st.markdown("---")
        st.subheader("📈 Open Positions (Avg Entry Prices)")
        pos_visible_cols = ['Market', 'UP/DOWN', 'Shares', 'AvgPrice', 'CurPrice', 'Amount', 'PnL', 'Status', 'Updated']
        pos_recent_mask = pos_df['age_sec'] <= 300
        def highlight_recent_pos(row):
            if pos_recent_mask.iloc[row.name]:
                return ['background-color: rgba(0, 255, 0, 0.15)'] * len(pos_visible_cols)
            return [''] * len(pos_visible_cols)
        
        styled_pos = pos_df[pos_visible_cols].style.apply(highlight_recent_pos, axis=1)
        st.dataframe(styled_pos, height=300, hide_index=True, column_config={
            "UP/DOWN": st.column_config.TextColumn(width="medium"),
            "AvgPrice": st.column_config.NumberColumn(format="$%.2f", width="small"),
            "CurPrice": st.column_config.NumberColumn(format="$%.2f", width="small"),
            "Amount": st.column_config.NumberColumn(format="$%.2f", width="small"),
            "PnL": st.column_config.NumberColumn(format="$%.2f", width="small"),
        })
        st.caption(f"✅ {len(pos_df)} crypto positions | Uses official avgPrice [data-api.polymarket.com/positions]")

# 👇 SIMULATE COMBINED (requires simulator import - kept minimal)
if st.session_state.get('show_combined', False) and not df.empty:
    st.markdown("---")
    # Note: You'll need to add back simulator import + variables when ready
    st.info("🛠️ Simulator section - add back imports when ready")
    if st.button("❌ Hide Combined"):
        st.session_state.show_combined = False
        st.rerun()
