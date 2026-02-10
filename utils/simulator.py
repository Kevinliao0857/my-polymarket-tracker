# utils/simulator.py - NO IMPORTS VERSION
import streamlit as st

def simulate_copy_trades(raw_trades, bankroll, alloc_pct, now_ts=None):
    """Copy trading simulator - ZERO external dependencies"""
    
    # Simple status check (no get_status_hybrid dependency)
    active_trades = []
    for trade in raw_trades:
        title = str(trade.get('title') or trade.get('question') or '').lower()
        # Quick heuristic: active if has time words but not "closed/settled"
        if any(word in title for word in ['pm', 'am', 'et', 'h', 'm']) and not any(word in title for word in ['closed', 'settled', 'expired']):
            active_trades.append(trade)
    
    st.markdown("### 📊 Dry Run: $1000 Bankroll")
    
    if not active_trades:
        st.info("✅ No trades detected (all expired/settled?)")
        return
    
    total_alloc = 0
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("💵 Starting", f"${bankroll:,.0f}")
    with col2: st.metric("🎯 Trades", len(active_trades))
    with col3: st.metric("⚖️ Ratio", f"1:{int(1/alloc_pct)}")
    
    st.markdown("**Per trade: ${:.0f} → {:.1f}% bankroll**".format(bankroll*alloc_pct, alloc_pct*100))
    st.markdown("| Market | Side | Price | Shares | **USDC** |")
    st.markdown("|--------|------|-------|--------|----------|")
    
    for trade in active_trades:
        title = str(trade.get('question') or trade.get('title') or 'N/A')[:45]
        price = trade.get('yesPrice') or trade.get('price') or 0.50
        price = max(price, 0.01)
        
        usdc_amount = bankroll * alloc_pct / price
        shares = usdc_amount / price
        total_alloc += usdc_amount
        
        side = "🟢 YES/UP" if 'up' in title.lower() or 'yes' in title.lower() else "🔴 NO/DOWN"
        
        st.markdown(f"| `{title}` | {side} | **${price:.3f}** | {shares:.0f} | **${usdc_amount:.0f}** |")
    
    remaining = bankroll - total_alloc
    st.balloons()
    st.success(f"🚀 **Total bet: ${total_alloc:.0f}** | **Cash left: ${remaining:.0f}**")
