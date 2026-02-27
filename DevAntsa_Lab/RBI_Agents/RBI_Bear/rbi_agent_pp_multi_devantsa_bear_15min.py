"""
 Devantsa RBI AI v3.0 PARALLEL PROCESSOR - BEAR MARKET 15-MINUTE VERSION
Forked from Moon Dev's original research bot

 BEAR MARKET 15-MINUTE SPECIALIZATION:
- Optimized for PURE SHORT strategies on 15-MINUTE bear market data
- Uses ideas_bear_15min.txt for BEAR 15m-specific strategy patterns
- Target: 30-100 trades on 15m timeframe (~2 months of data)
- Benchmark: SHORT-and-hold in bear markets
- CRITICAL: 0.055% commission per trade (0.11% round-trip on Bybit taker) - Crypto Fund Trader
- EXACTLY 2 conditions per strategy (prevents signal starvation)
- 4 CLEAN ASSETS: BTC, ETH, SOL, BNB (15m bear period data)

COST SAVINGS MODE:
 Toggle USE_BUDGET_MODELS (line 140) to switch between modes:
  - True = DeepSeek Chat (~$0.003/strategy - 100x cheaper!) - USE FOR TESTING!
  - False = Claude 3.5 Sonnet (~$0.33/strategy) - USE FOR PRODUCTION!

CUSTOM VERSION FOR DEVANTSA:
- Only saves WINNING strategies (50%+ return) to dashboard
- Parallel processing with 18 threads
- Auto-debugging and optimization
- Uses ideas_bear_15min.txt for BEAR 15m-specific strategies

- Each thread processes a different trading idea
- Thread-safe colored output
- Rate limiting to avoid API throttling
- Massively faster than sequential processing
-  AUTOMATIC MULTI-DATA TESTING on 25+ data sources (BTC, ETH, SOL, AAPL, TSLA, ES, NQ, etc.)

HOW IT WORKS:
1. Reads trading ideas from ideas.txt
2. Spawns up to MAX_PARALLEL_THREADS workers
3. Each thread independently: Research  Backtest  Debug  Optimize
4.  Each successful backtest automatically tests on 25+ data sources!
5. All threads run simultaneously until target returns are hit
6. Thread-safe file naming with unique 2-digit thread IDs
7.  Multi-data results saved to ./results/ folders for each strategy

NEW FEATURES:
-  Color-coded output per thread (Thread 1 = cyan, Thread 2 = magenta, etc.)
-  Rate limiting to avoid API throttling
-  Thread-safe file operations
-  Real-time progress tracking across all threads
-  Clean file organization with thread IDs in names
-   MULTI-DATA TESTING: Validates strategies on 25+ assets/timeframes automatically!
-   CSV results showing performance across all data sources
-  SAFE HEADERS: Meta-sections (-- ... --) in ideas.txt provide strategy generation guidelines
    - Meta-sections are NOT backtested - they shape HOW strategies are created
    - Only blocks starting with [NEW_IDEA] are treated as strategies
    - Backward compatible with existing ideas.txt files

Required Setup:
1. Conda environment 'tflow' with backtesting packages
2. Set MAX_PARALLEL_THREADS (default: 5)
3. Multi-data tester at: DevAntsa_Lab/RBI_Agents/RBI_Bear/multi_data_tester_15min.py
4. Run and watch all ideas process in parallel with multi-data validation! 

IMPORTANT: Each thread is fully independent and won't interfere with others!
"""

# Import execution functionality
import subprocess
import json
from pathlib import Path

# Core imports
import os
import time
import re
import hashlib
import csv
import pandas as pd
from datetime import datetime
from termcolor import cprint
import sys
import argparse  #  Moon Dev: For command-line args
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Semaphore, Thread
from queue import Queue

# Load environment variables FIRST
load_dotenv()
print("Environment variables loaded")

# Add config values directly to avoid import issues
AI_TEMPERATURE = 0.7
AI_MAX_TOKENS = 16000  # Moon Dev: Increased for complete backtest code generation with execution block!

# Import model factory with proper path handling
import sys
from pathlib import Path

# Add MoonDev_Bullshit to path (where src.models.model_factory lives)
moondev_root = Path(__file__).parent.parent.parent.parent / "MoonDev_Bullshit"
sys.path.insert(0, str(moondev_root))

try:
    from src.models import model_factory
    print("Successfully imported model_factory")
except ImportError as e:
    print(f"WARNING: Could not import model_factory: {e}")
    print(f"MoonDev root: {moondev_root}")
    sys.exit(1)

# ============================================
#  PARALLEL PROCESSING CONFIGURATION
# ============================================
MAX_PARALLEL_THREADS = 18  # How many ideas to process simultaneously
RATE_LIMIT_DELAY = .5  # Seconds to wait between API calls (per thread)
RATE_LIMIT_GLOBAL_DELAY = 0.5  # Global delay between any API calls

# Thread color mapping
THREAD_COLORS = {
    0: "cyan",
    1: "magenta",
    2: "yellow",
    3: "green",
    4: "blue"
}

# Global locks
console_lock = Lock()
api_lock = Lock()
file_lock = Lock()
date_lock = Lock()  #  Moon Dev: Lock for date checking/updating

# Rate limiter
rate_limiter = Semaphore(MAX_PARALLEL_THREADS)

# ============================================
#  PROPER TOKEN BUCKET RATE LIMITER
# ============================================
class TokenBucket:
    """
    Thread-safe token bucket rate limiter that releases lock before sleeping.
    """
    def __init__(self, tokens_per_second: float, burst_capacity: int = 10):
        self.tokens_per_second = tokens_per_second
        self.burst_capacity = burst_capacity
        self.tokens = burst_capacity
        self.last_update = time.time()
        self.lock = Lock()
        self.next_allowed_time = time.time()

    def acquire(self):
        while True:
            with self.lock:
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(self.burst_capacity,
                                self.tokens + elapsed * self.tokens_per_second)
                self.last_update = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    self.next_allowed_time = now
                    return
                tokens_needed = 1 - self.tokens
                sleep_time = tokens_needed / self.tokens_per_second
            time.sleep(sleep_time)

# Initialize rate limiter (allow 2 requests per second, burst of 10)
api_rate_limiter = TokenBucket(tokens_per_second=2.0, burst_capacity=10)

#  Moon Dev's Model Configurations
# Available types: "claude", "openai", "deepseek", "groq", "gemini", "xai", "ollama", "openrouter"
#
# OpenRouter Models (just set type="openrouter" and pick any model below):
# - Gemini: google/gemini-2.5-pro, google/gemini-2.5-flash
# - Qwen: qwen/qwen3-vl-32b-instruct, qwen/qwen3-max
# - DeepSeek: deepseek/deepseek-r1-0528
# - OpenAI: openai/gpt-4.5-preview, openai/gpt-5, openai/gpt-5-mini, openai/gpt-5-nano
# - Claude: anthropic/claude-sonnet-4.5, anthropic/claude-haiku-4.5, anthropic/claude-opus-4.1
# - GLM: z-ai/glm-4.6
# See src/models/openrouter_model.py for ALL available models!

# ============================================
#  MODEL STACK CONFIGURATION
# ============================================
# Switch between budget (testing) and premium (production) modes
#
# Set USE_BUDGET_MODELS = True for testing (saves $$$ during debugging)
# Set USE_BUDGET_MODELS = False when agent is working (best quality)
# ============================================

USE_BUDGET_MODELS = False  #  PRODUCTION MODE - Using Grok-4-Fast!

# ============================================
#  BUDGET MODEL STACK (ULTRA-CHEAP FOR TESTING!)
# ============================================
# Testing Mode: Using ULTRA-CHEAP paid models to debug agent workflow
# Cost: ~$0.003 per strategy (100x cheaper than Claude!)
# Quality: Good enough to test workflow, may need more debug iterations
#
# NOTE: Free models have rate limits (16/min) which causes errors with parallel processing!
#       Using cheap PAID models instead for reliable testing.
# ============================================

# Budget Models (ULTRA-CHEAP - DeepSeek V3 is excellent and dirt cheap!)
BUDGET_RESEARCH = {"type": "openrouter", "name": "deepseek/deepseek-chat"}
BUDGET_BACKTEST = {"type": "openrouter", "name": "deepseek/deepseek-chat"}
BUDGET_DEBUG = {"type": "openrouter", "name": "deepseek/deepseek-chat"}
BUDGET_PACKAGE = {"type": "openrouter", "name": "deepseek/deepseek-chat"}
BUDGET_OPTIMIZE = {"type": "openrouter", "name": "deepseek/deepseek-chat"}

# ============================================
#  PREMIUM MODEL STACK (DEEPSEEK-R1 - RELIABLE CODE GENERATION!)
# ============================================
# Production Mode: DeepSeek-R1 for reliable backtest code generation
# Cost: ~$0.03 per strategy (estimated - DeepSeek-R1 pricing)
# Quality: Best for generating correct backtesting.py code
# ============================================

# Premium Models (Grok-4-Fast - Proven Winner!)
PREMIUM_RESEARCH = {"type": "openrouter", "name": "x-ai/grok-4-fast"}
PREMIUM_BACKTEST = {"type": "openrouter", "name": "x-ai/grok-4-fast"}
PREMIUM_DEBUG = {"type": "openrouter", "name": "x-ai/grok-4-fast"}
PREMIUM_PACKAGE = {"type": "openrouter", "name": "x-ai/grok-4-fast"}
PREMIUM_OPTIMIZE = {"type": "openrouter", "name": "x-ai/grok-4-fast"}

# ============================================
#  ACTIVE CONFIGS (Auto-selected based on USE_BUDGET_MODELS)
# ============================================
RESEARCH_CONFIG = BUDGET_RESEARCH if USE_BUDGET_MODELS else PREMIUM_RESEARCH
BACKTEST_CONFIG = BUDGET_BACKTEST if USE_BUDGET_MODELS else PREMIUM_BACKTEST
DEBUG_CONFIG = BUDGET_DEBUG if USE_BUDGET_MODELS else PREMIUM_DEBUG
PACKAGE_CONFIG = BUDGET_PACKAGE if USE_BUDGET_MODELS else PREMIUM_PACKAGE
OPTIMIZE_CONFIG = BUDGET_OPTIMIZE if USE_BUDGET_MODELS else PREMIUM_OPTIMIZE
FALLBACK_CONFIG = {"type": "openrouter", "name": "deepseek/deepseek-chat"}  # Always cheap fallback

#  PROFIT TARGET CONFIGURATION (DEVANTSA CUSTOM - BEAR 15m)
TARGET_RETURN = 100.0  # Target 100% return - push optimization hard
MIN_SHARPE_FOR_SAVE = 0.3  # Minimum Sharpe to save (positive is the goal)
SAVE_IF_OVER_RETURN = 0.0  #  SAVE ALL RESULTS (even negative returns) - See everything in dashboard!
MIN_TRADES_FOR_SAVE = 12  # Minimum trade count for statistical validity

# COMMISSION CONFIGURATION (Bybit taker rate via Crypto Fund Trader)
DEFAULT_COMMISSION = 0.00055  # 0.055% per trade (Bybit taker fee)
COMMISSION_SENSITIVITY_TESTS = [0.0002, 0.00055, 0.001]  # maker, taker, taker+slippage

CONDA_ENV = "tflow"
MAX_DEBUG_ITERATIONS = 10  # Back to 10 - 20 takes too long and times out
MAX_OPTIMIZATION_ITERATIONS = 10  # Increased back to 10 for more thorough optimization
EXECUTION_TIMEOUT = 900  # 15 minutes - increased for 47 data sources (~19 sec per source)

# ============================================
#  DAILY COST LIMIT (SAFETY NET FOR OVERNIGHT RUNS)
# ============================================
MAX_DAILY_COST_USD = 50.0  # Stop processing if today's costs exceed $50
COST_TRACKER_FILE = Path(__file__).parent / "rbi_daily_cost_bear_15min.json"  # Track spending

# DeepSeek Configuration
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

#  Moon Dev: Date tracking for always-on mode - will update when date changes!
CURRENT_DATE = datetime.now().strftime("%m_%d_%Y")

# ============================================
#  COST TRACKING FUNCTIONS
# ============================================
def get_today_cost() -> float:
    """Get today's total RBI agent costs"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")

        if COST_TRACKER_FILE.exists():
            with open(COST_TRACKER_FILE, 'r', encoding='utf-8') as f:
                cost_data = json.load(f)

            if today in cost_data:
                return cost_data[today].get("cost", 0.0)

        return 0.0
    except Exception as e:
        cprint(f" Error reading cost tracker: {e}", "red")
        return 0.0

def add_strategy_cost(estimated_cost: float) -> float:
    """Track cost of processing one strategy and return new total"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")

        # Load existing data
        if COST_TRACKER_FILE.exists():
            with open(COST_TRACKER_FILE, 'r', encoding='utf-8') as f:
                cost_data = json.load(f)
        else:
            cost_data = {}

        # Initialize today if needed
        if today not in cost_data:
            cost_data[today] = {"strategies": 0, "cost": 0.0}

        # Add new cost
        cost_data[today]["strategies"] += 1
        cost_data[today]["cost"] += estimated_cost

        # Save
        COST_TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COST_TRACKER_FILE, 'w', encoding='utf-8') as f:
            json.dump(cost_data, f, indent=2)

        return cost_data[today]["cost"]
    except Exception as e:
        cprint(f" Error tracking cost: {e}", "red")
        return 0.0

def check_cost_limit() -> bool:
    """Check if we've exceeded daily cost limit. Returns True if OK to continue."""
    today_cost = get_today_cost()
    if today_cost >= MAX_DAILY_COST_USD:
        cprint(f"\n DAILY COST LIMIT REACHED: ${today_cost:.2f} / ${MAX_DAILY_COST_USD:.2f}", "red", attrs=['bold'])
        cprint(f" Stopping to prevent overspending. Reset tomorrow!", "yellow")
        return False
    return True

# Update data directory paths - BEAR 15min version (local to RBI_Bear folder)
# Script is in: DevAntsa_Lab/RBI_Agents/RBI_Bear/
SCRIPT_DIR = Path(__file__).parent  # RBI_Bear folder (config, ideas, CSV results)
DEVANTSA_ROOT = Path(__file__).parent.parent.parent  # DevAntsa_Lab folder
PROJECT_ROOT = DEVANTSA_ROOT  # For compatibility
DATA_DIR = DEVANTSA_ROOT / "RBI_Strategy_Code" / "rbi_devantsa"  # Where generated strategy code is saved

#  Moon Dev: These will be updated dynamically when date changes
TODAY_DIR = None
RESEARCH_DIR = None
BACKTEST_DIR = None
PACKAGE_DIR = None
WORKING_BACKTEST_DIR = None
FINAL_BACKTEST_DIR = None
OPTIMIZATION_DIR = None
CHARTS_DIR = None
EXECUTION_DIR = None
REPORTS_DIR = None  # Strategy reports folder

# Tier-based strategy storage (Gold/Silver/Bronze)
GOLD_STRATEGIES_DIR = None
SILVER_STRATEGIES_DIR = None
BRONZE_STRATEGIES_DIR = None
DEVANTSA_WINNERS_DIR = None  # Central repository for all winners

PROCESSED_IDEAS_LOG = SCRIPT_DIR / "processed_ideas_bear_15min.log"
STATS_CSV = SCRIPT_DIR / "backtest_stats_bear_15min.csv"  # Stats tracker for BEAR 15m strategies
IDEAS_FILE = SCRIPT_DIR / "ideas_bear_15min.txt"  # BEAR 15m-specific strategy ideas
CURRENT_REGIME = "BEAR"  # Hardcoded for bear 15min agent

# ============================================
#  PHASE 3A: MULTI-ASSET VALIDATION CONFIG
# ============================================

# Multi-data validation settings
MULTI_DATA_DIR = None  # Will be set dynamically based on CURRENT_REGIME in main()
ENABLE_MULTI_ASSET_VALIDATION = False  # OFF — we review results by hand

# Minimum thresholds for multi-asset tier qualification
MULTI_ASSET_MIN_SOURCES = {
    'GOLD': 5,    # Must pass on 5+ sources
    'SILVER': 3,  # Must pass on 3+ sources
    'BRONZE': 2   # Must pass on 2+ sources (including BTC)
}

MULTI_ASSET_MIN_SHARPE_AVG = {
    'GOLD': 0.6,     # Lowered for 15m (harder to get high Sharpe)
    'SILVER': 0.4,
    'BRONZE': 0.2
}

MULTI_ASSET_MAX_DD_THRESHOLD = {
    'GOLD': -10,    # Tighter for prop-firm compliance
    'SILVER': -15,
    'BRONZE': -20
}

# Minimum overall average return across ALL sources
MULTI_ASSET_MIN_OVERALL_RETURN = {
    'GOLD': 3.0,    # Lowered for 15m bear strategies
    'SILVER': 1.0,
    'BRONZE': 0.0
}

# Performance optimization
RUN_MULTI_DATA_ONLY_IF_BTC_PASSES = True  # Skip multi-data if BTC fails (saves compute)

# ============================================
#  CRYPTO-ONLY TIER SYSTEM CONFIG (NEW!)
# ============================================

# Toggle for crypto-only tier system (independent of traditional multi-asset tiers)
ENABLE_CRYPTO_TIER_SYSTEM = False  # OFF — we review results by hand, no auto-tiering

# Crypto assets list - ONLY these will be tested for crypto tiers
CRYPTO_ASSETS = [
    # Bear 15m assets (only those with verified 15m bear period data)
    "BTC-USD-15m",
    "ETH-USD-15m",
    "SOL-USD-15m",
    "BNB-USD-15m",
]

# Crypto tier thresholds (more lenient than multi-asset due to higher crypto volatility)
CRYPTO_GOLD_THRESHOLD = {
    'min_positive_sources': 3,     # 3 of 4 assets (we only have 4 bear 15m assets)
    'min_avg_sharpe': 0.6,
    'max_avg_drawdown': -10.0,     # Tighter for prop-firm
    'min_avg_return': 3.0,
    'must_pass_btc': False,        # BTC may not be best in bear 15m
}

CRYPTO_SILVER_THRESHOLD = {
    'min_positive_sources': 2,
    'min_avg_sharpe': 0.4,
    'max_avg_drawdown': -15.0,
    'min_avg_return': 1.5,
    'must_pass_major': True,       # Must pass at least one of BTC/ETH/SOL
}

CRYPTO_BRONZE_THRESHOLD = {
    'min_positive_sources': 2,
    'min_avg_sharpe': 0.2,
    'max_avg_drawdown': -20.0,
    'min_avg_return': 0.0,
    'must_pass_major': True,
}

# Crypto tier directories (parallel to traditional tiers)
CRYPTO_GOLD_STRATEGIES_DIR = None
CRYPTO_SILVER_STRATEGIES_DIR = None
CRYPTO_BRONZE_STRATEGIES_DIR = None
CRYPTO_STATS_CSV = SCRIPT_DIR / "backtest_stats_bear_15min_crypto.csv"  # Separate CSV for crypto

# ============================================
#  CRYPTO-ONLY MODE (NEW!)
# ============================================

# When True: Only test crypto assets (moves stocks/forex to backup folder)
# When False: Test all assets (crypto + stocks + forex)
CRYPTO_ONLY_MODE = True  # Set to False for full multi-asset testing

# Assets to exclude in crypto-only mode (stocks + forex)
NON_CRYPTO_ASSETS = [
    "AAPL-USD-1d.csv", "AAPL-USD-1h.csv",
    "GOOGL-USD-1d.csv", "GOOGL-USD-1h.csv",
    "IWM-USD-1d.csv", "IWM-USD-1h.csv",
    "MSFT-USD-1d.csv", "MSFT-USD-1h.csv",
    "NVDA-USD-1d.csv", "NVDA-USD-1h.csv",
    "QQQ-USD-1d.csv", "QQQ-USD-1h.csv",
    "SPY-USD-1d.csv", "SPY-USD-1h.csv",
    "TSLA-USD-1d.csv", "TSLA-USD-1h.csv",
    "EUR-USDT-15m.csv", "EUR-USDT-1h.csv",
]

def update_date_folders():
    """
     Moon Dev's Date Folder Updater!
    Checks if date has changed and updates all folder paths accordingly.
    Thread-safe and works in always-on mode!
    """
    global CURRENT_DATE, TODAY_DIR, RESEARCH_DIR, BACKTEST_DIR, PACKAGE_DIR
    global WORKING_BACKTEST_DIR, FINAL_BACKTEST_DIR, OPTIMIZATION_DIR, CHARTS_DIR, EXECUTION_DIR, REPORTS_DIR
    global GOLD_STRATEGIES_DIR, SILVER_STRATEGIES_DIR, BRONZE_STRATEGIES_DIR, DEVANTSA_WINNERS_DIR
    global CRYPTO_GOLD_STRATEGIES_DIR, CRYPTO_SILVER_STRATEGIES_DIR, CRYPTO_BRONZE_STRATEGIES_DIR  # NEW: Crypto tiers

    with date_lock:
        new_date = datetime.now().strftime("%m_%d_%Y")

        # Check if date has changed
        if new_date != CURRENT_DATE:
            with console_lock:
                cprint(f"\n NEW DAY DETECTED! {CURRENT_DATE}  {new_date}", "cyan", attrs=['bold'])
                cprint(f" Creating new folder structure for {new_date}...\n", "yellow")

            CURRENT_DATE = new_date

        # Update all directory paths (whether date changed or first run)
        TODAY_DIR = DATA_DIR / CURRENT_DATE
        RESEARCH_DIR = TODAY_DIR / "research"
        BACKTEST_DIR = TODAY_DIR / "backtests"
        PACKAGE_DIR = TODAY_DIR / "backtests_package"
        WORKING_BACKTEST_DIR = TODAY_DIR / "backtests_working"
        FINAL_BACKTEST_DIR = TODAY_DIR / "backtests_final"
        OPTIMIZATION_DIR = TODAY_DIR / "backtests_optimized"
        CHARTS_DIR = TODAY_DIR / "charts"
        EXECUTION_DIR = TODAY_DIR / "execution_results"
        REPORTS_DIR = TODAY_DIR / "strategy_reports"  # Comprehensive strategy reports

        # Tier-based strategy storage (daily folders)
        GOLD_STRATEGIES_DIR = TODAY_DIR / "strategies_gold"    # Sharpe>1.5, DD>-15%, Trades>50
        SILVER_STRATEGIES_DIR = TODAY_DIR / "strategies_silver"  # Sharpe>1.2, DD>-20%, Trades>30
        BRONZE_STRATEGIES_DIR = TODAY_DIR / "strategies_bronze"  # Sharpe>1.0, DD>-25%, Trades>20

        # Devantsa Winners - ALL tier-qualified strategies from ALL dates in one place
        DEVANTSA_WINNERS_DIR = DATA_DIR / "Devantsa_Winners"

        # NEW: Crypto-only tier directories (parallel to traditional tiers)
        if ENABLE_CRYPTO_TIER_SYSTEM:
            CRYPTO_GOLD_STRATEGIES_DIR = TODAY_DIR / "strategies_crypto_gold"
            CRYPTO_SILVER_STRATEGIES_DIR = TODAY_DIR / "strategies_crypto_silver"
            CRYPTO_BRONZE_STRATEGIES_DIR = TODAY_DIR / "strategies_crypto_bronze"

        # Create directories if they don't exist
        dirs_to_create = [DATA_DIR, TODAY_DIR, RESEARCH_DIR, BACKTEST_DIR, PACKAGE_DIR,
                          WORKING_BACKTEST_DIR, FINAL_BACKTEST_DIR, OPTIMIZATION_DIR, CHARTS_DIR, EXECUTION_DIR, REPORTS_DIR,
                          GOLD_STRATEGIES_DIR, SILVER_STRATEGIES_DIR, BRONZE_STRATEGIES_DIR, DEVANTSA_WINNERS_DIR]

        # NEW: Add crypto directories if enabled
        if ENABLE_CRYPTO_TIER_SYSTEM:
            dirs_to_create.extend([CRYPTO_GOLD_STRATEGIES_DIR, CRYPTO_SILVER_STRATEGIES_DIR, CRYPTO_BRONZE_STRATEGIES_DIR])

        for dir in dirs_to_create:
            dir.mkdir(parents=True, exist_ok=True)

#  Moon Dev: Initialize folders on startup!
update_date_folders()

# ============================================
#  CRYPTO-ONLY MODE SETUP (NEW!)
# ============================================

def setup_crypto_only_mode():
    """
     Crypto-Only Mode Manager

    When CRYPTO_ONLY_MODE = True:
      - Moves non-crypto CSVs to backup folder
      - Only crypto assets remain in rbi_multi/

    When CRYPTO_ONLY_MODE = False:
      - Restores all CSVs from backup
      - Tests all assets (crypto + stocks + forex)
    """
    # CRITICAL: Skip if MULTI_DATA_DIR not set yet (happens during module import)
    if MULTI_DATA_DIR is None:
        return

    backup_dir = MULTI_DATA_DIR / "_non_crypto_backup"

    if CRYPTO_ONLY_MODE:
        # Move non-crypto assets to backup
        moved_count = 0
        for csv_file in NON_CRYPTO_ASSETS:
            source = MULTI_DATA_DIR / csv_file
            if source.exists():
                backup_dir.mkdir(parents=True, exist_ok=True)
                dest = backup_dir / csv_file
                if not dest.exists():  # Don't overwrite existing backups
                    import shutil
                    shutil.move(str(source), str(dest))
                    moved_count += 1

        if moved_count > 0:
            cprint(f"\n CRYPTO-ONLY MODE ENABLED", "cyan", attrs=['bold'])
            cprint(f"   Moved {moved_count} non-crypto assets to backup", "yellow")
            cprint(f"   Testing ONLY crypto assets ({len(CRYPTO_ASSETS)} assets)\n", "yellow")
    else:
        # Restore non-crypto assets from backup
        if backup_dir.exists():
            restored_count = 0
            for csv_file in NON_CRYPTO_ASSETS:
                source = backup_dir / csv_file
                if source.exists():
                    dest = MULTI_DATA_DIR / csv_file
                    if not dest.exists():  # Don't overwrite existing files
                        import shutil
                        shutil.move(str(source), str(dest))
                        restored_count += 1

            if restored_count > 0:
                cprint(f"\n MULTI-ASSET MODE ENABLED", "cyan", attrs=['bold'])
                cprint(f"   Restored {restored_count} non-crypto assets", "yellow")
                cprint(f"   Testing ALL assets (crypto + stocks + forex)\n", "yellow")

#  Moon Dev: Setup crypto-only mode on startup!
setup_crypto_only_mode()

# ============================================
#  THREAD-SAFE PRINTING
# ============================================

def thread_print(message, thread_id, color=None, attrs=None):
    """Thread-safe colored print with thread ID prefix"""
    if color is None:
        color = THREAD_COLORS.get(thread_id % 5, "white")

    with console_lock:
        prefix = f"[T{thread_id:02d}]"
        cprint(f"{prefix} {message}", color, attrs=attrs)

def thread_print_status(thread_id, phase, message):
    """Print status update for a specific phase"""
    color = THREAD_COLORS.get(thread_id % 5, "white")
    with console_lock:
        cprint(f"[T{thread_id:02d}] {phase}: {message}", color)

# ============================================
#  RATE LIMITING
# ============================================

def rate_limited_api_call(func, thread_id, *args, **kwargs):
    """
    Wrapper for API calls with rate limiting
    - Per-thread rate limiting (RATE_LIMIT_DELAY)
    - Global rate limiting (RATE_LIMIT_GLOBAL_DELAY)
    """
    # Global rate limit (quick check)
    with api_lock:
        time.sleep(RATE_LIMIT_GLOBAL_DELAY)

    # Execute the API call
    result = func(*args, **kwargs)

    # Per-thread rate limit
    time.sleep(RATE_LIMIT_DELAY)

    return result

# ============================================
#  PDF CONTEXT LOADING (Phase 3a Enhancement)
# ============================================

def load_pdf_full_text(pdf_filename: str) -> str | None:
    """
    Load full PDF text from archived text file or extract directly from PDF

    Args:
        pdf_filename: Archive filename (e.g., "20251110_180605_ensemble.pdf")

    Returns:
        Full PDF text or None if file missing/unreadable
    """
    try:
        archive_dir = DATA_DIR / "alpha_archive"

        # Try loading pre-extracted .txt file first (created by alpha_collector_bot)
        txt_file = archive_dir / f"{pdf_filename}.txt"
        if txt_file.exists():
            with open(txt_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Extract content after "FULL PDF TEXT:" marker
            marker = "FULL PDF TEXT:"
            if marker in content:
                full_text = content.split(marker, 1)[1].strip()
                # Truncate if too large (>50KB to avoid token limits)
                if len(full_text) > 50000:
                    full_text = full_text[:50000] + "\n\n[... PDF truncated at 50KB for token limits ...]"
                return full_text
            else:
                return content  # Return entire file if no marker found

        # Fallback: Extract directly from PDF using PyPDF2
        pdf_file = archive_dir / pdf_filename
        if pdf_file.exists():
            try:
                import PyPDF2
                with open(pdf_file, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() + "\n"

                # Truncate if too large
                if len(text) > 50000:
                    text = text[:50000] + "\n\n[... PDF truncated at 50KB for token limits ...]"
                return text.strip()
            except Exception as e:
                cprint(f" PDF extraction failed for {pdf_filename}: {e}", "yellow")
                return None

        # File not found
        return None

    except Exception as e:
        cprint(f" Error loading PDF {pdf_filename}: {e}", "yellow")
        return None


def parse_idea_fields(idea_block: str) -> dict:
    """
    Parse structured [NEW_IDEA] block into fields

    Returns:
    {
        'source': 'telegram_pdf' | 'telegram_llm' | 'paper_derived' | 'telegram' | None,
        'timestamp': '2025-11-10 18:06' | None,
        'content': 'Strategy description...',
        'pdf_file': '20251110_180605_ensemble.pdf' | None,
        'twitter_url': 'https://x.com/...' | None,
        'status': 'pending_research' | 'in_progress' | 'completed' | None,
        'raw': original idea_block string
    }
    """
    fields = {
        'source': None,
        'timestamp': None,
        'content': None,
        'pdf_file': None,
        'twitter_url': None,
        'status': None,
        'raw': idea_block
    }

    lines = idea_block.strip().split('\n')
    for line in lines:
        line = line.strip()
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()

            if key == 'source':
                fields['source'] = value
            elif key == 'timestamp':
                fields['timestamp'] = value
            elif key == 'content':
                fields['content'] = value
            elif key == 'pdf_file':
                fields['pdf_file'] = value
            elif key == 'twitter_url':
                fields['twitter_url'] = value
            elif key == 'status':
                fields['status'] = value

    # If content is still None, use entire block as content (fallback for unstructured ideas)
    if fields['content'] is None:
        fields['content'] = idea_block.strip()

    return fields


def load_meta_sections():
    """
    Load meta-sections (safe headers) from ideas.txt

    Meta-sections are blocks that start and end with '--'
    They contain meta-guidelines for strategy generation (Archetype Engine, Grader Rules, etc.)
    These are NOT strategies to backtest - they shape HOW strategies are created.

    Returns:
        str: Concatenated meta sections text
    """
    global IDEAS_FILE

    if not IDEAS_FILE.exists():
        return ""

    meta_sections = []

    try:
        with open(IDEAS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()

        # Split into blocks (double newline separated)
        blocks = content.split('\n\n')

        for block in blocks:
            stripped = block.strip()
            # Detect meta-sections: start and end with '--'
            if stripped.startswith('--') and stripped.endswith('--'):
                meta_sections.append(block)

    except Exception as e:
        thread_print(f"  Error loading meta sections: {e}", 0, "yellow")
        return ""

    if meta_sections:
        return "\n\n".join(meta_sections)
    else:
        return ""


def parse_strategies_and_meta(content: str) -> tuple:
    """
    Parse ideas.txt content into strategies and meta-sections

    Args:
        content: Full text content of ideas.txt

    Returns:
        tuple: (strategies_list, meta_sections_text)
            - strategies_list: List of strategy idea blocks (start with [NEW_IDEA])
            - meta_sections_text: Concatenated meta-section text (blocks between -- ... --)
    """
    strategies = []
    meta_sections = []

    # Split by [NEW_IDEA] to find strategy blocks
    raw_ideas = content.split('[NEW_IDEA]')

    # First element is everything before first [NEW_IDEA] (header + meta-sections)
    header_section = raw_ideas[0] if raw_ideas else ""

    # Extract meta-sections from header
    header_blocks = header_section.split('\n\n')
    for block in header_blocks:
        stripped = block.strip()
        if stripped.startswith('--') and stripped.endswith('--'):
            meta_sections.append(block)

    # Process strategy blocks (skip first element which is header)
    for idea in raw_ideas[1:]:
        idea = idea.strip()
        if idea:  # Only include non-empty ideas
            strategies.append(idea)

    meta_text = "\n\n".join(meta_sections) if meta_sections else ""

    return strategies, meta_text


# ============================================
#  PROMPTS (Same as v3)
# ============================================

RESEARCH_PROMPT = """
You are Devantsa's Research AI

IMPORTANT NAMING RULES:
1. Create a UNIQUE TWO-WORD NAME for this specific strategy
2. The name must be DIFFERENT from any generic names like "TrendFollower" or "MomentumStrategy"
3. First word should describe the main approach (e.g., Adaptive, Neural, Quantum, Fractal, Dynamic)
4. Second word should describe the specific technique (e.g., Reversal, Breakout, Oscillator, Divergence)
5. Make the name SPECIFIC to this strategy's unique aspects

Examples of good names:
- "AdaptiveBreakout" for a strategy that adjusts breakout levels
- "FractalMomentum" for a strategy using fractal analysis with momentum
- "QuantumReversal" for a complex mean reversion strategy
- "NeuralDivergence" for a strategy focusing on divergence patterns

BAD names to avoid:
- "TrendFollower" (too generic)
- "SimpleMoving" (too basic)
- "PriceAction" (too vague)

Output format must start with:
STRATEGY_NAME: [Your unique two-word name]

Then analyze the trading strategy content and create detailed instructions.
Focus on:
1. Key strategy components
2. Entry/exit rules
3. Risk management
4. Required indicators

PDF CONTEXT INSTRUCTIONS (CRITICAL - READ CAREFULLY):
If full PDF text from an academic paper is provided below, YOU MUST extract:
1. EXACT parameter values from tables, figures, and results sections
   - Look for "optimal parameters", "best performing", "recommended values"
   - Extract specific numbers: lookback periods, thresholds, percentiles
2. MATHEMATICAL FORMULAS and precise thresholds
   - Entry conditions with exact operators (>, <, >=, <=)
   - Exit conditions with specific percentage values
3. SPECIFIC entry/exit logic from methodology section
   - Step-by-step implementation from the paper
   - Conditional logic (IF/THEN rules)
4. RISK MANAGEMENT rules tested in the paper
   - Stop loss percentages
   - Position sizing rules
   - Maximum drawdown limits
5. BACKTEST RESULTS to validate parameters
   - Which parameter combinations worked best?
   - What timeframes were tested?

DO NOT create generic variations - implement the EXACT strategy from the paper!
If the PDF describes "28-day lookback with 5-day holding", use those EXACT values.
If it says "top tercile (66.67th percentile)", use 66.67%, not "top third" or 70%.

Your complete output must follow this format:
STRATEGY_NAME: [Your unique two-word name]

STRATEGY_DETAILS:
[Your detailed analysis with EXACT parameters from PDF]

Remember: The name must be UNIQUE and SPECIFIC to this strategy's approach!
"""

BACKTEST_PROMPT = """
You are a Python code generator for BEAR market trading strategies.

========================================================================
⚠️ CRITICAL: POSITION MANAGEMENT - READ THIS FIRST! ⚠️
========================================================================

BANNED ATTRIBUTES & METHODS (DO NOT EXIST IN BACKTESTING.PY):
❌ self.position.sl - DOES NOT EXIST
❌ self.position.tp - DOES NOT EXIST
❌ self.position.entry_price - DOES NOT EXIST
❌ self.position.entry_bar - DOES NOT EXIST
❌ self._broker.get_cash() - DOES NOT EXIST (use self.equity instead)
❌ self._broker.get_value() - DOES NOT EXIST (use self.equity instead)
❌ Using self.buy(size=...) to close SHORT positions - WRONG (use self.position.close())

REQUIRED: Track ALL position data manually as class variables!
✅ Use self.equity for account value (NOT self._broker methods)

✅ CORRECT PATTERN:
```python
class BearStrategy(Strategy):
    def init(self):
        # Manual tracking (REQUIRED!)
        self.entry_price = None
        self.target_price = None
        self.bars_in_trade = 0
        # 3+ Indicators...

    def next(self):
        if not self.position:
            if <condition_1> and <condition_2> and <condition_3>:  # 3+ conditions!
                # Calculate prices HERE
                self.entry_price = self.data.Close[-1]
                stop_dist = 1.8 * self.atr[-1]
                self.target_price = self.entry_price * 0.99  # Fixed 1% target

                # Pass sl to sell() call
                # DO NOT use self._broker methods - use self.equity instead!
                self.sell(sl=self.entry_price + stop_dist)
                self.bars_in_trade = 0

        elif self.position.is_short:
            self.bars_in_trade += 1

            # Fixed target exit (NO trailing stop, NO multi-tier TP)
            if self.data.Close[-1] <= self.target_price:
                self.position.close()  # Take profit
            elif self.bars_in_trade >= 40:
                self.position.close()  # Max hold exit (30-50 bars)
```

If you use self.position.sl or self.position.entry_price, the code will be REJECTED by health check!

========================================================================

ROLE:
- Generate backtesting.py compatible code for bear market PURE SHORT strategies (SHORT ONLY)
- Target 2022 bear market data on 15-MINUTE timeframe (~35,000 bars, full year)
- Commission: 0.055% per trade (0.11% round-trip). Real friction with slippage: ~0.10% round-trip
- PRIMARY ASSET: BTC (best fit for live trading loop — no direction conflicts in bear regime)
- Goal: 30-120 trades, positive Sharpe, avg profit-per-trade >= 0.4%
- DESIGN: 3+ entry conditions (extremely selective), fixed 1-1.5% profit target, max 30-50 bars hold
- Strategy must be SELECTIVE — only fire during real breakdowns, not every red candle
- Bear moves are violent but brief. Quick profit capture (1-2%), then get out. No home runs.

MANDATORY OUTPUT CONSTRAINTS:
1. NO emojis ANYWHERE in code (Windows CP1252 encoding will CRASH)
2. ALWAYS use raw strings for file paths: r'c:\\Users\\...' (prevents Unicode escape errors)
3. ONLY return code (no explanatory text)
4. Include complete if __name__ == "__main__" block
5. Use multi_data_tester for cross-validation
6. NEVER use self.position.sl or self.position.entry_price (see above!)
7. NEVER use self._broker.get_cash() or self._broker.get_value() (use self.equity)
8. NEVER use self.buy(size=...) to close SHORT positions (use self.position.close())

========================================================================
BACKTESTING.PY API RULES
========================================================================

CRITICAL: self.data.Close is _Array (NOT pandas Series)
BANNED methods: .shift(), .rolling(), .iloc[], .values, .pct_change()

ALL calculations MUST use self.I() wrapper:
```python
self.rsi = self.I(RSI, self.data.Close, 14)
self.low_14 = self.I(lambda x: pd.Series(x).rolling(14).min(), self.data.Low)
self.momentum = self.I(lambda c: pd.Series(c).pct_change(7), self.data.Close)
```

========================================================================
CRITICAL: POSITION MANAGEMENT (READ THIS FIRST!)
========================================================================

⚠️ BANNED - These DO NOT exist in backtesting.py:
- self.position.sl (DOES NOT EXIST)
- self.position.tp (DOES NOT EXIST)
- self.position.entry_price (DOES NOT EXIST)
- self.position.entry_bar (DOES NOT EXIST)

✅ REQUIRED - Track manually as class variables:
```python
class MyStrategy(Strategy):
    def init(self):
        self.entry_price = None  # Track manually
        self.target_price = None # Track manually (fixed % target)
        self.bars_in_trade = 0   # Track manually

        # 3+ Indicators here (structure + momentum + confirmation)...

    def next(self):
        # Entry - 3+ conditions, calculate target HERE
        if not self.position:
            if <cond_1> and <cond_2> and <cond_3>:  # 3+ conditions!
                self.entry_price = self.data.Close[-1]
                stop_dist = 1.8 * self.atr[-1]
                self.target_price = self.entry_price * 0.99  # Fixed 1% target

                self.sell(sl=self.entry_price + stop_dist)  # Pass sl to sell()
                self.bars_in_trade = 0

        # Exit - fixed target OR max hold (NO trailing, NO multi-tier)
        elif self.position.is_short:
            self.bars_in_trade += 1

            if self.data.Close[-1] <= self.target_price:
                self.position.close()  # Fixed profit target
            elif self.bars_in_trade >= 40:
                self.position.close()  # Max hold exit (30-50 bars)
```

DO NOT use self.position.sl or self.position.entry_price - they will cause HEALTH CHECK FAILURES!

========================================================================
STRATEGY REQUIREMENTS (EXPERT-VALIDATED DESIGN FOR 15m SHORT)
========================================================================

ENTRY LOGIC:
- MINIMUM 3 conditions (2 is too loose on 15m — proven by 52 failed strategies)
- Expected trades: 30-120 on ~35,000 bars (full year 2022)
- PURE SHORT strategies ONLY
- Strategy must be EXTREMELY SELECTIVE — only fire during real breakdowns
- Avg profit-per-trade MUST be >= 0.4% (below this, friction kills the edge)

ENTRY CONDITION DESIGN (pick 3+ from these categories):
Category A — Breakdown structure:
  - Close < Low(14-30).shift(1) (breakdown below recent lows)
  - Close < SMA(50) * 0.97-0.99 (well below moving average)
  - Close < EMA(20) AND EMA(20) < EMA(50) (trend alignment)
Category B — Momentum confirmation:
  - Momentum(14-30) < -0.03 to -0.06 (sustained crash)
  - RSI(14) < 35 (deep oversold = already crashing)
  - MACD histogram < 0 AND declining
Category C — Volume/volatility confirmation:
  - Volume > 1.8-2.5x rolling avg (panic/liquidation volume)
  - ATR expanding (current ATR > ATR.shift(5))

COMBINE: At least 1 from Category A + 1 from Category B + 1 from Category C
This ensures: structure break + momentum + confirmation = high-quality signal

WARNING: 200+ trades = OVERTRADING. 3 conditions should naturally limit to 30-120 range.

BANNED:
- 2-condition entries (too loose, proven failure across 52 strategies)
- LONG strategies (SHORT only system)
- Overbought-at-premium entries (0/35 winners in Batches 1-2)
- Trailing stops (bear moves on 15m don't trend long enough)
- Multi-tier TP systems (TP1/TP2 — too complex, hold too long)

RISK MANAGEMENT (MANUAL TRACKING REQUIRED):
- Stop = 1.5-2.0x ATR(14) ABOVE entry (pass to sell(sl=...) call)
- Risk per trade: 0.35-0.50% of equity
- Size = (Equity * risk) / Stop Distance   (e.g., 1M * 0.004 / stop_dist)
- Take profit: SINGLE fixed target at 1.0-1.5% below entry (NO multi-tier)
  - target_price = entry_price * (1 - target_pct) where target_pct = 0.01 to 0.015
- Max hold: 30-50 bars (7.5-12.5 hours). If it hasn't worked by then, the move is over.
- NO trailing stop — use fixed target exit
- Track entry_price, target_price, and bars_in_trade manually

EXIT PRIORITY:
1. Fixed profit target hit (1-1.5% below entry) -> close entire position
2. Max hold bars exceeded (30-50 bars) -> close entire position
3. Stop loss hit (1.5-2.0x ATR above entry) -> automatic via sl= parameter
Optional: indicator recovery exit (e.g., RSI crosses back above 50 = move is over)

INDICATOR THRESHOLDS (SHORT — selective entry):
- Momentum(14-30): < -0.03 to -0.06 (price must already be crashing)
- Volume: > 1.8-2.5x rolling avg (20-25 bar period)
- RSI(14): < 30-40 (confirms momentum crash)
- SMA/EMA: Close below by 1-3% (structure broken)
- Low(14-30): Close < Low.shift(1) (new lows being made)
- ATR: period=14 (for stop calculation)
- MACD: histogram negative and falling (trend confirmation)

========================================================================
HELPER FUNCTIONS (USE THESE)
========================================================================

```python
def RSI(close, period=14):
    delta = pd.Series(close).diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(high, low, close, period=14):
    high, low, close = pd.Series(high), pd.Series(low), pd.Series(close)
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()
```

========================================================================
COMPLETE STRATEGY TEMPLATE (EXPERT-VALIDATED FOR 15m SHORT)
========================================================================

```python
from backtesting import Backtest, Strategy
import pandas as pd
import numpy as np

def RSI(close, period=14):
    delta = pd.Series(close).diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(high, low, close, period=14):
    high, low, close = pd.Series(high), pd.Series(low), pd.Series(close)
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()

class BearShortStrategy(Strategy):
    def init(self):
        # Entry tracking (manual — required)
        self.entry_price = None
        self.target_price = None
        self.bars_in_trade = 0

        # 3+ indicators for entry (structure + momentum + volume confirmation)
        self.sma_50 = self.I(lambda c: pd.Series(c).rolling(50).mean(), self.data.Close)
        self.momentum_20 = self.I(lambda c: pd.Series(c).pct_change(20), self.data.Close)
        self.vol_avg = self.I(lambda v: pd.Series(v).rolling(22).mean(), self.data.Volume)
        self.atr = self.I(calculate_atr, self.data.High, self.data.Low, self.data.Close, 14)

    def next(self):
        # Entry: 3 conditions (structure break + momentum crash + volume surge)
        if not self.position:
            if (self.data.Close[-1] < self.sma_50[-1] * 0.98
                    and self.momentum_20[-1] < -0.04
                    and self.data.Volume[-1] > 2.0 * self.vol_avg[-1]):

                self.entry_price = self.data.Close[-1]
                stop_dist = 1.8 * self.atr[-1]
                self.target_price = self.entry_price * 0.99  # Fixed 1% profit target

                self.sell(sl=self.entry_price + stop_dist)
                self.bars_in_trade = 0

        # Exit: fixed target OR max hold (NO trailing stop, NO multi-tier TP)
        elif self.position.is_short:
            self.bars_in_trade += 1

            # Fixed profit target hit
            if self.data.Close[-1] <= self.target_price:
                self.position.close()
            # Max hold exit (30-50 bars = 7.5-12.5 hours)
            elif self.bars_in_trade >= 40:
                self.position.close()

if __name__ == "__main__":
    import sys

    data = pd.read_csv(r'c:\\Users\\anton\\MoneyGlich\\moon-dev-ai-agents\\DevAntsa_Lab\\RBI_Agents\\RBI_Bear\\rbi_regime_bear\\BTC-USD-15m.csv')
    data['datetime'] = pd.to_datetime(data['datetime'])
    data = data.set_index('datetime')
    data.columns = ['Open', 'High', 'Low', 'Close', 'Volume']

    bt = Backtest(data, BearShortStrategy, cash=1_000_000, commission=0.00055)
    stats = bt.run()

    print("\\n" + "="*80)
    print("BACKTEST STATISTICS")
    print("="*80)
    print(stats)
    print("="*80 + "\\n")

    sys.path.append(r'c:\\Users\\anton\\MoneyGlich\\moon-dev-ai-agents\\DevAntsa_Lab\\RBI_Agents\\RBI_Bear')
    from multi_data_tester_15min import test_on_all_data

    print("="*80)
    print("MULTI-DATA BACKTEST - Testing on Bear 15m Assets")
    print("="*80)

    results = test_on_all_data(BearShortStrategy, 'BearShortStrategy', regime='BEAR', verbose=False)

    if results is not None:
        print(f"\\nTested on {len(results)} sources")
    else:
        print("\\nNo results - check errors above")
```

========================================================================
CHECKLIST (verify before generating)
========================================================================

✓ MINIMUM 3 entry conditions (structure + momentum + confirmation)
✓ Target 30-120 trades on ~35000 bars (200+ = OVERTRADING)
✓ SINGLE fixed profit target: 1.0-1.5% below entry (NO multi-tier TP)
✓ Stop: 1.5-2.0x ATR(14) above entry
✓ Max hold: 30-50 bars (7.5-12.5 hours, NOT 64-85)
✓ NO trailing stop — fixed target exit only
✓ Risk: 0.35-0.50% per trade
✓ Avg profit-per-trade must be >= 0.4% (friction kills anything lower)
✓ NO percentile ranking
✓ Includes if __name__ == "__main__"
✓ NO emojis

ONLY SEND BACK CODE. NO OTHER TEXT.
"""


OPTIMIZE_PROMPT = """
You are Devantsa's Optimization AI
Your job is to IMPROVE the strategy using MULTI-OBJECTIVE OPTIMIZATION.

========================================================================
CRITICAL: NO EMOJIS & USE RAW STRINGS - WINDOWS COMPATIBILITY!
========================================================================
1. ABSOLUTELY NO Unicode/Emoji characters in ANY print() statements!
   The code runs on Windows which CANNOT handle emoji characters.

   FORBIDDEN: \\U0001f319 (moon), \\U0001f680 (rocket), ANY emoji
   WRONG: print("\\U0001f319 MOON LONG...")  <- CRASHES ON WINDOWS
   RIGHT: print("MOON LONG...")              <- WORKS

2. ALWAYS use raw strings (r prefix) for file paths:
   WRONG: data = pd.read_csv('c:\\Users\\anton\\...')  <- Unicode escape error
   RIGHT: data = pd.read_csv(r'c:\\Users\\anton\\...')  <- Works

Remove ALL emojis and FIX ALL file paths in your optimized code!
========================================================================

CURRENT PERFORMANCE:
Return [%]: {current_return}%
TARGET RETURN: {target_return}% (aspirational goal)

 PHASE 2: MULTI-OBJECTIVE OPTIMIZATION

Your optimization goal is NOT just raw returns, but a COMPOSITE SCORE that balances:
- 40% Sharpe Ratio (risk-adjusted returns are the priority!)
- 30% Raw Returns (still important, but balanced)
- 20% Drawdown Protection (minimize max drawdown)
- 10% Win Rate (trading consistency)

CRITICAL: Improving Sharpe Ratio by 0.5 is MORE valuable than improving returns by 5%!
Focus on strategies that win consistently with low drawdown, not just high returns.

YOUR MISSION: Optimize this strategy to maximize the COMPOSITE SCORE!

OPTIMIZATION TECHNIQUES TO CONSIDER:
1. **Entry Optimization:**
   - Tighten entry conditions to catch better setups
   - Add filters to avoid low-quality signals
   - Use multiple timeframe confirmation
   - Add volume/momentum filters

2. **Exit Optimization:**
   - Improve take profit levels
   - Add trailing stops
   - Use dynamic position sizing based on volatility
   - Scale out of positions

3. **Risk Management:**
   - Adjust position sizing
   - Use volatility-based position sizing (ATR)
   - Add maximum drawdown limits
   - Improve stop loss placement

4. **Indicator Optimization:**
   - Fine-tune indicator parameters
   - Add complementary indicators
   - Use indicator divergence
   - Combine multiple timeframes

5. **Market Regime Filters:**
   - Add trend filters
   - Avoid choppy/ranging markets
   - Only trade in favorable conditions

IMPORTANT RULES:
- DO NOT break the code structure
- Keep all debug prints (but NO EMOJIS in print statements!)
- Maintain proper backtesting.py format
- Use self.I() for all indicators
- Position sizes must be int or fraction (0-1)
- Focus on REALISTIC improvements (no curve fitting!)
- Explain your optimization changes in code comments

Return the COMPLETE optimized code with plain text comments explaining what you improved!
ONLY SEND BACK CODE, NO OTHER TEXT.
"""

PACKAGE_PROMPT = """
You are Devantsa's Package AI
Your job is to ensure the backtest code NEVER uses ANY backtesting.lib imports or functions.

 STRICTLY FORBIDDEN:
1. from backtesting.lib import *
2. import backtesting.lib
3. from backtesting.lib import crossover
4. ANY use of backtesting.lib

 REQUIRED REPLACEMENTS:
1. For crossover detection:
   Instead of: backtesting.lib.crossover(a, b)
   Use: (a[-2] < b[-2] and a[-1] > b[-1])  # for bullish crossover
        (a[-2] > b[-2] and a[-1] < b[-1])  # for bearish crossover

2. For indicators:
   - Use pandas/numpy for ALL indicators (NO talib, NO pandas-ta)
   - SMA: lambda x, n: pd.Series(x).rolling(n).mean()
   - RSI: Use helper function with pandas
   - ALWAYS wrap in self.I()

3. For signal generation:
   - Use numpy/pandas boolean conditions
   - Use rolling window comparisons with array indexing
   - Use mathematical comparisons (>, <, ==)

Example conversions:
 from backtesting.lib import crossover
 if crossover(fast_ma, slow_ma):
 if fast_ma[-2] < slow_ma[-2] and fast_ma[-1] > slow_ma[-1]:

 self.sma = self.I(backtesting.lib.SMA, self.data.Close, 20)
 self.sma = self.I(lambda x, n: pd.Series(x).rolling(n).mean(), self.data.Close, 20)

IMPORTANT: Scan the ENTIRE code for any backtesting.lib usage and replace ALL instances!

CRITICAL WINDOWS COMPATIBILITY:
1. NO EMOJIS - plain ASCII only (Windows CP1252 encoding will CRASH)
2. ALWAYS use raw strings for file paths: r'c:\\Users\\...' (prevents Unicode escape errors)

Return the complete fixed code!
ONLY SEND BACK CODE, NO OTHER TEXT.
"""

DEBUG_PROMPT = """
You are Devantsa's Debug AI
Fix technical issues in the backtest code WITHOUT changing the strategy logic.

========================================================================
CRITICAL: NO EMOJIS IN PRINT STATEMENTS - WINDOWS COMPATIBILITY!
========================================================================
ABSOLUTELY NO Unicode/Emoji characters in ANY print() statements!
Windows CP1252 encoding CANNOT handle emojis - code will CRASH!

CORRECT EXAMPLES:
 print("Devantsa: Initializing...")
 print("Devantsa: Entry signal detected")

Remove ALL emojis from ALL print statements in your fix!
========================================================================

========================================================================
 COMMON ERROR PATTERNS - STUDY THESE BEFORE DEBUGGING!
========================================================================

 ERROR #1: AttributeError: '_Array' object has no attribute 'shift'
(Also: .rolling(), .iloc, .values, .pct_change())

CAUSE: Using pandas methods directly on backtesting _Array objects
The self.data.Close, self.data.High, etc. are _Array objects, NOT pandas Series!

WRONG CODE THAT CAUSES THIS:
```python
def init(self):
    shifted = self.data.Close.shift(1)  # CRASH
    rolling = self.data.High.rolling(20).mean()  # CRASH
```

CORRECT FIX - Wrap in self.I() with pd.Series conversion:
```python
def init(self):
    self.shifted = self.I(lambda x: pd.Series(x).shift(1), self.data.Close)
    self.rolling = self.I(lambda x: pd.Series(x).rolling(20).mean(), self.data.High)
```

If you see this error pattern in a function being called from self.I():
```python
# WRONG: Function tries to use .shift() on raw array
def my_indicator(data):
    return data.shift(1)  # CRASH if data is _Array

self.ind = self.I(my_indicator, self.data.Close)
```

Fix by converting to pandas INSIDE the function:
```python
# CORRECT: Convert to pandas inside the function
def my_indicator(data):
    return pd.Series(data).shift(1)  # Now works!

self.ind = self.I(my_indicator, self.data.Close)
```

 ERROR #2: AttributeError: 'Position' object has no attribute 'entry_price'
(Also: .sl, .entry_bar, .tp)

CAUSE: Trying to access position attributes that don't exist

WRONG CODE:
```python
if self.position:
    entry_price = self.position.entry_price  # DOES NOT EXIST
    if Close[-1] > self.position.sl:  # DOES NOT EXIST
```

CORRECT FIX - Track manually as class variables:
```python
class MyStrategy(Strategy):
    def init(self):
        self.entry_price = None
        self.stop_loss = None

    def next(self):
        # On entry
        if not self.position and <buy_signal>:
            self.entry_price = self.data.Close[-1]
            self.stop_loss = self.data.Low[-1] * 0.98
            self.buy()

        # On exit
        if self.position:
            if self.data.Close[-1] <= self.stop_loss:
                self.position.close()
                self.entry_price = None
```

Available position attributes you CAN use:
- self.position.size (current size)
- self.position.pl (profit/loss $)
- self.position.pl_pct (profit/loss %)
- self.position.is_long (boolean)
- self.position.is_short (boolean)

 ERROR #3: AssertionError: size must be a positive fraction of equity, or a positive whole number

CAUSE: Invalid size value passed to self.buy(size=X) or self.sell(size=X)

Common invalid sizes:
- size = 0 (from bad math)
- size < 0 (negative from subtraction)
- size = NaN (from division by zero)
- size = 1.5 (not fraction, not whole number)

WRONG CODE:
```python
risk_per_unit = atr[-1] * 2
size = (self.equity * 0.02) / risk_per_unit  # Can be 0 or invalid!
self.buy(size=size)  # CRASH if size is 0, negative, or NaN
```

CORRECT FIX - Always validate and clamp:
```python
risk_per_unit = max(atr[-1] * 2, 0.001)  # Prevent div by zero
raw_size = (self.equity * 0.02) / risk_per_unit

# Clamp to valid range: 1% to 50%
size = max(0.01, min(0.5, raw_size))

# Final validation before buy
if size > 0 and size < 1:
    self.buy(size=size)
else:
    self.buy(size=0.05)  # Safe fallback
```

UNIVERSAL SAFE PATTERN - Use this:
```python
def get_safe_position_size(self):
    # Your size calculation
    calculated_size = 0.02  # or your formula

    # MANDATORY: Clamp between 1% and 50%
    safe_size = max(0.01, min(0.5, calculated_size))

    # Return only if valid fraction
    return safe_size if (safe_size > 0 and safe_size < 1) else 0.05
```

 ERROR #4: ModuleNotFoundError: No module named 'talib'

CAUSE: Trying to import talib which is not installed

WRONG CODE:
```python
import talib
self.rsi = self.I(talib.RSI, self.data.Close, 14)
```

CORRECT FIX - Replace with pandas implementation:
```python
# Remove: import talib

def RSI(close, period=14):
    delta = pd.Series(close).diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# In init():
self.rsi = self.I(RSI, self.data.Close, 14)
```

Other talib replacements:
- talib.SMA  lambda x, n: pd.Series(x).rolling(n).mean()
- talib.EMA  lambda x, n: pd.Series(x).ewm(span=n).mean()
- talib.BBANDS  Calculate manually with rolling std
- talib.ATR  Calculate from High-Low ranges

 ERROR #5: UnicodeEncodeError: 'charmap' codec can't encode character '\\U0001f319'

CAUSE: Emoji in print statements (Windows can't handle Unicode emojis)

WRONG CODE:
```python
print("\\U0001f319 Moon Dev Long Signal")  # CRASH
```

CORRECT FIX - Remove all emojis:
```python
print("Devantsa Long Signal")  # Plain ASCII only
```

Scan ALL print() statements and remove:
- \\U0001f319 (moon)
- \\U0001f680 (rocket)
- Any other \\U codes
- Check marks, stars, etc.

 ERROR #6: Partial Position Close Errors

CAUSE: Using wrong method to close partial positions (2-tier TP)

WRONG CODE:
```python
# Tier 1 TP - WRONG approach
if not self.tier1_hit and self.data.Close[-1] <= self.tp1_price:
    half_size = abs(self.position.size) * 0.5
    self.buy(size=half_size)  # WRONG - causes errors
    self.tier1_hit = True
```

CORRECT FIX - Use position.close() with fraction:
```python
# Tier 1 TP - CORRECT approach
if not self.tier1_hit and self.data.Close[-1] <= self.tp1_price:
    self.position.close(0.5)  # Closes 50% of position automatically
    self.tier1_hit = True
```

For 2-tier TP exits:
- Tier 1: self.position.close(0.5) - closes 50%
- Tier 2: self.position.close() - closes remaining 50%
- Max hold: self.position.close() - closes all

NEVER use self.buy(size=...) to close SHORT positions - use self.position.close() instead!

 ERROR #7: Unicode Escape Errors in File Paths

CAUSE: File paths with \\U (like \\Users) interpreted as Unicode escape sequences

WRONG CODE:
```python
data = pd.read_csv('c:\\Users\\anton\\MoneyGlich\\moon-dev-ai-agents\\DevAntsa_Lab\\RBI_Agents\\RBI_Bear\\rbi_regime_bear\\BTC-USD-15m.csv')
# ERROR: (unicode error) 'unicodeescape' codec can't decode bytes in position 2-3: truncated \\UXXXXXXXX escape
```

CORRECT FIX - Use raw string (r prefix):
```python
data = pd.read_csv(r'c:\\Users\\anton\\MoneyGlich\\moon-dev-ai-agents\\DevAntsa_Lab\\RBI_Agents\\RBI_Bear\\rbi_regime_bear\\BTC-USD-15m.csv')
```

ALWAYS use raw strings for file paths on Windows:
- data = pd.read_csv(r'path\\to\\file.csv')
- sys.path.append(r'path\\to\\directory')
- open(r'path\\to\\file.txt')

The r prefix tells Python NOT to interpret backslash escape sequences!

========================================================================
 DEBUGGING PROCESS - FOLLOW THESE STEPS:
========================================================================

Step 1: READ THE ERROR MESSAGE
- Identify which of the 7 common errors above it matches
- Look at the line number where error occurred

Step 2: APPLY THE CORRECT FIX PATTERN
- Use the "CORRECT FIX" code from above
- Don't guess - use exact pattern shown

Step 3: SCAN FOR RELATED ISSUES
- If fixing _Array.shift(), check for ALL pandas methods (.rolling, .iloc, etc.)
- If fixing position.entry_price, check for position.sl, position.tp too
- If fixing one size calculation, check ALL buy/sell calls

Step 4: VALIDATE YOUR FIX
- Does the fixed code follow the correct pattern exactly?
- Did you add safety checks (max/min clamping for size)?
- Did you wrap indicators in self.I()?

Step 5: RETURN COMPLETE CODE
- Return the ENTIRE fixed code
- Don't skip any parts
- Remove ALL emojis from print statements

========================================================================
END OF COMMON ERROR PATTERNS
========================================================================

CRITICAL ERROR TO FIX:
{error_message}

CRITICAL DATA LOADING REQUIREMENTS:
The CSV file has these exact columns after processing:
- datetime, open, high, low, close, volume (all lowercase after .str.lower())
- After capitalization: Datetime, Open, High, Low, Close, Volume

CRITICAL BACKTESTING REQUIREMENTS:
1. Data Loading Rules:
   - Use data.columns.str.strip().str.lower() to clean columns
   - Drop unnamed columns: data.drop(columns=[col for col in data.columns if 'unnamed' in col.lower()])
   - Rename columns properly: data.rename(columns={{'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}})
   - Set datetime as index: data = data.set_index(pd.to_datetime(data['datetime']))

2. Position Sizing Rules:
   - Must be either a fraction (0 < size < 1) for percentage of equity
   - OR a positive whole number (round integer) for units
   - NEVER use floating point numbers for unit-based sizing

3. Indicator Issues:
   - Cannot use .shift() on backtesting indicators
   - Use array indexing like indicator[-2] for previous values
   - All indicators must be wrapped in self.I()

4. Position Object Issues:
   - Position object does NOT have .entry_price attribute
   - Use self.trades[-1].entry_price if you need entry price from last trade
   - Available position attributes: .size, .pl, .pl_pct
   - For partial closes (2-tier TP):
     ✅ CORRECT: self.position.close(0.5)  # Closes 50% of position
     ❌ WRONG: half_size = abs(self.position.size) * 0.5; self.buy(size=half_size)  # DO NOT DO THIS!
   - For stop losses: use sl= parameter in buy/sell calls, not in position.close()

5. Broker API - CRITICAL CORRECTIONS:
   - NEVER use self._broker.get_cash() - THIS DOES NOT EXIST
   - NEVER use self._broker.get_value() - THIS DOES NOT EXIST
   - CORRECT: Use self.equity to get current account value
   - Example: available_cash = self.equity (NOT self._broker.get_cash())
   - Example: account_value = self.equity (NOT self._broker.get_value())

6. Position Sizing - CRITICAL VALIDATION:
   - ERROR: "AssertionError: size must be a positive fraction of equity, or a positive whole number of units"
   - CAUSE: Passing invalid size to self.buy(size=...) or self.sell(size=...)
   - size must be: 0 < size < 1 (fraction) OR size >= 1 (whole number)
   - ALWAYS validate size before buy/sell:

     CORRECT PATTERN:
     size = calculate_position_size()  # Your size calculation
     if size > 0:  # CRITICAL: Validate before calling buy/sell
         self.buy(size=size, sl=..., tp=...)

     OR use max() to ensure minimum:
     size = max(0.01, your_calculation)  # Ensures at least 1% position
     self.buy(size=size, sl=..., tp=...)

   - Common causes of invalid size:
     * Division by zero (e.g., risk / (atr * 0) when atr is 0)
     * Negative values from bad math
     * Zero from overly restrictive conditions

7. No Trades Issue (Signals but no execution):
   - If strategy prints "ENTRY SIGNAL" but shows 0 trades, the self.buy() call is not executing
   - Common causes: invalid size parameter, insufficient cash, missing self.buy() call
   - Ensure self.buy() is actually called in the entry condition block
   - Check size parameter: must be fraction (0-1) or positive integer
   - Verify cash/equity is sufficient for the trade size

Focus on:
1. KeyError issues with column names
2. Syntax errors and import statements
3. Indicator calculation methods
4. Data loading and preprocessing
5. Position object attribute errors (.entry_price, .close() parameters)
6. Broker API errors (_broker.get_cash(), _broker.get_value() - replace with self.equity)
7. Position sizing errors (ALWAYS validate size > 0 before buy/sell)

DO NOT change strategy logic, entry/exit conditions, or risk management rules.

Return the complete fixed code with PLAIN TEXT debug prints (NO EMOJIS)!
ONLY SEND BACK CODE, NO OTHER TEXT.
"""

# ============================================
#  REGIME-SPECIFIC OVERRIDE SECTIONS
# ============================================

BEAR_REGIME_OVERRIDES = """
================================================================================
CRITICAL: BEAR MARKET REGIME DETECTED - OVERRIDE RULES BELOW TAKE PRECEDENCE!
================================================================================

When generating code for BEAR market strategies, the rules below OVERRIDE any
conflicting rules in the base prompt. If there's a conflict, ALWAYS follow
the BEAR-specific rules!

TRADE FREQUENCY OVERRIDE (BEAR):
- TARGET: 52-104 trades total on 1h timeframe over 365 days (1-2 trades per WEEK)
- This is roughly 1 trade every 3-7 days - use MODERATE filters, not overly strict!
- BEAR markets have good setups, but they're selective - not every day
- If your initial backtest shows <40 trades, your filters are TOO TIGHT - LOOSEN them!
- If your initial backtest shows >120 trades, your filters are TOO LOOSE - tighten them
- Commission-conscious but not signal-starved: 50-100 trades is the sweet spot

INDICATOR LOGIC OVERRIDE (BEAR - PURE SHORT):
- USE ABSOLUTE THRESHOLDS: RSI > 65-75 for overbought (SHORT entry)
- AVOID PERCENTILE RANKING: Percentile ranking assumes positive drift (doesn't exist in bear)
- PURE SHORT SYSTEM: Fade failed rallies, short breakdowns, sell overbought exhaustion
- WEAK MOMENTUM FILTERS: Look for momentum < 0.02-0.03 during rallies (weak rally = short)

ENTRY LOGIC OVERRIDE (BEAR - SHORT ONLY):

SHORT ARCHETYPE 1 - Failed Rally (price rallies into resistance, fails):
- RSI(14) > 65-75 (overbought in bear market context)
- Price near SMA(20/50/100) resistance or rolling high
- Momentum weak < 0.02-0.03 (rally can't sustain, exhausting)
- Entry: 2 conditions from overbought + resistance proximity

SHORT ARCHETYPE 2 - Breakdown Continuation (broken support retested):
- Close below recent support AND retest fails
- Price near broken support from below (now resistance)
- RSI > 55-65 on retest (not even overbought, just approaching resistance)
- Entry: 2 conditions from below-support + failed retest signal

SHORT ARCHETYPE 3 - Overbought Exhaustion (extreme overbought reversal):
- RSI > 70-80 (extreme for bear market)
- Stochastic > 80-85 (exhaustion zone)
- Entry: 2 conditions from overbought extreme + rejection signal

SHORT ARCHETYPE 4 - Momentum Divergence (price up, indicators down):
- Price makes higher high but RSI makes lower high
- MACD histogram declining while price rising
- Entry: 2 conditions from divergence + premium proximity

EXIT LOGIC OVERRIDE (BEAR SHORT):
- Take profit: 2-tier TP — TP1 at 4.0x stop dist, TP2 at 7.0x stop dist
- Let winners run: downtrends persist in bear markets
- Max hold: 80-90 bars on 15m (~20-22 hours)
- Quick exit if SHORT goes wrong: RSI < 30 (oversold bounce incoming)
- Use FIXED TP targets (not trailing stops)

RISK MANAGEMENT OVERRIDE (BEAR SHORT):
- Position sizing: 0.5-0.6
- Stop: 2.5-3.2x ATR ABOVE entry (bear rallies are violent but brief)
- Risk/Reward: 4.0-7.0x (favor letting shorts run)

BANNED PATTERNS IN BEAR SHORT SYSTEM:
- LONG strategies (this is a pure SHORT system)
- Donchian breakouts to upside (false breakouts in sustained downtrends)
- High-frequency strategies (200-400 trades causes commission death)
- Percentile ranking systems (assume positive drift that doesn't exist)
- Holding periods >90 bars (diminishing returns)

EXAMPLE BEAR SHORT STRATEGY STRUCTURE:
```python
def next(self):
    # SHORT Example - Failed Rally at Resistance
    rsi = self.rsi[-1]
    sma50 = self.sma50[-1]
    momentum = (self.data.Close[-1] / self.data.Close[-10] - 1)

    if (rsi > 68 and                              # Overbought in bear context
        self.data.Close[-1] > sma50 * 0.998 and   # Near SMA50 resistance
        momentum < 0.025):                         # Weak rally momentum

        atr = self.atr[-1]
        stop_loss = self.data.Close[-1] + (2.7 * atr)  # Stop ABOVE entry
        size = 0.55
        self.sell(size=size, sl=stop_loss)

    # Exit after 85 bars (let shorts run in bear)
    if self.position.is_short:
        bars_held = len(self.data) - self.trades[-1].entry_bar
        if bars_held >= 85:
            self.position.close()
```

Remember: BEAR SHORT strategies need BALANCE (30-100 trades), not starvation (1 trade) or overtrading (200+ trades)!
"""

BULL_REGIME_OVERRIDES = """
================================================================================
CRITICAL: BULL MARKET REGIME DETECTED - OVERRIDE RULES BELOW TAKE PRECEDENCE!
================================================================================

When generating code for BULL market strategies, the rules below OVERRIDE any
conflicting rules in the base prompt. If there's a conflict, ALWAYS follow
the BULL-specific rules!

TRADE FREQUENCY OVERRIDE (BULL):
- TARGET: 5-12 trades total on 1h timeframe (NOT 200-400!)
- BULL is about TREND CAPTURE, not scalping
- Fewer trades with MUCH larger average win (let trends run months)
- If your initial backtest shows >15 trades, you're exiting too early!
- If your initial backtest shows <3 trades, your entry filters are too tight

INDICATOR LOGIC OVERRIDE (BULL):
- LOOSER MOMENTUM THRESHOLDS: > 0.045-0.065 (not the tight 0.018-0.032)
- HIGHER VOLUME CONFIRMATION: > 1.6-2.1x avg (not 1.10-1.45x)
- SLOWER DONCHIAN PERIODS: 16-26 bars (not 4-14 bars)
- ATR RATIO for breakout: > 1.25-1.38 (confirms expansion not drift)
- TREND FILTERS: SMA(50) > SMA(100), Close > SMA(50) * 1.08

ENTRY LOGIC OVERRIDE (BULL):

PRIMARY PATTERN - Donchian Breakout + Momentum Continuation (40% of strategies):
- High.rolling(18-22).max() breakout (slower periods for quality)
- Momentum > 0.052 (LOOSER than all-market rules to catch moves early)
- Volume > 1.80x avg (strong institutional confirmation)
- ATR ratio > 1.30 (volatility expansion confirms breakout)
- Trend confirmation: SMA(50) > SMA(100), Close > SMA(50) * 1.08

SECONDARY PATTERN - Pullback Continuation (30% of strategies):
- Established uptrend: SMA(50) > SMA(100), Close > SMA(50) * 1.08
- Pullback to support: EMA(20) or SMA(50) support level
- Volume dries up on pullback < 0.9x avg (healthy consolidation)
- Bounce with volume return > 1.5x avg (buyers re-enter)

EXIT LOGIC OVERRIDE (BULL):
CRITICAL - THIS IS THE MOST IMPORTANT RULE FOR BULL MARKETS!

BANNED IN BULL MARKETS:
- Fixed take-profit targets (TP = 7.8x stop) - Tested strategies missed 98% of bull moves!
- Max hold time limits (44-56 bars) - Exited way too early on multi-month trends!
- Selling into strength - NEVER exit just because price went up!

REQUIRED FOR BULL MARKETS:
- USE TRAILING STOPS ONLY (no fixed TP):
  1. ATR Trailing: max(initial_stop, Close - 3.2 * ATR(14))
  2. SMA Trailing: Exit when Close < SMA(20) or SMA(50)
  3. Chandelier: High.rolling(20).max() - 3.0 * ATR(14)
- NO MAX HOLD LIMITS: Hold until trailing stop is hit (could be weeks/months!)
- Let winners run: Bull trends last 50-150 bars on 1h data

POSITION SIZING OVERRIDE (BULL):
- Initial position: 0.75-1.0% risk per trade
- Scale into winners: Add 0.5% risk on pullbacks to support levels
- Maximum total risk per trend: 2.5% (up to 3 position adds)
- Pyramiding: Allow up to 3 entries per trend

RISK MANAGEMENT OVERRIDE (BULL):
- Initial stop: 3.8x ATR (wider to accommodate normal volatility)
- Trailing stop: 3.2x ATR or SMA(20), whichever is tighter
- NEVER use fixed TP targets (destroys edge in trends!)
- NEVER use max hold limits (trends run for weeks/months!)

EXAMPLE BULL STRATEGY STRUCTURE:
```python
def next(self):
    # Donchian Breakout + Momentum
    high_20 = self.high_20[-1]
    momentum = (self.data.Close[-1] / self.data.Close[-10] - 1)
    vol_ratio = self.data.Volume[-1] / self.vol_avg[-1]
    atr = self.atr[-1]
    sma50 = self.sma50[-1]
    sma100 = self.sma100[-1]

    # Entry (looser filters for 5-12 trades)
    if (self.data.High[-1] > high_20 and           # Donchian breakout
        momentum > 0.055 and                        # Strong momentum (LOOSER)
        vol_ratio > 1.85 and                        # Volume confirmation (HIGHER)
        sma50 > sma100 and                          # Uptrend confirmed
        self.data.Close[-1] > sma50 * 1.08):       # Above trend

        stop_loss = self.data.Close[-1] - (3.8 * atr)
        size = 0.85  # 0.85% risk
        self.buy(size=size, sl=stop_loss)  # NO TP! Trailing stop only!

    # Trailing stop (NO max hold limit!)
    if self.position:
        trailing_stop = self.data.Close[-1] - (3.2 * atr)
        if self.data.Close[-1] < trailing_stop or self.data.Close[-1] < self.sma20[-1]:
            self.position.close()
```

Remember: BULL strategies are about RIDING TRENDS (hold weeks/months), not scalping (exit after 2 days)!
"""

SIDEWAYS_REGIME_OVERRIDES = """
================================================================================
CRITICAL: SIDEWAYS MARKET REGIME DETECTED - OVERRIDE RULES BELOW TAKE PRECEDENCE!
================================================================================

When generating code for SIDEWAYS market strategies, the rules below OVERRIDE any
conflicting rules in the base prompt. If there's a conflict, ALWAYS follow
the SIDEWAYS-specific rules!

TRADE FREQUENCY OVERRIDE (SIDEWAYS):
- TARGET: 60-120 trades total on 1h timeframe (moderate frequency)
- SIDEWAYS markets have consistent range oscillations (more opportunities than BULL)
- Not as many as old BULL rules (200-400 = commission death)
- If your initial backtest shows >140 trades, you're over-trading the range
- If your initial backtest shows <50 trades, you're missing range opportunities

INDICATOR LOGIC OVERRIDE (SIDEWAYS):
- BALANCED THRESHOLDS: Not too tight (BEAR 20-40), not too loose (old BULL 200-400)
- USE BOTH: Percentile ranking (works in ranging markets) + absolute thresholds (for extremes)
- OSCILLATOR-HEAVY: RSI, Stochastic, BB %B, Williams %R (range-bound indicators)
- SUPPORT/RESISTANCE: Horizontal levels are CRITICAL in sideways markets
- VOLUME CONFIRMATION: > 1.5x avg for breakouts, < 1.0x for fakeouts

ENTRY LOGIC OVERRIDE (SIDEWAYS):

PATTERN 1 - Mean Reversion Extremes (40% of strategies):
- RSI < 30 (oversold) or RSI > 70 (overbought) at range boundaries
- Bollinger Band %B < 0.05 (touch lower band) or %B > 0.95 (touch upper band)
- Price near support/resistance levels (horizontal lines matter most)
- Volume confirmation > 1.5x avg when reversing from extreme
- Target: Opposite range boundary (mean reversion)

PATTERN 2 - Range Breakout Fakeouts (30% of strategies):
- Price breaks above/below recent range boundary
- Volume NOT confirming (< 1.3x avg = fake breakout)
- Quick reversal back into range within 2-4 bars
- FADE the breakout, target opposite range boundary
- Stop: Just outside the false breakout level

PATTERN 3 - Bollinger Compression to Expansion (30% of strategies):
- BB width at lowest 20% percentile (squeeze)
- Breakout from compression with volume > 1.8x avg
- Quick scalp: Target 3.0-4.0x stop before range re-establishes
- Exit fast: Ranges cycle quickly in sideways markets

EXIT LOGIC OVERRIDE (SIDEWAYS):
- Use FIXED TP TARGETS at opposite range boundary (not trailing stops)
- Quick take profits: 3.0-4.5x stop distance (ranges don't persist like trends)
- Max hold: 28-42 bars (ranges cycle faster than trends)
- HYBRID approach: Set both TP target AND trailing stop (whichever hits first)
- If position open >40 bars without hitting target, exit (range likely broken)

RISK MANAGEMENT OVERRIDE (SIDEWAYS):
- Position sizing: 0.6-0.85% risk per trade (moderate, between BEAR and BULL)
- Stops: 2.5-3.2x ATR (tighter than BULL, similar to BEAR)
- Targets: 3.0-4.5x stop (moderate R:R, not aggressive like BULL)
- Win rate focus: Target 55-65% win rate (more important than R:R in ranges)

BANNED PATTERNS IN SIDEWAYS MARKETS:
- Trend continuation strategies (no sustained trends exist)
- Long holding periods (> 50 bars = range likely broken by then)
- Trailing stops only (need fixed targets for range boundaries)
- Very high frequency (200-400 trades = commission death)
- Donchian breakouts (most breakouts fail and reverse in sideways)

EXAMPLE SIDEWAYS STRATEGY STRUCTURE:
```python
def next(self):
    # Mean Reversion from Oversold
    rsi = self.rsi[-1]
    bb_pct = self.bb_pct[-1]  # Bollinger %B
    vol_ratio = self.data.Volume[-1] / self.vol_avg[-1]
    sma20 = self.sma20[-1]

    # Entry at lower range boundary
    if (rsi < 32 and                    # Oversold (absolute threshold)
        bb_pct < 0.08 and              # Near lower BB
        vol_ratio > 1.6):              # Volume confirmation

        atr = self.atr[-1]
        stop_loss = self.data.Close[-1] - (2.7 * atr)
        take_profit = sma20  # Target = BB middle (range midpoint)
        size = 0.7  # 0.7% risk
        self.buy(size=size, sl=stop_loss, tp=take_profit)

    # Exit if held too long (range likely broken)
    if self.position and len(self.data) - self.trades[-1].entry_bar >= 38:
        self.position.close()

    # Trailing stop backup (hybrid approach)
    if self.position:
        trailing = self.data.Close[-1] - (2.8 * atr)
        if self.data.Close[-1] < trailing:
            self.position.close()
```

Remember: SIDEWAYS strategies are about RANGE TRADING (target boundaries), not trend following!
"""

# Mapping dictionary for easy lookup
REGIME_OVERRIDES = {
    'BEAR': BEAR_REGIME_OVERRIDES,
    'BULL': BULL_REGIME_OVERRIDES,
    'SIDEWAYS': SIDEWAYS_REGIME_OVERRIDES
}

# ============================================
#  HELPER FUNCTIONS (with thread safety)
# ============================================

def parse_return_from_output(stdout: str, thread_id: int) -> float:
    """Extract the Return [%] from backtest output"""
    try:
        match = re.search(r'Return \[%\]\s+([-\d.]+)', stdout)
        if match:
            return_pct = float(match.group(1))
            thread_print(f" Extracted return: {return_pct}%", thread_id)
            return return_pct
        else:
            thread_print(" Could not find Return [%] in output", thread_id, "yellow")
            return None
    except Exception as e:
        thread_print(f" Error parsing return: {str(e)}", thread_id, "red")
        return None

def parse_all_stats_from_output(stdout: str, thread_id: int) -> dict:
    """
     Moon Dev's Stats Parser - Extract all key stats from backtest output!
    Returns dict with: return_pct, buy_hold_pct, max_drawdown_pct, sharpe, sortino, expectancy, trades, win_rate
    """
    stats = {
        'return_pct': None,
        'buy_hold_pct': None,
        'max_drawdown_pct': None,
        'sharpe': None,
        'sortino': None,
        'expectancy': None,
        'trades': None,
        'win_rate': None
    }

    try:
        # Return [%]
        match = re.search(r'Return \[%\]\s+([-\d.]+)', stdout)
        if match:
            stats['return_pct'] = float(match.group(1))

        # Buy & Hold Return [%]
        match = re.search(r'Buy & Hold Return \[%\]\s+([-\d.]+)', stdout)
        if match:
            stats['buy_hold_pct'] = float(match.group(1))

        # Max. Drawdown [%]
        match = re.search(r'Max\. Drawdown \[%\]\s+([-\d.]+)', stdout)
        if match:
            stats['max_drawdown_pct'] = float(match.group(1))

        # Sharpe Ratio
        match = re.search(r'Sharpe Ratio\s+([-\d.]+)', stdout)
        if match:
            stats['sharpe'] = float(match.group(1))

        # Sortino Ratio
        match = re.search(r'Sortino Ratio\s+([-\d.]+)', stdout)
        if match:
            stats['sortino'] = float(match.group(1))

        # Expectancy [%] (or Avg. Trade [%])
        match = re.search(r'Expectancy \[%\]\s+([-\d.]+)', stdout)
        if not match:
            match = re.search(r'Avg\. Trade \[%\]\s+([-\d.]+)', stdout)
        if match:
            stats['expectancy'] = float(match.group(1))

        # # Trades
        match = re.search(r'# Trades\s+(\d+)', stdout)
        if match:
            stats['trades'] = int(match.group(1))

        # Win Rate [%]
        match = re.search(r'Win Rate \[%\]\s+([-\d.]+)', stdout)
        if match:
            stats['win_rate'] = float(match.group(1))

        thread_print(f" Extracted {sum(1 for v in stats.values() if v is not None)}/8 stats", thread_id)
        return stats

    except Exception as e:
        thread_print(f" Error parsing stats: {str(e)}", thread_id, "red")
        return stats

def validate_regime_compliance(stats: dict, thread_id: int) -> tuple:
    """
    Validate that strategy respects regime-specific constraints

    Returns:
        tuple: (is_compliant: bool, warning_message: str)
    """
    if not CURRENT_REGIME or not stats:
        return True, ""

    trades = stats.get('trades', 0)

    # Regime-specific trade count validation
    if CURRENT_REGIME == 'BEAR':
        if trades > 120:
            return False, f"BEAR regime expects 52-104 trades (1-2/week), got {trades} (too high frequency!)"
        elif trades < 40:
            return False, f"BEAR regime expects 52-104 trades (1-2/week), got {trades} (signal starvation!)"

    elif CURRENT_REGIME == 'BULL':
        if trades > 15:
            return False, f"BULL regime expects 5-12 trades, got {trades} (over-trading!)"
        elif trades < 3:
            return False, f"BULL regime expects 5-12 trades, got {trades} (filters too tight!)"

    elif CURRENT_REGIME == 'SIDEWAYS':
        if trades > 140:
            return False, f"SIDEWAYS regime expects 60-120 trades, got {trades} (too high frequency!)"
        elif trades < 50:
            return False, f"SIDEWAYS regime expects 60-120 trades, got {trades} (missing opportunities!)"

    return True, ""

def calculate_composite_score(stats: dict, thread_id: int) -> float:
    """
     PHASE 2: Multi-objective composite scoring

    Balances multiple objectives instead of just maximizing returns:
    - 40% Sharpe Ratio (risk-adjusted returns)
    - 30% Raw Returns (scaled to 0-1 range)
    - 20% Drawdown Protection (inverse of max drawdown)
    - 10% Win Rate (trading consistency)

    Returns composite score (0-100 range) or None if missing critical stats
    """
    try:
        # Extract required stats
        sharpe = stats.get('sharpe')
        return_pct = stats.get('return_pct')
        max_dd = stats.get('max_drawdown_pct')
        win_rate = stats.get('win_rate')

        # Check if we have minimum required stats (Sharpe + Return)
        if sharpe is None or return_pct is None:
            thread_print(" Missing Sharpe or Return - cannot calculate composite score", thread_id, "yellow")
            return None

        # Normalize each component to 0-1 range

        # 1. Sharpe Ratio: Cap at 3.0 for normalization (3.0+ is exceptional)
        sharpe_normalized = min(max(sharpe, 0.0), 3.0) / 3.0

        # 2. Return: Scale by dividing by 10 (10% return = 1.0, 30% = 3.0)
        # Cap at 50% for normalization
        return_normalized = min(max(return_pct, 0.0), 50.0) / 50.0

        # 3. Drawdown Protection: Convert negative DD to positive score
        # -5% DD = 0.95, -20% DD = 0.80, -50% DD = 0.50
        if max_dd is not None:
            dd_normalized = 1.0 - min(abs(max_dd), 50.0) / 50.0
        else:
            # If DD not available, assume neutral (0.5)
            dd_normalized = 0.5

        # 4. Win Rate: Already in percentage (0-100), normalize to 0-1
        if win_rate is not None:
            wr_normalized = min(max(win_rate, 0.0), 100.0) / 100.0
        else:
            # If win rate not available, assume neutral (0.5)
            wr_normalized = 0.5

        # Calculate weighted composite score
        composite = (
            0.40 * sharpe_normalized +
            0.30 * return_normalized +
            0.20 * dd_normalized +
            0.10 * wr_normalized
        )

        # Scale to 0-100 range for readability
        composite_score = composite * 100.0

        thread_print(f" Composite Score: {composite_score:.2f} (Sharpe:{sharpe_normalized:.2f}, Ret:{return_normalized:.2f}, DD:{dd_normalized:.2f}, WR:{wr_normalized:.2f})", thread_id, "cyan")

        return composite_score

    except Exception as e:
        thread_print(f" Error calculating composite score: {str(e)}", thread_id, "red")
        return None

def log_stats_to_csv(strategy_name: str, thread_id: int, stats: dict, file_path: str, data_source: str = "BTC-USD-15m.csv", tier: str = "BRONZE") -> None:
    """
    CSV Logger with Tier Classification - Only Gold/Silver/Bronze strategies logged!
    Appends backtest stats to CSV for easy analysis and comparison
    """
    try:
        with file_lock:
            # Create CSV with headers if it doesn't exist
            file_exists = STATS_CSV.exists()

            with open(STATS_CSV, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Write header if new file
                if not file_exists:
                    writer.writerow([
                        'Strategy Name',
                        'Tier',  # NEW: Gold/Silver/Bronze classification
                        'Thread ID',
                        'Return %',
                        'Buy & Hold %',
                        'Max Drawdown %',
                        'Sharpe Ratio',
                        'Sortino Ratio',
                        'EV %',
                        'Trades',
                        'File Path',
                        'Data',
                        'Time'
                    ])
                    thread_print(" Created new stats CSV with Tier column", thread_id, "green")

                # Write stats row
                timestamp = datetime.now().strftime("%m/%d %H:%M")
                writer.writerow([
                    strategy_name,
                    tier,  # NEW: Tier classification
                    f"T{thread_id:02d}",
                    stats.get('return_pct', 'N/A'),
                    stats.get('buy_hold_pct', 'N/A'),
                    stats.get('max_drawdown_pct', 'N/A'),
                    stats.get('sharpe', 'N/A'),
                    stats.get('sortino', 'N/A'),
                    stats.get('expectancy', 'N/A'),
                    stats.get('trades', 'N/A'),
                    str(file_path),
                    data_source,
                    timestamp
                ])

                thread_print(f" Logged stats to CSV (Return: {stats.get('return_pct', 'N/A')}% on {data_source})", thread_id, "green")

    except Exception as e:
        thread_print(f" Error logging to CSV: {str(e)}", thread_id, "red")

def log_crypto_stats_to_csv(strategy_name: str, thread_id: int, stats: dict, file_path: str, data_source: str, tier: str) -> None:
    """
    CSV Logger for Crypto-Only Tier System (NEW - Parallel to log_stats_to_csv)

    Logs ONLY crypto results to a separate CSV (backtest_stats_crypto.csv).
    This keeps crypto and traditional results cleanly separated.

    IMPORTANT: This function is INDEPENDENT of log_stats_to_csv().
               Both can run for the same strategy if it qualifies for both systems.
    """
    try:
        with file_lock:
            file_exists = CRYPTO_STATS_CSV.exists()

            with open(CRYPTO_STATS_CSV, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Write header if new file
                if not file_exists:
                    writer.writerow([
                        'Strategy Name',
                        'Crypto Tier',  # NEW: CRYPTO-GOLD/SILVER/BRONZE
                        'Thread ID',
                        'Return %',
                        'Buy & Hold %',
                        'Max Drawdown %',
                        'Sharpe Ratio',
                        'Sortino Ratio',
                        'EV %',
                        'Trades',
                        'File Path',
                        'Data',
                        'Time'
                    ])
                    thread_print(" Created new crypto stats CSV", thread_id, "green")

                # Write stats row
                timestamp = datetime.now().strftime("%m/%d %H:%M")
                writer.writerow([
                    strategy_name,
                    tier,  # CRYPTO-GOLD/SILVER/BRONZE
                    f"T{thread_id:02d}",
                    stats.get('return_pct', 'N/A'),
                    stats.get('buy_hold_pct', 'N/A'),
                    stats.get('max_drawdown_pct', 'N/A'),
                    stats.get('sharpe', 'N/A'),
                    stats.get('sortino', 'N/A'),
                    stats.get('expectancy', 'N/A'),
                    stats.get('trades', 'N/A'),
                    str(file_path),
                    data_source,
                    timestamp
                ])

                thread_print(f" Logged crypto stats to CSV ({data_source})", thread_id, "green")

    except Exception as e:
        thread_print(f" Error logging crypto stats: {str(e)}", thread_id, "red")

def parse_and_log_multi_data_results(strategy_name: str, thread_id: int, backtest_file_path: Path) -> None:
    """
    Simple multi-data results logger. Reads CSVs from results_bear_15min/ and logs to stats CSV.
    No tier classification — we review results by hand.
    """
    try:
        results_dir = SCRIPT_DIR / "results_bear_15min"
        results_csv = results_dir / f"{strategy_name}.csv"

        if not results_csv.exists():
            return  # Silent — multi-data tester handles its own output

        df = pd.read_csv(results_csv)
        positive = len(df[df['Return_%'] > 0])
        thread_print(f" Multi-data: {positive}/{len(df)} assets positive", thread_id, "cyan")

        # Log all results to CSV
        for idx, row in df.iterrows():
            stats = {
                'return_pct': row['Return_%'],
                'buy_hold_pct': row.get('Buy_Hold_%', None),
                'max_drawdown_pct': row.get('Max_DD_%', None),
                'sharpe': row.get('Sharpe', None),
                'sortino': row.get('Sortino', None),
                'expectancy': row.get('Expectancy_%', None),
                'trades': row.get('Trades', None)
            }
            log_stats_to_csv(strategy_name, thread_id, stats, str(backtest_file_path), data_source=row['Data_Source'])

    except Exception as e:
        thread_print(f" Error parsing multi-data: {str(e)}", thread_id, "red")

def sanitize_emoji_from_code(code: str) -> str:
    """
    Strip emoji characters from code to prevent Windows CP1252 encoding errors.

    Grok sometimes adds emojis despite being told not to. This function removes them
    before execution to prevent crashes.
    """
    # Note: re module already imported globally at top of file (line 69)

    # Remove Unicode escape sequences (\U followed by 8 hex digits)
    code = re.sub(r'\\U[0-9a-fA-F]{8}', '', code)

    # Remove common emoji literals
    emoji_literals = ['', '', '', '', '', '', '', '', '', '', '', '', '', '', '']
    for emoji in emoji_literals:
        code = code.replace(emoji, '')

    # Remove any remaining non-ASCII characters from print statements
    # Pattern: find print(...) and clean the string inside
    def clean_print_statement(match):
        print_content = match.group(1)
        # Keep only ASCII characters (32-126)
        cleaned = ''.join(char for char in print_content if ord(char) < 128)
        return f'print({cleaned})'

    code = re.sub(r'print\(([^)]+)\)', clean_print_statement, code)

    return code

def health_check_code(code: str, strategy_name: str, thread_id: int) -> tuple[bool, str, str]:
    """
    Phase 1b: Health Check - Pre-execution validation

    Rejects obviously broken code before wasting compute time:
    - Missing critical imports (pandas, backtesting)
    - No Strategy class definition
    - No next() method
    - Syntax errors (basic check)
    - Import of banned packages (backtesting.lib)

    Returns:
        (is_valid, rejection_reason, sanitized_code)
    """
    try:
        # FIRST: Sanitize emojis before any checks
        sanitized_code = sanitize_emoji_from_code(code)
        code = sanitized_code  # Use sanitized version for all checks
        # Check 1: Critical imports
        if 'import pandas' not in code and 'from pandas' not in code:
            return False, "Missing pandas import (required for data handling)", code

        if 'from backtesting import' not in code:
            return False, "Missing backtesting import (required for Strategy class)", code

        # Check 2: Strategy class definition
        if 'class ' not in code or 'Strategy)' not in code:
            return False, "No Strategy class found (must inherit from backtesting.Strategy)", code

        # Check 3: next() method (core trading logic)
        if 'def next(self)' not in code:
            return False, "Missing next() method (required for signal generation)", code

        # Check 4: Banned imports (backtesting.lib)
        if 'backtesting.lib' in code or 'from backtesting.lib' in code:
            return False, "Uses backtesting.lib (banned - must use pandas/numpy indicators)", code

        # Check 4a: Detect file paths without raw strings (MUST CHECK BEFORE COMPILE!)
        # Pattern: pd.read_csv('path\Users' or sys.path.append('path\Users'
        # These will cause: "unicodeescape codec can't decode bytes" errors during compilation
        file_path_patterns = [
            r"pd\.read_csv\(['\"](?!r['\"])[^'\"]*\\Users",  # pd.read_csv('...\Users
            r"sys\.path\.append\(['\"](?!r['\"])[^'\"]*\\Users",  # sys.path.append('...\Users
            r"open\(['\"](?!r['\"])[^'\"]*\\Users",  # open('...\Users
        ]
        for pattern in file_path_patterns:
            if re.search(pattern, code):
                return False, "File path contains \\Users without raw string (r prefix) - will cause Unicode escape error - use r'path\\to\\file' instead of 'path\\to\\file'", code

        # Check 5: Basic syntax check (compile test)
        try:
            compile(code, '<string>', 'exec')
        except SyntaxError as e:
            return False, f"Syntax error: {str(e)}", code

        # Check 6: Data loading (must read CSV)
        if 'read_csv' not in code and 'pd.read_csv' not in code:
            return False, "No CSV data loading found (required for backtesting)", code

        # Check 7: Has buy/sell logic
        if 'self.buy' not in code and 'self.position.close' not in code:
            return False, "No trading actions found (missing buy/close calls)", code

        # Check 8: Incorrect broker API usage (common mistakes)
        if '_broker.get_cash()' in code:
            return False, "Uses _broker.get_cash() (incorrect API - use self.equity instead)", code

        if '_broker.get_value()' in code:
            return False, "Uses _broker.get_value() (incorrect API - use self.equity instead)", code

        if '_broker.getcash()' in code.lower():
            return False, "Uses incorrect broker cash method (use self.equity instead)", code

        # Check 9: Position sizing validation - DISABLED (too many false positives)
        # The BACKTEST_PROMPT and DEBUG_PROMPT now teach correct size validation
        # Let runtime errors be caught and fixed by debug agent instead
        # has_buy_or_sell = 'self.buy(' in code or 'self.sell(' in code
        # if has_buy_or_sell:
        #     has_size_validation = any([
        #         'if size > 0' in code,
        #         'if size >= ' in code,
        #         'size = max(' in code and '0.' in code,
        #         'size = min(max(' in code,
        #         'assert size > 0' in code,
        #         'if trade_size > 0' in code,
        #         'if position_size > 0' in code
        #     ])
        #     if not has_size_validation:
        #         return False, "Missing position size validation", code

        # ============================================
        # PHASE 2: PRE-EXECUTION VALIDATION
        # Catch common errors BEFORE wasting compute
        # ============================================

        # Check 10: Detect pandas methods on backtesting _Array objects
        # These will crash at runtime with AttributeError
        # Note: re module already imported globally at top of file (line 69)

        # Pattern: self.data.Close.shift / self.data.High.rolling / etc.
        array_pandas_pattern = r'self\.data\.\w+\.(shift|rolling|iloc|values|pct_change|diff|fillna|dropna)\('
        if re.search(array_pandas_pattern, code):
            return False, "Uses pandas methods (.shift/.rolling/.iloc) directly on self.data arrays - must wrap in self.I() with pd.Series conversion", code

        # Pattern: Check for common indicator patterns that might use _Array methods
        # e.g., close_shifted = self.data.Close.shift(1) in init()
        dangerous_patterns = [
            r'=\s*self\.data\.\w+\.shift\(',
            r'=\s*self\.data\.\w+\.rolling\(',
            r'=\s*self\.data\.\w+\.iloc\[',
            r'=\s*self\.data\.\w+\.values',
            r'=\s*self\.data\.\w+\.pct_change\(',
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, code):
                return False, "Direct pandas method usage on backtesting arrays detected - must use self.I() wrapper with pd.Series conversion inside", code

        # Check 11: Detect talib import (not installed)
        if 'import talib' in code or 'from talib' in code:
            return False, "Imports talib (not installed) - must use pandas/numpy equivalents (see BACKTEST_PROMPT for examples)", code

        # Check 12: Detect emoji unicode characters (Windows encoding crash)
        # Pattern: \U followed by 8 hex digits (Unicode escape)
        emoji_pattern = r'\\U[0-9a-fA-F]{8}'
        if re.search(emoji_pattern, code):
            return False, "Contains emoji unicode characters (\\U codes) - Windows CP1252 encoding will crash - remove ALL emojis from print statements", code

        # Also check for common emoji unicode literals in strings
        # COMMENTED OUT: This check itself contains emojis causing Windows encoding issues
        # The sanitize_emoji_from_code() function at line 3027 already handles emoji removal
        # emoji_literals = ['', '', '', '', '', '', '', '', '']
        # for emoji in emoji_literals:
        #     if emoji in code:
        #         return False, f"Contains emoji literal '{emoji}' - Windows encoding will crash - use plain ASCII text only", code

        # Check 13: Position sizing safeguards (relaxed - just check for obviously broken patterns)
        # Don't reject if missing safeguards, but reject if clearly wrong patterns exist
        if 'self.buy(size=0)' in code or 'self.sell(size=0)' in code:
            return False, "Contains hardcoded size=0 in buy/sell call - this will crash (size must be > 0)", code

        # Detect potential division by zero in size calculation (common mistake)
        # Pattern: size = ... / atr[-1] without any protection
        risky_size_pattern = r'size\s*=\s*[^/]+/\s*(?:atr|volatility|std|range)\[-?\d+\](?!\s*[),])'
        if re.search(risky_size_pattern, code):
            # Check if there's ANY max() safeguard in the code
            if 'max(' not in code or ('max(' in code and 'atr' not in code.split('max(')[1].split(')')[0]):
                return False, "Size calculation divides by volatility metric without safeguard - must use max(atr[-1], min_value) to prevent division by near-zero", code

        # Check 14: Detect Position attribute errors
        # These attributes don't exist on backtesting Position object
        forbidden_position_attrs = [
            r'self\.position\.entry_price',
            r'self\.position\.entry_bar',
            r'self\.position\.sl\b',  # \b = word boundary (not self.position.sl_price)
            r'self\.position\.tp\b',
        ]
        for pattern in forbidden_position_attrs:
            if re.search(pattern, code):
                attr = pattern.split('.')[-1].replace('\\b', '')
                return False, f"Uses self.position.{attr} (does not exist) - must track entry_price/stop_loss manually as class variables", code

        # All checks passed
        thread_print(" Health check PASSED", thread_id, "green")
        return True, "", sanitized_code

    except Exception as e:
        return False, f"Health check error: {str(e)}", code

def classify_strategy_tier(stats: dict) -> str:
    """
     Moon Dev's Tier Classification System (Phase 1a - Fixed Criteria)

    Classifies strategies into Gold/Silver/Bronze tiers based on:
    - Sharpe Ratio (risk-adjusted returns)
    - Max Drawdown (downside risk)
    - Trade Count (statistical significance - HIGHER thresholds prevent flukes)
    - Positive Returns (profitability requirement)

    Returns:
        "GOLD", "SILVER", "BRONZE", or "REJECT"
    """
    sharpe = stats.get('sharpe')
    max_dd = stats.get('max_drawdown_pct')
    trades = stats.get('trades')
    return_pct = stats.get('return_pct')

    # Convert to numbers, handle None/NaN
    try:
        sharpe = float(sharpe) if sharpe is not None else 0
        max_dd = float(max_dd) if max_dd is not None else -100
        trades = int(trades) if trades is not None else 0
        return_pct = float(return_pct) if return_pct is not None else 0
    except (ValueError, TypeError):
        return "REJECT"

    # Immediate reject conditions
    if return_pct <= 0:
        return "REJECT"
    if trades == 0:
        return "REJECT"
    if sharpe is None or max_dd is None:
        return "REJECT"

    #  GOLD TIER: Production-ready strategies
    # Balanced criteria: Good Sharpe, controlled DD, HIGH trade count for significance
    if sharpe > 1.2 and max_dd > -15 and trades >= 100:
        return "GOLD"

    #  SILVER TIER: Strong candidates
    # Moderate requirements with significant trade sample
    if sharpe > 1.0 and max_dd > -20 and trades >= 75:
        return "SILVER"

    #  BRONZE TIER: Research candidates
    # Lower bar but still requires meaningful trade count
    if sharpe > 0.8 and max_dd > -25 and trades >= 50:
        return "BRONZE"

    # Doesn't meet any tier requirements
    return "REJECT"

def classify_multi_asset_tier(results_df: pd.DataFrame, thread_id: int) -> str:
    """
     Phase 3a: Multi-Asset Tier Classification (v3 - Capital Optimized)

    Classifies strategies based on performance across MULTIPLE data sources.
    A strategy must prove robust across different assets/timeframes to qualify.

    Args:
        results_df: DataFrame from multi_data_tester (columns: Data_Source, Return_%, Sharpe, Max_DD_%, Trades, etc.)
        thread_id: Thread ID for logging

    Returns:
        "GOLD", "SILVER", "BRONZE", or "REJECT"

    Criteria (Updated Nov 23 v3):
        GOLD: 5+ sources passing, avg Sharpe >1.2, no DD worse than -20%, overall avg return >+5%, min 40 trades
        SILVER: 3+ sources passing, avg Sharpe >1.0, no DD worse than -25%, overall avg return >+2%, min 40 trades
        BRONZE: 2+ sources passing, avg Sharpe >0.8, no DD worse than -30%, overall avg return >0%, min 40 trades

    CRITICAL: "Overall avg return" is calculated across ALL 47 sources (not just passing sources).
              This prevents strategies that work on 2 sources but fail catastrophically on 45 others.
              Min 40 trades ensures capital efficiency for 1000-5000 accounts.
    """
    if results_df is None or len(results_df) == 0:
        thread_print(" Multi-asset: No results to classify", thread_id, "red")
        return "REJECT"

    # Define passing criteria for each tier
    # A source "passes" if it meets minimum thresholds
    def count_passing_sources(min_sharpe, max_dd_threshold):
        """Count how many sources pass the given thresholds"""
        passing = results_df[
            (results_df['Sharpe'] >= min_sharpe) &
            (results_df['Max_DD_%'] >= max_dd_threshold) &
            (results_df['Trades'] >= 20) &  # Lowered from 40 to 20 - focus on returns not trade count!
            (results_df['Return_%'] > 0)
        ]
        return len(passing), passing

    # Check for catastrophic failures (DD worse than absolute limit)
    worst_dd = results_df['Max_DD_%'].min()

    # Try GOLD tier first
    gold_count, gold_passing = count_passing_sources(
        MULTI_ASSET_MIN_SHARPE_AVG['GOLD'],
        MULTI_ASSET_MAX_DD_THRESHOLD['GOLD']
    )

    if gold_count >= MULTI_ASSET_MIN_SOURCES['GOLD']:
        avg_sharpe = gold_passing['Sharpe'].mean()
        overall_avg_return = results_df['Return_%'].mean()
        if overall_avg_return < MULTI_ASSET_MIN_OVERALL_RETURN['GOLD']:
            thread_print(f" REJECTED for GOLD: Needs +{MULTI_ASSET_MIN_OVERALL_RETURN['GOLD']}% overall avg return (got {overall_avg_return:.2f}%)", thread_id, "red")
        else:
            thread_print(f" GOLD TIER! Passed {gold_count}/{ len(results_df)} sources (Avg Sharpe: {avg_sharpe:.2f}, Overall Return: {overall_avg_return:.2f}%)", thread_id, "green", attrs=['bold'])
            return "GOLD"

    # Try SILVER tier
    silver_count, silver_passing = count_passing_sources(
        MULTI_ASSET_MIN_SHARPE_AVG['SILVER'],
        MULTI_ASSET_MAX_DD_THRESHOLD['SILVER']
    )

    if silver_count >= MULTI_ASSET_MIN_SOURCES['SILVER']:
        avg_sharpe = silver_passing['Sharpe'].mean()
        overall_avg_return = results_df['Return_%'].mean()
        if overall_avg_return < MULTI_ASSET_MIN_OVERALL_RETURN['SILVER']:
            thread_print(f" REJECTED for SILVER: Needs +{MULTI_ASSET_MIN_OVERALL_RETURN['SILVER']}% overall avg return (got {overall_avg_return:.2f}%)", thread_id, "red")
        else:
            thread_print(f" SILVER TIER! Passed {silver_count}/{len(results_df)} sources (Avg Sharpe: {avg_sharpe:.2f}, Overall Return: {overall_avg_return:.2f}%)", thread_id, "cyan", attrs=['bold'])
            return "SILVER"

    # Try BRONZE tier
    bronze_count, bronze_passing = count_passing_sources(
        MULTI_ASSET_MIN_SHARPE_AVG['BRONZE'],
        MULTI_ASSET_MAX_DD_THRESHOLD['BRONZE']
    )

    if bronze_count >= MULTI_ASSET_MIN_SOURCES['BRONZE']:
        avg_sharpe = bronze_passing['Sharpe'].mean()
        # CRITICAL FIX: Check overall average return across ALL sources
        overall_avg_return = results_df['Return_%'].mean()
        if overall_avg_return < MULTI_ASSET_MIN_OVERALL_RETURN['BRONZE']:
            thread_print(f" REJECTED: Bronze tier requires >{MULTI_ASSET_MIN_OVERALL_RETURN['BRONZE']}% overall avg return (got {overall_avg_return:.2f}%)", thread_id, "red")
            return "REJECT"
        thread_print(f" BRONZE TIER! Passed {bronze_count}/{len(results_df)} sources (Avg Sharpe: {avg_sharpe:.2f}, Overall Return: {overall_avg_return:.2f}%)", thread_id, "yellow", attrs=['bold'])
        return "BRONZE"

    # Doesn't qualify for any tier
    thread_print(f" REJECTED: Only passed {bronze_count}/{len(results_df)} sources (need {MULTI_ASSET_MIN_SOURCES['BRONZE']}+ for BRONZE)", thread_id, "red")
    return "REJECT"

def remove_catastrophic_crypto_outliers(crypto_df: pd.DataFrame) -> tuple:
    """
    Remove crypto markets with catastrophic failures (account blow-ups, fundamental incompatibility).
    Catastrophic = DD < -70% OR Return < -40% OR Sharpe < -3.0 OR Trades < 10
    Safety: Only removes up to 3 markets (21% of 14 crypto markets). If > 3 catastrophic, keep all.

    Returns:
        (cleaned_df, num_removed): Cleaned DataFrame and count of removed markets
    """
    catastrophic_mask = (
        (crypto_df['Return_%'] < -40) |
        (crypto_df['Max_DD_%'] < -70) |
        (crypto_df['Sharpe'] < -3.0) |
        (crypto_df['Trades'] < 10)
    )

    num_catastrophic = catastrophic_mask.sum()

    # Safety: Only remove if  3 markets catastrophic (21% of 14)
    if num_catastrophic > 0 and num_catastrophic <= 3:
        cleaned_df = crypto_df[~catastrophic_mask].copy()
        return cleaned_df, num_catastrophic

    # If > 3 catastrophic, keep all (strategy is genuinely bad on crypto)
    return crypto_df, 0

def winsorized_mean_crypto(series, lower_pct=0.1, upper_pct=0.1):
    """
    Calculate winsorized mean for crypto metrics.
    Caps bottom 10% and top 10% at percentile values.
    """
    if len(series) == 0:
        return 0.0

    lower_percentile = series.quantile(lower_pct)
    upper_percentile = series.quantile(1 - upper_pct)

    capped_series = series.clip(lower=lower_percentile, upper=upper_percentile)
    return capped_series.mean()

def classify_crypto_tier(results_df: pd.DataFrame, thread_id: int) -> tuple:
    """
     Crypto-Only Tier Classification (NEW - Parallel to classify_multi_asset_tier)

    Classifies strategies based on performance across CRYPTO assets ONLY.
    Ignores stocks, forex, and other traditional assets completely.

    Args:
        results_df: DataFrame from multi_data_tester (all assets)
        thread_id: Thread ID for logging

    Returns:
        tuple: (tier, tier_color, stats_dict) or (None, None, None)
        tier: "CRYPTO-GOLD", "CRYPTO-SILVER", "CRYPTO-BRONZE", or None

    IMPORTANT: This function is INDEPENDENT of classify_multi_asset_tier().
               A strategy can fail traditional tiers but pass crypto tiers (and vice versa).

    Criteria:
        CRYPTO-GOLD: 5+ crypto positive, Sharpe >0.8, DD <-15%, Return >8%, BTC positive
        CRYPTO-SILVER: 3+ crypto positive, Sharpe >0.6, DD <-20%, Return >5%, Major positive
        CRYPTO-BRONZE: 2+ crypto positive, Sharpe >0.5, DD <-25%, Return >2%, Major positive
    """
    if results_df is None or len(results_df) == 0:
        return None, None, None

    # Filter to crypto assets ONLY (NEW - traditional system uses all assets)
    crypto_results = results_df[results_df['Data_Source'].isin(CRYPTO_ASSETS)].copy()

    if len(crypto_results) == 0:
        thread_print(" No crypto results to classify", thread_id, "yellow")
        return None, None, None

    # OUTLIER PROTECTION: Remove catastrophic crypto markets (max 3 out of 14)
    cleaned_results, num_removed = remove_catastrophic_crypto_outliers(crypto_results)
    total_sources = len(crypto_results)
    usable_sources = len(cleaned_results)

    if num_removed > 0:
        thread_print(f" Removed {num_removed}/{total_sources} catastrophic crypto markets (outlier protection)", thread_id, "cyan")

    # Calculate positive count on CLEANED data
    positive_mask = cleaned_results['Return_%'] > 0
    num_positive = positive_mask.sum()

    # ROBUST STATISTICS: Use winsorized mean for Return/DD, median for Sharpe
    avg_return = winsorized_mean_crypto(cleaned_results['Return_%'])
    avg_sharpe = cleaned_results['Sharpe'].median()
    avg_dd = winsorized_mean_crypto(cleaned_results['Max_DD_%'])

    # Check BTC requirement (for GOLD) - use ORIGINAL data
    btc_sources = crypto_results[crypto_results['Data_Source'].str.contains('BTC-USD')]
    btc_positive = len(btc_sources) > 0 and (btc_sources['Return_%'] > 0).any()

    # Check major crypto requirement (for SILVER/BRONZE) - use ORIGINAL data
    major_pattern = 'BTC-USD|ETH-USD|SOL-USD'
    major_sources = crypto_results[crypto_results['Data_Source'].str.contains(major_pattern)]
    major_positive = len(major_sources) > 0 and (major_sources['Return_%'] > 0).any()

    # Evaluate tiers across ALL crypto markets
    tier = None
    color = None
    stats = None

    # Evaluate CRYPTO-GOLD
    if (num_positive >= CRYPTO_GOLD_THRESHOLD['min_positive_sources'] and
        avg_sharpe >= CRYPTO_GOLD_THRESHOLD['min_avg_sharpe'] and
        avg_dd >= CRYPTO_GOLD_THRESHOLD['max_avg_drawdown'] and
        avg_return >= CRYPTO_GOLD_THRESHOLD['min_avg_return'] and
        btc_positive):
        tier = "CRYPTO-GOLD"
        color = "yellow"
        stats = {
            'return_pct': avg_return,
            'sharpe': avg_sharpe,
            'max_drawdown_pct': avg_dd,
            'positive_sources': num_positive,
            'total_sources': total_sources,
            'usable_sources': usable_sources,
            'outliers_removed': num_removed
        }

    # Evaluate CRYPTO-SILVER
    elif (num_positive >= CRYPTO_SILVER_THRESHOLD['min_positive_sources'] and
          avg_sharpe >= CRYPTO_SILVER_THRESHOLD['min_avg_sharpe'] and
          avg_dd >= CRYPTO_SILVER_THRESHOLD['max_avg_drawdown'] and
          avg_return >= CRYPTO_SILVER_THRESHOLD['min_avg_return'] and
          major_positive):
        tier = "CRYPTO-SILVER"
        color = "cyan"
        stats = {
            'return_pct': avg_return,
            'sharpe': avg_sharpe,
            'max_drawdown_pct': avg_dd,
            'positive_sources': num_positive,
            'total_sources': total_sources,
            'usable_sources': usable_sources,
            'outliers_removed': num_removed
        }

    # Evaluate CRYPTO-BRONZE
    elif (num_positive >= CRYPTO_BRONZE_THRESHOLD['min_positive_sources'] and
          avg_sharpe >= CRYPTO_BRONZE_THRESHOLD['min_avg_sharpe'] and
          avg_dd >= CRYPTO_BRONZE_THRESHOLD['max_avg_drawdown'] and
          avg_return >= CRYPTO_BRONZE_THRESHOLD['min_avg_return'] and
          major_positive):
        tier = "CRYPTO-BRONZE"
        color = "blue"
        stats = {
            'return_pct': avg_return,
            'sharpe': avg_sharpe,
            'max_drawdown_pct': avg_dd,
            'positive_sources': num_positive,
            'total_sources': total_sources,
            'usable_sources': usable_sources,
            'outliers_removed': num_removed
        }

    # Return tier qualification
    if tier:
        if num_removed > 0:
            thread_print(f" {tier}! ({num_positive}/{usable_sources} crypto positive after removing {num_removed} outliers, Return: {avg_return:.2f}%, Median Sharpe: {avg_sharpe:.2f})", thread_id, color, attrs=['bold'])
        else:
            thread_print(f" {tier}! ({num_positive}/{total_sources} crypto positive, Return: {avg_return:.2f}%, Median Sharpe: {avg_sharpe:.2f})", thread_id, color, attrs=['bold'])
        return tier, color, stats

    # Didn't qualify
    thread_print(f" No crypto tier qualified ({num_positive}/{total_sources} positive, robust stats used)", thread_id, "red")
    return None, None, None

def save_to_crypto_tier_folder(code: str, strategy_name: str, iteration: int, thread_id: int, phase: str, crypto_tier: str, crypto_stats: dict, crypto_color: str) -> None:
    """
    Save strategy to crypto-tier-specific folder (CRYPTO-GOLD/SILVER/BRONZE)

    Args:
        code: The backtest code to save
        strategy_name: Name of the strategy
        iteration: Current iteration number
        thread_id: Thread ID
        phase: "debug", "opt", or "final"
        crypto_tier: "CRYPTO-GOLD", "CRYPTO-SILVER", or "CRYPTO-BRONZE"
        crypto_stats: Stats dict from classify_crypto_tier
        crypto_color: Color for terminal output
    """
    try:
        return_pct = crypto_stats['return_pct']
        timeframe = crypto_stats['timeframe']

        # Determine filename based on phase and crypto tier
        if phase == "debug":
            filename = f"T{thread_id:02d}_{strategy_name}_{crypto_tier}_DEBUG_v{iteration}_{return_pct:.1f}pct_{timeframe}.py"
        elif phase == "opt":
            filename = f"T{thread_id:02d}_{strategy_name}_{crypto_tier}_OPT_v{iteration}_{return_pct:.1f}pct_{timeframe}.py"
        else:  # final
            filename = f"T{thread_id:02d}_{strategy_name}_{crypto_tier}_FINAL_{return_pct:.1f}pct_{timeframe}.py"

        # Select crypto-tier-specific directory
        if crypto_tier == "CRYPTO-GOLD":
            tier_dir = CRYPTO_GOLD_STRATEGIES_DIR
        elif crypto_tier == "CRYPTO-SILVER":
            tier_dir = CRYPTO_SILVER_STRATEGIES_DIR
        else:  # CRYPTO-BRONZE
            tier_dir = CRYPTO_BRONZE_STRATEGIES_DIR

        # Save to CRYPTO-TIER-SPECIFIC folder (primary storage)
        tier_file = tier_dir / filename
        with file_lock:
            with open(tier_file, 'w', encoding='utf-8') as f:
                f.write(code)

        # Also save to WORKING folder (for compatibility)
        working_file = WORKING_BACKTEST_DIR / filename
        with file_lock:
            with open(working_file, 'w', encoding='utf-8') as f:
                f.write(code)

        # Also save to FINAL folder (for compatibility)
        final_file = FINAL_BACKTEST_DIR / filename
        with file_lock:
            with open(final_file, 'w', encoding='utf-8') as f:
                f.write(code)

        # Save to DEVANTSA_WINNERS folder (central repository)
        winners_file = DEVANTSA_WINNERS_DIR / filename
        with file_lock:
            with open(winners_file, 'w', encoding='utf-8') as f:
                f.write(code)

        thread_print(f" {crypto_tier}! ({timeframe} timeframe: {crypto_stats['positive_sources']}/{crypto_stats['total_sources']} positive, Return: {return_pct:.2f}%, Sharpe: {crypto_stats['sharpe']:.2f})", thread_id, crypto_color, attrs=['bold'])

        # Generate comprehensive strategy report for crypto winners
        generate_strategy_report(strategy_name, thread_id, code, crypto_stats, phase)

    except Exception as e:
        thread_print(f" Error saving crypto tier strategy: {str(e)}", thread_id, "red")

def save_backtest_if_threshold_met(code: str, stats: dict, strategy_name: str, iteration: int, thread_id: int, phase: str = "debug") -> bool:
    """
    Simple Strategy Saver — saves all strategies to working folders and CSV.
    No tier classification — we review results by hand.
    """
    return_pct = stats.get('return_pct')
    if return_pct is None:
        return False

    try:
        # Simple filename based on phase
        if phase == "debug":
            filename = f"T{thread_id:02d}_{strategy_name}_DEBUG_v{iteration}_{return_pct:.1f}pct.py"
        elif phase == "opt":
            filename = f"T{thread_id:02d}_{strategy_name}_OPT_v{iteration}_{return_pct:.1f}pct.py"
        else:
            filename = f"T{thread_id:02d}_{strategy_name}_FINAL_{return_pct:.1f}pct.py"

        # Save to working folders
        for save_dir in [WORKING_BACKTEST_DIR, FINAL_BACKTEST_DIR, DEVANTSA_WINNERS_DIR]:
            if save_dir and save_dir.exists():
                save_file = save_dir / filename
                with file_lock:
                    with open(save_file, 'w', encoding='utf-8') as f:
                        f.write(code)

        sharpe = stats.get('sharpe', 'N/A')
        trades = stats.get('trades', 'N/A')
        max_dd = stats.get('max_drawdown_pct', 'N/A')
        thread_print(f" Saved {return_pct:.1f}% | Sharpe:{sharpe} | DD:{max_dd}% | Trades:{trades}", thread_id, "green")

        # Log to CSV
        log_stats_to_csv(strategy_name, thread_id, stats, filename)

        return True

    except Exception as e:
        thread_print(f" Error saving: {str(e)}", thread_id, "red")
        return False

def generate_strategy_report(strategy_name: str, thread_id: int, code: str, stats: dict, phase: str):
    """
     Moon Dev's Strategy Report Generator
    Creates a comprehensive markdown report with all strategy details for easy implementation
    """
    try:
        # Read the original research file
        research_file = RESEARCH_DIR / f"T{thread_id:02d}_{strategy_name}_strategy.txt"
        research_content = "No research file found."
        if research_file.exists():
            with open(research_file, 'r', encoding='utf-8') as f:
                research_content = f.read()

        # Build comprehensive report
        report = f"""# {strategy_name} - Strategy Report

##  Performance Summary

**Return:** {stats.get('return_pct', 'N/A')}%
**Sharpe Ratio:** {stats.get('sharpe', 'N/A')}
**Sortino Ratio:** {stats.get('sortino', 'N/A')}
**Max Drawdown:** {stats.get('max_drawdown_pct', 'N/A')}%
**Total Trades:** {stats.get('trades', 'N/A')}
**Expectancy:** {stats.get('expectancy', 'N/A')}%
**Buy & Hold Return:** {stats.get('buy_hold_pct', 'N/A')}%

**Phase:** {phase.upper()}
**Thread ID:** T{thread_id:02d}
**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

##  Strategy Research & Analysis

{research_content}

---

##  Implementation Code

```python
{code}
```

---

##  Implementation Notes

### To Deploy This Strategy:

1. **Copy the code** from the Implementation Code section above
2. **Install dependencies**: `pip install backtesting pandas-ta`
3. **Prepare your data**: CSV file with OHLCV columns
4. **Run the backtest**: `python strategy_file.py`
5. **Review results**: Check stats match the Performance Summary above

### Key Indicators Used:

"""

        # Extract indicators from code
        if 'pandas_ta' in code or 'import talib' in code:
            report += "\n- Technical Analysis library: pandas_ta or talib\n"
        if 'RSI' in code.upper() or 'rsi' in code:
            report += "- RSI (Relative Strength Index)\n"
        if 'SMA' in code.upper() or 'sma' in code:
            report += "- SMA (Simple Moving Average)\n"
        if 'EMA' in code.upper() or 'ema' in code:
            report += "- EMA (Exponential Moving Average)\n"
        if 'MACD' in code.upper() or 'macd' in code:
            report += "- MACD (Moving Average Convergence Divergence)\n"
        if 'ATR' in code.upper() or 'atr' in code:
            report += "- ATR (Average True Range)\n"
        if 'BB' in code.upper() or 'bollinger' in code.lower():
            report += "- Bollinger Bands\n"

        report += f"""

### Risk Management:

- Position sizing controlled by backtesting.py framework
- Stop losses and take profits embedded in strategy logic
- Max drawdown observed: {stats.get('max_drawdown_pct', 'N/A')}%

---

##  Files Generated

- **Research**: `{research_file.name}`
- **Code (Working)**: Saved in `backtests_working/`
- **Code (Final)**: Saved in `backtests_final/`
- **This Report**: `{strategy_name}_REPORT.md`

---

*Generated by Moon Dev's RBI AI v3.0 - Parallel Processor*
*Using AI Model: {BACKTEST_CONFIG['name']}*
"""

        # Save report
        report_file = REPORTS_DIR / f"T{thread_id:02d}_{strategy_name}_REPORT.md"
        with file_lock:
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)

        thread_print(f"  Strategy report saved: {report_file.name}", thread_id, "cyan")

    except Exception as e:
        thread_print(f" Error generating strategy report: {str(e)}", thread_id, "yellow")

def execute_backtest(file_path: str, strategy_name: str, thread_id: int) -> dict:
    """Execute a backtest file using current Python interpreter"""
    thread_print(f" Executing: {strategy_name}", thread_id)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Use sys.executable to run with current Python (no conda needed!)
    cmd = [sys.executable, str(file_path)]

    start_time = datetime.now()

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=EXECUTION_TIMEOUT
    )

    execution_time = (datetime.now() - start_time).total_seconds()

    output = {
        "success": result.returncode == 0,
        "return_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "execution_time": execution_time,
        "timestamp": datetime.now().isoformat()
    }

    # Save execution results with thread ID
    result_file = EXECUTION_DIR / f"T{thread_id:02d}_{strategy_name}_{datetime.now().strftime('%H%M%S')}.json"
    with file_lock:
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2)

    if output['success']:
        thread_print(f" Backtest executed in {execution_time:.2f}s!", thread_id, "green")
    else:
        thread_print(f" Backtest failed: {output['return_code']}", thread_id, "red")

    return output

def parse_execution_error(execution_result: dict) -> str:
    """Extract meaningful error message for debug agent"""
    if execution_result.get('stderr'):
        return execution_result['stderr'].strip()
    return execution_result.get('error', 'Unknown error')

def get_idea_hash(idea: str) -> str:
    """Generate a unique hash for an idea to track processing status"""
    return hashlib.md5(idea.encode('utf-8')).hexdigest()

def is_idea_processed(idea: str) -> bool:
    """Check if an idea has already been processed (thread-safe)"""
    if not PROCESSED_IDEAS_LOG.exists():
        return False

    idea_hash = get_idea_hash(idea)

    with file_lock:
        with open(PROCESSED_IDEAS_LOG, 'r', encoding='utf-8') as f:
            processed_hashes = [line.strip().split(',')[0] for line in f if line.strip()]

    return idea_hash in processed_hashes

def log_processed_idea(idea: str, strategy_name: str, thread_id: int) -> None:
    """Log an idea as processed with timestamp and strategy name (thread-safe)"""
    idea_hash = get_idea_hash(idea)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with file_lock:
        if not PROCESSED_IDEAS_LOG.exists():
            PROCESSED_IDEAS_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(PROCESSED_IDEAS_LOG, 'w', encoding='utf-8') as f:
                f.write("# Moon Dev's RBI AI - Processed Ideas Log \n")
                f.write("# Format: hash,timestamp,thread_id,strategy_name,idea_snippet\n")

        idea_snippet = idea[:50].replace(',', ';') + ('...' if len(idea) > 50 else '')
        with open(PROCESSED_IDEAS_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{idea_hash},{timestamp},T{thread_id:02d},{strategy_name},{idea_snippet}\n")

    thread_print(f" Logged processed idea: {strategy_name}", thread_id, "green")

def has_nan_results(execution_result: dict) -> bool:
    """Check if backtest results contain NaN values indicating no trades"""
    if not execution_result.get('success'):
        return False

    stdout = execution_result.get('stdout', '')

    nan_indicators = [
        '# Trades                                    0',
        'Win Rate [%]                              NaN',
        'Exposure Time [%]                         0.0',
        'Return [%]                                0.0'
    ]

    nan_count = sum(1 for indicator in nan_indicators if indicator in stdout)
    return nan_count >= 2

def analyze_no_trades_issue(execution_result: dict) -> str:
    """Analyze why strategy shows signals but no trades"""
    stdout = execution_result.get('stdout', '')

    if 'ENTRY SIGNAL' in stdout and '# Trades                                    0' in stdout:
        return "Strategy is generating entry signals but self.buy() calls are not executing. This usually means: 1) Position sizing issues (size parameter invalid), 2) Insufficient cash/equity, 3) Logic preventing buy execution, or 4) Missing actual self.buy() call in the code. The strategy prints signals but never calls self.buy()."

    elif '# Trades                                    0' in stdout:
        return "Strategy executed but took 0 trades, resulting in NaN values. The entry conditions are likely too restrictive or there are logic errors preventing trade execution."

    return "Strategy executed but took 0 trades, resulting in NaN values. Please adjust the strategy logic to actually generate trading signals and take trades."

def chat_with_model(system_prompt, user_content, model_config, thread_id):
    """Chat with AI model using model factory with rate limiting"""
    def _api_call():
        model = model_factory.get_model(model_config["type"], model_config["name"])
        if not model:
            raise ValueError(f" Could not initialize {model_config['type']} {model_config['name']} model!")

        if model_config["type"] == "ollama":
            response = model.generate_response(
                system_prompt=system_prompt,
                user_content=user_content,
                temperature=AI_TEMPERATURE
            )
            if isinstance(response, str):
                return response
            if hasattr(response, 'content'):
                return response.content
            return str(response)
        else:
            response = model.generate_response(
                system_prompt=system_prompt,
                user_content=user_content,
                temperature=AI_TEMPERATURE,
                max_tokens=AI_MAX_TOKENS
            )
            if not response:
                raise ValueError("Model returned None response")
            return response.content

    # Apply rate limiting
    return rate_limited_api_call(_api_call, thread_id)

def clean_model_output(output, content_type="text"):
    """Clean model output by removing thinking tags and extracting code from markdown"""
    cleaned_output = output

    if "<think>" in output and "</think>" in output:
        clean_content = output.split("</think>")[-1].strip()
        if not clean_content:
            import re
            clean_content = re.sub(r'<think>.*?</think>', '', output, flags=re.DOTALL).strip()
        if clean_content:
            cleaned_output = clean_content

    if content_type == "code" and "```" in cleaned_output:
        try:
            import re
            # Try to extract code blocks with closing ```
            code_blocks = re.findall(r'```python\n(.*?)\n```', cleaned_output, re.DOTALL)
            if not code_blocks:
                code_blocks = re.findall(r'```(?:python)?\n(.*?)\n```', cleaned_output, re.DOTALL)

            # If no complete blocks found, try extracting from opening fence to end
            if not code_blocks:
                # Handle case where code starts with ```python but no closing ```
                match = re.search(r'```(?:python)?\s*\n(.*)', cleaned_output, re.DOTALL)
                if match:
                    cleaned_output = match.group(1).strip()
                    # Remove any trailing ``` if present
                    if cleaned_output.endswith('```'):
                        cleaned_output = cleaned_output[:-3].strip()
            else:
                cleaned_output = "\n\n".join(code_blocks)
        except Exception as e:
            thread_print(f" Error extracting code: {str(e)}", 0, "red")

    #  Moon Dev: Final cleanup - strip any remaining markdown fences
    if content_type == "code":
        cleaned_output = cleaned_output.replace('```python', '').replace('```', '').strip()

    return cleaned_output

# ============================================
#  AI AGENT FUNCTIONS (Thread-safe versions)
# ============================================

def research_strategy(content, thread_id):
    """Research AI: Analyzes and creates trading strategy"""
    thread_print_status(thread_id, " RESEARCH", "Starting analysis...")

    # Load meta-sections (safe headers) for strategy generation guidance
    meta_text = load_meta_sections()

    # Parse idea fields to check for PDF context
    idea_fields = parse_idea_fields(content)

    # Attempt to load full PDF text if pdf_file is specified
    pdf_context = None
    if idea_fields['pdf_file']:
        thread_print(f" PDF detected: {idea_fields['pdf_file']}", thread_id, "cyan")
        pdf_context = load_pdf_full_text(idea_fields['pdf_file'])
        if pdf_context:
            pdf_size_kb = len(pdf_context) / 1024
            thread_print(f" PDF loaded: {pdf_size_kb:.1f}KB", thread_id, "green")
        else:
            thread_print(f" PDF not found, using summary only", thread_id, "yellow")

    # Build enhanced system prompt with meta-sections
    if meta_text:
        enhanced_research_prompt = f"""{RESEARCH_PROMPT}

================================================================================
 META-GUIDELINES (MANDATORY - APPLY TO ALL STRATEGY GENERATION)
================================================================================

Below are mandatory meta-guidelines that you MUST follow when analyzing and generating ANY strategy.
These are NOT strategies to backtest. They shape HOW you CREATE and EVALUATE strategies.

{meta_text}

================================================================================
END OF META-GUIDELINES
================================================================================

Now proceed with your analysis following all meta-guidelines above.
"""
    else:
        enhanced_research_prompt = RESEARCH_PROMPT

    # Build enhanced content for LLM
    if pdf_context:
        enhanced_content = f"""STRATEGY SUMMARY:
{idea_fields['content']}

================================================================================
FULL PDF TEXT FROM ACADEMIC PAPER:
================================================================================

{pdf_context}

================================================================================
END OF PDF TEXT
================================================================================

IMPORTANT: Use the full PDF text above to extract EXACT parameters and implementation details!
"""
    else:
        # Fallback to content field only
        enhanced_content = idea_fields['content']

    output = chat_with_model(
        enhanced_research_prompt,
        enhanced_content,
        RESEARCH_CONFIG,
        thread_id
    )

    if output:
        output = clean_model_output(output, "text")

        strategy_name = "UnknownStrategy"
        if "STRATEGY_NAME:" in output:
            try:
                name_section = output.split("STRATEGY_NAME:")[1].strip()
                if "\n\n" in name_section:
                    strategy_name = name_section.split("\n\n")[0].strip()
                else:
                    strategy_name = name_section.split("\n")[0].strip()

                strategy_name = re.sub(r'[^\w\s-]', '', strategy_name)
                strategy_name = re.sub(r'[\s]+', '', strategy_name)

                thread_print(f" Strategy: {strategy_name}", thread_id, "green")
            except Exception as e:
                thread_print(f" Error extracting strategy name: {str(e)}", thread_id, "yellow")

        # Add thread ID to filename
        filepath = RESEARCH_DIR / f"T{thread_id:02d}_{strategy_name}_strategy.txt"
        with file_lock:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(output)

        return output, strategy_name
    return None, None

def create_backtest(strategy, strategy_name, thread_id):
    """Backtest AI: Creates backtest implementation"""
    thread_print_status(thread_id, " BACKTEST", f"Creating code with {BACKTEST_CONFIG['name']}...")

    # Load meta-sections (safe headers) from ideas_{regime}.txt
    meta_text = load_meta_sections()

    # Get regime-specific override section
    regime_override = REGIME_OVERRIDES.get(CURRENT_REGIME, "")

    # Build enhanced system prompt with meta-sections + regime overrides
    if meta_text or regime_override:
        enhanced_backtest_prompt = f"""{BACKTEST_PROMPT}

================================================================================
 META-GUIDELINES (MANDATORY - APPLY TO ALL CODE GENERATION)
================================================================================

Below are mandatory meta-guidelines that you MUST follow when generating backtest code.
These shape HOW you implement strategies in code.

{meta_text}

================================================================================
END OF META-GUIDELINES
================================================================================
"""

        # Add regime-specific overrides AFTER meta-guidelines
        if regime_override:
            enhanced_backtest_prompt += f"""

================================================================================
 REGIME-SPECIFIC OVERRIDES (HIGHEST PRIORITY - OVERRULE CONFLICTING RULES!)
================================================================================

MARKET REGIME: {CURRENT_REGIME}

The rules below are REGIME-SPECIFIC and take ABSOLUTE PRECEDENCE over any
conflicting rules in the base prompt or meta-guidelines above.

If you see a conflict between base rules and regime overrides, ALWAYS follow
the regime override rules!

{regime_override}

================================================================================
END OF REGIME-SPECIFIC OVERRIDES
================================================================================

Now proceed with code generation following:
1. Base BACKTEST_PROMPT rules (general best practices)
2. META-GUIDELINES from ideas file (strategy-specific patterns)
3. REGIME-SPECIFIC OVERRIDES (highest priority - resolve all conflicts!)
"""
    else:
        enhanced_backtest_prompt = BACKTEST_PROMPT

    # Replace regime placeholder with actual regime value
    enhanced_backtest_prompt = enhanced_backtest_prompt.replace('{CURRENT_REGIME}', CURRENT_REGIME)

    # Replace data folder placeholder with regime-specific directory
    data_folder = MULTI_DATA_DIR.name if MULTI_DATA_DIR else 'rbi_multi'
    enhanced_backtest_prompt = enhanced_backtest_prompt.replace('{DATA_FOLDER}', data_folder)

    output = chat_with_model(
        enhanced_backtest_prompt,
        f"Create a backtest for this strategy:\n\n{strategy}",
        BACKTEST_CONFIG,
        thread_id
    )

    if output:
        output = clean_model_output(output, "code")

        filepath = BACKTEST_DIR / f"T{thread_id:02d}_{strategy_name}_BT.py"
        with file_lock:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(output)

        thread_print(f" Backtest code saved", thread_id, "green")
        return output
    return None

def package_check(backtest_code, strategy_name, thread_id):
    """Package AI: Ensures correct indicator packages are used"""
    thread_print_status(thread_id, " PACKAGE", "Checking imports...")

    output = chat_with_model(
        PACKAGE_PROMPT,
        f"Check and fix indicator packages in this code:\n\n{backtest_code}",
        PACKAGE_CONFIG,
        thread_id
    )

    if output:
        output = clean_model_output(output, "code")

        filepath = PACKAGE_DIR / f"T{thread_id:02d}_{strategy_name}_PKG.py"
        with file_lock:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(output)

        thread_print(f" Package check complete", thread_id, "green")
        return output
    return None

def debug_backtest(backtest_code, error_message, strategy_name, thread_id, iteration=1):
    """Debug AI: Fixes technical issues in backtest code"""
    thread_print_status(thread_id, f" DEBUG #{iteration}", "Fixing errors...")

    debug_prompt_with_error = DEBUG_PROMPT.format(error_message=error_message)

    output = chat_with_model(
        debug_prompt_with_error,
        f"Fix this backtest code:\n\n{backtest_code}",
        DEBUG_CONFIG,
        thread_id
    )

    if output:
        output = clean_model_output(output, "code")

        #  Moon Dev: Save debug iterations to BACKTEST_DIR, not FINAL
        # Only threshold-passing backtests go to FINAL/WORKING folders!
        filepath = BACKTEST_DIR / f"T{thread_id:02d}_{strategy_name}_DEBUG_v{iteration}.py"
        with file_lock:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(output)

        thread_print(f" Debug iteration {iteration} complete", thread_id, "green")
        return output
    return None

def optimize_strategy(backtest_code, current_return, target_return, strategy_name, thread_id, iteration=1):
    """Optimization AI: Improves strategy to hit target return"""
    thread_print_status(thread_id, f" OPTIMIZE #{iteration}", f"{current_return}%  {target_return}%")

    optimize_prompt_with_stats = OPTIMIZE_PROMPT.format(
        current_return=current_return,
        target_return=target_return
    )

    # Add regime-specific overrides to optimization
    regime_override = REGIME_OVERRIDES.get(CURRENT_REGIME, "")
    if regime_override:
        optimize_prompt_with_stats += f"""

================================================================================
 REGIME-SPECIFIC OPTIMIZATION CONSTRAINTS
================================================================================

MARKET REGIME: {CURRENT_REGIME}

When optimizing this strategy, you MUST respect these regime-specific constraints:

{regime_override}

Your optimizations must work WITHIN the regime's rules (trade frequency targets,
indicator logic, exit strategies, risk management).

DO NOT optimize in ways that violate regime constraints!

For example:
- BEAR regime: Keep trades 20-40 (don't optimize to 200+ trades)
- BULL regime: Keep trailing stops (don't add fixed TP targets)
- SIDEWAYS regime: Keep 60-120 trades (don't optimize to 5 or 500 trades)

Focus on improving WITHIN regime boundaries, not violating them!
================================================================================
"""

    output = chat_with_model(
        optimize_prompt_with_stats,
        f"Optimize this backtest code to hit the target:\n\n{backtest_code}",
        OPTIMIZE_CONFIG,
        thread_id
    )

    if output:
        output = clean_model_output(output, "code")

        filepath = OPTIMIZATION_DIR / f"T{thread_id:02d}_{strategy_name}_OPT_v{iteration}.py"
        with file_lock:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(output)

        thread_print(f" Optimization {iteration} complete", thread_id, "green")
        return output
    return None

# ============================================
#  PARALLEL PROCESSING CORE
# ============================================

def process_trading_idea_parallel(idea: str, thread_id: int) -> dict:
    """
    Process a single trading idea with full Research  Backtest  Debug  Optimize pipeline
    This is the worker function for each parallel thread
    """
    try:
        #  Moon Dev: Check if date has changed and update folders!
        update_date_folders()

        thread_print(f" Starting processing", thread_id, attrs=['bold'])

        # Phase 1: Research
        strategy, strategy_name = research_strategy(idea, thread_id)

        if not strategy:
            thread_print(" Research failed", thread_id, "red")
            return {"success": False, "error": "Research failed", "thread_id": thread_id}

        log_processed_idea(idea, strategy_name, thread_id)

        # Phase 2: Backtest
        backtest = create_backtest(strategy, strategy_name, thread_id)

        if not backtest:
            thread_print(" Backtest failed", thread_id, "red")
            return {"success": False, "error": "Backtest failed", "thread_id": thread_id}

        # Phase 3: Package Check
        package_checked = package_check(backtest, strategy_name, thread_id)

        if not package_checked:
            thread_print(" Package check failed", thread_id, "red")
            return {"success": False, "error": "Package check failed", "thread_id": thread_id}

        package_file = PACKAGE_DIR / f"T{thread_id:02d}_{strategy_name}_PKG.py"

        # Phase 3b: Health Check (Phase 1b - Pre-execution validation)
        is_valid, rejection_reason, sanitized_code = health_check_code(package_checked, strategy_name, thread_id)

        if not is_valid:
            thread_print(f" Bad code: {rejection_reason}", thread_id, "red")
            return {"success": False, "error": f"Health check failed: {rejection_reason}", "thread_id": thread_id}

        # Phase 4: Execution Loop
        debug_iteration = 0
        current_code = sanitized_code  # Use emoji-sanitized code
        current_file = package_file
        error_history = []

        while debug_iteration < MAX_DEBUG_ITERATIONS:
            thread_print_status(thread_id, " EXECUTE", f"Attempt {debug_iteration + 1}/{MAX_DEBUG_ITERATIONS}")

            execution_result = execute_backtest(current_file, strategy_name, thread_id)

            if execution_result['success']:
                if has_nan_results(execution_result):
                    thread_print(" No trades taken", thread_id, "yellow")

                    error_message = analyze_no_trades_issue(execution_result)
                    debug_iteration += 1

                    if debug_iteration < MAX_DEBUG_ITERATIONS:
                        debugged_code = debug_backtest(
                            current_code,
                            error_message,
                            strategy_name,
                            thread_id,
                            debug_iteration
                        )

                        if not debugged_code:
                            thread_print(" Debug AI failed", thread_id, "red")
                            return {"success": False, "error": "Debug failed", "thread_id": thread_id}

                        # Health check debugged code before re-execution
                        is_valid, rejection_reason, debugged_sanitized = health_check_code(debugged_code, strategy_name, thread_id)
                        if not is_valid:
                            thread_print(f" Debug produced bad code: {rejection_reason}", thread_id, "red")
                            return {"success": False, "error": f"Debug health check failed: {rejection_reason}", "thread_id": thread_id}

                        current_code = debugged_sanitized  # Use sanitized debugged code
                        #  Moon Dev: Update to match new debug file location
                        current_file = BACKTEST_DIR / f"T{thread_id:02d}_{strategy_name}_DEBUG_v{debug_iteration}.py"
                        continue
                    else:
                        thread_print(f" Max debug iterations reached", thread_id, "red")
                        return {"success": False, "error": "Max debug iterations", "thread_id": thread_id}
                else:
                    # SUCCESS! Code executes with trades!
                    thread_print(" BACKTEST SUCCESSFUL!", thread_id, "green", attrs=['bold'])

                    #  Moon Dev: Parse ALL stats, not just return!
                    all_stats = parse_all_stats_from_output(execution_result['stdout'], thread_id)
                    current_return = all_stats.get('return_pct')

                    if current_return is None:
                        thread_print(" Could not parse return", thread_id, "yellow")
                        final_file = FINAL_BACKTEST_DIR / f"T{thread_id:02d}_{strategy_name}_BTFinal_WORKING.py"
                        with file_lock:
                            with open(final_file, 'w', encoding='utf-8') as f:
                                f.write(current_code)
                        break

                    #  Moon Dev: Check threshold and save if met!
                    save_backtest_if_threshold_met(
                        current_code,
                        all_stats,
                        strategy_name,
                        debug_iteration,
                        thread_id,
                        phase="debug"
                    )

                    # Log multi-data results to CSV
                    parse_and_log_multi_data_results(strategy_name, thread_id, current_file)

                    thread_print(f" Return: {current_return}% | Target: {TARGET_RETURN}%", thread_id)

                    if current_return >= TARGET_RETURN:
                        # TARGET HIT!
                        thread_print(" TARGET HIT! ", thread_id, "green", attrs=['bold'])

                        #  Moon Dev: Save to OPTIMIZATION_DIR for target hits
                        final_file = OPTIMIZATION_DIR / f"T{thread_id:02d}_{strategy_name}_TARGET_HIT_{current_return}pct.py"
                        with file_lock:
                            with open(final_file, 'w', encoding='utf-8') as f:
                                f.write(current_code)

                        return {
                            "success": True,
                            "thread_id": thread_id,
                            "strategy_name": strategy_name,
                            "return": current_return,
                            "target_hit": True
                        }
                    else:
                        # Need to optimize
                        thread_print(f" Optimizing ({current_return}% -> {TARGET_RETURN}%)", thread_id)

                        optimization_iteration = 0
                        optimization_code = current_code
                        best_return = current_return
                        best_code = current_code
                        best_stats = all_stats

                        # Early stopping: Track consecutive iterations without improvement
                        consecutive_no_improvement = 0

                        while optimization_iteration < MAX_OPTIMIZATION_ITERATIONS:
                            optimization_iteration += 1

                            optimized_code = optimize_strategy(
                                optimization_code,
                                best_return,
                                TARGET_RETURN,
                                strategy_name,
                                thread_id,
                                optimization_iteration
                            )

                            if not optimized_code:
                                thread_print(" Optimization AI failed", thread_id, "red")
                                break

                            # Health check optimized code before execution
                            is_valid, rejection_reason, opt_sanitized = health_check_code(optimized_code, strategy_name, thread_id)
                            if not is_valid:
                                thread_print(f" Optimization produced bad code: {rejection_reason}", thread_id, "yellow")
                                continue

                            optimized_code = opt_sanitized  # Use sanitized version

                            opt_file = OPTIMIZATION_DIR / f"T{thread_id:02d}_{strategy_name}_OPT_v{optimization_iteration}.py"
                            opt_result = execute_backtest(opt_file, strategy_name, thread_id)

                            if not opt_result['success'] or has_nan_results(opt_result):
                                thread_print(f" Optimization {optimization_iteration} failed", thread_id, "yellow")
                                continue

                            #  Moon Dev: Parse ALL stats from optimization!
                            opt_stats = parse_all_stats_from_output(opt_result['stdout'], thread_id)
                            new_return = opt_stats.get('return_pct')

                            if new_return is None:
                                continue

                            change = new_return - best_return
                            thread_print(f" Opt {optimization_iteration}: {new_return}% ({change:+.1f}%)", thread_id)

                            if new_return > best_return:
                                consecutive_no_improvement = 0
                                thread_print(f" +{change:.1f}%", thread_id, "green")
                                best_return = new_return
                                best_code = optimized_code
                                optimization_code = optimized_code
                                best_stats = opt_stats

                                # Save improved version
                                save_backtest_if_threshold_met(
                                    optimized_code,
                                    opt_stats,
                                    strategy_name,
                                    optimization_iteration,
                                    thread_id,
                                    phase="opt"
                                )

                                parse_and_log_multi_data_results(
                                    strategy_name,
                                    thread_id,
                                    opt_file
                                )
                            else:
                                # No improvement - increment early stop counter
                                consecutive_no_improvement += 1
                                thread_print(f" No improvement ({consecutive_no_improvement}/2)", thread_id, "yellow")

                                if consecutive_no_improvement >= 2:
                                    thread_print(f" Early stop", thread_id, "cyan")
                                    break

                                if new_return >= TARGET_RETURN:
                                    thread_print(" TARGET HIT VIA OPTIMIZATION! ", thread_id, "green", attrs=['bold'])

                                    final_file = OPTIMIZATION_DIR / f"T{thread_id:02d}_{strategy_name}_TARGET_HIT_{new_return}pct.py"
                                    with file_lock:
                                        with open(final_file, 'w', encoding='utf-8') as f:
                                            f.write(best_code)

                                    return {
                                        "success": True,
                                        "thread_id": thread_id,
                                        "strategy_name": strategy_name,
                                        "return": new_return,
                                        "target_hit": True,
                                        "optimizations": optimization_iteration
                                    }

                        # Max optimization iterations reached
                        thread_print(f" Done optimizing. Best: {best_return}%", thread_id, "yellow")

                        best_file = OPTIMIZATION_DIR / f"T{thread_id:02d}_{strategy_name}_BEST_{best_return}pct.py"
                        with file_lock:
                            with open(best_file, 'w', encoding='utf-8') as f:
                                f.write(best_code)

                        return {
                            "success": True,
                            "thread_id": thread_id,
                            "strategy_name": strategy_name,
                            "return": best_return,
                            "target_hit": False
                        }
            else:
                # Execution failed
                error_message = parse_execution_error(execution_result)

                error_signature = error_message.split('\n')[-1] if '\n' in error_message else error_message
                if error_signature in error_history:
                    thread_print(f" Repeated error detected - stopping", thread_id, "red")
                    return {"success": False, "error": "Repeated error", "thread_id": thread_id}

                error_history.append(error_signature)
                debug_iteration += 1

                if debug_iteration < MAX_DEBUG_ITERATIONS:
                    debugged_code = debug_backtest(
                        current_code,
                        error_message,
                        strategy_name,
                        thread_id,
                        debug_iteration
                    )

                    if not debugged_code:
                        thread_print(" Debug AI failed", thread_id, "red")
                        return {"success": False, "error": "Debug failed", "thread_id": thread_id}

                    # Health check debugged code before re-execution
                    is_valid, rejection_reason, debugged_sanitized = health_check_code(debugged_code, strategy_name, thread_id)
                    if not is_valid:
                        thread_print(f" Debug produced bad code: {rejection_reason}", thread_id, "red")
                        return {"success": False, "error": f"Debug health check failed: {rejection_reason}", "thread_id": thread_id}

                    current_code = debugged_sanitized  # Use sanitized debugged code
                    #  Moon Dev: Update to match new debug file location
                    current_file = BACKTEST_DIR / f"T{thread_id:02d}_{strategy_name}_DEBUG_v{debug_iteration}.py"
                else:
                    thread_print(f" Max debug iterations reached", thread_id, "red")
                    return {"success": False, "error": "Max debug iterations", "thread_id": thread_id}

        return {"success": True, "thread_id": thread_id}

    except Exception as e:
        thread_print(f" FATAL ERROR: {str(e)}", thread_id, "red", attrs=['bold'])
        return {"success": False, "error": str(e), "thread_id": thread_id}

def idea_monitor_thread(idea_queue: Queue, queued_ideas: set, queued_lock: Lock, stop_flag: dict):
    """ Moon Dev: Producer thread - continuously monitors ideas.txt and queues new ideas"""
    global IDEAS_FILE

    while not stop_flag.get('stop', False):
        try:
            if not IDEAS_FILE.exists():
                time.sleep(1)
                continue

            with open(IDEAS_FILE, 'r', encoding='utf-8') as f:
                content = f.read()

            # Use new parser that separates strategies from meta-sections
            strategies, meta_text = parse_strategies_and_meta(content)

            # Find new unprocessed ideas (only actual strategies, not meta-sections)
            for idea in strategies:
                idea_hash = get_idea_hash(idea)

                # Check if not processed AND not already queued (thread-safe)
                with queued_lock:
                    already_queued = idea_hash in queued_ideas

                if not is_idea_processed(idea) and not already_queued:
                    idea_queue.put(idea)
                    with queued_lock:
                        queued_ideas.add(idea_hash)
                    with console_lock:
                        cprint(f" NEW IDEA QUEUED: {idea[:80]}...", "green", attrs=['bold'])

            time.sleep(1)  # Check every 1 second

        except Exception as e:
            with console_lock:
                cprint(f" Monitor thread error: {str(e)}", "red")
            time.sleep(1)


def worker_thread(worker_id: int, idea_queue: Queue, queued_ideas: set, queued_lock: Lock, stats: dict, stop_flag: dict):
    """ Moon Dev: Consumer thread - processes ideas from queue"""
    while not stop_flag.get('stop', False):
        try:
            # Get idea from queue (timeout 1 second to check stop_flag periodically)
            try:
                idea = idea_queue.get(timeout=1)
            except:
                continue  # Queue empty, check again

            # Check cost limit before processing
            if not check_cost_limit():
                with console_lock:
                    cprint(f"\n Thread {worker_id:02d} skipping idea (cost limit reached)", "yellow")
                idea_queue.task_done()
                # Put idea back in queue for tomorrow
                idea_queue.put(idea)
                time.sleep(60)  # Sleep to avoid busy loop
                continue

            with console_lock:
                stats['active'] += 1
                today_cost = get_today_cost()
                cprint(f"\n Thread {worker_id:02d} starting: {idea[:80]}... (${today_cost:.2f}/${MAX_DAILY_COST_USD:.2f} spent today)", "cyan")

            # Process the idea
            start_time = datetime.now()
            result = process_trading_idea_parallel(idea, worker_id)
            total_time = (datetime.now() - start_time).total_seconds()

            # Track cost (estimate ~$0.03 per strategy with DeepSeek-R1)
            estimated_cost = 0.03 if not USE_BUDGET_MODELS else 0.003
            new_total = add_strategy_cost(estimated_cost)

            # Remove from queued set when done (thread-safe)
            idea_hash = get_idea_hash(idea)
            with queued_lock:
                if idea_hash in queued_ideas:
                    queued_ideas.remove(idea_hash)

            # Update stats
            with console_lock:
                stats['completed'] += 1
                stats['active'] -= 1

                cprint(f"\n{'='*60}", "green")
                cprint(f" Thread {worker_id:02d} COMPLETED ({stats['completed']} total) - {total_time:.1f}s", "green", attrs=['bold'])
                if result.get('success'):
                    stats['successful'] += 1
                    if result.get('target_hit'):
                        stats['targets_hit'] += 1
                        cprint(f" TARGET HIT: {result.get('strategy_name')} @ {result.get('return')}%", "green", attrs=['bold'])
                    else:
                        cprint(f" Best return: {result.get('return', 'N/A')}%", "yellow")
                else:
                    stats['failed'] += 1
                    cprint(f" Failed: {result.get('error', 'Unknown error')}", "red")
                cprint(f"{'='*60}\n", "green")

            idea_queue.task_done()

        except Exception as e:
            with console_lock:
                cprint(f"\n Worker thread {worker_id:02d} error: {str(e)}", "red", attrs=['bold'])


def main(ideas_file_path=None, run_name=None, regime=None):
    """Main parallel processing orchestrator with multi-data testing - CONTINUOUS QUEUE MODE"""
    #  Moon Dev: Use custom ideas file if provided, otherwise select based on regime
    global IDEAS_FILE, CURRENT_REGIME, MULTI_DATA_DIR

    # BEAR 15min agent - regime is always BEAR
    CURRENT_REGIME = "BEAR"
    regime = "BEAR"

    # BEAR 15min data directory (local to RBI_Bear folder)
    MULTI_DATA_DIR = Path(__file__).parent / "rbi_regime_bear"
    cprint(f"\n  Using BEAR 15m regime data: {MULTI_DATA_DIR}", "yellow", attrs=['bold'])

    # Now setup crypto-only mode (after MULTI_DATA_DIR is set)
    setup_crypto_only_mode()

    if ideas_file_path:
        IDEAS_FILE = Path(ideas_file_path)
    else:
        # Use bear 15min ideas file in SCRIPT_DIR (RBI_Bear folder)
        IDEAS_FILE = SCRIPT_DIR / "ideas_bear_15min.txt"

    cprint(f"\n{'='*60}", "cyan", attrs=['bold'])
    cprint(f" BEAR 15m SHORT Agent | {CURRENT_DATE}", "cyan", attrs=['bold'])
    cprint(f"{'='*60}", "cyan", attrs=['bold'])
    cprint(f" Target: {TARGET_RETURN}% | Threads: {MAX_PARALLEL_THREADS} | Model: {RESEARCH_CONFIG['name']}", "green")
    cprint(f" Ideas: {IDEAS_FILE}", "magenta")
    cprint(f" Data: {MULTI_DATA_DIR}", "magenta")
    today_cost = get_today_cost()
    if today_cost > 0:
        cprint(f" Cost today: ${today_cost:.2f} / ${MAX_DAILY_COST_USD:.2f}", "yellow")
    if today_cost >= MAX_DAILY_COST_USD:
        cprint(f" COST LIMIT REACHED!", "red", attrs=['bold'])
    cprint(f"{'='*60}\n", "cyan")

    # Create template if needed
    if not IDEAS_FILE.exists():
        cprint(f" ideas.txt not found! Creating template...", "red")
        IDEAS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(IDEAS_FILE, 'w', encoding='utf-8') as f:
            f.write("# Add your trading ideas here (one per line)\n")
            f.write("# Can be YouTube URLs, PDF links, or text descriptions\n")
            f.write("# Lines starting with # are ignored\n\n")
            f.write("Create a simple RSI strategy that buys when RSI < 30 and sells when RSI > 70\n")
            f.write("Momentum strategy using 20/50 SMA crossover with volume confirmation\n")
        cprint(f" Created template ideas.txt at: {IDEAS_FILE}", "yellow")

    # Load and display initial strategy count and meta-sections
    if IDEAS_FILE.exists():
        with open(IDEAS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        strategies, meta_text = parse_strategies_and_meta(content)
        meta_count = len([block for block in meta_text.split('\n\n') if block.strip()]) if meta_text else 0
        cprint(f"\n Loaded {len(strategies)} strategies and {meta_count} meta sections.", "cyan")

    cprint(f" Queue mode: monitoring ideas file", "yellow")

    # Shared queue, queued ideas set, and stats
    idea_queue = Queue()
    queued_ideas = set()  # Track which ideas are currently queued (by hash)
    queued_lock = Lock()  # Protect access to queued_ideas set
    stats = {
        'completed': 0,
        'successful': 0,
        'failed': 0,
        'targets_hit': 0,
        'active': 0
    }
    stop_flag = {'stop': False}

    # Start monitor thread (producer)
    monitor = Thread(target=idea_monitor_thread, args=(idea_queue, queued_ideas, queued_lock, stop_flag), daemon=True)
    monitor.start()
    # Start worker threads (consumers)
    workers = []
    for worker_id in range(MAX_PARALLEL_THREADS):
        worker = Thread(target=worker_thread, args=(worker_id, idea_queue, queued_ideas, queued_lock, stats, stop_flag), daemon=True)
        worker.start()
        workers.append(worker)
    cprint(f" {MAX_PARALLEL_THREADS} workers running\n", "green")

    # Main thread just monitors stats and waits
    try:
        while True:
            time.sleep(5)  # Status update every 5 seconds

            #  Moon Dev: Check for date changes periodically (even when idle!)
            update_date_folders()

            with console_lock:
                if stats['active'] > 0 or not idea_queue.empty():
                    cprint(f" Status: {stats['active']} active | {idea_queue.qsize()} queued | {stats['completed']} completed | {stats['targets_hit']} targets hit", "cyan")
                else:
                    cprint(f" AI swarm waiting... ({stats['completed']} total completed, {stats['targets_hit']} targets hit) - {datetime.now().strftime('%I:%M:%S %p')}", "yellow")

    except KeyboardInterrupt:
        cprint(f"\n\n Shutting down gracefully...", "yellow", attrs=['bold'])
        stop_flag['stop'] = True

        cprint(f"\n{'='*60}", "cyan", attrs=['bold'])
        cprint(f" FINAL STATS", "cyan", attrs=['bold'])
        cprint(f"{'='*60}", "cyan", attrs=['bold'])
        cprint(f" Successful: {stats['successful']}", "green")
        cprint(f" Targets hit: {stats['targets_hit']}", "green", attrs=['bold'])
        cprint(f" Failed: {stats['failed']}", "red")
        cprint(f" Total completed: {stats['completed']}", "cyan")
        cprint(f"{'='*60}\n", "cyan", attrs=['bold'])

if __name__ == "__main__":
    #  Moon Dev: Parse command-line arguments for custom ideas file and run name
    parser = argparse.ArgumentParser(description="Moon Dev's RBI Agent - Parallel Backtest Processor")
    parser.add_argument('--ideas-file', type=str, help='Custom ideas file path (overrides default ideas.txt)')
    parser.add_argument('--run-name', type=str, help='Run name for folder organization')
    parser.add_argument('--regime', type=str, choices=['BEAR', 'BULL', 'SIDEWAYS'], required=True,
                        help='Market regime for strategy testing (BEAR/BULL/SIDEWAYS) - REQUIRED!')
    args = parser.parse_args()

    # Call main with optional parameters
    main(ideas_file_path=args.ideas_file, run_name=args.run_name, regime=args.regime)


