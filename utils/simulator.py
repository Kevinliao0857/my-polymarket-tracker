import streamlit as st
import pandas as pd
from .api import get_open_positions
from .config import TRADER

def dry_run_copy(your_bankroll, copy_ratio):
    """Dry run copy trading simulation."""
    st.markdown("### 🤖 Dry Run Copy (1:200)")
    st.info(f"💰 Bankroll: ${your_bankroll:,.0f} | ⚖️ Ratio: 1:{copy_ratio}")
    
    positions = get_open_positions(TRADER)
    if positions.empty:
        st.warning("No open positions to copy")
        return
    
    total_size = positions['Amount'].sum()
    your_size = total_size * (your_bankroll / 1000) / copy_ratio
    st.metric("Your Copy Size", f"${your_size:.0f}", delta=your_size)
    
    st.dataframe(positions[['Market', 'Shares', 'Amount', 'PnL']])

def dry_run_copy_positions(your_bankroll, copy_ratio):
    """Copy current open positions (dry run)."""
    st.session_state.show_dry_run = True
    st.rerun()

def simulate_combined(df, your_bankroll, trader, copy_ratio, hedge_minutes, hedge_ratio):
    """Combined simulation results."""
    st.markdown("### 🚀 Combined Copy + Hedge Results")
    st.success("✅ Simulation complete!")
    st.info(f"📊 {len(df)} trades analyzed | 💰 ${your_bankroll:,} | ⚖️ 1:{copy_ratio}")
    if not df.empty:
        st.bar_chart(df.groupby('UP/DOWN')['Amount'].sum())

def simulate_historical_pnl(*args):
    """Historical PnL simulation."""
    st.info("📈 Historical PnL simulation (stub)")

def simulate_hedge(trader, minutes, ratio):
    """Hedge analysis."""
    st.session_state.show_hedge = True
    st.rerun()
