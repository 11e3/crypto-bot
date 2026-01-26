#!/usr/bin/env python3
"""Test USD/JPY as Market Regime Filter.

Theory: USD/JPY rising = risk-on environment (yen carry trade)
       USD/JPY falling = risk-off (yen safe haven)
"""

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

FEE = 0.0005
SLIPPAGE = 0.0005
INITIAL_CAPITAL = 1_000_000
SYMBOLS = ['BTC', 'ETH']
NOISE_RATIO = 0.5


def load_data(symbol: str) -> pd.DataFrame:
    data_dir = Path(__file__).parent.parent / "data"
    filepath = data_dir / f"{symbol}.csv"
    df = pd.read_csv(filepath, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    return df.sort_index()


def fetch_usdjpy() -> pd.DataFrame:
    """Fetch USD/JPY data from Yahoo Finance."""
    print("Fetching USD/JPY data...")
    ticker = yf.Ticker("USDJPY=X")
    df = ticker.history(start="2017-01-01", end="2026-01-01")
    df.index = df.index.tz_localize(None)
    df.columns = [c.lower() for c in df.columns]
    print(f"  Got {len(df)} days of USD/JPY data")
    return df


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def backtest(regime_filter: str, usdjpy_df: pd.DataFrame = None, btc_df: pd.DataFrame = None) -> dict:
    """
    Backtest with different regime filters.

    regime_filter: 'btc_sma20', 'usdjpy_sma20', 'usdjpy_ema20',
                   'usdjpy_sma10', 'usdjpy_rising', 'both'
    """
    if btc_df is None:
        btc_df = load_data("BTC")

    btc_df = btc_df.copy()
    btc_df['sma20'] = btc_df['close'].rolling(20).mean()

    if usdjpy_df is not None:
        usdjpy_df = usdjpy_df.copy()
        usdjpy_df['sma20'] = usdjpy_df['close'].rolling(20).mean()
        usdjpy_df['sma10'] = usdjpy_df['close'].rolling(10).mean()
        usdjpy_df['ema20'] = ema(usdjpy_df['close'], 20)
        usdjpy_df['pct_change'] = usdjpy_df['close'].pct_change(5)  # 5-day momentum

    data = {}
    for symbol in SYMBOLS:
        df = load_data(symbol)
        df = df.copy()

        df['sma5'] = df['close'].rolling(5).mean()
        df['prev_high'] = df['high'].shift(1)
        df['prev_low'] = df['low'].shift(1)
        df['prev_close'] = df['close'].shift(1)
        df['prev_sma5'] = df['sma5'].shift(1)
        df['target_price'] = df['open'] + (df['prev_high'] - df['prev_low']) * NOISE_RATIO

        # Align BTC data
        btc_aligned = btc_df.reindex(df.index, method='ffill')
        df['prev_btc_close'] = btc_aligned['close'].shift(1)
        df['prev_btc_sma20'] = btc_aligned['sma20'].shift(1)

        # Align USD/JPY data
        if usdjpy_df is not None:
            usdjpy_aligned = usdjpy_df.reindex(df.index, method='ffill')
            df['prev_usdjpy_close'] = usdjpy_aligned['close'].shift(1)
            df['prev_usdjpy_sma20'] = usdjpy_aligned['sma20'].shift(1)
            df['prev_usdjpy_sma10'] = usdjpy_aligned['sma10'].shift(1)
            df['prev_usdjpy_ema20'] = usdjpy_aligned['ema20'].shift(1)
            df['prev_usdjpy_momentum'] = usdjpy_aligned['pct_change'].shift(1)

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

        # Check validity
        valid = all(not pd.isna(prices[s]['prev_sma5']) for s in SYMBOLS)
        if regime_filter.startswith('usdjpy') or regime_filter == 'both':
            valid = valid and not pd.isna(prices[SYMBOLS[0]].get('prev_usdjpy_sma20', np.nan))

        if not valid:
            equity = cash + sum(positions[s] * prices[s]['close'] for s in SYMBOLS)
            equity_curve.append({'date': date, 'equity': equity})
            continue

        # EXIT: SMA5
        for s in SYMBOLS:
            if positions[s] > 0:
                row = prices[s]
                if row['prev_close'] < row['prev_sma5']:
                    sell_price = row['open'] * (1 - SLIPPAGE)
                    cash += positions[s] * sell_price * (1 - FEE)
                    positions[s] = 0.0

        # ENTRY: check regime filter
        row_check = prices[SYMBOLS[0]]
        regime_ok = True

        if regime_filter == 'btc_sma20':
            regime_ok = row_check['prev_btc_close'] > row_check['prev_btc_sma20']
        elif regime_filter == 'usdjpy_sma20':
            regime_ok = row_check['prev_usdjpy_close'] > row_check['prev_usdjpy_sma20']
        elif regime_filter == 'usdjpy_ema20':
            regime_ok = row_check['prev_usdjpy_close'] > row_check['prev_usdjpy_ema20']
        elif regime_filter == 'usdjpy_sma10':
            regime_ok = row_check['prev_usdjpy_close'] > row_check['prev_usdjpy_sma10']
        elif regime_filter == 'usdjpy_rising':
            regime_ok = row_check['prev_usdjpy_momentum'] > 0
        elif regime_filter == 'both':
            btc_ok = row_check['prev_btc_close'] > row_check['prev_btc_sma20']
            usdjpy_ok = row_check['prev_usdjpy_close'] > row_check['prev_usdjpy_sma20']
            regime_ok = btc_ok and usdjpy_ok
        elif regime_filter == 'either':
            btc_ok = row_check['prev_btc_close'] > row_check['prev_btc_sma20']
            usdjpy_ok = row_check['prev_usdjpy_close'] > row_check['prev_usdjpy_sma20']
            regime_ok = btc_ok or usdjpy_ok

        buy_candidates = []
        for s in SYMBOLS:
            if positions[s] == 0:
                row = prices[s]
                vbo_trigger = row['high'] >= row['target_price']
                if vbo_trigger and regime_ok:
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
    print("USD/JPY AS MARKET REGIME FILTER TEST")
    print("=" * 90)

    # Fetch data
    usdjpy_df = fetch_usdjpy()
    btc_df = load_data("BTC")

    # Show USD/JPY data range
    print(f"  Date range: {usdjpy_df.index[0].date()} ~ {usdjpy_df.index[-1].date()}")

    # Baseline
    v10 = backtest('btc_sma20', usdjpy_df, btc_df)
    print(f"\n[BASELINE] V10: BTC > SMA20")
    print(f"  CAGR: {v10['cagr']:.1f}%, MDD: {v10['mdd']:.1f}%, Sharpe: {v10['sharpe']:.2f}, WinRate: {v10['win_rate']:.0f}%")

    # ==========================================================================
    # Test USD/JPY filters
    # ==========================================================================
    print("\n" + "=" * 90)
    print("MARKET REGIME FILTER COMPARISON")
    print("=" * 90)

    filters = [
        ('btc_sma20', 'BTC > SMA20 (V10)'),
        ('usdjpy_sma20', 'USD/JPY > SMA20'),
        ('usdjpy_ema20', 'USD/JPY > EMA20'),
        ('usdjpy_sma10', 'USD/JPY > SMA10'),
        ('usdjpy_rising', 'USD/JPY 5d momentum > 0'),
        ('both', 'BTC + USD/JPY (AND)'),
        ('either', 'BTC or USD/JPY (OR)'),
    ]

    print(f"\n{'Filter':<30} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10} {'WinRate':>10} {'Worst':>10}")
    print("-" * 85)

    results = []
    for fcode, fname in filters:
        r = backtest(fcode, usdjpy_df, btc_df)
        marker = " *" if fcode == 'btc_sma20' else ""
        print(f"{fname:<30} {r['cagr']:>9.1f}% {r['mdd']:>9.1f}% {r['sharpe']:>10.2f} {r['win_rate']:>9.0f}% {r['worst_year']:>9.1f}%{marker}")
        results.append({'filter': fcode, 'name': fname, **r})

    # ==========================================================================
    # Yearly comparison for top filters
    # ==========================================================================
    print("\n" + "=" * 90)
    print("YEARLY RETURN COMPARISON")
    print("=" * 90)

    top_filters = ['btc_sma20', 'usdjpy_sma20', 'both']

    # Get yearly data
    yearly_data = {}
    for fcode in top_filters:
        r = backtest(fcode, usdjpy_df, btc_df)
        yearly_data[fcode] = r['yearly']

    years = sorted(set().union(*[d.keys() for d in yearly_data.values()]))

    print(f"\n{'Year':<8}", end="")
    for fcode in top_filters:
        print(f"{fcode:>15}", end="")
    print()
    print("-" * 55)

    for year in years:
        print(f"{year:<8}", end="")
        for fcode in top_filters:
            ret = yearly_data[fcode].get(year, 0)
            print(f"{ret:>14.1f}%", end="")
        print()

    # Summary
    print("\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)

    best = max(results, key=lambda x: x['sharpe'])
    print(f"\nBest Filter: {best['name']}")
    print(f"  Sharpe: {best['sharpe']:.2f}, CAGR: {best['cagr']:.1f}%, MDD: {best['mdd']:.1f}%")

    improvement = (best['sharpe'] - v10['sharpe']) / v10['sharpe'] * 100
    print(f"\nV10 vs Best: {improvement:+.1f}% Sharpe")

    if best['filter'] != 'btc_sma20':
        print(f"\n→ {best['name']} outperforms BTC filter")
    else:
        print(f"\n→ BTC_SMA20 remains the best regime filter")


if __name__ == "__main__":
    main()
