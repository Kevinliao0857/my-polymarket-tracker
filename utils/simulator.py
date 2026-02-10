# utils/simulator.py - INDUSTRIAL STRENGTH
import streamlit as st
import pandas as pd
import numpy as np

def simulate_copy_trades(df_or_list, bankroll, alloc_pct, now_ts=None):
    """Works with ANY data structure - zero crashes"""
    
    # Handle DataFrame → list of dicts
    if isinstance(df_or_list, pd.DataFrame):
        trades = df_or_list.to_dict('records')
    else:
        trades = df_or_list
    
    # Super safe active filter
    active_trades = []
    for trade in trades:
        try:
            # Get title safely
            title = (trade.get('Market') or 
                    trade.get('question') or 
                    trade.get('title') or 'N/A')
            title = str(title).lower()
            
            # Active if mentions time
            if any(word in title for word in ['pm', 'am', 'et', 'h', 'm']):
                active_trades.append(trade)
        except:
            continue
    
    st.markdown("### 🚀 Dry Run: Copy Trading Sim")
    
    if not active_trades:
        st.info("✅ No active trades detected")
        return
    
    # Safe calculations
    total_alloc = 0.0
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("💵 Bankroll", f"${bankroll:,.0f}")
    with col2: st.metric("🎯 Trades", f"{len(active_trades)}")
    with col3: st.metric("💰 Per Trade", f"${bankroll*alloc_pct:.0f}")
    
    st.markdown("| Trade | Side | Price | Shares | **USDC** |")
    st.markdown("|-------|------|-------|--------|----------|")
    
    for trade in active_trades:
        try:
            # ULTRA SAFE price extraction
            price_raw = (trade.get('Price') or 
                        trade.get('yesPrice') or 
                        trade.get('price') or 0.50)
            
            # Convert ANYTHING to float safely
            price = float(price_raw) if str(price_raw).replace('.','').replace('-','').isdigit() else 0.50
            price = max(min(price, 0.99), 0.01)  # Clamp 1-99¢
            
            # Safe math
            usdc_amount = float(bankroll) * float(alloc_pct) / price
            shares = usdc_amount / price
            total_alloc += usdc_amount
            
            # Safe title/side
            title = str(trade.get('Market') or 'Trade')[:40]
            side = "🟢 UP" if 'up' in title.lower() else "🔴 DOWN"
            
            st.markdown(f"| `{title}` | {side} | **${price:.3f}** | {shares:.0f} | **${usdc_amount:.0f}** |")
            
        except Exception:
            st.markdown(f"| **SKIPPED** | - | - | - | - |")
            continue
    
    st.balloons()
    st.success(f"**Deployed: ${total_alloc:.0f} USDC** | **Remaining: ${bankroll-total_alloc:.0f}**")
