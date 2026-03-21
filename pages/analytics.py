import streamlit as st

from utils.db import get_active_traders, get_all_trades, get_all_settled_trades
from utils.analytics import (
    compute_win_rate,
    compute_position_size_stats,
    compute_pnl_distribution,
    compute_hold_duration,
    compute_time_of_day_patterns,
)
from utils.hedge_analysis import compute_hedge_ratio


def show_analytics():
    st.header("Trader Analytics")

    traders = get_active_traders()
    options = ["All Traders"] + [
        f"{t.get('alias') or t['trader_address'][:10]}" for t in traders
    ]
    selection = st.selectbox("Select Trader", options)

    if selection == "All Traders":
        trader_addr = None
    else:
        idx = options.index(selection) - 1
        trader_addr = traders[idx]["trader_address"]

    trades = _load_trades(trader_addr)
    settled = _load_settled(trader_addr)

    if not settled and not trades:
        st.info("No data collected yet. Wait for the collector to gather trades.")
        return

    # --- Metrics Row ---
    win_data = compute_win_rate(settled, group_by="coin")
    size_stats = compute_position_size_stats(trades)
    hold_data = compute_hold_duration(trades, settled)
    hedge_data = compute_hedge_ratio(trades)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Win Rate", f"{win_data['overall']:.0%}",
              help=f"Based on {win_data['sample_size']} settled trades")
    c2.metric("Avg Position Size", f"${size_stats['mean']:,.0f}",
              help=f"Median: ${size_stats['median']:,.0f}")
    c3.metric("Hedge Ratio", f"{hedge_data['hedged_pct']:.0f}%",
              help=f"{hedge_data['hedged_count']} hedged / {hedge_data['hedged_count'] + hedge_data['directional_count']} total")
    c4.metric("Avg Hold", f"{hold_data['mean_hours']:.1f}h",
              help=f"Median: {hold_data['median_hours']:.1f}h, n={hold_data['sample_size']}")

    st.divider()

    # --- Charts ---
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("PnL Distribution")
        pnl_df = compute_pnl_distribution(settled)
        if not pnl_df.empty:
            st.bar_chart(pnl_df.set_index("coin")["pnl"] if len(pnl_df) < 50
                         else pnl_df["pnl"])
        else:
            st.caption("No settled trade data")

    with col_right:
        st.subheader("Trading Hours (EST)")
        tod_df = compute_time_of_day_patterns(trades)
        if not tod_df.empty and tod_df["trade_count"].sum() > 0:
            st.bar_chart(tod_df.set_index("hour")["trade_count"])
        else:
            st.caption("No trade timestamp data")

    # --- Win Rate by Coin ---
    if win_data["by_group"]:
        st.subheader("Win Rate by Coin")
        import pandas as pd
        wr_df = pd.DataFrame([
            {"Coin": coin, "Win Rate": rate}
            for coin, rate in win_data["by_group"].items()
        ])
        st.bar_chart(wr_df.set_index("Coin")["Win Rate"])


@st.cache_data(ttl=300)
def _load_trades(trader_addr):
    return get_all_trades(trader_address=trader_addr)


@st.cache_data(ttl=300)
def _load_settled(trader_addr):
    return get_all_settled_trades(trader_address=trader_addr)


show_analytics()
