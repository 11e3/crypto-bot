#!/usr/bin/env python3
"""Test parameter sensitivity for VBO strategy.

Tests different MA values to check if strategy is overfit to specific parameters.
If performance degrades significantly with small parameter changes, it indicates overfitting.
"""

import argparse
from pathlib import Path
from itertools import product

import numpy as np
import pandas as pd


# =============================================================================
# Configuration
# =============================================================================
FEE = 0.0005
SLIPPAGE = 0.0005
NOISE_RATIO = 0.5
INITIAL_CAPITAL = 1_000_000


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
def calculate_indicators(df: pd.DataFrame, btc_df: pd.DataFrame, ma_short: int, btc_ma: int) -> pd.DataFrame:
    """Calculate technical indicators with custom MA periods."""
    df = df.copy()
    btc_df = btc_df.copy()

    btc_aligned = btc_df.reindex(df.index, method='ffill')

    df['ma_short'] = df['close'].rolling(window=ma_short).mean()
    btc_aligned['btc_ma'] = btc_aligned['close'].rolling(window=btc_ma).mean()

    df['prev_high'] = df['high'].shift(1)
    df['prev_low'] = df['low'].shift(1)
    df['prev_close'] = df['close'].shift(1)
    df['prev_ma_short'] = df['ma_short'].shift(1)

    df['prev_btc_close'] = btc_aligned['close'].shift(1)
    df['prev_btc_ma'] = btc_aligned['btc_ma'].shift(1)

    df['target_price'] = df['open'] + (df['prev_high'] - df['prev_low']) * NOISE_RATIO

    return df


def backtest_portfolio(symbols: list[str], ma_short: int, btc_ma: int,
                       start: str | None = None, end: str | None = None) -> dict:
    """Backtest VBO portfolio with custom MA parameters."""
    data = {}
    btc_df = load_data("BTC")
    btc_df = filter_date_range(btc_df, start, end)

    for symbol in symbols:
        df = load_data(symbol)
        df = filter_date_range(df, start, end)
        df = calculate_indicators(df, btc_df, ma_short, btc_ma)
        data[symbol] = df

    all_dates = set(data[list(symbols)[0]].index)
    for df in data.values():
        all_dates &= set(df.index)
    all_dates = sorted(all_dates)

    if not all_dates:
        raise ValueError("No common dates")

    cash = INITIAL_CAPITAL
    positions = {symbol: 0.0 for symbol in symbols}
    equity_curve = []
    n_strategies = len(symbols)

    for date in all_dates:
        prices = {symbol: data[symbol].loc[date] for symbol in symbols}

        valid = all(
            not pd.isna(prices[symbol]['prev_ma_short']) and
            not pd.isna(prices[symbol]['prev_btc_ma'])
            for symbol in symbols
        )

        if not valid:
            equity = cash + sum(positions[symbol] * prices[symbol]['close'] for symbol in symbols)
            equity_curve.append({'date': date, 'equity': equity})
            continue

        # SELL
        for symbol in symbols:
            if positions[symbol] > 0:
                row = prices[symbol]
                sell_signal = (row['prev_close'] < row['prev_ma_short']) or (row['prev_btc_close'] < row['prev_btc_ma'])

                if sell_signal:
                    sell_price = row['open'] * (1 - SLIPPAGE)
                    sell_value = positions[symbol] * sell_price
                    sell_fee = sell_value * FEE
                    cash += sell_value - sell_fee
                    positions[symbol] = 0.0

        # BUY
        total_equity_start = cash + sum(positions[s] * prices[s]['open'] for s in symbols)
        target_allocation = total_equity_start / n_strategies

        for symbol in symbols:
            if positions[symbol] == 0:
                row = prices[symbol]
                buy_signal = (
                    row['high'] >= row['target_price'] and
                    row['prev_close'] > row['prev_ma_short'] and
                    row['prev_btc_close'] > row['prev_btc_ma']
                )

                if buy_signal:
                    buy_value = min(target_allocation, cash)

                    if buy_value > 0:
                        buy_price = max(row['target_price'], row['open']) * (1 + SLIPPAGE)
                        buy_fee = buy_value * FEE
                        positions[symbol] = (buy_value - buy_fee) / buy_price
                        cash -= buy_value

        equity = cash + sum(positions[symbol] * prices[symbol]['close'] for symbol in symbols)
        equity_curve.append({'date': date, 'equity': equity})

    equity_df = pd.DataFrame(equity_curve)
    equity_df.set_index('date', inplace=True)

    final_equity = equity_df['equity'].iloc[-1]
    initial_equity = equity_df['equity'].iloc[0]

    days = (equity_df.index[-1] - equity_df.index[0]).days
    years = days / 365.25
    cagr = (pow(final_equity / initial_equity, 1 / years) - 1) * 100 if years > 0 else 0

    running_max = equity_df['equity'].expanding().max()
    drawdown = (equity_df['equity'] / running_max - 1) * 100
    mdd = drawdown.min()

    equity_df['daily_return'] = equity_df['equity'].pct_change()
    daily_returns = equity_df['daily_return'].dropna()
    if len(daily_returns) > 0 and daily_returns.std() > 0:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365)
    else:
        sharpe = 0.0

    return {
        'ma_short': ma_short,
        'btc_ma': btc_ma,
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe
    }


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description='Test VBO parameter sensitivity')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    args = parser.parse_args()

    symbols = ['BTC', 'ETH']  # Best combination

    print("=" * 100)
    print("PARAMETER SENSITIVITY ANALYSIS - VBO Strategy (BTC+ETH Portfolio)")
    print("=" * 100)
    print()
    print(f"Testing portfolio: {'+'.join(symbols)}")
    if args.start or args.end:
        print(f"Period: {args.start or 'inception'} ~ {args.end or 'latest'}")
    print()

    # Parameter ranges to test
    ma_short_values = [3, 5, 7, 10]
    btc_ma_values = [10, 15, 20, 25, 30]

    print("Testing parameter combinations:")
    print(f"  MA Short: {ma_short_values}")
    print(f"  BTC MA:   {btc_ma_values}")
    print()

    results = []
    total_combos = len(ma_short_values) * len(btc_ma_values)
    current = 0

    for ma_short, btc_ma in product(ma_short_values, btc_ma_values):
        current += 1
        print(f"[{current}/{total_combos}] Testing MA{ma_short}/BTC_MA{btc_ma}...", end=' ', flush=True)
        try:
            result = backtest_portfolio(symbols, ma_short, btc_ma, args.start, args.end)
            results.append(result)
            print(f"CAGR: {result['cagr']:>7.2f}%, Sharpe: {result['sharpe']:>5.2f}")
        except Exception as e:
            print(f"Error: {e}")

    print()
    print("=" * 100)
    print("RESULTS")
    print("=" * 100)
    print()

    # Display results table
    print("All Parameter Combinations:")
    print("-" * 100)
    print(f"{'MA Short':<10} {'BTC MA':<10} {'CAGR':<15} {'MDD':<15} {'Sharpe':<15}")
    print("-" * 100)

    for r in sorted(results, key=lambda x: x['sharpe'], reverse=True):
        marker = " *** DEFAULT" if r['ma_short'] == 5 and r['btc_ma'] == 20 else ""
        print(f"{r['ma_short']:<10} {r['btc_ma']:<10} {r['cagr']:>13.2f}%  {r['mdd']:>13.2f}%  {r['sharpe']:>13.2f}{marker}")

    print("-" * 100)
    print()

    # Analyze sensitivity
    default_result = next((r for r in results if r['ma_short'] == 5 and r['btc_ma'] == 20), None)

    if default_result:
        print("SENSITIVITY ANALYSIS:")
        print("-" * 100)
        print(f"Default Parameters (MA5/BTC_MA20):")
        print(f"  CAGR:   {default_result['cagr']:.2f}%")
        print(f"  Sharpe: {default_result['sharpe']:.2f}")
        print()

        # Calculate performance range
        sharpe_values = [r['sharpe'] for r in results]
        cagr_values = [r['cagr'] for r in results]

        sharpe_min, sharpe_max = min(sharpe_values), max(sharpe_values)
        cagr_min, cagr_max = min(cagr_values), max(cagr_values)

        sharpe_range = ((sharpe_max - sharpe_min) / default_result['sharpe'] * 100) if default_result['sharpe'] > 0 else 0
        cagr_range = ((cagr_max - cagr_min) / default_result['cagr'] * 100) if default_result['cagr'] > 0 else 0

        print(f"Performance Range Across All Parameters:")
        print(f"  Sharpe: {sharpe_min:.2f} - {sharpe_max:.2f} (±{sharpe_range:.1f}% from default)")
        print(f"  CAGR:   {cagr_min:.2f}% - {cagr_max:.2f}% (±{cagr_range:.1f}% from default)")
        print()

        # Rank of default
        sorted_by_sharpe = sorted(results, key=lambda x: x['sharpe'], reverse=True)
        default_rank = next((i+1 for i, r in enumerate(sorted_by_sharpe) if r['ma_short'] == 5 and r['btc_ma'] == 20), None)

        print(f"Default Parameter Ranking: #{default_rank}/{len(results)} by Sharpe")
        print()

        # Check parameters near default
        nearby_params = [
            r for r in results
            if abs(r['ma_short'] - 5) <= 2 and abs(r['btc_ma'] - 20) <= 5
        ]

        if len(nearby_params) > 1:
            nearby_sharpe = [r['sharpe'] for r in nearby_params]
            nearby_std = np.std(nearby_sharpe)
            nearby_mean = np.mean(nearby_sharpe)
            cv = (nearby_std / nearby_mean * 100) if nearby_mean > 0 else 0

            print(f"Performance Stability Near Default (±2 MA_short, ±5 BTC_MA):")
            print(f"  Mean Sharpe:  {nearby_mean:.2f}")
            print(f"  Std Dev:      {nearby_std:.2f}")
            print(f"  Variation:    {cv:.1f}%")
            print()

            if cv < 10:
                print("✅ EXCELLENT: Very stable performance near default parameters (<10% variation)")
            elif cv < 20:
                print("✅ GOOD: Stable performance near default parameters (<20% variation)")
            elif cv < 30:
                print("⚠️  FAIR: Moderate stability near default parameters (20-30% variation)")
            else:
                print("❌ WARNING: High sensitivity to parameter changes (>30% variation)")

        print()

    # Overall assessment
    print("=" * 100)
    print("OVERFITTING ASSESSMENT")
    print("=" * 100)
    print()

    if default_result:
        # Check if default is in top quartile
        sorted_results = sorted(results, key=lambda x: x['sharpe'], reverse=True)
        top_quartile = len(sorted_results) // 4

        if default_rank <= top_quartile:
            print("✅ Parameter Selection: Default parameters are in TOP 25% of all combinations")
        else:
            print("⚠️  Parameter Selection: Default parameters are NOT in top quartile")

        # Check stability
        if sharpe_range < 50:
            print("✅ Parameter Stability: Performance varies <50% across all parameters")
        else:
            print("⚠️  Parameter Stability: High variation (>50%) across parameters")

        # Check if any parameter is far better
        best_sharpe = max(sharpe_values)
        improvement = ((best_sharpe - default_result['sharpe']) / default_result['sharpe'] * 100)

        if improvement < 20:
            print(f"✅ No Cherry-Picking: Best parameters only {improvement:.1f}% better than default")
        else:
            print(f"⚠️  Potential Issue: Best parameters are {improvement:.1f}% better than default")
            best = sorted_results[0]
            print(f"   (Best: MA{best['ma_short']}/BTC_MA{best['btc_ma']}, Sharpe: {best['sharpe']:.2f})")

    print()


if __name__ == "__main__":
    main()
