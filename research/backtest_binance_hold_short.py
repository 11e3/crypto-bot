#!/usr/bin/env python3
"""Binance VBO with Hold-Short Strategy

롱/숏 청산 조건 비대칭:
- 강세장 롱: 기존 VBO (MA5 or BTC MA20 청산)
- 약세장 숏: 길게 홀드 (BTC MA20만 청산, MA5 무시)

계단식 진동 하락에 대응하는 전략

Usage:
    python backtest_binance_hold_short.py
    python backtest_binance_hold_short.py --start 2022-01-01 --end 2024-12-31
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


# =============================================================================
# Data Loading
# =============================================================================
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

    df['prev_btc_close'] = btc_aligned['close'].shift(1)
    df['prev_btc_ma'] = btc_aligned['btc_ma'].shift(1)

    # Market regime (bull/bear)
    df['market_regime'] = np.where(df['prev_btc_close'] > df['prev_btc_ma'], 'BULL', 'BEAR')

    # VBO targets (both directions)
    df['target_long'] = df['open'] + (df['prev_high'] - df['prev_low']) * NOISE_RATIO
    df['target_short'] = df['open'] - (df['prev_high'] - df['prev_low']) * NOISE_RATIO

    return df


# =============================================================================
# Backtest
# =============================================================================
def backtest_hold_short(symbol: str, start: str | None = None, end: str | None = None) -> tuple[dict, pd.DataFrame]:
    """Backtest Hold-Short VBO strategy."""
    df = load_data(symbol)
    btc_df = load_data("BTC")

    df = filter_date_range(df, start, end)
    btc_df = filter_date_range(btc_df, start, end)

    df = calculate_indicators(df, btc_df)

    cash = 1_000_000
    position = 0.0
    position_entry_price = 0.0
    position_type = None
    trades = []
    equity_curve = []

    for date, row in df.iterrows():
        if pd.isna(row['prev_ma5']) or pd.isna(row['prev_btc_ma']):
            equity = cash + position * row['close']
            equity_curve.append({'date': date, 'equity': equity})
            continue

        regime = row['market_regime']

        # === SELL/COVER LOGIC ===
        if position != 0:
            sell_signal = False
            sell_reason = ""

            if position_type == 'LONG':
                # Long exit: prev_close < prev_ma5 OR prev_btc < prev_btc_ma (기존 VBO)
                if row['prev_close'] < row['prev_ma5']:
                    sell_signal = True
                    sell_reason = "Long Exit (MA5)"
                elif row['prev_btc_close'] < row['prev_btc_ma']:
                    sell_signal = True
                    sell_reason = "Long Exit (BTC MA20)"

            else:  # SHORT
                # Short cover: prev_btc > prev_btc_ma ONLY (MA5 무시!)
                # 약세장 끝날 때까지 홀드
                if row['prev_btc_close'] > row['prev_btc_ma']:
                    sell_signal = True
                    sell_reason = "Short Cover (BTC MA20)"

            if sell_signal:
                if position_type == 'LONG':
                    exit_price = row['open'] * (1 - SLIPPAGE)
                    exit_value = position * exit_price
                    exit_fee = exit_value * FEE
                    cash += exit_value - exit_fee
                    profit = exit_value - position * position_entry_price - exit_fee
                    profit_pct = (exit_price / position_entry_price - 1) * 100
                else:  # SHORT
                    exit_price = row['open'] * (1 + SLIPPAGE)
                    exit_notional = abs(position) * exit_price
                    exit_fee = exit_notional * FEE
                    entry_notional = abs(position) * position_entry_price
                    profit = entry_notional - exit_notional - exit_fee
                    cash += profit
                    profit_pct = (position_entry_price / exit_price - 1) * 100

                trades.append({
                    'entry_date': date,
                    'exit_date': date,
                    'type': position_type,
                    'entry_price': position_entry_price,
                    'exit_price': exit_price,
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'reason': sell_reason
                })

                position = 0.0
                position_entry_price = 0.0
                position_type = None

        # === BUY/SHORT LOGIC ===
        if position == 0:
            buy_signal = False

            if regime == 'BULL':
                # Long entry: high >= target_long AND prev_close > prev_ma5
                if (row['high'] >= row['target_long'] and
                    row['prev_close'] > row['prev_ma5'] and
                    row['prev_btc_close'] > row['prev_btc_ma']):
                    buy_signal = True
                    position_type = 'LONG'
                    entry_price = row['target_long'] * (1 + SLIPPAGE)

            else:  # BEAR
                # Short entry: low <= target_short AND prev_close < prev_ma5
                if (row['low'] <= row['target_short'] and
                    row['prev_close'] < row['prev_ma5'] and
                    row['prev_btc_close'] < row['prev_btc_ma']):
                    buy_signal = True
                    position_type = 'SHORT'
                    entry_price = row['target_short'] * (1 - SLIPPAGE)

            if buy_signal:
                entry_value = cash
                entry_fee = entry_value * FEE

                if position_type == 'LONG':
                    position = (entry_value - entry_fee) / entry_price
                    position_entry_price = entry_price
                    cash = 0.0
                else:  # SHORT
                    position = -(entry_value - entry_fee) / entry_price
                    position_entry_price = entry_price

        # Calculate equity (mark-to-market)
        if position > 0:  # Long
            equity = cash + position * row['close']
        elif position < 0:  # Short
            notional_entry = abs(position) * position_entry_price
            notional_current = abs(position) * row['close']
            pnl = notional_entry - notional_current
            equity = cash + pnl
        else:  # No position
            equity = cash

        equity_curve.append({'date': date, 'equity': equity})

    # Close final position
    if position != 0:
        final_price = df.iloc[-1]['close']
        if position > 0:  # Long
            final_value = position * final_price * (1 - SLIPPAGE)
            final_fee = final_value * FEE
            cash += final_value - final_fee
        else:  # Short
            exit_notional = abs(position) * final_price * (1 + SLIPPAGE)
            exit_fee = exit_notional * FEE
            entry_notional = abs(position) * position_entry_price
            pnl = entry_notional - exit_notional - exit_fee
            cash += pnl

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

    # Position type stats
    long_trades = len([t for t in trades if t['type'] == 'LONG'])
    short_trades = len([t for t in trades if t['type'] == 'SHORT'])

    return {
        'symbol': symbol,
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'long_trades': long_trades,
        'short_trades': short_trades
    }, equity_df


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description='Backtest Hold-Short VBO')
    parser.add_argument('--start', type=str, help='Start date')
    parser.add_argument('--end', type=str, help='End date')
    args = parser.parse_args()

    symbols = ['BTC', 'ETH', 'XRP', 'TRX', 'ADA']

    print("=" * 100)
    print("HOLD-SHORT VBO STRATEGY")
    print("=" * 100)
    print(f"\nBull Market (BTC > MA{BTC_MA}): VBO LONG (MA5 or BTC청산)")
    print(f"Bear Market (BTC < MA{BTC_MA}): VBO SHORT (BTC청산만, MA5무시)")
    if args.start or args.end:
        print(f"Period: {args.start or 'inception'} ~ {args.end or 'latest'}")
    print()

    results = []
    for symbol in symbols:
        print(f"Testing {symbol}...", end=' ', flush=True)
        try:
            metrics, _ = backtest_hold_short(symbol, args.start, args.end)
            results.append(metrics)
            print(f"CAGR: {metrics['cagr']:>7.2f}%, Trades: {metrics['total_trades']} (Long: {metrics['long_trades']}, Short: {metrics['short_trades']})")
        except Exception as e:
            print(f"Error: {e}")

    print("\n" + "=" * 100)
    print("RESULTS")
    print("=" * 100)
    print(f"\n{'Symbol':<10} {'CAGR':<12} {'MDD':<12} {'Sharpe':<12} {'Trades':<10} {'Win Rate':<12} {'Long/Short':<12}")
    print("-" * 100)

    for r in results:
        print(f"{r['symbol']:<10} {r['cagr']:>10.2f}%  {r['mdd']:>10.2f}%  {r['sharpe']:>10.2f}  "
              f"{r['total_trades']:>8}  {r['win_rate']:>10.2f}%  {r['long_trades']}/{r['short_trades']}")

    print("-" * 100)

    if results:
        best = max(results, key=lambda x: x['sharpe'])
        print(f"\nBest: {best['symbol']} (Sharpe: {best['sharpe']:.2f}, CAGR: {best['cagr']:.2f}%)")
    print()


if __name__ == "__main__":
    main()
