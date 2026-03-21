"""
SQLite persistence layer for the Polymarket tracker.

Thread-safe (one connection per thread via threading.local()),
WAL mode for concurrent reads + writes.
"""

import json
import os
import sqlite3
import threading

from .config import DB_PATH as _DEFAULT_DB_PATH

_local = threading.local()
_db_path_override = None


def set_db_path(path: str) -> None:
    """Override DB path (used by tests). Must be called before any DB access."""
    global _db_path_override
    _db_path_override = path


def _get_db_path() -> str:
    return _db_path_override or _DEFAULT_DB_PATH

# ---------------------------------------------------------------------------
# Schema migrations
# ---------------------------------------------------------------------------

MIGRATIONS = {
    1: [
        """CREATE TABLE IF NOT EXISTS schema_version (
            version    INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS traders (
            trader_address TEXT PRIMARY KEY,
            alias          TEXT,
            added_at       TEXT NOT NULL DEFAULT (datetime('now')),
            active         INTEGER NOT NULL DEFAULT 1
        )""",
        """CREATE TABLE IF NOT EXISTS trades (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            trader_address TEXT NOT NULL,
            tx_hash        TEXT NOT NULL,
            asset_id       TEXT,
            title          TEXT,
            outcome        TEXT,
            side           TEXT,
            size           REAL,
            price          REAL,
            amount         REAL,
            timestamp      INTEGER,
            source         TEXT NOT NULL DEFAULT 'rest',
            raw_json       TEXT,
            created_at     TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(trader_address, tx_hash)
        )""",
        """CREATE TABLE IF NOT EXISTS position_snapshots (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            trader_address TEXT NOT NULL,
            snapshot_at    TEXT NOT NULL DEFAULT (datetime('now')),
            title          TEXT,
            outcome        TEXT,
            size           REAL,
            avg_price      REAL,
            cur_price      REAL,
            cash_pnl       REAL,
            raw_json       TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS settled_trades (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            trader_address TEXT NOT NULL,
            tx_hash        TEXT,
            title          TEXT,
            outcome        TEXT,
            size           REAL,
            price          REAL,
            pnl            REAL,
            settled_at     TEXT,
            raw_json       TEXT,
            created_at     TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(trader_address, tx_hash)
        )""",
        """CREATE TABLE IF NOT EXISTS simulation_runs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            trader_address TEXT,
            run_at         TEXT NOT NULL DEFAULT (datetime('now')),
            bankroll       REAL,
            copy_ratio     REAL,
            total_cost     REAL,
            total_pnl      REAL,
            positions      INTEGER,
            hedge_pairs    INTEGER,
            skipped        INTEGER,
            config_json    TEXT,
            results_json   TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_trades_trader ON trades(trader_address)",
        "CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(trader_address, timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_trades_tx ON trades(tx_hash)",
        "CREATE INDEX IF NOT EXISTS idx_snapshots_trader ON position_snapshots(trader_address, snapshot_at)",
        "CREATE INDEX IF NOT EXISTS idx_settled_trader ON settled_trades(trader_address)",
        "CREATE INDEX IF NOT EXISTS idx_simruns_trader ON simulation_runs(trader_address)",
    ],
}

# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    """Return a thread-local connection, creating DB + schema on first call."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        _ensure_data_dir()
        conn = sqlite3.connect(_get_db_path(), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        _local.conn = conn
        _apply_migrations(conn)
    return conn


def close_connection() -> None:
    """Close the thread-local connection (for cleanup)."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def init_db() -> None:
    """Explicitly initialize the DB (creates tables if needed)."""
    get_connection()


def _ensure_data_dir() -> None:
    db_dir = os.path.dirname(_get_db_path())
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

def _get_schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        return row[0] or 0
    except sqlite3.OperationalError:
        return 0


def _apply_migrations(conn: sqlite3.Connection) -> None:
    current = _get_schema_version(conn)
    for version in sorted(MIGRATIONS.keys()):
        if version <= current:
            continue
        for sql in MIGRATIONS[version]:
            conn.execute(sql)
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)", (version,)
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Traders
# ---------------------------------------------------------------------------

def upsert_trader(address: str, alias: str = None, active: bool = True) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT INTO traders (trader_address, alias, active)
           VALUES (?, ?, ?)
           ON CONFLICT(trader_address) DO UPDATE SET
               alias = COALESCE(excluded.alias, traders.alias),
               active = excluded.active""",
        (address.lower(), alias, int(active)),
    )
    conn.commit()


def get_active_traders() -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT trader_address, alias, added_at FROM traders WHERE active = 1"
    ).fetchall()
    return [dict(r) for r in rows]


def deactivate_trader(address: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE traders SET active = 0 WHERE trader_address = ?",
        (address.lower(),),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

def _extract_tx_hash(trade: dict) -> str:
    """Extract or synthesize a unique key for a trade."""
    tx = trade.get("transactionHash") or trade.get("tx_hash")
    if tx:
        return tx
    # Fallback: synthesize from available fields
    asset_id = trade.get("asset_id") or trade.get("assetId") or ""
    ts = trade.get("timestamp") or trade.get("time") or ""
    size = trade.get("size") or trade.get("amount") or ""
    return f"synth_{asset_id}_{ts}_{size}"


def insert_trade(trader_address: str, trade: dict, source: str = "rest") -> bool:
    """Insert a single trade. Returns True if new (not duplicate)."""
    conn = get_connection()
    tx_hash = _extract_tx_hash(trade)
    try:
        conn.execute(
            """INSERT OR IGNORE INTO trades
               (trader_address, tx_hash, asset_id, title, outcome, side,
                size, price, amount, timestamp, source, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trader_address.lower(),
                tx_hash,
                trade.get("asset_id") or trade.get("assetId"),
                trade.get("title"),
                trade.get("outcome"),
                trade.get("side"),
                _safe_float(trade.get("size")),
                _safe_float(trade.get("price")),
                _safe_float(trade.get("amount")),
                _safe_int(trade.get("timestamp")),
                source,
                json.dumps(trade, default=str),
            ),
        )
        conn.commit()
        return conn.total_changes > 0
    except sqlite3.Error:
        return False


def insert_trades_batch(
    trader_address: str, trades: list, source: str = "rest"
) -> int:
    """Batch insert trades. Returns count of newly inserted rows."""
    conn = get_connection()
    addr = trader_address.lower()
    new_count = 0
    for trade in trades:
        tx_hash = _extract_tx_hash(trade)
        try:
            cur = conn.execute(
                """INSERT OR IGNORE INTO trades
                   (trader_address, tx_hash, asset_id, title, outcome, side,
                    size, price, amount, timestamp, source, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    addr,
                    tx_hash,
                    trade.get("asset_id") or trade.get("assetId"),
                    trade.get("title"),
                    trade.get("outcome"),
                    trade.get("side"),
                    _safe_float(trade.get("size")),
                    _safe_float(trade.get("price")),
                    _safe_float(trade.get("amount")),
                    _safe_int(trade.get("timestamp")),
                    source,
                    json.dumps(trade, default=str),
                ),
            )
            if cur.rowcount > 0:
                new_count += 1
        except sqlite3.Error:
            continue
    conn.commit()
    return new_count


def get_trades(
    trader_address: str, since_ts: int = None, limit: int = 500
) -> list:
    conn = get_connection()
    if since_ts is not None:
        rows = conn.execute(
            """SELECT * FROM trades
               WHERE trader_address = ? AND timestamp >= ?
               ORDER BY timestamp DESC LIMIT ?""",
            (trader_address.lower(), since_ts, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM trades
               WHERE trader_address = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (trader_address.lower(), limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_trade_count(trader_address: str) -> int:
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE trader_address = ?",
        (trader_address.lower(),),
    ).fetchone()
    return row[0]


# ---------------------------------------------------------------------------
# Position Snapshots
# ---------------------------------------------------------------------------

def insert_position_snapshot(trader_address: str, positions: list) -> None:
    """Insert a batch of position rows as one snapshot (same snapshot_at)."""
    conn = get_connection()
    addr = trader_address.lower()
    for pos in positions:
        try:
            conn.execute(
                """INSERT INTO position_snapshots
                   (trader_address, title, outcome, size, avg_price,
                    cur_price, cash_pnl, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    addr,
                    pos.get("title"),
                    pos.get("outcome"),
                    _safe_float(pos.get("size")),
                    _safe_float(pos.get("avgPrice") or pos.get("avg_price")),
                    _safe_float(pos.get("curPrice") or pos.get("cur_price")),
                    _safe_float(pos.get("cashPnl") or pos.get("pnl")),
                    json.dumps(pos, default=str),
                ),
            )
        except sqlite3.Error:
            continue
    conn.commit()


def get_latest_snapshot(trader_address: str) -> list:
    conn = get_connection()
    # Get the most recent snapshot_at for this trader
    row = conn.execute(
        """SELECT MAX(snapshot_at) FROM position_snapshots
           WHERE trader_address = ?""",
        (trader_address.lower(),),
    ).fetchone()
    if not row or not row[0]:
        return []
    rows = conn.execute(
        """SELECT * FROM position_snapshots
           WHERE trader_address = ? AND snapshot_at = ?""",
        (trader_address.lower(), row[0]),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Settled Trades
# ---------------------------------------------------------------------------

def insert_settled_trade(trader_address: str, trade: dict) -> bool:
    conn = get_connection()
    tx_hash = _extract_tx_hash(trade)
    try:
        cur = conn.execute(
            """INSERT OR IGNORE INTO settled_trades
               (trader_address, tx_hash, title, outcome, size, price,
                pnl, settled_at, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trader_address.lower(),
                tx_hash,
                trade.get("title"),
                trade.get("outcome"),
                _safe_float(trade.get("size")),
                _safe_float(trade.get("price")),
                _safe_float(trade.get("pnl")),
                trade.get("settled_at") or trade.get("timestamp"),
                json.dumps(trade, default=str),
            ),
        )
        conn.commit()
        return cur.rowcount > 0
    except sqlite3.Error:
        return False


def insert_settled_trades_batch(trader_address: str, trades: list) -> int:
    conn = get_connection()
    addr = trader_address.lower()
    new_count = 0
    for trade in trades:
        tx_hash = _extract_tx_hash(trade)
        try:
            cur = conn.execute(
                """INSERT OR IGNORE INTO settled_trades
                   (trader_address, tx_hash, title, outcome, size, price,
                    pnl, settled_at, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    addr,
                    tx_hash,
                    trade.get("title"),
                    trade.get("outcome"),
                    _safe_float(trade.get("size")),
                    _safe_float(trade.get("price")),
                    _safe_float(trade.get("pnl")),
                    trade.get("settled_at") or trade.get("timestamp"),
                    json.dumps(trade, default=str),
                ),
            )
            if cur.rowcount > 0:
                new_count += 1
        except sqlite3.Error:
            continue
    conn.commit()
    return new_count


def get_settled_trades(trader_address: str, limit: int = 500) -> list:
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM settled_trades
           WHERE trader_address = ?
           ORDER BY created_at DESC LIMIT ?""",
        (trader_address.lower(), limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Simulation Runs
# ---------------------------------------------------------------------------

def insert_simulation_run(
    trader_address: str, config: dict, results: dict
) -> int:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO simulation_runs
           (trader_address, bankroll, copy_ratio, total_cost, total_pnl,
            positions, hedge_pairs, skipped, config_json, results_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            trader_address.lower() if trader_address else None,
            config.get("bankroll"),
            config.get("copy_ratio"),
            results.get("total_cost"),
            results.get("total_pnl"),
            results.get("positions"),
            results.get("hedge_pairs"),
            results.get("skipped"),
            json.dumps(config, default=str),
            json.dumps(results, default=str),
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_simulation_runs(trader_address: str = None, limit: int = 20) -> list:
    conn = get_connection()
    if trader_address:
        rows = conn.execute(
            """SELECT * FROM simulation_runs
               WHERE trader_address = ?
               ORDER BY run_at DESC LIMIT ?""",
            (trader_address.lower(), limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM simulation_runs ORDER BY run_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        if isinstance(val, str):
            val = val.replace("$", "").replace(",", "").strip()
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None
