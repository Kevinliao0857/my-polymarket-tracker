# utils/simulator.py
import streamlit as st
from datetime import datetime
import time

def simulate_copy_trades(trades, bankroll, alloc_pct, now_ts=None):
    """Simulate copying ACTIVE trades only"""
    if now_ts is None:
        now_ts = int(time.time())
    
    from .status import get_status_hybrid
    from ..config import EST  # Note: .. because utils/ is subdir
    
    st.markdown("### 📊 Dry Run: $1000 @ 1:200 Ratio")
    
    # Filter ACTIVE trades
    active_trades = []
    for t in trades:
        status = get_status_hybrid(t, now_ts)
        if "🟢 ACTIVE" in status:
            active_trades.append((t, status))
    
    if not active_trades:
        st.info("✅ No active trades to copy!")
        return
    
    total_alloc = 0
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("💵 Bankroll", f"${bankroll:,.0f}")
    with col2: st.metric("🎯 Active Trades", len(active_trades))
    with col3: st.metric("💰 Allocated", f"${total_alloc:.0f}")
    
    st.markdown("| Market | Side | Price | Shares | **USDC** |")
    st.markdown("|--------|------|-------|--------|----------|")
    
    for trade, status in active_trades:
        title = (trade.get('question') or trade.get('title', 'N/A'))[:40]
        price = trade.get('yesPrice') or trade.get('price') or 0.50
        
        # Kelly 1:200 sizing (0.5% bankroll per trade)
        usdc_amount = bankroll * alloc_pct / max(price, 0.01)
        shares = usdc_amount / price
        total_alloc += usdc_amount
        
        side = "🟢 YES/UP" if any(x in title.lower() for x in ['up', 'yes']) else "🔴 NO/DOWN"
        st.markdown(f"| `{title}` | {side} | ${price:.3f} | {shares:.0f} | **${usdc_amount:.0f}** |")
    
    st.success(f"🚀 **Total: ${total_alloc:.0f} USDC** across {len(active_trades)} trades")
