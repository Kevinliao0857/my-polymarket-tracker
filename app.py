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
from utils.simulator import run_position_simulator, track_simulation_pnl

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

# =====================================================
# 🤖 SIMULATOR FUNCTIONS (INTERNAL)
# =====================================================
def render_simulator():
    """Compact simulator renderer"""
    saved_bankroll = st.session_state.get('bankroll', 1000.0)
    saved_copy_ratio = st.session_state.get('copy_ratio', 10)
    
    pos_df = get_open_positions(TRADER)
    if pos_df.empty:
        st.warning("No positions to simulate")
        return
    
    sim_results = run_position_simulator(pos_df, saved_bankroll, saved_copy_ratio)
    
    if not sim_results['valid']:
        st.error(sim_results['message'])
        return
    
    track_simulation_pnl(sim_results, saved_bankroll)
    
    # Results
    sim_df = sim_results['sim_df']
    total_cost = sim_results['total_cost']
    total_pnl = sim_results['total_pnl']
    skipped = sim_results['skipped']
    
    sim_color = "🟢" if total_pnl >= 0 else "🔴"
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.metric("💵 Cost", f"${total_cost:,.0f}", f"{sim_color}${abs(total_pnl):,.0f}")
    with col_m2:
        st.metric("📊 Positions", f"{len(sim_df)}/{len(sim_df)+skipped}")
    
    pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    runtime_min = (time.time() - st.session_state.sim_start_time) / 60
    
    if total_cost > saved_bankroll:
        st.error(f"⚠️ Need ${total_cost:,.0f} > ${saved_bankroll:,.0f}")
    else:
        st.success(f"✅ {len(sim_df)} positions | ${total_pnl:+.0f} ({pnl_pct:+.1f}%) | "
                  f"{runtime_min:.1f}min | 1:{saved_copy_ratio}")
    
    # History chart (if exists)
    if len(st.session_state.sim_pnl_history) > 1:
        try:
            hist_df = pd.DataFrame(st.session_state.sim_pnl_history)
            hist_df['Time'] = hist_df['time'].apply(lambda x: f"{int(x):.0f}m")
            st.line_chart(hist_df.set_index('Time')['pnl'], height=200)
        except:
            pass
    
    # 👇 TABLE WITH STATUS + GREEN HIGHLIGHTING
    sim_cols = ['Market', 'UP/DOWN', 'Your Shares', 'Your Cost', 'Your PnL', 'Status']
    recent_mask = sim_df['age_sec'] <= 300
    def highlight_recent(row):
        if recent_mask.iloc[row.name]:
            return ['background-color: rgba(0, 255, 0, 0.15)'] * len(sim_cols)
        return [''] * len(sim_cols)

    styled_sim = sim_df[sim_cols].style.apply(highlight_recent, axis=1)
    st.dataframe(styled_sim, use_container_width=True, height=300, hide_index=True,
                 column_config={
                     "Your Shares": st.column_config.NumberColumn(format="%.1f"),
                     "Your Cost": st.column_config.NumberColumn(format="$%.2f"),
                     "Your PnL": st.column_config.NumberColumn(format="$%.2f"),
                     "Status": st.column_config.TextColumn("Status/Expiry")
                 })
    st.caption("✅ Green rows = active <5min | Status shows expiry/active")


# =====================================================
# MAIN TRADES TABLE
# =====================================================
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

    # OPEN POSITIONS TABLE
    pos_df = get_open_positions(TRADER)
    if not pos_df.empty:
        st.markdown("---")
        st.subheader("📈 Open Positions")
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
        st.caption(f"✅ {len(pos_df)} positions")

# =====================================================
# 🤖 SIMULATOR (COLLAPSIBLE) - REAL BANKROLL TRACKING
# =====================================================

def render_real_bankroll_simulator(initial_bankroll: float, copy_ratio: int):
    """Dynamic sim with simulated realized PnL"""
    pos_df = get_open_positions(TRADER)
    if pos_df.empty:
        st.warning("No LIVE positions to simulate")
        return 
    
    # Safety check
    if 'AvgPrice' not in pos_df.columns or 'CurPrice' not in pos_df.columns:
        st.error(f"❌ Missing price columns. Got: {list(pos_df.columns)}")
        return
    
    sim_results = run_position_simulator(pos_df, initial_bankroll, copy_ratio)
    if not sim_results['valid']:
        st.error(sim_results['message'])
        return 
    
    track_simulation_pnl(sim_results, initial_bankroll)
    
    sim_df = sim_results['sim_df']
    total_cost = sim_results['total_cost']
    total_pnl = sim_results['total_pnl']
    skipped = sim_results['skipped']
    
    # Simulated realized PnL (expired positions scaled)
    all_pos_df = get_open_positions(TRADER)
    expired_mask = all_pos_df['Status'].str.contains('expired|settled|closed|finished', case=False, na=False)
    expired_df = all_pos_df[expired_mask].copy()
    
    simulated_realized_pnl = 0.0
    if len(expired_df) > 0 and 'PnL' in expired_df.columns:
        expired_df['Your Shares'] = (expired_df['Shares'].astype(float) / copy_ratio).round(1)
        trader_pnl = pd.to_numeric(expired_df['PnL'], errors='coerce')
        simulated_realized_pnl = (expired_df['Your Shares'] * trader_pnl).sum()
    
    current_bankroll = initial_bankroll + simulated_realized_pnl
    
    # Metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("🏦 Simulated Bankroll", f"${current_bankroll:,.0f}", f"${simulated_realized_pnl:+,.0f}")
    with col2:
        usage_pct = (total_cost / current_bankroll * 100) if current_bankroll > 0 else 0
        usage_color = "🟢" if usage_pct <= 50 else "🟡" if usage_pct <= 80 else "🔴"
        st.metric("💼 Capital Used", f"{usage_color}${total_cost:,.0f}", f"{usage_pct:.0f}%")
    with col3:
        st.metric("📈 Unrealized PnL", f"${total_pnl:+,.0f}")
    with col4:
        st.metric("💰 Simulated Realized", f"${simulated_realized_pnl:+,.0f}")
    with col5:
        st.metric("📊 Simulated", f"{len(sim_df)}/{len(sim_df)+skipped}")
    
    runtime_min = (time.time() - st.session_state.sim_start_time) / 60
    st.caption(f"⏱️ {runtime_min:.1f}min | 1:{copy_ratio}")
    
    # Hedge marker
    market_groups = sim_df.groupby('Market')
    hedge_markets = [m for m, g in market_groups if len(g) >= 2 and g['UP/DOWN'].str.contains('UP').any()]
    sim_df['Hedge?'] = sim_df['Market'].apply(lambda x: '🛡️ Hedge' if x in hedge_markets else '')
    
    # Charts
    if len(st.session_state.sim_pnl_history) > 1:
        hist_df = pd.DataFrame(st.session_state.sim_pnl_history)
        hist_df['Time'] = hist_df['time'].apply(lambda x: f"{int(x):.0f}m")
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.line_chart(hist_df.set_index('Time')['bankroll'], height=200)
        with col_chart2:
            st.line_chart(hist_df.set_index('Time')['pnl'], height=200)
    
    # Table
    sim_cols = ['Market', 'UP/DOWN', 'Status', 'Your Shares', 'Your Cost', 'Your PnL', 'Hedge?']
    recent_mask = sim_df['age_sec'] <= 300
    def highlight_recent(row):
        if recent_mask.iloc[row.name]:
            return ['background-color: rgba(0, 255, 0, 0.15)'] * len(sim_cols)
        return [''] * len(sim_cols)
    
    st.dataframe(sim_df[sim_cols].style.apply(highlight_recent, axis=1), 
                 use_container_width=True, height=350, hide_index=True)
    
    # Skipped
    if skipped > 0:
        st.markdown("---")
        skipped_df = pos_df.copy()
        skipped_df['Your Shares'] = (skipped_df['Shares'].astype(float) / copy_ratio).round(1)
        skipped_df = skipped_df[skipped_df['Your Shares'] < 5]
        if not skipped_df.empty:
            st.dataframe(skipped_df[['Market', 'UP/DOWN', 'Shares', 'Your Shares']], 
                        use_container_width=True)

# =====================================================
# EXPANDER (END OF FILE)
# =====================================================
with st.expander("🤖 Position Simulator", expanded=False):
    if 'sim_start_time' not in st.session_state:
        st.session_state.sim_start_time = None
    if 'sim_pnl_history' not in st.session_state:
        st.session_state.sim_pnl_history = []
    
    col1, col2 = st.columns(2)
    with col1:
        initial_bankroll = st.number_input("💰 Starting Bankroll", value=1000.0, step=100.0)
    with col2:
        copy_ratio = st.number_input("⚖️ Copy Ratio", value=10, step=5, min_value=1)
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if col_btn1.button("🚀 Start Sim", type="primary", use_container_width=True):
            st.session_state.initial_bankroll = initial_bankroll
            st.session_state.copy_ratio = copy_ratio
            if st.session_state.sim_start_time is None:
                st.session_state.sim_start_time = time.time()
                st.session_state.sim_pnl_history = []
            st.rerun()
    with col_btn2:
        if col_btn2.button("🛑 Reset", use_container_width=True):
            for key in ['sim_start_time', 'sim_pnl_history', 'initial_bankroll', 'copy_ratio']:
                st.session_state.pop(key, None)
            st.rerun()
    
    if st.session_state.sim_start_time:
        initial_bankroll = st.session_state.get('initial_bankroll', 1000.0)
        copy_ratio = st.session_state.get('copy_ratio', 10)
        render_real_bankroll_simulator(initial_bankroll, copy_ratio)
