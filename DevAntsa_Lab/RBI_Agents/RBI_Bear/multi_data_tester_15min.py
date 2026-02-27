"""
Moon Dev's Multi-Asset Data Tester - 15-MINUTE BEAR SPECIALIZED VERSION
Tests strategies across multiple 15m bear assets to validate robustness

DIFFERENCES FROM STANDARD VERSION:
- 15m timeframe is NOT excluded (that's what we're testing!)
- Commission is 0.00055 (0.055%) per trade for realistic 15m results (Bybit taker via CFT)
- Data directory points to RBI_Bear/rbi_regime_bear
- Only supports BEAR regime

Usage:
    from multi_data_tester_15min import test_on_all_data

    # Test on all 15m bear data
    results = test_on_all_data(YourStrategy, "YourStrategyName", regime="BEAR", verbose=False)
"""

import pandas as pd
from pathlib import Path
from backtesting import Backtest
import sys

# Configuration - 15m BEAR SPECIFIC
MULTI_DATA_DIR = Path(__file__).parent / "rbi_regime_bear"
DEFAULT_CASH = 1_000_000
DEFAULT_COMMISSION = 0.00055  # 0.055% per trade (Bybit taker fee via Crypto Fund Trader)

# NO EXCLUDED TIMEFRAMES for 15m version!
# The whole point is to test 15m data
EXCLUDED_TIMEFRAMES = []  # Empty - we WANT 15m data

# Regime-specific data directories (only BEAR supported in this version)
REGIME_DATA_DIRS = {
    "BEAR": MULTI_DATA_DIR,  # 15m bear data
}

def get_all_data_sources(regime):
    """
    Scan regime-specific folder and return list of all CSV file paths

    Args:
        regime: Market regime ("BEAR" only for 15m version)

    Returns:
        List of tuples: [(csv_path, display_name), ...]
        Example: [(Path("BTC-USD-15m.csv"), "BTC-USD-15m"), ...]
    """
    # Validate regime
    if regime not in REGIME_DATA_DIRS:
        raise ValueError(
            f"\nInvalid regime '{regime}'!\n"
            f"15m version only supports: BEAR\n"
        )

    data_dir = REGIME_DATA_DIRS[regime]

    if not data_dir.exists():
        print(f"WARNING: Data directory not found: {data_dir}")
        return []

    # Only get 15m files
    csv_files = list(data_dir.glob("*-15m.csv"))

    if not csv_files:
        print(f"WARNING: No 15m CSV files found in {data_dir}")
        return []

    # Create (path, name) tuples
    data_sources = [(csv_path, csv_path.stem) for csv_path in sorted(csv_files)]

    return data_sources

def load_and_prepare_data(csv_path):
    """
    Load CSV and prepare for backtesting.py format

    Args:
        csv_path: Path to CSV file

    Returns:
        pandas DataFrame with datetime index and OHLCV columns
        None if loading fails
    """
    try:
        df = pd.read_csv(csv_path)

        # Handle different datetime column names
        if 'datetime' in df.columns:
            df['datetime'] = pd.to_datetime(df['datetime'])
            df = df.set_index('datetime')
        elif 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
        else:
            print(f"  ERROR: No datetime/date column found in {csv_path.name}")
            return None

        # Standardize column names
        df.columns = [col.title() for col in df.columns]

        # Verify required columns
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            print(f"  ERROR: Missing columns {missing} in {csv_path.name}")
            return None

        return df[required_cols]

    except Exception as e:
        print(f"  ERROR loading {csv_path.name}: {str(e)}")
        return None

def test_single_source(strategy_class, csv_path, source_name):
    """
    Run backtest on a single data source

    Args:
        strategy_class: The strategy class to test
        csv_path: Path to CSV data file
        source_name: Display name for the data source

    Returns:
        dict with keys: data_source, return_%, buy_hold_%, max_dd_%, sharpe, sortino, expectancy_%, trades
        Returns None if backtest fails
    """
    try:
        # Load data
        data = load_and_prepare_data(csv_path)
        if data is None:
            return None

        # Run backtest with 0.055% commission for 15m
        bt = Backtest(data, strategy_class, cash=DEFAULT_CASH, commission=DEFAULT_COMMISSION)
        stats = bt.run()

        # Extract key metrics
        trades = int(stats['# Trades']) if '# Trades' in stats else 0

        # ZERO-TRADE BUG FIX: If no trades, return must be 0 (no trades = no profit/loss)
        if trades == 0:
            return_pct = 0.0
        else:
            return_pct = round(stats['Return [%]'], 2) if 'Return [%]' in stats else None

        result = {
            'Data_Source': source_name,
            'Return_%': return_pct,
            'Buy_Hold_%': round(stats['Buy & Hold Return [%]'], 2) if 'Buy & Hold Return [%]' in stats else None,
            'Max_DD_%': round(stats['Max. Drawdown [%]'], 2) if 'Max. Drawdown [%]' in stats else None,
            'Sharpe': round(stats['Sharpe Ratio'], 2) if 'Sharpe Ratio' in stats else None,
            'Sortino': round(stats['Sortino Ratio'], 2) if 'Sortino Ratio' in stats else None,
            'Expectancy_%': round(stats['Expectancy [%]'], 2) if 'Expectancy [%]' in stats else None,
            'Trades': trades
        }

        return result

    except Exception as e:
        print(f"  FAILED on {source_name}: {str(e)}")
        return None

def test_on_all_data(strategy_class, strategy_name, regime="BEAR", verbose=False):
    """
    Test strategy on all 15m data sources in bear folder

    Args:
        strategy_class: The strategy class to test
        strategy_name: Name for the strategy (used in CSV filename)
        regime: Market regime to test on ("BEAR" only for 15m version)
        verbose: If True, print detailed progress (set False in parallel processing!)

    Returns:
        pandas DataFrame with test results for all sources
        Saves results to ./results_bear_15min/ folder
        Returns None if no data sources found or all tests failed
    """
    if verbose:
        print("\n" + "="*80)
        print(f" Moon Dev's Multi-Data Tester [15m BEAR] - Testing {strategy_name}")
        print("="*80)

    # Get all 15m data sources for the specified regime
    data_sources = get_all_data_sources(regime)

    if not data_sources:
        if verbose:
            print(f"\nNo {regime} 15m data sources found!")
            print(f"Data directory: {REGIME_DATA_DIRS[regime]}")
        return None

    if verbose:
        print(f"\nFound {len(data_sources)} 15m {regime} market data sources")
        print(f"Testing {strategy_name} on all sources...\n")

    # Test on each source
    results = []

    for i, (csv_path, source_name) in enumerate(data_sources, 1):
        if verbose:
            print(f"[{i}/{len(data_sources)}] Testing on {source_name}...")

        result = test_single_source(strategy_class, csv_path, source_name)

        if result is not None:
            results.append(result)
            if verbose:
                print(f"  Return: {result['Return_%']}% | Sharpe: {result['Sharpe']} | Trades: {result['Trades']}")
        else:
            if verbose:
                print(f"  Skipped (failed to load/test)")

    # Convert to DataFrame
    if not results:
        if verbose:
            print("\nNo successful tests - all data sources failed!")
        return None

    df = pd.DataFrame(results)

    # Save results to RBI_Bear folder (same folder as this script)
    results_dir = Path(__file__).parent / "results_bear_15min"
    results_dir.mkdir(parents=True, exist_ok=True)

    results_csv = results_dir / f"{strategy_name}.csv"
    df.to_csv(results_csv, index=False)

    if verbose:
        print(f"\n" + "="*80)
        print(f" Multi-Data Testing Complete!")
        print("="*80)
        print(f"Successful tests: {len(results)}/{len(data_sources)}")
        print(f"Results saved to: {results_csv}")

        # Show summary stats
        print(f"\nSummary Across All 15m Sources:")
        print(f"  Avg Return: {df['Return_%'].mean():.2f}%")
        print(f"  Avg Sharpe: {df['Sharpe'].mean():.2f}")
        print(f"  Total Trades: {df['Trades'].sum()}")

        # Show passing sources (Sharpe >0.8)
        passing = df[df['Sharpe'] > 0.8]
        print(f"\nPassing Sources (Sharpe >0.8): {len(passing)}/{len(df)}")
        if len(passing) > 0:
            for _, row in passing.iterrows():
                print(f"  - {row['Data_Source']}: {row['Return_%']}% return, {row['Sharpe']} Sharpe")

        print("="*80 + "\n")

    return df

# Example usage
if __name__ == "__main__":
    print("\nMoon Dev's Multi-Data Tester - 15m BEAR VERSION")
    print("="*80)
    print("\nThis module is meant to be imported, not run directly.")
    print("\nUsage:")
    print("  from multi_data_tester_15min import test_on_all_data")
    print("  results = test_on_all_data(YourStrategy, 'YourStrategyName', regime='BEAR', verbose=True)")
    print("\nData directory:", MULTI_DATA_DIR)
    print("="*80 + "\n")
