import streamlit as st
import pandas as pd
import time
from utils.api import get_open_positions
from utils.simulator import run_position_simulator, track_simulation_pnl
from utils.config import TRADER

st.set_page_config(layout="wide", page_title="Position Simulator")

# SIMULATOR PAGE
st.markdown("# 🤖 Position Simulator")
st.caption("Copy trader positions with your bankroll • 5-share minimum • Real-time PnL")

# Controls
col1, col2, col3 = st.columns([2, 2, 1])
with col1:
    bankroll = st.number_input("💰 Your Bankroll", value=1000.0, step=100.0, min_value=100.0)
with col2:
    copy_ratio = st.number_input("⚖️ Copy Ratio", value=10, step=5, min_value=1, max_value=50)
with col3:
    if st.button("🔄 Refresh Positions", type="secondary"):
        st.rerun()

# Initialize session state
if 'sim_start_time' not in st.session_state:
    st.session_state.sim_start_time = None
if 'sim_pnl_history' not in st.session_state:
    st.session_state.sim_pnl_history = []

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    if col_btn1.button("🚀 Start Simulation", type="primary", use_container_width=True):
        st.session_state.bankroll = bankroll
        st.session_state.copy_ratio = copy_ratio
        if st.session_state.sim_start_time is None:
            st.session_state.sim_start_time = time.time()
            st.session_state.sim_pnl_history = []
        st.rerun()

with col_btn2:
    if col_btn2.button("🛑 Stop & Reset", type="secondary", use_container_width=True):
        st.session_state.sim_start_time = None
        st.session_state.sim_pnl_history = []
        st.session_state.pop('bankroll', None)
        st.session_state.pop('copy_ratio', None)
        st.rerun()

# MAIN SIMULATION LOGIC
if st.session_state.sim_start_time:
    saved_bankroll = st.session_state.get('bankroll', bankroll)
    saved_copy_ratio = st.session_state.get('copy_ratio', copy_ratio)
    
    pos_df = get_open_positions(TRADER)
    if pos_df.empty:
        st.warning("❌ No open positions to simulate")
    else:
        sim_results = run_position_simulator(pos_df, saved_bankroll, saved_copy_ratio)
        
        if not sim_results['valid']:
            st.error(sim_results['message'])
        else:
            track_simulation_pnl(sim_results, saved_bankroll)
            render_results(sim_results, saved_bankroll, saved_copy_ratio)

def render_results(sim_results, bankroll, copy_ratio):
    sim_df = sim_results['sim_df']
    total_cost = sim_results['total_cost']
    total_pnl = sim_results['total_pnl']
    skipped = sim_results['skipped']
    
    # Header metrics
    sim_color = "🟢" if total_pnl >= 0 else "🔴"
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("💵 Total Cost", f"${total_cost:,.0f}")
    with col_m2:
        st.metric("📈 PnL", f"{sim_color}${abs(total_pnl):,.0f}")
    with col_m3:
        pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
        st.metric("🎯 PnL %", f"{pnl_pct:+.1f}%")
    
    # Status
    runtime_min = (time.time() - st.session_state.sim_start_time) / 60
    st.success(f"✅ {len(sim_df)}/{len(sim_df)+skipped} positions simulated | "
              f"Runtime: {runtime_min:.1f}min | Ratio: 1:{copy_ratio}")
    
    if total_cost > bankroll:
        st.error(f"⚠️ Positions cost ${total_cost:,.0f} > your ${bankroll:,.0f} bankroll")
    
    # History chart
    if len(st.session_state.sim_pnl_history) > 1:
        render_pnl_history()
    
    # Simulated positions table
    render_positions_table(sim_df)

def render_pnl_history():
    try:
        hist_df = pd.DataFrame(st.session_state.sim_pnl_history)
        hist_df['Time'] = hist_df['time'].apply(lambda x: f"{int(x):.0f}m")
        hist_df['Portfolio $'] = hist_df['portfolio'].round(2)
        hist_df['PnL $'] = hist_df['pnl'].round(2)
        hist_df['PnL %'] = (hist_df['pnl'] / hist_df['cost'] * 100).round(2)
        
        col_chart, col_table = st.columns(2)
        with col_chart:
            st.markdown("**📈 PnL Trend**")
            st.line_chart(hist_df.set_index('Time')['PnL $'], height=250, use_container_width=True)
        with col_table:
            st.markdown("**📊 History**")
            recent = hist_df[['Time', 'PnL $', 'PnL %', 'positions']].tail(10)
            st.dataframe(recent, use_container_width=True, hide_index=True)
        
        st.caption(f"⏱️ {len(hist_df)} snapshots | Latest: ${hist_df['PnL $'].iloc[-1]:+.2f}")
    except Exception as e:
        st.caption("📈 Building history...")

def render_positions_table(sim_df):
    st.markdown("---")
    st.subheader("📋 Simulated Positions")
    
    visible_cols = ['Market', 'UP/DOWN', 'Shares', 'Your Shares', 'AvgPrice', 
                   'Your Cost', 'Your PnL', 'Status', 'Updated']
    
    recent_mask = sim_df['age_sec'] <= 300
    def highlight_recent(row):
        if recent_mask.iloc[row.name]:
            return ['background-color: rgba(0, 255, 0, 0.15)'] * len(visible_cols)
        return [''] * len(visible_cols)
    
    styled_sim = sim_df[visible_cols].style.apply(highlight_recent, axis=1)
    st.dataframe(styled_sim, height=400, hide_index=True, column_config={
        "Your Shares": st.column_config.NumberColumn(format="%.1f", width="small"),
        "Your Cost": st.column_config.NumberColumn(format="$%.2f", width="small"),
        "Your PnL": st.column_config.NumberColumn(format="$%.2f", width="small"),
        "UP/DOWN": st.column_config.TextColumn(width="medium"),
    })
    
    st.caption("✅ Real-time PnL | Green rows = updated <5min | Uses trader's avgPrice")
