#!/usr/bin/env python3
"""V1.1 Detailed Validation.

Extended tests:
1. Train/Test split (multiple periods)
2. Year-by-year with monthly breakdown
3. Trade statistics (count, win rate, avg hold, etc.)
4. Parameter grid search (EMA x BTC_MA x NOISE)
5. Fee/Slippage sensitivity
6. Drawdown analysis
7. Portfolio combinations
8. Rolling Sharpe analysis
9. Correlation with BTC buy & hold
"""

from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd

INITIAL_CAPITAL = 1_000_000
ALL_SYMBOLS = ['BTC', 'ETH', 'XRP', 'TRX', 'ADA']


def load_data(symbol: str, data_dir: str | None = None) -> pd.DataFrame:
    if data_dir is None:
        data_dir = Path(__file__).parent.parent.parent / "data"
    filepath = Path(data_dir) / f"{symbol}.csv"
    df = pd.read_csv(filepath, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    return df.sort_index()


def backtest_v1_1_detailed(
    symbols: list[str],
    ema_span: int = 5,
    btc_ma: int = 20,
    noise_ratio: float = 0.5,
    fee: float = 0.0005,
    slippage: float = 0.0005,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """V1.1 with detailed trade tracking."""
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
        df['target_price'] = df['open'] + (df['prev_high'] - df['prev_low']) * noise_ratio

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
    entry_prices = dict.fromkeys(symbols, 0.0)
    entry_dates = dict.fromkeys(symbols, None)
    equity_curve = []
    trades = []
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

        # SELL
        for s in symbols:
            if positions[s] > 0:
                row = prices[s]
                if row['prev_close'] < row['prev_ema']:
                    sell_price = row['open'] * (1 - slippage)
                    sell_value = positions[s] * sell_price * (1 - fee)
                    pnl = sell_value - (positions[s] * entry_prices[s])
                    pnl_pct = (sell_price / entry_prices[s] - 1) * 100
                    hold_days = (date - entry_dates[s]).days if entry_dates[s] else 0

                    trades.append({
                        'symbol': s,
                        'entry_date': entry_dates[s],
                        'exit_date': date,
                        'entry_price': entry_prices[s],
                        'exit_price': sell_price,
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                        'hold_days': hold_days,
                    })

                    cash += sell_value
                    positions[s] = 0.0

        # BUY
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
                buy_price = row['target_price'] * (1 + slippage)
                positions[s] = (val * (1 - fee)) / buy_price
                entry_prices[s] = buy_price
                entry_dates[s] = date
                cash -= val

        equity = cash + sum(positions[s] * prices[s]['close'] for s in symbols)
        equity_curve.append({'date': date, 'equity': equity})

    if not equity_curve:
        return {'cagr': 0, 'mdd': 0, 'sharpe': 0, 'trades': [], 'equity_curve': pd.DataFrame()}

    eq_df = pd.DataFrame(equity_curve).set_index('date')
    final = eq_df['equity'].iloc[-1]
    initial = eq_df['equity'].iloc[0]
    days = (eq_df.index[-1] - eq_df.index[0]).days
    years = days / 365.25
    cagr = (pow(final / initial, 1 / years) - 1) * 100 if years > 0 else 0

    running_max = eq_df['equity'].expanding().max()
    drawdown = (eq_df['equity'] / running_max - 1) * 100
    mdd = drawdown.min()

    ret = eq_df['equity'].pct_change().dropna()
    sharpe = (ret.mean() / ret.std()) * np.sqrt(365) if ret.std() > 0 else 0

    eq_df['year'] = eq_df.index.year
    yearly = eq_df.groupby('year')['equity'].agg(['first', 'last'])
    yearly['return'] = (yearly['last'] / yearly['first'] - 1) * 100
    yearly_returns = yearly['return'].to_dict()

    # Monthly returns
    eq_df['month'] = eq_df.index.to_period('M')
    monthly = eq_df.groupby('month')['equity'].agg(['first', 'last'])
    monthly['return'] = (monthly['last'] / monthly['first'] - 1) * 100
    monthly_returns = monthly['return'].to_dict()

    return {
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
        'yearly': yearly_returns,
        'monthly': monthly_returns,
        'trades': trades,
        'equity_curve': eq_df,
        'drawdown': drawdown,
        'final_equity': final,
    }


def main():
    symbols = ['BTC', 'ETH']

    print("=" * 90)
    print("V1.1 DETAILED VALIDATION")
    print("Strategy: VBO+BTC entry, EMA5 exit | Portfolio: BTC+ETH")
    print("=" * 90)

    # Full backtest with details
    full = backtest_v1_1_detailed(symbols)

    # =========================================================================
    # 1. TRADE STATISTICS
    # =========================================================================
    print("\n" + "=" * 90)
    print("1. TRADE STATISTICS")
    print("=" * 90)

    trades = full['trades']
    if trades:
        trades_df = pd.DataFrame(trades)

        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df['pnl_pct'] > 0])
        losing_trades = len(trades_df[trades_df['pnl_pct'] <= 0])
        win_rate = winning_trades / total_trades * 100 if total_trades > 0 else 0

        avg_win = trades_df[trades_df['pnl_pct'] > 0]['pnl_pct'].mean() if winning_trades > 0 else 0
        avg_loss = trades_df[trades_df['pnl_pct'] <= 0]['pnl_pct'].mean() if losing_trades > 0 else 0
        avg_hold = trades_df['hold_days'].mean()
        max_win = trades_df['pnl_pct'].max()
        max_loss = trades_df['pnl_pct'].min()

        profit_factor = abs(trades_df[trades_df['pnl_pct'] > 0]['pnl_pct'].sum() /
                           trades_df[trades_df['pnl_pct'] <= 0]['pnl_pct'].sum()) if losing_trades > 0 else float('inf')

        print(f"\nTotal trades: {total_trades}")
        print(f"Winning: {winning_trades} ({win_rate:.1f}%)")
        print(f"Losing: {losing_trades} ({100-win_rate:.1f}%)")
        print(f"\nAvg win: +{avg_win:.2f}%")
        print(f"Avg loss: {avg_loss:.2f}%")
        print(f"Max win: +{max_win:.2f}%")
        print(f"Max loss: {max_loss:.2f}%")
        print(f"\nAvg hold days: {avg_hold:.1f}")
        print(f"Profit factor: {profit_factor:.2f}")

        # By symbol
        print(f"\n{'Symbol':<8} {'Trades':>8} {'Win%':>8} {'Avg%':>10}")
        print("-" * 38)
        for sym in symbols:
            sym_trades = trades_df[trades_df['symbol'] == sym]
            sym_wins = len(sym_trades[sym_trades['pnl_pct'] > 0])
            sym_total = len(sym_trades)
            sym_win_rate = sym_wins / sym_total * 100 if sym_total > 0 else 0
            sym_avg = sym_trades['pnl_pct'].mean() if sym_total > 0 else 0
            print(f"{sym:<8} {sym_total:>8} {sym_win_rate:>7.1f}% {sym_avg:>9.2f}%")

    # =========================================================================
    # 2. DRAWDOWN ANALYSIS
    # =========================================================================
    print("\n" + "=" * 90)
    print("2. DRAWDOWN ANALYSIS")
    print("=" * 90)

    dd = full['drawdown']

    # Find drawdown periods
    in_dd = dd < 0
    dd_starts = in_dd & ~in_dd.shift(1).fillna(False)
    dd_ends = ~in_dd & in_dd.shift(1).fillna(False)

    dd_periods = []
    start_idx = None
    for i, (date, is_start) in enumerate(dd_starts.items()):
        if is_start:
            start_idx = date
        if dd_ends.iloc[i] and start_idx:
            dd_periods.append({
                'start': start_idx,
                'end': date,
                'depth': dd[start_idx:date].min(),
                'days': (date - start_idx).days,
            })
            start_idx = None

    if dd_periods:
        dd_df = pd.DataFrame(dd_periods).sort_values('depth')
        print(f"\nTop 5 Drawdowns:")
        print(f"{'Start':<12} {'End':<12} {'Depth':>10} {'Days':>8}")
        print("-" * 46)
        for _, row in dd_df.head(5).iterrows():
            print(f"{str(row['start'].date()):<12} {str(row['end'].date()):<12} {row['depth']:>9.1f}% {row['days']:>8}")

        avg_dd_days = dd_df['days'].mean()
        max_dd_days = dd_df['days'].max()
        print(f"\nAvg drawdown duration: {avg_dd_days:.0f} days")
        print(f"Max drawdown duration: {max_dd_days} days")

    # =========================================================================
    # 3. MONTHLY RETURNS DISTRIBUTION
    # =========================================================================
    print("\n" + "=" * 90)
    print("3. MONTHLY RETURNS DISTRIBUTION")
    print("=" * 90)

    monthly_rets = list(full['monthly'].values())
    print(f"\nMonths: {len(monthly_rets)}")
    print(f"Positive: {sum(1 for r in monthly_rets if r > 0)} ({sum(1 for r in monthly_rets if r > 0)/len(monthly_rets)*100:.0f}%)")
    print(f"Negative: {sum(1 for r in monthly_rets if r <= 0)} ({sum(1 for r in monthly_rets if r <= 0)/len(monthly_rets)*100:.0f}%)")
    print(f"\nMean: {np.mean(monthly_rets):.2f}%")
    print(f"Median: {np.median(monthly_rets):.2f}%")
    print(f"Std: {np.std(monthly_rets):.2f}%")
    print(f"Min: {min(monthly_rets):.2f}%")
    print(f"Max: {max(monthly_rets):.2f}%")

    # Distribution
    bins = [(-100, -20), (-20, -10), (-10, -5), (-5, 0), (0, 5), (5, 10), (10, 20), (20, 50), (50, 100), (100, 500)]
    print(f"\n{'Range':>15} {'Count':>8} {'Pct':>8}")
    print("-" * 35)
    for low, high in bins:
        count = sum(1 for r in monthly_rets if low < r <= high)
        if count > 0:
            print(f"{low:>6}% ~ {high:>4}% {count:>8} {count/len(monthly_rets)*100:>7.1f}%")

    # =========================================================================
    # 4. PARAMETER GRID SEARCH
    # =========================================================================
    print("\n" + "=" * 90)
    print("4. PARAMETER GRID SEARCH (EMA x BTC_MA x NOISE)")
    print("=" * 90)

    ema_range = [3, 5, 7, 10]
    btc_ma_range = [15, 20, 25, 30]
    noise_range = [0.4, 0.5, 0.6]

    grid_results = []
    for ema in ema_range:
        for btc_ma in btc_ma_range:
            for noise in noise_range:
                r = backtest_v1_1_detailed(symbols, ema_span=ema, btc_ma=btc_ma, noise_ratio=noise)
                grid_results.append({
                    'ema': ema, 'btc_ma': btc_ma, 'noise': noise,
                    'cagr': r['cagr'], 'mdd': r['mdd'], 'sharpe': r['sharpe']
                })

    grid_df = pd.DataFrame(grid_results).sort_values('sharpe', ascending=False)

    print(f"\nTop 10 parameter combinations (by Sharpe):")
    print(f"{'EMA':>5} {'BTC_MA':>8} {'NOISE':>7} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10}")
    print("-" * 55)
    for i, row in grid_df.head(10).iterrows():
        marker = " ← default" if row['ema'] == 5 and row['btc_ma'] == 20 and row['noise'] == 0.5 else ""
        print(f"{row['ema']:>5} {row['btc_ma']:>8} {row['noise']:>7.1f} {row['cagr']:>9.1f}% {row['mdd']:>9.1f}% {row['sharpe']:>10.2f}{marker}")

    # Default rank
    default_sharpe = grid_df[(grid_df['ema'] == 5) & (grid_df['btc_ma'] == 20) & (grid_df['noise'] == 0.5)]['sharpe'].values[0]
    default_rank = (grid_df['sharpe'] > default_sharpe).sum() + 1
    print(f"\nDefault (5, 20, 0.5) rank: {default_rank}/{len(grid_df)}")
    print(f"Sharpe range: {grid_df['sharpe'].min():.2f} ~ {grid_df['sharpe'].max():.2f}")
    print(f"Sharpe std: {grid_df['sharpe'].std():.3f}")

    # =========================================================================
    # 5. FEE & SLIPPAGE SENSITIVITY
    # =========================================================================
    print("\n" + "=" * 90)
    print("5. FEE & SLIPPAGE SENSITIVITY")
    print("=" * 90)

    fee_slip_combos = [
        (0.0, 0.0, "No costs"),
        (0.0005, 0.0005, "Default (0.05%/0.05%)"),
        (0.001, 0.001, "High (0.1%/0.1%)"),
        (0.002, 0.002, "Very high (0.2%/0.2%)"),
    ]

    print(f"\n{'Scenario':<25} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10}")
    print("-" * 60)
    for fee, slip, label in fee_slip_combos:
        r = backtest_v1_1_detailed(symbols, fee=fee, slippage=slip)
        print(f"{label:<25} {r['cagr']:>9.1f}% {r['mdd']:>9.1f}% {r['sharpe']:>10.2f}")

    # =========================================================================
    # 6. MULTIPLE TRAIN/TEST SPLITS
    # =========================================================================
    print("\n" + "=" * 90)
    print("6. MULTIPLE TRAIN/TEST SPLITS")
    print("=" * 90)

    splits = [
        ("2017-2019 / 2020-2025", "2017-01-01", "2019-12-31", "2020-01-01", "2025-12-31"),
        ("2017-2020 / 2021-2025", "2017-01-01", "2020-12-31", "2021-01-01", "2025-12-31"),
        ("2017-2021 / 2022-2025", "2017-01-01", "2021-12-31", "2022-01-01", "2025-12-31"),
        ("2017-2022 / 2023-2025", "2017-01-01", "2022-12-31", "2023-01-01", "2025-12-31"),
    ]

    print(f"\n{'Split':<25} {'Train Sharpe':>14} {'Test Sharpe':>14} {'Degradation':>14}")
    print("-" * 72)

    for label, ts, te, vs, ve in splits:
        train_r = backtest_v1_1_detailed(symbols, start=ts, end=te)
        test_r = backtest_v1_1_detailed(symbols, start=vs, end=ve)
        degrad = (train_r['sharpe'] - test_r['sharpe']) / train_r['sharpe'] * 100 if train_r['sharpe'] > 0 else 0
        status = "✓" if degrad < 50 else "✗"
        print(f"{label:<25} {train_r['sharpe']:>14.2f} {test_r['sharpe']:>14.2f} {degrad:>13.1f}% {status}")

    # =========================================================================
    # 7. PORTFOLIO COMBINATIONS (Top 5)
    # =========================================================================
    print("\n" + "=" * 90)
    print("7. PORTFOLIO COMBINATIONS COMPARISON")
    print("=" * 90)

    portfolio_results = []
    for size in [1, 2, 3]:
        for combo in combinations(ALL_SYMBOLS, size):
            r = backtest_v1_1_detailed(list(combo))
            portfolio_results.append({
                'symbols': '+'.join(combo),
                'size': size,
                'cagr': r['cagr'],
                'mdd': r['mdd'],
                'sharpe': r['sharpe'],
            })

    port_df = pd.DataFrame(portfolio_results).sort_values('sharpe', ascending=False)

    print(f"\nTop 10 portfolios (by Sharpe):")
    print(f"{'Rank':<6} {'Portfolio':<20} {'CAGR':>10} {'MDD':>10} {'Sharpe':>10}")
    print("-" * 62)
    for i, (_, row) in enumerate(port_df.head(10).iterrows(), 1):
        marker = " ← selected" if row['symbols'] == 'BTC+ETH' else ""
        print(f"{i:<6} {row['symbols']:<20} {row['cagr']:>9.1f}% {row['mdd']:>9.1f}% {row['sharpe']:>10.2f}{marker}")

    btc_eth_rank = (port_df['sharpe'] > port_df[port_df['symbols'] == 'BTC+ETH']['sharpe'].values[0]).sum() + 1
    print(f"\nBTC+ETH rank: {btc_eth_rank}/{len(port_df)}")

    # =========================================================================
    # 8. ROLLING SHARPE (252-day)
    # =========================================================================
    print("\n" + "=" * 90)
    print("8. ROLLING SHARPE ANALYSIS (252-day)")
    print("=" * 90)

    eq = full['equity_curve']['equity']
    ret = eq.pct_change().dropna()
    rolling_sharpe = (ret.rolling(252).mean() / ret.rolling(252).std()) * np.sqrt(365)
    rolling_sharpe = rolling_sharpe.dropna()

    print(f"\nRolling Sharpe statistics:")
    print(f"Min: {rolling_sharpe.min():.2f}")
    print(f"Max: {rolling_sharpe.max():.2f}")
    print(f"Mean: {rolling_sharpe.mean():.2f}")
    print(f"Std: {rolling_sharpe.std():.2f}")
    print(f"% below 1.0: {(rolling_sharpe < 1.0).sum() / len(rolling_sharpe) * 100:.1f}%")
    print(f"% below 0.5: {(rolling_sharpe < 0.5).sum() / len(rolling_sharpe) * 100:.1f}%")

    # By year
    rolling_sharpe_df = rolling_sharpe.to_frame('sharpe')
    rolling_sharpe_df['year'] = rolling_sharpe_df.index.year
    yearly_rolling = rolling_sharpe_df.groupby('year')['sharpe'].mean()

    print(f"\n{'Year':<8} {'Avg Rolling Sharpe':>20}")
    print("-" * 30)
    for year, sharpe in yearly_rolling.items():
        status = "✓" if sharpe > 1.0 else "⚠" if sharpe > 0.5 else "✗"
        print(f"{year:<8} {sharpe:>20.2f} {status}")

    # =========================================================================
    # 9. BUY & HOLD COMPARISON
    # =========================================================================
    print("\n" + "=" * 90)
    print("9. VS BUY & HOLD COMPARISON")
    print("=" * 90)

    btc_data = load_data("BTC")
    eth_data = load_data("ETH")

    # Align dates
    start_date = full['equity_curve'].index[0]
    end_date = full['equity_curve'].index[-1]

    btc_start = btc_data.loc[start_date:end_date].iloc[0]['close']
    btc_end = btc_data.loc[start_date:end_date].iloc[-1]['close']
    btc_ret = (btc_end / btc_start - 1) * 100

    eth_start = eth_data.loc[start_date:end_date].iloc[0]['close']
    eth_end = eth_data.loc[start_date:end_date].iloc[-1]['close']
    eth_ret = (eth_end / eth_start - 1) * 100

    bh_ret = (btc_ret + eth_ret) / 2  # 50/50

    days = (end_date - start_date).days
    years = days / 365.25
    v1_1_total_ret = (full['final_equity'] / INITIAL_CAPITAL - 1) * 100

    print(f"\nPeriod: {start_date.date()} ~ {end_date.date()} ({years:.1f} years)")
    print(f"\n{'Strategy':<20} {'Total Return':>15} {'CAGR':>10}")
    print("-" * 50)
    print(f"{'V1.1':<20} {v1_1_total_ret:>14.0f}% {full['cagr']:>9.1f}%")
    print(f"{'BTC B&H':<20} {btc_ret:>14.0f}% {(pow(btc_end/btc_start, 1/years)-1)*100:>9.1f}%")
    print(f"{'ETH B&H':<20} {eth_ret:>14.0f}% {(pow(eth_end/eth_start, 1/years)-1)*100:>9.1f}%")
    print(f"{'50/50 B&H':<20} {bh_ret:>14.0f}% {(pow(1+bh_ret/100, 1/years)-1)*100:>9.1f}%")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 90)
    print("VALIDATION SUMMARY")
    print("=" * 90)

    checks = [
        ("Trade win rate > 50%", win_rate > 50 if trades else False),
        ("Profit factor > 1.5", profit_factor > 1.5 if trades else False),
        ("Default params in top 25%", default_rank <= len(grid_df) * 0.25),
        ("BTC+ETH in top 3 portfolios", btc_eth_rank <= 3),
        ("Rolling Sharpe mean > 1.5", rolling_sharpe.mean() > 1.5),
        ("All train/test degradation < 50%", all(
            (backtest_v1_1_detailed(symbols, start=ts, end=te)['sharpe'] -
             backtest_v1_1_detailed(symbols, start=vs, end=ve)['sharpe']) /
            backtest_v1_1_detailed(symbols, start=ts, end=te)['sharpe'] * 100 < 50
            for _, ts, te, vs, ve in splits
        )),
        ("Beats 50/50 B&H CAGR", full['cagr'] > (pow(1+bh_ret/100, 1/years)-1)*100),
    ]

    print()
    passed = 0
    for check, result in checks:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {check}: {status}")
        if result:
            passed += 1

    print(f"\nResult: {passed}/{len(checks)} checks passed")

    if passed >= len(checks) - 1:
        print("\n✓ V1.1 STRATEGY ROBUST - PRODUCTION READY")
    elif passed >= len(checks) - 2:
        print("\n⚠ V1.1 MOSTLY ROBUST - MINOR CONCERNS")
    else:
        print("\n✗ V1.1 NEEDS REVIEW")


if __name__ == "__main__":
    main()
