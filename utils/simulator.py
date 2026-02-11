import streamlit as st
import pandas as pd
import re
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from utils.config import TRADER

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

def simulate_combined(df, your_bankroll, wallet_address, ratio=200, hedge_minutes=15):
    """🚀 BLIND COPY + 🔄 HEDGE ANALYZER in one view"""
    
    # ===== BLIND COPY (your original, fixed) =====
    st.markdown("### 🚀 Blind Copy Trades")
    active_trades = [t for t in df.to_dict('records') 
                    if any(w in str(t.get('Market', '')).lower() 
                          for w in ['6pm','7pm','8pm','9pm','10pm','pm','am','et','h '])]
    
    if active_trades:
        total_trader = total_your = valid = 0
        table_rows = ["| Market | Trader $ | Price | Ratio'd | Shares | Your $ |"]
        table_rows.append("|--------|----------|-------|---------|--------|---------|")
        
        for trade in active_trades:
            trader_size = parse_usd(trade.get('Amount'))
            if trader_size <= 0: continue
            
            price = max(min(parse_usd(trade.get('Price')) or 0.50, 0.99), 0.01)
            ratiod = trader_size / ratio
            min_order = 5 * price
            
            title = str(trade.get('Market', 'N/A'))[:35]
            if ratiod >= min_order:
                your_usd = max(ratiod, min_order)
                shares = max(your_usd / price, 5)
                total_trader += trader_size
                total_your += your_usd
                valid += 1
                table_rows.append(f"| `{title}` | **${trader_size:.2f}** | **${price:.3f}** | **${ratiod:.2f}** | {shares:.0f} | **${your_usd:.2f}** |")
            else:
                table_rows.append(f"| `{title}` | **${trader_size:.2f}** | **${price:.3f}** | **${ratiod:.2f}** | **0** | **SKIPPED** |")
        
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("Trader", f"${total_trader:.2f}")
        with col2: st.metric("Your Total", f"${total_your:.2f}")
        with col3: st.metric("Valid", valid)
        st.markdown("\n".join(table_rows))
    else:
        st.info("📭 No time-based trades")
    
    st.markdown("---")
    
    # ===== HEDGE ANALYZER =====
    st.markdown("### 🔄 Net Hedge Positions")
    url = f"https://data-api.polymarket.com/positions?user={wallet_address}&limit=500"
    try:
        positions = requests.get(url, timeout=10).json()
        cutoff = datetime.now() - timedelta(minutes=hedge_minutes)
        btc_pos = [p for p in positions if (p.get('endDate') and 
                                          datetime.fromisoformat(p['endDate'].replace('Z','+00:00')) > cutoff and
                                          'btc' in str(p.get('title','')).lower() and 
                                          ('up' in str(p.get('title','')).lower() or 'down' in str(p.get('title','')).lower()))]
        
        if btc_pos:
            up = defaultdict(float)
            down = defaultdict(float)
            for p in btc_pos:
                cid = p.get('conditionId')
                if cid:
                    size = abs(p.get('size', 0))
                    outcome = p.get('outcome', '').lower()
                    if 'up' in outcome or 'yes' in outcome:
                        up[cid] += size
                    elif 'down' in outcome or 'no' in outcome:
                        down[cid] += size
            
            hedge_data = []
            net_up = net_down = 0
            for cid in set(list(up) + list(down)):
                u = up[cid]
                d = down[cid]
                net = u - d
                if abs(net) > 5:
                    your_up = max(net / ratio * 0.52, 0)   # avg price ~0.52
                    your_down = max((d - u) / ratio * 0.48, 0)
                    net_up += your_up
                    net_down += your_down
                    hedge_data.append({
                        'ID': cid[:8],
                        'Up': f"{u:.0f}",
                        'Down': f"{d:.0f}",
                        'Net': f"{net:+.0f}",
                        'Your Up $': f"${your_up:.2f}",
                        'Your Down $': f"${your_down:.2f}"
                    })
            
            if hedge_data:
                st.dataframe(pd.DataFrame(hedge_data))
                col1, col2 = st.columns(2)
                with col1: st.metric("📈 Net UP", f"${net_up:.2f}")
                with col2: st.metric("📉 Net DOWN", f"${net_down:.2f}")
                st.info(f"**Hedge**: ${net_up:.0f} UP + ${net_down:.0f} DOWN (1:{ratio})")
            else:
                st.info("⚖️ No meaningful net hedges")
        else:
            st.info("📭 No BTC Up/Down positions")
    except:
        st.error("❌ Hedge fetch failed")
    
    # Bankroll check (combined)
    combined_total = total_your + net_up + net_down
    if combined_total > your_bankroll * 1.1:
        st.error(f"⚠️ Combined: ${combined_total:.2f} > bankroll!")


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
