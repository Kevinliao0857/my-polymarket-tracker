import streamlit as st
import pandas as pd
import re
import requests
from datetime import datetime, timedelta
from collections import defaultdict

def parse_usd(value):
    """$1,234 → 1234.0, N/A → 0, 1k → 1000"""
    if pd.isna(value) or value is None:
        return 0.0
    text = str(value).upper()
    if 'N/A' in text or 'NAN' in text:
        return 0.0
    nums = re.findall(r'[\d,]+\.?\d*', text.replace('$', ''))
    if nums:
        num = float(nums[0].replace(',', ''))
        if 'K' in text:
            num *= 1000
        return num
    return 0.0

def simulate_copy_trades(df, your_bankroll, ratio=200):
    """Blind copy trades - your original working version"""
    trades = df.to_dict('records')
    
    # Time filter
    active_trades = [t for t in trades 
                    if any(word in str(t.get('Market', '')).lower() 
                          for word in ['6pm', '7pm', '8pm', '9pm', '10pm', 'pm', 'am', 'et', 'h '])]
    
    if not active_trades:
        st.warning("⚠️ No time-based bets found")
        return
    
    # 👇 TOTALS (skip tiny)
    total_trader = total_your = valid_trades = 0
    for trade in active_trades:
        trader_size = parse_usd(trade.get('Amount'))
        if trader_size <= 0: continue
        
        price = max(min(parse_usd(trade.get('Price')) or 0.50, 0.99), 0.01)
        ratiod_usdc = trader_size / ratio
        min_order = 5 * price
        
        if ratio > 0 and ratiod_usdc >= min_order:
            your_usdc = max(ratiod_usdc, min_order)
            total_trader += trader_size
            total_your += your_usdc
            valid_trades += 1
    
    # Display
    with st.expander(f"🚀 Blind Copy 1:{ratio} ({valid_trades}/{len(active_trades)})", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Trader Total", f"${total_trader:.2f}")
        with col2: st.metric("Your Total", f"${total_your:.2f}")
        with col3: st.metric("Valid", valid_trades)
        with col4: st.metric("Bankroll", f"${your_bankroll:.0f}")
        
        if total_your > your_bankroll * 1.1:
            st.error(f"⚠️ Exceeds bankroll!")
        
        # Table (same logic)
        table_rows = ["| Market | Trader $ | Price | Ratio'd | Shares | Your $ |"]
        table_rows.append("|--------|----------|-------|---------|--------|---------|")
        for trade in active_trades:
            trader_size = parse_usd(trade.get('Amount'))
            if trader_size <= 0: continue
            
            price = max(min(parse_usd(trade.get('Price')) or 0.50, 0.99), 0.01)
            title = str(trade.get('Market', 'N/A'))[:35]
            ratiod_usdc = trader_size / ratio
            min_order = 5 * price
            
            if ratio > 0 and ratiod_usdc >= min_order:
                your_usdc = max(ratiod_usdc, min_order)
                shares = max(your_usdc / price, 5)
                table_rows.append(f"| `{title}` | **${trader_size:.2f}** | **${price:.3f}** | **${ratiod_usdc:.2f}** | {shares:.0f} | **${your_usdc:.2f}** |")
            else:
                table_rows.append(f"| `{title}` | **${trader_size:.2f}** | **${price:.3f}** | **${ratiod_usdc:.2f}** | **0** | **SKIPPED** |")
        
        st.markdown("\n".join(table_rows))
        st.success(f"Trader: ${total_trader:.0f} → You: ${total_your:.2f}")

def simulate_historical_pnl(closed_pnl, ratio=200):
    """Backtest P&L"""
    if closed_pnl['crypto_count'] == 0:
        st.info("📭 No closed trades")
        return
    
    your_pnl = closed_pnl['total'] / ratio
    col1, col2 = st.columns(2)
    with col1: st.metric("Their Closed", f"${closed_pnl['total']:.0f}")
    with col2:
        color = "🟢" if your_pnl >= 0 else "🔴"
        st.metric("Your P&L", f"{color}${abs(your_pnl):,.0f}")
    
    st.success(f"Backtest: ${your_pnl:.0f} (1:{ratio})")

def simulate_hedge(wallet_address: str = TRADER, minutes_back: int = 15, ratio: int = 200):
    """Smart hedge: net Up/Down positions"""
    url = f"https://data-api.polymarket.com/positions?user={wallet_address}&limit=500"
    try:
        positions = requests.get(url, timeout=10).json()
    except:
        st.error("❌ Hedge fetch failed")
        return
    
    if not positions: 
        st.info("📭 No positions")
        return
    
    # Filter BTC Up/Down in timeframe
    now = datetime.now()
    cutoff = now - timedelta(minutes=minutes_back)
    btc_positions = [p for p in positions 
                    if p.get('endDate') and 
                    datetime.fromisoformat(p['endDate'].replace('Z','+00:00')) > cutoff and
                    'btc' in (p.get('title') or '').lower() and 
                    ('up' in (p.get('title') or '').lower() or 'down' in (p.get('title') or '').lower())]
    
    if not btc_positions:
        st.info("📭 No BTC Up/Down in timeframe")
        return
    
    # Group by conditionId
    up_pos = defaultdict(list)
    down_pos = defaultdict(list)
    for p in btc_positions:
        cid = p.get('conditionId')
        if not cid: continue
        outcome = p.get('outcome', '').lower()
        up_pos[cid].append(p) if 'up' in outcome or 'yes' in outcome else down_pos[cid].append(p)
    
    # Net delta table
    hedge_table = []
    total_up = total_down = 0
    for cid in set(list(up_pos) + list(down_pos)):
        up_shares = sum(abs(p.get('size', 0)) for p in up_pos[cid])
        down_shares = sum(abs(p.get('size', 0)) for p in down_pos[cid])
        net = up_shares - down_shares
        
        if abs(net) > 5:  # Meaningful
            up_price = sum(p.get('avgPrice', 0.5) for p in up_pos[cid]) / max(1, len(up_pos[cid]))
            down_price = sum(p.get('avgPrice', 0.5) for p in down_pos[cid]) / max(1, len(down_pos[cid]))
            
            your_up = max(net / ratio * up_price, 0)
            your_down = max((down_shares - up_shares) / ratio * down_price, 0)
            
            total_up += your_up
            total_down += your_down
            
            hedge_table.append({
                'Market': cid[:8]+'...',
                'Up': f"{up_shares:.0f}",
                'Down': f"{down_shares:.0f}",
                'Net': f"{net:+.0f}",
                'Your Up $': f"${your_up:.2f}",
                'Your Down $': f"${your_down:.2f}"
            })
    
    if hedge_table:
        st.markdown(f"### 🔄 Hedge Copy 1:{ratio}")
        pd.DataFrame(hedge_table).style.format({'Your Up $': '${:.2f}', 'Your Down $': '${:.2f}'}).to_html()
        st.dataframe(pd.DataFrame(hedge_table), hide_index=True)
        
        col1, col2 = st.columns(2)
        with col1: st.metric("📈 Net UP", f"${total_up:.2f}")
        with col2: st.metric("📉 Net DOWN", f"${total_down:.2f}")
        st.info(f"**Order**: ${total_up:.0f} UP + ${total_down:.0f} DOWN")
