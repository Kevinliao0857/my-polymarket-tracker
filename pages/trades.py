import streamlit as st
from utils.api import track_0x8dxd


def show_trades(minutes_back: int, include_5m: bool = False):
    df = track_0x8dxd(minutes_back, include_5m=include_5m)

    rest_count = len(df)
    try:
        from utils.websocket import get_live_trades_count
        ws_count = get_live_trades_count()
        st.sidebar.success(f"🚀 {rest_count} tracked | {ws_count} live WS")
    except Exception:
        st.sidebar.info(f"📊 {rest_count} tracked trades")

    if df.empty:
        st.info("No crypto trades found")
        return

    newest_sec = df['age_sec'].min()
    span_sec = df['age_sec'].max()
    newest_str = f"{int(newest_sec) // 60}m {int(newest_sec) % 60}s ago"
    span_str = f"{int(span_sec) // 60}m {int(span_sec) % 60}s"
    up_bets = len(df[df['UP/DOWN'].str.contains('🟢 UP', na=False)])

    st.info(f"✅ {len(df)} LIVE crypto bets ({minutes_back}min window)")

    st.markdown(
        "<div style='display:flex;justify-content:space-between;font-size:13px;margin-bottom:10px;'>"
        f"<span><b>🟢 UP:</b> {up_bets}</span>"
        f"<span><b>🔴 DOWN:</b> {len(df) - up_bets}</span>"
        f"<span>Newest: {newest_str}</span>"
        f"<span>Span: {span_str}</span>"
        "</div>",
        unsafe_allow_html=True
    )

    visible_cols = ['Market', 'UP/DOWN', 'Shares', 'Price', 'Amount', 'Status', 'Updated']
    recent_mask = df['age_sec'] <= 30
    n_cols = len(visible_cols)  # ✅ Dynamic — won't silently break if cols change

    def highlight_recent(row):
        return (['background-color: rgba(0, 255, 0, 0.15)'] * n_cols
                if recent_mask.iloc[row.name] else [''] * n_cols)

    # ✅ Shares stored as float from trades.py fix — NumberColumn now works
    st.dataframe(
        df[visible_cols].style.apply(highlight_recent, axis=1),
        height=400, hide_index=True,
        column_config={
            "Market":   st.column_config.TextColumn(width="medium"),
            "UP/DOWN":  st.column_config.TextColumn(width="medium"),
            "Shares":   st.column_config.NumberColumn(format="%.1f", width="small"),
            "Price":    st.column_config.TextColumn(width="small"),
            "Amount":   st.column_config.NumberColumn(format="$%.2f", width="small"),
            "Status":   st.column_config.TextColumn(width="medium"),
        }
    )
