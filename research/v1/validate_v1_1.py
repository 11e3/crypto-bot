#!/usr/bin/env python3
"""V1.1 Overfitting & Robustness Validation.

Tests:
1. Train/Test split (2017-2021 vs 2022-2025)
2. Year-by-year consistency
3. Parameter sensitivity (EMA span variations)
4. Walk-forward analysis
"""

from pathlib import Path
import numpy as np
import pandas as pd

FEE = 0.0005
SLIPPAGE = 0.0005
NOISE_RATIO = 0.5
BTC_MA = 20
INITIAL_CAPITAL = 1_000_000


def load_data(symbol: str, data_dir: str | None = None) -> pd.DataFrame:
    if data_dir is None:
        data_dir = Path(__file__).parent.parent.parent / "data"
    filepath = Path(data_dir) / f"{symbol}.csv"
    df = pd.read_csv(filepath, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    return df.sort_index()


def backtest_v1_1(symbols: list[str], ema_span: int = 5, btc_ma: int = 20,
                  start: str | None = None, end: str | None = None) -> dict:
    """V1.1: VBO+BTC entry, EMA exit."""
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
        df['ema'] = df['close'].ewm(span=ema_span, adjust=False).mean()
        df['prev_high'] = df['high'].shift(1)
        df['prev_low'] = df['low'].shift(1)
        df['prev_close'] = df['close'].shift(1)
        df['prev_ema'] = df['ema'].shift(1)
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
            not pd.isna(prices[s]['prev_ema']) and
            not pd.isna(prices[s]['prev_btc_ma'])
            for s in symbols
        )

        if not valid:
            equity = cash + sum(positions[s] * prices[s]['close'] for s in symbols)
            equity_curve.append({'date': date, 'equity': equity})
            continue

        # SELL: EMA only
        for s in symbols:
            if positions[s] > 0:
                row = prices[s]
                if row['prev_close'] < row['prev_ema']:
                    sell_price = row['open'] * (1 - SLIPPAGE)
                    cash += positions[s] * sell_price * (1 - FEE)
                    positions[s] = 0.0

        # BUY: VBO + BTC
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

    if not equity_curve:
        return {'cagr': 0, 'mdd': 0, 'sharpe': 0, 'yearly': {}}

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
    print("V1.1 OVERFITTING & ROBUSTNESS VALIDATION")
    print("Strategy: VBO+BTC entry, EMA5 exit | Portfolio: BTC+ETH")
    print("=" * 80)

    # 1. Train/Test Split
    print("\n" + "=" * 80)
    print("1. TRAIN/TEST SPLIT")
    print("=" * 80)

    train = backtest_v1_1(symbols, start="2017-01-01", end="2021-12-31")
    test = backtest_v1_1(symbols, start="2022-01-01", end="2025-12-31")
    full = backtest_v1_1(symbols)

    print(f"\n{'Period':<15} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10}")
    print("-" * 50)
    print(f"{'Train 17-21':<15} {train['cagr']:>9.1f}% {train['mdd']:>9.1f}% {train['sharpe']:>10.2f}")
    print(f"{'Test 22-25':<15} {test['cagr']:>9.1f}% {test['mdd']:>9.1f}% {test['sharpe']:>10.2f}")
    print(f"{'Full':<15} {full['cagr']:>9.1f}% {full['mdd']:>9.1f}% {full['sharpe']:>10.2f}")

    # Degradation check
    sharpe_degrad = (train['sharpe'] - test['sharpe']) / train['sharpe'] * 100 if train['sharpe'] > 0 else 0
    print(f"\nSharpe degradation: {sharpe_degrad:.1f}%", end="")
    if sharpe_degrad < 30:
        print(" ✓ PASS (< 30%)")
    else:
        print(" ✗ FAIL (>= 30%)")

    # 2. Year-by-Year Consistency
    print("\n" + "=" * 80)
    print("2. YEAR-BY-YEAR CONSISTENCY")
    print("=" * 80)

    yearly = full['yearly']
    print(f"\n{'Year':<8} {'Return':>10}")
    print("-" * 20)
    for year in sorted(yearly.keys()):
        ret = yearly[year]
        status = "✓" if ret > 0 else "✗"
        print(f"{year:<8} {ret:>9.1f}% {status}")

    positive_years = sum(1 for r in yearly.values() if r > 0)
    total_years = len(yearly)
    win_rate = positive_years / total_years * 100 if total_years > 0 else 0
    worst = min(yearly.values()) if yearly else 0

    print(f"\nWin rate: {positive_years}/{total_years} ({win_rate:.0f}%)")
    print(f"Worst year: {worst:.1f}%")

    # 3. Parameter Sensitivity (EMA span)
    print("\n" + "=" * 80)
    print("3. PARAMETER SENSITIVITY (EMA Span)")
    print("=" * 80)

    ema_spans = [3, 4, 5, 6, 7, 8, 10]
    param_results = []

    print(f"\n{'EMA':<8} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10}")
    print("-" * 42)

    for span in ema_spans:
        r = backtest_v1_1(symbols, ema_span=span)
        param_results.append({'ema': span, 'sharpe': r['sharpe'], 'cagr': r['cagr']})
        marker = " ← default" if span == 5 else ""
        print(f"{span:<8} {r['cagr']:>9.1f}% {r['mdd']:>9.1f}% {r['sharpe']:>10.2f}{marker}")

    sharpes = [r['sharpe'] for r in param_results]
    default_sharpe = next(r['sharpe'] for r in param_results if r['ema'] == 5)
    avg_sharpe = np.mean(sharpes)
    std_sharpe = np.std(sharpes)

    print(f"\nSharpe: avg={avg_sharpe:.2f}, std={std_sharpe:.2f}")
    print(f"Default (EMA5) rank: {sorted(sharpes, reverse=True).index(default_sharpe) + 1}/{len(sharpes)}")

    # 4. BTC MA Sensitivity
    print("\n" + "=" * 80)
    print("4. BTC MA SENSITIVITY")
    print("=" * 80)

    btc_mas = [10, 15, 20, 25, 30]

    print(f"\n{'BTC_MA':<8} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10}")
    print("-" * 42)

    for ma in btc_mas:
        r = backtest_v1_1(symbols, btc_ma=ma)
        marker = " ← default" if ma == 20 else ""
        print(f"{ma:<8} {r['cagr']:>9.1f}% {r['mdd']:>9.1f}% {r['sharpe']:>10.2f}{marker}")

    # 5. Walk-Forward Analysis
    print("\n" + "=" * 80)
    print("5. WALK-FORWARD ANALYSIS (2-year train, 1-year test)")
    print("=" * 80)

    wf_results = []
    windows = [
        ("2017-2018", "2019", "2017-01-01", "2018-12-31", "2019-01-01", "2019-12-31"),
        ("2018-2019", "2020", "2018-01-01", "2019-12-31", "2020-01-01", "2020-12-31"),
        ("2019-2020", "2021", "2019-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
        ("2020-2021", "2022", "2020-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
        ("2021-2022", "2023", "2021-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
        ("2022-2023", "2024", "2022-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
        ("2023-2024", "2025", "2023-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
    ]

    print(f"\n{'Train':<12} {'Test':<8} {'Train Sharpe':>14} {'Test Sharpe':>14} {'Status':<8}")
    print("-" * 65)

    for train_label, test_label, ts, te, vs, ve in windows:
        train_r = backtest_v1_1(symbols, start=ts, end=te)
        test_r = backtest_v1_1(symbols, start=vs, end=ve)

        status = "✓" if test_r['sharpe'] > 0 else "✗"
        wf_results.append({'test_sharpe': test_r['sharpe']})

        print(f"{train_label:<12} {test_label:<8} {train_r['sharpe']:>14.2f} {test_r['sharpe']:>14.2f} {status:<8}")

    wf_positive = sum(1 for r in wf_results if r['test_sharpe'] > 0)
    print(f"\nPositive test Sharpe: {wf_positive}/{len(wf_results)}")

    # Summary
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)

    checks = []

    # Check 1: Sharpe degradation
    checks.append(("Train/Test degradation < 30%", sharpe_degrad < 30))

    # Check 2: Win rate >= 80%
    checks.append(("Year win rate >= 80%", win_rate >= 80))

    # Check 3: Default param in top 3
    default_rank = sorted(sharpes, reverse=True).index(default_sharpe) + 1
    checks.append(("Default EMA5 in top 3", default_rank <= 3))

    # Check 4: Walk-forward positive > 70%
    wf_rate = wf_positive / len(wf_results) * 100
    checks.append(("Walk-forward positive > 70%", wf_rate > 70))

    print()
    passed = 0
    for check, result in checks:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {check}: {status}")
        if result:
            passed += 1

    print(f"\nResult: {passed}/{len(checks)} checks passed")

    if passed == len(checks):
        print("\n✓ V1.1 STRATEGY VALIDATED - LOW OVERFITTING RISK")
    elif passed >= len(checks) - 1:
        print("\n⚠ V1.1 MOSTLY VALIDATED - MINOR CONCERNS")
    else:
        print("\n✗ V1.1 MAY BE OVERFIT - REVIEW NEEDED")


if __name__ == "__main__":
    main()
