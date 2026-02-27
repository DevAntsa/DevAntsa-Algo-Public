# RBI Agent - Parallel Processor Multi-Data (Devantsa Custom)

**Research-Based Inference Agent with Parallel Processing and Multi-Data Testing**

---

## Overview

The RBI (Research-Based Inference) Parallel Processor is an advanced version of Moon Dev's RBI agent, customized for high-throughput strategy generation and testing. It processes multiple trading ideas simultaneously using parallel threads and automatically tests successful strategies across 25+ data sources.

**Key Features**:
- **Parallel Processing**: 18 concurrent worker threads
- **Multi-Data Testing**: Automatic validation across BTC, ETH, SOL, stocks, futures
- **Cost Optimization**: Toggle between budget (DeepSeek) and premium (Claude) models
- **Windows Compatible**: Fixed emoji/encoding issues for Windows systems
- **Strategy Reports**: Comprehensive markdown reports for winning strategies

**File**: `src/agents/rbi_agent_pp_multi_devantsa.py`

---

## Quick Start

```bash
# Activate your environment
conda activate tflow

# Run the agent
python src/agents/rbi_agent_pp_multi_devantsa.py

# The agent will:
# 1. Read trading ideas from src/data/rbi_devantsa/ideas.txt
# 2. Process up to 18 ideas simultaneously
# 3. Generate, debug, and optimize strategies
# 4. Test successful strategies on multiple data sources
# 5. Save results to CSV and generate reports
```

---

## How It Works

### 1. Input: Trading Ideas

Create a file at `src/data/rbi_devantsa/ideas.txt`:

```
Simple RSI oversold overbought strategy buy at 30 sell at 70
Moving average crossover with 50 and 200 period
Bollinger band mean reversion strategy
```

Each line = one trading idea. The agent processes them in parallel.

### 2. Pipeline Stages

For each idea, the agent runs through:

```
Research → Code Generation → Package Check → Execute → Debug → Optimize
```

**Research** (DeepSeek/Claude):
- Extracts trading logic from your idea
- Defines entry/exit rules
- Identifies required indicators

**Code Generation** (DeepSeek/Claude):
- Creates backtesting.py compatible Python code
- Implements strategy class with indicators
- Adds performance tracking

**Package Check** (DeepSeek/Claude):
- Validates imports and dependencies
- Ensures pandas_ta/talib compatibility
- Fixes common import errors

**Execute**:
- Runs backtest on BTC-USD-15m.csv
- Captures performance metrics
- Detects errors (if any)

**Debug** (up to 10 iterations):
- Fixes code errors automatically
- Resolves crossover detection issues
- Handles NaN/zero-trade problems

**Optimize** (up to 10 iterations):
- Tunes parameters to hit target return (30% default)
- Adjusts indicator periods
- Optimizes entry/exit thresholds

### 3. Output: Results and Reports

**CSV Results** (`src/data/rbi_devantsa/backtest_stats.csv`):
```csv
Strategy Name,Return %,Sharpe,Sortino,Max DD %,Trades,...
AdaptiveEquilibrium,3.38,0.577,0.992,-7.47,19,...
VolatilityPulse,95.60,1.31,5.09,-19.51,1,...
```

**Strategy Reports** (`src/data/rbi_devantsa/[date]/strategy_reports/`):
- Comprehensive markdown report per winning strategy
- Includes: performance stats, AI research, full code, implementation notes

**Dashboard**:
```bash
streamlit run src/agents/backtest_dashboard.py
```

View all results in a sortable, filterable web UI.

---

## Configuration

### Model Selection (CRITICAL for Cost Control)

**Budget Mode** (Testing - Recommended):
```python
USE_BUDGET_MODELS = True  # ~$0.003 per strategy
```
Uses DeepSeek Chat (ultra-cheap, good quality)

**Premium Mode** (Production):
```python
USE_BUDGET_MODELS = False  # ~$0.33 per strategy
```
Uses Claude 3.5 Sonnet (best quality, expensive)

**Cost Comparison**:
| Mode | Model | Cost/Strategy | 30 Strategies | Quality |
|------|-------|---------------|---------------|---------|
| Budget | DeepSeek | $0.003 | $0.09 | Good for testing |
| Premium | Claude 3.5 | $0.33 | $10.00 | Best quality |

### Key Settings

**Line 186-188**: Performance Targets
```python
TARGET_RETURN = 30  # Target return % for optimization
SAVE_IF_OVER_RETURN = 0.0  # Save strategies with return > 0%
```

**Line 193**: Parallel Workers
```python
MAX_PARALLEL_THREADS = 18  # Number of simultaneous ideas to process
```

**Line 175-176**: Debug/Optimize Limits
```python
MAX_DEBUG_ITERATIONS = 10  # Max attempts to fix errors
MAX_OPTIMIZATION_ITERATIONS = 10  # Max parameter tuning attempts
```

---

## Architecture Details

### Thread-Safe Parallel Processing

**Design Pattern**:
```python
# Each thread processes one idea independently
def process_trading_idea_parallel(idea: str, thread_id: int):
    research_strategy(idea, thread_id)
    create_backtest(strategy, thread_id)
    execute_and_debug(code, thread_id)
    optimize_strategy(code, thread_id)
```

**Thread Safety**:
- File locks for all writes (CSV, code files, reports)
- Unique thread IDs (T00-T17) in all filenames
- Console output locks for clean logging
- API rate limiting per thread

### Multi-Data Testing (Automatic)

When a strategy passes the debug phase, it's automatically tested on:

**Crypto** (7 pairs):
- BTC-USD, ETH-USD, SOL-USD, BNB-USD, XRP-USD, ADA-USD, DOGE-USD

**Stocks** (6 tickers):
- AAPL, TSLA, NVDA, MSFT, GOOGL, AMZN

**Futures** (12 contracts):
- ES, NQ, YM, RTY, GC, SI, CL, NG, ZB, ZN, ZC, ZW

**Results**:
- Each data source gets separate backtest
- Results logged to CSV with data source column
- Only strategies that work across multiple assets are truly robust

### Directory Structure

```
src/data/rbi_devantsa/
├── ideas.txt                    # Input: Your trading ideas
├── processed_ideas.log          # Tracking: Processed ideas (prevents duplicates)
├── backtest_stats.csv          # Output: All strategy results
└── [date]/                      # Daily folder (MM_DD_YYYY)
    ├── research/                # AI research analysis per strategy
    ├── backtests/               # Debug iteration files
    ├── backtests_package/       # Package-checked code
    ├── backtests_working/       # Successful strategies
    ├── backtests_final/         # Final saved strategies
    ├── backtests_optimized/     # Optimization attempts
    ├── execution_results/       # JSON logs of all executions
    ├── strategy_reports/        # Comprehensive markdown reports
    └── charts/                  # (Future) Performance charts
```

---

## Windows Compatibility Notes

This version includes fixes for Windows-specific issues:

### Emoji/Unicode Handling

**Problem**: Windows uses CP1252 encoding, which can't handle emojis.

**Solution**: Added explicit warnings in all prompts:
```
ABSOLUTELY NO EMOJIS OR UNICODE CHARACTERS IN PRINT STATEMENTS!
FORBIDDEN: 🌙 (U0001f319), 🚀 (U0001f680), ANY emoji
```

**Status**: Warnings added to BACKTEST_PROMPT, DEBUG_PROMPT, OPTIMIZE_PROMPT

### Path Handling

All paths use forward slashes with Path objects:
```python
from pathlib import Path
DATA_DIR = Path("src/data/rbi_devantsa")  # Works on Windows & Mac
```

### File Encoding

All file operations specify UTF-8:
```python
with open(file, 'w', encoding='utf-8') as f:
    f.write(content)
```

---

## Differences from Moon Dev's Original

### Enhancements (Devantsa Custom)

1. **Parallel Processing** (Original: Sequential)
   - 18 threads vs 1
   - 18x faster for batch processing

2. **Multi-Data Testing** (Original: Single dataset)
   - Automatic testing on 25+ data sources
   - Validates strategy robustness

3. **Strategy Reports** (Original: None)
   - Comprehensive markdown reports
   - Includes AI research + code + stats

4. **Cost Optimization Toggle** (Original: Fixed model)
   - Easy budget/premium switching
   - 100x cost savings for testing

5. **Windows Compatibility** (Original: Mac-focused)
   - Fixed emoji encoding issues
   - Path compatibility

### Same Philosophy

- Minimal error handling (fail fast)
- Real data only (no synthetic)
- Under 800 lines per file (modular)
- Agent independence (standalone executable)

---

## Common Workflows

### 1. Generate 10 Strategies

```bash
# 1. Add 10 ideas to ideas.txt
echo "RSI divergence strategy" >> src/data/rbi_devantsa/ideas.txt
echo "MACD crossover with trend filter" >> src/data/rbi_devantsa/ideas.txt
# ... 8 more ideas

# 2. Run agent
python src/agents/rbi_agent_pp_multi_devantsa.py

# 3. Wait ~15-20 minutes (10 ideas × 2 min each, but parallel)

# 4. View results
streamlit run src/agents/backtest_dashboard.py
```

### 2. Test a Single Complex Idea

```bash
# 1. Clear ideas.txt (or comment out old ideas with #)
echo "Multi-timeframe momentum strategy using 1H and 4H RSI with volume confirmation and ATR-based stops" > src/data/rbi_devantsa/ideas.txt

# 2. Run agent
python src/agents/rbi_agent_pp_multi_devantsa.py

# 3. Check strategy report
# Look in: src/data/rbi_devantsa/[today]/strategy_reports/
```

### 3. Cost-Effective Testing (Budget Mode)

```bash
# 1. Enable budget models (already default)
# In rbi_agent_pp_multi_devantsa.py line 140:
# USE_BUDGET_MODELS = True  ✅ Already set

# 2. Add 30 test ideas
# ... create ideas.txt with 30 ideas

# 3. Run agent
python src/agents/rbi_agent_pp_multi_devantsa.py

# Cost: ~$0.09 (vs $10 with Claude)
```

### 4. Production Run (Premium Models)

```bash
# 1. Switch to premium models
# Edit line 140: USE_BUDGET_MODELS = False

# 2. Add carefully curated ideas (quality over quantity)
# ... 5-10 high-quality strategy ideas

# 3. Run agent
python src/agents/rbi_agent_pp_multi_devantsa.py

# Cost: ~$1.65-$3.30 for 5-10 strategies
# Quality: Best possible code generation
```

---

## Troubleshooting

### Issue: "Repeated error detected - stopping"

**Cause**: Same error occurring multiple times (emoji, syntax, import error)

**Fix**:
1. Check `execution_results/` for the specific error
2. Look for emoji characters in generated code
3. Strengthen prompts if needed
4. Manually fix the package_checked code and re-run

### Issue: "No trades taken" (# Trades = 0)

**Cause**: Crossover detection logic broken

**Fix**: Already handled in prompts. Agent auto-fixes with array indexing examples.

### Issue: Rate limit errors (free models)

**Cause**: Using free models with 18 parallel threads

**Fix**: Switch to budget paid models (DeepSeek) - no rate limits

### Issue: CSV not updating

**Cause**: Strategies not passing threshold (return ≤ 0%)

**Fix**: Lower `SAVE_IF_OVER_RETURN` to -100% to see all results

---

## Performance Metrics

**Speed** (18 threads):
- Sequential: ~2 min per strategy → 30 strategies = 60 min
- Parallel: ~2 min per batch → 30 strategies = ~6-8 min

**Success Rate**:
- Research phase: ~98% (DeepSeek/Claude both excellent)
- Code generation: ~90% (some syntax errors)
- Debug phase: ~85% (after 1-3 iterations)
- Optimization: ~60% (emoji issues still present)

**Cost** (Budget Mode, 30 strategies):
- DeepSeek Chat: ~$0.09 total
- Claude 3.5 Sonnet: ~$10.00 total
- **Savings: 111x cheaper**

---

## Integration with Dashboard

**Dashboard File**: `src/agents/backtest_dashboard.py`

**Features**:
- View all strategies in sortable table
- Filter by min trades, min return, date
- Search by strategy name
- Performance charts (Sharpe vs Return)
- Top 10 strategies bar chart

**Column Mapping** (Auto-handled):
```python
# Multi agent CSV columns → Dashboard columns
'Max Drawdown %' → 'Max DD %'
'Sharpe Ratio' → 'Sharpe'
'Sortino Ratio' → 'Sortino'
'EV %' → 'Expo %'
```

---

## Future Enhancements

**Planned**:
- [ ] Chart generation for each strategy
- [ ] Email/Discord alerts for winning strategies
- [ ] Auto-deploy to live trading (with risk checks)
- [ ] Strategy backtesting on custom date ranges
- [ ] Multi-exchange data sources (Hyperliquid, Extended)

**Community Contributions Welcome!**

---

## Related Agents

- `rbi_agent.py`: Original RBI (single-threaded)
- `rbi_agent_pp_multi.py`: Moon Dev's parallel version
- `rbi_batch_backtester.py`: Batch backtest existing strategies

---

## Credits

**Original RBI Agent**: Moon Dev
**Parallel Processor**: Moon Dev
**Devantsa Customizations**:
- Multi-data testing
- Strategy reports
- Windows compatibility
- Cost optimization toggle
- Dashboard enhancements

---

**Built with 🌙 by Moon Dev**

*Customized for Windows & parallel processing by Devantsa*

---

## Support

- **GitHub**: https://github.com/DevAntsa/moon-dev-ai-agents
- **Original Repo**: https://github.com/MoonDevX/moon-dev-ai-agents-for-trading
- **Moon Dev Discord**: https://discord.gg/moondev
- **Moon Dev YouTube**: @MoonDevTrading

---

*"Never over-engineer, always ship real trading systems."* — Moon Dev
