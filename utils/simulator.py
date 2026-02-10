import streamlit as st
import pandas as pd
import re

def parse_usd(value):
    """$1,234 → 1234.0, N/A → 0, 1k → 1000"""
    if pd.isna(value) or value is None:
        return 0.0
    text = str(value).upper()
    if 'N/A' in text or 'NAN' in text:
        return 0.0
    
    # Extract numbers: $1,234.56 → 1234.56
    nums = re.findall(r'[\d,]+\.?\d*', text.replace('$', ''))
    if nums:
        num = float(nums[0].replace(',', ''))
        if 'K' in text:
            num *= 1000
        return num
    return 0.0

def simulate_copy_trades(df, your_bankroll, ratio=200):
    trades = df.to_dict('records')
    
    # 👇 LENIENT FILTER - catches ALL time-based bets
    active_trades = []
    for trade in trades:
        title = str(trade.get('Market', '')).lower()
        # ANY time indicator
        if any(word in title for word in ['6pm', '7pm', '8pm', '9pm', '10pm', 'pm', 'am', 'et', 'h ']):
            active_trades.append(trade)
    
    st.markdown(f"### 🚀 Copy Trading 1:{ratio}")
    
    if not active_trades:
        st.warning("⚠️ No time-based bets found - expand MINUTES_BACK slider")
        return
    
    total_trader = 0
    total_your = 0
    valid_trades = 0
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("👤 Trader Total", f"${total_trader:.0f}")
    with col2: st.metric("🧑 Your Total", f"${total_your:.0f}")
    with col3: st.metric("✅ Valid Bets", valid_trades)
    with col4: st.metric("💰 Bankroll", f"${your_bankroll:.0f}")
    
    st.markdown("| Market | Trader Size | Price | Your Shares | **Your USDC** |")
    st.markdown("|--------|-------------|-------|-------------|---------------|")
    
    for trade in active_trades:
        trader_size = parse_usd(trade.get('Size'))
        price_raw = trade.get('Price')
        price = parse_usd(price_raw) if price_raw else 0.50
        price = max(min(price, 0.99), 0.01)
        
        if trader_size > 0:  # Only valid sizes
            your_usdc = trader_size / ratio
            your_shares = max(your_usdc / price, 5)  # 👇 MIN 5 SHARES[web:59]
            
            # Polymarket MIN ORDER ~$2.50
            min_order = 5 * price
            your_usdc = max(your_usdc, min_order)
            
            total_trader += trader_size
            total_your += your_usdc
            valid_trades += 1
            
            title = str(trade.get('Market') or 'N/A')[:40]
            side = "🟢 UP" if 'up' in title.lower() else "🔴 DOWN"
            
            st.markdown(f"| `{title}` | **${trader_size:.0f}** | **${price:.3f}** | {your_shares:.0f} | **${your_usdc:.2f}** |")
        else:
            st.markdown(f"| `{trade.get('Market', 'N/A')[:40]}` | **$0** | **{price_raw}** | **INVALID** | **SKIPPED** |")
    
    # MIN ORDER WARNING
    st.info(f"⚠️ **Polymarket min: 5 shares (~${price:.2f} USDC)** | Total valid: {valid_trades}/{len(active_trades)}")
    
    st.success(f"**Trader: ${total_trader:.0f}** → **You: ${total_your:.2f}** (1:{ratio})")
