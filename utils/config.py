import os
import pytz
from dotenv import load_dotenv

load_dotenv()

# Database
DB_PATH = os.getenv("TRACKER_DB_PATH", "data/tracker.db")

# Trader address (default; multi-trader uses DB registry)
TRADER = os.getenv("TRADER_ADDRESS", "0x63ce342161250d705dc0b16df89036c8e5f9ba9a").lower()

# Collector
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "3"))

# Crypto tickers and names
TICKERS = ['btc', 'eth', 'sol', 'xrp', 'ada', 'doge', 'shib', 'link', 'avax', 'matic', 'dot', 'uni', 'bnb', 'usdt', 'usdc']
FULL_NAMES = ['bitcoin', 'ethereum', 'solana', 'ripple', 'xrp', 'cardano', 'dogecoin', 'shiba', 'chainlink', 'avalanche', 'polygon', 'polkadot', 'uniswap', 'binance coin']

# Timezone
EST = pytz.timezone('US/Eastern')

# Date
MONTHS_MAP = {
    'jan':1,'january':1,'feb':2,'february':2,'mar':3,'march':3,'apr':4,'april':4,
    'may':5,'jun':6,'june':6,'jul':7,'july':7,'aug':8,'august':8,'sep':9,'sept':9,
    'september':9,'oct':10,'october':10,'nov':11,'november':11,'dec':12,'december':12
}

# Feature toggles
ALLOW_5M_MARKETS = os.getenv("ALLOW_5M_MARKETS", "false").lower() == "true"
DISABLE_WS_LIVE = os.getenv("DISABLE_WS_LIVE", "false").lower() == "true"