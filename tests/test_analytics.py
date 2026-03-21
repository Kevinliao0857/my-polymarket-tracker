"""Tests for utils/analytics.py — strategy reverse-engineering & copy profitability."""

import pytest
from utils.analytics import (
    _extract_coin,
    _match_buy_sell,
    compute_win_rate,
    compute_hold_duration,
    compute_time_of_day_patterns,
    compute_sharpe_ratio,
    compute_market_overlap,
    compute_allocation_weights,
    analyze_entry_prices,
    analyze_exit_behavior,
    analyze_conviction,
    analyze_copy_delay_impact,
    analyze_risk_reward,
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
# _match_buy_sell
# ---------------------------------------------------------------------------

class TestMatchBuySell:
    def test_basic_match(self):
        trades = [
            {"side": "BUY", "title": "BTC", "outcome": "UP", "timestamp": 1000},
            {"side": "SELL", "title": "BTC", "outcome": "UP", "timestamp": 2000},
        ]
        matched, unmatched = _match_buy_sell(trades)
        assert len(matched) == 1
        assert len(unmatched) == 0

    def test_unmatched_buy(self):
        trades = [
            {"side": "BUY", "title": "BTC", "outcome": "UP", "timestamp": 1000},
        ]
        matched, unmatched = _match_buy_sell(trades)
        assert len(matched) == 0
        assert len(unmatched) == 1

    def test_fifo_order(self):
        trades = [
            {"side": "BUY", "title": "BTC", "outcome": "UP", "timestamp": 1000, "price": 0.5},
            {"side": "BUY", "title": "BTC", "outcome": "UP", "timestamp": 2000, "price": 0.6},
            {"side": "SELL", "title": "BTC", "outcome": "UP", "timestamp": 3000, "price": 0.8},
        ]
        matched, unmatched = _match_buy_sell(trades)
        assert len(matched) == 1
        assert len(unmatched) == 1
        # First BUY matched with first SELL
        assert matched[0][0]["timestamp"] == 1000

    def test_different_markets_no_match(self):
        trades = [
            {"side": "BUY", "title": "BTC", "outcome": "UP", "timestamp": 1000},
            {"side": "SELL", "title": "ETH", "outcome": "UP", "timestamp": 2000},
        ]
        matched, unmatched = _match_buy_sell(trades)
        assert len(matched) == 0
        assert len(unmatched) == 1


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

    def test_zero_pnl_is_not_win(self):
        settled = [{"pnl": 0, "title": "BTC"}]
        assert compute_win_rate(settled)["overall"] == 0.0


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

    def test_with_settled_fallback(self):
        trades = [
            {"side": "BUY", "title": "BTC up", "outcome": "UP", "timestamp": 1000},
        ]
        settled = [
            {"title": "BTC up", "outcome": "UP", "settled_at": "7600"},
        ]
        result = compute_hold_duration(trades, settled)
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
        df = compute_market_overlap({"0x1": [{"title": "BTC"}]})
        assert df.empty


# ---------------------------------------------------------------------------
# compute_allocation_weights
# ---------------------------------------------------------------------------

class TestAllocationWeights:
    def test_equal(self):
        metrics = {"0x1": {"pnl_std": 10}, "0x2": {"pnl_std": 20}}
        w = compute_allocation_weights(metrics, method="equal")
        assert w["0x1"] == pytest.approx(0.5)

    def test_equal_risk(self):
        metrics = {"0x1": {"pnl_std": 10}, "0x2": {"pnl_std": 20}}
        w = compute_allocation_weights(metrics, method="equal_risk")
        assert w["0x1"] > w["0x2"]
        assert abs(w["0x1"] + w["0x2"] - 1.0) < 0.01

    def test_empty(self):
        assert compute_allocation_weights({}) == {}


# ===========================================================================
# Strategy Analysis Tests
# ===========================================================================


# ---------------------------------------------------------------------------
# analyze_entry_prices
# ---------------------------------------------------------------------------

class TestEntryPrices:
    def test_basic(self):
        trades = [
            {"side": "BUY", "price": 0.3, "title": "BTC up"},
            {"side": "BUY", "price": 0.7, "title": "ETH up"},
            {"side": "BUY", "price": 0.5, "title": "BTC down"},
        ]
        result = analyze_entry_prices(trades)
        assert result["sample_size"] == 3
        assert result["mean_entry"] == pytest.approx(0.5)
        assert result["price_buckets"]["underdog (0.20-0.40)"] == 1
        assert result["price_buckets"]["coinflip (0.40-0.60)"] == 1
        assert result["price_buckets"]["favorite (0.60-0.80)"] == 1

    def test_by_coin(self):
        trades = [
            {"side": "BUY", "price": 0.3, "title": "BTC up"},
            {"side": "BUY", "price": 0.5, "title": "BTC down"},
        ]
        result = analyze_entry_prices(trades)
        assert "BTC" in result["by_coin"]
        assert result["by_coin"]["BTC"] == pytest.approx(0.4)

    def test_ignores_sell(self):
        trades = [
            {"side": "BUY", "price": 0.3, "title": "BTC"},
            {"side": "SELL", "price": 0.8, "title": "BTC"},
        ]
        result = analyze_entry_prices(trades)
        assert result["sample_size"] == 1

    def test_empty(self):
        result = analyze_entry_prices([])
        assert result["sample_size"] == 0

    def test_deep_underdog_bucket(self):
        trades = [{"side": "BUY", "price": 0.05, "title": "BTC"}]
        result = analyze_entry_prices(trades)
        assert result["price_buckets"]["deep_underdog (<0.20)"] == 1

    def test_heavy_favorite_bucket(self):
        trades = [{"side": "BUY", "price": 0.95, "title": "BTC"}]
        result = analyze_entry_prices(trades)
        assert result["price_buckets"]["heavy_favorite (>0.80)"] == 1


# ---------------------------------------------------------------------------
# analyze_exit_behavior
# ---------------------------------------------------------------------------

class TestExitBehavior:
    def test_take_profit(self):
        trades = [
            {"side": "BUY", "title": "BTC", "outcome": "UP", "price": 0.5, "timestamp": 1000},
            {"side": "SELL", "title": "BTC", "outcome": "UP", "price": 0.8, "timestamp": 5000},
        ]
        result = analyze_exit_behavior(trades)
        assert result["exit_triggers"]["take_profit"] == 1
        assert result["exit_triggers"]["stop_loss"] == 0
        assert result["early_exit_pct"] == 100.0

    def test_stop_loss(self):
        trades = [
            {"side": "BUY", "title": "BTC", "outcome": "UP", "price": 0.5, "timestamp": 1000},
            {"side": "SELL", "title": "BTC", "outcome": "UP", "price": 0.3, "timestamp": 5000},
        ]
        result = analyze_exit_behavior(trades)
        assert result["exit_triggers"]["stop_loss"] == 1

    def test_held_to_settlement(self):
        trades = [
            {"side": "BUY", "title": "BTC", "outcome": "UP", "price": 0.5, "timestamp": 1000},
        ]
        settled = [
            {"title": "BTC", "outcome": "UP", "pnl": 10},
        ]
        result = analyze_exit_behavior(trades, settled)
        assert result["held_to_settlement_pct"] == 100.0
        assert result["early_exit_pct"] == 0

    def test_mixed(self):
        trades = [
            {"side": "BUY", "title": "BTC", "outcome": "UP", "price": 0.5, "timestamp": 1000},
            {"side": "SELL", "title": "BTC", "outcome": "UP", "price": 0.8, "timestamp": 5000},
            {"side": "BUY", "title": "ETH", "outcome": "UP", "price": 0.4, "timestamp": 2000},
        ]
        settled = [{"title": "ETH", "outcome": "UP", "pnl": 5}]
        result = analyze_exit_behavior(trades, settled)
        assert result["early_exit_pct"] == 50.0
        assert result["held_to_settlement_pct"] == 50.0

    def test_empty(self):
        result = analyze_exit_behavior([])
        assert result["sample_size"] == 0

    def test_hold_before_exit(self):
        trades = [
            {"side": "BUY", "title": "BTC", "outcome": "UP", "price": 0.5, "timestamp": 1000},
            {"side": "SELL", "title": "BTC", "outcome": "UP", "price": 0.8, "timestamp": 4600},
        ]
        result = analyze_exit_behavior(trades)
        assert result["avg_hold_before_exit_hours"] == 1.0


# ---------------------------------------------------------------------------
# analyze_conviction
# ---------------------------------------------------------------------------

class TestConviction:
    def test_big_bets_win_more(self):
        trades = [
            {"side": "BUY", "title": "BTC", "outcome": "UP", "size": 200},
            {"side": "BUY", "title": "ETH", "outcome": "UP", "size": 50},
        ]
        settled = [
            {"title": "BTC", "outcome": "UP", "pnl": 100},
            {"title": "ETH", "outcome": "UP", "pnl": -20},
        ]
        result = analyze_conviction(trades, settled)
        assert result["big_bet_win_rate"] > result["small_bet_win_rate"]

    def test_scales_in(self):
        trades = [
            {"side": "BUY", "title": "BTC", "outcome": "UP", "size": 100},
            {"side": "BUY", "title": "BTC", "outcome": "UP", "size": 50},
        ]
        result = analyze_conviction(trades)
        assert result["scales_in"] is True
        assert result["avg_buys_per_market"] == 2.0

    def test_no_scaling(self):
        trades = [
            {"side": "BUY", "title": "BTC", "outcome": "UP", "size": 100},
            {"side": "BUY", "title": "ETH", "outcome": "UP", "size": 50},
        ]
        result = analyze_conviction(trades)
        assert result["scales_in"] is False

    def test_empty(self):
        result = analyze_conviction([])
        assert result["sample_size"] == 0


# ---------------------------------------------------------------------------
# analyze_copy_delay_impact
# ---------------------------------------------------------------------------

class TestCopyDelayImpact:
    def test_basic_delay_curve(self):
        trades = [
            {"side": "BUY", "title": "BTC up", "outcome": "UP", "price": 0.50, "timestamp": 1000},
        ]
        # Snapshots showing price increase after entry
        history = [
            {"title": "BTC up", "outcome": "UP", "cur_price": 0.52, "snapshot_at": "1970-01-01T00:17:40"},  # ~1min after
            {"title": "BTC up", "outcome": "UP", "cur_price": 0.55, "snapshot_at": "1970-01-01T00:21:40"},  # ~5min after
            {"title": "BTC up", "outcome": "UP", "cur_price": 0.60, "snapshot_at": "1970-01-01T00:31:40"},  # ~15min after
            {"title": "BTC up", "outcome": "UP", "cur_price": 0.65, "snapshot_at": "1970-01-01T00:47:40"},  # ~30min after
        ]
        result = analyze_copy_delay_impact(trades, history)
        assert result["sample_size"] >= 1
        # Price should increase over time
        if result["delay_impact"]:
            assert result["delay_impact"][0]["avg_price_change_pct"] > 0

    def test_no_snapshots(self):
        trades = [
            {"side": "BUY", "title": "BTC", "outcome": "UP", "price": 0.50, "timestamp": 1000},
        ]
        result = analyze_copy_delay_impact(trades, [])
        assert result["sample_size"] == 0

    def test_empty(self):
        result = analyze_copy_delay_impact([], [])
        assert result["sample_size"] == 0


# ---------------------------------------------------------------------------
# analyze_risk_reward
# ---------------------------------------------------------------------------

class TestRiskReward:
    def test_basic(self):
        settled = [
            {"pnl": 50, "size": 100, "price": 0.5, "title": "BTC up"},   # cost=50, return=100%
            {"pnl": -25, "size": 100, "price": 0.5, "title": "ETH up"},  # cost=50, return=-50%
        ]
        result = analyze_risk_reward(settled)
        assert result["sample_size"] == 2
        assert result["avg_return_on_capital"] == 25.0  # (100 + -50) / 2
        assert result["best_return_pct"] == 100.0
        assert result["worst_return_pct"] == -50.0
        assert result["risk_reward_ratio"] == 2.0  # 50/25

    def test_by_coin(self):
        settled = [
            {"pnl": 50, "size": 100, "price": 0.5, "title": "BTC up"},
            {"pnl": -10, "size": 100, "price": 0.5, "title": "BTC down"},
        ]
        result = analyze_risk_reward(settled)
        assert "BTC" in result["by_coin"]

    def test_all_wins(self):
        settled = [
            {"pnl": 50, "size": 100, "price": 0.5, "title": "BTC"},
        ]
        result = analyze_risk_reward(settled)
        assert result["risk_reward_ratio"] == 0  # No losses to compare

    def test_trades_detail_sorted(self):
        settled = [
            {"pnl": -25, "size": 100, "price": 0.5, "title": "Loser"},
            {"pnl": 50, "size": 100, "price": 0.5, "title": "Winner"},
        ]
        result = analyze_risk_reward(settled)
        assert result["trades_detail"][0]["return_pct"] > result["trades_detail"][1]["return_pct"]

    def test_empty(self):
        result = analyze_risk_reward([])
        assert result["sample_size"] == 0

    def test_skips_zero_cost(self):
        settled = [
            {"pnl": 50, "size": 0, "price": 0.5, "title": "BTC"},
            {"pnl": 50, "size": 100, "price": 0, "title": "ETH"},
        ]
        result = analyze_risk_reward(settled)
        assert result["sample_size"] == 0
