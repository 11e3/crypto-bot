#!/usr/bin/env python3
"""Grid Trading Strategy (횡보장 최적화)

가격 범위 내에서 기계적 매매:
- 일정 간격마다 매수/매도 주문 배치
- 변동성으로 수익 (횡보장 최적)

Usage:
    python backtest_grid_trading.py
    python backtest_grid_trading.py --start 2022-01-01 --end 2024-12-31
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

# Grid Parameters
GRID_LEVELS = 10      # 그리드 레벨 개수
GRID_SPACING = 0.02   # 2% 간격
REBALANCE_PERIOD = 30 # 30일마다 그리드 재설정


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


# =============================================================================
# Grid Trading Logic
# =============================================================================
def calculate_grid_levels(current_price: float, levels: int, spacing: float) -> tuple[list, list]:
    """Calculate grid buy/sell levels."""
    buy_levels = []
    sell_levels = []

    for i in range(1, levels + 1):
        buy_price = current_price * (1 - spacing * i)
        sell_price = current_price * (1 + spacing * i)
        buy_levels.append(buy_price)
        sell_levels.append(sell_price)

    return buy_levels, sell_levels


def backtest_grid_trading(symbol: str, start: str | None = None, end: str | None = None) -> tuple[dict, pd.DataFrame]:
    """Backtest grid trading strategy."""
    df = load_data(symbol)
    df = filter_date_range(df, start, end)

    cash = 1_000_000
    total_capital = cash
    positions = []  # List of (entry_price, quantity)
    trades = []
    equity_curve = []

    # Initial grid setup
    initial_price = df.iloc[0]['close']
    buy_levels, sell_levels = calculate_grid_levels(initial_price, GRID_LEVELS, GRID_SPACING)

    last_rebalance = df.index[0]
    days_since_rebalance = 0

    for date, row in df.iterrows():
        # Rebalance grid periodically
        days_since_rebalance = (date - last_rebalance).days
        if days_since_rebalance >= REBALANCE_PERIOD:
            buy_levels, sell_levels = calculate_grid_levels(row['close'], GRID_LEVELS, GRID_SPACING)
            last_rebalance = date

        # Check sell levels (if holding positions)
        positions_to_remove = []
        for i, (entry_price, quantity) in enumerate(positions):
            for sell_level in sell_levels:
                if row['high'] >= sell_level and entry_price < sell_level:
                    # Sell signal
                    sell_price = sell_level * (1 - SLIPPAGE)
                    sell_value = quantity * sell_price
                    sell_fee = sell_value * FEE
                    cash += sell_value - sell_fee

                    profit = sell_value - quantity * entry_price
                    profit_pct = (sell_price / entry_price - 1) * 100
                    trades.append({
                        'entry_price': entry_price,
                        'exit_price': sell_price,
                        'profit': profit,
                        'profit_pct': profit_pct
                    })

                    positions_to_remove.append(i)
                    break

        # Remove sold positions
        for i in reversed(positions_to_remove):
            positions.pop(i)

        # Check buy levels
        for buy_level in buy_levels:
            if row['low'] <= buy_level and cash > 0:
                # Buy signal
                buy_price = buy_level * (1 + SLIPPAGE)

                # Use 1/N of remaining cash per buy
                buy_value = min(cash / (GRID_LEVELS - len(positions) + 1), cash)

                if buy_value > 1000:  # Minimum order
                    buy_fee = buy_value * FEE
                    quantity = (buy_value - buy_fee) / buy_price
                    positions.append((buy_price, quantity))
                    cash -= buy_value

        # Calculate equity
        position_value = sum(quantity * row['close'] for _, quantity in positions)
        equity = cash + position_value
        equity_curve.append({'date': date, 'equity': equity})

    # Close all positions
    if positions:
        final_price = df.iloc[-1]['close']
        for entry_price, quantity in positions:
            final_value = quantity * final_price * (1 - SLIPPAGE)
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
    parser = argparse.ArgumentParser(description='Backtest Grid Trading')
    parser.add_argument('--start', type=str, help='Start date')
    parser.add_argument('--end', type=str, help='End date')
    args = parser.parse_args()

    symbols = ['BTC', 'ETH', 'XRP', 'TRX', 'ADA']

    print("=" * 100)
    print("GRID TRADING STRATEGY (횡보장 최적화)")
    print("=" * 100)
    print(f"\nGrid Levels: {GRID_LEVELS}, Spacing: {GRID_SPACING*100}%")
    print(f"Rebalance: Every {REBALANCE_PERIOD} days")
    if args.start or args.end:
        print(f"Period: {args.start or 'inception'} ~ {args.end or 'latest'}")
    print()

    results = []
    for symbol in symbols:
        print(f"Testing {symbol}...", end=' ', flush=True)
        try:
            metrics, _ = backtest_grid_trading(symbol, args.start, args.end)
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
