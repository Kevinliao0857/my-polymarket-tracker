import re
import pandas as pd

def parse_usd(price_raw):
    """Parse messy USD prices → float. Handles '$0.52', '0.52 USD', 0.52, None."""
    if not price_raw:
        return 0.50
    try:
        if isinstance(price_raw, (int, float)):
            return float(price_raw)
        # Clean common formats
        clean = str(price_raw).replace('$', '').replace(',', '').replace('USD', '').strip()
        return float(clean)
    except:
        return 0.50

def format_short_title(title, max_len=85):
    """Truncate titles safely."""
    if len(title) > max_len:
        return title[:max_len] + '...'
    return title

def safe_float(val, default=0.0):
    """Convert to float safely."""
    try:
        return float(val)
    except:
        return default