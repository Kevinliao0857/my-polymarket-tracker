import streamlit as st
import pandas as pd
import time
from typing import Dict

def run_position_simulator(pos_df: pd.DataFrame, initial_bankroll: float, copy_ratio: int = 10) -> Dict:
    """Hedge-aware simulator - pairs UP/DOWN same market"""
    sim_df = pos_df.copy()
    sim_df['Your Shares'] = (sim_df['Shares'].astype(float) / copy_ratio).round(1)
    
    # 👇 HEDGE PAIRING LOGIC
    market_groups = sim_df.groupby('Market')
    paired_df = []
    
    for market, group in market_groups:
        if len(group) == 2 and 'UP' in group['UP/DOWN'].str.cat() and 'DOWN' in group['UP/DOWN'].str.cat():
            # Hedge pair found - simulate BOTH if ANY >=5 shares
            up_group = group[group['UP/DOWN'].str.contains('UP')].iloc[0]
            down_group = group[group['UP/DOWN'].str.contains('DOWN')].iloc[0]
            
            if up_group['Your Shares'] >= 5 or down_group['Your Shares'] >= 5:
                paired_df.append(up_group)
                paired_df.append(down_group)
        else:
            # Single position - normal threshold
            valid_group = group[group['Your Shares'] >= 5]
            paired_df.extend(valid_group.to_dict('records'))
    
    sim_df = pd.DataFrame(paired_df).reset_index(drop=True)
    
    if len(sim_df) == 0:
        return {'valid': False, 'message': "No valid positions (hedge/single)"}
    
    # Price/PnL math (unchanged)
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
        'hedge_pairs': len(market_groups)  # Track hedge detection
    }


def get_realized_bankroll(initial_bankroll: float, sim_df: pd.DataFrame) -> float:
    """Calculate REAL bankroll: initial $ + realized PnL from EXPIRED positions"""
    # Expired/settled positions (status indicates closed/expired)
    expired_positions = sim_df[sim_df['Status'].str.contains('expired|settled|closed', case=False, na=False)]
    
    if len(expired_positions) == 0:
        return initial_bankroll  # No realized gains/losses yet
    
    # Sum realized PnL from expired positions only
    realized_pnl = expired_positions['Your PnL'].sum()
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
