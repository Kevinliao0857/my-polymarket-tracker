import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
from .config import EST, TRADER


@st.cache_data(ttl=2)
def safe_fetch(url: str) -> List[Dict[str, Any]]:
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return data[:500]
    except json.JSONDecodeError:
        pass
    except Exception:
        pass
    return []


@st.cache_data(ttl=60)
def get_market_enddate(condition_id: str, slug: str = None) -> str:
    """Get exact end time from Polymarket Gamma API."""
    try:
        if condition_id:
            url = f"https://gamma-api.polymarket.com/markets?conditionIds={condition_id}"
        elif slug:
            url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
        else:
            return None
            
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            markets = resp.json()
            if markets and isinstance(markets, list) and markets:
                market = markets[0]
                end_iso = market.get('endDateIso') or market.get('end_date_iso')
                if end_iso:
                    end_dt = pd.to_datetime(end_iso).tz_convert(EST)
                    return end_dt.strftime('%I:%M %p ET')
    except:
        pass
    return None

