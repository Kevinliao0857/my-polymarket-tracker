# Thin gateway - re-export functions
from .trades import track_0x8dxd, get_latest_bets
from .profile import get_profile_name, get_trader_pnl
from .positions import get_open_positions
from .closed_trades import get_closed_trades_pnl  # You'll need to create this

__all__ = [
    'track_0x8dxd', 'get_latest_bets', 
    'get_profile_name', 'get_trader_pnl', 
    'get_open_positions', 'get_closed_trades_pnl'
]
