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
    """🆕 Fixed WS listener with pings, server pongs, and real asset IDs."""
    reconnect_delay = 1
    ping_interval = 10  # Seconds
    ws_base_url = "wss://ws-subscriptions-clob.polymarket.com"

    while True:  # Reconnect loop
        # 🆕 Extract unique asset IDs from recent trades (REST uses 'asset')
        recent_trades = safe_fetch(f"https://data-api.polymarket.com/trades?user={TRADER}&limit=200")
        assets = list(set(item.get('asset') for item in recent_trades if item.get('asset')))[:20]
        
        # 🆕 Fallback: Fetch active crypto markets if no trader assets
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

        def on_message(ws, msg):
            if msg.strip() == "ping":
                ws.send("PING")
                print("🏓 PONG")
                return
            
            try:
                data = json.loads(msg)
                event_type = data.get('event_type', 'unknown')
                asset_id = data.get('asset_id') or data.get('asset') or 'N/A'
                size = (data.get('size') or 
                        data.get('price', {}).get('value', 0) or 
                        data.get('price', 0) or 0)
                print(f"🧑‍💻 EVENT: {event_type} | Asset: {asset_id} | Size/Price: {size}")
                
                # 🆕 Handle only trades/last_trade_price + robust size
                if event_type not in ('trade', 'last_trade_price'):
                    return
                
                trade_data = data
                trade_data['proxyWallet'] = TRADER
                trade_data['title'] = data.get('question', data.get('market', {}).get('question', 'Market Trade'))
                ts = trade_data.get('timestamp') or time.time()
                live_trades.append(trade_data)
                print(f"✅ ADDED #{len(live_trades)}")
            except Exception as e:
                print(f"❌ Parse: {e}")
        
        def on_open(ws):
            ws.send(json.dumps({"type": "market", "assets_ids": assets}))
            print(f"📡 SUBSCRIBED to {len(assets)} assets")
            # 🆕 Ping thread (sends "PING")
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

        ws_url = f"{ws_base_url}/ws/market"
        ws = websocket.WebSocketApp(ws_url, 
                                    on_message=on_message, 
                                    on_open=on_open,
                                    on_error=on_error, 
                                    on_close=on_close)
        try:
            ws.run_forever(ping_interval=0, ping_timeout=None)  # 🆕 No auto-ping
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Run error: {e}")
            time.sleep(reconnect_delay)
