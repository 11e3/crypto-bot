#!/usr/bin/env python3
"""Compare yearly returns across V1-V5 strategies."""

from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

FEE = 0.0005
SLIPPAGE = 0.0005
NOISE_RATIO = 0.5
INITIAL_CAPITAL = 1_000_000


def load_data(symbol: str, data_dir: str = "data") -> pd.DataFrame:
    filepath = Path(data_dir) / f"{symbol}.csv"
    df = pd.read_csv(filepath, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    return df.sort_index()


def calculate_indicators(df: pd.DataFrame, btc_df: pd.DataFrame | None = None) -> pd.DataFrame:
    df = df.copy()
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['prev_high'] = df['high'].shift(1)
    df['prev_low'] = df['low'].shift(1)
    df['prev_close'] = df['close'].shift(1)
    df['prev_ma5'] = df['ma5'].shift(1)
    df['prev_ma20'] = df['ma20'].shift(1)
    df['target_price'] = df['open'] + (df['prev_high'] - df['prev_low']) * NOISE_RATIO

    if btc_df is not None:
        btc_aligned = btc_df.reindex(df.index, method='ffill')
        btc_aligned['btc_ma20'] = btc_aligned['close'].rolling(20).mean()
        df['prev_btc_close'] = btc_aligned['close'].shift(1)
        df['prev_btc_ma20'] = btc_aligned['btc_ma20'].shift(1)

    return df


def backtest_yearly(symbols: list[str], version: str) -> pd.DataFrame:
    """Returns DataFrame with yearly returns."""
    need_btc = version in ('V1', 'V2', 'V5')
    btc_df = load_data("BTC") if need_btc else None

    data = {}
    for symbol in symbols:
        df = load_data(symbol)
        df = calculate_indicators(df, btc_df if need_btc else None)
        data[symbol] = df

    all_dates = set(data[list(symbols)[0]].index)
    for df in data.values():
        all_dates &= set(df.index)
    all_dates = sorted(all_dates)

    cash = INITIAL_CAPITAL
    positions = dict.fromkeys(symbols, 0.0)
    equity_curve = []
    n = len(symbols)

    for date in all_dates:
        prices = {s: data[s].loc[date] for s in symbols}

        if version in ('V1', 'V2'):
            valid = all(not pd.isna(prices[s]['prev_ma5']) and not pd.isna(prices[s]['prev_btc_ma20']) for s in symbols)
        elif version == 'V3':
            valid = all(not pd.isna(prices[s]['prev_ma5']) for s in symbols)
        elif version == 'V5':
            valid = all(not pd.isna(prices[s]['prev_ma5']) and not pd.isna(prices[s]['prev_ma20']) and not pd.isna(prices[s]['prev_btc_ma20']) for s in symbols)
        else:  # V4
            valid = all(not pd.isna(prices[s]['prev_ma5']) and not pd.isna(prices[s]['prev_ma20']) for s in symbols)

        if not valid:
            equity = cash + sum(positions[s] * prices[s]['close'] for s in symbols)
            equity_curve.append({'date': date, 'equity': equity})
            continue

        # SELL
        for s in symbols:
            if positions[s] > 0:
                row = prices[s]
                if version == 'V1':
                    sell = (row['prev_close'] < row['prev_ma5']) or (row['prev_btc_close'] < row['prev_btc_ma20'])
                else:
                    sell = row['prev_close'] < row['prev_ma5']

                if sell:
                    sell_price = row['open'] * (1 - SLIPPAGE)
                    cash += positions[s] * sell_price * (1 - FEE)
                    positions[s] = 0.0

        # BUY
        buy_candidates = []
        for s in symbols:
            if positions[s] == 0:
                row = prices[s]
                if version in ('V1', 'V2'):
                    buy = (row['high'] >= row['target_price'] and
                           row['prev_close'] > row['prev_ma5'] and
                           row['prev_btc_close'] > row['prev_btc_ma20'])
                elif version == 'V3':
                    buy = (row['high'] >= row['target_price'] and
                           row['prev_close'] > row['prev_ma5'])
                elif version == 'V5':
                    buy = (row['high'] >= row['target_price'] and
                           row['prev_close'] > row['prev_ma5'] and
                           row['prev_close'] > row['prev_ma20'] and
                           row['prev_btc_close'] > row['prev_btc_ma20'])
                else:  # V4
                    buy = (row['high'] >= row['target_price'] and
                           row['prev_close'] > row['prev_ma5'] and
                           row['prev_close'] > row['prev_ma20'])

                if buy:
                    buy_candidates.append(s)

        if buy_candidates and cash > 0:
            total_eq = cash + sum(positions[s] * prices[s]['open'] for s in symbols)
            alloc = total_eq / n
            for s in buy_candidates:
                row = prices[s]
                val = min(alloc, cash * 0.99)
                if val <= 0:
                    continue
                buy_price = row['target_price'] * (1 + SLIPPAGE)
                positions[s] = (val * (1 - FEE)) / buy_price
                cash -= val

        equity = cash + sum(positions[s] * prices[s]['close'] for s in symbols)
        equity_curve.append({'date': date, 'equity': equity})

    eq_df = pd.DataFrame(equity_curve).set_index('date')

    # Calculate yearly returns
    eq_df['year'] = eq_df.index.year
    yearly = eq_df.groupby('year')['equity'].agg(['first', 'last'])
    yearly['return'] = (yearly['last'] / yearly['first'] - 1) * 100

    return yearly['return']


def main():
    versions = ['V1', 'V2', 'V3', 'V4', 'V5']

    # Best combo for each version based on Sharpe
    best_combos = {
        'V1': ['BTC', 'ETH', 'XRP'],
        'V2': ['BTC', 'ETH', 'XRP'],
        'V3': ['BTC', 'ETH', 'XRP', 'TRX', 'ADA'],
        'V4': ['BTC', 'ETH', 'XRP', 'TRX', 'ADA'],
        'V5': ['BTC', 'ETH', 'XRP'],
    }

    results = {}
    for v in versions:
        combo = best_combos[v]
        yearly = backtest_yearly(combo, v)
        results[f"{v} ({'+'.join(combo)})"] = yearly

    df = pd.DataFrame(results)

    # Filter to recent 5 years
    df = df[df.index >= 2021]

    print("=" * 100)
    print("연도별 수익률 비교 (각 버전 최적 조합)")
    print("=" * 100)
    print()
    print(df.round(2).to_string())
    print()

    # Summary stats
    print("-" * 100)
    print("요약 통계")
    print("-" * 100)
    summary = pd.DataFrame({
        'Win Rate': (df > 0).sum() / len(df) * 100,
        'Avg': df.mean(),
        'Std': df.std(),
        'CV': df.std() / df.mean(),
        'Worst': df.min(),
        'Best': df.max(),
        'Median': df.median(),
    }).round(2)
    print(summary.to_string())


if __name__ == "__main__":
    main()
