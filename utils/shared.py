import re


def parse_usd(price_raw) -> float:
    """Parse messy USD prices → float. Handles '$0.52', '0.52 USD', 0.52, None."""
    if price_raw is None:
        return 0.50
    if isinstance(price_raw, (int, float)):
        return float(price_raw)
    try:
        clean = re.sub(r'[\$,USD\s]', '', str(price_raw))
        return float(clean)
    except ValueError:
        return 0.50


def truncate_title(title: str, max_len: int = 85) -> str:
    """
    Canonical title truncation — use this everywhere instead of
    local _truncate() or format_short_title() copies.
    """
    if not title:
        return ''
    return (title[:max_len] + '...') if len(title) > max_len else title


def safe_float(val, default: float = 0.0) -> float:
    """Convert to float safely."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default
