#!/usr/bin/env python3
"""V5 Overfitting Validation.

Tests:
1. Train/Test split (2017-2021 vs 2022-2026)
2. Year-by-year consistency
3. Parameter sensitivity (MA5/MA20 variations)
4. Walk-forward analysis
"""

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


def backtest_v5(symbols: list[str], ma_short: int = 5, ma_long: int = 20, btc_ma: int = 20,
                start: str | None = None, end: str | None = None) -> dict:
    """Backtest V5 strategy with configurable parameters."""
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
        df['ma_short'] = df['close'].rolling(ma_short).mean()
        df['ma_long'] = df['close'].rolling(ma_long).mean()
        df['prev_high'] = df['high'].shift(1)
        df['prev_low'] = df['low'].shift(1)
        df['prev_close'] = df['close'].shift(1)
        df['prev_ma_short'] = df['ma_short'].shift(1)
        df['prev_ma_long'] = df['ma_long'].shift(1)
        df['target_price'] = df['open'] + (df['prev_high'] - df['prev_low']) * NOISE_RATIO

        btc_aligned = btc_df.reindex(df.index, method='ffill')
        btc_aligned['btc_ma'] = btc_aligned['close'].rolling(btc_ma).mean()
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
            not pd.isna(prices[s]['prev_ma_long']) and
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

        # BUY: VBO + MA5 + MA20 + BTC
        buy_candidates = []
        for s in symbols:
            if positions[s] == 0:
                row = prices[s]
                buy = (row['high'] >= row['target_price'] and
                       row['prev_close'] > row['prev_ma_short'] and
                       row['prev_close'] > row['prev_ma_long'] and
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

    return {
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
        'yearly': yearly_returns,
    }


def main():
    symbols = ['BTC', 'ETH']

    print("=" * 80)
    print("V5 OVERFITTING VALIDATION")
    print("=" * 80)

    # ==========================================================================
    # 1. Train/Test Split
    # ==========================================================================
    print("\n" + "=" * 80)
    print("1. TRAIN/TEST SPLIT")
    print("=" * 80)

    train = backtest_v5(symbols, start="2017-01-01", end="2021-12-31")
    test = backtest_v5(symbols, start="2022-01-01", end="2026-12-31")

    print(f"\n{'Period':<15} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10}")
    print("-" * 50)
    print(f"{'Train (17-21)':<15} {train['cagr']:>9.1f}% {train['mdd']:>9.1f}% {train['sharpe']:>10.2f}")
    print(f"{'Test (22-26)':<15} {test['cagr']:>9.1f}% {test['mdd']:>9.1f}% {test['sharpe']:>10.2f}")

    sharpe_degradation = (train['sharpe'] - test['sharpe']) / train['sharpe'] * 100
    print(f"\nSharpe Degradation: {sharpe_degradation:.1f}%")
    print(f"✅ PASS" if sharpe_degradation < 50 else "❌ FAIL", f"(threshold: <50%)")

    # ==========================================================================
    # 2. Year-by-Year Consistency
    # ==========================================================================
    print("\n" + "=" * 80)
    print("2. YEAR-BY-YEAR CONSISTENCY")
    print("=" * 80)

    full = backtest_v5(symbols)
    yearly = full['yearly']

    print(f"\n{'Year':<10} {'Return':>10}")
    print("-" * 25)
    positive_years = 0
    for year, ret in sorted(yearly.items()):
        status = "✅" if ret > 0 else "❌"
        print(f"{year:<10} {ret:>9.1f}% {status}")
        if ret > 0:
            positive_years += 1

    win_rate = positive_years / len(yearly) * 100
    print(f"\nWin Rate: {positive_years}/{len(yearly)} ({win_rate:.0f}%)")
    print(f"✅ PASS" if win_rate >= 80 else "❌ FAIL", f"(threshold: >=80%)")

    # ==========================================================================
    # 3. Parameter Sensitivity
    # ==========================================================================
    print("\n" + "=" * 80)
    print("3. PARAMETER SENSITIVITY (MA_SHORT × MA_LONG)")
    print("=" * 80)

    param_results = []
    for ma_short in [3, 4, 5, 6, 7]:
        for ma_long in [15, 18, 20, 22, 25]:
            r = backtest_v5(symbols, ma_short=ma_short, ma_long=ma_long)
            param_results.append({
                'ma_short': ma_short,
                'ma_long': ma_long,
                'cagr': r['cagr'],
                'sharpe': r['sharpe'],
            })

    df = pd.DataFrame(param_results)

    print(f"\n{'MA_SHORT':<10} {'MA_LONG':<10} {'CAGR':>10} {'Sharpe':>10}")
    print("-" * 45)
    for _, row in df.iterrows():
        marker = " *" if row['ma_short'] == 5 and row['ma_long'] == 20 else ""
        print(f"{row['ma_short']:<10} {row['ma_long']:<10} {row['cagr']:>9.1f}% {row['sharpe']:>10.2f}{marker}")

    # Default params performance
    default = df[(df['ma_short'] == 5) & (df['ma_long'] == 20)].iloc[0]
    best = df.loc[df['sharpe'].idxmax()]
    worst = df.loc[df['sharpe'].idxmin()]

    print(f"\nDefault (5/20): Sharpe {default['sharpe']:.2f}")
    print(f"Best ({best['ma_short']}/{best['ma_long']}): Sharpe {best['sharpe']:.2f}")
    print(f"Worst ({worst['ma_short']}/{worst['ma_long']}): Sharpe {worst['sharpe']:.2f}")

    sharpe_range = best['sharpe'] - worst['sharpe']
    sharpe_cv = df['sharpe'].std() / df['sharpe'].mean() * 100
    print(f"\nSharpe Range: {sharpe_range:.2f}")
    print(f"Sharpe CV: {sharpe_cv:.1f}%")
    print(f"✅ PASS" if sharpe_cv < 20 else "❌ FAIL", f"(threshold: CV <20%)")

    # Default rank
    df_sorted = df.sort_values('sharpe', ascending=False).reset_index(drop=True)
    default_rank = df_sorted[(df_sorted['ma_short'] == 5) & (df_sorted['ma_long'] == 20)].index[0] + 1
    print(f"\nDefault Rank: {default_rank}/{len(df)}")
    print(f"✅ PASS" if default_rank <= 10 else "❌ FAIL", f"(threshold: top 10)")

    # ==========================================================================
    # 4. Walk-Forward Analysis (2-year train, 1-year test)
    # ==========================================================================
    print("\n" + "=" * 80)
    print("4. WALK-FORWARD ANALYSIS (2yr train → 1yr test)")
    print("=" * 80)

    wf_results = []
    periods = [
        ("2018-2019", "2020", "2018-01-01", "2019-12-31", "2020-01-01", "2020-12-31"),
        ("2019-2020", "2021", "2019-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
        ("2020-2021", "2022", "2020-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
        ("2021-2022", "2023", "2021-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
        ("2022-2023", "2024", "2022-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
        ("2023-2024", "2025", "2023-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
    ]

    print(f"\n{'Train':<12} {'Test':<8} {'Train CAGR':>12} {'Test CAGR':>12} {'Status':<8}")
    print("-" * 60)

    for train_name, test_name, train_start, train_end, test_start, test_end in periods:
        try:
            train_r = backtest_v5(symbols, start=train_start, end=train_end)
            test_r = backtest_v5(symbols, start=test_start, end=test_end)
            status = "✅" if test_r['cagr'] > 0 else "❌"
            print(f"{train_name:<12} {test_name:<8} {train_r['cagr']:>11.1f}% {test_r['cagr']:>11.1f}% {status:<8}")
            wf_results.append({'test_year': test_name, 'test_cagr': test_r['cagr']})
        except Exception as e:
            print(f"{train_name:<12} {test_name:<8} Error: {e}")

    wf_positive = sum(1 for r in wf_results if r['test_cagr'] > 0)
    print(f"\nWalk-Forward Win Rate: {wf_positive}/{len(wf_results)}")
    print(f"✅ PASS" if wf_positive >= len(wf_results) * 0.8 else "❌ FAIL", f"(threshold: >=80%)")

    # ==========================================================================
    # Summary
    # ==========================================================================
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    tests = [
        ("Train/Test Split", sharpe_degradation < 50),
        ("Year-by-Year Consistency", win_rate >= 80),
        ("Parameter Sensitivity", sharpe_cv < 20),
        ("Default Param Rank", default_rank <= 10),
        ("Walk-Forward", wf_positive >= len(wf_results) * 0.8),
    ]

    print(f"\n{'Test':<30} {'Result':<10}")
    print("-" * 45)
    passed = 0
    for name, result in tests:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name:<30} {status:<10}")
        if result:
            passed += 1

    print(f"\nOverall: {passed}/{len(tests)} tests passed")
    if passed == len(tests):
        print("\n🎉 V5 STRATEGY VALIDATED - LOW OVERFITTING RISK")
    elif passed >= len(tests) - 1:
        print("\n⚠️ V5 STRATEGY MOSTLY VALIDATED - MINOR CONCERNS")
    else:
        print("\n❌ V5 STRATEGY MAY BE OVERFIT - REVIEW NEEDED")


if __name__ == "__main__":
    main()
