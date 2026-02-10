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
        if trader_size > 0:
            price_raw = trade.get('Price')
            price = parse_usd(price_raw) if price_raw else 0.50
            price = max(min(price, 0.99), 0.01)

            # PRE‑COMPUTE LOOP
            your_usdc = trader_size / ratio
            your_shares = max(your_usdc / price, 5) if ratio > 0 else 0

            if ratio > 0 and your_usdc > 0:  # 👈 Check BEFORE min_order
                min_order = 5 * price
                your_usdc = max(your_usdc, min_order)

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
                        f"| `{title}` | **${trader_size:.2f}** | **${price:.3f}** | **${ratiod_usdc:.4f}** | **<min** | **SKIPPED** |"
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
