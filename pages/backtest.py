import streamlit as st

from utils.db import get_active_traders
from utils.backtest import (
    BacktestConfig,
    run_backtest,
    compute_drawdown_series,
    compare_backtests,
)


def show_backtest():
    st.header("Backtesting")

    traders = get_active_traders()
    if not traders:
        st.info("No active traders. Add traders to run backtests.")
        return

    # --- Config Panel ---
    st.subheader("Configuration")

    trader_options = {
        f"{t.get('alias') or t['trader_address'][:10]}": t["trader_address"]
        for t in traders
    }
    selected_names = st.multiselect(
        "Traders", list(trader_options.keys()), default=list(trader_options.keys())
    )
    selected_addrs = [trader_options[n] for n in selected_names]

    if not selected_addrs:
        st.warning("Select at least one trader")
        return

    col1, col2, col3 = st.columns(3)
    bankroll = col1.number_input("Bankroll ($)", value=1000, min_value=100, step=100)
    copy_ratio = col2.number_input("Copy Ratio (1:X)", value=10.0, min_value=1.0, step=1.0)
    stop_loss = col3.number_input("Stop Loss %", value=0, min_value=0, max_value=100, step=5,
                                   help="0 = disabled")

    col4, col5 = st.columns(2)
    only_hedged = col4.checkbox("Only Hedged Positions")
    only_crypto = col5.checkbox("Only Crypto Markets", value=True)

    # --- Run ---
    if st.button("Run Backtest", type="primary"):
        config = BacktestConfig(
            trader_addresses=selected_addrs,
            bankroll=bankroll,
            copy_ratio=copy_ratio,
            stop_loss_pct=stop_loss if stop_loss > 0 else None,
            only_hedged=only_hedged,
            only_crypto=only_crypto,
        )

        with st.spinner("Running backtest..."):
            result = run_backtest(config)

        # Store in session for comparison
        if "backtest_results" not in st.session_state:
            st.session_state.backtest_results = []
        st.session_state.backtest_results.append(
            (f"Run {len(st.session_state.backtest_results) + 1}", result)
        )

        st.divider()

        # --- Results ---
        st.subheader("Results")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total PnL", f"${result.total_pnl:,.2f}")
        c2.metric("Win Rate", f"{result.win_rate:.1f}%")
        c3.metric("Max Drawdown", f"{result.max_drawdown_pct:.1f}%")
        c4.metric("Sharpe", f"{result.sharpe:.2f}")

        # PnL Curve
        if not result.pnl_curve.empty:
            st.subheader("PnL Curve")
            st.line_chart(result.pnl_curve.set_index("timestamp")["bankroll"])

            # Drawdown Chart
            dd = compute_drawdown_series(result.pnl_curve)
            if not dd.empty and dd["drawdown_pct"].max() > 0:
                st.subheader("Drawdown")
                st.area_chart(dd.set_index("timestamp")["drawdown_pct"])

        # Trade Log
        if not result.trades_log.empty:
            with st.expander(f"Trade Log ({len(result.trades_log)} entries)"):
                st.dataframe(result.trades_log, use_container_width=True, hide_index=True)

        st.metric("Trades Completed", result.total_trades)

    # --- Compare Previous Runs ---
    if st.session_state.get("backtest_results") and len(st.session_state.backtest_results) > 1:
        with st.expander("Compare Previous Runs"):
            labels = [r[0] for r in st.session_state.backtest_results]
            results = [r[1] for r in st.session_state.backtest_results]
            comparison = compare_backtests(results, labels)
            st.dataframe(comparison, use_container_width=True, hide_index=True)


show_backtest()
