# CLAUDE.md - Ganymede Trading Bot

## Project Overview

**Ganymede-Prod-Rev-1.9** is an automated Forex trading bot for MetaTrader 5 (MT5) with ML-enhanced analytics. The system implements confluence-based mean reversion trading derived from reverse-engineering analysis of 428 profitable trades (64.3% win rate).

### Core Trading Strategies
- **Confluence-based mean reversion** (primary) - Multi-factor scoring using VWAP, Volume Profile, and HTF levels
- **Breakout strategies** (secondary) - Range and Low Volume Node breakouts
- **Smart Money Concepts (SMC)** (alternative bot) - Liquidity sweeps and market structure shifts

### Key Technologies
- Python 3.8+
- MetaTrader5 (MT5 API)
- Pandas/NumPy for data manipulation
- scikit-learn, XGBoost for ML models
- Tkinter for GUI
- Threading for concurrent MT5 API access

---

## Repository Structure

```
Ganymede-Prod-Rev-1.9/
├── trading_bot/              # Core confluence trading bot
│   ├── main.py               # Entry point (CLI + GUI launcher)
│   ├── core/
│   │   └── mt5_manager.py    # MT5 connection and order management
│   ├── strategies/
│   │   ├── confluence_strategy.py   # Main orchestrator (400+ lines)
│   │   ├── signal_detector.py       # Multi-factor confluence scoring
│   │   ├── recovery_manager.py      # Grid/Hedge/DCA (800+ lines)
│   │   ├── breakout_strategy.py     # Breakout detection
│   │   ├── partial_close_manager.py # Position scaling
│   │   └── time_filters.py          # Session filters
│   ├── indicators/
│   │   ├── vwap.py           # VWAP + deviation bands (±1σ, ±2σ, ±3σ)
│   │   ├── volume_profile.py # POC, VAH, VAL, HVN, LVN
│   │   ├── htf_levels.py     # Higher timeframe levels
│   │   └── adx.py            # ADX trend filtering
│   ├── portfolio/
│   │   ├── instruments_config.py  # Per-instrument settings
│   │   └── portfolio_manager.py   # Trading coordination
│   ├── utils/
│   │   ├── logger.py         # Multi-file logging
│   │   ├── risk_calculator.py
│   │   ├── timezone_manager.py
│   │   └── config_reloader.py
│   ├── config/
│   │   └── strategy_config.py # 500+ lines of parameters
│   └── gui/
│       └── trading_gui.py     # Tkinter dashboard
├── smc_bot/                   # Alternative SMC trading methodology
│   ├── smc_trade_bot.py
│   ├── config/smc_config.py
│   └── strategies/
├── ml_system/                 # ML analysis and automation
│   ├── ml_system_startup.py   # Integration entry point
│   ├── continuous_logger.py   # Background trade logging (1800+ lines)
│   ├── ml_integration_manager.py
│   ├── adaptive_confluence_weighting.py
│   ├── models/
│   ├── scripts/
│   ├── reports/
│   ├── outputs/               # JSON analysis results
│   └── scheduler/
├── config/                    # Global configuration
│   ├── config.yaml
│   └── email_config.json
└── docs/                      # Documentation
```

---

## Quick Reference

### Running the Bot

```bash
# Command-line mode
python trading_bot/main.py \
    --login 12345 \
    --password "pass" \
    --server "Broker-Server" \
    --symbols EURUSD GBPUSD

# GUI mode
python trading_bot/main.py --gui

# Test mode (bypass time filters)
python trading_bot/main.py --test-mode --login ... --password ... --server ...

# Disable ML automation
python trading_bot/main.py --disable-ml --login ... --password ... --server ...

# Debug mode (verbose output)
python trading_bot/main.py --debug --login ... --password ... --server ...
```

### Running SMC Bot

```bash
python smc_bot/smc_trade_bot.py \
    --login 12345 \
    --password "pass" \
    --server "Broker-Server" \
    --symbols EURUSD GBPUSD
```

### Running ML Analysis (Standalone)

```bash
python ml_system/scripts/create_dataset.py
python ml_system/models/baseline_model.py
python ml_system/reports/decision_report.py
```

---

## Key Configuration Files

| File | Purpose |
|------|---------|
| `trading_bot/config/strategy_config.py` | Primary trading parameters (500+ lines) |
| `trading_bot/portfolio/instruments_config.py` | Per-instrument settings (EURUSD, GBPUSD, USDJPY) |
| `smc_bot/config/smc_config.py` | SMC strategy parameters |
| `config/config.yaml` | Global settings (indicators, ML, risk) |
| `config/email_config.json` | Email delivery for ML reports |

### Important Parameters (strategy_config.py)

```python
MIN_CONFLUENCE_SCORE = 7      # Minimum score to enter trade
OPTIMAL_CONFLUENCE_SCORE = 8  # Best win rate (83.3%)
BASE_LOT_SIZE = 0.04
MAX_TOTAL_LOTS = 15.0
MAX_DRAWDOWN_PERCENT = 50.0
GRID_ENABLED = False          # Disabled after $500 loss analysis
HEDGE_ENABLED = True
DCA_ENABLED = True
ENABLE_CASCADE_PROTECTION = True
ENABLE_ADX_HARD_STOPS = True
ADX_HARD_STOP_THRESHOLD = 30
```

---

## Coding Conventions

### Variable Naming
- Config booleans: `UPPERCASE_UNDERSCORE` (e.g., `HEDGE_ENABLED`)
- Pips values: `_pips` suffix (e.g., `grid_spacing_pips`)
- Time values: `_hours` or `_minutes` suffix
- Lot sizes: `_size` or `_multiplier` suffix

### Function Naming
- MT5 operations: wrapped in `_with_lock()` helper
- Strategy methods: `is_[condition]()`, `detect_[pattern]()`, `calculate_[metric]()`
- Indicator calculations: return DataFrames or Dicts

### Threading Model
```python
# Global lock for thread-safe MT5 API access
mt5_api_lock = threading.Lock()

# All MT5 calls use this pattern:
def _with_lock(self, operation):
    with self._api_lock:
        return operation()
```

### Error Handling Pattern
```python
try:
    # Risky operation (MT5 API, file I/O, model loading)
    result = mt5_operation()
except Exception as e:
    logger.warning(f"Operation failed: {e}")
    # Graceful degradation - don't crash, use fallback
    result = fallback_default
```

### Import Order
1. Standard library
2. Third-party packages
3. Local modules

### Path Handling
- Always use `Path` objects (not string concatenation)
- Use absolute paths via `Path(__file__).parent`
- Example: `current_dir = Path(__file__).parent`

---

## Logging System

| Log File | Purpose |
|----------|---------|
| `trading_bot.log` | Main bot activity |
| `trades.log` | Trade entry/exit/recovery events |
| `signals.log` | Signal detection details |
| `ml_system/logs/ml_system.log` | ML automation logs |
| `ml_system/outputs/continuous_trade_log.jsonl` | Live trade stream (append-only) |

### Logging Usage
```python
from utils.logger import logger

logger.info("Information message")
logger.warning("Warning message")
logger.error("Error message")
```

---

## Trading Strategy Overview

### Confluence Scoring
The bot scores potential trades using 15+ confluence factors:

**Lower Timeframe (weight = 1):**
- VWAP bands (±1σ, ±2σ, ±3σ)
- Volume profile (POC, VAH, VAL, HVN, LVN)
- Swing highs/lows

**Higher Timeframe (weight = 2-3):**
- Previous Day VAH/VAL/POC
- Weekly HVN/POC
- Previous Week Swing High/Low

Minimum score of 7 required to enter. Score of 8+ has 83.3% win rate.

### Recovery Mechanisms

| Mechanism | Status | Trigger | Notes |
|-----------|--------|---------|-------|
| Grid | DISABLED | - | $500 loss led to disabling |
| Hedge | ENABLED | 45-55 pips | 1.5x ratio, max 1 per position |
| DCA | ENABLED | 30-40 pips | 1.2x multiplier, max 2 levels |

### Risk Management
- Per-stack stop loss: -$75 (DCA-only), -$125 (DCA+Hedge)
- Cascade protection: Closes underwater positions after 2+ stop-outs in 30 min
- ADX hard stops: Fixed 50-pip stop when ADX > 30 (trending market)

---

## ML System Integration

The ML system runs in the background:
- **Continuous Logger**: Tracks all trades every 60 seconds
- **Model Retraining**: Every 8 hours
- **Daily Reports**: 8:00 AM with email delivery

### ML-Optimized Features (Unlock thresholds)
- 10+ trades: Basic pattern detection
- 30+ trades: Time performance analysis
- 50+ trades: Adaptive confluence weighting
- 100+ trades: Full ML recommendations

---

## Common Development Tasks

### Adding a New Indicator
1. Create file in `trading_bot/indicators/`
2. Follow pattern from `vwap.py` or `volume_profile.py`
3. Return DataFrame or Dict with calculated values
4. Import and use in `signal_detector.py`

### Adding a New Confluence Factor
1. Add detection logic to `signal_detector.py`
2. Add weight to `CONFLUENCE_WEIGHTS` in `strategy_config.py`
3. ML system will automatically track effectiveness

### Modifying Recovery Behavior
1. Edit `trading_bot/strategies/recovery_manager.py`
2. Per-instrument settings in `instruments_config.py`
3. Global toggles in `strategy_config.py`

### Running Tests
Currently manual/integration-based:
```bash
# Validate time filters
python trading_bot/verify_trading_times.py

# Test email delivery
python ml_system/test_email.py
```

---

## Important Notes for AI Assistants

### Do NOT
- Modify `.gitignore` patterns without explicit request
- Change MT5 credentials or connection logic without review
- Disable cascade protection or risk limits
- Remove thread safety locks (`mt5_api_lock`)
- Modify recovery mechanism triggers without understanding implications

### Always
- Use existing logging patterns (`from utils.logger import logger`)
- Preserve thread-safe MT5 API access patterns
- Test changes with `--test-mode` flag first
- Update relevant configuration files when adding features
- Document parameter changes with comments showing original values

### Data Types
- Use `convert_numpy_types()` for JSON serialization
- Use `round_volume_to_step()` for lot size rounding
- Enforce UTF-8 encoding for international symbols

### Configuration Precedence
1. Per-instrument settings (instruments_config.py)
2. Strategy config (strategy_config.py)
3. ML-optimized weights (loaded dynamically if 50+ trades)

---

## Files by Importance

| Priority | File | Why |
|----------|------|-----|
| Critical | `confluence_strategy.py` | Main trading orchestrator |
| Critical | `recovery_manager.py` | Grid/Hedge/DCA logic |
| Critical | `strategy_config.py` | All trading parameters |
| Critical | `mt5_manager.py` | MT5 API connection |
| High | `signal_detector.py` | Entry signal logic |
| High | `instruments_config.py` | Per-instrument settings |
| High | `continuous_logger.py` | ML trade tracking |
| Medium | `vwap.py`, `volume_profile.py` | Core indicators |
| Medium | `time_filters.py` | Session restrictions |
| Low | `trading_gui.py` | GUI interface |

---

## Git Workflow

- Main branch: `main`
- Feature branches: `claude/feature-name-sessionId`
- Commit messages: Describe the "why" not just the "what"
- Always verify MT5 connection tests pass before pushing

---

## Troubleshooting

### MT5 Connection Issues
```python
# Check connection status
mt5_manager.get_account_info()  # Returns None if disconnected

# Reconnect pattern
mt5_manager.disconnect()
mt5_manager.connect()
```

### Thread Deadlock
- Ensure all MT5 calls use `_with_lock()` pattern
- Check for nested lock acquisitions
- Background thread waits 30s before first check

### ML System Not Starting
- Check `--disable-ml` flag
- Verify `ml_system/requirements.txt` dependencies installed
- Check `ml_system/logs/ml_system.log` for errors

---

## References

- Trading Bot README: `trading_bot/README.md`
- ML System README: `ml_system/README.md`
- ML Integration Guide: `ml_system/INTEGRATION.md`
- Recovery System Design: `docs/RECOVERY_SYSTEM_SUMMARY.md`
- Cascade Protection: `docs/CASCADE_PROTECTION_DESIGN.md`
