import streamlit as st
import pandas as pd
from datetime import datetime
import time
from .api import get_open_positions, track_0x8dxd, get_trader_pnl
from .config import EST, TRADER

def dry_run_copy(your_bankroll, copy_ratio):
    """Dry run copy trading simulation - ORIGINAL table styling."""
    st.markdown("### 🤖 Dry Run Copy (1:200)")
    
    # Copy your EXACT metrics layout
    pnl_data = get_trader_pnl(TRADER)
    col1, col2, col3 = st.columns(3)
    with col1:
        pnl_color = "🟢" if pnl_data['total_pnl'] >= 0 else "🔴"
        st.metric("Simulated P&L", f"{pnl_color}${abs(pnl_data['total_pnl']):,.0f}")
    with col2:
        st.metric("Positions to Copy", pnl_data['crypto_count'])
    with col3:
        your_total_size = pnl_data['total_size'] * (your_bankroll / 1000) / copy_ratio
        st.metric("Your Size", f"${your_total_size:.0f}")
    
    # Load RECENT trades (like main table)
    df = track_0x8dxd(30)  # 30min window
    if df.empty:
        st.info("No recent trades to simulate")
        return
    
    # EXACT SAME STYLING as main table
    newest_sec = df['age_sec'].min()
    newest_str = f"{int(newest_sec)//60}m {int(newest_sec)%60}s ago"
    up_bets = len(df[df['UP/DOWN'].str.contains('🟢 UP', na=False)])
    
    st.info(f"✅ {len(df)} RECENT crypto bets to copy")
    
    recent_mask = df['age_sec'] <= 30
    def highlight_recent(row):
        if recent_mask.iloc[row.name]:
            return ['background-color: rgba(0, 255, 0, 0.15)'] * 7
        return [''] * 7
    
    visible_cols = ['Market', 'UP/DOWN', 'Shares', 'Price', 'Amount', 'Status', 'Updated']
    styled_df = df[visible_cols].style.apply(highlight_recent, axis=1)
    
    st.markdown(f"""
    <div style='display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 10px;'>
        <span><b>🟢 UP:</b> {up_bets}</span>
        <span><b>🔴 DOWN:</b> {len(df)-up_bets}</span>
        <span>Newest: {newest_str}</span>
        <span>Copy Size: ${your_total_size:.0f}</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.dataframe(styled_df, height=400, hide_index=True,
                column_config={
                    "Market": st.column_config.TextColumn(width="medium"),
                    "UP/DOWN": st.column_config.TextColumn(width="medium"),
                    "Shares": st.column_config.NumberColumn(format="%.1f", width="small"),
                    "Price": st.column_config.TextColumn(width="small"), 
                    "Amount": st.column_config.NumberColumn(format="$%.2f", width="small"), 
                    "Status": st.column_config.TextColumn(width="medium")
                })

def dry_run_copy_positions(your_bankroll, copy_ratio):
    """Trigger dry run display."""
    st.session_state.show_dry_run = True
    st.rerun()

def simulate_combined(df, your_bankroll, trader, copy_ratio, hedge_minutes, hedge_ratio):
    """Combined simulation - COPIES Open Positions layout exactly."""
    st.markdown("### 🚀 Combined Copy + Hedge Results")
    st.success("✅ Simulation complete! (Copy + Hedge)")
    
    # === COPY OPEN POSITIONS TABLE EXACTLY ===
    st.markdown("---")
    st.subheader("📈 Simulated Open Positions (Avg Entry Prices)")
    
    # Get real open positions data (same source)
    pos_df = get_open_positions(TRADER)
    
    if not pos_df.empty:
        # EXACT SAME styling as your Open Positions table
        pos_visible_cols = ['Market', 'UP/DOWN', 'Shares', 'AvgPrice', 'CurPrice', 'Amount', 'PnL', 'Status', 'Updated']
        pos_recent_mask = pos_df['age_sec'] <= 300  # 5min for positions
        
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
        st.caption(f"✅ {len(pos_df)} simulated positions | Your bankroll: ${your_bankroll:,} | Ratio: 1:{copy_ratio}")
    else:
        st.info("No open positions available for simulation")
    
    # Add hedge summary
    st.markdown("### 🛡️ Hedge Analysis")
    st.info(f"🕒 {hedge_minutes}min hedge | ⚖️ 1:{hedge_ratio} ratio")

def simulate_historical_pnl(*args):
    """Historical PnL stub."""
    pass

def simulate_hedge(trader, minutes, ratio):
    """Hedge analyzer trigger."""
    st.session_state.show_hedge = True
    st.rerun()
