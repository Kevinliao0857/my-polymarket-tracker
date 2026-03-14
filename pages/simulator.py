import streamlit as st
import time
import pandas as pd
from utils.config import TRADER
from utils.api import get_open_positions, get_closed_trades_pnl
from utils.simulator import run_position_simulator, track_simulation_pnl, calculate_simulated_realized, tag_realized_rows
from utils.websocket import get_recent_trader_trades
from utils.copy_trader import get_latest_trader_activity, detect_new_trades, build_copy_signal

recent_trades = get_recent_trader_trades(300)

def show_copy_signals(copy_ratio: float, bankroll: float):
    """Live copy signal feed — shows new trader buys as actionable cards"""
    st.subheader("⚡ Live Copy Signals")

    raw_trades = get_latest_trader_activity(TRADER, limit=10)
    new_trades = detect_new_trades(raw_trades)

    if 'copy_queue' not in st.session_state:
        st.session_state.copy_queue = []

    for trade in new_trades:
        signal = build_copy_signal(trade, copy_ratio)
        if signal:
            st.session_state.copy_queue.insert(0, signal)

    st.session_state.copy_queue = st.session_state.copy_queue[:20]

    if not st.session_state.copy_queue:
        st.info("👂 Listening for new trades...")
        return

    for i, sig in enumerate(st.session_state.copy_queue):
        age_sec = int(time.time() - sig['detected_at'])
        is_fresh = age_sec < 60
        is_copied = sig.get('status') == 'COPIED'

        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            with col1:
                freshness = "🔴 NEW" if is_fresh else f"⏱️ {age_sec}s ago"
                label = "~~" if is_copied else ""  # strikethrough if copied
                st.markdown(f"**{freshness}** {sig['updown']} {label}`{sig['market'][:60]}`{label}")
            with col2:
                st.metric("Your Shares", sig['your_shares'])
            with col3:
                st.metric("Your Cost", f"${sig['your_cost']:.2f}")
            with col4:
                if is_copied:
                    st.success("✅ Done")
                elif st.button("✅ Copied", key=f"copied_{i}_{sig['tx_hash']}"):
                    st.session_state.copy_queue[i]['status'] = 'COPIED'
                    st.rerun()

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

    simulated_realized_pnl = calculate_simulated_realized(sim_df, copy_ratio)
    closed_data = get_closed_trades_pnl(TRADER)
    api_realized = closed_data['total'] / copy_ratio
    simulated_realized_pnl = max(simulated_realized_pnl, api_realized)
    current_bankroll = initial_bankroll + simulated_realized_pnl
    sim_df = tag_realized_rows(sim_df)


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

    # Hedge marker
    market_groups = sim_df.groupby('Market')
    hedge_markets = {
        m for m, g in market_groups
        if len(g) >= 2 and g['UP/DOWN'].str.contains('UP').any()
    }
    sim_df['Hedge?'] = sim_df['Market'].apply(lambda x: '🛡️ Hedge' if x in hedge_markets else '')

    if len(st.session_state.get('sim_pnl_history', [])) > 1:
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

        col1, col2 = st.columns(2)
        with col1:
            initial_bankroll = st.number_input("💰 Starting Bankroll", value=1000.0, step=100.0)
        with col2:
            allocation_pct = st.number_input(
                "⚖️ Allocation %", value=10.0, min_value=1.0, max_value=100.0, step=1.0,
                help="10% = copy 10% of trader's shares (equiv 1:10)"
            )

        if st.button("🗑️ CLEAR CACHES", key="nuke_cache"):
            st.cache_data.clear()
            st.rerun()
        st.info("💡 Click 'CLEAR CACHES' if Simulated Realized stuck at $0")

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if col_btn1.button("🚀 Start Sim", type="primary", use_container_width=True):
                st.session_state.initial_bankroll = initial_bankroll
                st.session_state.allocation_pct = allocation_pct  # ✅ Used by both renderers
                if st.session_state.sim_start_time is None:
                    st.session_state.sim_start_time = time.time()
                    st.session_state.sim_pnl_history = []
                st.rerun()
        with col_btn2:
            if col_btn2.button("🛑 Reset", use_container_width=True):
                for key in ['sim_start_time', 'sim_pnl_history', 'initial_bankroll', 'allocation_pct']:
                    st.session_state.pop(key, None)
                st.rerun()

        if st.session_state.sim_start_time:
            render_real_bankroll_simulator(
                st.session_state.get('initial_bankroll', 1000.0),
                100 / st.session_state.get('allocation_pct', 10.0),
            )
            st.markdown("---")
            show_copy_signals(
                copy_ratio=100 / st.session_state.get('allocation_pct', 10.0),
                bankroll=st.session_state.get('initial_bankroll', 1000.0),
            )

