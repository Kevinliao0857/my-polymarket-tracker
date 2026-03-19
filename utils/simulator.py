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
    skipped_rows = []  # ✅ NEW
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
                    hedge_pair_count += 1
                else:
                    # ✅ Hedge pair exists but below threshold
                    for _, row in group.iterrows():
                        r = row.to_dict()
                        r['Skip Reason'] = '⚖️ Hedge below threshold'
                        skipped_rows.append(r)
                continue

        # ✅ Unhedged single position
        for _, row in group.iterrows():
            r = row.to_dict()
            r['Skip Reason'] = '🚫 Unhedged'
            skipped_rows.append(r)

    if not paired_rows:
        return {'valid': False, 'message': "No valid positions (hedge/single)"}

    sim_df = pd.DataFrame(paired_rows).reset_index(drop=True)

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

    skipped_df = pd.DataFrame(skipped_rows) if skipped_rows else pd.DataFrame()  # ✅ NEW

    return {
        'valid':       True,
        'sim_df':      sim_df,
        'total_cost':  total_cost,
        'total_pnl':   total_pnl,
        'positions':   len(sim_df),
        'skipped':     len(skipped_rows),   # ✅ CHANGED — was len(pos_df) - len(sim_df)
        'skipped_df':  skipped_df,          # ✅ NEW
        'hedge_pairs': hedge_pair_count,
    }

def track_simulation_pnl(sim_results: Dict, initial_bankroll: float, current_bankroll: float = None) -> None:
    """Track bankroll/PnL history snapshots over session runtime"""
    if not st.session_state.get('sim_start_time'):
        return

    runtime_min = (time.time() - st.session_state.sim_start_time) / 60
    if current_bankroll is None:
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

    # ✅ Thin out old entries — keep all recent (last 2hrs) but compress older ones
    history = st.session_state.sim_pnl_history
    # ✅ Only recompress when old portion has grown by 60+ new points (~5 min)
    if len(history) > 1440 and len(history) % 60 == 0:
        old = history[:-1440:6]
        recent = history[-1440:]
        st.session_state.sim_pnl_history = old + recent

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


def check_drawdown(current_bankroll: float, initial_bankroll: float, threshold_pct: float = 10.0) -> dict:
    """
    Check if bankroll has dropped below drawdown threshold.
    Returns drawdown status and metrics.
    """
    if initial_bankroll <= 0:
        return {'triggered': False, 'drawdown_pct': 0, 'drawdown_amt': 0}

    drawdown_amt = initial_bankroll - current_bankroll
    drawdown_pct = (drawdown_amt / initial_bankroll) * 100

    return {
        'triggered':    drawdown_pct >= threshold_pct,
        'drawdown_pct': round(drawdown_pct, 2),
        'drawdown_amt': round(drawdown_amt, 2),
    }

def filter_baseline_positions(pos_df: pd.DataFrame, baseline_keys: set) -> pd.DataFrame:
    if not baseline_keys:
        return pos_df
    key_series = pos_df['Market'] + '|' + pos_df['UP/DOWN']
    return pos_df[key_series.isin(baseline_keys)]

def calc_safe_ratio(pos_df: pd.DataFrame, bankroll: float, target_exposure: float = 0.80) -> dict:
    """
    Calculate copy ratio based purely on exposure target.
    5-share floor is handled per-position in run_position_simulator.
    """
    if pos_df.empty:
        return {'ratio': 10.0, 'alloc_pct': 10.0, 'est_cost': 0, 'binding': 'none'}

    shares = pos_df['Shares'].astype(float)
    avg_prices = pd.to_numeric(pos_df['AvgPrice'], errors='coerce').fillna(0)
    trader_total_cost = (shares * avg_prices).sum()

    max_spend = bankroll * target_exposure
    safe_ratio = trader_total_cost / max_spend if max_spend > 0 else 10.0
    safe_ratio = max(safe_ratio, 1.0)

    alloc_pct = round(100 / safe_ratio, 2)
    est_cost = round(trader_total_cost / safe_ratio, 2)

    return {
        'ratio':        round(safe_ratio, 1),
        'alloc_pct':    alloc_pct,
        'est_cost':     est_cost,
        'binding':      'exposure',
        'exposure_pct': round((est_cost / bankroll) * 100, 1),
    }