import websocket
import threading
import time
import json
from typing import List, Dict
from collections import deque
from .data import safe_fetch
from .config import TRADER

live_trades: deque = deque(maxlen=5000)
_live_lock = threading.Lock()  # ✅ Thread-safe reads


def rtds_listener():
    """Bulletproof WS listener with non-blocking title resolution"""
    reconnect_delay = 1
    ping_interval = 10
    ws_base_url = "wss://ws-subscriptions-clob.polymarket.com"

    # ✅ Title cache avoids repeated HTTP lookups per asset
    _title_cache: Dict[str, str] = {}

    def resolve_title_async(asset_id: str, trade_data: dict):
        """Fetch title in background thread so WS message loop never blocks"""
        def _fetch():
            if asset_id in _title_cache:
                trade_data['title'] = _title_cache[asset_id]
                return
            market_info = safe_fetch(
                f"https://gamma-api.polymarket.com/markets?tokenIds={asset_id}"
            )
            if market_info:
                title = market_info[0].get('question', '')
                _title_cache[asset_id] = title
                trade_data['title'] = title or trade_data['title']
        threading.Thread(target=_fetch, daemon=True).start()

    def process_trade(raw_data):
        try:
            if isinstance(raw_data, str) and raw_data.strip() == "ping":
                return
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            if not isinstance(data, dict):
                return
            event_type = data.get('event_type', 'unknown')
            if event_type not in ('trade', 'last_trade_price'):
                return

            size = float(data.get('size') or data.get('amount') or 0)
            price = float(data.get('price') or 0)
            asset_id = str(
                data.get('asset_id') or data.get('asset') or data.get('assetId') or 'N/A'
            )
            title = data.get('question') or _title_cache.get(asset_id, '')

            trade_data = {
                'event_type': event_type,
                'asset_id': asset_id,
                'size': size,
                'price': price,
                'timestamp': time.time(),
                'title': title or f"Asset {asset_id[:12]}...",
                'proxyWallet': TRADER,
            }

            # ✅ Resolve title without blocking message loop
            if not title and asset_id != 'N/A':
                resolve_title_async(asset_id, trade_data)

            with _live_lock:
                live_trades.append(trade_data)

            try:
                from .db import insert_trade
                insert_trade(TRADER, trade_data, source='ws')
            except Exception:
                pass

        except Exception as e:
            print(f"⚠️ process_trade error: {e} | input: {str(raw_data)[:50]}")

    def on_message(ws, msg):
        process_trade(msg)

    def on_open(ws):
        def send_subscribe():
            recent_trades = safe_fetch(
                f"https://data-api.polymarket.com/trades?user={TRADER}&limit=200"
            )
            assets = list({
                item.get('asset') for item in recent_trades if item.get('asset')
            })[:20]

            if not assets:
                popular = safe_fetch(
                    "https://gamma-api.polymarket.com/markets?active=true&category=crypto&limit=20"
                )
                assets = [
                    (m.get('tokens') or [{}])[0].get('id') or
                    (m.get('tokens') or [{}])[0].get('token_id')
                    for m in (popular or [])
                    if m.get('tokens')
                ][:20]
                assets = [a for a in assets if a]  # drop None

            if assets:
                ws.send(json.dumps({"type": "market", "assets_ids": assets}))
                print(f"🚀 Subscribed to {len(assets)} assets")

        send_subscribe()

        def ping_loop():
            while ws.sock and ws.sock.connected:
                try:
                    ws.send("ping")
                except Exception:
                    break
                time.sleep(ping_interval)

        threading.Thread(target=ping_loop, daemon=True).start()

    def on_error(ws, error):
        nonlocal reconnect_delay
        print(f"❌ WS error: {error} (retry in {reconnect_delay}s)")
        time.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, 60)

    def on_close(ws, code, reason):
        print(f"🔌 WS closed: {code} - {reason}")

    while True:
        try:
            ws = websocket.WebSocketApp(
                f"{ws_base_url}/ws/market",
                on_message=on_message,
                on_open=on_open,
                on_error=on_error,
                on_close=on_close,
            )
            ws.run_forever(ping_interval=0, ping_timeout=None)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Run error: {e}")
            time.sleep(reconnect_delay)


def get_recent_live_trades(minutes: int = 30) -> List[Dict]:
    cutoff = time.time() - minutes * 60
    with _live_lock:  # ✅ Thread-safe snapshot
        return [t for t in live_trades if t.get('timestamp', 0) > cutoff]


def get_live_trades_count() -> int:
    with _live_lock:
        return len(live_trades)


def get_recent_trader_trades(seconds: int = 300) -> list:
    """Legacy compatibility for simulator.py"""
    cutoff = time.time() - seconds
    with _live_lock:
        return [
            t for t in live_trades
            if t.get('proxyWallet') == TRADER and t.get('timestamp', 0) > cutoff
        ]


if __name__ == "__main__":
    print("🚀 Starting Polymarket RTDS listener...")
    rtds_listener()
