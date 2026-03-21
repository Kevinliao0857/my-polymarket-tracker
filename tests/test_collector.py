"""Tests for collector.py — background data collection process."""

import json
import pytest
from unittest.mock import patch, MagicMock

from utils.db import (
    set_db_path,
    close_connection,
    init_db,
    get_active_traders,
    get_trade_count,
    get_trades,
    get_latest_snapshot,
    get_settled_trades,
    upsert_trader,
)
from collector import (
    _ensure_default_trader,
    poll_trades,
    poll_positions,
    poll_settled,
    run_collection_cycle,
)

FAKE_ADDR = "0xaabbccdd"


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    """Use a fresh temp DB for every test."""
    db_file = str(tmp_path / "test.db")
    set_db_path(db_file)
    init_db()
    yield db_file
    close_connection()
    set_db_path(None)


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


# -----------------------------------------------------------------------
# Default Trader Seeding
# -----------------------------------------------------------------------

class TestEnsureDefaultTrader:
    def test_seeds_default_trader(self):
        _ensure_default_trader()
        traders = get_active_traders()
        assert len(traders) == 1
        assert traders[0]["alias"] == "0x8dxd"

    def test_idempotent(self):
        _ensure_default_trader()
        _ensure_default_trader()
        assert len(get_active_traders()) == 1


# -----------------------------------------------------------------------
# poll_trades
# -----------------------------------------------------------------------

class TestPollTrades:
    @patch("collector.requests.get")
    def test_inserts_buy_and_sell_trades(self, mock_get):
        mock_get.return_value = _mock_response([
            {"type": "TRADE", "side": "BUY", "transactionHash": "0xtx1",
             "title": "BTC Up", "size": 100, "price": 0.5, "timestamp": 1000},
            {"type": "TRADE", "side": "BUY", "transactionHash": "0xtx2",
             "title": "ETH Up", "size": 50, "price": 0.6, "timestamp": 1001},
            {"type": "TRADE", "side": "SELL", "transactionHash": "0xtx3",
             "title": "SOL Down", "size": 25, "price": 0.3, "timestamp": 1002},
        ])
        new_count = poll_trades(FAKE_ADDR)
        assert new_count == 3  # BUY and SELL trades
        assert get_trade_count(FAKE_ADDR) == 3

    @patch("collector.requests.get")
    def test_sell_trades_stored_with_correct_side(self, mock_get):
        mock_get.return_value = _mock_response([
            {"type": "TRADE", "side": "SELL", "transactionHash": "0xtx_sell",
             "title": "BTC Up", "size": 50, "price": 0.8, "timestamp": 2000},
        ])
        assert poll_trades(FAKE_ADDR) == 1
        trades = get_trades(FAKE_ADDR)
        assert len(trades) == 1
        assert trades[0]["side"] == "SELL"
        assert trades[0]["price"] == 0.8

    @patch("collector.requests.get")
    def test_buy_and_sell_same_market_both_stored(self, mock_get):
        mock_get.return_value = _mock_response([
            {"type": "TRADE", "side": "BUY", "transactionHash": "0xtx_buy",
             "title": "BTC Up", "size": 100, "price": 0.5, "timestamp": 1000},
            {"type": "TRADE", "side": "SELL", "transactionHash": "0xtx_sell",
             "title": "BTC Up", "size": 100, "price": 0.8, "timestamp": 2000},
        ])
        assert poll_trades(FAKE_ADDR) == 2
        trades = get_trades(FAKE_ADDR)
        sides = {t["side"] for t in trades}
        assert sides == {"BUY", "SELL"}

    @patch("collector.requests.get")
    def test_deduplicates_on_second_poll(self, mock_get):
        trades = [
            {"type": "TRADE", "side": "BUY", "transactionHash": "0xtx1",
             "title": "BTC", "size": 100, "price": 0.5, "timestamp": 1000},
        ]
        mock_get.return_value = _mock_response(trades)
        assert poll_trades(FAKE_ADDR) == 1
        assert poll_trades(FAKE_ADDR) == 0  # duplicate
        assert get_trade_count(FAKE_ADDR) == 1

    @patch("collector.requests.get")
    def test_handles_api_error(self, mock_get):
        mock_get.return_value = _mock_response([], status_code=500)
        assert poll_trades(FAKE_ADDR) == 0

    @patch("collector.requests.get")
    def test_handles_network_error(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        assert poll_trades(FAKE_ADDR) == 0

    @patch("collector.requests.get")
    def test_filters_non_trade_activities(self, mock_get):
        mock_get.return_value = _mock_response([
            {"type": "DEPOSIT", "transactionHash": "0xd1"},
            {"type": "TRADE", "side": "BUY", "transactionHash": "0xtx1",
             "title": "BTC", "size": 10, "price": 0.5, "timestamp": 1000},
        ])
        assert poll_trades(FAKE_ADDR) == 1


# -----------------------------------------------------------------------
# poll_positions
# -----------------------------------------------------------------------

class TestPollPositions:
    @patch("collector.requests.get")
    def test_inserts_positions(self, mock_get):
        mock_get.return_value = _mock_response([
            {"title": "BTC Up or Down", "outcome": "UP", "size": 100,
             "avgPrice": 0.5, "curPrice": 0.7, "cashPnl": 20},
            {"title": "ETH Up or Down", "outcome": "DOWN", "size": 50,
             "avgPrice": 0.4, "curPrice": 0.3, "cashPnl": -5},
        ])
        count = poll_positions(FAKE_ADDR)
        assert count == 2
        snapshot = get_latest_snapshot(FAKE_ADDR)
        assert len(snapshot) == 2

    @patch("collector.requests.get")
    def test_handles_api_error(self, mock_get):
        mock_get.return_value = _mock_response([], status_code=500)
        assert poll_positions(FAKE_ADDR) == 0

    @patch("collector.requests.get")
    def test_handles_empty_positions(self, mock_get):
        mock_get.return_value = _mock_response([])
        assert poll_positions(FAKE_ADDR) == 0


# -----------------------------------------------------------------------
# poll_settled
# -----------------------------------------------------------------------

class TestPollSettled:
    @patch("collector.requests.get")
    def test_inserts_settled_trades(self, mock_get):
        mock_get.return_value = _mock_response([
            {"status": "settled", "pnl": 50.0, "transactionHash": "0xs1",
             "title": "BTC", "size": 100},
            {"status": "settled", "pnl": -20.0, "transactionHash": "0xs2",
             "title": "ETH", "size": 50},
            {"status": "open", "pnl": None, "transactionHash": "0xs3",
             "title": "SOL", "size": 25},
        ])
        new_count = poll_settled(FAKE_ADDR)
        assert new_count == 2  # only settled with pnl
        assert len(get_settled_trades(FAKE_ADDR)) == 2

    @patch("collector.requests.get")
    def test_handles_no_settled(self, mock_get):
        mock_get.return_value = _mock_response([
            {"status": "open", "pnl": None, "transactionHash": "0xo1"},
        ])
        assert poll_settled(FAKE_ADDR) == 0


# -----------------------------------------------------------------------
# run_collection_cycle
# -----------------------------------------------------------------------

class TestCollectionCycle:
    @patch("collector.poll_settled")
    @patch("collector.poll_positions")
    @patch("collector.poll_trades")
    def test_polls_all_active_traders(self, mock_trades, mock_positions, mock_settled):
        mock_trades.return_value = 5
        mock_positions.return_value = 3
        mock_settled.return_value = 1

        upsert_trader("0x1111", alias="trader_a")
        upsert_trader("0x2222", alias="trader_b")

        run_collection_cycle()

        assert mock_trades.call_count == 2
        assert mock_positions.call_count == 2
        assert mock_settled.call_count == 2

        called_addrs = [call.args[0] for call in mock_trades.call_args_list]
        assert "0x1111" in called_addrs
        assert "0x2222" in called_addrs

    @patch("collector.poll_settled")
    @patch("collector.poll_positions")
    @patch("collector.poll_trades")
    def test_skips_inactive_traders(self, mock_trades, mock_positions, mock_settled):
        upsert_trader("0x1111", alias="active")
        upsert_trader("0x2222", alias="inactive")
        from utils.db import deactivate_trader
        deactivate_trader("0x2222")

        run_collection_cycle()

        assert mock_trades.call_count == 1
        assert mock_trades.call_args_list[0].args[0] == "0x1111"

    def test_handles_no_traders(self):
        """Should not error when no traders exist."""
        run_collection_cycle()  # no assert needed — just shouldn't raise
