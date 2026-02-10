# utils/simulator.py - WORKS WITH YOUR df DataFrame
import streamlit as st
import pandas as pd

def simulate_copy_trades(df_or_list, bankroll, alloc_pct, now_ts=None):
    """Handles both DataFrame and list of dicts"""
    
    # Convert df to list of dicts if needed
    if isinstance(df_or_list, pd.DataFrame):
        trades = df_or_list.to_dict('records')
    else:
        trades = df_or_list
    
    # Filter "active" trades (heuristic)
    active_trades = []
    for trade in trades:
        # Works with df columns OR dict keys
        market_col = trade.get('Market') or trade.get('title') or trade.get('question') or ''
        if isinstance(market_col, str) and any(word in market_col.lower() for word in ['pm', 'am', 'et', 'h', 'm']):
            active_trades.append(trade)
    
    st.markdown("### 🚀 Dry Run Simulator")
    
    if not active_trades:
        st.info("✅ All trades expired/settled")
        return
    
    total_alloc = 0
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("💰 Bankroll", f"${bankroll:,.0f}")
    with col2: st.metric("📊 Active", len(active_trades))
    with col3: st.metric("⚖️ Per Trade", f"${bankroll*alloc_pct:.0f}")
    
    st.markdown("| Market | Side | Price | Shares | **USDC** |")
    st.markdown("|--------|------|-------|--------|----------|")
    
    for trade in active_trades:
        # Flexible column/key access
        title = str(trade.get('Market') or trade.get('question') or trade.get('title') or 'N/A')[:45]
        price = trade.get('Price') or trade.get('yesPrice') or trade.get('price') or 0.50
        price = max(price, 0.01)
        
        usdc_amount = bankroll * alloc_pct / price
        shares = usdc_amount / price
        total_alloc += usdc_amount
        
        side = "🟢 UP" if 'up' in title.lower() else "🔴 DOWN"
        
        st.markdown(f"| `{title}` | {side} | **${price:.3f}** | {shares:.0f} | **${usdc_amount:.0f}** |")
    
    st.balloons()
    st.success(f"**Total: ${total_alloc:.0f} USDC** | **Remaining: ${bankroll-total_alloc:.0f}**")
