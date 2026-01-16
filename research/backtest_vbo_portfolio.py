#!/usr/bin/env python3
"""Backtest VBO portfolio strategies with all combinations.

Tests all combinations of 2, 3, 4, and 5 cryptocurrencies.
Each strategy allocates 1/n of total equity when buying.

Usage:
    python backtest_vbo_portfolio.py
    python backtest_vbo_portfolio.py --start 2020-01-01 --end 2024-12-31
"""

import argparse
from pathlib import Path
from itertools import combinations

import numpy as np
import pandas as pd


# =============================================================================
# Configuration
# =============================================================================
FEE = 0.0005  # 0.05% trading fee
SLIPPAGE = 0.0005  # 0.05% slippage
MA_SHORT = 5  # Short MA for coin
BTC_MA = 20  # BTC MA for market filter
NOISE_RATIO = 0.5  # VBO breakout multiplier
INITIAL_CAPITAL = 1_000_000  # 1M KRW


# =============================================================================
# Data Loading
# =============================================================================
def load_data(symbol: str, data_dir: str = "data") -> pd.DataFrame:
    """Load OHLCV data for a single symbol."""
    filepath = Path(data_dir) / f"{symbol}.csv"
    if not filepath.exists():
        raise FileNotFoundError(f"No data for {symbol}: {filepath}")

    df = pd.read_csv(filepath, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    df = df.sort_index()
    return df


def filter_date_range(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    """Filter dataframe by date range."""
    if start:
        df = df[df.index >= pd.to_datetime(start)]
    if end:
        df = df[df.index <= pd.to_datetime(end)]
    return df


# =============================================================================
# Strategy Logic
# =============================================================================
def calculate_indicators(df: pd.DataFrame, btc_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate technical indicators for the strategy."""
    df = df.copy()
    btc_df = btc_df.copy()

    # Align BTC data with coin data
    btc_aligned = btc_df.reindex(df.index, method='ffill')

    # Calculate coin MA5
    df['ma5'] = df['close'].rolling(window=MA_SHORT).mean()

    # Calculate BTC MA20
    btc_aligned['btc_ma20'] = btc_aligned['close'].rolling(window=BTC_MA).mean()

    # Previous day values for coin
    df['prev_high'] = df['high'].shift(1)
    df['prev_low'] = df['low'].shift(1)
    df['prev_close'] = df['close'].shift(1)
    df['prev_ma5'] = df['ma5'].shift(1)

    # Previous day values for BTC
    df['prev_btc_close'] = btc_aligned['close'].shift(1)
    df['prev_btc_ma20'] = btc_aligned['btc_ma20'].shift(1)

    # VBO target price
    df['target_price'] = df['open'] + (df['prev_high'] - df['prev_low']) * NOISE_RATIO

    return df


def backtest_portfolio(symbols: list[str], start: str | None = None, end: str | None = None) -> dict:
    """Backtest VBO portfolio strategy with multiple cryptocurrencies.

    Args:
        symbols: List of cryptocurrency symbols to trade
        start: Start date (YYYY-MM-DD)
        end: End date (YYYY-MM-DD)

    Returns:
        dict with portfolio metrics
    """
    # Load and prepare data for all symbols
    data = {}
    btc_df = load_data("BTC")
    btc_df = filter_date_range(btc_df, start, end)

    for symbol in symbols:
        df = load_data(symbol)
        df = filter_date_range(df, start, end)
        df = calculate_indicators(df, btc_df)
        data[symbol] = df

    # Get common date range
    all_dates = set(data[list(symbols)[0]].index)
    for df in data.values():
        all_dates &= set(df.index)
    all_dates = sorted(all_dates)

    if not all_dates:
        raise ValueError("No common dates across all symbols")

    # Initialize portfolio
    cash = INITIAL_CAPITAL
    positions = {symbol: 0.0 for symbol in symbols}  # Amount of each coin held
    equity_curve = []
    n_strategies = len(symbols)

    for date in all_dates:
        # Get current prices
        prices = {symbol: data[symbol].loc[date] for symbol in symbols}

        # Check if we have valid indicators
        valid = all(
            not pd.isna(prices[symbol]['prev_ma5']) and
            not pd.isna(prices[symbol]['prev_btc_ma20'])
            for symbol in symbols
        )

        if not valid:
            # Record equity
            equity = cash + sum(positions[symbol] * prices[symbol]['close'] for symbol in symbols)
            equity_curve.append({'date': date, 'equity': equity})
            continue

        # === SELL LOGIC (execute at open) ===
        for symbol in symbols:
            if positions[symbol] > 0:
                row = prices[symbol]
                # Sell condition: Prev Close < Prev MA5 OR Prev BTC Close < Prev BTC MA20
                sell_signal = (row['prev_close'] < row['prev_ma5']) or (row['prev_btc_close'] < row['prev_btc_ma20'])

                if sell_signal:
                    sell_price = row['open'] * (1 - SLIPPAGE)
                    sell_value = positions[symbol] * sell_price
                    sell_fee = sell_value * FEE
                    cash += sell_value - sell_fee
                    positions[symbol] = 0.0

        # === BUY LOGIC ===
        # Step 1: Collect buy candidates
        buy_candidates = []
        for symbol in symbols:
            if positions[symbol] == 0:
                row = prices[symbol]
                buy_signal = (
                    row['high'] >= row['target_price'] and
                    row['prev_close'] > row['prev_ma5'] and
                    row['prev_btc_close'] > row['prev_btc_ma20']
                )
                if buy_signal:
                    buy_candidates.append(symbol)

        # Step 2: Allocate based on total equity / n_strategies (matches bot logic)
        if buy_candidates and cash > 0:
            total_equity = cash + sum(positions[s] * prices[s]['open'] for s in symbols)
            target_alloc = total_equity / n_strategies

            for symbol in buy_candidates:
                row = prices[symbol]
                buy_value = min(target_alloc, cash * 0.99)
                if buy_value <= 0:
                    continue
                buy_price = row['target_price'] * (1 + SLIPPAGE)
                buy_fee = buy_value * FEE
                positions[symbol] = (buy_value - buy_fee) / buy_price
                cash -= buy_value

        # Record equity (at close prices)
        equity = cash + sum(positions[symbol] * prices[symbol]['close'] for symbol in symbols)
        equity_curve.append({'date': date, 'equity': equity})

    # Convert to DataFrame
    equity_df = pd.DataFrame(equity_curve)
    equity_df.set_index('date', inplace=True)

    # Calculate metrics
    final_equity = equity_df['equity'].iloc[-1]
    initial_equity = equity_df['equity'].iloc[0]
    total_return = (final_equity / initial_equity - 1) * 100

    # CAGR
    days = (equity_df.index[-1] - equity_df.index[0]).days
    years = days / 365.25
    cagr = (pow(final_equity / initial_equity, 1 / years) - 1) * 100 if years > 0 else 0

    # MDD
    running_max = equity_df['equity'].expanding().max()
    drawdown = (equity_df['equity'] / running_max - 1) * 100
    mdd = drawdown.min()

    # Sharpe Ratio
    equity_df['daily_return'] = equity_df['equity'].pct_change()
    daily_returns = equity_df['daily_return'].dropna()
    if len(daily_returns) > 0 and daily_returns.std() > 0:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365)
    else:
        sharpe = 0.0

    return {
        'symbols': symbols,
        'symbols_str': '+'.join(symbols),
        'n_coins': len(symbols),
        'total_return': total_return,
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
        'final_equity': final_equity
    }


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description='Backtest VBO portfolio strategies')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    args = parser.parse_args()

    # All cryptocurrencies
    all_symbols = ['BTC', 'ETH', 'XRP', 'TRX', 'ADA']

    print("=" * 100)
    print("VBO Portfolio Strategy Backtest - All Combinations")
    print("=" * 100)
    print(f"\nStrategy: VBO with MA{MA_SHORT} and BTC MA{BTC_MA}")
    print(f"Fee: {FEE*100}%, Slippage: {SLIPPAGE*100}%")
    print(f"Initial Capital: {INITIAL_CAPITAL:,} KRW")
    if args.start or args.end:
        print(f"Period: {args.start or 'inception'} ~ {args.end or 'latest'}")
    print()

    # Generate all combinations
    all_results = []

    for n in range(2, 6):  # 2, 3, 4, 5 coins
        print(f"\n{'='*100}")
        print(f"{n}-COIN COMBINATIONS (C(5,{n}) = {len(list(combinations(all_symbols, n)))} combinations)")
        print(f"{'='*100}\n")

        combo_results = []
        for combo in combinations(all_symbols, n):
            symbols = list(combo)
            print(f"Testing {'+'.join(symbols)}...", end=' ', flush=True)
            try:
                result = backtest_portfolio(symbols, args.start, args.end)
                combo_results.append(result)
                all_results.append(result)
                print(f"CAGR: {result['cagr']:>7.2f}%, MDD: {result['mdd']:>7.2f}%, Sharpe: {result['sharpe']:>5.2f}")
            except Exception as e:
                print(f"Error: {e}")

        # Display top 5 for this combination size
        if combo_results:
            combo_results.sort(key=lambda x: x['sharpe'], reverse=True)
            print(f"\nTop 5 by Sharpe Ratio ({n}-coin combinations):")
            print("-" * 100)
            print(f"{'Combination':<25} {'CAGR':<12} {'MDD':<12} {'Sharpe':<12}")
            print("-" * 100)
            for r in combo_results[:5]:
                print(f"{r['symbols_str']:<25} {r['cagr']:>10.2f}%  {r['mdd']:>10.2f}%  {r['sharpe']:>10.2f}")

    # Overall best performers
    print("\n" + "=" * 100)
    print("OVERALL BEST PERFORMERS (All Combinations)")
    print("=" * 100)

    # Best by Sharpe
    all_results.sort(key=lambda x: x['sharpe'], reverse=True)
    print(f"\nTop 10 by Sharpe Ratio:")
    print("-" * 100)
    print(f"{'Combination':<25} {'N':<5} {'CAGR':<12} {'MDD':<12} {'Sharpe':<12}")
    print("-" * 100)
    for r in all_results[:10]:
        print(f"{r['symbols_str']:<25} {r['n_coins']:<5} {r['cagr']:>10.2f}%  {r['mdd']:>10.2f}%  {r['sharpe']:>10.2f}")

    # Best by CAGR
    all_results.sort(key=lambda x: x['cagr'], reverse=True)
    print(f"\nTop 10 by CAGR:")
    print("-" * 100)
    print(f"{'Combination':<25} {'N':<5} {'CAGR':<12} {'MDD':<12} {'Sharpe':<12}")
    print("-" * 100)
    for r in all_results[:10]:
        print(f"{r['symbols_str']:<25} {r['n_coins']:<5} {r['cagr']:>10.2f}%  {r['mdd']:>10.2f}%  {r['sharpe']:>10.2f}")

    # Best by MDD (least negative)
    all_results.sort(key=lambda x: x['mdd'], reverse=True)
    print(f"\nTop 10 by MDD (lowest drawdown):")
    print("-" * 100)
    print(f"{'Combination':<25} {'N':<5} {'CAGR':<12} {'MDD':<12} {'Sharpe':<12}")
    print("-" * 100)
    for r in all_results[:10]:
        print(f"{r['symbols_str']:<25} {r['n_coins']:<5} {r['cagr']:>10.2f}%  {r['mdd']:>10.2f}%  {r['sharpe']:>10.2f}")

    print("\n")


if __name__ == "__main__":
    main()
