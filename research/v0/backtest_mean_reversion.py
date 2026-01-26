#!/usr/bin/env python3
"""Mean Reversion Strategy Backtest for Upbit

약세장/횡보장 최적화 평균회귀 전략:
- RSI 과매도 구간에서 매수 (역발상)
- 볼린저밴드 하단 돌파 시 매수
- 빠른 익절 (3-5% 목표)

VBO와 비교:
- VBO: 추세추종 (강세장 유리)
- Mean Reversion: 평균회귀 (약세장/횡보장 유리)

Usage:
    python backtest_mean_reversion.py
    python backtest_mean_reversion.py --start 2022-01-01 --end 2024-12-31
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# =============================================================================
# Configuration
# =============================================================================
FEE = 0.0005  # 0.05% trading fee
SLIPPAGE = 0.0005  # 0.05% slippage

# Mean Reversion Parameters
RSI_PERIOD = 14
RSI_OVERSOLD = 30  # RSI < 30 매수
RSI_EXIT = 50      # RSI > 50 매도

BB_PERIOD = 20
BB_STD = 2.0       # 볼린저밴드 표준편차

PROFIT_TARGET = 0.03  # 3% 익절
STOP_LOSS = -0.05     # -5% 손절 (선택)

# BTC Market Filter
BTC_MA = 20  # BTC > MA20일 때만 매수 (약세장 필터)


# =============================================================================
# Data Loading
# =============================================================================
def load_data(symbol: str, data_dir: str = "data") -> pd.DataFrame:
    """Load OHLCV data for a single symbol."""
    filepath = Path(data_dir) / f"{symbol}.csv"
    if not filepath.exists():
        raise FileNotFoundError(f"No data for {symbol}: {filepath}")

    df = pd.read_csv(filepath, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    df = df.sort_index()
    return df


def filter_date_range(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    """Filter dataframe by date range."""
    if start:
        df = df[df.index >= pd.to_datetime(start)]
    if end:
        df = df[df.index <= pd.to_datetime(end)]
    return df


# =============================================================================
# Technical Indicators
# =============================================================================
def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI (Relative Strength Index)."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_bollinger_bands(series: pd.Series, period: int = 20, std: float = 2.0) -> tuple:
    """Calculate Bollinger Bands."""
    middle = series.rolling(window=period).mean()
    std_dev = series.rolling(window=period).std()
    upper = middle + (std_dev * std)
    lower = middle - (std_dev * std)
    return upper, middle, lower


def calculate_indicators(df: pd.DataFrame, btc_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all technical indicators."""
    df = df.copy()
    btc_df = btc_df.copy()

    # RSI
    df['rsi'] = calculate_rsi(df['close'], RSI_PERIOD)

    # Bollinger Bands
    df['bb_upper'], df['bb_middle'], df['bb_lower'] = calculate_bollinger_bands(
        df['close'], BB_PERIOD, BB_STD
    )

    # BTC Filter
    btc_aligned = btc_df.reindex(df.index, method='ffill')
    btc_aligned['btc_ma'] = btc_aligned['close'].rolling(window=BTC_MA).mean()

    # Previous day values (avoid look-ahead bias)
    df['prev_close'] = df['close'].shift(1)
    df['prev_rsi'] = df['rsi'].shift(1)
    df['prev_bb_lower'] = df['bb_lower'].shift(1)
    df['prev_bb_middle'] = df['bb_middle'].shift(1)

    df['prev_btc_close'] = btc_aligned['close'].shift(1)
    df['prev_btc_ma'] = btc_aligned['btc_ma'].shift(1)

    return df


# =============================================================================
# Backtest Logic
# =============================================================================
def backtest_mean_reversion(symbol: str, start: str | None = None, end: str | None = None,
                            use_stop_loss: bool = False) -> tuple[dict, pd.DataFrame]:
    """Backtest mean reversion strategy for a single cryptocurrency."""
    # Load data
    df = load_data(symbol)
    btc_df = load_data("BTC")

    # Filter date range
    df = filter_date_range(df, start, end)
    btc_df = filter_date_range(btc_df, start, end)

    # Calculate indicators
    df = calculate_indicators(df, btc_df)

    # Initialize backtest
    cash = 1_000_000
    position = 0.0
    position_entry_price = 0.0
    trades = []
    equity_curve = []

    for i, (date, row) in enumerate(df.iterrows()):
        # Skip if insufficient data
        if pd.isna(row['prev_rsi']) or pd.isna(row['prev_btc_ma']):
            equity = cash + position * row['close']
            equity_curve.append({'date': date, 'equity': equity})
            continue

        # === SELL LOGIC ===
        if position > 0:
            current_return = (row['close'] / position_entry_price - 1)

            sell_signal = False
            sell_reason = ""

            # Exit 1: Profit Target
            if current_return >= PROFIT_TARGET:
                sell_signal = True
                sell_reason = "Profit Target"

            # Exit 2: RSI Recovery
            elif row['prev_rsi'] > RSI_EXIT:
                sell_signal = True
                sell_reason = "RSI Exit"

            # Exit 3: Price above BB Middle
            elif row['prev_close'] > row['prev_bb_middle']:
                sell_signal = True
                sell_reason = "BB Middle"

            # Exit 4: Stop Loss (optional)
            elif use_stop_loss and current_return <= STOP_LOSS:
                sell_signal = True
                sell_reason = "Stop Loss"

            if sell_signal:
                sell_price = row['open'] * (1 - SLIPPAGE)
                sell_value = position * sell_price
                sell_fee = sell_value * FEE
                cash += sell_value - sell_fee

                # Record trade
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

        # === BUY LOGIC ===
        if position == 0:
            buy_signal = False

            # Entry 1: RSI Oversold + Below BB Lower
            if (row['prev_rsi'] < RSI_OVERSOLD and
                row['prev_close'] < row['prev_bb_lower'] and
                row['prev_btc_close'] > row['prev_btc_ma']):  # BTC filter
                buy_signal = True

            if buy_signal:
                buy_price = row['open'] * (1 + SLIPPAGE)
                buy_value = cash
                buy_fee = buy_value * FEE
                position = (buy_value - buy_fee) / buy_price
                position_entry_price = buy_price
                cash = 0.0

        # Record equity
        equity = cash + position * row['close']
        equity_curve.append({'date': date, 'equity': equity})

    # Close final position
    if position > 0:
        final_price = df.iloc[-1]['close']
        final_value = position * final_price * (1 - SLIPPAGE)
        final_fee = final_value * FEE
        cash += final_value - final_fee
        position = 0.0

    # Convert to DataFrame
    equity_df = pd.DataFrame(equity_curve)
    equity_df.set_index('date', inplace=True)

    # Calculate metrics
    final_equity = equity_df['equity'].iloc[-1]
    initial_equity = equity_df['equity'].iloc[0]
    total_return = (final_equity / initial_equity - 1) * 100

    # CAGR
    days = (equity_df.index[-1] - equity_df.index[0]).days
    years = days / 365.25
    cagr = (pow(final_equity / initial_equity, 1 / years) - 1) * 100 if years > 0 else 0

    # MDD
    running_max = equity_df['equity'].expanding().max()
    drawdown = (equity_df['equity'] / running_max - 1) * 100
    mdd = drawdown.min()

    # Sharpe
    equity_df['daily_return'] = equity_df['equity'].pct_change()
    daily_returns = equity_df['daily_return'].dropna()
    if len(daily_returns) > 0 and daily_returns.std() > 0:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365)
    else:
        sharpe = 0.0

    # Trade stats
    total_trades = len(trades)
    winning_trades = len([t for t in trades if t['profit'] > 0])
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

    # Average holding period
    if trades:
        avg_profit = np.mean([t['profit_pct'] for t in trades])
    else:
        avg_profit = 0.0

    metrics = {
        'symbol': symbol,
        'total_return': total_return,
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'avg_profit': avg_profit,
        'final_equity': final_equity
    }

    return metrics, equity_df


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description='Backtest Mean Reversion strategy')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--stop-loss', action='store_true', help='Enable stop loss')
    args = parser.parse_args()

    symbols = ['BTC', 'ETH', 'XRP', 'TRX', 'ADA']

    print("=" * 100)
    print("MEAN REVERSION STRATEGY BACKTEST (약세장 최적화)")
    print("=" * 100)
    print("\nStrategy Parameters:")
    print(f"  - Entry: RSI < {RSI_OVERSOLD} AND Price < BB Lower AND BTC > MA{BTC_MA}")
    print(f"  - Exit: RSI > {RSI_EXIT} OR Price > BB Middle OR Profit > {PROFIT_TARGET*100}%")
    if args.stop_loss:
        print(f"  - Stop Loss: {STOP_LOSS*100}%")
    print(f"  - Fee: {FEE*100}%, Slippage: {SLIPPAGE*100}%")
    if args.start or args.end:
        print(f"  - Period: {args.start or 'inception'} ~ {args.end or 'latest'}")
    print()

    # Run backtest
    results = []
    for symbol in symbols:
        print(f"Backtesting {symbol}...", end=' ', flush=True)
        try:
            metrics, equity_df = backtest_mean_reversion(symbol, args.start, args.end, args.stop_loss)
            results.append(metrics)
            print(f"CAGR: {metrics['cagr']:>7.2f}%, Trades: {metrics['total_trades']}")
        except Exception as e:
            print(f"Error: {e}")

    # Display results
    print("\n" + "=" * 100)
    print("RESULTS")
    print("=" * 100)
    print(f"\n{'Symbol':<10} {'CAGR':<12} {'MDD':<12} {'Sharpe':<12} {'Trades':<10} {'Win Rate':<12} {'Avg Profit':<12}")
    print("-" * 100)

    for r in results:
        print(f"{r['symbol']:<10} "
              f"{r['cagr']:>10.2f}%  "
              f"{r['mdd']:>10.2f}%  "
              f"{r['sharpe']:>10.2f}  "
              f"{r['total_trades']:>8}  "
              f"{r['win_rate']:>10.2f}%  "
              f"{r['avg_profit']:>10.2f}%")

    print("-" * 100)

    # Best performers
    if results:
        best_cagr = max(results, key=lambda x: x['cagr'])
        best_sharpe = max(results, key=lambda x: x['sharpe'])
        best_mdd = max(results, key=lambda x: x['mdd'])

        print(f"\nBest CAGR:   {best_cagr['symbol']} ({best_cagr['cagr']:.2f}%)")
        print(f"Best Sharpe: {best_sharpe['symbol']} ({best_sharpe['sharpe']:.2f})")
        print(f"Best MDD:    {best_mdd['symbol']} ({best_mdd['mdd']:.2f}%)")
        print()


if __name__ == "__main__":
    main()
