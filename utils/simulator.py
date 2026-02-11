import streamlit as st
import pandas as pd
import re

import requests
from datetime import datetime, timedelta


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
        if any(word in title for word in ['6pm', '7pm', '8pm', '9pm', '10pm', 'pm', 'am', 'et', 'h ']):
            active_trades.append(trade)

    if not active_trades:
        st.warning("⚠️ No time-based bets found - expand MINUTES_BACK slider")
        return

    # 👇 COMPUTE TOTALS FIRST (for title)
    total_trader = 0
    total_your = 0
    valid_trades = 0
    
    for trade in active_trades:
        trader_size = parse_usd(trade.get('Amount'))
        if trader_size <= 0:
            continue
        
        price_raw = trade.get('Price')
        price = parse_usd(price_raw) if price_raw else 0.50
        price = max(min(price, 0.99), 0.01)
    
        ratiod_usdc = trader_size / ratio
        min_order = 5 * price
    
        # 👈 SAME SKIP LOGIC AS TABLE
        if ratio > 0 and ratiod_usdc >= min_order:
            your_usdc = max(ratiod_usdc, min_order)
            your_shares = max(your_usdc / price, 5)
    
            total_trader += trader_size
            total_your += your_usdc
            valid_trades += 1
    
    # 👇 NOW EXPANDER WITH CORRECT COUNT
    with st.expander(f"🚀 Copy Trading 1:{ratio} ({valid_trades}/{len(active_trades)} valid)", expanded=True):
        st.markdown(f"### 🚀 Copy Trading 1:{ratio}")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("👤 Trader Total", f"${total_trader:.2f}")
        with col2:
            st.metric("🧑 Your Total", f"${total_your:.2f}")
        with col3:
            st.metric("✅ Valid Bets", valid_trades)
        with col4:
            st.metric("💰 Bankroll", f"${your_bankroll:.0f}")

        # Bank roll check
        if total_your > your_bankroll * 1.1:  # 10% buffer
            st.error(f"⚠️ **Exceeds bankroll by ${total_your - your_bankroll:.0f}!** Reduce ratio or bankroll.")
        elif total_your > your_bankroll:
            st.warning(f"⚠️ **Slightly over bankroll by ${total_your - your_bankroll:.0f}.**")

        # 👇 REBUILD TABLE (detailed version) – identical to pre‑compute logic
        table_rows = ["| Market | Trader Amount | Price | Ratio'd | Your Shares | **Your USDC** |"]
        table_rows.append("|--------|---------------|-------|---------|-------------|---------------|")
        
        last_price = 0.50  # For warning
        min_shares = 5
        for trade in active_trades:
            trader_size = parse_usd(trade.get('Amount'))
            price_raw = trade.get('Price')
            price = parse_usd(price_raw) if price_raw else 0.50
            last_price = price
            price = max(min(price, 0.99), 0.01)
        
            if trader_size > 0 and price > 0:
                title = str(trade.get('Market') or 'N/A')[:35]  # Shorten for display
        
                ratiod_usdc = trader_size / ratio
                min_order = min_shares * price
        
                # SKIP tiny ratio'd amounts (i.e., $0.00 after rounding)
                if ratio <= 0 or ratiod_usdc < min_order:
                    table_rows.append(
                        f"| `{title}` | **${trader_size:.2f}** | **${price:.3f}** | **${ratiod_usdc:.2f}** | **0** | **SKIPPED** |"
                    )

                else:
                    your_usdc = max(ratiod_usdc, min_order)
                    your_shares = max(your_usdc / price, min_shares)
        
                    table_rows.append(
                        f"| `{title}` | **${trader_size:.2f}** | **${price:.3f}** | **${ratiod_usdc:.2f}** | {your_shares:.0f} | **${your_usdc:.2f}** |"
                    )
            else:
                table_rows.append(
                    f"| `{trade.get('Market', 'N/A')[:35]}` | **$0** | **{price_raw}** | **$0** | **INVALID** | **SKIPPED** |"
                )

        st.markdown("\n".join(table_rows))

        st.info(f"⚠️ **Polymarket min: 5 shares (~${last_price:.2f} USDC)** | Total valid: {valid_trades}/{len(active_trades)}")
        st.success(f"**Trader: ${total_trader:.0f}** → **You: ${total_your:.2f}** (1:{ratio})")


def simulate_historical_pnl(closed_pnl, ratio=200):
    if closed_pnl['crypto_count'] == 0:
        st.info("📭 No closed trades")
        return

    your_pnl = closed_pnl['total'] / ratio
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Their Closed", f"${closed_pnl['total']:.0f}")
    with col2:
        color = "🟢" if your_pnl >= 0 else "🔴"
        st.metric("🧑 Your 1:{ratio}", f"{color}${abs(your_pnl):,.0f}")

    st.success(f"**Backtest: ${your_pnl:.0f}** (copied their {closed_pnl['crypto_count']} trades)")

def simulate_hedge(wallet_address: str = "0x8dxd...", minutes_back: int = 15, ratio: int = 200):
    """ANALYZE Polymarket hedge positions for wallet, scale 1:ratio"""
    
    # 1. Fetch positions
    url = f"https://data-api.polymarket.com/positions?user={wallet_address}&limit=500"
    try:
        response = requests.get(url, timeout=10)
        positions = response.json()
    except:
        st.error("❌ Failed to fetch positions")
        return
    
    if not positions:
        st.info("📭 No positions found")
        return
    
    # 2. Filter: 15min + BTC Up/Down markets
    now = datetime.now()
    cutoff = now - timedelta(minutes=minutes_back)
    
    btc_positions = []
    for pos in positions:
        # Check endDate within window
        end_str = pos.get('endDate')
        if end_str:
            try:
                end_date = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                if end_date > cutoff:
                    # BTC Up/Down title check
                    title = str(pos.get('title', '')).lower()
                    if 'btc' in title and ('up' in title or 'down' in title):
                        btc_positions.append(pos)
            except:
                continue
    
    if not btc_positions:
        st.info("📭 No BTC Up/Down markets in timeframe")
        return
    
    # 3. GROUP by conditionId
    from collections import defaultdict
    
    up_positions = defaultdict(list)  # conditionId → [pos]
    down_positions = defaultdict(list)
    
    for pos in btc_positions:
        condition_id = pos.get('conditionId')
        if not condition_id:
            continue
            
        outcome = pos.get('outcome', '').lower()
        size = abs(pos.get('size', 0))  # absolute position size
        avg_price = pos.get('avgPrice', 0.50)
        
        if 'up' in outcome or 'yes' in outcome:
            up_positions[condition_id].append({'size': size, 'price': avg_price})
        elif 'down' in outcome or 'no' in outcome:
            down_positions[condition_id].append({'size': size, 'price': avg_price})
    
    # 4. Net Delta per market
    hedge_table = []
    total_up_usdc = 0
    total_down_usdc = 0
    
    for condition_id in set(list(up_positions.keys()) + list(down_positions.keys())):
        up_total = sum(p['size'] for p in up_positions[condition_id])
        down_total = sum(p['size'] for p in down_positions[condition_id])
        
        net_delta = up_total - down_total  # Positive = net long Up
        
        if abs(net_delta) > 5:  # Only meaningful nets
            avg_up_price = sum(p['price'] for p in up_positions[condition_id]) / len(up_positions[condition_id]) if up_positions[condition_id] else 0.50
            avg_down_price = sum(p['price'] for p in down_positions[condition_id]) / len(down_positions[condition_id]) if down_positions[condition_id] else 0.50
            
            # 5. Scale 1:ratio
            your_net_up = net_delta / ratio
            your_up_usdc = max(your_net_up * avg_up_price, 0)
            your_down_usdc = max((down_total - up_total) / ratio * avg_down_price, 0)
            
            total_up_usdc += your_up_usdc
            total_down_usdc += your_down_usdc
            
            hedge_table.append({
                'Market': condition_id[:8] + '...',
                'Up Shares': f"{up_total:.0f}",
                'Down Shares': f"{down_total:.0f}",
                'Net Delta': f"{net_delta:+.0f}",
                'Your Up $': f"${your_up_usdc:.2f}",
                'Your Down $': f"${your_down_usdc:.2f}"
            })
    
    # 6. Output Table
    if hedge_table:
        st.markdown("### 🔄 Hedge Copy Trading 1:" + str(ratio))
        
        df_hedge = pd.DataFrame(hedge_table)
        st.dataframe(df_hedge, hide_index=True)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("📈 Your Net UP", f"${total_up_usdc:.2f}")
        with col2:
            st.metric("📉 Your Net DOWN", f"${total_down_usdc:.2f}")
        
        # Edge: combined avg price < $1?
        avg_combined = (sum(p.get('avgPrice', 0.50) for p in btc_positions) / len(btc_positions))
        if avg_combined < 1.00:
            st.success(f"🟢 **Edge detected**: Avg price ${avg_combined:.3f} (ROI potential)")
        
        st.info(f"**Net Order**: Buy ${total_up_usdc:.0f} UP + ${total_down_usdc:.0f} DOWN (1:{ratio})")
    else:
        st.info("⚖️ No net hedge positions found")