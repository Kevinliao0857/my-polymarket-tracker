#!/usr/bin/env python3
"""Background data collector — runs independently of Streamlit."""

import logging
import signal
import time

import requests

from utils.config import TRADER, POLL_INTERVAL
from utils.db import (
    get_active_traders,
    insert_position_snapshot,
    insert_settled_trades_batch,
    insert_trades_batch,
    upsert_trader,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [collector] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    log.info("Received signal %s, shutting down gracefully...", signum)
    _shutdown = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def _ensure_default_trader():
    """Seed the traders table with the hardcoded trader on first run."""
    upsert_trader(TRADER, alias="0x8dxd")


def poll_trades(address: str) -> int:
    """Fetch recent trades and persist. Returns count of new trades."""
    try:
        resp = requests.get(
            f"https://data-api.polymarket.com/activity?user={address}&limit=500",
            timeout=15,
        )
        if resp.status_code != 200:
            log.warning("trades API returned %s for %s", resp.status_code, address[:10])
            return 0
        activities = resp.json()
        buy_trades = [
            a for a in activities if a.get("type") == "TRADE" and a.get("side") == "BUY"
        ]
        return insert_trades_batch(address, buy_trades, source="rest")
    except Exception as e:
        log.error("poll_trades error for %s: %s", address[:10], e)
        return 0


def poll_positions(address: str) -> int:
    """Fetch open positions and persist a snapshot. Returns position count."""
    try:
        resp = requests.get(
            f"https://data-api.polymarket.com/positions?user={address}&sizeThreshold=0",
            timeout=15,
        )
        if resp.status_code != 200:
            return 0
        positions = resp.json()
        insert_position_snapshot(address, positions)
        return len(positions)
    except Exception as e:
        log.error("poll_positions error for %s: %s", address[:10], e)
        return 0


def poll_settled(address: str) -> int:
    """Fetch trades and persist settled ones. Returns count of new settled."""
    try:
        resp = requests.get(
            f"https://data-api.polymarket.com/trades?user={address}&limit=1000",
            timeout=15,
        )
        if resp.status_code != 200:
            return 0
        trades = resp.json()
        settled = [
            t for t in trades if t.get("status") == "settled" and t.get("pnl") is not None
        ]
        return insert_settled_trades_batch(address, settled)
    except Exception as e:
        log.error("poll_settled error for %s: %s", address[:10], e)
        return 0


def run_collection_cycle():
    """One full cycle: loop over all active traders, poll everything."""
    traders = get_active_traders()
    if not traders:
        log.warning("No active traders in DB")
        return

    for trader in traders:
        addr = trader["trader_address"]
        alias = trader.get("alias") or addr[:10]

        new_trades = poll_trades(addr)
        pos_count = poll_positions(addr)
        new_settled = poll_settled(addr)

        log.info(
            "[%s] +%d trades, %d positions, +%d settled",
            alias, new_trades, pos_count, new_settled,
        )

        if _shutdown:
            return


def main():
    log.info("Collector starting (poll interval: %ds)...", POLL_INTERVAL)
    _ensure_default_trader()

    cycle = 0
    while not _shutdown:
        cycle += 1
        log.info("--- Cycle %d ---", cycle)
        try:
            run_collection_cycle()
        except Exception as e:
            log.error("Cycle %d failed: %s", cycle, e)

        # Sleep in small increments for responsive shutdown
        for _ in range(POLL_INTERVAL):
            if _shutdown:
                break
            time.sleep(1)

    log.info("Collector stopped.")


if __name__ == "__main__":
    main()
