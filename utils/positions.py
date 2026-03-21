import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import time

from .config import EST, TICKERS, FULL_NAMES
from .status import get_status_hybrid


def _is_crypto_position(title: str) -> bool:
    """Reuse the same ticker/name list from config — single source of truth"""
    t = title.lower()
    return any(ticker in t for ticker in TICKERS + FULL_NAMES)


def _truncate(title: str, max_len: int = 85) -> str:
    return (title[:max_len] + '...') if len(title) > max_len else title


@st.cache_data(ttl=30)
def get_open_positions(address: str) -> pd.DataFrame:
    """📈 Trader's OPEN positions → true avgPrice per market/outcome"""
    try:
        url = f"https://data-api.polymarket.com/positions?user={address}&sizeThreshold=0"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return pd.DataFrame()

        positions = response.json()

        try:
            from .db import insert_position_snapshot
            insert_position_snapshot(address, positions)
        except Exception:
            pass

        df_data = []
        now_ts = int(time.time())

        for pos in positions:
            raw_title = str(pos.get('title') or '')
            if not _is_crypto_position(raw_title):  # ✅ Full ticker list
                continue

            outcome = str(pos.get('outcome', '')).upper()
            size = abs(float(pos.get('size', 0) or 0))
            avg_price = float(pos.get('avgPrice') or 0.50)
            cur_price = float(pos.get('curPrice') or avg_price)

            updown = "🟢 UP" if "UP" in outcome else "🔴 DOWN"
            updown_price = f"{updown} @ ${avg_price:.2f}"

            # ✅ Positions endpoint uses 'startDate' or 'createdAt', not 'timestamp'
            ts_field = (
                pos.get('startDate')
                or pos.get('createdAt')
                or pos.get('updatedAt')
            )
            try:
                # ISO string (e.g. "2025-03-01T12:00:00Z") or unix int
                if isinstance(ts_field, str):
                    ts = int(pd.Timestamp(ts_field).timestamp())
                else:
                    ts = int(float(ts_field)) if ts_field else now_ts
            except Exception:
                ts = now_ts

            age_sec = now_ts - ts
            update_str = datetime.fromtimestamp(ts, EST).strftime('%I:%M:%S %p ET')
            status_str = get_status_hybrid(pos, now_ts)

            cash_pnl = float(pos.get('cashPnl') or 0.0)

            df_data.append({
                'Market':    _truncate(raw_title),
                'UP/DOWN':   updown_price,
                'Shares':    round(size, 1),           # ✅ Numeric
                'AvgPrice':  round(avg_price, 4),      # ✅ Numeric
                'CurPrice':  round(cur_price, 4),      # ✅ Numeric
                'Amount':    round(size * avg_price, 2),
                'PnL':       round(cash_pnl, 2),       # ✅ Numeric, no "$"
                'Status':    status_str,
                'Updated':   update_str,
                'age_sec':   age_sec,
            })

        df = pd.DataFrame(df_data)
        if not df.empty:
            df = df.sort_values('age_sec').reset_index(drop=True)
        return df

    except Exception as e:
        st.error(f"positions fetch error: {e}")
        return pd.DataFrame()
