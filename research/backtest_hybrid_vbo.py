#!/usr/bin/env python3
"""Hybrid VBO Strategy (VBO + Inverse VBO)

시장 상황에 따라 전략 전환:
- 강세장 (BTC > MA20): VBO (추세추종)
- 약세장 (BTC < MA20): Inverse VBO (평균회귀)

전천후 전략:
- 모든 시장 환경에서 수익 창출
- 자동 적응형

Usage:
    python backtest_hybrid_vbo.py
    python backtest_hybrid_vbo.py --start 2022-01-01 --end 2024-12-31
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


# =============================================================================
# Configuration
# =============================================================================
FEE = 0.0005
SLIPPAGE = 0.0005

MA_SHORT = 5
BTC_MA = 20
NOISE_RATIO = 0.5

# Inverse VBO params
RSI_PERIOD = 14
RSI_OVERSOLD = 35


# =============================================================================
# Indicators
# =============================================================================
def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def load_data(symbol: str, data_dir: str = "data") -> pd.DataFrame:
    """Load OHLCV data."""
    filepath = Path(data_dir) / f"{symbol}.csv"
    if not filepath.exists():
        raise FileNotFoundError(f"No data for {symbol}: {filepath}")

    df = pd.read_csv(filepath, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    df = df.sort_index()
    return df


def filter_date_range(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    """Filter by date range."""
    if start:
        df = df[df.index >= pd.to_datetime(start)]
    if end:
        df = df[df.index <= pd.to_datetime(end)]
    return df


def calculate_indicators(df: pd.DataFrame, btc_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all indicators."""
    df = df.copy()
    btc_df = btc_df.copy()

    # RSI
    df['rsi'] = calculate_rsi(df['close'], RSI_PERIOD)

    # MA
    df['ma5'] = df['close'].rolling(window=MA_SHORT).mean()

    # BTC
    btc_aligned = btc_df.reindex(df.index, method='ffill')
    btc_aligned['btc_ma'] = btc_aligned['close'].rolling(window=BTC_MA).mean()

    # Previous values
    df['prev_high'] = df['high'].shift(1)
    df['prev_low'] = df['low'].shift(1)
    df['prev_close'] = df['close'].shift(1)
    df['prev_ma5'] = df['ma5'].shift(1)
    df['prev_rsi'] = df['rsi'].shift(1)

    df['prev_btc_close'] = btc_aligned['close'].shift(1)
    df['prev_btc_ma'] = btc_aligned['btc_ma'].shift(1)

    # Market regime (bull/bear)
    df['market_regime'] = np.where(df['prev_btc_close'] > df['prev_btc_ma'], 'BULL', 'BEAR')

    # VBO target
    df['target_price'] = df['open'] + (df['prev_high'] - df['prev_low']) * NOISE_RATIO

    return df


# =============================================================================
# Backtest
# =============================================================================
def backtest_hybrid_vbo(symbol: str, start: str | None = None, end: str | None = None) -> tuple[dict, pd.DataFrame]:
    """Backtest Hybrid VBO strategy."""
    df = load_data(symbol)
    btc_df = load_data("BTC")

    df = filter_date_range(df, start, end)
    btc_df = filter_date_range(btc_df, start, end)

    df = calculate_indicators(df, btc_df)

    cash = 1_000_000
    position = 0.0
    position_entry_price = 0.0
    entry_regime = None
    trades = []
    equity_curve = []

    for date, row in df.iterrows():
        if pd.isna(row['prev_ma5']) or pd.isna(row['prev_btc_ma']):
            equity = cash + position * row['close']
            equity_curve.append({'date': date, 'equity': equity})
            continue

        # === SELL ===
        if position > 0:
            sell_signal = False
            sell_reason = ""

            if entry_regime == 'BULL':
                # VBO exit: 전일종가 < 전일MA5 OR 전일BTC < 전일BTC_MA20
                if row['prev_close'] < row['prev_ma5']:
                    sell_signal = True
                    sell_reason = "VBO Exit (MA5)"
                elif row['prev_btc_close'] < row['prev_btc_ma']:
                    sell_signal = True
                    sell_reason = "VBO Exit (BTC MA20)"

            else:  # BEAR
                # Inverse exit: 전일종가 > 전일MA5 OR 전일BTC > 전일BTC_MA20
                if row['prev_close'] > row['prev_ma5']:
                    sell_signal = True
                    sell_reason = "Inverse Exit (MA5)"
                elif row['prev_btc_close'] > row['prev_btc_ma']:
                    sell_signal = True
                    sell_reason = "Inverse Exit (BTC MA20)"

            if sell_signal:
                sell_price = row['open'] * (1 - SLIPPAGE)
                sell_value = position * sell_price
                sell_fee = sell_value * FEE
                cash += sell_value - sell_fee

                profit = sell_value - position * position_entry_price
                profit_pct = (sell_price / position_entry_price - 1) * 100
                trades.append({
                    'entry_date': date,
                    'exit_date': date,
                    'entry_price': position_entry_price,
                    'exit_price': sell_price,
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'regime': entry_regime,
                    'reason': sell_reason
                })

                position = 0.0
                position_entry_price = 0.0
                entry_regime = None

        # === BUY ===
        if position == 0:
            buy_signal = False
            regime = row['market_regime']

            if regime == 'BULL':
                # VBO Logic (강세장 추세추종)
                if (row['high'] >= row['target_price'] and
                    row['prev_close'] > row['prev_ma5'] and
                    row['prev_btc_close'] > row['prev_btc_ma']):
                    buy_signal = True
                    entry_regime = 'BULL'

            else:  # BEAR
                # Inverse VBO Logic (약세장 평균회귀)
                if (row['high'] < row['target_price'] and
                    row['prev_rsi'] < RSI_OVERSOLD and
                    row['prev_close'] < row['prev_ma5'] and
                    row['prev_btc_close'] < row['prev_btc_ma']):
                    buy_signal = True
                    entry_regime = 'BEAR'

            if buy_signal:
                # Entry price depends on regime
                if entry_regime == 'BULL':
                    # VBO: target breakout → enter at target
                    buy_price = row['target_price'] * (1 + SLIPPAGE)
                else:  # BEAR
                    # Inverse: failed breakout → enter at open
                    buy_price = row['open'] * (1 + SLIPPAGE)

                buy_value = cash
                buy_fee = buy_value * FEE
                position = (buy_value - buy_fee) / buy_price
                position_entry_price = buy_price
                cash = 0.0

        equity = cash + position * row['close']
        equity_curve.append({'date': date, 'equity': equity})

    # Close final position
    if position > 0:
        final_price = df.iloc[-1]['close']
        final_value = position * final_price * (1 - SLIPPAGE)
        final_fee = final_value * FEE
        cash += final_value - final_fee

    equity_df = pd.DataFrame(equity_curve)
    equity_df.set_index('date', inplace=True)

    # Metrics
    final_equity = equity_df['equity'].iloc[-1]
    initial_equity = equity_df['equity'].iloc[0]

    days = (equity_df.index[-1] - equity_df.index[0]).days
    years = days / 365.25
    cagr = (pow(final_equity / initial_equity, 1 / years) - 1) * 100 if years > 0 else 0

    running_max = equity_df['equity'].expanding().max()
    drawdown = (equity_df['equity'] / running_max - 1) * 100
    mdd = drawdown.min()

    equity_df['daily_return'] = equity_df['equity'].pct_change()
    daily_returns = equity_df['daily_return'].dropna()
    sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365) if len(daily_returns) > 0 and daily_returns.std() > 0 else 0

    total_trades = len(trades)
    winning_trades = len([t for t in trades if t['profit'] > 0])
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

    # Regime stats
    bull_trades = len([t for t in trades if t['regime'] == 'BULL'])
    bear_trades = len([t for t in trades if t['regime'] == 'BEAR'])

    return {
        'symbol': symbol,
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'bull_trades': bull_trades,
        'bear_trades': bear_trades
    }, equity_df


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description='Backtest Hybrid VBO')
    parser.add_argument('--start', type=str, help='Start date')
    parser.add_argument('--end', type=str, help='End date')
    args = parser.parse_args()

    symbols = ['BTC', 'ETH', 'XRP', 'TRX', 'ADA']

    print("=" * 100)
    print("HYBRID VBO STRATEGY (전천후)")
    print("=" * 100)
    print(f"\nBull Market (BTC > MA{BTC_MA}): VBO (추세추종)")
    print(f"Bear Market (BTC < MA{BTC_MA}): Inverse VBO (평균회귀)")
    if args.start or args.end:
        print(f"Period: {args.start or 'inception'} ~ {args.end or 'latest'}")
    print()

    results = []
    for symbol in symbols:
        print(f"Testing {symbol}...", end=' ', flush=True)
        try:
            metrics, _ = backtest_hybrid_vbo(symbol, args.start, args.end)
            results.append(metrics)
            print(f"CAGR: {metrics['cagr']:>7.2f}%, Trades: {metrics['total_trades']} (Bull: {metrics['bull_trades']}, Bear: {metrics['bear_trades']})")
        except Exception as e:
            print(f"Error: {e}")

    print("\n" + "=" * 100)
    print("RESULTS")
    print("=" * 100)
    print(f"\n{'Symbol':<10} {'CAGR':<12} {'MDD':<12} {'Sharpe':<12} {'Trades':<10} {'Win Rate':<12} {'Bull/Bear':<12}")
    print("-" * 100)

    for r in results:
        print(f"{r['symbol']:<10} {r['cagr']:>10.2f}%  {r['mdd']:>10.2f}%  {r['sharpe']:>10.2f}  "
              f"{r['total_trades']:>8}  {r['win_rate']:>10.2f}%  {r['bull_trades']}/{r['bear_trades']}")

    print("-" * 100)

    if results:
        best = max(results, key=lambda x: x['sharpe'])
        print(f"\nBest: {best['symbol']} (Sharpe: {best['sharpe']:.2f}, CAGR: {best['cagr']:.2f}%)")
    print()


if __name__ == "__main__":
    main()
