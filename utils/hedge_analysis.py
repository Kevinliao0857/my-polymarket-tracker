"""Hedge analysis engine — identifies and analyzes hedge pairs."""

import math
from collections import defaultdict

from .filters import get_up_down


# ---------------------------------------------------------------------------
# Hedge Pair Identification
# ---------------------------------------------------------------------------

def identify_hedge_pairs(trades: list) -> list:
    """Match BUY trades into hedge pairs (UP + DOWN on same market).

    Groups trades by title, finds UP/DOWN pairs using filters.get_up_down().
    Returns list of pair dicts with size_ratio, time_delta, symmetry info.
    """
    # Group BUY trades by market title
    by_market = defaultdict(list)
    for t in trades:
        if t.get("side") != "BUY":
            continue
        title = t.get("title")
        if not title:
            continue
        by_market[title].append(t)

    pairs = []
    for title, group in by_market.items():
        ups = []
        downs = []
        for t in group:
            direction = get_up_down(t)
            if "UP" in direction:
                ups.append(t)
            elif "DOWN" in direction:
                downs.append(t)

        # Pair up FIFO by timestamp
        ups.sort(key=lambda t: t.get("timestamp") or 0)
        downs.sort(key=lambda t: t.get("timestamp") or 0)

        for i in range(min(len(ups), len(downs))):
            up_t = ups[i]
            down_t = downs[i]
            up_size = float(up_t.get("size") or 0)
            down_size = float(down_t.get("size") or 0)

            if up_size == 0 and down_size == 0:
                continue

            max_size = max(up_size, down_size)
            min_size = min(up_size, down_size)
            ratio = min_size / max_size if max_size > 0 else 0

            up_ts = int(up_t.get("timestamp") or 0)
            down_ts = int(down_t.get("timestamp") or 0)
            time_delta = abs(up_ts - down_ts)

            pairs.append({
                "market": title,
                "up_trade": up_t,
                "down_trade": down_t,
                "up_size": up_size,
                "down_size": down_size,
                "size_ratio": round(ratio, 3),
                "time_delta_sec": time_delta,
                "symmetric": 0.95 <= ratio <= 1.05,
            })

    return pairs


# ---------------------------------------------------------------------------
# Hedge Ratio
# ---------------------------------------------------------------------------

def compute_hedge_ratio(trades: list) -> dict:
    """What % of BUY trades are part of a hedge pair vs directional.

    Returns: {"hedged_pct": float, "directional_pct": float,
              "hedged_count": int, "directional_count": int, "by_market": dict}
    """
    buy_trades = [t for t in trades if t.get("side") == "BUY"]
    if not buy_trades:
        return {
            "hedged_pct": 0, "directional_pct": 0,
            "hedged_count": 0, "directional_count": 0, "by_market": {},
        }

    pairs = identify_hedge_pairs(trades)
    hedged_titles = set()
    for p in pairs:
        hedged_titles.add(p["market"])

    hedged = sum(1 for t in buy_trades if t.get("title") in hedged_titles)
    directional = len(buy_trades) - hedged

    total = len(buy_trades)
    by_market = {}
    by_title = defaultdict(lambda: {"hedged": False, "count": 0})
    for t in buy_trades:
        title = t.get("title")
        by_title[title]["count"] += 1
        if title in hedged_titles:
            by_title[title]["hedged"] = True
    for title, info in by_title.items():
        by_market[title] = "hedged" if info["hedged"] else "directional"

    return {
        "hedged_pct": round(hedged / total * 100, 1) if total else 0,
        "directional_pct": round(directional / total * 100, 1) if total else 0,
        "hedged_count": hedged,
        "directional_count": directional,
        "by_market": by_market,
    }


# ---------------------------------------------------------------------------
# Hedge Timing
# ---------------------------------------------------------------------------

def compute_hedge_timing(hedge_pairs: list) -> dict:
    """How quickly does the second leg follow the first?

    Returns: {"mean_delay_sec": float, "median_delay_sec": float, "sample_size": int}
    """
    delays = [p["time_delta_sec"] for p in hedge_pairs if p.get("time_delta_sec") is not None]
    if not delays:
        return {"mean_delay_sec": 0, "median_delay_sec": 0, "sample_size": 0}

    delays.sort()
    n = len(delays)
    mean = sum(delays) / n
    median = delays[n // 2] if n % 2 else (delays[n // 2 - 1] + delays[n // 2]) / 2
    return {
        "mean_delay_sec": round(mean, 1),
        "median_delay_sec": round(median, 1),
        "sample_size": n,
    }


# ---------------------------------------------------------------------------
# Hedge Symmetry
# ---------------------------------------------------------------------------

def compute_hedge_symmetry(hedge_pairs: list) -> dict:
    """Distribution of size ratios between UP and DOWN legs.

    Returns: {"mean_ratio": float, "std_ratio": float, "perfectly_symmetric_pct": float}
    """
    ratios = [p["size_ratio"] for p in hedge_pairs if p.get("size_ratio") is not None]
    if not ratios:
        return {"mean_ratio": 0, "std_ratio": 0, "perfectly_symmetric_pct": 0, "sample_size": 0}

    n = len(ratios)
    mean = sum(ratios) / n
    variance = sum((r - mean) ** 2 for r in ratios) / n if n > 1 else 0
    symmetric_count = sum(1 for r in ratios if 0.95 <= r <= 1.05)

    return {
        "mean_ratio": round(mean, 3),
        "std_ratio": round(math.sqrt(variance), 3),
        "perfectly_symmetric_pct": round(symmetric_count / n * 100, 1),
        "sample_size": n,
    }


# ---------------------------------------------------------------------------
# Hedge Style Classification
# ---------------------------------------------------------------------------

def classify_hedge_style(hedge_ratio: dict, timing: dict, symmetry: dict) -> str:
    """Heuristic classification of hedging style.

    "Arbitrageur" — high symmetry, fast timing
    "Risk Manager" — lower symmetry or slower timing
    "Mixed" — somewhere in between
    "Directional" — mostly unhedged
    """
    hedged_pct = hedge_ratio.get("hedged_pct", 0)
    if hedged_pct < 30:
        return "Directional"

    sym_pct = symmetry.get("perfectly_symmetric_pct", 0)
    mean_delay = timing.get("mean_delay_sec", float("inf"))

    if sym_pct >= 60 and mean_delay <= 60:
        return "Arbitrageur"
    elif sym_pct >= 40 or mean_delay <= 120:
        return "Mixed"
    else:
        return "Risk Manager"
