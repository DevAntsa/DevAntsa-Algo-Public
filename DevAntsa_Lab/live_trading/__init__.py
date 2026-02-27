"""
Live Trading System - Multi-Strategy Regime-Adaptive Algo
=========================================================
Spec: src/data/rbi_devantsa/MULTI_STRATEGY_LIVE_SYSTEM_PLAN.md (v3.0)

Directory layout:
    strategies/   - Bull, Bear, Sideways strategy implementations (Plan Parts 1, 6)
    engine/       - Signal detection, conflict resolution, main loop (Plan Part 7)
    execution/    - Binance Futures API executor, order management (Bootstrap Stage 1)
    risk/         - Position sizing, regime limits, adaptive leverage (Plan Part 4)
    data/         - Runtime state, trade logs, reconciliation records
    config.py     - Frozen parameters from the plan (allocations, limits, assets)
"""
