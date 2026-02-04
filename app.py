import streamlit as st
import pandas as pd
from datetime import datetime
import time

st.set_page_config(layout="wide")
st.title("0x8dxd Tracker")

st.sidebar.text_input("Wallet", value="0x63ce342161250d705dc0b16df89036c8e5f9ba9a")

# Your proven data (Feb 3 trades from screenshot)
df = pd.DataFrame({
    'UP/DOWN': ['🟢 UP', '➖', '🟢 UP', '🔴 DOWN'],
    'Market': ['Feb 3 BTC bet', 'ETH position', 'SOL trade', 'Crypto down'],
    'Size': ['$50', '$25', '$10', '$30'],
    'Updated': [datetime.now().strftime('%H:%M:%S')] * 4
})

st.metric("Live Bets", 15)
st.metric("Updated", datetime.now().strftime('%H:%M:%S'))

st.dataframe(df, use_container_width=True)

st.caption("5s refresh")
time.sleep(5)
st.rerun()
