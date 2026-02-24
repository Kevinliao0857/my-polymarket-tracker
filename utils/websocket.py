import websocket
import threading
import time
import json
from typing import List, Dict, Any
from collections import deque
from .data import safe_fetch
from .config import TRADER

# Global live trades buffer - accessible everywhere
live_trades: deque = deque(maxlen=5000)

def rtds_listener():
    """🆕 BULLETPROOF WS listener - handles raw strings + fixes assets scope."""
    reconnect_delay = 1
    ping_interval = 10
    ws_base_url = "wss://ws-subscriptions-clob.polymarket.com"

    def process_trade(raw_data):
        """🛡️ 100% CRASH-PROOF - handles malformed data."""
        try:
            # print(f"📥 RAW TYPE: {type(raw_data)} | LEN: {len(str(raw_data))}")

            # Handle ping
            if isinstance(raw_data, str) and raw_data.strip() == "ping":
                return

            # Try JSON parse FIRST
            if isinstance(raw_data, str):
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    print(f"⚠️ BAD JSON: {raw_data[:100]}...")
                    return
            else:
                data = raw_data

            # Must be dict
            if not isinstance(data, dict):
                print(f"⚠️ Not dict: {type(data)}")
                return

            # Trade check
            event_type = data.get('event_type', 'unknown')
            if event_type not in ('trade', 'last_trade_price'):
                return

            # Extract (safe)
            size = data.get('size') or data.get('amount') or 0
            price = data.get('price') or 0  
            asset_id = data.get('asset_id') or data.get('asset') or data.get('assetId') or 'N/A'

            # PRINT FIRST (before any complex logic)
            print(f"🧑‍💻 TRADE: {event_type} | Asset: {asset_id[:16]}... | Size: {size} | Price: {price}")

            # Build & append - FIXED VERSION
            title = data.get('question') or ''  # 👈 Start with question
            
            # Quick asset lookup ONLY if no question
            if not title and asset_id != 'N/A':
                market_info = safe_fetch(f"https://gamma-api.polymarket.com/markets?tokenIds={asset_id}")
                if market_info and isinstance(market_info, list) and market_info:
                    title = market_info[0].get('question', title)
            
            trade_data = {
                'event_type': event_type, 
                'asset_id': asset_id, 
                'size': float(size),
                'price': float(price), 
                'timestamp': time.time(),
                'title': title or f"Asset {asset_id[:12]}...",  # 👈 Full title or fallback
                'proxyWallet': TRADER  # 👈 Bonus: easier filtering
            }
            live_trades.append(trade_data)
            print(f"✅ ADDED #{len(live_trades)} | Title: {trade_data['title'][:50]}...")

        except Exception as e:
            print(f"⚠️ process_trade CRASH: {e} | INPUT: {str(raw_data)[:50]}...")
            # STILL WORKS - just logs


    def on_message(ws, msg):
        process_trade(msg)

    def on_open(ws):
        def send_subscribe():
            recent_trades = safe_fetch(f"https://data-api.polymarket.com/trades?user={TRADER}&limit=200")
            assets = list(set(item.get('asset') for item in recent_trades if item.get('asset')))[:20]

            if not assets:
                print("⚠️ No trader assets—fetching popular crypto...")
                popular = safe_fetch("https://gamma-api.polymarket.com/markets?active=true&category=crypto&limit=20")
                assets = []
                for m in popular or []:
                    tokens = m.get('tokens', [])
                    if tokens:
                        assets.append(tokens[0].get('id') or tokens[0].get('token_id'))
                assets = assets[:20]

            print(f"🚀 SUBSCRIBED to {len(assets)} assets: {assets[:3] if assets else 'NONE'}...")
            
            if assets:
                subscribe_msg = {
                    "type": "market",
                    "assets_ids": assets
                }
                ws.send(json.dumps(subscribe_msg))

        send_subscribe()

        def ping_loop():
            while ws.sock and ws.sock.connected:
                try:
                    ws.send("ping")
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

    while True:
        try:
            ws_url = f"{ws_base_url}/ws/market"
            ws = websocket.WebSocketApp(
                ws_url,
                on_message=on_message,
                on_open=on_open,
                on_error=on_error,
                on_close=on_close,
            )
            ws.run_forever(ping_interval=0, ping_timeout=None)
        except KeyboardInterrupt:
            print("🛑 Listener stopped by user")
            break
        except Exception as e:
            print(f"❌ Run error: {e}")
            time.sleep(reconnect_delay)

# Convenience functions
def get_recent_trader_trades(seconds: int = 300) -> list:
    cutoff = time.time() - seconds
    return [t for t in live_trades if t.get('proxyWallet') == TRADER and t['timestamp'] > cutoff]

def get_live_trades_count() -> int:
    return len(live_trades)

if __name__ == "__main__":
    print("🚀 Starting Polymarket RTDS listener...")
    rtds_listener()
