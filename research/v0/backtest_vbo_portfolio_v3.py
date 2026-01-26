#!/usr/bin/env python3
"""Backtest VBO portfolio - V3: No BTC filter at all.

Entry: VBO breakout + coin MA5 only
Exit: coin MA5 only
"""

import argparse
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

FEE = 0.0005
SLIPPAGE = 0.0005
MA_SHORT = 5
NOISE_RATIO = 0.5
INITIAL_CAPITAL = 1_000_000


def load_data(symbol: str, data_dir: str = "data") -> pd.DataFrame:
    filepath = Path(data_dir) / f"{symbol}.csv"
    if not filepath.exists():
        raise FileNotFoundError(f"No data for {symbol}: {filepath}")
    df = pd.read_csv(filepath, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    df = df.sort_index()
    return df


def filter_date_range(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if start:
        df = df[df.index >= pd.to_datetime(start)]
    if end:
        df = df[df.index <= pd.to_datetime(end)]
    return df


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['ma5'] = df['close'].rolling(window=MA_SHORT).mean()
    df['prev_high'] = df['high'].shift(1)
    df['prev_low'] = df['low'].shift(1)
    df['prev_close'] = df['close'].shift(1)
    df['prev_ma5'] = df['ma5'].shift(1)
    df['target_price'] = df['open'] + (df['prev_high'] - df['prev_low']) * NOISE_RATIO
    return df


def backtest_portfolio(symbols: list[str], start: str | None = None, end: str | None = None) -> dict:
    data = {}
    for symbol in symbols:
        df = load_data(symbol)
        df = filter_date_range(df, start, end)
        df = calculate_indicators(df)
        data[symbol] = df

    all_dates = set(data[list(symbols)[0]].index)
    for df in data.values():
        all_dates &= set(df.index)
    all_dates = sorted(all_dates)

    if not all_dates:
        raise ValueError("No common dates across all symbols")

    cash = INITIAL_CAPITAL
    positions = dict.fromkeys(symbols, 0.0)
    equity_curve = []
    n_strategies = len(symbols)

    for date in all_dates:
        prices = {symbol: data[symbol].loc[date] for symbol in symbols}

        valid = all(not pd.isna(prices[symbol]['prev_ma5']) for symbol in symbols)

        if not valid:
            equity = cash + sum(positions[symbol] * prices[symbol]['close'] for symbol in symbols)
            equity_curve.append({'date': date, 'equity': equity})
            continue

        # === SELL: coin MA5 only ===
        for symbol in symbols:
            if positions[symbol] > 0:
                row = prices[symbol]
                sell_signal = row['prev_close'] < row['prev_ma5']
                if sell_signal:
                    sell_price = row['open'] * (1 - SLIPPAGE)
                    sell_value = positions[symbol] * sell_price
                    sell_fee = sell_value * FEE
                    cash += sell_value - sell_fee
                    positions[symbol] = 0.0

        # === BUY: VBO + coin MA5 only (no BTC filter) ===
        buy_candidates = []
        for symbol in symbols:
            if positions[symbol] == 0:
                row = prices[symbol]
                buy_signal = (
                    row['high'] >= row['target_price'] and
                    row['prev_close'] > row['prev_ma5']
                )
                if buy_signal:
                    buy_candidates.append(symbol)

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
        'symbols': symbols,
        'symbols_str': '+'.join(symbols),
        'n_coins': len(symbols),
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str)
    parser.add_argument('--end', type=str)
    args = parser.parse_args()

    all_symbols = ['BTC', 'ETH', 'XRP', 'TRX', 'ADA']

    print("=" * 80)
    print("V3: No BTC filter (Entry: VBO+MA5, Exit: MA5 only)")
    print("=" * 80)

    for n in range(2, 6):
        print(f"\n{n}-COIN COMBINATIONS:")
        print("-" * 80)
        print(f"{'Combo':<25} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10}")
        print("-" * 80)

        for combo in combinations(all_symbols, n):
            symbols = list(combo)
            try:
                r = backtest_portfolio(symbols, args.start, args.end)
                print(f"{r['symbols_str']:<25} {r['cagr']:>9.2f}% {r['mdd']:>9.2f}% {r['sharpe']:>10.2f}")
            except Exception as e:
                print(f"{'+'.join(symbols):<25} Error: {e}")


if __name__ == "__main__":
    main()
