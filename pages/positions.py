import streamlit as st
from utils.api import get_open_positions

def show_positions(trader):
    pos_df = get_open_positions(trader)
    if not pos_df.empty:
        st.markdown("---")
        st.subheader("📈 Open Positions")
        pos_visible_cols = ['Market', 'UP/DOWN', 'Shares', 'AvgPrice', 'CurPrice', 'Amount', 'PnL', 'Status', 'Updated']
        pos_recent_mask = pos_df['age_sec'] <= 300
        def highlight_recent_pos(row):
            if pos_recent_mask.iloc[row.name]:
                return ['background-color: rgba(0, 255, 0, 0.15)'] * len(pos_visible_cols)
            return [''] * len(pos_visible_cols)
        
        styled_pos = pos_df[pos_visible_cols].style.apply(highlight_recent_pos, axis=1)
        st.dataframe(styled_pos, height=300, hide_index=True, column_config={
            "UP/DOWN": st.column_config.TextColumn(width="medium"),
            "AvgPrice": st.column_config.NumberColumn(format="$%.2f", width="small"),
            "CurPrice": st.column_config.NumberColumn(format="$%.2f", width="small"),
            "Amount": st.column_config.NumberColumn(format="$%.2f", width="small"),
            "PnL": st.column_config.NumberColumn(format="$%.2f", width="small"),
        })
        st.caption(f"✅ {len(pos_df)} positions")