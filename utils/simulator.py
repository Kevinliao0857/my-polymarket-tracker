import streamlit as st
import pandas as pd
import time
from typing import Dict


def run_position_simulator(pos_df: pd.DataFrame, initial_bankroll: float, copy_ratio: float = 10) -> Dict:
    """Hedge-aware simulator - pairs UP/DOWN same market"""
    sim_df = pos_df.copy()
    sim_df['Your Shares'] = (sim_df['Shares'].astype(float) / copy_ratio).round(1)

    market_groups = sim_df.groupby('Market')
    paired_rows = []
    hedge_pair_count = 0

    for market, group in market_groups:
        group = group.reset_index(drop=True)

        if len(group) == 2:
            up_mask = group['UP/DOWN'].str.contains('UP', na=False)
            down_mask = group['UP/DOWN'].str.contains('DOWN', na=False)

            if up_mask.any() and down_mask.any():
                up_row = group[up_mask].iloc[0]
                down_row = group[down_mask].iloc[0]

                if up_row['Your Shares'] >= 5 and down_row['Your Shares'] >= 5:
                    paired_rows.append(up_row.to_dict())
                    paired_rows.append(down_row.to_dict())
                    hedge_pair_count += 1  # ✅ Count here, not after loop
                continue

        valid_rows = group[group['Your Shares'] >= 5].to_dict('records')
        paired_rows.extend(valid_rows)

    if not paired_rows:
        return {'valid': False, 'message': "No valid positions (hedge/single)"}

    sim_df = pd.DataFrame(paired_rows).reset_index(drop=True)

    # Ensure age_sec exists to prevent KeyError in page renderers
    if 'age_sec' not in sim_df.columns:
        sim_df['age_sec'] = 9999

    def clean_price(col):
        return pd.to_numeric(
            col.astype(str)
            .str.replace(r'[\$,′\"]', '', regex=True)
            .str.strip(),
            errors='coerce'
        ).fillna(0.0)

    avg_price = clean_price(sim_df['AvgPrice'])
    cur_price = clean_price(sim_df['CurPrice'])

    sim_df['Your Avg'] = sim_df['AvgPrice']
    sim_df['Your Cost'] = (sim_df['Your Shares'] * avg_price).round(2)
    sim_df['Your PnL'] = (sim_df['Your Shares'] * (cur_price - avg_price)).round(2)

    total_cost = sim_df['Your Cost'].sum().round(2)
    total_pnl = sim_df['Your PnL'].sum().round(2)

    return {
        'valid': True,
        'sim_df': sim_df,
        'total_cost': total_cost,
        'total_pnl': total_pnl,
        'positions': len(sim_df),
        'skipped': len(pos_df) - len(sim_df),
        'hedge_pairs': hedge_pair_count,  # ✅ Fixed
    }

def track_simulation_pnl(sim_results: Dict, initial_bankroll: float) -> None:
    """Track bankroll/PnL history snapshots over session runtime"""
    if not st.session_state.get('sim_start_time'):
        return

    runtime_min = (time.time() - st.session_state.sim_start_time) / 60
    # ✅ Now passes sim_df (which has 'Your PnL') instead of raw pos_df
    current_bankroll = get_realized_bankroll(initial_bankroll, sim_results['sim_df'])

    snapshot = {
        'time': runtime_min,
        'bankroll': current_bankroll,
        'pnl': sim_results['total_pnl'],
        'realized_pnl': current_bankroll - initial_bankroll,
        'cost': sim_results['total_cost'],
        'positions': sim_results['positions'],
    }

    if 'sim_pnl_history' not in st.session_state:
        st.session_state.sim_pnl_history = []
    st.session_state.sim_pnl_history.append(snapshot)

def get_simulated_realized_pnl(pos_df: pd.DataFrame, copy_ratio: float, initial_bankroll: float) -> float:
    """Calculate proportional realized PnL from trader's closed positions"""
    expired_mask = pos_df['Status'].str.contains(
        'expired|settled|closed|finished', case=False, na=False
    )
    expired_df = pos_df[expired_mask].copy()

    if expired_df.empty or 'PnL' not in expired_df.columns:
        return 0.0

    expired_df['Your Shares'] = (expired_df['Shares'].astype(float) / copy_ratio).round(1)
    trader_pnl = pd.to_numeric(expired_df['PnL'], errors='coerce').fillna(0.0)
    trader_shares = expired_df['Shares'].astype(float)

    # Per-share PnL scaled to your share count
    per_share_pnl = trader_pnl / trader_shares.replace(0, float('nan'))
    your_pnl = (per_share_pnl * expired_df['Your Shares']).fillna(0.0)

    return round(your_pnl.sum(), 2)

def calculate_simulated_realized(sim_df: pd.DataFrame, copy_ratio: float) -> float:
    """
    Realize PnL based on price thresholds — don't wait for API settlement.
    - CurPrice >= 0.95 → treat as WIN (resolved YES)
    - CurPrice <= 0.05 → treat as LOSS (resolved NO)
    """
    if sim_df.empty:
        return 0.0

    cur_price = pd.to_numeric(sim_df['CurPrice'], errors='coerce').fillna(0.0)
    avg_price = pd.to_numeric(sim_df['AvgPrice'], errors='coerce').fillna(0.0)
    your_shares = pd.to_numeric(sim_df['Your Shares'], errors='coerce').fillna(0.0)

    # Win: price resolved to ~$1.00
    win_mask = cur_price >= 0.95
    # Loss: price resolved to ~$0.00
    loss_mask = cur_price <= 0.05
    realized_mask = win_mask | loss_mask

    if not realized_mask.any():
        return 0.0

    realized_pnl = (your_shares[realized_mask] * (cur_price[realized_mask] - avg_price[realized_mask])).sum()
    return round(float(realized_pnl), 2)

def tag_realized_rows(sim_df: pd.DataFrame) -> pd.DataFrame:
    """Add 'Realized?' column for display — price-based, not API status"""
    cur_price = pd.to_numeric(sim_df['CurPrice'], errors='coerce').fillna(0.0)
    sim_df = sim_df.copy()
    sim_df['Realized?'] = ''
    sim_df.loc[cur_price >= 0.95, 'Realized?'] = '✅ WIN'
    sim_df.loc[cur_price <= 0.05, 'Realized?'] = '❌ LOSS'
    return sim_df

def get_realized_bankroll(initial_bankroll: float, sim_df: pd.DataFrame) -> float:
    """
    Calculate realized bankroll from ALREADY SIMULATED expired rows.
    Expects sim_df to have 'Your PnL' and 'Status' columns.
    """
    if 'Status' not in sim_df.columns or 'Your PnL' not in sim_df.columns:
        return float(initial_bankroll)

    expired_mask = sim_df['Status'].str.contains(
        'expired|settled|closed|finished', case=False, na=False
    )
    expired_pnl = pd.to_numeric(
        sim_df.loc[expired_mask, 'Your PnL'], errors='coerce'
    ).sum()

    return round(float(initial_bankroll) + expired_pnl, 2)
