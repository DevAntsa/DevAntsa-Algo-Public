# RBI Regular Agent - AI Strategy Factory

## Overview

The RBI (Research-Backtest-Iterate) system is an AI-powered strategy factory that uses LLMs to generate, backtest, and optimize trading strategies automatically.

## How to Run

```
conda activate tflow
cd DevAntsa_Lab/RBI_Agents/RBI_Regular

# Bull market strategies
python rbi_agent_pp_multi_devantsa.py

# Bear market strategies
python rbi_bear.py
```

## Processing Pipeline

```
ideas.txt --> Monitor Thread (reads every 1s, deduplicates)
                  |
                  v
            Queue (up to 18 workers)
                  |
                  v
         Worker Thread Pipeline:
         1. RESEARCH: idea -> strategy name + details
         2. BACKTEST: details -> Python code
         3. PACKAGE: fix imports (no talib, no backtesting.lib)
         4. EXECUTE: run in conda env (900s timeout)
         5. DEBUG: up to 10 iterations if errors
         6. OPTIMIZE: up to 10 iterations toward TARGET_RETURN
                  |
                  v
         qualify_strategy() gate
                  |
                  v
         Save to: winners/, results/, backtest_stats.csv
```

## Agent Configuration

- TARGET_RETURN = 100 (aspirational, forces optimization)
- MAX_PARALLEL_THREADS = 18
- MAX_OPTIMIZATION_ITERATIONS = 6
- Commission = 0.001 (0.1% round-trip)
- Starting cash = $1,000,000
- Model: Grok-4-Fast via OpenRouter

## Data

The agent reads OHLCV data from `../RBI_FullData/rbi_full_data/` (BTC/ETH/SOL, 1h+4h, Jan 2021+).

## Output Directories

| Path | Purpose |
|------|---------|
| `data/` | Runtime outputs (daily folders) |
| `results/` | Multi-data CSVs per strategy |
| `winners/` | Qualified strategy .py files |
| `portfolio/` | Curated portfolio strategies |

## Ideas Format

```
-- META_SECTION_START --
Guidelines for strategy generation...
-- META_SECTION_END --

[NEW_IDEA]
Strategy description here
```

## Full-Data Self-Gating

Strategies are tested on ALL market data (5+ years). Strict entry conditions (3+ filters) naturally don't trigger in wrong regimes. The entry conditions ARE the regime filter.
