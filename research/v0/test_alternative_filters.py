#!/usr/bin/env python3
"""Test Alternative Filters for V10 Strategy.

Market Regime Filters:
1. BTC SMA20 (current)
2. BTC EMA20
3. ETH SMA20
4. ETH EMA20
5. BTC RSI > 50
6. BTC volatility low (ATR < SMA of ATR)

Exit Filters:
1. SMA5 (current)
2. EMA5
3. EMA3
4. ATR trailing stop
5. Donchian low (lowest low N days)
6. Parabolic SAR style
"""

from pathlib import Path

import numpy as np
import pandas as pd

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


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift(1)).abs()
    low_close = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def backtest(regime_filter: str, exit_filter: str) -> dict:
    """
    Backtest with different regime and exit filters.

    regime_filter: 'btc_sma20', 'btc_ema20', 'eth_sma20', 'eth_ema20',
                   'btc_rsi50', 'btc_lowvol', 'none'
    exit_filter: 'sma5', 'ema5', 'ema3', 'atr_trail', 'donchian5', 'none'
    """
    btc_df = load_data("BTC")
    eth_df = load_data("ETH")

    # Prepare regime data
    btc_df['sma20'] = btc_df['close'].rolling(20).mean()
    btc_df['ema20'] = ema(btc_df['close'], 20)
    btc_df['rsi14'] = rsi(btc_df['close'], 14)
    btc_df['atr14'] = atr(btc_df, 14)
    btc_df['atr_sma'] = btc_df['atr14'].rolling(20).mean()

    eth_df['sma20'] = eth_df['close'].rolling(20).mean()
    eth_df['ema20'] = ema(eth_df['close'], 20)

    data = {}
    for symbol in SYMBOLS:
        df = load_data(symbol)
        df = df.copy()

        # Exit indicators
        df['sma5'] = df['close'].rolling(5).mean()
        df['ema5'] = ema(df['close'], 5)
        df['ema3'] = ema(df['close'], 3)
        df['atr14'] = atr(df, 14)
        df['donchian5'] = df['low'].rolling(5).min()

        df['prev_high'] = df['high'].shift(1)
        df['prev_low'] = df['low'].shift(1)
        df['prev_close'] = df['close'].shift(1)
        df['target_price'] = df['open'] + (df['prev_high'] - df['prev_low']) * NOISE_RATIO

        # Shift exit indicators
        df['prev_sma5'] = df['sma5'].shift(1)
        df['prev_ema5'] = df['ema5'].shift(1)
        df['prev_ema3'] = df['ema3'].shift(1)
        df['prev_atr14'] = df['atr14'].shift(1)
        df['prev_donchian5'] = df['donchian5'].shift(1)

        # Align regime data
        btc_aligned = btc_df.reindex(df.index, method='ffill')
        eth_aligned = eth_df.reindex(df.index, method='ffill')

        df['prev_btc_close'] = btc_aligned['close'].shift(1)
        df['prev_btc_sma20'] = btc_aligned['sma20'].shift(1)
        df['prev_btc_ema20'] = btc_aligned['ema20'].shift(1)
        df['prev_btc_rsi'] = btc_aligned['rsi14'].shift(1)
        df['prev_btc_atr'] = btc_aligned['atr14'].shift(1)
        df['prev_btc_atr_sma'] = btc_aligned['atr_sma'].shift(1)

        df['prev_eth_close'] = eth_aligned['close'].shift(1)
        df['prev_eth_sma20'] = eth_aligned['sma20'].shift(1)
        df['prev_eth_ema20'] = eth_aligned['ema20'].shift(1)

        data[symbol] = df

    all_dates = set(data[SYMBOLS[0]].index)
    for df in data.values():
        all_dates &= set(df.index)
    all_dates = sorted(all_dates)

    cash = INITIAL_CAPITAL
    positions = dict.fromkeys(SYMBOLS, 0.0)
    entry_prices = dict.fromkeys(SYMBOLS, 0.0)
    equity_curve = []
    n = len(SYMBOLS)

    for date in all_dates:
        prices = {s: data[s].loc[date] for s in SYMBOLS}

        # Check validity
        valid = all(
            not pd.isna(prices[s]['prev_sma5']) and
            not pd.isna(prices[s]['prev_btc_sma20'])
            for s in SYMBOLS
        )

        if not valid:
            equity = cash + sum(positions[s] * prices[s]['close'] for s in SYMBOLS)
            equity_curve.append({'date': date, 'equity': equity})
            continue

        # EXIT logic
        for s in SYMBOLS:
            if positions[s] > 0:
                row = prices[s]
                should_sell = False

                if exit_filter == 'sma5':
                    should_sell = row['prev_close'] < row['prev_sma5']
                elif exit_filter == 'ema5':
                    should_sell = row['prev_close'] < row['prev_ema5']
                elif exit_filter == 'ema3':
                    should_sell = row['prev_close'] < row['prev_ema3']
                elif exit_filter == 'atr_trail':
                    # Exit if price drops 2*ATR from entry
                    trail_stop = entry_prices[s] - 2 * row['prev_atr14']
                    should_sell = row['prev_close'] < trail_stop
                elif exit_filter == 'donchian5':
                    should_sell = row['prev_close'] < row['prev_donchian5']
                elif exit_filter == 'none':
                    should_sell = False  # Only time cut (next day)

                if should_sell:
                    sell_price = row['open'] * (1 - SLIPPAGE)
                    cash += positions[s] * sell_price * (1 - FEE)
                    positions[s] = 0.0
                    entry_prices[s] = 0.0

        # ENTRY logic - check regime filter
        regime_ok = True
        row_check = prices[SYMBOLS[0]]  # Use first symbol for regime check

        if regime_filter == 'btc_sma20':
            regime_ok = row_check['prev_btc_close'] > row_check['prev_btc_sma20']
        elif regime_filter == 'btc_ema20':
            regime_ok = row_check['prev_btc_close'] > row_check['prev_btc_ema20']
        elif regime_filter == 'eth_sma20':
            regime_ok = row_check['prev_eth_close'] > row_check['prev_eth_sma20']
        elif regime_filter == 'eth_ema20':
            regime_ok = row_check['prev_eth_close'] > row_check['prev_eth_ema20']
        elif regime_filter == 'btc_rsi50':
            regime_ok = row_check['prev_btc_rsi'] > 50
        elif regime_filter == 'btc_lowvol':
            regime_ok = row_check['prev_btc_atr'] < row_check['prev_btc_atr_sma']
        elif regime_filter == 'none':
            regime_ok = True

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
                entry_prices[s] = buy_price
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
    }


def main():
    print("=" * 95)
    print("ALTERNATIVE FILTERS TEST")
    print("=" * 95)

    # Baseline
    v10 = backtest('btc_sma20', 'sma5')
    print(f"\n[BASELINE] V10: BTC_SMA20 + SMA5 exit")
    print(f"  CAGR: {v10['cagr']:.1f}%, MDD: {v10['mdd']:.1f}%, Sharpe: {v10['sharpe']:.2f}, WinRate: {v10['win_rate']:.0f}%")

    # ==========================================================================
    # 1. Exit Filter Comparison (with BTC_SMA20 regime)
    # ==========================================================================
    print("\n" + "=" * 95)
    print("1. EXIT FILTER COMPARISON (Market Regime: BTC_SMA20)")
    print("=" * 95)

    exit_filters = ['sma5', 'ema5', 'ema3', 'atr_trail', 'donchian5']

    print(f"\n{'Exit Filter':<15} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10} {'WinRate':>10} {'Worst':>10}")
    print("-" * 70)

    exit_results = []
    for ef in exit_filters:
        r = backtest('btc_sma20', ef)
        marker = " *" if ef == 'sma5' else ""
        print(f"{ef:<15} {r['cagr']:>9.1f}% {r['mdd']:>9.1f}% {r['sharpe']:>10.2f} {r['win_rate']:>9.0f}% {r['worst_year']:>9.1f}%{marker}")
        exit_results.append({'filter': ef, **r})

    # ==========================================================================
    # 2. Market Regime Filter Comparison (with SMA5 exit)
    # ==========================================================================
    print("\n" + "=" * 95)
    print("2. MARKET REGIME FILTER COMPARISON (Exit: SMA5)")
    print("=" * 95)

    regime_filters = ['btc_sma20', 'btc_ema20', 'eth_sma20', 'eth_ema20', 'btc_rsi50', 'btc_lowvol', 'none']

    print(f"\n{'Regime Filter':<15} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10} {'WinRate':>10} {'Worst':>10}")
    print("-" * 70)

    regime_results = []
    for rf in regime_filters:
        r = backtest(rf, 'sma5')
        marker = " *" if rf == 'btc_sma20' else ""
        print(f"{rf:<15} {r['cagr']:>9.1f}% {r['mdd']:>9.1f}% {r['sharpe']:>10.2f} {r['win_rate']:>9.0f}% {r['worst_year']:>9.1f}%{marker}")
        regime_results.append({'filter': rf, **r})

    # ==========================================================================
    # 3. Best Combinations
    # ==========================================================================
    print("\n" + "=" * 95)
    print("3. TOP COMBINATIONS (Regime × Exit)")
    print("=" * 95)

    # Test promising combinations
    combos = []
    best_regimes = ['btc_sma20', 'btc_ema20', 'eth_sma20']
    best_exits = ['sma5', 'ema5', 'ema3']

    for rf in best_regimes:
        for ef in best_exits:
            r = backtest(rf, ef)
            combos.append({'regime': rf, 'exit': ef, **r})

    df = pd.DataFrame(combos).sort_values('sharpe', ascending=False)

    print(f"\n{'Regime':<15} {'Exit':<10} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10} {'WinRate':>10}")
    print("-" * 70)

    for _, row in df.iterrows():
        marker = " *" if row['regime'] == 'btc_sma20' and row['exit'] == 'sma5' else ""
        print(f"{row['regime']:<15} {row['exit']:<10} {row['cagr']:>9.1f}% {row['mdd']:>9.1f}% {row['sharpe']:>10.2f} {row['win_rate']:>9.0f}%{marker}")

    # Summary
    print("\n" + "=" * 95)
    print("SUMMARY")
    print("=" * 95)

    best_exit = max(exit_results, key=lambda x: x['sharpe'])
    best_regime = max(regime_results, key=lambda x: x['sharpe'])
    best_combo = df.iloc[0]

    print(f"\nBest Exit Filter: {best_exit['filter']} (Sharpe {best_exit['sharpe']:.2f})")
    print(f"Best Regime Filter: {best_regime['filter']} (Sharpe {best_regime['sharpe']:.2f})")
    print(f"Best Combination: {best_combo['regime']} + {best_combo['exit']} (Sharpe {best_combo['sharpe']:.2f})")

    improvement = (best_combo['sharpe'] - v10['sharpe']) / v10['sharpe'] * 100
    print(f"\nV10 vs Best: {improvement:+.1f}% Sharpe")


if __name__ == "__main__":
    main()
