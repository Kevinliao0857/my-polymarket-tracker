import streamlit as st
import pandas as pd

from utils.db import get_active_traders, get_all_trades
from utils.hedge_analysis import (
    identify_hedge_pairs,
    compute_hedge_ratio,
    compute_hedge_timing,
    compute_hedge_symmetry,
    classify_hedge_style,
)


def show_hedge_analysis():
    st.header("Hedge Analysis")

    traders = get_active_traders()
    options = [f"{t.get('alias') or t['trader_address'][:10]}" for t in traders]

    if not options:
        st.info("No active traders. Add traders to start analysis.")
        return

    selection = st.selectbox("Select Trader", options)
    idx = options.index(selection)
    trader_addr = traders[idx]["trader_address"]

    trades = _load_trades(trader_addr)
    if not trades:
        st.info("No trade data collected yet for this trader.")
        return

    pairs = identify_hedge_pairs(trades)
    hedge_data = compute_hedge_ratio(trades)
    timing = compute_hedge_timing(pairs)
    symmetry = compute_hedge_symmetry(pairs)
    style = classify_hedge_style(hedge_data, timing, symmetry)

    # --- Metrics Row ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Hedge Ratio", f"{hedge_data['hedged_pct']:.0f}%")
    c2.metric("Symmetry", f"{symmetry['perfectly_symmetric_pct']:.0f}%",
              help="% of pairs with size ratio 0.95-1.05")
    c3.metric("Avg Delay", f"{timing['mean_delay_sec']:.0f}s",
              help=f"Median: {timing['median_delay_sec']:.0f}s")
    c4.metric("Style", style)

    st.divider()

    # --- Hedge Pairs Table ---
    if pairs:
        st.subheader(f"Hedge Pairs ({len(pairs)})")
        rows = []
        for p in pairs:
            rows.append({
                "Market": (p["market"] or "")[:60],
                "UP Size": p["up_size"],
                "DOWN Size": p["down_size"],
                "Ratio": p["size_ratio"],
                "Delay (s)": p["time_delta_sec"],
                "Symmetric": "Yes" if p["symmetric"] else "No",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No hedge pairs found")

    st.divider()

    # --- Cross-Trader Comparison ---
    if len(traders) > 1:
        st.subheader("Cross-Trader Hedge Comparison")
        comparison_rows = []
        for t in traders:
            addr = t["trader_address"]
            alias = t.get("alias") or addr[:10]
            t_trades = get_all_trades(trader_address=addr)
            if not t_trades:
                continue
            t_pairs = identify_hedge_pairs(t_trades)
            t_hedge = compute_hedge_ratio(t_trades)
            t_timing = compute_hedge_timing(t_pairs)
            t_sym = compute_hedge_symmetry(t_pairs)
            t_style = classify_hedge_style(t_hedge, t_timing, t_sym)
            comparison_rows.append({
                "Trader": alias,
                "Hedge %": t_hedge["hedged_pct"],
                "Symmetry %": t_sym["perfectly_symmetric_pct"],
                "Avg Delay (s)": t_timing["mean_delay_sec"],
                "Style": t_style,
            })
        if comparison_rows:
            st.dataframe(pd.DataFrame(comparison_rows), use_container_width=True, hide_index=True)


@st.cache_data(ttl=300)
def _load_trades(trader_addr):
    return get_all_trades(trader_address=trader_addr)


show_hedge_analysis()
