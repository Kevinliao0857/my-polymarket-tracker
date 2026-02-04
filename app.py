import streamlit as st
import requests
import pandas as pd
from datetime import datetime

st.set_page_config(layout="wide")

st.title("🔥 Polymarket Live Tracker - Fixed!")
search = st.sidebar.text_input("Wallet or Username", value="nanoin123")

@st.cache_data(ttl=300)
def fetch_data(query):
    data = []
    # Try positions API
    try:
        resp = requests.get(f"https://data-api.polymarket.com/positions?proxyWallet={query}", timeout=10)
        if resp.status_code == 200:
            data.extend(resp.json())
    except: pass
    
    # Try trades API
    try:
        resp = requests.get(f"https://data-api.polymarket.com/trades?user={query}", timeout=10)
        if resp.status_code == 200:
            trades = resp.json()
            if trades:
                data.append({
                    'type': 'Recent Trade',
                    'market': trades[0].get('question', 'N/A'),
                    'size
