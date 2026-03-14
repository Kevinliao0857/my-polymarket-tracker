import streamlit as st
import time
import pandas as pd
from utils.config import TRADER
from utils.api import get_open_positions, get_closed_trades_pnl
from utils.simulator import run_position_simulator, track_simulation_pnl, \
    calculate_simulated_realized, tag_realized_rows, check_drawdown
from utils.websocket import get_recent_trader_trades
from utils.copy_trader import get_latest_trader_activity, detect_new_trades, build_copy_signal

recent_trades = get_recent_trader_trades(300)

def estimate_required_capital(pos_df: pd.DataFrame, copy_ratio: float) -> dict:
    """
    Pre-flight check: estimate how much capital is needed before starting sim.
    Returns estimated cost, max single position, and whether it's safe.
    """
    if pos_df.empty:
        return {'valid': True, 'estimated_cost': 0, 'max_position': 0, 'position_count': 0}

    shares = pos_df['Shares'].astype(float) / copy_ratio
    avg_prices = pd.to_numeric(pos_df['AvgPrice'], errors='coerce').fillna(0.0)
    costs = (shares * avg_prices)

    # Filter to only positions that would pass the >=5 share threshold
    valid_mask = shares >= 5
    valid_costs = costs[valid_mask]

    return {
        'estimated_cost':  round(valid_costs.sum(), 2),
        'max_position':    round(valid_costs.max(), 2) if not valid_costs.empty else 0,
        'position_count':  int(valid_mask.sum()),
        'valid':           True
    }

def show_copy_signals(copy_ratio: float, bankroll: float, include_5m: bool = False):
    """Live copy signal feed — shows new trader buys as actionable cards"""
    raw_trades = get_latest_trader_activity(TRADER, limit=10)
    new_trades = detect_new_trades(raw_trades)

    if 'copy_queue' not in st.session_state:
        st.session_state.copy_queue = []

    for trade in new_trades:
        signal = build_copy_signal(trade, copy_ratio, include_5m=include_5m)
        if signal:
            st.session_state.copy_queue.insert(0, signal)

    st.session_state.copy_queue = st.session_state.copy_queue[:20]

    if not st.session_state.copy_queue:
        st.info("👂 Listening for new trades...")
        return

    with st.expander(f"⚡ Signals ({len(st.session_state.copy_queue)})", expanded=True):
        display_queue = st.session_state.copy_queue[:5]

        for display_i, sig in enumerate(display_queue):
            full_i = st.session_state.copy_queue.index(sig)
            age_sec = int(time.time() - sig['detected_at'])
            is_fresh = age_sec < 60
            is_copied = sig.get('status') == 'COPIED'

            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                with col1:
                    freshness = "🔴 NEW" if is_fresh else f"⏱️ {age_sec}s ago"
                    label = "~~" if is_copied else ""
                    st.markdown(f"**{freshness}** {sig['updown']} {label}`{sig['market'][:60]}`{label}")
                with col2:
                    st.metric("Your Shares", sig['your_shares'])
                with col3:
                    st.metric("Your Cost", f"${sig['your_cost']:.2f}")
                with col4:
                    if is_copied:
                        st.success("✅ Done")
                    elif st.button("✅ Copied", key=f"copied_{sig['tx_hash']}"):
                        st.session_state.copy_queue[full_i]['status'] = 'COPIED'
                        st.rerun()

        if len(st.session_state.copy_queue) > 5:
            st.caption(f"Showing 5 of {len(st.session_state.copy_queue)} signals")

def render_real_bankroll_simulator(initial_bankroll: float, copy_ratio: float):
    pos_df = get_open_positions(TRADER)
    if pos_df.empty:
        st.warning("No LIVE positions to simulate")
        return

    if 'AvgPrice' not in pos_df.columns or 'CurPrice' not in pos_df.columns:
        st.error(f"❌ Missing price columns. Got: {list(pos_df.columns)}")
        return

    sim_results = run_position_simulator(pos_df, initial_bankroll, copy_ratio)
    if not sim_results['valid']:
        st.error(sim_results['message'])
        return

    track_simulation_pnl(sim_results, initial_bankroll)

    sim_df = sim_results['sim_df']
    total_cost = sim_results['total_cost']
    total_pnl = sim_results['total_pnl']
    skipped = sim_results['skipped']

    # Price-threshold realized (positions fully resolved)
    price_realized = calculate_simulated_realized(sim_df, copy_ratio)

    # API settled realized
    closed_data = get_closed_trades_pnl(TRADER)
    api_realized = closed_data['total'] / copy_ratio

    # ✅ Use whichever has greater magnitude (handles both wins AND losses)
    simulated_realized_pnl = price_realized if abs(price_realized) >= abs(api_realized) else api_realized

    # ✅ Unrealized PnL also reflected in bankroll so it can dip below starting
    current_bankroll = initial_bankroll + simulated_realized_pnl + total_pnl
    sim_df = tag_realized_rows(sim_df)

    # ✅ DRAWDOWN CIRCUIT BREAKER
    drawdown_threshold = st.session_state.get('drawdown_threshold', 10.0)
    drawdown = check_drawdown(current_bankroll, initial_bankroll, drawdown_threshold)

    if drawdown['triggered']:
        # Check if user has already made a decision
        dd_decision = st.session_state.get('drawdown_decision', None)

        if dd_decision is None:
            # ⛔ Pause and prompt — don't render the rest of the sim
            st.error(
                f"🚨 **DRAWDOWN ALERT** — Bankroll dropped "
                f"${drawdown['drawdown_amt']:,.2f} "
                f"({drawdown['drawdown_pct']:.1f}%) below starting bankroll. "
                f"Simulation paused."
            )
            st.warning(
                f"Started: ${initial_bankroll:,.2f} → "
                f"Current: ${current_bankroll:,.2f}"
            )

            col_dd1, col_dd2 = st.columns(2)
            with col_dd1:
                if st.button("⚠️ Continue Anyway", type="secondary", use_container_width=True):
                    st.session_state.drawdown_decision = 'continue'
                    st.rerun()
            with col_dd2:
                if st.button("🛑 Stop Simulation", type="primary", use_container_width=True):
                    st.session_state.drawdown_decision = 'stop'
                    st.rerun()
            return  # ← pauses rendering below this point

        elif dd_decision == 'stop':
            st.error("🛑 Simulation stopped due to drawdown limit.")
            st.metric("Final Bankroll", f"${current_bankroll:,.2f}",
                      f"-${drawdown['drawdown_amt']:,.2f} ({drawdown['drawdown_pct']:.1f}%)")
            if st.button("🔄 Reset & Start Fresh"):
                for key in ['sim_start_time', 'sim_pnl_history', 'drawdown_decision',
                            'initial_bankroll', 'allocation_pct']:
                    st.session_state.pop(key, None)
                st.rerun()
            return  # ← stops all rendering

        elif dd_decision == 'continue':
            # Show a persistent but non-blocking warning
            st.warning(
                f"⚠️ Running with {drawdown['drawdown_pct']:.1f}% drawdown "
                f"(${drawdown['drawdown_amt']:,.2f} below start) — "
                f"monitor closely."
            )

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("🏦 Simulated Bankroll", f"${current_bankroll:,.0f}", f"${simulated_realized_pnl:+,.0f}")
    with col2:
        usage_pct = (total_cost / current_bankroll * 100) if current_bankroll > 0 else 0
        usage_color = "🟢" if usage_pct <= 50 else "🟡" if usage_pct <= 80 else "🔴"
        st.metric("💼 Capital Used", f"{usage_color}${total_cost:,.0f}", f"{usage_pct:.0f}%")
    with col3:
        st.metric("📈 Unrealized PnL", f"${total_pnl:+,.0f}")
    with col4:
        st.metric("💰 Simulated Realized", f"${simulated_realized_pnl:+,.0f}")
    with col5:
        st.metric("📊 Simulated", f"{len(sim_df)}/{len(sim_df) + skipped}")

    allocation_pct = (total_cost / current_bankroll * 100) if current_bankroll > 0 else 0
    runtime_min = (time.time() - st.session_state.sim_start_time) / 60
    st.caption(f"⏱️ {runtime_min:.1f}min | {allocation_pct:.0f}% alloc | "
               f"🛡️ {sim_results['hedge_pairs']} hedge pairs")


    # ✅ MID-SIM OVER-EXPOSURE GUARD
    if total_cost > current_bankroll:
        over_amt = total_cost - current_bankroll
        over_pct = (over_amt / current_bankroll) * 100

        oe_decision = st.session_state.get('overexposure_decision', None)

        if oe_decision is None:
            st.error(
                f"🚨 **OVER-EXPOSED** — Current positions cost ${total_cost:,.2f} "
                f"but simulated bankroll is only ${current_bankroll:,.2f}. "
                f"You are ${over_amt:,.2f} ({over_pct:.0f}%) over budget."
            )
            col_oe1, col_oe2 = st.columns(2)
            with col_oe1:
                if st.button("⚠️ Continue Anyway", key="oe_continue", type="secondary", use_container_width=True):
                    st.session_state.overexposure_decision = 'continue'
                    st.rerun()
            with col_oe2:
                if st.button("🛑 Stop Simulation", key="oe_stop", type="primary", use_container_width=True):
                    st.session_state.overexposure_decision = 'stop'
                    st.rerun()
            return

        elif oe_decision == 'stop':
            st.error("🛑 Simulation stopped — over-exposure limit reached.")
            st.metric("Final Bankroll", f"${current_bankroll:,.2f}",
                      f"-${over_amt:,.2f} over budget")
            if st.button("🔄 Reset & Start Fresh", key="oe_reset"):
                for key in ['sim_start_time', 'sim_pnl_history', 'overexposure_decision',
                            'initial_bankroll', 'allocation_pct', 'drawdown_decision']:
                    st.session_state.pop(key, None)
                st.rerun()
            return

        elif oe_decision == 'continue':
            st.warning(
                f"⚠️ Running over-exposed — ${over_amt:,.2f} ({over_pct:.0f}%) "
                f"over current bankroll of ${current_bankroll:,.2f}."
            )

    elif total_cost > current_bankroll * 0.80:
        st.warning(
            f"⚠️ **High exposure** — ${total_cost:,.2f} is "
            f"{total_cost/current_bankroll*100:.0f}% of current bankroll ${current_bankroll:,.2f}."
        )

    # Hedge marker
    market_groups = sim_df.groupby('Market')
    hedge_markets = {
        m for m, g in market_groups
        if len(g) >= 2 and g['UP/DOWN'].str.contains('UP').any()
    }
    sim_df['Hedge?'] = sim_df['Market'].apply(lambda x: '🛡️ Hedge' if x in hedge_markets else '')

    if len(st.session_state.get('sim_pnl_history', [])) > 1:
        with st.expander("📈 PnL History Charts", expanded=False):
            hist_df = pd.DataFrame(st.session_state.sim_pnl_history)
            hist_df['Time'] = hist_df['time'].apply(lambda x: f"{int(x)}m")
            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                st.line_chart(hist_df.set_index('Time')['bankroll'], height=200)
            with col_chart2:
                st.line_chart(hist_df.set_index('Time')['pnl'], height=200)

    sim_cols = ['Market', 'UP/DOWN', 'Status', 'Your Shares', 'Your Cost', 'Your PnL', 'Realized?', 'Hedge?']
    recent_mask = sim_df['age_sec'] <= 300

    def highlight_recent(row):
        if recent_mask.iloc[row.name]:
            return ['background-color: rgba(0, 255, 0, 0.15)'] * len(sim_cols)
        return [''] * len(sim_cols)

    st.dataframe(
        sim_df[sim_cols].style.apply(highlight_recent, axis=1),
        use_container_width=True, height=350, hide_index=True
    )

    if skipped > 0:
        st.markdown("---")
        with st.expander(f"⏭️ Skipped Positions ({skipped})", expanded=False):
            skipped_df = pos_df.copy()
            skipped_df['Your Shares'] = (skipped_df['Shares'].astype(float) / copy_ratio).round(1)
            skipped_df = skipped_df[skipped_df['Your Shares'] < 5]
            if not skipped_df.empty:
                st.dataframe(
                    skipped_df[['Market', 'UP/DOWN', 'Shares', 'Your Shares']],
                    use_container_width=True
                )

def render_simulator():
    saved_bankroll = st.session_state.get('initial_bankroll', 1000.0)
    # ✅ Derive copy_ratio from stored allocation_pct, matching show_simulator()
    saved_allocation_pct = st.session_state.get('allocation_pct', 10.0)
    copy_ratio = 100 / saved_allocation_pct

    pos_df = get_open_positions(TRADER)
    if pos_df.empty:
        st.warning("No positions to simulate")
        return

    sim_results = run_position_simulator(pos_df, saved_bankroll, copy_ratio)
    if not sim_results['valid']:
        st.error(sim_results['message'])
        return

    track_simulation_pnl(sim_results, saved_bankroll)

    sim_df = sim_results['sim_df']
    total_cost = sim_results['total_cost']
    total_pnl = sim_results['total_pnl']
    skipped = sim_results['skipped']

    sim_color = "🟢" if total_pnl >= 0 else "🔴"
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.metric("💵 Cost", f"${total_cost:,.0f}", f"{sim_color}${abs(total_pnl):,.0f}")
    with col_m2:
        st.metric("📊 Positions", f"{len(sim_df)}/{len(sim_df) + skipped}")

    pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    runtime_min = (time.time() - st.session_state.sim_start_time) / 60

    if total_cost > saved_bankroll:
        st.error(f"⚠️ Need ${total_cost:,.0f} > ${saved_bankroll:,.0f}")
    else:
        st.success(
            f"✅ {len(sim_df)} positions | ${total_pnl:+.0f} ({pnl_pct:+.1f}%) | "
            f"{runtime_min:.1f}min | 1:{copy_ratio:.0f}"
        )

    if len(st.session_state.get('sim_pnl_history', [])) > 1:
        with st.expander("📈 PnL History", expanded=False):
            try:
                hist_df = pd.DataFrame(st.session_state.sim_pnl_history)
                hist_df['Time'] = hist_df['time'].apply(lambda x: f"{int(x)}m")
                st.line_chart(hist_df.set_index('Time')['pnl'], height=200)
            except Exception:
                pass

    sim_cols = ['Market', 'UP/DOWN', 'Your Shares', 'Your Cost', 'Your PnL', 'Status']
    recent_mask = sim_df['age_sec'] <= 300

    def highlight_recent(row):
        if recent_mask.iloc[row.name]:
            return ['background-color: rgba(0, 255, 0, 0.15)'] * len(sim_cols)
        return [''] * len(sim_cols)

    st.dataframe(
        sim_df[sim_cols].style.apply(highlight_recent, axis=1),
        use_container_width=True, height=300, hide_index=True,
        column_config={
            "Your Shares": st.column_config.NumberColumn(format="%.1f"),
            "Your Cost": st.column_config.NumberColumn(format="$%.2f"),
            "Your PnL": st.column_config.NumberColumn(format="$%.2f"),
            "Status": st.column_config.TextColumn("Status/Expiry"),
        }
    )
    st.caption("✅ Green rows = active <5min | Status shows expiry/active")

def show_simulator():
    with st.expander("🤖 Position Simulator", expanded=False):
        if 'sim_start_time' not in st.session_state:
            st.session_state.sim_start_time = None
        if 'sim_pnl_history' not in st.session_state:
            st.session_state.sim_pnl_history = []

        col1, col2, col3 = st.columns(3)
        with col1:
            initial_bankroll = st.number_input("💰 Starting Bankroll", value=1000.0, step=100.0)
        with col2:
            allocation_pct = st.number_input(
                "⚖️ Allocation %", value=10.0, min_value=1.0, max_value=100.0, step=1.0,
                help="10% = copy 10% of trader's shares (equiv 1:10)"
            )
        with col3:
            drawdown_threshold = st.number_input(
                "🛑 Drawdown %", value=10.0, min_value=1.0, max_value=50.0, step=1.0,
                help="Pause sim if bankroll drops by this % from start"
            )
        st.session_state.drawdown_threshold = drawdown_threshold

        copy_ratio = 100 / allocation_pct

        # ✅ PRE-FLIGHT CAPITAL CHECK
        pos_df = get_open_positions(TRADER)
        preflight = estimate_required_capital(pos_df, copy_ratio)
        estimated_cost = preflight['estimated_cost']
        max_position = preflight['max_position']
        position_count = preflight['position_count']

        # Safety checks
        over_bankroll = estimated_cost > initial_bankroll
        over_50pct = estimated_cost > (initial_bankroll * 0.50)
        over_80pct = estimated_cost > (initial_bankroll * 0.80)

        # Display pre-flight summary
        st.markdown("#### 🛡️ Pre-Flight Check")
        pf_col1, pf_col2, pf_col3 = st.columns(3)
        with pf_col1:
            st.metric("📊 Positions to Copy", position_count)
        with pf_col2:
            cost_color = "🔴" if over_bankroll else "🟡" if over_80pct else "🟢"
            st.metric("💸 Estimated Cost", f"{cost_color} ${estimated_cost:,.2f}")
        with pf_col3:
            st.metric("📌 Largest Position", f"${max_position:,.2f}")

        # Warnings
        if over_bankroll:
            st.error(
                f"🚫 **Insufficient funds** — estimated cost ${estimated_cost:,.2f} "
                f"exceeds bankroll ${initial_bankroll:,.2f}. "
                f"Lower allocation % or increase bankroll."
            )
        elif over_80pct:
            st.warning(
                f"⚠️ **High exposure** — ${estimated_cost:,.2f} is "
                f"{estimated_cost/initial_bankroll*100:.0f}% of your bankroll. "
                f"Consider lowering allocation %."
            )
        elif over_50pct:
            st.warning(
                f"🟡 **Moderate exposure** — ${estimated_cost:,.2f} uses "
                f"{estimated_cost/initial_bankroll*100:.0f}% of bankroll."
            )
        else:
            st.success(
                f"✅ **Safe to run** — ${estimated_cost:,.2f} uses "
                f"{estimated_cost/initial_bankroll*100:.0f}% of bankroll. "
                f"Note: costs may increase if trader adds positions mid-session."
            )

        if st.button("🗑️ CLEAR CACHES", key="nuke_cache"):
            st.cache_data.clear()
            st.rerun()
        st.info("💡 Click 'CLEAR CACHES' if Simulated Realized stuck at $0")

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            # ✅ Disable Start button if over bankroll
            start_disabled = over_bankroll
            if col_btn1.button(
                "🚀 Start Sim",
                type="primary",
                use_container_width=True,
                disabled=start_disabled  
            ):
                st.session_state.initial_bankroll = initial_bankroll
                st.session_state.allocation_pct = allocation_pct
                if st.session_state.sim_start_time is None:
                    st.session_state.sim_start_time = time.time()
                    st.session_state.sim_pnl_history = []
                st.rerun()
        with col_btn2:
            if col_btn2.button("🛑 Reset", use_container_width=True):
                for key in ['sim_start_time', 'sim_pnl_history', 'initial_bankroll', 'allocation_pct', 'drawdown_decision', 'overexposure_decision']:
                    st.session_state.pop(key, None)
                st.rerun()

        if st.session_state.sim_start_time:
            include_5m = st.session_state.get('include_5m', False)
            render_real_bankroll_simulator(
                st.session_state.get('initial_bankroll', 1000.0),
                100 / st.session_state.get('allocation_pct', 10.0),
            )
            st.markdown("---")
            show_copy_signals(
                copy_ratio=100 / st.session_state.get('allocation_pct', 10.0),
                bankroll=st.session_state.get('initial_bankroll', 1000.0),
                include_5m=include_5m,
            )

