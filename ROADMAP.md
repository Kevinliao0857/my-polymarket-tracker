# Polymarket Copy-Trader: Phased Roadmap

## Context
We're inheriting a functional but fragile Streamlit dashboard that tracks a Polymarket quant trader (Cosmos/0x8dxd) who hedges most of his bets. The app works for real-time monitoring but has no persistence, no backtesting, and no trade execution. We want to: understand the trader's strategy through data, validate that copy-trading him is profitable, and eventually execute trades automatically with risk controls.

**Key design principle:** Multi-trader from day one. Rather than betting everything on one trader, we track and analyze multiple traders to diversify risk. The database schema, collector, and UI all support a configurable list of watched traders.

---

## Phase 1: Stabilize & Persist (Start Here)

**Goal:** Make the app reliable and start collecting data we can analyze later.

### 1a. Add a Database
- Add **SQLite** (simple, no infra) with a migration path to Postgres later if needed
- Store: trades, positions (snapshots), simulation results, PnL history
- **All tables keyed by `trader_address`** — multi-trader from the start
- Tables:
  - `traders` — watched traders (address, alias, added_at, active flag)
  - `trades` — every trade we see (deduplicated by trader_address + tx_hash)
  - `position_snapshots` — periodic snapshots of open positions per trader
  - `settled_trades` — realized PnL records per trader
  - `simulation_runs` — simulator config + results per trader (and combined)
- Use SQLAlchemy or raw sqlite3 (keep it simple)
- **Files to modify:** New `utils/db.py`, modify `utils/trades.py`, `utils/positions.py`, `utils/closed_trades.py`, `utils/simulator.py`

### 1b. Background Data Collector
- Add a **background process** (separate from Streamlit) that continuously polls and persists trades
- **Loops over all active traders** in the `traders` table — one poll cycle covers everyone
- This decouples data collection from the UI — data keeps flowing even when nobody has the dashboard open
- Could be a simple Python script with a loop + sleep, or a lightweight scheduler
- **New file:** `collector.py` (entry point for background collection)

### 1c. Code Cleanup
- Replace hardcoded trader address with a **trader registry** (config file or DB-driven)
- Add/remove traders via UI sidebar or config — no code changes needed to watch someone new
- Clean up the slippage calculation (currently noted as not working)
- Add proper error handling where it's missing
- Add `.env` support for configuration
- **Files to modify:** `utils/config.py`, various utils

### 1d. Dev Container Updates
- Add SQLite tooling to the dev container
- Add the collector process to the container startup
- **Files to modify:** `.devcontainer/devcontainer.json`, `requirements.txt`

---

## Phase 2: Analyze & Understand the Traders (Run Alongside Phase 1)

**Goal:** Once we have persisted data, build tools to understand each trader's strategy and compare them.

### 2a. Per-Trader Analytics Dashboard
- New Streamlit page: `pages/analytics.py`
- **Trader selector** — pick a trader or view aggregate across all
- Per-trader metrics:
  - **Win rate** by market type (crypto subcategories)
  - **Average position size** and how it varies
  - **Hedge ratio** — what % of positions are hedged vs directional
  - **Hold duration** — how long positions stay open
  - **PnL distribution** — histogram of trade outcomes
  - **Time-of-day patterns** — when does he trade most/best

### 2b. Cross-Trader Comparison
- **Trader leaderboard** — rank watched traders by PnL, win rate, Sharpe
- **Correlation analysis** — do traders overlap on the same markets? Are their signals redundant or diversified?
- **Allocation optimizer** — given N traders, what % of bankroll to allocate to each for best risk-adjusted return
- This is the core diversification tool — helps decide who to copy and how much

### 2c. Backtesting Framework
- Replay historical trades from the database
- Simulate copy-trading with different parameters:
  - Copy ratio variations (per trader)
  - Different entry delays (how fast can we realistically copy)
  - Stop-loss thresholds
  - Selective copying (e.g., only hedged positions, only certain market types)
  - **Multi-trader portfolios** — backtest copying 2-3 traders simultaneously with allocation splits
- Output: PnL curves, drawdown analysis, Sharpe-like metrics
- **New files:** `utils/backtest.py`, `pages/backtest.py`

### 2d. Hedge Analysis
- Deep dive into each trader's hedging behavior
- Identify: hedge ratios per market, whether hedges are symmetric, timing of hedge legs
- Understand: is he hedging for risk management or is the hedge itself the strategy (e.g., arbitrage)?
- Compare hedging styles across traders
- **New file:** `pages/hedge_analysis.py` or integrate into analytics

---

## Phase 3: Live Execution (After We're Confident in the Strategy)

**Goal:** Actually execute copy trades with real money and proper risk controls.

### 3a. Polymarket CLOB API Integration
- Integrate with Polymarket's CLOB API for order placement
- Need: API key management, order signing, wallet integration
- Support: market orders and limit orders
- **Multiple portfolios / API keys:**
  - Each portfolio gets its own API key + wallet — isolates execution per trader (or group of traders)
  - Avoids rate limiting from funneling all activity through one key
  - Note: Polymarket may also rate-limit by IP — if that becomes an issue, we can proxy through different IPs later, but start simple with key-per-portfolio
  - Portfolio config: `{ portfolio_name, api_key, wallet, assigned_traders[], bankroll }`
- **New files:** `utils/executor.py`, `utils/wallet.py`, `utils/portfolio.py`

### 3b. Risk Management Engine
- **Per-portfolio isolation:** Each portfolio has its own bankroll, risk limits, and stop-loss — one blowing up doesn't affect the others
- **Per-trader allocation:** Cap how much of a portfolio's bankroll goes to each assigned trader
- **Stop-loss:** Per-position, per-trader, and per-portfolio
- **Max position size:** Cap based on bankroll percentage
- **Daily loss limit:** Hard stop if cumulative daily loss exceeds threshold (per-trader and global)
- **Exposure limits:** Max % of bankroll deployed at once across all traders
- **Cooldown:** After stop-loss triggers, wait period before resuming (can pause one trader without stopping others)
- **Conflict detection:** If two traders take opposite sides of the same market, flag it rather than blindly copying both
- **New file:** `utils/risk.py`

### 3c. Execution Pipeline
- Signal detection (already exists in `utils/copy_trader.py`) → Risk check → Order placement → Confirmation → Position tracking
- **Multi-trader signal aggregation** — process signals from all watched traders, apply per-trader allocation
- Add execution logging to database (tagged by source trader)
- Add alerting (start simple: log file, then add Telegram/Discord webhook)
- **Files to modify:** `utils/copy_trader.py`, new `utils/alerts.py`

### 3d. Live Dashboard Updates
- Execution status panel
- Real vs simulated PnL comparison
- Risk metrics display (current exposure, distance to stop-loss)
- Trade execution history with fills and slippage

---

## Immediate Next Steps (What We'll Build First)

1. **Set up SQLite persistence** (`utils/db.py` + schema)
2. **Wire up trade persistence** in existing tracking code
3. **Build the background collector** (`collector.py`)
4. **Extract config to env vars** (trader address, etc.)
5. Start collecting data immediately so we have history to analyze

---

## Verification

- Start dev container, confirm Streamlit loads on `:8501`
- Verify trades are being written to SQLite
- Verify collector runs independently and persists data
- Query the DB directly to confirm data integrity
- Run the simulator and verify it can read from persisted data
