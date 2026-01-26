#!/usr/bin/env python3
"""V10 Optimization - Same or lower complexity variations.

Tests:
1. Exit MA period (3, 5, 7, 10)
2. BTC MA period (10, 15, 20, 25, 30)
3. Noise ratio (0.3, 0.4, 0.5, 0.6, 0.7)
4. No BTC filter (simpler)
"""

from pathlib import Path

import numpy as np
import pandas as pd

FEE = 0.0005
SLIPPAGE = 0.0005
INITIAL_CAPITAL = 1_000_000
SYMBOLS = ['BTC', 'ETH']


def load_data(symbol: str) -> pd.DataFrame:
    data_dir = Path(__file__).parent.parent / "data"
    filepath = data_dir / f"{symbol}.csv"
    df = pd.read_csv(filepath, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    return df.sort_index()


def backtest(ma_exit: int, btc_ma: int | None, noise_ratio: float) -> dict:
    """
    Backtest with configurable parameters.
    btc_ma=None means no BTC filter (simpler strategy).
    """
    btc_df = load_data("BTC")

    data = {}
    for symbol in SYMBOLS:
        df = load_data(symbol)
        df = df.copy()
        df['ma_exit'] = df['close'].rolling(ma_exit).mean()
        df['prev_high'] = df['high'].shift(1)
        df['prev_low'] = df['low'].shift(1)
        df['prev_close'] = df['close'].shift(1)
        df['prev_ma_exit'] = df['ma_exit'].shift(1)
        df['target_price'] = df['open'] + (df['prev_high'] - df['prev_low']) * noise_ratio

        if btc_ma:
            btc_aligned = btc_df.reindex(df.index, method='ffill')
            btc_aligned['btc_ma'] = btc_aligned['close'].rolling(btc_ma).mean()
            df['prev_btc_close'] = btc_aligned['close'].shift(1)
            df['prev_btc_ma'] = btc_aligned['btc_ma'].shift(1)

        data[symbol] = df

    all_dates = set(data[SYMBOLS[0]].index)
    for df in data.values():
        all_dates &= set(df.index)
    all_dates = sorted(all_dates)

    cash = INITIAL_CAPITAL
    positions = dict.fromkeys(SYMBOLS, 0.0)
    equity_curve = []
    n = len(SYMBOLS)

    for date in all_dates:
        prices = {s: data[s].loc[date] for s in SYMBOLS}

        if btc_ma:
            valid = all(
                not pd.isna(prices[s]['prev_ma_exit']) and
                not pd.isna(prices[s]['prev_btc_ma'])
                for s in SYMBOLS
            )
        else:
            valid = all(not pd.isna(prices[s]['prev_ma_exit']) for s in SYMBOLS)

        if not valid:
            equity = cash + sum(positions[s] * prices[s]['close'] for s in SYMBOLS)
            equity_curve.append({'date': date, 'equity': equity})
            continue

        # SELL: MA exit
        for s in SYMBOLS:
            if positions[s] > 0:
                row = prices[s]
                if row['prev_close'] < row['prev_ma_exit']:
                    sell_price = row['open'] * (1 - SLIPPAGE)
                    cash += positions[s] * sell_price * (1 - FEE)
                    positions[s] = 0.0

        # BUY: VBO + optional BTC filter
        buy_candidates = []
        for s in SYMBOLS:
            if positions[s] == 0:
                row = prices[s]
                vbo_trigger = row['high'] >= row['target_price']
                if btc_ma:
                    btc_bull = row['prev_btc_close'] > row['prev_btc_ma']
                    buy = vbo_trigger and btc_bull
                else:
                    buy = vbo_trigger
                if buy:
                    buy_candidates.append(s)

        if buy_candidates and cash > 0:
            total_eq = cash + sum(positions[s] * prices[s]['open'] for s in SYMBOLS)
            alloc = total_eq / n
            for s in buy_candidates:
                row = prices[s]
                val = min(alloc, cash * 0.99)
                if val <= 0:
                    continue
                buy_price = row['target_price'] * (1 + SLIPPAGE)
                positions[s] = (val * (1 - FEE)) / buy_price
                cash -= val

        equity = cash + sum(positions[s] * prices[s]['close'] for s in SYMBOLS)
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
    }


def main():
    print("=" * 90)
    print("V10 OPTIMIZATION (Same or Lower Complexity)")
    print("=" * 90)

    # Baseline V10
    v10 = backtest(ma_exit=5, btc_ma=20, noise_ratio=0.5)
    print(f"\n[BASELINE] V10 (MA5 exit, BTC20, NR=0.5)")
    print(f"  CAGR: {v10['cagr']:.1f}%, MDD: {v10['mdd']:.1f}%, Sharpe: {v10['sharpe']:.2f}, WinRate: {v10['win_rate']:.0f}%, Worst: {v10['worst_year']:.1f}%")

    results = []

    # ==========================================================================
    # 1. Exit MA variations
    # ==========================================================================
    print("\n" + "=" * 90)
    print("1. EXIT MA PERIOD (BTC20, NR=0.5)")
    print("=" * 90)

    print(f"\n{'MA':<6} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10} {'WinRate':>10} {'Worst':>10}")
    print("-" * 60)

    for ma in [3, 5, 7, 10, 15]:
        r = backtest(ma_exit=ma, btc_ma=20, noise_ratio=0.5)
        marker = " *" if ma == 5 else ""
        print(f"{ma:<6} {r['cagr']:>9.1f}% {r['mdd']:>9.1f}% {r['sharpe']:>10.2f} {r['win_rate']:>9.0f}% {r['worst_year']:>9.1f}%{marker}")
        results.append({'param': f'MA_EXIT={ma}', 'btc_ma': 20, 'noise': 0.5, **r})

    # ==========================================================================
    # 2. BTC MA variations
    # ==========================================================================
    print("\n" + "=" * 90)
    print("2. BTC MA PERIOD (MA5 exit, NR=0.5)")
    print("=" * 90)

    print(f"\n{'BTC_MA':<8} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10} {'WinRate':>10} {'Worst':>10}")
    print("-" * 60)

    for btc in [10, 15, 20, 25, 30]:
        r = backtest(ma_exit=5, btc_ma=btc, noise_ratio=0.5)
        marker = " *" if btc == 20 else ""
        print(f"{btc:<8} {r['cagr']:>9.1f}% {r['mdd']:>9.1f}% {r['sharpe']:>10.2f} {r['win_rate']:>9.0f}% {r['worst_year']:>9.1f}%{marker}")
        results.append({'param': f'BTC_MA={btc}', 'ma_exit': 5, 'noise': 0.5, **r})

    # ==========================================================================
    # 3. Noise ratio variations
    # ==========================================================================
    print("\n" + "=" * 90)
    print("3. NOISE RATIO (MA5 exit, BTC20)")
    print("=" * 90)

    print(f"\n{'NR':<8} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10} {'WinRate':>10} {'Worst':>10}")
    print("-" * 60)

    for nr in [0.3, 0.4, 0.5, 0.6, 0.7]:
        r = backtest(ma_exit=5, btc_ma=20, noise_ratio=nr)
        marker = " *" if nr == 0.5 else ""
        print(f"{nr:<8} {r['cagr']:>9.1f}% {r['mdd']:>9.1f}% {r['sharpe']:>10.2f} {r['win_rate']:>9.0f}% {r['worst_year']:>9.1f}%{marker}")
        results.append({'param': f'NR={nr}', 'ma_exit': 5, 'btc_ma': 20, **r})

    # ==========================================================================
    # 4. No BTC filter (simpler)
    # ==========================================================================
    print("\n" + "=" * 90)
    print("4. NO BTC FILTER (Simpler - VBO + MA exit only)")
    print("=" * 90)

    print(f"\n{'Config':<20} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10} {'WinRate':>10} {'Worst':>10}")
    print("-" * 75)

    for ma in [3, 5, 7, 10]:
        r = backtest(ma_exit=ma, btc_ma=None, noise_ratio=0.5)
        print(f"VBO + MA{ma} exit{'':<7} {r['cagr']:>9.1f}% {r['mdd']:>9.1f}% {r['sharpe']:>10.2f} {r['win_rate']:>9.0f}% {r['worst_year']:>9.1f}%")
        results.append({'param': f'NO_BTC_MA{ma}', **r})

    # ==========================================================================
    # 5. Grid search top combinations
    # ==========================================================================
    print("\n" + "=" * 90)
    print("5. GRID SEARCH (MA_EXIT × BTC_MA × NR)")
    print("=" * 90)

    grid_results = []
    for ma in [3, 5, 7]:
        for btc in [15, 20, 25]:
            for nr in [0.4, 0.5, 0.6]:
                r = backtest(ma_exit=ma, btc_ma=btc, noise_ratio=nr)
                grid_results.append({
                    'ma_exit': ma, 'btc_ma': btc, 'noise': nr,
                    **r
                })

    df = pd.DataFrame(grid_results).sort_values('sharpe', ascending=False)

    print(f"\n{'MA':<4} {'BTC':<5} {'NR':<5} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10} {'WinRate':>10} {'Worst':>10}")
    print("-" * 75)

    for i, row in df.head(15).iterrows():
        marker = " *" if row['ma_exit'] == 5 and row['btc_ma'] == 20 and row['noise'] == 0.5 else ""
        print(f"{row['ma_exit']:<4} {row['btc_ma']:<5} {row['noise']:<5} {row['cagr']:>9.1f}% {row['mdd']:>9.1f}% {row['sharpe']:>10.2f} {row['win_rate']:>9.0f}% {row['worst_year']:>9.1f}%{marker}")

    # Summary
    best = df.iloc[0]
    v10_rank = df[(df['ma_exit'] == 5) & (df['btc_ma'] == 20) & (df['noise'] == 0.5)].index[0]
    v10_rank_pos = list(df.index).index(v10_rank) + 1

    print(f"\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)
    print(f"\nV10 Default (5/20/0.5): Rank {v10_rank_pos}/{len(df)}, Sharpe {v10['sharpe']:.2f}")
    print(f"Best ({best['ma_exit']}/{best['btc_ma']}/{best['noise']}): Sharpe {best['sharpe']:.2f}")

    improvement = (best['sharpe'] - v10['sharpe']) / v10['sharpe'] * 100
    print(f"\nPotential Improvement: {improvement:+.1f}% Sharpe")

    if improvement > 5:
        print(f"\n→ Consider: MA_EXIT={int(best['ma_exit'])}, BTC_MA={int(best['btc_ma'])}, NR={best['noise']}")
    else:
        print(f"\n→ V10 defaults are near-optimal. No significant improvement possible.")


if __name__ == "__main__":
    main()
