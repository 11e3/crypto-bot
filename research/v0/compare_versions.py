#!/usr/bin/env python3
"""Compare V1, V2, V5, V6, V7, V8, V9 strategies."""

from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

FEE = 0.0005
SLIPPAGE = 0.0005
NOISE_RATIO = 0.5
INITIAL_CAPITAL = 1_000_000
TRAILING_STOP_PCT = 0.05  # V7: 5% trailing stop


def load_data(symbol: str, data_dir: str = "data") -> pd.DataFrame:
    filepath = Path(data_dir) / f"{symbol}.csv"
    df = pd.read_csv(filepath, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    return df.sort_index()


def filter_date_range(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if start:
        df = df[df.index >= pd.to_datetime(start)]
    if end:
        df = df[df.index <= pd.to_datetime(end)]
    return df


def calculate_indicators(df: pd.DataFrame, btc_df: pd.DataFrame | None = None) -> pd.DataFrame:
    df = df.copy()
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    df['prev_high'] = df['high'].shift(1)
    df['prev_low'] = df['low'].shift(1)
    df['prev_close'] = df['close'].shift(1)
    df['prev_ma5'] = df['ma5'].shift(1)
    df['prev_ma20'] = df['ma20'].shift(1)
    df['prev_vol'] = df['volume'].shift(1)
    df['prev_vol_ma20'] = df['vol_ma20'].shift(1)
    df['target_price'] = df['open'] + (df['prev_high'] - df['prev_low']) * NOISE_RATIO
    # 이격도: prev_close / prev_ma20
    df['prev_disparity'] = df['prev_close'] / df['prev_ma20']

    if btc_df is not None:
        btc_aligned = btc_df.reindex(df.index, method='ffill')
        btc_aligned['btc_ma20'] = btc_aligned['close'].rolling(20).mean()
        df['prev_btc_close'] = btc_aligned['close'].shift(1)
        df['prev_btc_ma20'] = btc_aligned['btc_ma20'].shift(1)

    return df


def backtest(symbols: list[str], version: str, start: str | None = None, end: str | None = None) -> dict:
    """
    V1: Entry=VBO+MA5+BTC, Exit=MA5 OR BTC
    V2: Entry=VBO+MA5+BTC, Exit=MA5 only
    V5: Entry=VBO+MA5+BTC+MA20, Exit=MA5 only
    V6: Entry=VBO+MA5>MA20, Exit=MA5<MA20 (golden/death cross)
    V7: Entry=VBO+MA5, Exit=5% trailing stop
    V8: Entry=VBO+MA5+(disparity<1.1), Exit=MA5 (이격도 필터)
    V9: Entry=VBO+MA5+(vol>vol_ma20), Exit=MA5 (거래량 필터)
    """
    need_btc = version in ('V1', 'V2', 'V5')
    btc_df = None
    if need_btc:
        btc_df = load_data("BTC")
        btc_df = filter_date_range(btc_df, start, end)

    data = {}
    for symbol in symbols:
        df = load_data(symbol)
        df = filter_date_range(df, start, end)
        df = calculate_indicators(df, btc_df if need_btc else None)
        data[symbol] = df

    all_dates = set(data[list(symbols)[0]].index)
    for df in data.values():
        all_dates &= set(df.index)
    all_dates = sorted(all_dates)

    cash = INITIAL_CAPITAL
    positions = dict.fromkeys(symbols, 0.0)
    entry_prices = dict.fromkeys(symbols, 0.0)  # V7: 진입가 추적
    peak_prices = dict.fromkeys(symbols, 0.0)   # V7: 고점 추적
    equity_curve = []
    n = len(symbols)

    for date in all_dates:
        prices = {s: data[s].loc[date] for s in symbols}

        # Validity check
        if version in ('V1', 'V2'):
            valid = all(not pd.isna(prices[s]['prev_ma5']) and not pd.isna(prices[s]['prev_btc_ma20']) for s in symbols)
        elif version == 'V5':
            valid = all(not pd.isna(prices[s]['prev_ma5']) and not pd.isna(prices[s]['prev_ma20']) and not pd.isna(prices[s]['prev_btc_ma20']) for s in symbols)
        elif version in ('V6', 'V8'):
            valid = all(not pd.isna(prices[s]['prev_ma5']) and not pd.isna(prices[s]['prev_ma20']) for s in symbols)
        elif version == 'V9':
            valid = all(not pd.isna(prices[s]['prev_ma5']) and not pd.isna(prices[s]['prev_vol_ma20']) for s in symbols)
        else:  # V7
            valid = all(not pd.isna(prices[s]['prev_ma5']) for s in symbols)

        if not valid:
            equity = cash + sum(positions[s] * prices[s]['close'] for s in symbols)
            equity_curve.append({'date': date, 'equity': equity})
            continue

        # Update peak prices for V7
        if version == 'V7':
            for s in symbols:
                if positions[s] > 0:
                    peak_prices[s] = max(peak_prices[s], prices[s]['high'])

        # SELL
        for s in symbols:
            if positions[s] > 0:
                row = prices[s]
                if version == 'V1':
                    sell = (row['prev_close'] < row['prev_ma5']) or (row['prev_btc_close'] < row['prev_btc_ma20'])
                elif version == 'V6':
                    sell = row['prev_ma5'] < row['prev_ma20']
                elif version == 'V7':
                    # Trailing stop: 고점 대비 5% 하락 시 매도
                    sell = row['open'] < peak_prices[s] * (1 - TRAILING_STOP_PCT)
                else:  # V2, V5, V8, V9
                    sell = row['prev_close'] < row['prev_ma5']

                if sell:
                    sell_price = row['open'] * (1 - SLIPPAGE)
                    cash += positions[s] * sell_price * (1 - FEE)
                    positions[s] = 0.0
                    entry_prices[s] = 0.0
                    peak_prices[s] = 0.0

        # BUY
        buy_candidates = []
        for s in symbols:
            if positions[s] == 0:
                row = prices[s]
                if version in ('V1', 'V2'):
                    buy = (row['high'] >= row['target_price'] and
                           row['prev_close'] > row['prev_ma5'] and
                           row['prev_btc_close'] > row['prev_btc_ma20'])
                elif version == 'V5':
                    buy = (row['high'] >= row['target_price'] and
                           row['prev_close'] > row['prev_ma5'] and
                           row['prev_close'] > row['prev_ma20'] and
                           row['prev_btc_close'] > row['prev_btc_ma20'])
                elif version == 'V6':
                    buy = (row['high'] >= row['target_price'] and
                           row['prev_ma5'] > row['prev_ma20'])
                elif version == 'V7':
                    buy = (row['high'] >= row['target_price'] and
                           row['prev_close'] > row['prev_ma5'])
                elif version == 'V8':
                    buy = (row['high'] >= row['target_price'] and
                           row['prev_close'] > row['prev_ma5'] and
                           row['prev_disparity'] < 1.1)  # 이격도 110% 미만
                elif version == 'V9':
                    buy = (row['high'] >= row['target_price'] and
                           row['prev_close'] > row['prev_ma5'] and
                           row['prev_vol'] > row['prev_vol_ma20'])  # 거래량 > 20일 평균
                else:
                    buy = False

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
                entry_prices[s] = buy_price
                peak_prices[s] = buy_price  # V7: 초기 고점 = 진입가
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
    neg_ret = ret[ret < 0]
    sortino = (ret.mean() / neg_ret.std()) * np.sqrt(365) if len(neg_ret) > 0 and neg_ret.std() > 0 else 0

    # Yearly returns for consistency
    eq_df['year'] = eq_df.index.year
    yearly = eq_df.groupby('year')['equity'].agg(['first', 'last'])
    yearly['return'] = (yearly['last'] / yearly['first'] - 1) * 100
    win_rate = (yearly['return'] > 0).sum() / len(yearly) * 100
    worst_year = yearly['return'].min()

    return {
        'combo': '+'.join(symbols),
        'n': len(symbols),
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
        'sortino': sortino,
        'win_rate': win_rate,
        'worst_year': worst_year,
    }


def main():
    start = None  # Full period
    symbols_list = ['BTC', 'ETH', 'XRP', 'TRX', 'ADA']
    versions = ['V1', 'V2', 'V5', 'V6', 'V7', 'V8', 'V9']

    all_combos = []
    for n in range(2, 6):
        for combo in combinations(symbols_list, n):
            all_combos.append(list(combo))

    results = {v: [] for v in versions}

    for v in versions:
        for combo in all_combos:
            r = backtest(combo, v, start=start)
            results[v].append(r)

    # Find best for each metric
    for v in versions:
        df = pd.DataFrame(results[v])
        best_cagr = df.loc[df['cagr'].idxmax()]
        best_mdd = df.loc[df['mdd'].idxmax()]
        best_sharpe = df.loc[df['sharpe'].idxmax()]
        best_sortino = df.loc[df['sortino'].idxmax()]

        print(f"\n{'='*100}")
        print(f"{v} Best Results (Full Period)")
        print(f"{'='*100}")
        print(f"{'Metric':<10} {'Combo':<20} {'CAGR':>8} {'MDD':>8} {'Sharpe':>8} {'Sortino':>8} {'WinRate':>8} {'Worst':>8}")
        print("-" * 100)
        print(f"{'CAGR':<10} {best_cagr['combo']:<20} {best_cagr['cagr']:>7.1f}% {best_cagr['mdd']:>7.1f}% {best_cagr['sharpe']:>8.2f} {best_cagr['sortino']:>8.2f} {best_cagr['win_rate']:>7.0f}% {best_cagr['worst_year']:>7.1f}%")
        print(f"{'MDD':<10} {best_mdd['combo']:<20} {best_mdd['cagr']:>7.1f}% {best_mdd['mdd']:>7.1f}% {best_mdd['sharpe']:>8.2f} {best_mdd['sortino']:>8.2f} {best_mdd['win_rate']:>7.0f}% {best_mdd['worst_year']:>7.1f}%")
        print(f"{'Sharpe':<10} {best_sharpe['combo']:<20} {best_sharpe['cagr']:>7.1f}% {best_sharpe['mdd']:>7.1f}% {best_sharpe['sharpe']:>8.2f} {best_sharpe['sortino']:>8.2f} {best_sharpe['win_rate']:>7.0f}% {best_sharpe['worst_year']:>7.1f}%")
        print(f"{'Sortino':<10} {best_sortino['combo']:<20} {best_sortino['cagr']:>7.1f}% {best_sortino['mdd']:>7.1f}% {best_sortino['sharpe']:>8.2f} {best_sortino['sortino']:>8.2f} {best_sortino['win_rate']:>7.0f}% {best_sortino['worst_year']:>7.1f}%")

    # Summary comparison
    print(f"\n{'='*100}")
    print("VERSION COMPARISON SUMMARY (Best Sharpe combo for each version)")
    print(f"{'='*100}")
    print(f"{'Version':<8} {'Combo':<20} {'CAGR':>8} {'MDD':>8} {'Sharpe':>8} {'Sortino':>8} {'WinRate':>8} {'Worst':>8}")
    print("-" * 100)

    summary = []
    for v in versions:
        df = pd.DataFrame(results[v])
        best = df.loc[df['sharpe'].idxmax()]
        summary.append(best)
        print(f"{v:<8} {best['combo']:<20} {best['cagr']:>7.1f}% {best['mdd']:>7.1f}% {best['sharpe']:>8.2f} {best['sortino']:>8.2f} {best['win_rate']:>7.0f}% {best['worst_year']:>7.1f}%")


if __name__ == "__main__":
    main()
