#!/usr/bin/env python3
"""Analyze Bidirectional VBO performance by position type."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd


def analyze_trades(symbol: str, start: str = None, end: str = None):
    """Analyze long vs short performance."""
    # Run backtest
    from backtest_binance_bidirectional_vbo import (
        FEE,
        SLIPPAGE,
        calculate_indicators,
        filter_date_range,
        load_data,
    )

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

    for date, row in df.iterrows():
        if pd.isna(row['prev_ma5']) or pd.isna(row['prev_btc_ma']):
            continue

        regime = row['market_regime']

        # SELL/COVER
        if position != 0:
            sell_signal = False

            if position_type == 'LONG':
                if row['prev_close'] < row['prev_ma5'] or row['prev_btc_close'] < row['prev_btc_ma']:
                    sell_signal = True
            else:  # SHORT
                if row['prev_close'] > row['prev_ma5'] or row['prev_btc_close'] > row['prev_btc_ma']:
                    sell_signal = True

            if sell_signal:
                if position_type == 'LONG':
                    exit_price = row['open'] * (1 - SLIPPAGE)
                    exit_value = position * exit_price
                    exit_fee = exit_value * FEE
                    profit = exit_value - position * position_entry_price - exit_fee
                    profit_pct = (exit_price / position_entry_price - 1) * 100
                else:  # SHORT
                    exit_price = row['open'] * (1 + SLIPPAGE)
                    exit_notional = abs(position) * exit_price
                    exit_fee = exit_notional * FEE
                    entry_notional = abs(position) * position_entry_price
                    profit = entry_notional - exit_notional - exit_fee
                    profit_pct = (position_entry_price / exit_price - 1) * 100

                trades.append({
                    'entry_date': date,
                    'exit_date': date,
                    'type': position_type,
                    'entry_price': position_entry_price,
                    'exit_price': exit_price,
                    'profit': profit,
                    'profit_pct': profit_pct
                })

                position = 0.0
                position_entry_price = 0.0
                position_type = None

        # BUY/SHORT
        if position == 0:
            buy_signal = False

            if regime == 'BULL':
                if (row['high'] >= row['target_long'] and
                    row['prev_close'] > row['prev_ma5'] and
                    row['prev_btc_close'] > row['prev_btc_ma']):
                    buy_signal = True
                    position_type = 'LONG'
                    entry_price = row['target_long'] * (1 + SLIPPAGE)
            else:  # BEAR
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
                else:
                    position = -(entry_value - entry_fee) / entry_price

                position_entry_price = entry_price

    # Analyze trades
    df_trades = pd.DataFrame(trades)

    if len(df_trades) == 0:
        print(f"\n{symbol}: No trades")
        return

    long_trades = df_trades[df_trades['type'] == 'LONG']
    short_trades = df_trades[df_trades['type'] == 'SHORT']

    print(f"\n{'='*80}")
    print(f"{symbol} - Trade Analysis")
    print(f"{'='*80}")

    print(f"\n{'Type':<10} {'Count':<10} {'Win Rate':<12} {'Avg Profit %':<15} {'Total Profit':<15}")
    print("-" * 80)

    for name, trades_df in [('LONG', long_trades), ('SHORT', short_trades)]:
        if len(trades_df) == 0:
            continue

        count = len(trades_df)
        wins = len(trades_df[trades_df['profit'] > 0])
        win_rate = wins / count * 100
        avg_profit_pct = trades_df['profit_pct'].mean()
        total_profit = trades_df['profit'].sum()

        print(f"{name:<10} {count:<10} {win_rate:>10.1f}%  {avg_profit_pct:>13.2f}%  {total_profit:>13,.0f}")

    print("-" * 80)
    total_count = len(df_trades)
    total_wins = len(df_trades[df_trades['profit'] > 0])
    total_win_rate = total_wins / total_count * 100
    total_avg_profit = df_trades['profit_pct'].mean()
    total_profit_sum = df_trades['profit'].sum()
    print(f"{'TOTAL':<10} {total_count:<10} {total_win_rate:>10.1f}%  {total_avg_profit:>13.2f}%  {total_profit_sum:>13,.0f}")


if __name__ == "__main__":
    symbols = ['BTC', 'ETH', 'XRP', 'TRX', 'ADA']

    print("\n" + "="*80)
    print("FULL PERIOD ANALYSIS")
    print("="*80)
    for symbol in symbols:
        analyze_trades(symbol)

    print("\n\n" + "="*80)
    print("2022-2024 ANALYSIS")
    print("="*80)
    for symbol in symbols:
        analyze_trades(symbol, '2022-01-01', '2024-12-31')
