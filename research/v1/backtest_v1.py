#!/usr/bin/env python3
"""V1 Strategy Portfolio Size Comparison.

Compares V1 (VBO+BTC entry, MA5 exit) across 1-5 asset combinations.
"""

from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

FEE = 0.0005
SLIPPAGE = 0.0005
NOISE_RATIO = 0.5
MA_SHORT = 5
BTC_MA = 20
INITIAL_CAPITAL = 1_000_000

ALL_SYMBOLS = ['BTC', 'ETH', 'XRP', 'TRX', 'ADA']


def load_data(symbol: str, data_dir: str | None = None) -> pd.DataFrame:
    if data_dir is None:
        data_dir = Path(__file__).parent.parent / "data"
    filepath = Path(data_dir) / f"{symbol}.csv"
    df = pd.read_csv(filepath, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    return df.sort_index()


def backtest_v1(symbols: list[str], start: str | None = None, end: str | None = None) -> dict:
    """V1: VBO+BTC entry, MA5 exit."""
    btc_df = load_data("BTC")
    if start:
        btc_df = btc_df[btc_df.index >= pd.to_datetime(start)]
    if end:
        btc_df = btc_df[btc_df.index <= pd.to_datetime(end)]

    data = {}
    for symbol in symbols:
        df = load_data(symbol)
        if start:
            df = df[df.index >= pd.to_datetime(start)]
        if end:
            df = df[df.index <= pd.to_datetime(end)]

        df = df.copy()
        df['ma_short'] = df['close'].rolling(MA_SHORT).mean()
        df['prev_high'] = df['high'].shift(1)
        df['prev_low'] = df['low'].shift(1)
        df['prev_close'] = df['close'].shift(1)
        df['prev_ma_short'] = df['ma_short'].shift(1)
        df['target_price'] = df['open'] + (df['prev_high'] - df['prev_low']) * NOISE_RATIO

        btc_aligned = btc_df.reindex(df.index, method='ffill')
        btc_aligned['btc_ma'] = btc_aligned['close'].rolling(BTC_MA).mean()
        df['prev_btc_close'] = btc_aligned['close'].shift(1)
        df['prev_btc_ma'] = btc_aligned['btc_ma'].shift(1)

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

        valid = all(
            not pd.isna(prices[s]['prev_ma_short']) and
            not pd.isna(prices[s]['prev_btc_ma'])
            for s in symbols
        )

        if not valid:
            equity = cash + sum(positions[s] * prices[s]['close'] for s in symbols)
            equity_curve.append({'date': date, 'equity': equity})
            continue

        # SELL: MA5 only
        for s in symbols:
            if positions[s] > 0:
                row = prices[s]
                if row['prev_close'] < row['prev_ma_short']:
                    sell_price = row['open'] * (1 - SLIPPAGE)
                    cash += positions[s] * sell_price * (1 - FEE)
                    positions[s] = 0.0

        # BUY: VBO + BTC only (no MA5)
        buy_candidates = []
        for s in symbols:
            if positions[s] == 0:
                row = prices[s]
                buy = (row['high'] >= row['target_price'] and
                       row['prev_btc_close'] > row['prev_btc_ma'])
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
    final = eq_df['equity'].iloc[-1]
    initial = eq_df['equity'].iloc[0]
    days = (eq_df.index[-1] - eq_df.index[0]).days
    years = days / 365.25
    cagr = (pow(final / initial, 1 / years) - 1) * 100 if years > 0 else 0

    running_max = eq_df['equity'].expanding().max()
    mdd = ((eq_df['equity'] / running_max - 1) * 100).min()

    ret = eq_df['equity'].pct_change().dropna()
    sharpe = (ret.mean() / ret.std()) * np.sqrt(365) if ret.std() > 0 else 0

    # Yearly returns
    eq_df['year'] = eq_df.index.year
    yearly = eq_df.groupby('year')['equity'].agg(['first', 'last'])
    yearly['return'] = (yearly['last'] / yearly['first'] - 1) * 100
    yearly_returns = yearly['return'].to_dict()

    positive_years = sum(1 for r in yearly_returns.values() if r > 0)
    win_rate = positive_years / len(yearly_returns) * 100 if yearly_returns else 0
    worst_year = min(yearly_returns.values()) if yearly_returns else 0

    return {
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
        'win_rate': win_rate,
        'worst_year': worst_year,
        'yearly': yearly_returns,
    }


def main():
    print("=" * 90)
    print("V1 PORTFOLIO SIZE COMPARISON")
    print("V1: VBO+BTC entry, MA5 exit")
    print("=" * 90)

    all_results = []

    for size in range(1, 6):
        print(f"\n{'=' * 90}")
        print(f"{size}-ASSET PORTFOLIOS")
        print("=" * 90)

        combos = list(combinations(ALL_SYMBOLS, size))
        results = []

        for combo in combos:
            r = backtest_v1(list(combo))
            results.append({
                'symbols': '+'.join(combo),
                'size': size,
                'cagr': r['cagr'],
                'mdd': r['mdd'],
                'sharpe': r['sharpe'],
                'win_rate': r['win_rate'],
                'worst_year': r['worst_year'],
            })

        df = pd.DataFrame(results).sort_values('sharpe', ascending=False)

        print(f"\n{'Symbols':<20} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10} {'WinRate':>10} {'Worst':>10}")
        print("-" * 75)
        for _, row in df.iterrows():
            print(f"{row['symbols']:<20} {row['cagr']:>9.1f}% {row['mdd']:>9.1f}% {row['sharpe']:>10.2f} {row['win_rate']:>9.0f}% {row['worst_year']:>9.1f}%")

        all_results.extend(results)

        # Best of this size
        best = df.iloc[0]
        print(f"\n→ Best {size}-asset: {best['symbols']} (Sharpe {best['sharpe']:.2f})")

    # Overall summary
    print("\n" + "=" * 90)
    print("SUMMARY BY SIZE (Best of each)")
    print("=" * 90)

    df_all = pd.DataFrame(all_results)

    print(f"\n{'Size':<6} {'Best Combo':<20} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10} {'WinRate':>10} {'Worst':>10}")
    print("-" * 85)

    for size in range(1, 6):
        size_df = df_all[df_all['size'] == size].sort_values('sharpe', ascending=False)
        best = size_df.iloc[0]
        print(f"{size:<6} {best['symbols']:<20} {best['cagr']:>9.1f}% {best['mdd']:>9.1f}% {best['sharpe']:>10.2f} {best['win_rate']:>9.0f}% {best['worst_year']:>9.1f}%")

    # Top 10 overall
    print("\n" + "=" * 90)
    print("TOP 10 OVERALL (by Sharpe)")
    print("=" * 90)

    top10 = df_all.sort_values('sharpe', ascending=False).head(10)
    print(f"\n{'Rank':<6} {'Symbols':<20} {'Size':<6} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10} {'WinRate':>10}")
    print("-" * 80)
    for i, (_, row) in enumerate(top10.iterrows(), 1):
        print(f"{i:<6} {row['symbols']:<20} {row['size']:<6} {row['cagr']:>9.1f}% {row['mdd']:>9.1f}% {row['sharpe']:>10.2f} {row['win_rate']:>9.0f}%")


if __name__ == "__main__":
    main()
