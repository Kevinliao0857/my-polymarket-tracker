import streamlit as st
import threading
import time
from utils.websocket import rtds_listener, get_live_trades_count, get_recent_trader_trades

@st.cache_resource
def start_listener():
    """Start RTDS listener once."""
    if not any(t.name == 'rtds_listener' for t in threading.enumerate()):
        thread = threading.Thread(target=rtds_listener, daemon=True, name='rtds_listener')
        thread.start()
        st.success("🚀 WebSocket listener started!")
        time.sleep(2)
    return True

def show_websocket_status():
    """Sidebar + metrics for WS."""
    st.markdown("### 🔴 Live WebSocket")
    
    if st.button("🚀 Start Listener", type="primary"):
        start_listener()
        st.rerun()
    
    try:
        count = get_live_trades_count()
        recent = len(get_recent_trader_trades(300))
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Buffer", f"{count:,}")
        with col2:
            st.metric("Trader 5m", recent)
        st.success("✅ Live trades streaming!")
    except Exception as e:
        st.warning(f"⚠️ Connect listener first: {e}")
    
    if st.button("🔄 Restart WS"):
        st.cache_resource.clear()
        st.rerun()
