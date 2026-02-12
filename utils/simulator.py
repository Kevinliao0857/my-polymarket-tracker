import streamlit as st
import pandas as pd
import time
from datetime import datetime
from typing import Optional, List, Dict

def run_position_simulator(pos_df: pd.DataFrame, bankroll: float, copy_ratio: int = 10) -> Dict:
    """Core simulation logic - returns results dict"""
    sim_df = pos_df.copy()
    sim_df['Your Shares'] = (sim_df['Shares'].astype(float) / copy_ratio).round(1)
    sim_df['Buy?'] = sim_df['Your Shares'] >= 5
    sim_df = sim_df[sim_df['Buy?']].copy().reset_index(drop=True)
    
    if len(sim_df) == 0:
        return {'valid': False, 'message': "No positions ≥5 shares!"}
    
    # Price math
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
        'skipped': len(pos_df) - len(sim_df)
    }

def track_simulation_pnl(sim_results, bankroll: float) -> None:
    """Track PnL history - FIXED for Streamlit"""
    if 'sim_start_time' in st.session_state and st.session_state.sim_start_time:
        runtime_min = (time.time() - st.session_state.sim_start_time) / 60
        snapshot = {
            'time': runtime_min, 
            'pnl': sim_results['total_pnl'], 
            'portfolio': bankroll + sim_results['total_pnl'],
            'cost': sim_results['total_cost'],
            'positions': sim_results['positions']
        }
        st.session_state.sim_pnl_history.append(snapshot)

