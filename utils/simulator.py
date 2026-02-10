import streamlit as st
import pandas as pd
import numpy as np

def safe_float(value):
    """Handles '$1,000', '1k', 'N/A', None → float"""
    if pd.isna(value) or value is None:
        return 0.0
    try:
        cleaned = (str(value)
                  .replace('$', '')
                  .replace(',', '')
                  .replace('k', '*1000')
                  .replace('K', '*1000')
                  .strip())
        if cleaned.lower() in ['n/a', 'nan', '']:
            return 0.0
        return float(cleaned)
    except:
        return 0.0

def simulate_copy_trades(df, your_bankroll, ratio=200):
    trades = df.to_dict('records') if isinstance(df, pd.DataFrame) else df
    active_trades = [t for t in trades if any(w in str(t.get('Market','')).lower() 
                                             for w in ['pm','am','et','h','m'])]
    
    st.markdown("### 🚀 Copy Trading 1:{}".format(ratio))
    
    if not active_trades:
        st.info("No active trades")
        return
    
    total_trader = 0
    total_your = 0
    
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("👤 Trader", f"${total_trader:.0f}")
    with col2: st.metric("🧑 You 1:{}".format(ratio), f"${total_your:.0f}")
    with col3: st.metric("💰 Bankroll", f"${your_bankroll:.0f}")
    
    st.markdown("| Market | Trader $ | Price | Your Shares | **Your $** |")
    st.markdown("|--------|----------|-------|-------------|------------|")
    
    for trade in active_trades:
        trader_size = safe_float(trade.get('Size'))
        price = max(safe_float(trade.get('Price')), 0.01)
        
        your_usdc = trader_size / ratio
        your_shares = your_usdc / price
        
        total_trader += trader_size
        total_your += your_usdc
        
        title = str(trade.get('Market') or 'N/A')[:40]
        side = "🟢 UP" if 'up' in title.lower() else "🔴 DOWN"
        
        st.markdown(f"| `{title}` | **${trader_size:.0f}** | **${price:.3f}** | {your_shares:.0f} | **${your_usdc:.0f}** |")
    
    st.success(f"**Trader: ${total_trader:.0f}** → **You: ${total_your:.0f}** | Remaining: **${your_bankroll-total_your:.0f}**")
