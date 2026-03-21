import streamlit as st
import pandas as pd

from utils.db import (
    get_active_traders,
    get_all_trades,
    get_all_settled_trades,
    get_trade_summary_by_trader,
    get_settled_summary_by_trader,
)
from utils.analytics import (
    compute_sharpe_ratio,
    compute_market_overlap,
    compute_allocation_weights,
)
from utils.hedge_analysis import compute_hedge_ratio


def show_leaderboard():
    st.header("Trader Leaderboard")

    traders = get_active_traders()
    if not traders:
        st.info("No active traders to compare.")
        return

    # --- Leaderboard Table ---
    trade_summary = {r["trader_address"]: r for r in get_trade_summary_by_trader()}
    settled_summary = {r["trader_address"]: r for r in get_settled_summary_by_trader()}

    rows = []
    trader_metrics = {}
    for t in traders:
        addr = t["trader_address"]
        alias = t.get("alias") or addr[:10]
        ts = trade_summary.get(addr, {})
        ss = settled_summary.get(addr, {})

        settled = get_all_settled_trades(trader_address=addr)
        sharpe = compute_sharpe_ratio(settled)

        trades = get_all_trades(trader_address=addr)
        hedge = compute_hedge_ratio(trades)

        total_pnl = ss.get("total_pnl", 0) or 0
        wins = ss.get("wins", 0) or 0
        count = ss.get("count", 0) or 0
        win_pct = round(wins / count * 100, 1) if count else 0

        # Compute PnL std for allocation weights
        pnls = [s.get("pnl", 0) for s in settled if s.get("pnl") is not None]
        if len(pnls) > 1:
            mean = sum(pnls) / len(pnls)
            pnl_std = (sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)) ** 0.5
        else:
            pnl_std = 0
        trader_metrics[addr] = {"pnl_std": pnl_std, "alias": alias}

        rows.append({
            "Trader": alias,
            "Trades": ts.get("trade_count", 0) or 0,
            "Settled": count,
            "Win %": win_pct,
            "Total PnL": round(total_pnl, 2),
            "Sharpe": sharpe,
            "Hedge %": hedge["hedged_pct"],
        })

    if rows:
        df = pd.DataFrame(rows).sort_values("Total PnL", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("No trade data yet")

    st.divider()

    # --- Market Overlap Matrix ---
    if len(traders) >= 2:
        st.subheader("Market Overlap")
        traders_trades = {}
        for t in traders:
            addr = t["trader_address"]
            traders_trades[t.get("alias") or addr[:10]] = get_all_trades(trader_address=addr)

        overlap = compute_market_overlap(traders_trades)
        if not overlap.empty:
            st.dataframe(overlap.style.format("{:.1f}%"), use_container_width=True)
        else:
            st.caption("Need at least 2 traders with data")

    st.divider()

    # --- Allocation Optimizer ---
    st.subheader("Allocation Optimizer")
    if len(trader_metrics) < 2:
        st.caption("Need at least 2 traders for allocation optimization")
        return

    col1, col2 = st.columns(2)
    alloc_bankroll = col1.number_input("Bankroll ($)", value=1000, min_value=100, step=100)
    method = col2.selectbox("Method", ["equal_risk", "equal"])

    weights = compute_allocation_weights(trader_metrics, method=method)
    alloc_rows = []
    for addr, weight in weights.items():
        alias = trader_metrics[addr].get("alias", addr[:10])
        alloc_rows.append({
            "Trader": alias,
            "Weight": f"{weight:.1%}",
            "Allocated": f"${alloc_bankroll * weight:,.2f}",
        })
    st.dataframe(pd.DataFrame(alloc_rows), use_container_width=True, hide_index=True)


show_leaderboard()
