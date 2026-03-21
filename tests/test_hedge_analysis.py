"""Tests for utils/hedge_analysis.py — hedge pair identification and analysis."""

import pytest
from utils.hedge_analysis import (
    identify_hedge_pairs,
    compute_hedge_ratio,
    compute_hedge_timing,
    compute_hedge_symmetry,
    classify_hedge_style,
)


def _trade(side="BUY", title="BTC above $100k?", outcome="Up", size=100, price=0.5, ts=1000):
    return {
        "side": side,
        "title": title,
        "outcome": outcome,
        "size": size,
        "price": price,
        "timestamp": ts,
    }


# ---------------------------------------------------------------------------
# identify_hedge_pairs
# ---------------------------------------------------------------------------

class TestIdentifyHedgePairs:
    def test_basic_pair(self):
        trades = [
            _trade(outcome="Up", size=100, ts=1000),
            _trade(outcome="Down", size=100, ts=1060),
        ]
        pairs = identify_hedge_pairs(trades)
        assert len(pairs) == 1
        assert pairs[0]["size_ratio"] == 1.0
        assert pairs[0]["time_delta_sec"] == 60
        assert pairs[0]["symmetric"] is True

    def test_asymmetric_pair(self):
        trades = [
            _trade(outcome="Up", size=100, ts=1000),
            _trade(outcome="Down", size=50, ts=1000),
        ]
        pairs = identify_hedge_pairs(trades)
        assert len(pairs) == 1
        assert pairs[0]["size_ratio"] == 0.5
        assert pairs[0]["symmetric"] is False

    def test_no_pair_single_direction(self):
        trades = [
            _trade(outcome="Up", size=100),
            _trade(outcome="Up", size=50),
        ]
        pairs = identify_hedge_pairs(trades)
        assert len(pairs) == 0

    def test_ignores_sell_trades(self):
        trades = [
            _trade(side="BUY", outcome="Up", size=100),
            _trade(side="SELL", outcome="Down", size=100),
        ]
        pairs = identify_hedge_pairs(trades)
        assert len(pairs) == 0

    def test_multiple_markets(self):
        trades = [
            _trade(title="BTC up?", outcome="Up", size=100, ts=1000),
            _trade(title="BTC up?", outcome="Down", size=100, ts=1010),
            _trade(title="ETH up?", outcome="Up", size=50, ts=2000),
            _trade(title="ETH up?", outcome="Down", size=50, ts=2005),
        ]
        pairs = identify_hedge_pairs(trades)
        assert len(pairs) == 2

    def test_empty(self):
        assert identify_hedge_pairs([]) == []

    def test_fifo_matching(self):
        trades = [
            _trade(outcome="Up", size=100, ts=1000),
            _trade(outcome="Up", size=200, ts=1100),
            _trade(outcome="Down", size=100, ts=1050),
            _trade(outcome="Down", size=200, ts=1150),
        ]
        pairs = identify_hedge_pairs(trades)
        assert len(pairs) == 2
        # First pair: ts=1000 UP with ts=1050 DOWN
        assert pairs[0]["up_size"] == 100
        assert pairs[0]["down_size"] == 100


# ---------------------------------------------------------------------------
# compute_hedge_ratio
# ---------------------------------------------------------------------------

class TestHedgeRatio:
    def test_fully_hedged(self):
        trades = [
            _trade(outcome="Up", size=100),
            _trade(outcome="Down", size=100),
        ]
        ratio = compute_hedge_ratio(trades)
        assert ratio["hedged_pct"] == 100.0
        assert ratio["directional_pct"] == 0.0

    def test_fully_directional(self):
        trades = [
            _trade(title="BTC", outcome="Up", size=100),
            _trade(title="ETH", outcome="Up", size=50),
        ]
        ratio = compute_hedge_ratio(trades)
        assert ratio["hedged_pct"] == 0.0
        assert ratio["directional_pct"] == 100.0

    def test_mixed(self):
        trades = [
            _trade(title="BTC", outcome="Up", size=100),
            _trade(title="BTC", outcome="Down", size=100),
            _trade(title="ETH", outcome="Up", size=50),
        ]
        ratio = compute_hedge_ratio(trades)
        assert ratio["hedged_count"] == 2
        assert ratio["directional_count"] == 1

    def test_empty(self):
        ratio = compute_hedge_ratio([])
        assert ratio["hedged_pct"] == 0


# ---------------------------------------------------------------------------
# compute_hedge_timing
# ---------------------------------------------------------------------------

class TestHedgeTiming:
    def test_basic(self):
        pairs = [
            {"time_delta_sec": 30},
            {"time_delta_sec": 90},
        ]
        timing = compute_hedge_timing(pairs)
        assert timing["mean_delay_sec"] == 60.0
        assert timing["median_delay_sec"] == 60.0
        assert timing["sample_size"] == 2

    def test_empty(self):
        timing = compute_hedge_timing([])
        assert timing["sample_size"] == 0

    def test_single(self):
        timing = compute_hedge_timing([{"time_delta_sec": 45}])
        assert timing["mean_delay_sec"] == 45.0


# ---------------------------------------------------------------------------
# compute_hedge_symmetry
# ---------------------------------------------------------------------------

class TestHedgeSymmetry:
    def test_perfect_symmetry(self):
        pairs = [
            {"size_ratio": 1.0},
            {"size_ratio": 0.98},
        ]
        sym = compute_hedge_symmetry(pairs)
        assert sym["perfectly_symmetric_pct"] == 100.0

    def test_asymmetric(self):
        pairs = [
            {"size_ratio": 1.0},
            {"size_ratio": 0.5},
        ]
        sym = compute_hedge_symmetry(pairs)
        assert sym["perfectly_symmetric_pct"] == 50.0

    def test_empty(self):
        sym = compute_hedge_symmetry([])
        assert sym["sample_size"] == 0


# ---------------------------------------------------------------------------
# classify_hedge_style
# ---------------------------------------------------------------------------

class TestClassifyHedgeStyle:
    def test_arbitrageur(self):
        style = classify_hedge_style(
            {"hedged_pct": 80},
            {"mean_delay_sec": 30},
            {"perfectly_symmetric_pct": 70},
        )
        assert style == "Arbitrageur"

    def test_directional(self):
        style = classify_hedge_style(
            {"hedged_pct": 10},
            {"mean_delay_sec": 300},
            {"perfectly_symmetric_pct": 20},
        )
        assert style == "Directional"

    def test_risk_manager(self):
        style = classify_hedge_style(
            {"hedged_pct": 60},
            {"mean_delay_sec": 300},
            {"perfectly_symmetric_pct": 20},
        )
        assert style == "Risk Manager"

    def test_mixed(self):
        style = classify_hedge_style(
            {"hedged_pct": 50},
            {"mean_delay_sec": 90},
            {"perfectly_symmetric_pct": 45},
        )
        assert style == "Mixed"
