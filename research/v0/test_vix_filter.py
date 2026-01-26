#!/usr/bin/env python3
"""Test VIX as Market Regime Filter.

Theory: Low VIX = risk-on (complacency), High VIX = risk-off (fear)
       VIX < 20 is generally considered low volatility
       VIX > 30 is high fear
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


def fetch_vix() -> pd.DataFrame:
    """Fetch VIX data from Yahoo Finance."""
    print("Fetching VIX data...")
    ticker = yf.Ticker("^VIX")
    df = ticker.history(start="2017-01-01", end="2026-01-01")
    df.index = df.index.tz_localize(None)
    df.columns = [c.lower() for c in df.columns]
    print(f"  Got {len(df)} days of VIX data")
    print(f"  VIX range: {df['close'].min():.1f} ~ {df['close'].max():.1f}")
    print(f"  VIX mean: {df['close'].mean():.1f}")
    return df


def backtest(regime_filter: str, vix_df: pd.DataFrame = None, btc_df: pd.DataFrame = None) -> dict:
    """
    Backtest with different regime filters.
    """
    if btc_df is None:
        btc_df = load_data("BTC")

    btc_df = btc_df.copy()
    btc_df['sma20'] = btc_df['close'].rolling(20).mean()

    if vix_df is not None:
        vix_df = vix_df.copy()
        vix_df['sma20'] = vix_df['close'].rolling(20).mean()
        vix_df['sma10'] = vix_df['close'].rolling(10).mean()
        vix_df['pct_change'] = vix_df['close'].pct_change(5)

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

        # Align VIX data
        if vix_df is not None:
            vix_aligned = vix_df.reindex(df.index, method='ffill')
            df['prev_vix'] = vix_aligned['close'].shift(1)
            df['prev_vix_sma20'] = vix_aligned['sma20'].shift(1)
            df['prev_vix_sma10'] = vix_aligned['sma10'].shift(1)
            df['prev_vix_momentum'] = vix_aligned['pct_change'].shift(1)

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

        valid = all(not pd.isna(prices[s]['prev_sma5']) for s in SYMBOLS)
        if regime_filter.startswith('vix') or regime_filter in ['both', 'either']:
            valid = valid and not pd.isna(prices[SYMBOLS[0]].get('prev_vix', np.nan))

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
        elif regime_filter == 'vix_below20':
            regime_ok = row_check['prev_vix'] < 20
        elif regime_filter == 'vix_below25':
            regime_ok = row_check['prev_vix'] < 25
        elif regime_filter == 'vix_below30':
            regime_ok = row_check['prev_vix'] < 30
        elif regime_filter == 'vix_below_sma':
            regime_ok = row_check['prev_vix'] < row_check['prev_vix_sma20']
        elif regime_filter == 'vix_falling':
            regime_ok = row_check['prev_vix_momentum'] < 0
        elif regime_filter == 'both_vix20':
            btc_ok = row_check['prev_btc_close'] > row_check['prev_btc_sma20']
            vix_ok = row_check['prev_vix'] < 20
            regime_ok = btc_ok and vix_ok
        elif regime_filter == 'both_vix25':
            btc_ok = row_check['prev_btc_close'] > row_check['prev_btc_sma20']
            vix_ok = row_check['prev_vix'] < 25
            regime_ok = btc_ok and vix_ok
        elif regime_filter == 'both_vix_sma':
            btc_ok = row_check['prev_btc_close'] > row_check['prev_btc_sma20']
            vix_ok = row_check['prev_vix'] < row_check['prev_vix_sma20']
            regime_ok = btc_ok and vix_ok
        elif regime_filter == 'either':
            btc_ok = row_check['prev_btc_close'] > row_check['prev_btc_sma20']
            vix_ok = row_check['prev_vix'] < 20
            regime_ok = btc_ok or vix_ok

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
    print("VIX AS MARKET REGIME FILTER TEST")
    print("=" * 90)

    # Fetch data
    vix_df = fetch_vix()
    btc_df = load_data("BTC")

    print(f"  Date range: {vix_df.index[0].date()} ~ {vix_df.index[-1].date()}")

    # Baseline
    v10 = backtest('btc_sma20', vix_df, btc_df)
    print(f"\n[BASELINE] V10: BTC > SMA20")
    print(f"  CAGR: {v10['cagr']:.1f}%, MDD: {v10['mdd']:.1f}%, Sharpe: {v10['sharpe']:.2f}, WinRate: {v10['win_rate']:.0f}%")

    # ==========================================================================
    # Test VIX filters
    # ==========================================================================
    print("\n" + "=" * 90)
    print("VIX FILTER COMPARISON")
    print("=" * 90)

    filters = [
        ('btc_sma20', 'BTC > SMA20 (V10)'),
        ('vix_below20', 'VIX < 20'),
        ('vix_below25', 'VIX < 25'),
        ('vix_below30', 'VIX < 30'),
        ('vix_below_sma', 'VIX < VIX_SMA20'),
        ('vix_falling', 'VIX 5d falling'),
        ('both_vix20', 'BTC + VIX<20 (AND)'),
        ('both_vix25', 'BTC + VIX<25 (AND)'),
        ('both_vix_sma', 'BTC + VIX<SMA (AND)'),
        ('either', 'BTC or VIX<20 (OR)'),
    ]

    print(f"\n{'Filter':<25} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10} {'WinRate':>10} {'Worst':>10}")
    print("-" * 80)

    results = []
    for fcode, fname in filters:
        r = backtest(fcode, vix_df, btc_df)
        marker = " *" if fcode == 'btc_sma20' else ""
        print(f"{fname:<25} {r['cagr']:>9.1f}% {r['mdd']:>9.1f}% {r['sharpe']:>10.2f} {r['win_rate']:>9.0f}% {r['worst_year']:>9.1f}%{marker}")
        results.append({'filter': fcode, 'name': fname, **r})

    # ==========================================================================
    # Yearly comparison
    # ==========================================================================
    print("\n" + "=" * 90)
    print("YEARLY RETURN COMPARISON (Top filters)")
    print("=" * 90)

    top_filters = ['btc_sma20', 'vix_below25', 'both_vix25']

    yearly_data = {}
    for fcode in top_filters:
        r = backtest(fcode, vix_df, btc_df)
        yearly_data[fcode] = r['yearly']

    years = sorted(set().union(*[d.keys() for d in yearly_data.values()]))

    print(f"\n{'Year':<8}", end="")
    for fcode in top_filters:
        label = fcode[:12]
        print(f"{label:>15}", end="")
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

    # Check if any combined filter beats V10
    combined = [r for r in results if r['filter'].startswith('both')]
    best_combined = max(combined, key=lambda x: x['sharpe']) if combined else None

    if best_combined and best_combined['sharpe'] > v10['sharpe']:
        improvement = (best_combined['sharpe'] - v10['sharpe']) / v10['sharpe'] * 100
        print(f"\n→ {best_combined['name']} beats V10 by {improvement:+.1f}% Sharpe")
    else:
        print(f"\n→ VIX doesn't improve V10")


if __name__ == "__main__":
    main()
