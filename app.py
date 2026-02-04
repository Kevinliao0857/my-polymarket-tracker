import streamlit as st
import time
from datetime import datetime
import pandas as pd

# ERROR HANDLING
try:
    from data_fetch import track_0x8dxd, est
except ImportError as e:
    st.error(f"Import error: {e}. Check data_fetch.py in same folder.")
    st.stop()

st.set_page_config(layout="wide")
st.markdown("# ₿ 0x8dxd Crypto Bot Tracker - Last 15 Min")

st.info("🟢 Live crypto-only | UP/DOWN focus | Last 15min")

now_est = datetime.now(est)
st.caption(f"🕐 Current EST: {now_est.strftime('%Y-%m-%d %H:%M:%S %Z')} | Auto 5s + Force 🔄")

if st.button("🔄 Force Refresh"):
    st.rerun()

placeholder = st.empty()
refresh_count = 0
while True:
    refresh_count += 1
    now_est = datetime.now(est)
    with placeholder.container():
        df = track_0x8dxd()
        if df.empty:
            st.info("No qualifying crypto bets in last 15 min")
        else:
            st.success(f"✅ {len(df)} crypto bets (15min ET)")
            st.dataframe(df, use_container_width=True, height=500, column_config={
                "Market": st.column_config.TextColumn("Market", width="medium"),
                "Status": st.column_config.TextColumn("Status", width="medium")
            })
            
            up_bets = len(df[df['UP/DOWN'] == '🟢 UP'])
            st.metric("🟢 UP Bets", up_bets)
            st.metric("🔴 DOWN Bets", len(df) - up_bets)
            
            df['ts'] = pd.to_datetime(df['Updated'], format='%I:%M:%S %p ET').apply(lambda x: x.timestamp())
            min_ts = df['ts'].min()
            now_ts = time.time()
            span_min = min(int((now_ts - min_ts) / 60), 15)  # Caps at 15
            st.metric("Newest", f"{span_min} min ago (ET)")
        
        st.caption(f"🕐 {now_est.strftime('%H:%M:%S ET')} | #{refresh_count}")
    time.sleep(5)
    st.rerun()
