import websocket
import threading
import time
import json
from typing import List, Dict, Any
from collections import deque
from .data import safe_fetch
from .config import TRADER

live_trades: deque = deque(maxlen=2000)

def rtds_listener():
    """🆕 BULLETPROOF WS listener - handles raw strings + fixes assets scope."""
    reconnect_delay = 1
    ping_interval = 10
    ws_base_url = "wss://ws-subscriptions-clob.polymarket.com"

    def process_trade(raw_data):  # 🆕 Bulletproof: handles str OR dict
        """Parse single trade safely - auto-handles strings."""
        try:
            # 🆕 FORCE PARSE strings
            if isinstance(raw_data, str):
                data = json.loads(raw_data)
            else:
                data = raw_data

            if not isinstance(data, dict):
                print(f"⚠️ SKIP: Not dict: {type(data)}")
                return

            event_type = data.get('event_type', 'unknown')
            if event_type not in ('trade', 'last_trade_price'):
                return  # Skip non-trades

            size = (
                data.get('size') or 
                data.get('amount') or 
                data.get('sizeMatched') or 0
            )
            price = (
                data.get('price') or 
                data.get('last_price') or 
                data.get('price', {}).get('value') or 0
            )
            asset_id = (
                data.get('asset_id') or 
                data.get('asset') or 
                data.get('assetId') or 'N/A'
            )

            print(f"🧑‍💻 TRADE: {event_type} | Asset: {asset_id[:16]}... | Size: {size} | Price: {price}")

            trade_data = {
                'event_type': event_type,
                'asset_id': asset_id,
                'size': size,
                'price': price,
                'timestamp': data.get('timestamp', time.time()),
                'market': data.get('market'),
                'proxyWallet': TRADER,
                'title': (
                    data.get('question') or 
                    data.get('market', {}).get('question', f"Asset {asset_id[:16]} Trade")
                ),
            }

            live_trades.append(trade_data)
            print(f"✅ TRADE ADDED #{len(live_trades)} | Size: {size} Price: ${price:.3f}")

        except Exception as e:
            print(f"⚠️ process_trade failed: {e} | Type: {type(raw_data)}")

    def on_message(ws, msg):
        if msg.strip() == "ping":
            ws.send("PING")
            print("🏓 PONG")
            return
        process_trade(msg)  # 🆕 Single bulletproof call

    def on_open(ws):
        # 🆕 assets now guaranteed to exist (moved scope)
        ws.send(json.dumps({"type": "market", "assets_ids": assets}))
        print(f"📡 SUBSCRIBED to {len(assets)} assets")

        def ping_loop():
            while ws.sock and ws.sock.connected:
                try:
                    ws.send("PING")
                    print("🏓 PING")
                except:
                    break
                time.sleep(ping_interval)
        threading.Thread(target=ping_loop, daemon=True).start()

    def on_error(ws, error):
        nonlocal reconnect_delay
        print(f"❌ ERROR: {error} (retry in {reconnect_delay}s)")
        time.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, 60)

    def on_close(ws, code, reason):
        print(f"🔌 CLOSED: {code} - {reason}")

    while True:  # Reconnect loop
        # 🆕 Get assets FIRST
        recent_trades = safe_fetch(f"https://data-api.polymarket.com/trades?user={TRADER}&limit=200")
        assets = list(set(item.get('asset') for item in recent_trades if item.get('asset')))[:20]

        if not assets:
            print("⚠️ No trader assets—fetching popular crypto...")
            popular = safe_fetch("https://gamma-api.polymarket.com/markets?active=true&category=crypto&limit=20")
            assets = []
            for m in popular:
                tokens = m.get('tokens', [])
                if tokens:
                    assets.append(tokens[0].get('id') or tokens[0].get('token_id'))
            assets = assets[:20]

        print(f"🚀 ASSETS ({len(assets)}): {assets[:3] if assets else 'NONE'}...")

        if not assets:
            print("⚠️ No assets—retry in 30s")
            time.sleep(30)
            continue

        # 🆕 Now assets exists in scope for on_open()
        ws_url = f"{ws_base_url}/ws/market"
        ws = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_open=on_open,
            on_error=on_error,
            on_close=on_close,
        )

        try:
            ws.run_forever(ping_interval=0, ping_timeout=None)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Run error: {e}")
            time.sleep(reconnect_delay)
