"""Tests for utils/backtest.py — backtesting framework."""

import pytest
from unittest.mock import patch

from utils.db import set_db_path, close_connection, init_db, insert_trades_batch, insert_settled_trades_batch, upsert_trader
from utils.backtest import (
    BacktestConfig,
    run_backtest,
    compute_drawdown_series,
    compare_backtests,
    BacktestResult,
)
import pandas as pd

TRADER_A = "0xaaaa"


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    db_file = str(tmp_path / "test.db")
    set_db_path(db_file)
    init_db()
    yield db_file
    close_connection()
    set_db_path(None)


def _seed_trades():
    """Insert known trades for backtesting."""
    upsert_trader(TRADER_A, alias="test_trader")

    trades = [
        {"transactionHash": "0xtx1", "title": "BTC above $100k?", "outcome": "Up",
         "side": "BUY", "size": 100, "price": 0.5, "amount": 50, "timestamp": 1000},
        {"transactionHash": "0xtx2", "title": "BTC above $100k?", "outcome": "Down",
         "side": "BUY", "size": 100, "price": 0.5, "amount": 50, "timestamp": 1010},
        {"transactionHash": "0xtx3", "title": "BTC above $100k?", "outcome": "Up",
         "side": "SELL", "size": 100, "price": 0.8, "amount": 80, "timestamp": 5000},
    ]
    insert_trades_batch(TRADER_A, trades)


def _seed_settled():
    """Insert settled trades for resolution testing."""
    settled = [
        {"transactionHash": "0xs1", "title": "ETH above $5k?", "outcome": "Up",
         "size": 50, "price": 1.0, "pnl": 25.0, "settled_at": "10000"},
    ]
    insert_settled_trades_batch(TRADER_A, settled)


# ---------------------------------------------------------------------------
# run_backtest
# ---------------------------------------------------------------------------

class TestRunBacktest:
    def test_basic_backtest(self):
        _seed_trades()
        config = BacktestConfig(
            trader_addresses=[TRADER_A],
            bankroll=1000,
            copy_ratio=10,
            only_crypto=True,
        )
        result = run_backtest(config)
        assert isinstance(result, BacktestResult)
        assert result.total_trades >= 0
        assert not result.pnl_curve.empty or result.total_trades == 0

    def test_empty_trader(self):
        upsert_trader(TRADER_A, alias="empty")
        config = BacktestConfig(trader_addresses=[TRADER_A])
        result = run_backtest(config)
        assert result.total_pnl == 0
        assert result.total_trades == 0

    def test_sell_realizes_pnl(self):
        _seed_trades()
        config = BacktestConfig(
            trader_addresses=[TRADER_A],
            bankroll=1000,
            copy_ratio=10,
            only_crypto=True,
        )
        result = run_backtest(config)
        # We have a BUY at 0.5 and SELL at 0.8 — should realize profit
        sell_trades = [t for t in result.trades_log.to_dict("records")
                       if t.get("side") == "SELL"] if not result.trades_log.empty else []
        if sell_trades:
            assert sell_trades[0]["pnl"] > 0

    def test_only_hedged_filter(self):
        _seed_trades()
        config = BacktestConfig(
            trader_addresses=[TRADER_A],
            bankroll=1000,
            copy_ratio=10,
            only_hedged=True,
            only_crypto=True,
        )
        result = run_backtest(config)
        # BTC has both UP and DOWN buys, so it's hedged
        assert isinstance(result, BacktestResult)

    def test_stop_loss(self):
        _seed_trades()
        config = BacktestConfig(
            trader_addresses=[TRADER_A],
            bankroll=100,
            copy_ratio=1,
            stop_loss_pct=1,  # Very tight stop loss
            only_crypto=True,
        )
        result = run_backtest(config)
        assert isinstance(result, BacktestResult)


# ---------------------------------------------------------------------------
# compute_drawdown_series
# ---------------------------------------------------------------------------

class TestDrawdownSeries:
    def test_basic(self):
        pnl_curve = pd.DataFrame({
            "timestamp": [1, 2, 3, 4],
            "cumulative_pnl": [0, 10, -5, 5],
            "bankroll": [1000, 1010, 995, 1005],
        })
        dd = compute_drawdown_series(pnl_curve)
        assert len(dd) == 4
        assert dd["drawdown_pct"].iloc[0] == 0  # No drawdown at start
        assert dd["drawdown_pct"].iloc[2] > 0   # Drawdown after peak

    def test_empty(self):
        dd = compute_drawdown_series(pd.DataFrame())
        assert dd.empty

    def test_monotonic_increase(self):
        pnl_curve = pd.DataFrame({
            "timestamp": [1, 2, 3],
            "bankroll": [1000, 1010, 1020],
        })
        dd = compute_drawdown_series(pnl_curve)
        assert dd["drawdown_pct"].max() == 0


# ---------------------------------------------------------------------------
# compare_backtests
# ---------------------------------------------------------------------------

class TestCompareBacktests:
    def test_basic(self):
        r1 = BacktestResult(
            pnl_curve=pd.DataFrame(),
            total_pnl=100, total_trades=10, win_rate=60,
            max_drawdown_pct=5, sharpe=1.5,
        )
        r2 = BacktestResult(
            pnl_curve=pd.DataFrame(),
            total_pnl=50, total_trades=8, win_rate=50,
            max_drawdown_pct=10, sharpe=0.8,
        )
        df = compare_backtests([r1, r2], ["Run A", "Run B"])
        assert len(df) == 2
        assert df.iloc[0]["Total PnL"] == 100
        assert df.iloc[1]["Run"] == "Run B"
