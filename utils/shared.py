import re
import pandas as pd

def parse_usd(value):
    """$1,234 → 1234.0, N/A → 0"""
    if pd.isna(value) or value is None: return 0.0
    text = str(value).upper().replace('$', '').replace(',', '')
    nums = re.findall(r'[\d.]+\d*', text)
    if nums: return float(nums[0])
    return 0.0
