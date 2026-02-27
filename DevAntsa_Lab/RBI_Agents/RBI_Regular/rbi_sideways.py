"""
 Devantsa RBI AI v3.0 PARALLEL PROCESSOR
Forked from Moon Dev's original research bot

COST SAVINGS MODE:
 Toggle USE_BUDGET_MODELS (line 140) to switch between modes:
  - True = DeepSeek Chat (~$0.003/strategy - 100x cheaper!) - USE FOR TESTING!
  - False = Claude 3.5 Sonnet (~$0.33/strategy) - USE FOR PRODUCTION!

CUSTOM VERSION FOR DEVANTSA:
- Only saves WINNING strategies (50%+ return) to dashboard
- Parallel processing with 18 threads
- Auto-debugging and optimization
- Simple ideas.txt structure

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
3. Multi-data in: DevAntsa_Lab/RBI_Agents/RBI_FullData/rbi_full_data/ (BTC/ETH/SOL 1h+4h CSVs)
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
AI_TEMPERATURE = 0.6  # DeepSeek R1 optimal temperature
AI_MAX_TOKENS = 16000  # Moon Dev: Increased for complete backtest code generation with execution block!

# Direct OpenRouter API client (no external model_factory dependency)
from openai import OpenAI

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
if not OPENROUTER_API_KEY:
    print("ERROR: OPENROUTER_API_KEY not found in .env")
    sys.exit(1)

_openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)
print(f"OpenRouter client initialized (key: {OPENROUTER_API_KEY[:8]}...)")

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
# Full list at: https://openrouter.ai/models

# ============================================
#  MODEL STACK CONFIGURATION
# ============================================
# Switch between budget (testing) and premium (production) modes
#
# Set USE_BUDGET_MODELS = True for testing (saves $$$ during debugging)
# Set USE_BUDGET_MODELS = False when agent is working (best quality)
# ============================================

USE_BUDGET_MODELS = False  #  PRODUCTION MODE - Using DeepSeek-R1!

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
#  PREMIUM MODEL STACK (DEEPSEEK-R1 - REASONING MODEL!)
# ============================================
# Production Mode: DeepSeek-R1 reasoning model for complex SMC pattern code
# Cost: ~$0.55/$2.19 per M tokens (40x cheaper than Opus, 5x cheaper than Grok-4-Fast)
# Quality: Reasoning chain helps with multi-bar pattern indexing and edge cases
# ============================================

# Premium Models (DeepSeek-R1 - Reasoning model for complex SMC code!)
PREMIUM_RESEARCH = {"type": "openrouter", "name": "deepseek/deepseek-r1"}
PREMIUM_BACKTEST = {"type": "openrouter", "name": "deepseek/deepseek-r1"}
PREMIUM_DEBUG = {"type": "openrouter", "name": "deepseek/deepseek-r1"}
PREMIUM_PACKAGE = {"type": "openrouter", "name": "deepseek/deepseek-r1"}
PREMIUM_OPTIMIZE = {"type": "openrouter", "name": "deepseek/deepseek-r1"}

# ============================================
#  ACTIVE CONFIGS (Auto-selected based on USE_BUDGET_MODELS)
# ============================================
RESEARCH_CONFIG = BUDGET_RESEARCH if USE_BUDGET_MODELS else PREMIUM_RESEARCH
BACKTEST_CONFIG = BUDGET_BACKTEST if USE_BUDGET_MODELS else PREMIUM_BACKTEST
DEBUG_CONFIG = BUDGET_DEBUG if USE_BUDGET_MODELS else PREMIUM_DEBUG
PACKAGE_CONFIG = BUDGET_PACKAGE if USE_BUDGET_MODELS else PREMIUM_PACKAGE
OPTIMIZE_CONFIG = BUDGET_OPTIMIZE if USE_BUDGET_MODELS else PREMIUM_OPTIMIZE
FALLBACK_CONFIG = {"type": "openrouter", "name": "deepseek/deepseek-chat"}  # Always cheap fallback

#  PROFIT TARGET CONFIGURATION (DEVANTSA CUSTOM)
TARGET_RETURN = 15  # Non-bull: realistic target. 100% destroyed strategies via optimizer. 15% forces optimization without breaking logic.
SAVE_IF_OVER_RETURN = 0.0  #  SAVE ALL RESULTS (even negative returns) - See everything in dashboard!
CONDA_ENV = "tflow"
MAX_DEBUG_ITERATIONS = 10  # Back to 10 - 20 takes too long and times out
MAX_OPTIMIZATION_ITERATIONS = 10  # Increased back to 10 for more thorough optimization
EXECUTION_TIMEOUT = 900  # 15 minutes - increased for 47 data sources (~19 sec per source)

# ============================================
#  DAILY COST LIMIT (SAFETY NET FOR OVERNIGHT RUNS)
# ============================================
MAX_DAILY_COST_USD = 10.0  # Stop processing if today's costs exceed $10
COST_TRACKER_FILE = Path(__file__).parent / "data" / "rbi_daily_cost.json"  # Track spending


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

# ============================================
#  DIRECTORY PATHS - All within RBI_Regular/
# ============================================
RBI_REGULAR_DIR = Path(__file__).parent  # RBI_Regular/ folder
DATA_DIR = RBI_REGULAR_DIR / "data"

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
WINNERS_DIR = None  # All winning strategies

PROCESSED_IDEAS_LOG = DATA_DIR / "processed_ideas_sideways.log"
STATS_CSV = DATA_DIR / "backtest_stats_sideways.csv"
IDEAS_FILE = RBI_REGULAR_DIR / "ideas_sideways.txt"
CURRENT_REGIME = None

# Multi-data validation settings
MULTI_DATA_DIR = None  # Set in main() - points to RBI_FullData/rbi_full_data/
ENABLE_MULTI_ASSET_VALIDATION = True

def update_date_folders():
    """
    Date Folder Updater - creates daily working directories within RBI_Regular/data/
    Thread-safe and works in always-on mode.
    """
    global CURRENT_DATE, TODAY_DIR, RESEARCH_DIR, BACKTEST_DIR, PACKAGE_DIR
    global WORKING_BACKTEST_DIR, FINAL_BACKTEST_DIR, OPTIMIZATION_DIR, CHARTS_DIR, EXECUTION_DIR, REPORTS_DIR
    global WINNERS_DIR

    with date_lock:
        new_date = datetime.now().strftime("%m_%d_%Y")

        if new_date != CURRENT_DATE:
            with console_lock:
                cprint(f"\n NEW DAY DETECTED! {CURRENT_DATE}  {new_date}", "cyan", attrs=['bold'])
                cprint(f" Creating new folder structure for {new_date}...\n", "yellow")

            CURRENT_DATE = new_date

        # Update all directory paths
        TODAY_DIR = DATA_DIR / CURRENT_DATE
        RESEARCH_DIR = TODAY_DIR / "research"
        BACKTEST_DIR = TODAY_DIR / "backtests"
        PACKAGE_DIR = TODAY_DIR / "backtests_package"
        WORKING_BACKTEST_DIR = TODAY_DIR / "backtests_working"
        FINAL_BACKTEST_DIR = TODAY_DIR / "backtests_final"
        OPTIMIZATION_DIR = TODAY_DIR / "backtests_optimized"
        CHARTS_DIR = TODAY_DIR / "charts"
        EXECUTION_DIR = TODAY_DIR / "execution_results"
        REPORTS_DIR = TODAY_DIR / "strategy_reports"

        # Winners - all qualifying strategies from all dates
        WINNERS_DIR = RBI_REGULAR_DIR / "winners_sideways"

        # Create directories
        dirs_to_create = [DATA_DIR, TODAY_DIR, RESEARCH_DIR, BACKTEST_DIR, PACKAGE_DIR,
                          WORKING_BACKTEST_DIR, FINAL_BACKTEST_DIR, OPTIMIZATION_DIR, CHARTS_DIR, EXECUTION_DIR, REPORTS_DIR,
                          WINNERS_DIR]

        for dir in dirs_to_create:
            dir.mkdir(parents=True, exist_ok=True)

# Initialize folders on startup
update_date_folders()

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
Analyze this trading strategy idea and create implementation instructions.

NAMING: If idea starts with "Thread T##:", name MUST start with that prefix (e.g. T05_AdaptiveBreakout).
Two-word name after prefix: [Approach][Technique]. Must be UNIQUE and SPECIFIC.

Output format:
STRATEGY_NAME: [name with thread prefix]

STRATEGY_DETAILS:
- Key components and SMC pattern type
- Entry/exit rules with specific parameters
- Required indicators
- Risk management approach
"""

BACKTEST_PROMPT = """
You are a backtest code generator for cryptocurrency trading strategies.

NO EMOJIS in code or print statements. Windows CP1252 encoding crashes on unicode.

BACKTESTING.PY RULES:
- _Array objects are NOT pandas. NO .shift(), .rolling(), .iloc[], .values on _Array.
- ALL indicators MUST use self.I() wrapper with pd.Series conversion inside.
- Position has NO .entry_price, .entry_bar, .sl, .tp - track manually as class variables.
- Position HAS: .size, .pl, .pl_pct, .is_long, .is_short
- Sizing: fraction 0-1. Clamp: max(0.01, min(0.5, raw_size)). Validate before buy.
- NO talib. Use pandas: SMA via rolling().mean(), EMA via ewm().mean(), all in self.I().
- NO backtesting.lib. Crossover: signal[-2] < ref[-2] and signal[-1] > ref[-1]
- _Array uses NEGATIVE indexing: [-1]=current, [-2]=previous. NO positive indexing.
- NO bt.plot(). Only print on TRADE ENTRY/EXIT, never every bar.
- Use self.equity for account value, never self._broker.

RSI helper (define OUTSIDE class):
def RSI(close, period=14):
    delta = pd.Series(close).diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


========================================================================
 STRATEGY REQUIREMENTS (SIDEWAYS SMC)
========================================================================
REGIME: SIDEWAYS MARKET. LONG ONLY. Detect institutional price action in ranges.

MANDATORY DUAL GATE (both required for every entry):
1. BEAR FLOOR: Close > SMA(200) - prevents longs during crashes.
2. BULL CEILING: ADX(14) < 30 - prevents longs during strong trends.

SMC ENTRY SIGNALS (implement ONE based on the idea):
- LIQUIDITY SWEEP: wick below recent swing low, close back above (stop hunt)
- FAIR VALUE GAP (FVG): 3-candle gap (candle[-4].High < candle[-2].Low), price returns to fill
- ORDER BLOCK: last bearish candle before a rally, price retests that zone
- MARKET STRUCTURE SHIFT (MSS): break above last lower high in a pullback
- SUPPORT RECLAIM: dip below key level (EMA/SMA) then close back above

ENTRY STRUCTURE: 4+ conditions = bear_guard + sideways_gate + SMC_signal + volume
Volume: ONE check only - Volume[-1] > N * vol_avg[-1] (N = 1.3 to 2.0)

TRADE FREQUENCY (1h data, 5 years): Target 80-300 trades. >400=churning. <20=too strict.
If <20 trades: use longer lookback (30 vs 20), accept smaller gaps, loosen confirmation.
Commission: 0.002 (0.2% round-trip). Prop firm: Max DD 5-6%, target 8-10%.

RISK MANAGEMENT - PYRAMID + ADAPTIVE TRAIL (always use this):
MAX_UNITS=3, 1% risk per unit, 3% max. Trail: 3.0x ATR at 0R, 2.5x at 2R, 2.0x at 4R.
Use indicator periods 5-20 for 1h data. Code template:
```python
class MyStrategy(Strategy):
    MAX_UNITS = 3
    def init(self):
        self.atr = self.I(lambda h, l, c: pd.Series(
            pd.concat([pd.Series(h)-pd.Series(l),
                        abs(pd.Series(h)-pd.Series(c).shift(1)),
                        abs(pd.Series(l)-pd.Series(c).shift(1))], axis=1).max(axis=1)
        ).rolling(14).mean(), self.data.High, self.data.Low, self.data.Close)
        self.entry_price = None
        self.trailing_stop = None
        self.bars_held = 0
        self.units = 0
        self.highest_since_entry = None
        self.sma200 = self.I(lambda x: pd.Series(x).rolling(200).mean(), self.data.Close)
        self.vol_avg = self.I(lambda x: pd.Series(x).rolling(20).mean(), self.data.Volume)
        # ADX(14) for sideways gate - MANDATORY
        def calc_adx(high, low, close, period=14):
            h = pd.Series(high); l = pd.Series(low); c = pd.Series(close)
            tr = pd.concat([h-l, abs(h-c.shift(1)), abs(l-c.shift(1))], axis=1).max(axis=1)
            plus_dm = ((h - h.shift(1)).clip(lower=0)).where((h - h.shift(1)) > (l.shift(1) - l), 0)
            minus_dm = ((l.shift(1) - l).clip(lower=0)).where((l.shift(1) - l) > (h - h.shift(1)), 0)
            atr = tr.rolling(period).mean()
            plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
            minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
            return dx.rolling(period).mean()
        self.adx = self.I(calc_adx, self.data.High, self.data.Low, self.data.Close)
        # ... other indicators for your SMC pattern (swing highs/lows, FVG zones, etc.) ...

    def next(self):
        atr = self.atr[-1]
        if atr is None or atr != atr or atr <= 0:
            return

        # PYRAMID ENTRY: same conditions for all units
        can_enter = self.units < self.MAX_UNITS
        if can_enter and self.units > 0:
            # Pyramid only if existing position is profitable
            if not self.position or self.position.pl <= 0:
                can_enter = False

        if can_enter:
            bear_guard = self.data.Close[-1] > self.sma200[-1]  # MANDATORY: bear floor
            sideways_gate = self.adx[-1] < 30                     # MANDATORY: bull ceiling
            entry_signal = bear_guard and sideways_gate and <smc_signal> and <volume>
            if entry_signal:
                entry_price = self.data.Close[-1]
                stop_dist = 3.5 * atr  # Fresh ATR for each unit
                raw_size = 0.01 / (stop_dist / entry_price)  # 1% risk per unit
                size = max(0.01, min(0.5, raw_size))
                if size > 0 and size < 1:
                    self.buy(size=size)
                    self.units += 1
                    print(f"Devantsa: ENTRY unit {{self.units}} at {{entry_price:.2f}}")
                    if self.units == 1:
                        self.entry_price = entry_price
                        self.trailing_stop = entry_price - stop_dist
                        self.highest_since_entry = self.data.High[-1]
                        self.bars_held = 0

        # EXIT - adaptive trailing stop management
        if self.position and self.entry_price:
            self.bars_held += 1
            if self.data.High[-1] > self.highest_since_entry:
                self.highest_since_entry = self.data.High[-1]

            # Adaptive trail: tightens as profit grows
            profit_pct = (self.data.Close[-1] - self.entry_price) / self.entry_price
            initial_risk_pct = 3.5 * atr / self.entry_price
            risk_multiples = profit_pct / max(initial_risk_pct, 0.001)

            if risk_multiples >= 4.0:
                trail_mult = 2.0   # Tight trail at 4R+ profit
            elif risk_multiples >= 2.0:
                trail_mult = 2.5   # Medium trail at 2R+ profit
            else:
                trail_mult = 3.0   # Wide trail early in trade

            new_trail = self.highest_since_entry - trail_mult * atr
            if new_trail > self.trailing_stop:
                self.trailing_stop = new_trail

            # Exit ALL units on trail hit
            if self.data.Low[-1] <= self.trailing_stop:
                self.position.close()
                print(f"Devantsa: EXIT trail ({{self.units}} units) at {{self.data.Close[-1]:.2f}}, held {{self.bars_held}} bars")
                self.entry_price = None
                self.trailing_stop = None
                self.highest_since_entry = None
                self.units = 0
                self.bars_held = 0
            # Max hold safety valve (200 bars for pyramid strategies)
            elif self.bars_held >= 200:
                self.position.close()
                print(f"Devantsa: EXIT max hold ({{self.units}} units) at {{self.data.Close[-1]:.2f}}")
                self.entry_price = None
                self.trailing_stop = None
                self.highest_since_entry = None
                self.units = 0
                self.bars_held = 0
```




BANNED: Volume percentile ranks, bt.plot(), talib, backtesting.lib, bare self.buy() without size,
fixed % stops, printing every bar, multiple volume checks, MAX_UNITS>4 or <2,
missing ADX<30 gate, missing SMA200 gate, .shift(-N) lookahead bias.

MANDATORY EXECUTION BLOCK (replace YourStrategyClassName/YourStrategyName).
Cash: $1,000,000, commission: 0.002. No plotting, no optimization.

```python
# MOON DEV'S MULTI-DATA TESTING FRAMEWORK
# Tests this strategy on 25+ data sources automatically!
if __name__ == "__main__":
    import sys
    import os
    from backtesting import Backtest
    import pandas as pd

    # FIRST: Run standard backtest and print stats (REQUIRED for parsing!)
    print("\\nRunning initial backtest for stats extraction...")
    data = pd.read_csv('{DATA_PATH}\\\\BTC-USD-1h.csv')
    data['datetime'] = pd.to_datetime(data['datetime'])
    data = data.set_index('datetime')
    data.columns = ['Open', 'High', 'Low', 'Close', 'Volume']

    bt = Backtest(data, YourStrategyClassName, cash=1_000_000, commission=0.002)
    stats = bt.run()

    # CRITICAL: Print full stats for Moon Dev's parser!
    print("\\n" + "="*80)
    print("BACKTEST STATISTICS (Moon Dev's Format)")
    print("="*80)
    print(stats)
    print("="*80 + "\\n")

    # THEN: Run multi-data testing on all data files in the data directory
    data_dir = '{DATA_PATH}'
    csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv') and '1h' in f]

    print("\\n" + "="*80)
    print(f"MULTI-DATA BACKTEST - Testing on {{len(csv_files)}} Data Sources!")
    print("="*80)

    results = []
    for csv_file in csv_files:
        try:
            test_data = pd.read_csv(os.path.join(data_dir, csv_file))
            test_data['datetime'] = pd.to_datetime(test_data['datetime'])
            test_data = test_data.set_index('datetime')
            test_data.columns = ['Open', 'High', 'Low', 'Close', 'Volume']

            bt_test = Backtest(test_data, YourStrategyClassName, cash=1_000_000, commission=0.002)
            test_stats = bt_test.run()

            result_row = {{
                'Data_Source': csv_file.replace('.csv', ''),
                'Return_%': float(test_stats['Return [%]']),
                'Buy_Hold_%': float(test_stats['Buy & Hold Return [%]']),
                'Max_DD_%': float(test_stats['Max. Drawdown [%]']),
                'Sharpe': float(test_stats['Sharpe Ratio']) if test_stats['Sharpe Ratio'] == test_stats['Sharpe Ratio'] else 0.0,
                'Sortino': float(test_stats['Sortino Ratio']) if test_stats['Sortino Ratio'] == test_stats['Sortino Ratio'] else 0.0,
                'Trades': int(test_stats['# Trades']),
                'Expectancy_%': float(test_stats['Expectancy [%]']) if test_stats['Expectancy [%]'] == test_stats['Expectancy [%]'] else 0.0
            }}
            results.append(result_row)
            print(f"  {{csv_file}}: Return={{result_row['Return_%']:.2f}}%, Sharpe={{result_row['Sharpe']:.2f}}, Trades={{result_row['Trades']}}")
        except Exception as e:
            print(f"  {{csv_file}}: ERROR - {{str(e)}}")

    if results:
        import pandas as pd
        results_df = pd.DataFrame(results)
        os.makedirs('results_sideways', exist_ok=True)
        results_csv_path = f'results_sideways/YourStrategyName.csv'
        new_avg_return = results_df['Return_%'].mean()
        save_it = True
        if os.path.exists(results_csv_path):
            try:
                old_df = pd.read_csv(results_csv_path)
                old_avg_return = old_df['Return_%'].mean()
                if new_avg_return <= old_avg_return:
                    save_it = False
                    print(f"\\nSkipping save: new avg return ({{new_avg_return:.2f}}%) <= existing ({{old_avg_return:.2f}}%)")
                else:
                    print(f"\\nUpgrading results: {{old_avg_return:.2f}}% -> {{new_avg_return:.2f}}%")
            except Exception:
                pass
        if save_it:
            results_df.to_csv(results_csv_path, index=False)
            print(f"\\nMulti-data results saved (avg return: {{new_avg_return:.2f}}%)")
        print(f"Tested on {{len(results)}} different data sources")
    else:
        print("\\nNo results generated - check for errors above")
```

REQUIREMENTS:
1. Replace YourStrategyClassName/YourStrategyName with actual names
2. Include COMPLETE execution block with multi-data testing
3. 4+ entry conditions: SMA200 + ADX<30 + SMC signal + volume
4. 1% risk per unit, clamped: max(0.01, min(0.5, raw_size))
5. Pyramid + adaptive trail always. ADX(14)<30 AND Close>SMA(200) BOTH MANDATORY.

Use this data path: {DATA_PATH}\\BTC-USD-1h.csv
The data format:
datetime,Open,High,Low,Close,Volume
2021-01-01 00:00:00,28948.19,29300.0,28946.0,29249.79,2051.23548

SEND BACK ONLY CODE, NO OTHER TEXT.

"""

DEBUG_PROMPT = """
Fix the technical error in this backtest code. Do NOT change strategy logic.
NO EMOJIS in print statements - Windows CP1252 crashes.

ERROR: {error_message}

FIX RULES:
- _Array objects are NOT pandas. NO .shift()/.rolling()/.iloc[]. Wrap in self.I(lambda x: pd.Series(x)...).
- Position has NO .entry_price/.entry_bar/.sl/.tp. Track manually as class variables.
- Size must be fraction 0-1. Clamp: max(0.01, min(0.5, raw_size)). Guard division by zero.
- NO talib. Use pandas: RSI via diff(), SMA via rolling().mean(), EMA via ewm().mean().
- NO backtesting.lib. Crossover: signal[-2] < ref[-2] and signal[-1] > ref[-1].
- Use self.equity, never self._broker.
- 0 trades: check self.buy() is reachable and size is valid.
- If fixing one issue, scan for ALL related issues of the same type.

Return COMPLETE fixed code. ONLY CODE, NO OTHER TEXT.
"""

PACKAGE_PROMPT = """
Ensure this code uses NO backtesting.lib imports or functions. NO EMOJIS in print statements.

Replace: backtesting.lib.crossover(a,b) with (a[-2]<b[-2] and a[-1]>b[-1])
Replace: backtesting.lib.SMA with self.I(lambda x,n: pd.Series(x).rolling(n).mean(), ...)
Replace: talib with pandas/numpy equivalents wrapped in self.I().

Scan ENTIRE code. Return complete fixed code. ONLY CODE, NO OTHER TEXT.
"""

OPTIMIZE_PROMPT = """
Optimize this strategy. Maximize composite: 45% Sharpe + 25% Return + 20% DD + 10% WR.
NO EMOJIS in print statements.

CURRENT: Return={current_return}%, Sharpe={current_sharpe}, DD={current_dd}%, Trades={current_trades}, WR={current_winrate}%
TARGET: {target_return}% (aspirational). ITERATION: {iteration}/{max_iterations}
{previous_attempts}

RULES:
- Sharpe 0.3 improvement = 10% return improvement in value.
- If Sharpe > 1.0, do NOT drop it below 1.0.
- Prop firm: DD MUST stay under 5%.
- Trades > 400 = CHURNING (add stricter filters). Trades < 30 = too strict (loosen detection).
- NEVER remove: SMA200 gate, ADX<30 gate (adjust 25-35 OK), pyramid, adaptive trail.
- NEVER: MAX_UNITS > 4 or < 2, risk < 0.5%/unit, max hold < 100 bars.
- Make 3+ meaningful changes per iteration.

ITERATION FOCUS (try something DIFFERENT each time):
1: ADX threshold (25/28/30/35)
2: SMC lookback (10/15/20/30 bars)
3: Volume multiplier (1.3x/1.5x/1.8x/2.0x)
4: Trail R-thresholds
5: Add/remove confirmation filter
6: SMC detection sensitivity
7: MAX_UNITS (2/3/4)
8: Add second SMC confluence signal
9: Base trail multiplier (2.5x/3.0x/3.5x ATR)
10: Combine best from above

Return COMPLETE code with comments on changes. ONLY CODE, NO OTHER TEXT.
"""


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
    """Stub - regime compliance removed in full-data mode. Always passes."""
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
            0.45 * sharpe_normalized +
            0.25 * return_normalized +
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

def log_stats_to_csv(strategy_name: str, thread_id: int, stats: dict, file_path: str, data_source: str = "BTC-USD-1h.csv") -> None:
    """
    CSV Logger - Appends backtest stats to CSV for easy analysis and comparison.
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
                    thread_print(" Created new stats CSV", thread_id, "green")

                # Write stats row
                timestamp = datetime.now().strftime("%m/%d %H:%M")
                writer.writerow([
                    strategy_name,
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

def parse_and_log_multi_data_results(strategy_name: str, thread_id: int, backtest_file_path: Path) -> None:
    """
    Multi-Asset Results Parser - logs results from multi-data testing.

    Args:
        strategy_name: Name of the strategy
        thread_id: Thread ID
        backtest_file_path: Path to the backtest file that was executed
    """
    try:
        # Results are saved in ./results/ relative to working directory
        results_dir = RBI_REGULAR_DIR / "results_sideways"
        results_csv = results_dir / f"{strategy_name}.csv"

        # Check if results exist
        if not results_csv.exists():
            thread_print(f" No multi-data results found at {results_csv}", thread_id, "yellow")
            return

        # Read the results CSV
        df = pd.read_csv(results_csv)

        # Fix naming collision: copy to thread-prefixed filename to prevent overwrites
        prefixed_csv = results_dir / f"T{thread_id:02d}_{strategy_name}.csv"
        if not strategy_name.startswith(f"T{thread_id:02d}_"):
            import shutil
            shutil.copy2(results_csv, prefixed_csv)
            thread_print(f" Saved thread-safe copy: {prefixed_csv.name}", thread_id, "cyan")

        thread_print(f" Found {len(df)} multi-data test results", thread_id, "cyan")

        # Log all results with positive returns
        passing_results = df[df['Return_%'] > SAVE_IF_OVER_RETURN]

        if len(passing_results) == 0:
            thread_print(f" No multi-data results passed {SAVE_IF_OVER_RETURN}% threshold", thread_id, "yellow")
            return

        thread_print(f" {len(passing_results)} data sources passed threshold!", thread_id, "green", attrs=['bold'])

        for idx, row in passing_results.iterrows():
            stats = {
                'return_pct': row['Return_%'],
                'buy_hold_pct': row.get('Buy_Hold_%', None),
                'max_drawdown_pct': row.get('Max_DD_%', None),
                'sharpe': row.get('Sharpe', None),
                'sortino': row.get('Sortino', None),
                'expectancy': row.get('Expectancy_%', None),
                'trades': row.get('Trades', None)
            }

            data_source = row['Data_Source']

            log_stats_to_csv(
                strategy_name,
                thread_id,
                stats,
                str(backtest_file_path),
                data_source=data_source
            )

        thread_print(f" Logged {len(passing_results)} multi-data results to CSV!", thread_id, "green", attrs=['bold'])

    except Exception as e:
        thread_print(f" Error parsing multi-data results: {str(e)}", thread_id, "red")

def check_trade_count_limit(strategy_name: str, thread_id: int, max_trades: int = 400) -> tuple:
    """
    Code-level trade count enforcement.
    Reads the results CSV and checks if ANY dataset has more than max_trades.

    Returns:
        (churning_detected: bool, warning_msg: str)
    """
    try:
        results_dir = RBI_REGULAR_DIR / "results_sideways"
        # Check both naming conventions (with and without thread prefix)
        results_csv = results_dir / f"T{thread_id:02d}_{strategy_name}.csv"
        if not results_csv.exists():
            results_csv = results_dir / f"{strategy_name}.csv"
        if not results_csv.exists():
            return (False, "")

        df = pd.read_csv(results_csv)
        if 'Trades' not in df.columns:
            return (False, "")

        churning_rows = df[df['Trades'] > max_trades]
        if len(churning_rows) == 0:
            return (False, "")

        # Build warning message with details
        details = []
        for _, row in churning_rows.iterrows():
            details.append(f"{row['Data_Source']}: {int(row['Trades'])} trades")

        warning = f"CHURNING DETECTED on {len(churning_rows)} dataset(s): {', '.join(details)}"
        thread_print(f" {warning}", thread_id, "red", attrs=['bold'])
        return (True, warning)

    except Exception as e:
        thread_print(f" Error checking trade count limit: {str(e)}", thread_id, "yellow")
        return (False, "")

def sanitize_emoji_from_code(code: str) -> str:
    """
    Strip emoji characters from code to prevent Windows CP1252 encoding errors.

    Grok sometimes adds emojis despite being told not to. This function removes them
    before execution to prevent crashes.
    """
    import re

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
        import re

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

        # Check 15: Pyramid logic consistency
        # If code defines MAX_UNITS, it must also have self.units counter
        if 'MAX_UNITS' in code and 'self.units' not in code:
            return False, "Has MAX_UNITS but no self.units counter - pyramid logic is incomplete (need self.units = 0 in init, self.units += 1 on entry, self.units = 0 on exit)", code

        # All checks passed
        thread_print(" Health check PASSED", thread_id, "green")
        return True, "", sanitized_code

    except Exception as e:
        return False, f"Health check error: {str(e)}", code

def qualify_strategy(stats: dict) -> bool:
    """
    Simple pass/fail strategy qualification.
    Returns True if strategy meets minimum quality thresholds.

    Thresholds (Non-bull SMC system):
    - Return > 0% (positive)
    - Sharpe > 0.8 (realistic floor; manually filter 1.5+ on deployment asset)
    - Max DD > -8% (prop firm safe)
    - Trades >= 50
    """
    try:
        sharpe = float(stats.get('sharpe', 0) or 0)
        max_dd = float(stats.get('max_drawdown_pct', -100) or -100)
        trades = int(stats.get('trades', 0) or 0)
        return_pct = float(stats.get('return_pct', 0) or 0)
    except (ValueError, TypeError):
        return False

    if return_pct <= 0:
        return False
    if trades < 50:
        return False
    if sharpe < 0.8:
        return False
    if max_dd < -8:
        return False

    return True

def save_backtest_if_threshold_met(code: str, stats: dict, strategy_name: str, iteration: int, thread_id: int, phase: str = "debug") -> bool:
    """
    Strategy Saver - saves qualifying strategies to winners/ folder.

    Args:
        code: The backtest code to save
        stats: Dict of parsed stats
        strategy_name: Name of the strategy
        iteration: Current iteration number
        thread_id: Thread ID
        phase: "debug", "opt", or "final" to determine filename

    Returns:
        True if saved (qualified), False if rejected
    """
    return_pct = stats.get('return_pct')

    # Simple pass/fail qualification
    if not qualify_strategy(stats):
        sharpe = stats.get('sharpe', 'N/A')
        max_dd = stats.get('max_drawdown_pct', 'N/A')
        trades = stats.get('trades', 'N/A')
        thread_print(f" REJECTED - Sharpe:{sharpe}, DD:{max_dd}%, Trades:{trades}", thread_id, "red")
        return False

    try:
        # Determine filename based on phase
        if phase == "debug":
            filename = f"T{thread_id:02d}_{strategy_name}_DEBUG_v{iteration}_{return_pct:.1f}pct.py"
        elif phase == "opt":
            filename = f"T{thread_id:02d}_{strategy_name}_OPT_v{iteration}_{return_pct:.1f}pct.py"
        else:  # final
            filename = f"T{thread_id:02d}_{strategy_name}_FINAL_{return_pct:.1f}pct.py"

        # Save to WORKING folder
        working_file = WORKING_BACKTEST_DIR / filename
        with file_lock:
            with open(working_file, 'w', encoding='utf-8') as f:
                f.write(code)

        # Save to WINNERS folder (central repository)
        winners_file = WINNERS_DIR / filename
        with file_lock:
            with open(winners_file, 'w', encoding='utf-8') as f:
                f.write(code)

        thread_print(f" WINNER! Saved! Return: {return_pct:.2f}%", thread_id, "green", attrs=['bold'])

        # Log to CSV
        log_stats_to_csv(strategy_name, thread_id, stats, str(winners_file))

        # Generate strategy report
        generate_strategy_report(strategy_name, thread_id, code, stats, phase)

        return True

    except Exception as e:
        thread_print(f" Error saving backtest: {str(e)}", thread_id, "red")
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
    """Chat with AI model via OpenRouter API with rate limiting"""
    def _api_call():
        # DeepSeek R1: merge system into user message (R1 doesn't use system prompts well)
        if "deepseek-r1" in model_config.get("name", ""):
            messages = [
                {"role": "user", "content": system_prompt + "\n\n" + user_content},
            ]
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
        response = _openrouter_client.chat.completions.create(
            model=model_config["name"],
            messages=messages,
            temperature=AI_TEMPERATURE,
            max_tokens=AI_MAX_TOKENS,
        )
        if not response or not response.choices:
            raise ValueError(f"Empty response from {model_config['name']}")
        return response.choices[0].message.content

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

    # Load meta-sections (safe headers) from ideas.txt
    meta_text = load_meta_sections()

    # Build enhanced system prompt with meta-sections
    if meta_text:
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
    else:
        enhanced_backtest_prompt = BACKTEST_PROMPT

    # Replace data path placeholder with actual data directory (double-escaped for generated Python code)
    data_path = str(MULTI_DATA_DIR).replace('\\', '\\\\') if MULTI_DATA_DIR else ''
    enhanced_backtest_prompt = enhanced_backtest_prompt.replace('{DATA_PATH}', data_path)

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

def _strip_comments_for_compare(code):
    """Strip comments and whitespace for code identity comparison"""
    lines = []
    for line in code.splitlines():
        stripped = line.split('#')[0].rstrip()
        if stripped:
            lines.append(stripped)
    return '\n'.join(lines)


def optimize_strategy(backtest_code, current_return, target_return, strategy_name, thread_id, iteration=1, stats=None, previous_attempts=None, churning_warning=None):
    """Optimization AI: Improves strategy to hit target return"""
    thread_print_status(thread_id, f" OPTIMIZE #{iteration}", f"{current_return}%  {target_return}%")

    # Build previous attempts summary
    prev_text = ""
    if previous_attempts:
        prev_text = "PREVIOUS ATTEMPTS (do NOT repeat these, try something DIFFERENT):\n"
        for attempt in previous_attempts:
            prev_text += f"- Iteration {attempt['iter']}: Return {attempt['ret']}%, Sharpe {attempt['sharpe']}\n"

    # Add churning warning if detected
    if churning_warning:
        prev_text += f"\nCRITICAL WARNING: {churning_warning}\nYou MUST add stricter entry filters to reduce trade count below 400. Tighten SMC detection (shorter lookback, require bullish candle confirmation), raise volume threshold, or add RSI < 40 filter.\n"

    # Extract stats for the prompt
    current_sharpe = stats.get('sharpe', 'N/A') if stats else 'N/A'
    current_dd = stats.get('max_drawdown_pct', 'N/A') if stats else 'N/A'
    current_trades = stats.get('trades', 'N/A') if stats else 'N/A'
    current_winrate = stats.get('win_rate', 'N/A') if stats else 'N/A'

    optimize_prompt_with_stats = OPTIMIZE_PROMPT.format(
        current_return=current_return,
        target_return=target_return,
        current_sharpe=current_sharpe,
        current_dd=current_dd,
        current_trades=current_trades,
        current_winrate=current_winrate,
        iteration=iteration,
        max_iterations=MAX_OPTIMIZATION_ITERATIONS,
        previous_attempts=prev_text
    )

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
        thread_print(" Running health check...", thread_id, "cyan")
        is_valid, rejection_reason, sanitized_code = health_check_code(package_checked, strategy_name, thread_id)

        if not is_valid:
            thread_print(f" HEALTH CHECK FAILED: {rejection_reason}", thread_id, "red", attrs=['bold'])
            thread_print(" Skipping execution (bad code rejected)", thread_id, "yellow")
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

                    #  Moon Dev: Parse and log multi-data results!
                    thread_print(" Checking for multi-data test results...", thread_id, "cyan")
                    parse_and_log_multi_data_results(
                        strategy_name,
                        thread_id,
                        current_file
                    )

                    # Code-level trade count enforcement (Batch 5)
                    churning_detected, churning_warning = check_trade_count_limit(strategy_name, thread_id)
                    if churning_detected:
                        thread_print(f" Optimizer will be told to add stricter filters", thread_id, "yellow")

                    #  PHASE 2: Calculate composite score for multi-objective optimization
                    current_composite_score = calculate_composite_score(all_stats, thread_id)

                    if current_composite_score is not None:
                        thread_print(f" Return: {current_return}% | Composite Score: {current_composite_score:.2f} | Target: {TARGET_RETURN}%", thread_id)
                    else:
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
                        gap = TARGET_RETURN - current_return
                        thread_print(f" Need {gap}% more - Starting optimization", thread_id)

                        optimization_iteration = 0
                        optimization_code = current_code
                        best_return = current_return
                        best_code = current_code
                        best_composite_score = current_composite_score if current_composite_score is not None else 0.0
                        best_stats = all_stats

                        # Early stopping: Track consecutive iterations without improvement
                        consecutive_no_improvement = 0
                        # Track previous optimization attempts for context
                        opt_history = []

                        while optimization_iteration < MAX_OPTIMIZATION_ITERATIONS:
                            optimization_iteration += 1

                            optimized_code = optimize_strategy(
                                optimization_code,
                                best_return,
                                TARGET_RETURN,
                                strategy_name,
                                thread_id,
                                optimization_iteration,
                                stats=best_stats,
                                previous_attempts=opt_history if opt_history else None,
                                churning_warning=churning_warning if churning_detected else None
                            )

                            if not optimized_code:
                                thread_print(" Optimization AI failed", thread_id, "red")
                                break

                            # Code identity check: skip if Grok returned identical code
                            if _strip_comments_for_compare(optimized_code) == _strip_comments_for_compare(optimization_code):
                                thread_print(f" Opt {optimization_iteration}: IDENTICAL code returned - skipping execution", thread_id, "yellow")
                                consecutive_no_improvement += 1
                                if consecutive_no_improvement >= 2:
                                    thread_print(f" Early stop: Identical code in {consecutive_no_improvement} consecutive iterations", thread_id, "cyan")
                                    break
                                continue

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

                            # Track this attempt for history context
                            opt_history.append({
                                'iter': optimization_iteration,
                                'ret': round(new_return, 2),
                                'sharpe': round(opt_stats.get('sharpe', 0) or 0, 2)
                            })

                            #  PHASE 2: Calculate composite score for optimization comparison
                            new_composite_score = calculate_composite_score(opt_stats, thread_id)

                            # Display results with composite score
                            change = new_return - best_return
                            if new_composite_score is not None:
                                score_change = new_composite_score - best_composite_score
                                thread_print(f" Opt {optimization_iteration}: {new_return}% ({change:+.2f}%) | Score: {new_composite_score:.2f} ({score_change:+.2f})", thread_id)
                            else:
                                thread_print(f" Opt {optimization_iteration}: {new_return}% ({change:+.2f}%)", thread_id)

                            #  PHASE 2: Compare using composite score instead of just return
                            # If composite score available, use it for comparison; otherwise fall back to return
                            is_improvement = False
                            if new_composite_score is not None and best_composite_score is not None:
                                is_improvement = new_composite_score > best_composite_score
                            else:
                                # Fallback to return comparison if composite score unavailable
                                is_improvement = new_return > best_return

                            if is_improvement:
                                # Reset early stop counter on improvement
                                consecutive_no_improvement = 0
                                if new_composite_score is not None:
                                    thread_print(f" Improved composite score by {score_change:.2f}!", thread_id, "green")
                                else:
                                    thread_print(f" Improved by {change:.2f}%!", thread_id, "green")
                                best_return = new_return
                                best_code = optimized_code
                                optimization_code = optimized_code
                                best_stats = opt_stats
                                if new_composite_score is not None:
                                    best_composite_score = new_composite_score

                                #  Moon Dev: Check threshold and save if met!
                                save_backtest_if_threshold_met(
                                    optimized_code,
                                    opt_stats,
                                    strategy_name,
                                    optimization_iteration,
                                    thread_id,
                                    phase="opt"
                                )

                                #  Moon Dev: Parse and log multi-data results from optimization!
                                thread_print(" Checking for multi-data test results...", thread_id, "cyan")
                                parse_and_log_multi_data_results(
                                    strategy_name,
                                    thread_id,
                                    opt_file
                                )

                                # Re-check trade count after optimization (Batch 5)
                                churning_detected, churning_warning = check_trade_count_limit(strategy_name, thread_id)
                                if churning_detected:
                                    thread_print(f" Optimization still churning - will warn next iteration", thread_id, "yellow")
                            else:
                                # No improvement - increment early stop counter
                                consecutive_no_improvement += 1
                                thread_print(f" No improvement (strike {consecutive_no_improvement}/2)", thread_id, "yellow")

                                # Early stopping: Break if no improvement in 2 consecutive iterations
                                if consecutive_no_improvement >= 2:
                                    thread_print(f" Early stop: No improvement in 2 consecutive iterations", thread_id, "cyan")
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
                        if best_composite_score > 0:
                            thread_print(f" Max optimizations reached. Best: {best_return}% | Composite Score: {best_composite_score:.2f}", thread_id, "yellow")
                        else:
                            thread_print(f" Max optimizations reached. Best: {best_return}%", thread_id, "yellow")

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


def main(ideas_file_path=None, run_name=None, fulldata=True):
    """Main parallel processing orchestrator with full-data testing - CONTINUOUS QUEUE MODE"""
    global IDEAS_FILE, CURRENT_REGIME, MULTI_DATA_DIR

    # FULLDATA MODE: Use full market data (Jan 2021+) - primary mode
    if fulldata:
        CURRENT_REGIME = 'FULLDATA'
        MULTI_DATA_DIR = RBI_REGULAR_DIR.parent / "RBI_FullData" / "rbi_full_data"
        cprint(f"\n  FULL-DATA MODE: Using all-regime data (Jan 2021+): {MULTI_DATA_DIR}", "green", attrs=['bold'])
        if not MULTI_DATA_DIR.exists():
            raise FileNotFoundError(f"Full data directory not found: {MULTI_DATA_DIR}\nRun download_full_data.py first!")
    else:
        raise ValueError(
            f"\n{'='*80}\n"
            f"ERROR: You MUST specify --fulldata mode!\n"
            f"\n"
            f"Usage:\n"
            f"  python rbi_agent_pp_multi_devantsa.py --fulldata\n"
            f"{'='*80}\n"
        )

    if ideas_file_path:
        IDEAS_FILE = Path(ideas_file_path)
    else:
        # Use the sideways ideas file in RBI_Regular/
        IDEAS_FILE = RBI_REGULAR_DIR / "ideas_sideways.txt"

    cprint(f"\n{'='*60}", "cyan", attrs=['bold'])
    cprint(f" Moon Dev's RBI AI v3.0 PARALLEL PROCESSOR + MULTI-DATA ", "cyan", attrs=['bold'])
    cprint(f"{'='*60}", "cyan", attrs=['bold'])

    cprint(f"\n Date: {CURRENT_DATE}", "magenta")
    cprint(f" Target Return: {TARGET_RETURN}%", "green", attrs=['bold'])
    cprint(f" Save Threshold: {SAVE_IF_OVER_RETURN}%", "green", attrs=['bold'])
    cprint(f" Max Parallel Threads: {MAX_PARALLEL_THREADS}", "yellow", attrs=['bold'])

    # Show cost tracking
    today_cost = get_today_cost()
    cprint(f" Daily Cost Limit: ${MAX_DAILY_COST_USD:.2f}", "yellow", attrs=['bold'])
    cprint(f" Spent Today: ${today_cost:.2f}", "cyan")
    if today_cost >= MAX_DAILY_COST_USD:
        cprint(f" COST LIMIT REACHED - Agent will pause until tomorrow!", "red", attrs=['bold'])

    # Show model configuration
    if USE_BUDGET_MODELS:
        cprint(f" AI Model: {RESEARCH_CONFIG['name']} (BUDGET - TESTING MODE)", "yellow", attrs=['bold'])
        cprint(f" Est. Cost: ~$0.003 per strategy (100x cheaper!)", "green")
    else:
        cprint(f" AI Model: {RESEARCH_CONFIG['name']} (PREMIUM - PRODUCTION MODE)", "cyan", attrs=['bold'])
        cprint(f" Est. Cost: ~$0.03 per strategy (DeepSeek-R1 - Reliable code generation!)", "yellow")

    cprint(f" Conda env: {CONDA_ENV}", "cyan")
    cprint(f" Data dir: {MULTI_DATA_DIR}", "magenta")
    cprint(f" Ideas file: {IDEAS_FILE}", "magenta")
    cprint(f" Mode: FULLDATA (Jan 2021+)", "green", attrs=['bold'])
    if run_name:
        cprint(f" Run Name: {run_name}\n", "green", attrs=['bold'])
    else:
        cprint("", "white")

    # Display Model Stack Configuration
    cprint(f"\n{'='*60}", "cyan")
    cprint(f" STABLE MODEL STACK CONFIGURATION", "cyan", attrs=['bold'])
    cprint(f"{'='*60}", "cyan")
    cprint(f" Research:      {RESEARCH_CONFIG['name']}", "green")
    cprint(f" Code Gen:      {BACKTEST_CONFIG['name']}", "green", attrs=['bold'])
    cprint(f" Debugging:     {DEBUG_CONFIG['name']}", "green", attrs=['bold'])
    cprint(f" Optimization:  {OPTIMIZE_CONFIG['name']}", "green", attrs=['bold'])
    cprint(f" Fallback:      {FALLBACK_CONFIG['name']}", "yellow")
    cprint(f" Package Check: {PACKAGE_CONFIG['name']}", "cyan")
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

    #  Moon Dev: CONTINUOUS QUEUE MODE
    cprint(f"\n CONTINUOUS QUEUE MODE ACTIVATED", "cyan", attrs=['bold'])
    cprint(f"Monitoring ideas.txt every 1 second", "yellow")
    cprint(f"{MAX_PARALLEL_THREADS} worker threads ready\n", "yellow")

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
    cprint(" Idea monitor thread started", "green")

    # Start worker threads (consumers)
    workers = []
    for worker_id in range(MAX_PARALLEL_THREADS):
        worker = Thread(target=worker_thread, args=(worker_id, idea_queue, queued_ideas, queued_lock, stats, stop_flag), daemon=True)
        worker.start()
        workers.append(worker)
    cprint(f" {MAX_PARALLEL_THREADS} worker threads started (IDs 00-{MAX_PARALLEL_THREADS-1:02d})\n", "green")

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
    parser = argparse.ArgumentParser(description="Moon Dev's RBI Agent - Full-Data Parallel Backtest Processor")
    parser.add_argument('--ideas-file', type=str, help='Custom ideas file path (overrides default ideas.txt)')
    parser.add_argument('--run-name', type=str, help='Run name for folder organization')
    parser.add_argument('--fulldata', action='store_true', default=True,
                        help='Use full market data (Jan 2021+) - default mode')
    args = parser.parse_args()

    main(ideas_file_path=args.ideas_file, run_name=args.run_name, fulldata=True)


