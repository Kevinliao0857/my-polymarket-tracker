"""Tests for utils/db.py — SQLite persistence layer."""

import os
import tempfile
import pytest

from utils.db import (
    set_db_path,
    close_connection,
    init_db,
    get_connection,
    _get_schema_version,
    # Traders
    upsert_trader,
    get_active_traders,
    deactivate_trader,
    # Trades
    insert_trade,
    insert_trades_batch,
    get_trades,
    get_trade_count,
    get_all_trades,
    get_trade_summary_by_trader,
    # Position Snapshots
    insert_position_snapshot,
    get_latest_snapshot,
    get_position_history,
    # Settled Trades
    insert_settled_trade,
    insert_settled_trades_batch,
    get_settled_trades,
    get_all_settled_trades,
    get_settled_summary_by_trader,
    # Simulation Runs
    insert_simulation_run,
    get_simulation_runs,
    # Helpers
    _safe_float,
    _safe_int,
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


# -----------------------------------------------------------------------
# Schema & Migrations
# -----------------------------------------------------------------------

class TestSchema:
    def test_tables_created(self):
        conn = get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = sorted(t["name"] for t in tables)
        assert "traders" in names
        assert "trades" in names
        assert "position_snapshots" in names
        assert "settled_trades" in names
        assert "simulation_runs" in names
        assert "schema_version" in names

    def test_schema_version_is_1(self):
        conn = get_connection()
        assert _get_schema_version(conn) == 1

    def test_indexes_created(self):
        conn = get_connection()
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        ).fetchall()
        names = [i["name"] for i in indexes]
        assert "idx_trades_trader" in names
        assert "idx_trades_timestamp" in names
        assert "idx_trades_tx" in names
        assert "idx_snapshots_trader" in names
        assert "idx_settled_trader" in names
        assert "idx_simruns_trader" in names

    def test_wal_mode_enabled(self):
        conn = get_connection()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_idempotent_init(self):
        """Calling init_db twice doesn't error."""
        init_db()
        init_db()
        conn = get_connection()
        assert _get_schema_version(conn) == 1


# -----------------------------------------------------------------------
# Traders
# -----------------------------------------------------------------------

class TestTraders:
    def test_upsert_and_get(self):
        upsert_trader(FAKE_ADDR, alias="test_trader")
        traders = get_active_traders()
        assert len(traders) == 1
        assert traders[0]["trader_address"] == FAKE_ADDR.lower()
        assert traders[0]["alias"] == "test_trader"

    def test_upsert_updates_alias(self):
        upsert_trader(FAKE_ADDR, alias="old_name")
        upsert_trader(FAKE_ADDR, alias="new_name")
        traders = get_active_traders()
        assert len(traders) == 1
        assert traders[0]["alias"] == "new_name"

    def test_upsert_preserves_alias_if_none(self):
        upsert_trader(FAKE_ADDR, alias="keep_me")
        upsert_trader(FAKE_ADDR, alias=None)
        traders = get_active_traders()
        assert traders[0]["alias"] == "keep_me"

    def test_deactivate(self):
        upsert_trader(FAKE_ADDR, alias="active_trader")
        assert len(get_active_traders()) == 1
        deactivate_trader(FAKE_ADDR)
        assert len(get_active_traders()) == 0

    def test_reactivate(self):
        upsert_trader(FAKE_ADDR)
        deactivate_trader(FAKE_ADDR)
        assert len(get_active_traders()) == 0
        upsert_trader(FAKE_ADDR, active=True)
        assert len(get_active_traders()) == 1

    def test_multiple_traders(self):
        upsert_trader("0x1111", alias="trader_a")
        upsert_trader("0x2222", alias="trader_b")
        upsert_trader("0x3333", alias="trader_c")
        deactivate_trader("0x2222")
        active = get_active_traders()
        assert len(active) == 2
        addrs = {t["trader_address"] for t in active}
        assert "0x2222" not in addrs

    def test_address_lowercased(self):
        upsert_trader("0xAABBCCDD", alias="upper")
        traders = get_active_traders()
        assert traders[0]["trader_address"] == "0xaabbccdd"


# -----------------------------------------------------------------------
# Trades
# -----------------------------------------------------------------------

def _make_trade(tx_hash="0xtx1", **overrides):
    trade = {
        "transactionHash": tx_hash,
        "asset_id": "asset_123",
        "title": "BTC Up or Down",
        "outcome": "UP",
        "side": "BUY",
        "size": "100.5",
        "price": "0.65",
        "amount": "$65.33",
        "timestamp": 1700000000,
    }
    trade.update(overrides)
    return trade


class TestTrades:
    def test_insert_and_get(self):
        trade = _make_trade()
        result = insert_trade(FAKE_ADDR, trade, source="rest")
        assert result is True
        trades = get_trades(FAKE_ADDR)
        assert len(trades) == 1
        assert trades[0]["tx_hash"] == "0xtx1"
        assert trades[0]["size"] == 100.5
        assert trades[0]["price"] == 0.65
        assert trades[0]["source"] == "rest"

    def test_deduplication(self):
        trade = _make_trade()
        insert_trade(FAKE_ADDR, trade)
        insert_trade(FAKE_ADDR, trade)
        assert get_trade_count(FAKE_ADDR) == 1

    def test_batch_insert(self):
        trades = [_make_trade(f"0xtx{i}") for i in range(5)]
        new_count = insert_trades_batch(FAKE_ADDR, trades)
        assert new_count == 5
        assert get_trade_count(FAKE_ADDR) == 5

    def test_batch_dedup(self):
        trades = [_make_trade("0xtx1"), _make_trade("0xtx2")]
        insert_trades_batch(FAKE_ADDR, trades)
        # Insert again with one new
        trades2 = [_make_trade("0xtx2"), _make_trade("0xtx3")]
        new_count = insert_trades_batch(FAKE_ADDR, trades2)
        assert new_count == 1
        assert get_trade_count(FAKE_ADDR) == 3

    def test_get_trades_with_since(self):
        insert_trade(FAKE_ADDR, _make_trade("0xtx1", timestamp=1000))
        insert_trade(FAKE_ADDR, _make_trade("0xtx2", timestamp=2000))
        insert_trade(FAKE_ADDR, _make_trade("0xtx3", timestamp=3000))
        trades = get_trades(FAKE_ADDR, since_ts=2000)
        assert len(trades) == 2

    def test_get_trades_with_limit(self):
        for i in range(10):
            insert_trade(FAKE_ADDR, _make_trade(f"0xtx{i}", timestamp=1000 + i))
        trades = get_trades(FAKE_ADDR, limit=3)
        assert len(trades) == 3

    def test_different_traders_isolated(self):
        insert_trade("0x1111", _make_trade("0xtx1"))
        insert_trade("0x2222", _make_trade("0xtx2"))
        assert get_trade_count("0x1111") == 1
        assert get_trade_count("0x2222") == 1

    def test_same_tx_different_traders(self):
        """Same tx_hash for different traders should both be stored."""
        insert_trade("0x1111", _make_trade("0xtx_same"))
        insert_trade("0x2222", _make_trade("0xtx_same"))
        assert get_trade_count("0x1111") == 1
        assert get_trade_count("0x2222") == 1

    def test_synthetic_tx_hash(self):
        """Trade without transactionHash gets a synthetic key."""
        trade = {"asset_id": "abc", "timestamp": 1234, "size": 10}
        insert_trade(FAKE_ADDR, trade)
        trades = get_trades(FAKE_ADDR)
        assert len(trades) == 1
        assert trades[0]["tx_hash"].startswith("synth_")

    def test_raw_json_stored(self):
        trade = _make_trade()
        insert_trade(FAKE_ADDR, trade)
        trades = get_trades(FAKE_ADDR)
        import json
        raw = json.loads(trades[0]["raw_json"])
        assert raw["transactionHash"] == "0xtx1"

    def test_price_parsing(self):
        """Prices with $ and commas are handled."""
        trade = _make_trade(price="$1,234.56", amount="$100.00", size="50")
        insert_trade(FAKE_ADDR, trade)
        trades = get_trades(FAKE_ADDR)
        assert trades[0]["price"] == 1234.56
        assert trades[0]["amount"] == 100.0


# -----------------------------------------------------------------------
# Position Snapshots
# -----------------------------------------------------------------------

def _make_position(**overrides):
    pos = {
        "title": "ETH Up or Down",
        "outcome": "DOWN",
        "size": "200",
        "avgPrice": "0.45",
        "curPrice": "0.52",
        "cashPnl": "14.00",
    }
    pos.update(overrides)
    return pos


class TestPositionSnapshots:
    def test_insert_and_get_latest(self):
        positions = [_make_position(), _make_position(title="BTC Up or Down")]
        insert_position_snapshot(FAKE_ADDR, positions)
        latest = get_latest_snapshot(FAKE_ADDR)
        assert len(latest) == 2

    def test_latest_snapshot_only(self):
        """get_latest_snapshot returns only the most recent batch."""
        insert_position_snapshot(FAKE_ADDR, [_make_position(title="old")])
        import time
        time.sleep(1.1)  # ensure different snapshot_at
        insert_position_snapshot(FAKE_ADDR, [_make_position(title="new")])
        latest = get_latest_snapshot(FAKE_ADDR)
        assert len(latest) == 1
        assert latest[0]["title"] == "new"

    def test_empty_snapshot(self):
        assert get_latest_snapshot(FAKE_ADDR) == []

    def test_numeric_fields(self):
        insert_position_snapshot(FAKE_ADDR, [_make_position()])
        snap = get_latest_snapshot(FAKE_ADDR)[0]
        assert snap["size"] == 200.0
        assert snap["avg_price"] == 0.45
        assert snap["cur_price"] == 0.52
        assert snap["cash_pnl"] == 14.0


# -----------------------------------------------------------------------
# Settled Trades
# -----------------------------------------------------------------------

class TestSettledTrades:
    def test_insert_and_get(self):
        trade = {"transactionHash": "0xsettled1", "title": "BTC", "pnl": 50.0, "size": 100}
        assert insert_settled_trade(FAKE_ADDR, trade) is True
        settled = get_settled_trades(FAKE_ADDR)
        assert len(settled) == 1
        assert settled[0]["pnl"] == 50.0

    def test_deduplication(self):
        trade = {"transactionHash": "0xsettled1", "title": "BTC", "pnl": 50.0}
        insert_settled_trade(FAKE_ADDR, trade)
        insert_settled_trade(FAKE_ADDR, trade)
        assert len(get_settled_trades(FAKE_ADDR)) == 1

    def test_batch_insert(self):
        trades = [
            {"transactionHash": f"0xs{i}", "title": "BTC", "pnl": i * 10.0}
            for i in range(3)
        ]
        new_count = insert_settled_trades_batch(FAKE_ADDR, trades)
        assert new_count == 3
        assert len(get_settled_trades(FAKE_ADDR)) == 3


# -----------------------------------------------------------------------
# Simulation Runs
# -----------------------------------------------------------------------

class TestSimulationRuns:
    def test_insert_and_get(self):
        row_id = insert_simulation_run(
            FAKE_ADDR,
            config={"bankroll": 1000, "copy_ratio": 10},
            results={"total_cost": 500, "total_pnl": 50, "positions": 4,
                     "hedge_pairs": 2, "skipped": 1},
        )
        assert row_id > 0
        runs = get_simulation_runs(FAKE_ADDR)
        assert len(runs) == 1
        assert runs[0]["bankroll"] == 1000
        assert runs[0]["total_pnl"] == 50

    def test_null_trader(self):
        """Combined/multi-trader runs have NULL trader_address."""
        row_id = insert_simulation_run(
            None,
            config={"bankroll": 5000},
            results={"total_cost": 2000, "total_pnl": 100},
        )
        assert row_id > 0
        # Get all runs (no trader filter)
        runs = get_simulation_runs()
        assert len(runs) == 1

    def test_multiple_runs(self):
        for i in range(5):
            insert_simulation_run(
                FAKE_ADDR,
                config={"bankroll": 1000 * i},
                results={"total_pnl": i * 10},
            )
        runs = get_simulation_runs(FAKE_ADDR, limit=3)
        assert len(runs) == 3


# -----------------------------------------------------------------------
# Analytics Queries (Phase 2)
# -----------------------------------------------------------------------

class TestGetAllTrades:
    def test_all_traders(self):
        insert_trade("0x1111", {"transactionHash": "tx1", "title": "BTC", "timestamp": 100})
        insert_trade("0x2222", {"transactionHash": "tx2", "title": "ETH", "timestamp": 200})
        trades = get_all_trades()
        assert len(trades) == 2

    def test_filter_by_trader(self):
        insert_trade("0x1111", {"transactionHash": "tx1", "title": "BTC", "timestamp": 100})
        insert_trade("0x2222", {"transactionHash": "tx2", "title": "ETH", "timestamp": 200})
        trades = get_all_trades(trader_address="0x1111")
        assert len(trades) == 1
        assert trades[0]["title"] == "BTC"

    def test_filter_by_timestamp(self):
        insert_trade("0x1111", {"transactionHash": "tx1", "title": "BTC", "timestamp": 100})
        insert_trade("0x1111", {"transactionHash": "tx2", "title": "ETH", "timestamp": 200})
        trades = get_all_trades(since_ts=150)
        assert len(trades) == 1

    def test_empty(self):
        assert get_all_trades() == []


class TestGetTradeSummary:
    def test_basic(self):
        insert_trade("0x1111", {"transactionHash": "tx1", "timestamp": 100})
        insert_trade("0x1111", {"transactionHash": "tx2", "timestamp": 200})
        insert_trade("0x2222", {"transactionHash": "tx3", "timestamp": 300})
        summary = get_trade_summary_by_trader()
        assert len(summary) == 2
        for s in summary:
            if s["trader_address"] == "0x1111":
                assert s["trade_count"] == 2
                assert s["first_trade"] == 100
                assert s["last_trade"] == 200

    def test_empty(self):
        assert get_trade_summary_by_trader() == []


class TestGetAllSettledTrades:
    def test_all_traders(self):
        insert_settled_trade("0x1111", {"transactionHash": "s1", "pnl": 10})
        insert_settled_trade("0x2222", {"transactionHash": "s2", "pnl": -5})
        trades = get_all_settled_trades()
        assert len(trades) == 2

    def test_filter_by_trader(self):
        insert_settled_trade("0x1111", {"transactionHash": "s1", "pnl": 10})
        insert_settled_trade("0x2222", {"transactionHash": "s2", "pnl": -5})
        trades = get_all_settled_trades(trader_address="0x1111")
        assert len(trades) == 1

    def test_empty(self):
        assert get_all_settled_trades() == []


class TestGetSettledSummary:
    def test_basic(self):
        insert_settled_trade("0x1111", {"transactionHash": "s1", "pnl": 10})
        insert_settled_trade("0x1111", {"transactionHash": "s2", "pnl": -5})
        insert_settled_trade("0x2222", {"transactionHash": "s3", "pnl": 20})
        summary = get_settled_summary_by_trader()
        assert len(summary) == 2
        for s in summary:
            if s["trader_address"] == "0x1111":
                assert s["count"] == 2
                assert s["total_pnl"] == 5
                assert s["wins"] == 1

    def test_empty(self):
        assert get_settled_summary_by_trader() == []


class TestGetPositionHistory:
    def test_returns_all_snapshots(self):
        insert_position_snapshot("0x1111", [
            {"title": "BTC", "outcome": "UP", "size": 100, "avgPrice": 0.5,
             "curPrice": 0.6, "cashPnl": 10},
        ])
        insert_position_snapshot("0x1111", [
            {"title": "BTC", "outcome": "UP", "size": 100, "avgPrice": 0.5,
             "curPrice": 0.7, "cashPnl": 20},
        ])
        history = get_position_history("0x1111")
        assert len(history) == 2

    def test_filter_by_title(self):
        insert_position_snapshot("0x1111", [
            {"title": "BTC", "outcome": "UP", "size": 100},
            {"title": "ETH", "outcome": "UP", "size": 50},
        ])
        history = get_position_history("0x1111", title="BTC")
        assert len(history) == 1

    def test_empty(self):
        assert get_position_history("0x1111") == []


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

class TestHelpers:
    def test_safe_float(self):
        assert _safe_float("1.5") == 1.5
        assert _safe_float("$1,234.56") == 1234.56
        assert _safe_float(42) == 42.0
        assert _safe_float(None) is None
        assert _safe_float("not a number") is None
        assert _safe_float("") is None

    def test_safe_int(self):
        assert _safe_int("100") == 100
        assert _safe_int(100.7) == 100
        assert _safe_int("1700000000.0") == 1700000000
        assert _safe_int(None) is None
        assert _safe_int("nope") is None
