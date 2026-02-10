# utils/simulator.py - TRUE 1:200 POSITION MATCHING
import streamlit as st
import pandas as pd

def simulate_copy_trades(df, your_bankroll, ratio=200, now_ts=None):
    """Matches trader's EXACT position sizes at 1:200 ratio"""
    
    # Convert df → trades
    trades = df.to_dict('records') if isinstance(df, pd.DataFrame) else df
    active_trades = [t for t in trades if any(word in str(t.get('Market','')).lower() 
                                              for word in ['pm','am','et','h','m'])]
    
    st.markdown("### 🚀 1:200 Copy Trading")
    
    if not active_trades:
        st.info("No active trades")
        return
    
    total_trader_size = 0
    total_your_size = 0
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("👤 Trader Size", f"${total_trader_size:.0f}")
    with col2: st.metric("🧑‍💻 Your Size (1:{})".format(ratio), f"${total_your_size:.0f}")
    with col3: st.metric("💰 Your Bankroll", f"${your_bankroll:.0f}")
    with col4: st.metric("📊 Active", len(active_trades))
    
    st.markdown("| Market | Trader Size | Price | Your Shares | **Your USDC** |")
    st.markdown("|--------|-------------|-------|-------------|---------------|")
    
    for trade in active_trades:
        trader_size_raw = trade.get('Size') or 0
        price_raw = trade.get('Price') or 0.50
        
        # Safe parsing
        trader_size = float(trader_size_raw) if str(trader_size_raw).replace('.','').replace(',','').replace('$','').isdigit() else 0
        price = float(price_raw) if str(price_raw).replace('.','').isdigit() else 0.50
        price = max(min(price, 0.99), 0.01)
        
        # 👇 TRUE 1:200: Your size = trader_size / 200
        your_size_usdc = trader_size / ratio
        your_shares = your_size_usdc / price
        
        total_trader_size += trader_size
        total_your_size += your_size_usdc
        
        title = str(trade.get('Market') or 'N/A')[:40]
        side = "🟢 UP" if 'up' in title.lower() else "🔴 DOWN"
        
        st.markdown(f"| `{title}` | **${trader_size:.0f}** | **${price:.3f}** | {your_shares:.0f} | **${your_size_usdc:.0f}** |")
    
    remaining = your_bankroll - total_your_size
    st.balloons()
    st.success(f"**Trader: ${total_trader_size:.0f}** → **You: ${total_your_size:.0f} (1:{ratio})** | Remaining: **${remaining:.0f}**")
