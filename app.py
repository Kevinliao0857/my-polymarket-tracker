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
from utils.simulator import run_position_simulator, track_simulation_pnl

if 'refresh_count' not in st.session_state:
    st.session_state.refresh_count = 0
st.session_state.refresh_count += 1

if 'sim_start_time' not in st.session_state:
    st.session_state.sim_start_time = None
if 'sim_pnl_history' not in st.session_state:
    st.session_state.sim_pnl_history = []
if 'sim_bankroll_used' not in st.session_state:
    st.session_state.sim_bankroll_used = 0


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

# SIDEBAR (after profile/slider/refresh):
if st.sidebar.button("🔄 Force Refresh", type="primary"):
    st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("🤖 Simulate", type="primary"):
    if st.session_state.sim_start_time is None:
        st.session_state.sim_start_time = time.time()  # 👈 START TRACKING
        st.session_state.sim_pnl_history = []  # 👈 RESET
    st.session_state.show_simulate = True


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

if st.session_state.get('show_simulate', False) and not pos_df.empty:
    st.markdown("---")
    st.subheader("🤖 Your Position Simulator")
    
    # Sliders
    col_sim1, col_sim2 = st.columns(2)
    with col_sim1:
        bankroll = st.number_input("💰 Your Bankroll", value=1000.0, step=100.0)
    with col_sim2:
        copy_ratio = st.number_input("⚖️ Copy Ratio", value=10, step=5, min_value=1)
    
    # 🧠 Run simulation (clean!)
    sim_results = run_position_simulator(pos_df, bankroll, copy_ratio)
    
    if not sim_results['valid']:
        st.error(sim_results['message'])
    else:
        # Track PnL history
        track_simulation_pnl(sim_results)
        
        sim_df = sim_results['sim_df']
        total_cost = sim_results['total_cost']
        total_pnl = sim_results['total_pnl']
        skipped = sim_results['skipped']
        
        # Header metric
        sim_color = "🟢" if total_pnl >= 0 else "🔴"
        st.metric("Total Investment", f"${total_cost:,.0f}", f"{sim_color}${abs(total_pnl):,.0f}")
        
        # Bankroll + history
        if total_cost > bankroll:
            st.error(f"⚠️ Need ${total_cost:,.0f} > ${bankroll:,.0f}")
        else:
            pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
            runtime_min = (time.time() - st.session_state.sim_start_time) / 60 if st.session_state.sim_start_time else 0
            st.success(f"✅ {len(sim_df)}/{len(pos_df)} positions | Skipped {skipped} tiny | PnL: ${total_pnl:+.0f}")
        
        # 👇 CHART + RAW NUMBERS (best of both!)
        # 👇 BULLETPROOF P&L HISTORY (handles all edge cases)
        if len(st.session_state.sim_pnl_history) > 1:
            try:
                hist_df = pd.DataFrame(st.session_state.sim_pnl_history)
                
                # Fix time column
                hist_df['Time'] = hist_df['time'].apply(lambda x: f"{int(x):.0f}m")
                
                # Safe PnL % (avoid div0 + NaN)
                hist_df['PnL $'] = hist_df['pnl'].round(2)
                hist_df['PnL %'] = hist_df.apply(lambda row: f"{(row["pnl"]/total_cost*100):+.1f}%" if total_cost > 0 else "0.0%", axis=1)
                
                col_chart, col_table = st.columns(2)
                
                with col_chart:
                    st.markdown("**📈 Trend**")
                    st.line_chart(hist_df.set_index('Time')['PnL $'], height=200)
                
                with col_table:
                    st.markdown("**📊 Raw $**")
                    recent = hist_df[['Time', 'PnL $', 'PnL %']].tail(8)
                    st.dataframe(recent, use_container_width=True, hide_index=True)
                
                st.caption(f"⏱️ {len(hist_df)} snapshots | Latest: ${total_pnl:+.2f}")
                
            except Exception as e:
                st.caption("📈 History loading...")
        
        
        # 👇 Styled table (same as positions)
        sim_visible_cols = ['Market', 'UP/DOWN', 'Shares', 'Your Shares', 'AvgPrice', 'Your Avg', 
                           'Your Cost', 'Your PnL', 'Status', 'Updated']
        sim_recent_mask = sim_df['age_sec'] <= 300
        def highlight_recent_sim(row):
            if sim_recent_mask.iloc[row.name]:
                return ['background-color: rgba(0, 255, 0, 0.15)'] * len(sim_visible_cols)
            return [''] * len(sim_visible_cols)
        
        styled_sim = sim_df[sim_visible_cols].style.apply(highlight_recent_sim, axis=1)
        st.dataframe(styled_sim, height=300, hide_index=True, column_config={
            "UP/DOWN": st.column_config.TextColumn(width="medium"),
            "Your Shares": st.column_config.NumberColumn(format="%.1f", width="small"),
            "AvgPrice": st.column_config.TextColumn("Their Avg", width="small"),
            "Your Avg": st.column_config.TextColumn("Your Avg", width="small"),
            "Your Cost": st.column_config.NumberColumn(format="$%.2f", width="small"),
            "Your PnL": st.column_config.NumberColumn(format="$%.2f", width="small"),
        })
        
        st.caption(f"✅ Simulated PnL tracking | 1:{copy_ratio} | 5-share minimum")
        
        # 👇 Buttons
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if col_btn1.button("❌ Hide", use_container_width=True):
                st.session_state.show_simulate = False
                st.rerun()
        with col_btn2:
            if col_btn2.button("🛑 Stop Sim", use_container_width=True):
                st.session_state.sim_start_time = None
                st.session_state.sim_pnl_history = []
                st.session_state.show_simulate = False
                st.rerun()