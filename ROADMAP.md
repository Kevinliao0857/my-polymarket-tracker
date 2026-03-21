# Polymarket Copy-Trader: Phased Roadmap

## Context
We're inheriting a functional but fragile Streamlit dashboard that tracks a Polymarket quant trader (Cosmos/0x8dxd) who hedges most of his bets. The app works for real-time monitoring but has no persistence, no backtesting, and no trade execution. We want to: understand the trader's strategy through data, validate that copy-trading him is profitable, and eventually execute trades automatically with risk controls.

---

## Phase 1: Stabilize & Persist (Start Here)

**Goal:** Make the app reliable and start collecting data we can analyze later.

### 1a. Add a Database
- Add **SQLite** (simple, no infra) with a migration path to Postgres later if needed
- Store: trades, positions (snapshots), simulation results, PnL history
- Tables:
  - `trades` — every trade we see (deduplicated by tx_hash)
  - `position_snapshots` — periodic snapshots of open positions (for time-series analysis)
  - `settled_trades` — realized PnL records
  - `simulation_runs` — simulator config + results for backtesting comparison
- Use SQLAlchemy or raw sqlite3 (keep it simple)
- **Files to modify:** New `utils/db.py`, modify `utils/trades.py`, `utils/positions.py`, `utils/closed_trades.py`, `utils/simulator.py`

### 1b. Background Data Collector
- Add a **background process** (separate from Streamlit) that continuously polls and persists trades
- This decouples data collection from the UI — data keeps flowing even when nobody has the dashboard open
- Could be a simple Python script with a loop + sleep, or a lightweight scheduler
- **New file:** `collector.py` (entry point for background collection)

### 1c. Code Cleanup
- Extract hardcoded trader address to config/env var
- Clean up the slippage calculation (currently noted as not working)
- Add proper error handling where it's missing
- Add `.env` support for configuration
- **Files to modify:** `utils/config.py`, various utils

### 1d. Dev Container Updates
- Add SQLite tooling to the dev container
- Add the collector process to the container startup
- **Files to modify:** `.devcontainer/devcontainer.json`, `requirements.txt`

---

## Phase 2: Analyze & Understand the Trader (Run Alongside Phase 1)

**Goal:** Once we have persisted data, build tools to understand the trader's strategy.

### 2a. Trader Analytics Dashboard
- New Streamlit page: `pages/analytics.py`
- Metrics to compute:
  - **Win rate** by market type (crypto subcategories)
  - **Average position size** and how it varies
  - **Hedge ratio** — what % of positions are hedged vs directional
  - **Hold duration** — how long positions stay open
  - **PnL distribution** — histogram of trade outcomes
  - **Time-of-day patterns** — when does he trade most/best

### 2b. Backtesting Framework
- Replay historical trades from the database
- Simulate copy-trading with different parameters:
  - Copy ratio variations
  - Different entry delays (how fast can we realistically copy)
  - Stop-loss thresholds
  - Selective copying (e.g., only hedged positions, only certain market types)
- Output: PnL curves, drawdown analysis, Sharpe-like metrics
- **New files:** `utils/backtest.py`, `pages/backtest.py`

### 2c. Hedge Analysis
- Deep dive into the trader's hedging behavior
- Identify: hedge ratios per market, whether hedges are symmetric, timing of hedge legs
- Understand: is he hedging for risk management or is the hedge itself the strategy (e.g., arbitrage)?
- **New file:** `pages/hedge_analysis.py` or integrate into analytics

---

## Phase 3: Live Execution (After We're Confident in the Strategy)

**Goal:** Actually execute copy trades with real money and proper risk controls.

### 3a. Polymarket CLOB API Integration
- Integrate with Polymarket's CLOB API for order placement
- Need: API key management, order signing, wallet integration
- Support: market orders and limit orders
- **New files:** `utils/executor.py`, `utils/wallet.py`

### 3b. Risk Management Engine
- **Stop-loss:** Per-position and portfolio-level
- **Max position size:** Cap based on bankroll percentage
- **Daily loss limit:** Hard stop if cumulative daily loss exceeds threshold
- **Exposure limits:** Max % of bankroll deployed at once
- **Cooldown:** After stop-loss triggers, wait period before resuming
- **New file:** `utils/risk.py`

### 3c. Execution Pipeline
- Signal detection (already exists in `utils/copy_trader.py`) → Risk check → Order placement → Confirmation → Position tracking
- Add execution logging to database
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
