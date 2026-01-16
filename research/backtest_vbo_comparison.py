#!/usr/bin/env python3
"""Backtest VBO strategy for individual cryptocurrencies.

Strategy:
- Buy Price: Daily Open + (Previous High - Previous Low) * 0.5
- Buy Condition: Daily High >= Target AND Prev Close > Prev MA5 AND Prev BTC Close > Prev BTC MA20
- Sell Price: Daily Open
- Sell Condition: Prev Close < Prev MA5 OR Prev BTC Close < Prev BTC MA20
- Parameters: MA5, BTC_MA20

Usage:
    python backtest_vbo_comparison.py
    python backtest_vbo_comparison.py --start 2020-01-01 --end 2024-12-31
"""

import argparse
from pathlib import Path
from datetime import datetime

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
    """Calculate technical indicators for the strategy.

    Returns a copy of df with added columns:
    - ma5: 5-day moving average of close
    - prev_high, prev_low, prev_close, prev_ma5: Previous day values
    - target_price: VBO breakout price (Open + (Prev High - Prev Low) * 0.5)
    - btc_ma20, prev_btc_close, prev_btc_ma20: Bitcoin indicators
    """
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

    # VBO target price: Today's open + (Yesterday's high - Yesterday's low) * noise_ratio
    df['target_price'] = df['open'] + (df['prev_high'] - df['prev_low']) * NOISE_RATIO

    return df


def backtest_single_coin(symbol: str, start: str | None = None, end: str | None = None) -> tuple[dict, pd.DataFrame]:
    """Backtest VBO strategy for a single cryptocurrency.

    Returns:
        tuple: (dict with metrics, equity_curve DataFrame)
    """
    # Load data
    df = load_data(symbol)
    btc_df = load_data("BTC")

    # Filter date range
    df = filter_date_range(df, start, end)
    btc_df = filter_date_range(btc_df, start, end)

    # Calculate indicators
    df = calculate_indicators(df, btc_df)

    # Initialize backtest variables
    cash = 1_000_000  # Start with 1M KRW
    position = 0.0  # Amount of coin held
    position_entry_price = 0.0
    trades = []
    equity_curve = []

    for i, (date, row) in enumerate(df.iterrows()):
        # Skip if we don't have enough data for indicators
        if pd.isna(row['prev_ma5']) or pd.isna(row['prev_btc_ma20']):
            equity = cash + position * row['close']
            equity_curve.append({'date': date, 'equity': equity})
            continue

        equity_start = cash + position * row['close']

        # === SELL LOGIC (check first, execute at open) ===
        if position > 0:
            # Sell condition: Prev Close < Prev MA5 OR Prev BTC Close < Prev BTC MA20
            sell_signal = (row['prev_close'] < row['prev_ma5']) or (row['prev_btc_close'] < row['prev_btc_ma20'])

            if sell_signal:
                sell_price = row['open']
                # Apply slippage (sell at slightly lower price)
                sell_price_actual = sell_price * (1 - SLIPPAGE)

                # Execute sell
                sell_value = position * sell_price_actual
                sell_fee = sell_value * FEE
                cash += sell_value - sell_fee

                # Record trade
                profit = sell_value - position * position_entry_price
                profit_pct = (sell_price_actual / position_entry_price - 1) * 100
                trades.append({
                    'entry_date': None,  # We'll track this properly below
                    'exit_date': date,
                    'entry_price': position_entry_price,
                    'exit_price': sell_price_actual,
                    'profit': profit,
                    'profit_pct': profit_pct
                })

                position = 0.0
                position_entry_price = 0.0

        # === BUY LOGIC ===
        if position == 0:
            # Buy condition: High >= Target AND Prev Close > Prev MA5 AND Prev BTC Close > Prev BTC MA20
            buy_signal = (
                row['high'] >= row['target_price'] and
                row['prev_close'] > row['prev_ma5'] and
                row['prev_btc_close'] > row['prev_btc_ma20']
            )

            if buy_signal:
                # Buy at target price (or open if target is below open)
                buy_price = max(row['target_price'], row['open'])
                # Apply slippage (buy at slightly higher price)
                buy_price_actual = buy_price * (1 + SLIPPAGE)

                # Use all available cash
                buy_value = cash
                buy_fee = buy_value * FEE
                position = (buy_value - buy_fee) / buy_price_actual
                position_entry_price = buy_price_actual
                cash = 0.0

                # Record entry
                if trades and trades[-1]['entry_date'] is None:
                    trades[-1]['entry_date'] = date

        # Record equity
        equity_end = cash + position * row['close']
        equity_curve.append({'date': date, 'equity': equity_end})

    # Close any remaining position at last price
    if position > 0:
        last_row = df.iloc[-1]
        final_price = last_row['close']
        final_value = position * final_price * (1 - SLIPPAGE)
        final_fee = final_value * FEE
        cash += final_value - final_fee
        position = 0.0

    # Convert equity curve to DataFrame
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

    # Sharpe Ratio (annualized)
    equity_df['daily_return'] = equity_df['equity'].pct_change()
    daily_returns = equity_df['daily_return'].dropna()
    if len(daily_returns) > 0 and daily_returns.std() > 0:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365)
    else:
        sharpe = 0.0

    # Win rate
    completed_trades = [t for t in trades if t['entry_date'] is not None]
    total_trades = len(completed_trades)
    winning_trades = len([t for t in completed_trades if t['profit'] > 0])
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

    metrics = {
        'symbol': symbol,
        'total_return': total_return,
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'final_equity': final_equity
    }

    return metrics, equity_df


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description='Backtest VBO strategy for individual cryptocurrencies')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    args = parser.parse_args()

    # Cryptocurrencies to test
    symbols = ['BTC', 'ETH', 'XRP', 'TRX', 'ADA']

    print("=" * 80)
    print("VBO Strategy Backtest - Individual Cryptocurrencies")
    print("=" * 80)
    print(f"\nStrategy Parameters:")
    print(f"  - Buy: High >= Open + (Prev High - Prev Low) * {NOISE_RATIO}")
    print(f"  - Buy Condition: Prev Close > MA{MA_SHORT} AND Prev BTC Close > BTC MA{BTC_MA}")
    print(f"  - Sell: Prev Close < MA{MA_SHORT} OR Prev BTC Close < BTC MA{BTC_MA}")
    print(f"  - Fee: {FEE*100}%, Slippage: {SLIPPAGE*100}%")
    if args.start or args.end:
        print(f"  - Period: {args.start or 'inception'} ~ {args.end or 'latest'}")
    print()

    # Run backtest for each coin
    results = []
    equity_curves = {}
    for symbol in symbols:
        print(f"Backtesting {symbol}...", end=' ', flush=True)
        try:
            metrics, equity_df = backtest_single_coin(symbol, args.start, args.end)
            results.append(metrics)
            equity_curves[symbol] = equity_df
            print("Done")
        except Exception as e:
            print(f"Error: {e}")

    # Display results
    print("\n" + "=" * 80)
    print("RESULTS COMPARISON")
    print("=" * 80)
    print(f"\n{'Symbol':<10} {'CAGR':<12} {'MDD':<12} {'Sharpe':<12} {'Trades':<10} {'Win Rate':<12}")
    print("-" * 80)

    for r in results:
        print(f"{r['symbol']:<10} "
              f"{r['cagr']:>10.2f}%  "
              f"{r['mdd']:>10.2f}%  "
              f"{r['sharpe']:>10.2f}  "
              f"{r['total_trades']:>8}  "
              f"{r['win_rate']:>10.2f}%")

    print("-" * 80)

    # Best performers
    best_cagr = max(results, key=lambda x: x['cagr'])
    best_sharpe = max(results, key=lambda x: x['sharpe'])
    best_mdd = max(results, key=lambda x: x['mdd'])  # Least negative = best

    print(f"\nBest CAGR:   {best_cagr['symbol']} ({best_cagr['cagr']:.2f}%)")
    print(f"Best Sharpe: {best_sharpe['symbol']} ({best_sharpe['sharpe']:.2f})")
    print(f"Best MDD:    {best_mdd['symbol']} ({best_mdd['mdd']:.2f}%)")
    print()

    # Calculate correlation between strategies
    print("\n" + "=" * 80)
    print("STRATEGY CORRELATION (Daily Returns)")
    print("=" * 80)

    # Combine all daily returns
    returns_df = pd.DataFrame()
    for symbol, equity_df in equity_curves.items():
        if 'daily_return' in equity_df.columns:
            returns_df[symbol] = equity_df['daily_return']
        else:
            returns_df[symbol] = equity_df['equity'].pct_change()

    # Calculate correlation matrix
    corr_matrix = returns_df.corr()

    # Display correlation matrix
    print("\nCorrelation Matrix:")
    print("-" * 80)
    print(f"{'':>8}", end='')
    for symbol in symbols:
        print(f"{symbol:>10}", end='')
    print()
    print("-" * 80)

    for i, symbol1 in enumerate(symbols):
        print(f"{symbol1:>8}", end='')
        for symbol2 in symbols:
            if symbol1 in corr_matrix.index and symbol2 in corr_matrix.columns:
                corr = corr_matrix.loc[symbol1, symbol2]
                print(f"{corr:>10.3f}", end='')
            else:
                print(f"{'N/A':>10}", end='')
        print()

    print("-" * 80)

    # Average correlation (excluding diagonal)
    mask = np.ones(corr_matrix.shape, dtype=bool)
    np.fill_diagonal(mask, False)
    avg_corr = corr_matrix.where(mask).stack().mean()

    print(f"\nAverage Correlation (excl. diagonal): {avg_corr:.3f}")
    print()


if __name__ == "__main__":
    main()
