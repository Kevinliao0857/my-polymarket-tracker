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

def simulate_combined(df, your_bankroll, wallet_address, ratio=200, hedge_minutes=15, hedge_ratio=200):
    """🚀 BLIND COPY + 🔄 HEDGE - TRUE SCROLLING + SHOWS FULL DATA"""
    
    total_your = 0.0
    net_up = 0.0
    net_down = 0.0
    
    st.markdown("### 🚀 Blind Copy (Time-based Bets)")
    
    active_trades = [t for t in df.to_dict('records') 
                     if any(w in str(t.get('Market', '')).lower() 
                            for w in ['6pm','7pm','8pm','9pm','10pm','pm','am','et','h '])]
    
    if active_trades:
        valid = 0
        blind_data = []
        
        for trade in active_trades:
            trader_size = parse_usd(trade.get('Amount'))
            if trader_size <= 0: continue
            
            price = max(min(parse_usd(trade.get('Price')) or 0.50, 0.99), 0.01)
            ratiod = trader_size / ratio
            min_order = 5 * price
            
            title = str(trade.get('Market', 'N/A'))[:35]
            
            if ratiod >= min_order:
                your_usd = max(ratiod, min_order)
                shares = int(your_usd / price)
                total_your += your_usd
                valid += 1
                blind_data.append({
                    'Market': title,
                    'Trader $': f"${trader_size:.2f}",
                    'Price': f"${price:.3f}",
                    "Ratio'd": f"${ratiod:.2f}",
                    'Shares': shares,
                    'Your $': f"${your_usd:.2f}"
                })
            else:
                blind_data.append({
                    'Market': title,
                    'Trader $': f"${trader_size:.2f}",
                    'Price': f"${price:.3f}",
                    "Ratio'd": f"${ratiod:.2f}",
                    'Shares': 0,
                    'Your $': 'SKIPPED'
                })
        
        col1, col2, col3 = st.columns(3)
        trader_total = sum(parse_usd(t.get('Amount', 0)) for t in active_trades)
        with col1: st.metric("Trader Total", f"${trader_total:.0f}")
        with col2: st.metric("Your Copy", f"${total_your:.2f}")
        with col3: st.metric("Valid", valid)
        
        # ✅ FIXED SCROLL: height=300 shows ~4 rows → forces scrollbar if >4
        blind_df = pd.DataFrame(blind_data)
        st.dataframe(
            blind_df,  # FULL data - no .head()
            height=300,  # Fixed height → always scrollable if data exists
            hide_index=True, 
            use_container_width=True
        )
        
        st.caption(f"📜 {len(blind_df)} total trades - scroll ↕️ to view")
    else:
        st.info("📭 No qualifying trades")
    
    st.markdown("---")
    
    # Hedge analyzer - SAME SCROLL FIX
    st.markdown("### 🔄 Net Hedge Exposure")
    url = f"https://data-api.polymarket.com/positions?user={wallet_address}&limit=500"
    try:
        positions = requests.get(url, timeout=10).json()
        cutoff = datetime.now() - timedelta(minutes=hedge_minutes)
        btc_pos = [p for p in positions 
                   if (p.get('endDate') and 
                       datetime.fromisoformat(p['endDate'].replace('Z','+00:00')) > cutoff and
                       'btc' in str(p.get('title','')).lower() and 
                       any(x in str(p.get('title','')).lower() for x in ['up','down']))]
        
        if btc_pos:
            up = defaultdict(float)
            down = defaultdict(float)
            for p in btc_pos:
                cid = p.get('conditionId')
                if cid:
                    size = abs(p.get('size', 0))
                    outcome = str(p.get('outcome','')).lower()
                    if any(x in outcome for x in ['up','yes']):
                        up[cid] += size
                    elif any(x in outcome for x in ['down','no']):
                        down[cid] += size
            
            hedge_data = []
            for cid in set(list(up.keys()) + list(down.keys())):
                u, d = up[cid], down[cid]
                net = u - d
                if abs(net) > 5:
                    your_up = max(net / hedge_ratio * 0.52, 0)
                    your_down = max((d - u) / hedge_ratio * 0.48, 0)
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
                # ✅ FULL data + fixed scroll height
                hedge_df = pd.DataFrame(hedge_data)
                st.dataframe(
                    hedge_df,  # FULL data
                    height=300,  # Fixed → scroll if needed
                    hide_index=True,
                    use_container_width=True
                )
                
                st.caption(f"📜 {len(hedge_df)} total hedges - scroll ↕️ to view")
                
                col1, col2 = st.columns(2)
                with col1: st.metric("📈 Net UP", f"${net_up:.2f}")
                with col2: st.metric("📉 Net DOWN", f"${net_down:.2f}")
                st.info(f"**Hedge**: ${net_up:.0f} UP + ${net_down:.0f} DOWN (1:{hedge_ratio})")
            else:
                st.info("⚖️ Balanced / no net exposure")
        else:
            st.info("📭 No recent BTC Up/Down positions")
    except:
        st.error("❌ Hedge analysis failed")
    
    combined = total_your + net_up + net_down
    if combined > your_bankroll:
        st.warning(f"⚠️ Combined: ${combined:.2f} > bankroll ${your_bankroll:.0f}")


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
        st.dataframe(pd.DataFrame(hedge_table), hide_index=True)
        
        col1, col2 = st.columns(2)
        with col1: st.metric("📈 Net UP", f"${total_up:.2f}")
        with col2: st.metric("📉 Net DOWN", f"${total_down:.2f}")
        st.info(f"**Order**: ${total_up:.0f} UP + ${total_down:.0f} DOWN")
