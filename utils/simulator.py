# utils/simulator.py
import streamlit as st
from datetime import datetime
from .status import get_status_hybrid  # Your status function
from .config import EST

def simulate_copy_trades(trades, bankroll, alloc_pct):
    """Simulate $1000 @ 1:200 copying all ACTIVE trades"""
    st.markdown("### 📊 Dry Run Results")
    
    # Filter active trades only
    active_trades = [t for t in trades if "🟢 ACTIVE" in get_status_hybrid(t, int(datetime.now(EST).timestamp()))]
    
    total_alloc = 0
    col1, col2, col3 = st.columns(3)
    
    with col1: st.metric("💵 Bankroll", f"${bankroll:,.0f}")
    with col2: st.metric("🎯 Active Trades", len(active_trades))
    with col3: st.metric("💼 Allocation", f"${total_alloc:.0f}")
    
    if not active_trades:
        st.info("✅ No active trades to copy!")
        return
    
    st.markdown("| Market | Side | Price | Shares | USDC |")
    st.markdown("|--------|------|-------|--------|------|")
    
    for trade in active_trades:
        title = trade.get('question', trade.get('title', 'N/A'))[:40]
        price = trade.get('yesPrice', 0.50)  # Use actual API price
        
        # 1:200 sizing
        usdc_amount = bankroll * alloc_pct / max(price, 0.01)
        shares = usdc_amount / price
        
        total_alloc += usdc_amount
        
        side_emoji = "🟢 UP" if "up" in title.lower() else "🔴 DOWN"
        st.markdown(f"| `{title}` | {side_emoji} | ${price:.3f} | **{shares:.0f}** | **${usdc_amount:.0f}** |")
    
    st.success(f"💰 **Total Deployed: ${total_alloc:.0f}** | Remaining: ${bankroll-total_alloc:.0f}")
