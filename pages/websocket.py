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
    """Dynamic color + compact WS."""
    with st.sidebar.expander("🔴 Live WS", expanded=False):
        try:
            count = get_live_trades_count()
            recent = len(get_recent_trader_trades(300))
            is_active = count > 0 or recent > 0
            
            status_emoji = "🟢" if is_active else "🔴"
            
            col1, col2 = st.columns([3,1])
            with col1:
                if st.button(f"{status_emoji} Start", type="primary" if not is_active else "secondary", use_container_width=True):
                    start_listener()
                    st.rerun()
            with col2:
                if st.button("🔄", key="restart"):
                    st.cache_resource.clear()
                    st.rerun()
            
            c1, c2 = st.columns(2)
            with c1: st.metric("Buffer", count)
            with c2: st.metric("5m", recent)
            
            st.success("✅ Streaming!") if is_active else st.warning("⚠️ Start listener")
            
        except Exception as e:
            st.error(f"❌ {e}")
