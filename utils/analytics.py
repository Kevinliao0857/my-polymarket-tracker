"""Core analytics engine — strategy reverse-engineering & copy profitability.

Pure computation, no Streamlit imports. Functions take lists (from DB)
and return dicts/DataFrames.
"""

import math
from collections import defaultdict
from datetime import datetime

import pandas as pd

from .config import TICKERS, FULL_NAMES, EST


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_coin(title: str) -> str | None:
    """Extract the coin name from a market title, or None."""
    t = (title or "").lower()
    for ticker in TICKERS:
        if ticker in t:
            return ticker.upper()
    for name in FULL_NAMES:
        if name in t:
            idx = FULL_NAMES.index(name)
            return TICKERS[idx].upper() if idx < len(TICKERS) else name.upper()
    return None


def _median(values: list) -> float:
    """Compute median of a sorted list."""
    if not values:
        return 0
    n = len(values)
    return values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2


def _match_buy_sell(trades: list) -> tuple:
    """Match BUY → SELL trades FIFO by (title, outcome).

    Returns: (matched_pairs, unmatched_buys)
    - matched_pairs: list of (buy_trade, sell_trade) tuples
    - unmatched_buys: list of buy trades with no matching sell
    """
    buys = defaultdict(list)
    sells = defaultdict(list)
    for t in trades:
        key = (t.get("title"), t.get("outcome"))
        if t.get("side") == "BUY":
            buys[key].append(t)
        elif t.get("side") == "SELL":
            sells[key].append(t)

    # Sort each group by timestamp
    for key in buys:
        buys[key].sort(key=lambda t: t.get("timestamp") or 0)
    for key in sells:
        sells[key].sort(key=lambda t: t.get("timestamp") or 0)

    matched = []
    unmatched = []
    for key in buys:
        sell_list = sells.get(key, [])
        for i, buy in enumerate(buys[key]):
            if i < len(sell_list):
                matched.append((buy, sell_list[i]))
            else:
                unmatched.append(buy)

    return matched, unmatched


# ---------------------------------------------------------------------------
# Win Rate
# ---------------------------------------------------------------------------

def compute_win_rate(settled_trades: list, group_by: str = None) -> dict:
    """Compute win rate overall and optionally grouped by coin.

    Returns: {"overall": float, "by_group": {coin: float}, "sample_size": int}
    """
    if not settled_trades:
        return {"overall": 0.0, "by_group": {}, "sample_size": 0}

    wins = sum(1 for t in settled_trades if (t.get("pnl") or 0) > 0)
    total = len(settled_trades)
    result = {
        "overall": wins / total if total else 0.0,
        "by_group": {},
        "sample_size": total,
    }

    if group_by == "coin":
        groups = defaultdict(lambda: {"wins": 0, "total": 0})
        for t in settled_trades:
            coin = _extract_coin(t.get("title", ""))
            if coin:
                groups[coin]["total"] += 1
                if (t.get("pnl") or 0) > 0:
                    groups[coin]["wins"] += 1
        result["by_group"] = {
            coin: g["wins"] / g["total"] if g["total"] else 0.0
            for coin, g in sorted(groups.items())
        }

    return result


# ---------------------------------------------------------------------------
# Hold Duration
# ---------------------------------------------------------------------------

def compute_hold_duration(trades: list, settled_trades: list = None) -> dict:
    """Estimate hold duration by matching BUY → SELL trades on title+outcome.

    Falls back to BUY → settled_at for positions held to resolution.
    Returns: {"mean_hours": float, "median_hours": float, "sample_size": int}
    """
    matched, unmatched_buys = _match_buy_sell(trades)
    durations = []

    # Matched BUY → SELL pairs
    for buy, sell in matched:
        bt = buy.get("timestamp")
        st = sell.get("timestamp")
        if bt and st and int(st) > int(bt):
            durations.append((int(st) - int(bt)) / 3600)

    # Unmatched buys → try settled_at
    if settled_trades and unmatched_buys:
        settled_map = {}
        for s in settled_trades:
            key = (s.get("title"), s.get("outcome"))
            sa = s.get("settled_at")
            if sa and key not in settled_map:
                settled_map[key] = sa

        for buy in unmatched_buys:
            key = (buy.get("title"), buy.get("outcome"))
            bt = buy.get("timestamp")
            if not bt or key not in settled_map:
                continue
            sa = settled_map[key]
            try:
                settled_ts = int(float(sa))
            except (ValueError, TypeError):
                try:
                    settled_ts = int(datetime.fromisoformat(str(sa)).timestamp())
                except (ValueError, TypeError):
                    continue
            if settled_ts > int(bt):
                durations.append((settled_ts - int(bt)) / 3600)

    if not durations:
        return {"mean_hours": 0, "median_hours": 0, "sample_size": 0}

    durations.sort()
    return {
        "mean_hours": round(sum(durations) / len(durations), 2),
        "median_hours": round(_median(durations), 2),
        "sample_size": len(durations),
    }


# ---------------------------------------------------------------------------
# Time-of-Day Patterns
# ---------------------------------------------------------------------------

def compute_time_of_day_patterns(trades: list) -> pd.DataFrame:
    """Group trades by hour-of-day (EST). Returns DataFrame: hour, trade_count, avg_size."""
    hours = defaultdict(lambda: {"count": 0, "total_size": 0.0})
    for t in trades:
        ts = t.get("timestamp")
        if not ts:
            continue
        dt = datetime.fromtimestamp(int(ts), tz=EST)
        h = dt.hour
        hours[h]["count"] += 1
        hours[h]["total_size"] += float(t.get("size") or 0)

    rows = []
    for h in range(24):
        data = hours[h]
        rows.append({
            "hour": h,
            "trade_count": data["count"],
            "avg_size": round(data["total_size"] / data["count"], 2) if data["count"] else 0,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Sharpe Ratio
# ---------------------------------------------------------------------------

def compute_sharpe_ratio(settled_trades: list, annualization: int = 365) -> float:
    """Compute Sharpe ratio from settled trades grouped by day."""
    daily_pnl = defaultdict(float)
    for t in settled_trades:
        pnl = t.get("pnl")
        sa = t.get("settled_at") or t.get("created_at")
        if pnl is None or not sa:
            continue
        try:
            day = str(sa)[:10]
            if day.isdigit():
                day = datetime.fromtimestamp(int(sa), tz=EST).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        daily_pnl[day] += float(pnl)

    if len(daily_pnl) < 2:
        return 0.0

    values = list(daily_pnl.values())
    n = len(values)
    mean = sum(values) / n
    std = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))
    if std == 0:
        return 0.0
    return round(mean / std * math.sqrt(annualization), 2)


# ---------------------------------------------------------------------------
# Market Overlap (Cross-Trader)
# ---------------------------------------------------------------------------

def compute_market_overlap(traders_trades: dict) -> pd.DataFrame:
    """Compute market overlap matrix between traders."""
    markets = {}
    for addr, trades in traders_trades.items():
        markets[addr] = {t.get("title") for t in trades if t.get("title")}

    addrs = sorted(markets.keys())
    if len(addrs) < 2:
        return pd.DataFrame()

    rows = []
    for a in addrs:
        row = {}
        for b in addrs:
            if not markets[a]:
                row[b] = 0.0
            else:
                overlap = len(markets[a] & markets[b])
                row[b] = round(overlap / len(markets[a]) * 100, 1)
        rows.append(row)
    return pd.DataFrame(rows, index=addrs, columns=addrs)


# ---------------------------------------------------------------------------
# Allocation Weights
# ---------------------------------------------------------------------------

def compute_allocation_weights(
    trader_metrics: dict, method: str = "equal_risk"
) -> dict:
    """Compute portfolio allocation weights across traders."""
    addrs = list(trader_metrics.keys())
    if not addrs:
        return {}
    if len(addrs) == 1:
        return {addrs[0]: 1.0}

    if method == "equal":
        w = 1.0 / len(addrs)
        return {a: round(w, 4) for a in addrs}

    inv_vols = {}
    for addr, m in trader_metrics.items():
        std = m.get("pnl_std", 0)
        inv_vols[addr] = 1.0 / std if std > 0 else 0.0

    total = sum(inv_vols.values())
    if total == 0:
        w = 1.0 / len(addrs)
        return {a: round(w, 4) for a in addrs}

    return {a: round(v / total, 4) for a, v in inv_vols.items()}


# ===========================================================================
# Strategy Analysis Functions
# ===========================================================================


# ---------------------------------------------------------------------------
# Entry Price Analysis
# ---------------------------------------------------------------------------

def analyze_entry_prices(trades: list) -> dict:
    """What prices does the trader buy at? Reveals contrarian vs momentum vs arb.

    Returns: mean/median entry, price bucket distribution, by-coin breakdown.
    """
    buys = [t for t in trades if t.get("side") == "BUY" and t.get("price")]
    if not buys:
        return {
            "mean_entry": 0, "median_entry": 0,
            "price_buckets": {}, "by_coin": {}, "sample_size": 0,
        }

    prices = [float(t["price"]) for t in buys]
    prices.sort()

    buckets = {
        "deep_underdog (<0.20)": 0,
        "underdog (0.20-0.40)": 0,
        "coinflip (0.40-0.60)": 0,
        "favorite (0.60-0.80)": 0,
        "heavy_favorite (>0.80)": 0,
    }
    for p in prices:
        if p < 0.20:
            buckets["deep_underdog (<0.20)"] += 1
        elif p < 0.40:
            buckets["underdog (0.20-0.40)"] += 1
        elif p < 0.60:
            buckets["coinflip (0.40-0.60)"] += 1
        elif p < 0.80:
            buckets["favorite (0.60-0.80)"] += 1
        else:
            buckets["heavy_favorite (>0.80)"] += 1

    by_coin = defaultdict(list)
    for t in buys:
        coin = _extract_coin(t.get("title", ""))
        if coin:
            by_coin[coin].append(float(t["price"]))

    return {
        "mean_entry": round(sum(prices) / len(prices), 4),
        "median_entry": round(_median(prices), 4),
        "price_buckets": buckets,
        "by_coin": {
            coin: round(sum(ps) / len(ps), 4) for coin, ps in sorted(by_coin.items())
        },
        "sample_size": len(buys),
    }


# ---------------------------------------------------------------------------
# Exit Behavior Analysis
# ---------------------------------------------------------------------------

def analyze_exit_behavior(trades: list, settled_trades: list = None) -> dict:
    """When/why does the trader exit? Take-profit vs stop-loss patterns.

    Returns: early exit %, exit triggers, avg hold before exit.
    """
    matched, unmatched_buys = _match_buy_sell(trades)

    # Check which unmatched buys appear in settled trades
    settled_titles = set()
    if settled_trades:
        for s in settled_trades:
            settled_titles.add((s.get("title"), s.get("outcome")))

    held_to_settlement = sum(
        1 for b in unmatched_buys
        if (b.get("title"), b.get("outcome")) in settled_titles
    )

    total_positions = len(matched) + len(unmatched_buys)
    early_exits = len(matched)

    if total_positions == 0:
        return {
            "early_exit_pct": 0, "held_to_settlement_pct": 0,
            "avg_exit_price": 0, "avg_exit_pnl_pct": 0,
            "exit_triggers": {"take_profit": 0, "stop_loss": 0},
            "avg_hold_before_exit_hours": 0, "sample_size": 0,
        }

    # Analyze the matched (early exit) pairs
    take_profit = 0
    stop_loss = 0
    exit_prices = []
    exit_pnl_pcts = []
    hold_hours = []

    for buy, sell in matched:
        entry_price = float(buy.get("price") or 0)
        exit_price = float(sell.get("price") or 0)
        exit_prices.append(exit_price)

        if entry_price > 0:
            pnl_pct = (exit_price - entry_price) / entry_price * 100
            exit_pnl_pcts.append(pnl_pct)
            if exit_price > entry_price:
                take_profit += 1
            else:
                stop_loss += 1

        bt = buy.get("timestamp")
        st_val = sell.get("timestamp")
        if bt and st_val and int(st_val) > int(bt):
            hold_hours.append((int(st_val) - int(bt)) / 3600)

    return {
        "early_exit_pct": round(early_exits / total_positions * 100, 1) if total_positions else 0,
        "held_to_settlement_pct": round(held_to_settlement / total_positions * 100, 1) if total_positions else 0,
        "avg_exit_price": round(sum(exit_prices) / len(exit_prices), 4) if exit_prices else 0,
        "avg_exit_pnl_pct": round(sum(exit_pnl_pcts) / len(exit_pnl_pcts), 2) if exit_pnl_pcts else 0,
        "exit_triggers": {"take_profit": take_profit, "stop_loss": stop_loss},
        "avg_hold_before_exit_hours": round(sum(hold_hours) / len(hold_hours), 2) if hold_hours else 0,
        "sample_size": total_positions,
    }


# ---------------------------------------------------------------------------
# Conviction Analysis
# ---------------------------------------------------------------------------

def analyze_conviction(trades: list, settled_trades: list = None) -> dict:
    """Do bigger bets win more? Does the trader scale into positions?

    Returns: big vs small bet win rates, scaling behavior, size vs outcome data.
    """
    buys = [t for t in trades if t.get("side") == "BUY" and t.get("size")]
    if not buys:
        return {
            "size_vs_outcome": [], "big_bet_win_rate": 0, "small_bet_win_rate": 0,
            "scales_in": False, "avg_buys_per_market": 0, "sample_size": 0,
        }

    # Build settled PnL lookup
    settled_pnl = {}
    if settled_trades:
        for s in settled_trades:
            key = (s.get("title"), s.get("outcome"))
            if s.get("pnl") is not None:
                settled_pnl[key] = float(s["pnl"])

    # Match buys to outcomes
    size_outcome = []
    for t in buys:
        key = (t.get("title"), t.get("outcome"))
        pnl = settled_pnl.get(key)
        if pnl is not None:
            size_outcome.append({
                "size": float(t["size"]),
                "pnl": pnl,
                "won": pnl > 0,
                "title": (t.get("title") or "")[:50],
            })

    # Split at median size
    if size_outcome:
        sizes = sorted(s["size"] for s in size_outcome)
        median_size = _median(sizes)
        big = [s for s in size_outcome if s["size"] >= median_size]
        small = [s for s in size_outcome if s["size"] < median_size]
        big_wr = sum(1 for s in big if s["won"]) / len(big) if big else 0
        small_wr = sum(1 for s in small if s["won"]) / len(small) if small else 0
    else:
        big_wr = 0
        small_wr = 0

    # Scaling behavior: multiple BUYs on same (title, outcome)
    buy_counts = defaultdict(int)
    for t in buys:
        key = (t.get("title"), t.get("outcome"))
        buy_counts[key] += 1

    total_markets = len(buy_counts)
    avg_buys = sum(buy_counts.values()) / total_markets if total_markets else 0
    scales_in = any(c > 1 for c in buy_counts.values())

    return {
        "size_vs_outcome": size_outcome,
        "big_bet_win_rate": round(big_wr, 3),
        "small_bet_win_rate": round(small_wr, 3),
        "scales_in": scales_in,
        "avg_buys_per_market": round(avg_buys, 2),
        "sample_size": len(size_outcome),
    }


# ---------------------------------------------------------------------------
# Copy Delay Impact
# ---------------------------------------------------------------------------

def analyze_copy_delay_impact(trades: list, position_history: list) -> dict:
    """How does price move after the trader enters? Can you still profit entering late?

    Uses position snapshots to build price curves after each BUY entry.
    Returns: delay impact at various time windows, per-trade price curves.
    """
    buys = [t for t in trades if t.get("side") == "BUY" and t.get("price") and t.get("timestamp")]
    if not buys:
        return {
            "delay_impact": [], "still_profitable_at_5m": False,
            "edge_decay_per_minute": 0, "price_curves": [], "sample_size": 0,
        }

    # Index snapshots by (title, outcome) sorted by time
    snap_index = defaultdict(list)
    for s in position_history:
        key = (s.get("title"), s.get("outcome"))
        snap_index[key].append(s)
    for key in snap_index:
        snap_index[key].sort(key=lambda s: s.get("snapshot_at") or "")

    delay_windows = [1, 5, 15, 30, 60]  # minutes
    window_changes = defaultdict(list)  # delay_min -> list of price_change_pct
    price_curves = []

    for buy in buys:
        entry_price = float(buy["price"])
        entry_ts = int(buy["timestamp"])
        key = (buy.get("title"), buy.get("outcome"))
        snaps = snap_index.get(key, [])

        if entry_price <= 0 or not snaps:
            continue

        # Find snapshots after entry
        # snapshot_at is ISO datetime string — parse to timestamp
        curve_points = []
        for s in snaps:
            sa = s.get("snapshot_at")
            cp = s.get("cur_price")
            if not sa or cp is None:
                continue
            try:
                snap_ts = int(datetime.fromisoformat(sa).timestamp())
            except (ValueError, TypeError):
                continue
            minutes_after = (snap_ts - entry_ts) / 60
            if minutes_after < 0:
                continue
            curve_points.append({
                "minutes_after": round(minutes_after, 1),
                "price": float(cp),
            })

        if len(curve_points) < 3:
            continue  # Not enough data for this trade

        # Record price at each delay window
        for delay_min in delay_windows:
            # Find closest snapshot to the target delay
            closest = None
            closest_diff = float("inf")
            for pt in curve_points:
                diff = abs(pt["minutes_after"] - delay_min)
                if diff < closest_diff:
                    closest_diff = diff
                    closest = pt
            # Only use if within 50% of the window (e.g., for 5min, accept 2.5-7.5min)
            if closest and closest_diff <= delay_min * 0.5:
                change_pct = (closest["price"] - entry_price) / entry_price * 100
                window_changes[delay_min].append(change_pct)

        price_curves.append({
            "title": (buy.get("title") or "")[:50],
            "entry_price": entry_price,
            "snapshots": curve_points[:20],  # Cap for display
        })

    # Build delay impact summary
    delay_impact = []
    for delay_min in delay_windows:
        changes = window_changes.get(delay_min, [])
        if changes:
            avg_change = sum(changes) / len(changes)
            delay_impact.append({
                "delay_minutes": delay_min,
                "avg_price_change_pct": round(avg_change, 3),
                "sample_size": len(changes),
            })

    # Edge decay: average price change per minute (from 1m to 60m)
    edge_decay = 0
    if len(delay_impact) >= 2:
        first = delay_impact[0]
        last = delay_impact[-1]
        time_span = last["delay_minutes"] - first["delay_minutes"]
        if time_span > 0:
            edge_decay = round(
                (last["avg_price_change_pct"] - first["avg_price_change_pct"]) / time_span, 4
            )

    # Still profitable at 5min?
    five_min = next((d for d in delay_impact if d["delay_minutes"] == 5), None)
    still_profitable = five_min is not None and five_min["avg_price_change_pct"] < 50

    return {
        "delay_impact": delay_impact,
        "still_profitable_at_5m": still_profitable,
        "edge_decay_per_minute": edge_decay,
        "price_curves": price_curves[:10],  # Cap for display
        "sample_size": len(price_curves),
    }


# ---------------------------------------------------------------------------
# Risk / Reward Analysis
# ---------------------------------------------------------------------------

def analyze_risk_reward(settled_trades: list) -> dict:
    """How much risk did the trader take for how much reward?

    Returns: return on capital, risk/reward ratio, per-coin breakdown.
    """
    if not settled_trades:
        return {
            "avg_return_on_capital": 0, "best_return_pct": 0, "worst_return_pct": 0,
            "risk_reward_ratio": 0, "by_coin": {}, "trades_detail": [], "sample_size": 0,
        }

    returns = []
    win_pnls = []
    loss_pnls = []
    by_coin_data = defaultdict(lambda: {"returns": [], "win_pnls": [], "loss_pnls": []})
    detail = []

    for t in settled_trades:
        pnl = t.get("pnl")
        size = t.get("size")
        price = t.get("price")
        if pnl is None or not size or not price:
            continue

        cost = float(size) * float(price)
        if cost <= 0:
            continue

        pnl_f = float(pnl)
        return_pct = pnl_f / cost * 100
        returns.append(return_pct)

        if pnl_f > 0:
            win_pnls.append(pnl_f)
        elif pnl_f < 0:
            loss_pnls.append(pnl_f)

        coin = _extract_coin(t.get("title", ""))
        if coin:
            by_coin_data[coin]["returns"].append(return_pct)
            if pnl_f > 0:
                by_coin_data[coin]["win_pnls"].append(pnl_f)
            elif pnl_f < 0:
                by_coin_data[coin]["loss_pnls"].append(pnl_f)

        detail.append({
            "title": (t.get("title") or "")[:50],
            "cost": round(cost, 2),
            "pnl": round(pnl_f, 2),
            "return_pct": round(return_pct, 1),
        })

    avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0
    avg_loss = abs(sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0
    rr_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0

    by_coin = {}
    for coin, data in sorted(by_coin_data.items()):
        r = data["returns"]
        w = data["win_pnls"]
        l = data["loss_pnls"]
        avg_w = sum(w) / len(w) if w else 0
        avg_l = abs(sum(l) / len(l)) if l else 0
        by_coin[coin] = {
            "return_pct": round(sum(r) / len(r), 1) if r else 0,
            "risk_reward": round(avg_w / avg_l, 2) if avg_l > 0 else 0,
        }

    return {
        "avg_return_on_capital": round(sum(returns) / len(returns), 2) if returns else 0,
        "best_return_pct": round(max(returns), 1) if returns else 0,
        "worst_return_pct": round(min(returns), 1) if returns else 0,
        "risk_reward_ratio": rr_ratio,
        "by_coin": by_coin,
        "trades_detail": sorted(detail, key=lambda d: d["return_pct"], reverse=True),
        "sample_size": len(returns),
    }
