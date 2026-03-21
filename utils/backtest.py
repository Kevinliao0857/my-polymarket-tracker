"""Backtesting framework — replay historical trades with configurable parameters."""

import math
from dataclasses import dataclass, field
from collections import defaultdict

import pandas as pd

from .db import get_all_trades, get_all_settled_trades
from .filters import is_crypto
from .hedge_analysis import identify_hedge_pairs


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class BacktestConfig:
    trader_addresses: list[str]
    bankroll: float = 1000.0
    copy_ratio: float = 10.0
    entry_delay_sec: int = 0
    stop_loss_pct: float | None = None
    only_hedged: bool = False
    only_crypto: bool = True
    only_market_types: list[str] | None = None
    allocation_weights: dict[str, float] | None = None
    start_ts: int | None = None
    end_ts: int | None = None


@dataclass
class BacktestResult:
    pnl_curve: pd.DataFrame  # timestamp, cumulative_pnl, bankroll
    total_pnl: float = 0.0
    total_trades: int = 0
    win_rate: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_amt: float = 0.0
    sharpe: float = 0.0
    trades_log: pd.DataFrame = field(default_factory=lambda: pd.DataFrame())


# ---------------------------------------------------------------------------
# Backtest Engine
# ---------------------------------------------------------------------------

def run_backtest(config: BacktestConfig) -> BacktestResult:
    """Replay historical trades and simulate copy-trading.

    Uses BUY for entries, SELL for early exits, settled_trades for held-to-resolution.
    """
    # Load data
    all_trades = []
    for addr in config.trader_addresses:
        trades = get_all_trades(trader_address=addr)
        for t in trades:
            t["_trader"] = addr
        all_trades.extend(trades)

    settled_map = _build_settled_map(config.trader_addresses)

    # Sort chronologically
    all_trades.sort(key=lambda t: t.get("timestamp") or 0)

    # Filter by time range
    if config.start_ts:
        all_trades = [t for t in all_trades if (t.get("timestamp") or 0) >= config.start_ts]
    if config.end_ts:
        all_trades = [t for t in all_trades if (t.get("timestamp") or 0) <= config.end_ts]

    # Identify hedged markets if filtering
    hedged_titles = set()
    if config.only_hedged:
        buy_trades = [t for t in all_trades if t.get("side") == "BUY"]
        pairs = identify_hedge_pairs(buy_trades)
        hedged_titles = {p["market"] for p in pairs}

    # Allocation weights
    weights = config.allocation_weights or {}
    if not weights:
        w = 1.0 / len(config.trader_addresses) if config.trader_addresses else 1.0
        weights = {a: w for a in config.trader_addresses}

    # Simulation state
    bankroll = config.bankroll
    peak_bankroll = bankroll
    open_positions = {}  # (trader, title, outcome) -> {entry_price, shares, cost, timestamp}
    realized_pnl = 0.0
    pnl_points = []
    trade_log = []
    stopped_traders = set()

    for t in all_trades:
        trader = t["_trader"]
        side = t.get("side")
        title = t.get("title")
        outcome = t.get("outcome")
        ts = t.get("timestamp") or 0
        price = float(t.get("price") or 0)
        size = float(t.get("size") or 0)

        if not title or not side:
            continue

        # Apply filters
        if config.only_crypto and not is_crypto(t):
            continue
        if config.only_hedged and title not in hedged_titles:
            continue
        if config.only_market_types:
            from .analytics import _extract_coin
            coin = _extract_coin(title)
            if coin and coin not in config.only_market_types:
                continue

        # Stop-loss check
        if trader in stopped_traders:
            continue

        pos_key = (trader, title, outcome)
        trader_weight = weights.get(trader, 1.0)

        if side == "BUY":
            # Apply entry delay filter
            if config.entry_delay_sec > 0:
                # Skip if we can't react fast enough (simplified)
                pass

            copied_shares = round(size / config.copy_ratio * trader_weight, 2)
            cost = copied_shares * price
            if cost > bankroll - realized_pnl:
                continue  # Not enough capital

            open_positions[pos_key] = {
                "entry_price": price,
                "shares": copied_shares,
                "cost": cost,
                "timestamp": ts,
            }
            trade_log.append({
                "trader": trader,
                "title": title,
                "outcome": outcome,
                "side": "BUY",
                "shares": copied_shares,
                "price": price,
                "cost": cost,
                "timestamp": ts,
                "pnl": None,
            })

        elif side == "SELL" and pos_key in open_positions:
            # Early exit
            pos = open_positions.pop(pos_key)
            exit_value = pos["shares"] * price
            pnl = exit_value - pos["cost"]
            realized_pnl += pnl

            trade_log.append({
                "trader": trader,
                "title": title,
                "outcome": outcome,
                "side": "SELL",
                "shares": pos["shares"],
                "price": price,
                "cost": pos["cost"],
                "timestamp": ts,
                "pnl": round(pnl, 2),
            })

        # Record PnL point
        current_value = bankroll + realized_pnl
        pnl_points.append({
            "timestamp": ts,
            "cumulative_pnl": round(realized_pnl, 2),
            "bankroll": round(current_value, 2),
        })

        # Update peak and check drawdown
        if current_value > peak_bankroll:
            peak_bankroll = current_value
        if config.stop_loss_pct and peak_bankroll > 0:
            drawdown_pct = (peak_bankroll - current_value) / peak_bankroll * 100
            if drawdown_pct >= config.stop_loss_pct:
                stopped_traders.add(trader)

    # Resolve remaining open positions using settled trades
    for pos_key, pos in list(open_positions.items()):
        trader, title, outcome = pos_key
        settled_pnl = settled_map.get((trader, title, outcome))
        if settled_pnl is not None:
            # Scale the settled PnL by our copy ratio
            trader_size = _get_trader_size(all_trades, trader, title, outcome)
            if trader_size > 0:
                scale = pos["shares"] / trader_size
                pnl = settled_pnl * scale
            else:
                pnl = 0
            realized_pnl += pnl
            trade_log.append({
                "trader": trader,
                "title": title,
                "outcome": outcome,
                "side": "SETTLED",
                "shares": pos["shares"],
                "price": None,
                "cost": pos["cost"],
                "timestamp": None,
                "pnl": round(pnl, 2),
            })

    # Build result
    pnl_curve = pd.DataFrame(pnl_points) if pnl_points else pd.DataFrame(
        columns=["timestamp", "cumulative_pnl", "bankroll"]
    )
    trades_df = pd.DataFrame(trade_log) if trade_log else pd.DataFrame()

    completed = [t for t in trade_log if t.get("pnl") is not None]
    wins = sum(1 for t in completed if t["pnl"] > 0)
    total_completed = len(completed)

    # Max drawdown from PnL curve
    max_dd_pct, max_dd_amt = _compute_max_drawdown(pnl_curve)

    # Sharpe from trade PnLs
    trade_pnls = [t["pnl"] for t in completed if t["pnl"] is not None]
    sharpe = _compute_trade_sharpe(trade_pnls)

    return BacktestResult(
        pnl_curve=pnl_curve,
        total_pnl=round(realized_pnl, 2),
        total_trades=total_completed,
        win_rate=round(wins / total_completed * 100, 1) if total_completed else 0,
        max_drawdown_pct=max_dd_pct,
        max_drawdown_amt=max_dd_amt,
        sharpe=sharpe,
        trades_log=trades_df,
    )


# ---------------------------------------------------------------------------
# Drawdown
# ---------------------------------------------------------------------------

def compute_drawdown_series(pnl_curve: pd.DataFrame) -> pd.DataFrame:
    """From a PnL curve, compute running drawdown at each point."""
    if pnl_curve.empty or "bankroll" not in pnl_curve.columns:
        return pd.DataFrame(columns=["timestamp", "drawdown_pct", "drawdown_amt"])

    peak = pnl_curve["bankroll"].cummax()
    dd_amt = peak - pnl_curve["bankroll"]
    dd_pct = (dd_amt / peak * 100).fillna(0)

    return pd.DataFrame({
        "timestamp": pnl_curve["timestamp"],
        "drawdown_pct": dd_pct.round(2),
        "drawdown_amt": dd_amt.round(2),
    })


def compare_backtests(results: list, labels: list) -> pd.DataFrame:
    """Side-by-side comparison of multiple backtest runs."""
    rows = []
    for r, label in zip(results, labels):
        rows.append({
            "Run": label,
            "Total PnL": r.total_pnl,
            "Trades": r.total_trades,
            "Win Rate %": r.win_rate,
            "Max Drawdown %": r.max_drawdown_pct,
            "Sharpe": r.sharpe,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _build_settled_map(trader_addresses: list) -> dict:
    """Build lookup: (trader, title, outcome) -> total pnl."""
    result = {}
    for addr in trader_addresses:
        settled = get_all_settled_trades(trader_address=addr)
        for s in settled:
            key = (addr, s.get("title"), s.get("outcome"))
            pnl = s.get("pnl")
            if pnl is not None:
                result[key] = result.get(key, 0) + float(pnl)
    return result


def _get_trader_size(trades: list, trader: str, title: str, outcome: str) -> float:
    """Get the trader's total BUY size for a specific position."""
    total = 0.0
    for t in trades:
        if (t.get("_trader") == trader and t.get("title") == title
                and t.get("outcome") == outcome and t.get("side") == "BUY"):
            total += float(t.get("size") or 0)
    return total


def _compute_max_drawdown(pnl_curve: pd.DataFrame) -> tuple:
    """Returns (max_drawdown_pct, max_drawdown_amt)."""
    if pnl_curve.empty or "bankroll" not in pnl_curve.columns:
        return 0.0, 0.0

    peak = pnl_curve["bankroll"].cummax()
    dd_amt = (peak - pnl_curve["bankroll"]).max()
    peak_at_max_dd = peak[pnl_curve["bankroll"].idxmin()] if len(pnl_curve) > 0 else 0
    dd_pct = (dd_amt / peak_at_max_dd * 100) if peak_at_max_dd > 0 else 0

    return round(float(dd_pct), 2), round(float(dd_amt), 2)


def _compute_trade_sharpe(pnls: list) -> float:
    """Simple Sharpe from individual trade PnLs."""
    if len(pnls) < 2:
        return 0.0
    mean = sum(pnls) / len(pnls)
    std = math.sqrt(sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1))
    if std == 0:
        return 0.0
    return round(mean / std, 2)
