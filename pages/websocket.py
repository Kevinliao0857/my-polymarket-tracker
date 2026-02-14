import streamlit as st
import threading
import time
from utils.websocket import rtds_listener, get_live_trades_count, get_recent_trader_trades

@st.cache_resource
def start_listener():
    if not any(t.name == 'rtds_listener' for t in threading.enumerate()):
        thread = threading.Thread(target=rtds_listener, daemon=True, name='rtds_listener')
        thread.start()
        st.success("🚀 Started!")
        time.sleep(2)
    return True

def show_websocket_status():
    """Compact sidebar WS - auto-collapses."""
    with st.sidebar.expander("🔴 Live WS", expanded=False):
        col1, col2 = st.columns([3,1])
        with col1:
            if st.button("🚀 Start", type="primary", use_container_width=True):
                start_listener()
                st.rerun()
        with col2:
            if st.button("🔄", key="restart"):
                st.cache_resource.clear()
                st.rerun()
        
        try:
            count = get_live_trades_count()
            recent = len(get_recent_trader_trades(300))
            c1, c2 = st.columns(2)
            with c1: st.metric("Buffer", count)
            with c2: st.metric("5m", recent)
            st.success("✅ Streaming")
        except Exception as e:
            st.warning(f"⚠️ {e}")
