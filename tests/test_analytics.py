"""Tests for utils/analytics.py — core analytics engine."""

import pytest
from utils.analytics import (
    _extract_coin,
    compute_win_rate,
    compute_position_size_stats,
    compute_pnl_distribution,
    compute_hold_duration,
    compute_time_of_day_patterns,
    compute_sharpe_ratio,
    compute_market_overlap,
    compute_allocation_weights,
)


# ---------------------------------------------------------------------------
# _extract_coin
# ---------------------------------------------------------------------------

class TestExtractCoin:
    def test_ticker_match(self):
        assert _extract_coin("Will BTC go above $100k?") == "BTC"

    def test_full_name_match(self):
        assert _extract_coin("Will bitcoin reach $100k?") == "BTC"

    def test_case_insensitive(self):
        assert _extract_coin("ETH price prediction") == "ETH"

    def test_no_match(self):
        assert _extract_coin("Will it rain tomorrow?") is None

    def test_empty(self):
        assert _extract_coin("") is None
        assert _extract_coin(None) is None


# ---------------------------------------------------------------------------
# compute_win_rate
# ---------------------------------------------------------------------------

class TestWinRate:
    def test_basic(self):
        settled = [
            {"pnl": 10, "title": "BTC up"},
            {"pnl": -5, "title": "ETH up"},
            {"pnl": 20, "title": "BTC down"},
        ]
        result = compute_win_rate(settled)
        assert result["overall"] == pytest.approx(2 / 3)
        assert result["sample_size"] == 3

    def test_grouped_by_coin(self):
        settled = [
            {"pnl": 10, "title": "BTC up"},
            {"pnl": -5, "title": "BTC down"},
            {"pnl": 20, "title": "ETH up"},
        ]
        result = compute_win_rate(settled, group_by="coin")
        assert result["by_group"]["BTC"] == pytest.approx(0.5)
        assert result["by_group"]["ETH"] == pytest.approx(1.0)

    def test_empty(self):
        result = compute_win_rate([])
        assert result["overall"] == 0.0
        assert result["sample_size"] == 0

    def test_all_wins(self):
        settled = [{"pnl": 10, "title": "BTC"}, {"pnl": 5, "title": "ETH"}]
        assert compute_win_rate(settled)["overall"] == 1.0

    def test_all_losses(self):
        settled = [{"pnl": -10, "title": "BTC"}, {"pnl": -5, "title": "ETH"}]
        assert compute_win_rate(settled)["overall"] == 0.0

    def test_zero_pnl_is_not_win(self):
        settled = [{"pnl": 0, "title": "BTC"}]
        assert compute_win_rate(settled)["overall"] == 0.0


# ---------------------------------------------------------------------------
# compute_position_size_stats
# ---------------------------------------------------------------------------

class TestPositionSizeStats:
    def test_basic(self):
        trades = [{"size": 100}, {"size": 200}, {"size": 300}]
        stats = compute_position_size_stats(trades)
        assert stats["mean"] == 200
        assert stats["median"] == 200
        assert stats["min"] == 100
        assert stats["max"] == 300
        assert stats["count"] == 3

    def test_empty(self):
        stats = compute_position_size_stats([])
        assert stats["mean"] == 0
        assert stats["count"] == 0

    def test_single(self):
        stats = compute_position_size_stats([{"size": 50}])
        assert stats["mean"] == 50
        assert stats["median"] == 50

    def test_skips_none_sizes(self):
        trades = [{"size": 100}, {"size": None}, {"size": 200}]
        stats = compute_position_size_stats(trades)
        assert stats["count"] == 2


# ---------------------------------------------------------------------------
# compute_pnl_distribution
# ---------------------------------------------------------------------------

class TestPnlDistribution:
    def test_basic(self):
        settled = [
            {"pnl": 10, "title": "BTC up"},
            {"pnl": -5, "title": "ETH down"},
        ]
        df = compute_pnl_distribution(settled)
        assert len(df) == 2
        assert "pnl" in df.columns
        assert "coin" in df.columns

    def test_empty(self):
        df = compute_pnl_distribution([])
        assert df.empty


# ---------------------------------------------------------------------------
# compute_hold_duration
# ---------------------------------------------------------------------------

class TestHoldDuration:
    def test_buy_sell_match(self):
        trades = [
            {"side": "BUY", "title": "BTC up", "outcome": "UP", "timestamp": 1000},
            {"side": "SELL", "title": "BTC up", "outcome": "UP", "timestamp": 4600},
        ]
        result = compute_hold_duration(trades)
        assert result["mean_hours"] == 1.0
        assert result["sample_size"] == 1

    def test_multiple_pairs(self):
        trades = [
            {"side": "BUY", "title": "BTC up", "outcome": "UP", "timestamp": 1000},
            {"side": "SELL", "title": "BTC up", "outcome": "UP", "timestamp": 4600},
            {"side": "BUY", "title": "ETH up", "outcome": "UP", "timestamp": 2000},
            {"side": "SELL", "title": "ETH up", "outcome": "UP", "timestamp": 9200},
        ]
        result = compute_hold_duration(trades)
        assert result["sample_size"] == 2
        assert result["mean_hours"] == 1.5  # (1h + 2h) / 2

    def test_no_sells(self):
        trades = [
            {"side": "BUY", "title": "BTC", "outcome": "UP", "timestamp": 1000},
        ]
        result = compute_hold_duration(trades)
        assert result["sample_size"] == 0

    def test_with_settled_fallback(self):
        trades = [
            {"side": "BUY", "title": "BTC up", "outcome": "UP", "timestamp": 1000},
        ]
        settled = [
            {"title": "BTC up", "outcome": "UP", "settled_at": "7600"},
        ]
        result = compute_hold_duration(trades, settled)
        assert result["mean_hours"] == pytest.approx(1.833, abs=0.01)
        assert result["sample_size"] == 1

    def test_empty(self):
        result = compute_hold_duration([])
        assert result["sample_size"] == 0


# ---------------------------------------------------------------------------
# compute_time_of_day_patterns
# ---------------------------------------------------------------------------

class TestTimeOfDay:
    def test_returns_24_hours(self):
        trades = [{"timestamp": 1700000000, "size": 100}]
        df = compute_time_of_day_patterns(trades)
        assert len(df) == 24
        assert df["trade_count"].sum() >= 1

    def test_empty(self):
        df = compute_time_of_day_patterns([])
        assert len(df) == 24
        assert df["trade_count"].sum() == 0


# ---------------------------------------------------------------------------
# compute_sharpe_ratio
# ---------------------------------------------------------------------------

class TestSharpeRatio:
    def test_basic(self):
        settled = [
            {"pnl": 10, "settled_at": "2025-01-01"},
            {"pnl": -5, "settled_at": "2025-01-02"},
            {"pnl": 15, "settled_at": "2025-01-03"},
        ]
        sharpe = compute_sharpe_ratio(settled)
        assert isinstance(sharpe, float)

    def test_single_day(self):
        settled = [{"pnl": 10, "settled_at": "2025-01-01"}]
        assert compute_sharpe_ratio(settled) == 0.0

    def test_empty(self):
        assert compute_sharpe_ratio([]) == 0.0


# ---------------------------------------------------------------------------
# compute_market_overlap
# ---------------------------------------------------------------------------

class TestMarketOverlap:
    def test_full_overlap(self):
        traders_trades = {
            "0x1": [{"title": "BTC up"}, {"title": "ETH up"}],
            "0x2": [{"title": "BTC up"}, {"title": "ETH up"}],
        }
        df = compute_market_overlap(traders_trades)
        assert df.loc["0x1", "0x2"] == 100.0

    def test_no_overlap(self):
        traders_trades = {
            "0x1": [{"title": "BTC up"}],
            "0x2": [{"title": "SOL up"}],
        }
        df = compute_market_overlap(traders_trades)
        assert df.loc["0x1", "0x2"] == 0.0

    def test_single_trader(self):
        traders_trades = {"0x1": [{"title": "BTC"}]}
        df = compute_market_overlap(traders_trades)
        assert df.empty


# ---------------------------------------------------------------------------
# compute_allocation_weights
# ---------------------------------------------------------------------------

class TestAllocationWeights:
    def test_equal(self):
        metrics = {"0x1": {"pnl_std": 10}, "0x2": {"pnl_std": 20}}
        w = compute_allocation_weights(metrics, method="equal")
        assert w["0x1"] == pytest.approx(0.5)
        assert w["0x2"] == pytest.approx(0.5)

    def test_equal_risk(self):
        metrics = {"0x1": {"pnl_std": 10}, "0x2": {"pnl_std": 20}}
        w = compute_allocation_weights(metrics, method="equal_risk")
        # Inverse vol: 1/10=0.1, 1/20=0.05 → 0x1 gets 2/3, 0x2 gets 1/3
        assert w["0x1"] > w["0x2"]
        assert abs(w["0x1"] + w["0x2"] - 1.0) < 0.01

    def test_single_trader(self):
        w = compute_allocation_weights({"0x1": {"pnl_std": 5}})
        assert w["0x1"] == 1.0

    def test_empty(self):
        assert compute_allocation_weights({}) == {}

    def test_zero_std_fallback(self):
        metrics = {"0x1": {"pnl_std": 0}, "0x2": {"pnl_std": 0}}
        w = compute_allocation_weights(metrics, method="equal_risk")
        assert w["0x1"] == pytest.approx(0.5)
