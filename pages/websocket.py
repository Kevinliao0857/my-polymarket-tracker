import streamlit as st
import threading
import time
import utils.config as config  # ✅ Module reference, not value import
from utils.websocket import rtds_listener, get_live_trades_count, get_recent_trader_trades, live_trades


@st.cache_resource
def start_listener():
    """Start RTDS listener once — cache_resource ensures single execution."""
    if not any(t.name == 'rtds_listener' for t in threading.enumerate()):
        thread = threading.Thread(target=rtds_listener, daemon=True, name='rtds_listener')
        thread.start()
        time.sleep(2)
    return True


def show_websocket_status():
    try:
        count = get_live_trades_count()
        recent = len(get_recent_trader_trades(300))
        has_streaming = count > 0
        status_emoji = "🟢" if has_streaming else "🔴"
    except Exception:
        status_emoji = "🔴"
        has_streaming = False
        count = 0
        recent = 0

    with st.sidebar.expander(f"{status_emoji} Live WS", expanded=False):
        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            if st.button(
                f"{status_emoji} Start",
                type="secondary" if has_streaming else "primary",
                width="stretch"
            ):
                start_listener()
                st.rerun()
        with col2:
            if st.button("🔄", key="restart_ws"):
                st.cache_resource.clear()
                st.rerun()
        with col3:
            if st.button("⛔ Stop", key="disable_ws_global"):
                # ✅ Mutate the module attribute — affects all importers
                config.DISABLE_WS_LIVE = True
                live_trades.clear()
                st.success("⛔ WS disabled")
                st.rerun()

        try:
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Buffer", count)
            with c2:
                st.metric("5m trades", recent)
            if has_streaming:
                st.success("✅ Streaming!")
            else:
                st.warning("⚠️ Start listener")
        except Exception as e:
            st.error(f"❌ {e}")
