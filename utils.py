import re
from datetime import datetime
import pytz

est = pytz.timezone('US/Eastern')

def is_crypto(item):
    title = str(item.get('title') or item.get('question') or '').lower()
    tickers = ['btc', 'eth', 'sol', 'xrp', 'ada', 'doge', 'shib', 'link', 'avax', 'matic', 'dot', 'uni', 'bnb', 'usdt', 'usdc']
    full_names = ['bitcoin', 'ethereum', 'solana', 'ripple', 'xrp', 'cardano', 'dogecoin', 'shiba', 'chainlink', 'avalanche', 'polygon', 'polkadot', 'uniswap', 'binance coin']
    return any(t in title for t in tickers) or any(f in title for f in full_names)

def get_up_down(item):
    # Your full logic here
    return "🟢 UP"  # etc.

def get_status(item, now_ts):
    # Your full logic here (uses est)
    return "🟢 ACTIVE (no timer)"
