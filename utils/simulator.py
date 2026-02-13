import streamlit as st
import pandas as pd
import time
from typing import Dict


def run_position_simulator(pos_df: pd.DataFrame, initial_bankroll: float, copy_ratio: int = 10) -> Dict:
    """Hedge-aware simulator - pairs UP/DOWN same market"""
    sim_df = pos_df.copy()
    sim_df['Your Shares'] = (sim_df['Shares'].astype(float) / copy_ratio).round(1)
    
    # 👇 FIXED HEDGE PAIRING LOGIC
    market_groups = sim_df.groupby('Market')
    paired_rows = []  # List of dicts for safe DataFrame construction

    for market, group in market_groups:
        group = group.reset_index(drop=True)

        if len(group) == 2:
            up_mask = group['UP/DOWN'].str.contains('UP', na=False)
            down_mask = group['UP/DOWN'].str.contains('DOWN', na=False)

            if up_mask.any() and down_mask.any():
                up_row = group[up_mask].iloc[0]
                down_row = group[down_mask].iloc[0]

                # ✅ BOTH must have >=5 Your Shares → include pair, else skip both
                if up_row['Your Shares'] >= 5 and down_row['Your Shares'] >= 5:
                    paired_rows.append(up_row.to_dict())
                    paired_rows.append(down_row.to_dict())
                continue  # Skip normal single logic
            
        # Single positions only (non-hedges)
        valid_rows = group[group['Your Shares'] >= 5].to_dict('records')
        paired_rows.extend(valid_rows)

    sim_df = pd.DataFrame(paired_rows).reset_index(drop=True)
    
    if len(sim_df) == 0:
        return {'valid': False, 'message': "No valid positions (hedge/single)"}
    
    # Rest unchanged...
    avg_price = sim_df['AvgPrice'].str.replace('$', '').astype(float)
    cur_price = sim_df['CurPrice'].str.replace('$', '').astype(float)
    
    sim_df['Your Avg'] = sim_df['AvgPrice']
    sim_df['Your Cost'] = (sim_df['Your Shares'] * avg_price).round(2)
    sim_df['Your PnL'] = sim_df['Your Shares'] * (cur_price - avg_price).round(2)
    
    total_cost = sim_df['Your Cost'].sum().round(2)
    total_pnl = sim_df['Your PnL'].sum().round(2)
    
    return {
        'valid': True,
        'sim_df': sim_df,
        'total_cost': total_cost,
        'total_pnl': total_pnl,
        'positions': len(sim_df),
        'skipped': len(pos_df) - len(sim_df),
        'hedge_pairs': len([m for m, g in market_groups if len(g) == 2 and g['UP/DOWN'].str.contains('UP').any() and g['UP/DOWN'].str.contains('DOWN').any()])  # Improved count
    }


def get_realized_bankroll(initial_bankroll: float, pos_df: pd.DataFrame) -> float:
    """Safe realized PnL calc - handles missing columns"""
    expired_mask = pos_df['Status'].str.contains('expired|settled|closed|finished', 
                                                 case=False, na=False)
    expired_positions = pos_df[expired_mask]
    
    if len(expired_positions) == 0:
        return float(initial_bankroll)
    
    # Safe PnL column lookup (try multiple possible names)
    pnl_col = None
    for col in ['Your PnL', 'PnL', 'pnl', 'profit_loss', 'P&L']:
        if col in expired_positions.columns:
            pnl_col = col
            break
    
    if pnl_col is None:
        print(f"WARNING: No PnL column found in {list(expired_positions.columns)}")
        return float(initial_bankroll)
    
    realized_pnl = pd.to_numeric(expired_positions[pnl_col], errors='coerce').sum()
    final_bankroll = float(initial_bankroll) + realized_pnl
    return round(final_bankroll, 2)

def track_simulation_pnl(sim_results, initial_bankroll: float) -> None:
    """Track real bankroll history"""
    if 'sim_start_time' in st.session_state and st.session_state.sim_start_time:
        runtime_min = (time.time() - st.session_state.sim_start_time) / 60
        current_bankroll = get_realized_bankroll(initial_bankroll, sim_results['sim_df'])
        
        snapshot = {
            'time': runtime_min,
            'bankroll': current_bankroll,
            'pnl': sim_results['total_pnl'],
            'realized_pnl': current_bankroll - initial_bankroll,
            'cost': sim_results['total_cost'],
            'positions': sim_results['positions']
        }
        if 'sim_pnl_history' not in st.session_state:
            st.session_state.sim_pnl_history = []
        st.session_state.sim_pnl_history.append(snapshot)

def get_simulated_realized_pnl(pos_df: pd.DataFrame, copy_ratio: int, initial_bankroll: float) -> float:
    """Calculate realized PnL from trader positions using current copy ratio"""
    # Filter expired positions
    expired_mask = pos_df['Status'].str.contains('expired|settled|closed|finished', case=False, na=False)
    expired_df = pos_df[expired_mask].copy()
    
    if len(expired_df) == 0:
        return 0.0
    
    # Calculate Your Shares for expired positions
    expired_df['Your Shares'] = (expired_df['Shares'].astype(float) / copy_ratio).round(1)
    
    # Calculate PnL (safe column handling)
    if 'PnL' in expired_df.columns:
        trader_pnl = pd.to_numeric(expired_df['PnL'], errors='coerce')
    else:
        return 0.0
    
    avg_price = pd.to_numeric(expired_df['AvgPrice'].str.replace('$', ''), errors='coerce')
    your_pnl = expired_df['Your Shares'] * trader_pnl  # Proportional PnL
    
    return your_pnl.sum()

