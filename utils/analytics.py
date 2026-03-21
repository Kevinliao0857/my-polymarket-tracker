"""Core analytics engine — pure computation, no Streamlit imports."""

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
            # Map full name back to ticker
            idx = FULL_NAMES.index(name)
            return TICKERS[idx].upper() if idx < len(TICKERS) else name.upper()
    return None


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
# Position Size Stats
# ---------------------------------------------------------------------------

def compute_position_size_stats(trades: list) -> dict:
    """Compute position size statistics from trade records."""
    sizes = [t.get("size") or 0 for t in trades if t.get("size")]
    if not sizes:
        return {"mean": 0, "median": 0, "std": 0, "min": 0, "max": 0, "count": 0}

    sizes.sort()
    n = len(sizes)
    mean = sum(sizes) / n
    median = sizes[n // 2] if n % 2 else (sizes[n // 2 - 1] + sizes[n // 2]) / 2
    variance = sum((s - mean) ** 2 for s in sizes) / n if n > 1 else 0
    return {
        "mean": round(mean, 2),
        "median": round(median, 2),
        "std": round(math.sqrt(variance), 2),
        "min": round(min(sizes), 2),
        "max": round(max(sizes), 2),
        "count": n,
    }


# ---------------------------------------------------------------------------
# PnL Distribution
# ---------------------------------------------------------------------------

def compute_pnl_distribution(settled_trades: list) -> pd.DataFrame:
    """Return a DataFrame of PnL values suitable for histogram plotting."""
    rows = []
    for t in settled_trades:
        pnl = t.get("pnl")
        if pnl is not None:
            rows.append({
                "pnl": float(pnl),
                "coin": _extract_coin(t.get("title", "")) or "Other",
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["pnl", "coin"])


# ---------------------------------------------------------------------------
# Hold Duration
# ---------------------------------------------------------------------------

def compute_hold_duration(trades: list, settled_trades: list = None) -> dict:
    """Estimate hold duration by matching BUY → SELL trades on title+outcome.

    Falls back to BUY → settled_at for positions held to resolution.
    Returns: {"mean_hours": float, "median_hours": float, "sample_size": int}
    """
    # Group BUY trades by (title, outcome) — earliest first
    buys = defaultdict(list)
    sells = defaultdict(list)
    for t in trades:
        key = (t.get("title"), t.get("outcome"))
        ts = t.get("timestamp")
        if not ts:
            continue
        if t.get("side") == "BUY":
            buys[key].append(int(ts))
        elif t.get("side") == "SELL":
            sells[key].append(int(ts))

    durations = []

    # Match BUY → SELL (FIFO)
    for key in buys:
        buy_times = sorted(buys[key])
        sell_times = sorted(sells.get(key, []))
        for i, bt in enumerate(buy_times):
            if i < len(sell_times) and sell_times[i] > bt:
                durations.append((sell_times[i] - bt) / 3600)

    # For unmatched buys, try settled_at
    if settled_trades:
        settled_map = {}
        for s in settled_trades:
            key = (s.get("title"), s.get("outcome"))
            sa = s.get("settled_at")
            if sa and key not in settled_map:
                settled_map[key] = sa

        for key in buys:
            buy_times = sorted(buys[key])
            sell_count = len(sells.get(key, []))
            unmatched = buy_times[sell_count:]
            if key in settled_map and unmatched:
                # settled_at may be ISO string or epoch
                sa = settled_map[key]
                try:
                    settled_ts = int(float(sa))
                except (ValueError, TypeError):
                    try:
                        settled_ts = int(datetime.fromisoformat(str(sa)).timestamp())
                    except (ValueError, TypeError):
                        continue
                for bt in unmatched:
                    if settled_ts > bt:
                        durations.append((settled_ts - bt) / 3600)

    if not durations:
        return {"mean_hours": 0, "median_hours": 0, "sample_size": 0}

    durations.sort()
    n = len(durations)
    mean = sum(durations) / n
    median = durations[n // 2] if n % 2 else (durations[n // 2 - 1] + durations[n // 2]) / 2
    return {
        "mean_hours": round(mean, 2),
        "median_hours": round(median, 2),
        "sample_size": n,
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
        # Extract date string (works for both ISO and epoch)
        try:
            day = str(sa)[:10]  # ISO date prefix
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
    """Compute market overlap matrix between traders.

    Input: {trader_address: [trades]}
    Returns: DataFrame with overlap % between each pair.
    """
    # Build set of market titles per trader
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
    """Compute portfolio allocation weights across traders.

    Input: {address: {"pnl_std": float, ...}}
    Methods: "equal_risk" (inverse-volatility), "equal" (uniform)
    Returns: {address: weight} summing to 1.0
    """
    addrs = list(trader_metrics.keys())
    if not addrs:
        return {}
    if len(addrs) == 1:
        return {addrs[0]: 1.0}

    if method == "equal":
        w = 1.0 / len(addrs)
        return {a: round(w, 4) for a in addrs}

    # equal_risk: inverse volatility
    inv_vols = {}
    for addr, m in trader_metrics.items():
        std = m.get("pnl_std", 0)
        inv_vols[addr] = 1.0 / std if std > 0 else 0.0

    total = sum(inv_vols.values())
    if total == 0:
        w = 1.0 / len(addrs)
        return {a: round(w, 4) for a in addrs}

    return {a: round(v / total, 4) for a, v in inv_vols.items()}
