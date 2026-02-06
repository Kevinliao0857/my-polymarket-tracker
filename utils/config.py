import pytz
from typing import List

# Trader address
TRADER = "0x63ce342161250d705dc0b16df89036c8e5f9ba9a".lower()

# Crypto tickers and names
TICKERS = ['btc', 'eth', 'sol', 'xrp', 'ada', 'doge', 'shib', 'link', 'avax', 'matic', 'dot', 'uni', 'bnb', 'usdt', 'usdc']
FULL_NAMES = ['bitcoin', 'ethereum', 'solana', 'ripple', 'xrp', 'cardano', 'dogecoin', 'shiba', 'chainlink', 'avalanche', 'polygon', 'polkadot', 'uniswap', 'binance coin']

# Timezone
EST = pytz.timezone('US/Eastern')
