import streamlit as st
import pandas as pd

from utils.db import get_active_traders, get_all_trades, get_all_settled_trades, get_position_history
from utils.analytics import (
    compute_win_rate,
    compute_hold_duration,
    compute_time_of_day_patterns,
    compute_sharpe_ratio,
    analyze_entry_prices,
    analyze_exit_behavior,
    analyze_conviction,
    analyze_copy_delay_impact,
    analyze_risk_reward,
)


def show_analytics():
    st.header("Trader Strategy Analysis")

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

    # ━━━ Overview ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    win_data = compute_win_rate(settled, group_by="coin")
    rr = analyze_risk_reward(settled)
    sharpe = compute_sharpe_ratio(settled)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Win Rate", f"{win_data['overall']:.0%}",
              help=f"Based on {win_data['sample_size']} settled trades")
    c2.metric("Risk/Reward", f"{rr['risk_reward_ratio']:.1f}x",
              help="Avg win size / avg loss size")
    c3.metric("Avg Return", f"{rr['avg_return_on_capital']:.1f}%",
              help="Average return on capital per trade")
    c4.metric("Sharpe", f"{sharpe:.2f}")

    st.divider()

    # ━━━ Entry Strategy ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.subheader("Entry Strategy")
    entry = analyze_entry_prices(trades)

    if entry["sample_size"] > 0:
        col_l, col_r = st.columns(2)
        with col_l:
            st.caption(f"Mean entry: {entry['mean_entry']:.2f} | Median: {entry['median_entry']:.2f} | n={entry['sample_size']}")
            bucket_df = pd.DataFrame([
                {"Price Range": k, "Count": v}
                for k, v in entry["price_buckets"].items()
            ])
            st.bar_chart(bucket_df.set_index("Price Range")["Count"])

        with col_r:
            if win_data["by_group"]:
                st.caption("Win rate by coin")
                wr_df = pd.DataFrame([
                    {"Coin": coin, "Win Rate": rate}
                    for coin, rate in win_data["by_group"].items()
                ])
                st.bar_chart(wr_df.set_index("Coin")["Win Rate"])
            else:
                st.caption("No settled data by coin yet")
    else:
        st.caption("No BUY trades with price data yet")

    st.divider()

    # ━━━ Exit Behavior ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.subheader("Exit Behavior")
    exit_data = analyze_exit_behavior(trades, settled)

    if exit_data["sample_size"] > 0:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Early Exit", f"{exit_data['early_exit_pct']:.0f}%",
                  help="% of positions sold before settlement")
        c2.metric("Held to Settlement", f"{exit_data['held_to_settlement_pct']:.0f}%")
        c3.metric("Take-Profit", str(exit_data["exit_triggers"]["take_profit"]),
                  help="Sold above entry price")
        c4.metric("Stop-Loss", str(exit_data["exit_triggers"]["stop_loss"]),
                  help="Sold below entry price")

        if exit_data["avg_exit_pnl_pct"]:
            st.caption(
                f"Avg exit PnL: {exit_data['avg_exit_pnl_pct']:+.1f}% | "
                f"Avg hold before exit: {exit_data['avg_hold_before_exit_hours']:.1f}h"
            )
    else:
        st.caption("No position data yet")

    st.divider()

    # ━━━ Conviction ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.subheader("Conviction")
    conviction = analyze_conviction(trades, settled)

    if conviction["sample_size"] > 0:
        c1, c2, c3 = st.columns(3)
        c1.metric("Big Bet Win Rate", f"{conviction['big_bet_win_rate']:.0%}",
                  help="Win rate on above-median size trades")
        c2.metric("Small Bet Win Rate", f"{conviction['small_bet_win_rate']:.0%}")
        c3.metric("Scales In?", "Yes" if conviction["scales_in"] else "No",
                  help=f"Avg {conviction['avg_buys_per_market']:.1f} buys per market")
    else:
        st.caption("Need settled trades to analyze conviction")

    st.divider()

    # ━━━ Copy Delay Impact ━━━━━━━━━━━━━━━━━━━━━━━━━
    st.subheader("Copy Delay Impact")

    if trader_addr:
        pos_history = _load_position_history(trader_addr)
        delay = analyze_copy_delay_impact(trades, pos_history)

        if delay["delay_impact"]:
            delay_df = pd.DataFrame(delay["delay_impact"])
            st.line_chart(delay_df.set_index("delay_minutes")["avg_price_change_pct"])
            st.caption(
                f"Edge decay: {delay['edge_decay_per_minute']:+.4f}%/min | "
                f"Profitable at 5min delay: {'Yes' if delay['still_profitable_at_5m'] else 'No'} | "
                f"n={delay['sample_size']} trades"
            )
        else:
            st.caption("Need more position snapshot data to analyze copy delay")
    else:
        st.caption("Select a specific trader for copy delay analysis")

    st.divider()

    # ━━━ Risk/Reward Detail ━━━━━━━━━━━━━━━━━━━━━━━━
    if rr["by_coin"]:
        st.subheader("Risk/Reward by Coin")
        rr_df = pd.DataFrame([
            {"Coin": coin, "Avg Return %": d["return_pct"], "Risk/Reward": d["risk_reward"]}
            for coin, d in rr["by_coin"].items()
        ])
        st.dataframe(rr_df, use_container_width=True, hide_index=True)

    if rr["trades_detail"]:
        with st.expander(f"Trade Details ({len(rr['trades_detail'])} settled)"):
            st.dataframe(pd.DataFrame(rr["trades_detail"]), use_container_width=True, hide_index=True)

    st.divider()

    # ━━━ Activity ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.subheader("Activity")
    col_l, col_r = st.columns(2)

    with col_l:
        st.caption("Trading Hours (EST)")
        tod_df = compute_time_of_day_patterns(trades)
        if not tod_df.empty and tod_df["trade_count"].sum() > 0:
            st.bar_chart(tod_df.set_index("hour")["trade_count"])
        else:
            st.caption("No trade timestamp data")

    with col_r:
        hold = compute_hold_duration(trades, settled)
        st.metric("Avg Hold Duration", f"{hold['mean_hours']:.1f}h",
                  help=f"Median: {hold['median_hours']:.1f}h, n={hold['sample_size']}")


@st.cache_data(ttl=300)
def _load_trades(trader_addr):
    return get_all_trades(trader_address=trader_addr)


@st.cache_data(ttl=300)
def _load_settled(trader_addr):
    return get_all_settled_trades(trader_address=trader_addr)


@st.cache_data(ttl=300)
def _load_position_history(trader_addr):
    return get_position_history(trader_addr)


show_analytics()
