#!/usr/bin/env python3
"""Analyze Live Trading Performance vs Backtest

Compare actual trading results from bot with backtest expectations.

Usage:
    python analyze_live_trades.py                    # All accounts
    python analyze_live_trades.py Main              # Specific account
    python analyze_live_trades.py --since 2025-01-01  # Date range
"""

import argparse
import sys
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
except ImportError as e:
    print(f"Error: {e}")
    print("Install: pip install pandas numpy")
    sys.exit(1)


# =============================================================================
# Backtest Expectations (from backtest_vbo_portfolio.py)
# =============================================================================
BACKTEST_EXPECTATIONS = {
    'BTC+ETH': {
        'full_period': {
            'CAGR': 91.61,
            'Sharpe': 2.15,
            'MDD': -21.17,
            'win_rate': 100.0  # 8/8 years
        },
        'test_period_2022_2024': {
            'CAGR': 51.92,
            'Sharpe': 1.92,
            'MDD': -14.95,
            'win_rate': 100.0  # 3/3 years
        },
        '2025': {
            'CAGR': 12.11,
            'MDD': -8.23
        }
    }
}


# =============================================================================
# Trade Analysis
# =============================================================================
class TradeAnalyzer:
    """Analyze trading performance."""

    def __init__(self, csv_file: Path):
        self.csv_file = csv_file
        self.account_name = csv_file.stem.replace('trades_', '')
        self.df = self._load_trades()

    def _load_trades(self) -> pd.DataFrame:
        """Load trade log."""
        if not self.csv_file.exists():
            raise FileNotFoundError(f"Trade log not found: {self.csv_file}")

        df = pd.read_csv(self.csv_file)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['date'] = pd.to_datetime(df['date'])
        return df

    def filter_by_date(self, start_date: str | None = None, end_date: str | None = None):
        """Filter trades by date range."""
        if start_date:
            self.df = self.df[self.df['date'] >= start_date]
        if end_date:
            self.df = self.df[self.df['date'] <= end_date]

    def get_summary(self) -> dict:
        """Calculate summary statistics."""
        buys = self.df[self.df['action'] == 'BUY']
        sells = self.df[self.df['action'] == 'SELL']

        if len(sells) == 0:
            return {
                'account': self.account_name,
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'total_profit_krw': 0.0,
                'total_profit_pct': 0.0,
                'avg_profit_pct': 0.0,
                'avg_win_pct': 0.0,
                'avg_loss_pct': 0.0,
                'best_trade_pct': 0.0,
                'worst_trade_pct': 0.0,
                'total_invested': 0.0,
                'roi': 0.0
            }

        wins = sells[sells['profit_krw'] > 0]
        losses = sells[sells['profit_krw'] < 0]

        total_invested = buys['amount'].sum()
        total_profit = sells['profit_krw'].sum()

        return {
            'account': self.account_name,
            'total_trades': len(sells),
            'winning_trades': len(wins),
            'losing_trades': len(losses),
            'win_rate': (len(wins) / len(sells) * 100) if len(sells) > 0 else 0,
            'total_profit_krw': total_profit,
            'total_profit_pct': (total_profit / total_invested * 100) if total_invested > 0 else 0,
            'avg_profit_pct': sells['profit_pct'].mean(),
            'avg_win_pct': wins['profit_pct'].mean() if len(wins) > 0 else 0,
            'avg_loss_pct': losses['profit_pct'].mean() if len(losses) > 0 else 0,
            'best_trade_pct': sells['profit_pct'].max() if len(sells) > 0 else 0,
            'worst_trade_pct': sells['profit_pct'].min() if len(sells) > 0 else 0,
            'total_invested': total_invested,
            'roi': (total_profit / total_invested * 100) if total_invested > 0 else 0
        }

    def calculate_cagr(self, start_date: str | None = None, end_date: str | None = None) -> float:
        """Calculate annualized return (CAGR)."""
        sells = self.df[self.df['action'] == 'SELL']
        if len(sells) == 0:
            return 0.0

        # Get date range
        if start_date:
            first_date = pd.to_datetime(start_date)
        else:
            first_date = self.df['date'].min()

        if end_date:
            last_date = pd.to_datetime(end_date)
        else:
            last_date = self.df['date'].max()

        days = (last_date - first_date).days
        if days < 1:
            return 0.0

        years = days / 365.25

        # Calculate total return
        buys = self.df[self.df['action'] == 'BUY']
        total_invested = buys['amount'].sum()
        total_profit = sells['profit_krw'].sum()

        if total_invested <= 0:
            return 0.0

        total_return = (total_invested + total_profit) / total_invested

        # CAGR = (Final/Initial)^(1/years) - 1
        cagr = (total_return ** (1/years) - 1) * 100 if years > 0 else 0

        return cagr

    def get_trades_by_symbol(self) -> dict[str, dict]:
        """Get performance by symbol."""
        sells = self.df[self.df['action'] == 'SELL']

        results = {}
        for symbol in sells['symbol'].unique():
            symbol_sells = sells[sells['symbol'] == symbol]
            symbol_buys = self.df[(self.df['action'] == 'BUY') & (self.df['symbol'] == symbol)]

            wins = symbol_sells[symbol_sells['profit_krw'] > 0]

            results[symbol] = {
                'trades': len(symbol_sells),
                'win_rate': (len(wins) / len(symbol_sells) * 100) if len(symbol_sells) > 0 else 0,
                'total_profit_krw': symbol_sells['profit_krw'].sum(),
                'avg_profit_pct': symbol_sells['profit_pct'].mean(),
                'total_invested': symbol_buys['amount'].sum()
            }

        return results

    def compare_with_backtest(self) -> dict:
        """Compare with backtest expectations."""
        summary = self.get_summary()

        # Determine which period we're in
        # Assume BTC+ETH strategy for now
        expected = BACKTEST_EXPECTATIONS['BTC+ETH']['test_period_2022_2024']

        return {
            'expected_cagr': expected['CAGR'],
            'actual_cagr': self.calculate_cagr(),
            'cagr_diff': self.calculate_cagr() - expected['CAGR'],
            'expected_sharpe': expected['Sharpe'],
            'expected_win_rate': expected['win_rate'],
            'actual_win_rate': summary['win_rate'],
            'win_rate_diff': summary['win_rate'] - expected['win_rate'],
            'expected_mdd': expected['MDD'],
        }


# =============================================================================
# Display Functions
# =============================================================================
def print_summary(analyzer: TradeAnalyzer):
    """Print performance summary."""
    summary = analyzer.get_summary()

    print("\n" + "="*70)
    print(f"TRADING PERFORMANCE SUMMARY - [{summary['account']}]")
    print("="*70)
    print(f"Total Trades:        {summary['total_trades']:>6}")
    print(f"Winning Trades:      {summary['winning_trades']:>6}")
    print(f"Losing Trades:       {summary['losing_trades']:>6}")
    print(f"Win Rate:            {summary['win_rate']:>6.2f}%")
    print("-"*70)
    print(f"Total Invested:      {summary['total_invested']:>13,.0f} KRW")
    print(f"Total Profit:        {summary['total_profit_krw']:>13,.0f} KRW")
    print(f"ROI:                 {summary['roi']:>6.2f}%")
    print("-"*70)
    print(f"Avg Profit/Trade:    {summary['avg_profit_pct']:>6.2f}%")
    print(f"Avg Win:             {summary['avg_win_pct']:>6.2f}%")
    print(f"Avg Loss:            {summary['avg_loss_pct']:>6.2f}%")
    print(f"Best Trade:          {summary['best_trade_pct']:>6.2f}%")
    print(f"Worst Trade:         {summary['worst_trade_pct']:>6.2f}%")
    print("="*70)


def print_by_symbol(analyzer: TradeAnalyzer):
    """Print performance by symbol."""
    by_symbol = analyzer.get_trades_by_symbol()

    if not by_symbol:
        return

    print("\n" + "="*70)
    print("PERFORMANCE BY SYMBOL")
    print("="*70)
    print(f"{'Symbol':<10} {'Trades':>8} {'Win Rate':>10} {'Avg Profit':>12} {'Total Profit':>15}")
    print("-"*70)

    for symbol, stats in sorted(by_symbol.items()):
        print(f"{symbol:<10} {stats['trades']:>8} {stats['win_rate']:>9.1f}% "
              f"{stats['avg_profit_pct']:>11.2f}% {stats['total_profit_krw']:>14,.0f}")

    print("="*70)


def print_backtest_comparison(analyzer: TradeAnalyzer):
    """Print comparison with backtest."""
    comparison = analyzer.compare_with_backtest()

    print("\n" + "="*70)
    print("BACKTEST COMPARISON (BTC+ETH Strategy)")
    print("="*70)
    print(f"{'Metric':<25} {'Expected':>15} {'Actual':>15} {'Diff':>15}")
    print("-"*70)
    print(f"{'CAGR':<25} {comparison['expected_cagr']:>14.2f}% "
          f"{comparison['actual_cagr']:>14.2f}% "
          f"{comparison['cagr_diff']:>+14.2f}%")
    print(f"{'Win Rate':<25} {comparison['expected_win_rate']:>14.2f}% "
          f"{comparison['actual_win_rate']:>14.2f}% "
          f"{comparison['win_rate_diff']:>+14.2f}%")
    print(f"{'Sharpe Ratio':<25} {comparison['expected_sharpe']:>15.2f} {'N/A':>15} {'N/A':>15}")
    print(f"{'Max Drawdown':<25} {comparison['expected_mdd']:>14.2f}% {'N/A':>15} {'N/A':>15}")
    print("="*70)

    # Assessment
    cagr_ok = abs(comparison['cagr_diff']) < 20  # Within 20% of expected
    win_rate_ok = comparison['actual_win_rate'] >= 50  # At least 50% win rate

    print("\nASSESSMENT:")
    if cagr_ok and win_rate_ok:
        print("✅ Performance is within expected range")
    elif not cagr_ok:
        print("⚠️  CAGR differs significantly from backtest")
    elif not win_rate_ok:
        print("⚠️  Win rate is below acceptable threshold")

    print("\nNOTE:")
    print("- Backtest expectations are based on 2022-2024 test period")
    print("- Live trading includes real slippage and execution delays")
    print("- Short trading periods may show high variance")
    print("- Need at least 20+ trades for statistical significance")
    print("="*70)


def print_recent_trades(analyzer: TradeAnalyzer, n: int = 10):
    """Print recent trades."""
    df = analyzer.df

    print("\n" + "="*70)
    print(f"RECENT TRADES (Last {n})")
    print("="*70)
    print(f"{'Date':<12} {'Action':<6} {'Symbol':<8} {'Price':>12} {'Amount':>12} {'Profit':>10}")
    print("-"*70)

    recent = df.tail(n)
    for _, trade in recent.iterrows():
        date_str = trade['date'].strftime('%Y-%m-%d')
        action = trade['action']
        symbol = trade['symbol']
        price = f"{trade['price']:,.0f}"
        amount = f"{trade['amount']:,.0f}"

        if action == 'SELL':
            profit = f"{trade['profit_pct']:+.2f}%"
        else:
            profit = "-"

        print(f"{date_str:<12} {action:<6} {symbol:<8} {price:>12} {amount:>12} {profit:>10}")

    print("="*70)


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description='Analyze live trading performance')
    parser.add_argument('account', nargs='?', help='Account name (optional)')
    parser.add_argument('--since', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--until', help='End date (YYYY-MM-DD)')
    parser.add_argument('--recent', type=int, default=10, help='Number of recent trades to show')

    args = parser.parse_args()

    # Find trade log files
    if args.account:
        log_files = [Path(f"trades_{args.account}.csv")]
    else:
        log_files = list(Path().glob('trades_*.csv'))

    if not log_files:
        print("No trade log files found!")
        print("Expected format: trades_AccountName.csv")
        return

    # Analyze each account
    for log_file in sorted(log_files):
        if not log_file.exists():
            print(f"Warning: {log_file} not found, skipping...")
            continue

        try:
            analyzer = TradeAnalyzer(log_file)

            # Apply date filters
            if args.since or args.until:
                analyzer.filter_by_date(args.since, args.until)

            # Print analysis
            print_summary(analyzer)
            print_by_symbol(analyzer)
            print_backtest_comparison(analyzer)
            print_recent_trades(analyzer, args.recent)

        except Exception as e:
            print(f"Error analyzing {log_file}: {e}")
            import traceback
            traceback.print_exc()

    print()


if __name__ == '__main__':
    main()
