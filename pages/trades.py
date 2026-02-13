import streamlit as st
from utils.api import track_0x8dxd

def show_trades(minutes_back):
    df = track_0x8dxd(minutes_back)

    if df.empty:
        st.info("No crypto trades found")
    else:
        newest_sec = df['age_sec'].min()
        newest_str = f"{int(newest_sec)//60}m {int(newest_sec)%60}s ago"
        span_sec = df['age_sec'].max()
        span_str = f"{int(span_sec)//60}m {int(span_sec)%60}s"
        up_bets = len(df[df['UP/DOWN'].str.contains('🟢 UP', na=False)])

        st.info(f"✅ {len(df)} LIVE crypto bets ({minutes_back}min window)")

        recent_mask = df['age_sec'] <= 30
        def highlight_recent(row):
            if recent_mask.iloc[row.name]:
                return ['background-color: rgba(0, 255, 0, 0.15)'] * 7
            return [''] * 7

        visible_cols = ['Market', 'UP/DOWN', 'Shares', 'Price', 'Amount', 'Status', 'Updated']
        styled_df = df[visible_cols].style.apply(highlight_recent, axis=1)

        st.markdown("""
        <div style='display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 10px;'>
            <span><b>🟢 UP:</b> {}</span>
            <span><b>🔴 DOWN:</b> {}</span>
            <span>Newest: {}</span>
            <span>Span: {}</span>
        </div>
        """.format(up_bets, len(df)-up_bets, newest_str, span_str), unsafe_allow_html=True)

        st.dataframe(styled_df, height=400, hide_index=True,
             column_config={
                "Market": st.column_config.TextColumn(width="medium"),
                "UP/DOWN": st.column_config.TextColumn(width="medium"),
                "Shares": st.column_config.NumberColumn(format="%.1f", width="small"),
                "Price": st.column_config.TextColumn(width="small"), 
                "Amount": st.column_config.NumberColumn(format="$%.2f", width="small"), 
                "Status": st.column_config.TextColumn(width="medium")
             })