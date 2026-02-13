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
    """Calculate REAL bankroll from trader's positions (handles missing Your PnL)"""
    # Expired positions
    expired_mask = pos_df['Status'].str.contains('expired|settled|closed|finished', 
                                                 case=False, na=False)
    expired_positions = pos_df[expired_mask]
    
    if len(expired_positions) == 0:
        return initial_bankroll
    
    # Handle missing Your PnL column (use PnL if available)
    if 'Your PnL' in expired_positions.columns:
        realized_pnl = expired_positions['Your PnL'].sum()
    elif 'PnL' in expired_positions.columns:
        realized_pnl = expired_positions['PnL'].sum()
    else:
        return initial_bankroll  # No PnL data
    
    final_bankroll = initial_bankroll + realized_pnl
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
