#!/usr/bin/env python3
"""Inverse VBO Strategy - Fade Breakouts (약세장 특화)

VBO의 역발상 전략:
- VBO: 돌파 → 매수 (추세추종)
- Inverse: 돌파 실패 → 매수 (평균회귀)

약세장/횡보장 최적화:
- 가짜 돌파 후 하락 시 매수
- 빠른 반등 익절

Usage:
    python backtest_inverse_vbo.py
    python backtest_inverse_vbo.py --start 2022-01-01 --end 2024-12-31
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

# Inverse VBO Parameters
MA_SHORT = 5
BTC_MA = 20
NOISE_RATIO = 0.5

# Entry: 돌파 실패 시
RSI_PERIOD = 14
RSI_OVERSOLD = 35  # RSI < 35 (추가 필터)

# Exit
PROFIT_TARGET = 0.03  # 3% 익절
STOP_LOSS = -0.07     # -7% 손절


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
    """Calculate indicators for Inverse VBO."""
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

    # VBO target (for inverse logic)
    df['target_price'] = df['open'] + (df['prev_high'] - df['prev_low']) * NOISE_RATIO

    return df


# =============================================================================
# Backtest
# =============================================================================
def backtest_inverse_vbo(symbol: str, start: str | None = None, end: str | None = None) -> tuple[dict, pd.DataFrame]:
    """Backtest Inverse VBO strategy."""
    df = load_data(symbol)
    btc_df = load_data("BTC")

    df = filter_date_range(df, start, end)
    btc_df = filter_date_range(btc_df, start, end)

    df = calculate_indicators(df, btc_df)

    cash = 1_000_000
    position = 0.0
    position_entry_price = 0.0
    trades = []
    equity_curve = []

    for date, row in df.iterrows():
        if pd.isna(row['prev_ma5']) or pd.isna(row['prev_btc_ma']):
            equity = cash + position * row['close']
            equity_curve.append({'date': date, 'equity': equity})
            continue

        # === SELL ===
        if position > 0:
            current_return = (row['close'] / position_entry_price - 1)

            sell_signal = False
            sell_reason = ""

            # Profit target
            if current_return >= PROFIT_TARGET:
                sell_signal = True
                sell_reason = "Profit Target"

            # Price recovered above MA
            elif row['prev_close'] > row['prev_ma5']:
                sell_signal = True
                sell_reason = "MA Recovery"

            # Stop loss
            elif current_return <= STOP_LOSS:
                sell_signal = True
                sell_reason = "Stop Loss"

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
                    'reason': sell_reason
                })

                position = 0.0
                position_entry_price = 0.0

        # === BUY (INVERSE LOGIC) ===
        if position == 0:
            buy_signal = False

            # Inverse VBO: 돌파 실패 후 하락 시 매수
            # 1. 가격이 VBO 타겟 이하 (돌파 실패)
            # 2. RSI 과매도 (추가 하락)
            # 3. BTC 약세 확인 (BTC < MA20)
            if (row['high'] < row['target_price'] and  # 돌파 실패
                row['prev_rsi'] < RSI_OVERSOLD and      # 과매도
                row['prev_close'] < row['prev_ma5'] and # 약세 확인
                row['prev_btc_close'] < row['prev_btc_ma']):  # BTC 약세
                buy_signal = True

            if buy_signal:
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

    return {
        'symbol': symbol,
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
        'total_trades': total_trades,
        'win_rate': win_rate
    }, equity_df


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description='Backtest Inverse VBO strategy')
    parser.add_argument('--start', type=str, help='Start date')
    parser.add_argument('--end', type=str, help='End date')
    args = parser.parse_args()

    symbols = ['BTC', 'ETH', 'XRP', 'TRX', 'ADA']

    print("=" * 100)
    print("INVERSE VBO STRATEGY (약세장 특화)")
    print("=" * 100)
    print(f"\nEntry: High < Target AND RSI < {RSI_OVERSOLD} AND Price < MA5 AND BTC < MA{BTC_MA}")
    print(f"Exit: Profit {PROFIT_TARGET*100}% OR Price > MA5 OR Loss {STOP_LOSS*100}%")
    if args.start or args.end:
        print(f"Period: {args.start or 'inception'} ~ {args.end or 'latest'}")
    print()

    results = []
    for symbol in symbols:
        print(f"Testing {symbol}...", end=' ', flush=True)
        try:
            metrics, _ = backtest_inverse_vbo(symbol, args.start, args.end)
            results.append(metrics)
            print(f"CAGR: {metrics['cagr']:>7.2f}%, Trades: {metrics['total_trades']}")
        except Exception as e:
            print(f"Error: {e}")

    print("\n" + "=" * 100)
    print("RESULTS")
    print("=" * 100)
    print(f"\n{'Symbol':<10} {'CAGR':<12} {'MDD':<12} {'Sharpe':<12} {'Trades':<10} {'Win Rate':<12}")
    print("-" * 100)

    for r in results:
        print(f"{r['symbol']:<10} {r['cagr']:>10.2f}%  {r['mdd']:>10.2f}%  {r['sharpe']:>10.2f}  {r['total_trades']:>8}  {r['win_rate']:>10.2f}%")

    print("-" * 100)

    if results:
        best = max(results, key=lambda x: x['sharpe'])
        print(f"\nBest: {best['symbol']} (Sharpe: {best['sharpe']:.2f}, CAGR: {best['cagr']:.2f}%)")
    print()


if __name__ == "__main__":
    main()
