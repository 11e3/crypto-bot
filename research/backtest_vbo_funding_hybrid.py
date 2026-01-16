#!/usr/bin/env python3
"""VBO + Funding Arbitrage Hybrid Strategy

전천후 하이브리드 전략:
- 강세장 (BTC > MA20): VBO (업비트 현물 롱)
- 약세장 (BTC < MA20): 펀딩비 차익거래 (업비트 현물 롱 + 바이낸스 선물 숏)

VBO의 약점(약세장 관망)을 펀딩비 차익으로 보완

Usage:
    python backtest_vbo_funding_hybrid.py
    python backtest_vbo_funding_hybrid.py --start 2022-01-01 --end 2024-12-31
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

# VBO params
MA_SHORT = 5
BTC_MA = 20
NOISE_RATIO = 0.5

# Funding params
FUNDING_RATE_BULL = 0.0002  # Not used (bull = VBO)
FUNDING_RATE_BEAR = 0.00005  # 0.005% per 8h
FUNDING_RATE_NEUTRAL = 0.0001
FUTURES_LEVERAGE = 1


# =============================================================================
# Data Loading
# =============================================================================
def load_data(symbol: str, data_dir: str = "data") -> pd.DataFrame:
    filepath = Path(data_dir) / f"{symbol}.csv"
    if not filepath.exists():
        raise FileNotFoundError(f"No data for {symbol}: {filepath}")

    df = pd.read_csv(filepath, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    df = df.sort_index()
    return df


def filter_date_range(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if start:
        df = df[df.index >= pd.to_datetime(start)]
    if end:
        df = df[df.index <= pd.to_datetime(end)]
    return df


def calculate_indicators(df: pd.DataFrame, btc_df: pd.DataFrame) -> pd.DataFrame:
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

    # Market regime
    df['market_regime'] = np.where(df['prev_btc_close'] > df['prev_btc_ma'], 'BULL', 'BEAR')

    # VBO target
    df['target_price'] = df['open'] + (df['prev_high'] - df['prev_low']) * NOISE_RATIO

    return df


# =============================================================================
# Backtest
# =============================================================================
def backtest_vbo_funding_hybrid(symbol: str, start: str | None = None, end: str | None = None) -> tuple[dict, pd.DataFrame]:
    df = load_data(symbol)
    btc_df = load_data("BTC")

    df = filter_date_range(df, start, end)
    btc_df = filter_date_range(btc_df, start, end)

    df = calculate_indicators(df, btc_df)

    cash = 1_000_000
    position = 0.0
    position_entry_price = 0.0
    current_strategy = None  # 'VBO' or 'FUNDING'

    # Funding arbitrage state
    spot_quantity_funding = 0.0
    futures_quantity_funding = 0.0
    funding_entry_price = 0.0
    total_funding_received = 0.0

    trades = []
    equity_curve = []

    for date, row in df.iterrows():
        if pd.isna(row['prev_ma5']) or pd.isna(row['prev_btc_ma']):
            equity = cash + position * row['close']
            equity_curve.append({'date': date, 'equity': equity, 'strategy': current_strategy})
            continue

        regime = row['market_regime']

        # === REGIME CHANGE: Switch strategy ===
        if current_strategy is not None and regime != current_strategy:
            if current_strategy == 'VBO' and position > 0:
                # Close VBO position
                sell_price = row['open'] * (1 - SLIPPAGE)
                sell_value = position * sell_price
                sell_fee = sell_value * FEE
                cash += sell_value - sell_fee

                trades.append({
                    'date': date,
                    'strategy': 'VBO',
                    'action': 'exit',
                    'reason': 'Regime Switch to BEAR'
                })

                position = 0.0
                position_entry_price = 0.0

            elif current_strategy == 'FUNDING' and spot_quantity_funding > 0:
                # Close funding arbitrage
                exit_price = row['close'] * (1 - SLIPPAGE)

                spot_exit_value = spot_quantity_funding * exit_price
                spot_exit_fee = spot_exit_value * FEE
                cash += spot_exit_value - spot_exit_fee

                futures_exit_notional = futures_quantity_funding * exit_price
                futures_exit_fee = futures_exit_notional * FEE
                # Futures PnL already in total_funding_received tracking

                trades.append({
                    'date': date,
                    'strategy': 'FUNDING',
                    'action': 'exit',
                    'reason': 'Regime Switch to BULL'
                })

                spot_quantity_funding = 0.0
                futures_quantity_funding = 0.0
                funding_entry_price = 0.0

            current_strategy = None

        # === BULL MARKET: VBO Strategy ===
        if regime == 'BULL':
            # VBO exit
            if position > 0:
                if row['prev_close'] < row['prev_ma5'] or row['prev_btc_close'] < row['prev_btc_ma']:
                    sell_price = row['open'] * (1 - SLIPPAGE)
                    sell_value = position * sell_price
                    sell_fee = sell_value * FEE
                    cash += sell_value - sell_fee

                    trades.append({
                        'date': date,
                        'strategy': 'VBO',
                        'action': 'exit',
                        'reason': 'VBO Signal'
                    })

                    position = 0.0
                    position_entry_price = 0.0
                    current_strategy = None

            # VBO entry
            if position == 0:
                if (row['high'] >= row['target_price'] and
                    row['prev_close'] > row['prev_ma5'] and
                    row['prev_btc_close'] > row['prev_btc_ma']):

                    buy_price = row['target_price'] * (1 + SLIPPAGE)
                    buy_value = cash
                    buy_fee = buy_value * FEE
                    position = (buy_value - buy_fee) / buy_price
                    position_entry_price = buy_price
                    cash = 0.0
                    current_strategy = 'VBO'

                    trades.append({
                        'date': date,
                        'strategy': 'VBO',
                        'action': 'entry',
                        'reason': 'VBO Signal'
                    })

        # === BEAR MARKET: Funding Arbitrage ===
        else:  # BEAR
            # Funding arbitrage: hold position and collect funding
            if spot_quantity_funding > 0:
                # Collect funding (daily, 3x per 8h)
                funding_rate_per_8h = FUNDING_RATE_BEAR
                daily_funding_rate = funding_rate_per_8h * 3
                funding_payment = futures_quantity_funding * row['close'] * daily_funding_rate
                total_funding_received += funding_payment

            else:
                # Enter funding arbitrage
                entry_price = row['close'] * (1 + SLIPPAGE)

                # Split capital: 50% spot, 50% futures margin
                available_cash = cash
                spot_capital = available_cash * 0.5
                futures_margin_budget = available_cash * 0.5

                # Spot long
                spot_fee = spot_capital * FEE
                spot_quantity_funding = (spot_capital - spot_fee) / entry_price

                # Futures short (delta neutral with spot)
                futures_quantity_funding = spot_quantity_funding
                futures_notional = futures_quantity_funding * entry_price
                futures_fee = futures_notional * FEE
                futures_margin_needed = futures_notional / FUTURES_LEVERAGE

                # Total cost
                total_cost = spot_capital + futures_margin_needed + spot_fee + futures_fee

                # Deduct from cash
                cash = available_cash - total_cost

                funding_entry_price = entry_price
                current_strategy = 'FUNDING'

                trades.append({
                    'date': date,
                    'strategy': 'FUNDING',
                    'action': 'entry',
                    'reason': 'Bear Market'
                })

        # Calculate equity
        if current_strategy == 'VBO':
            equity = cash + position * row['close']
        elif current_strategy == 'FUNDING':
            # Spot value
            spot_value = spot_quantity_funding * row['close']
            # Futures PnL
            futures_pnl = futures_quantity_funding * (funding_entry_price - row['close'])
            # Total
            equity = cash + spot_value + futures_pnl + total_funding_received
        else:
            equity = cash

        equity_curve.append({
            'date': date,
            'equity': equity,
            'strategy': current_strategy
        })

    # Close final position
    final_price = df.iloc[-1]['close']
    if position > 0:  # VBO
        final_value = position * final_price * (1 - SLIPPAGE)
        final_fee = final_value * FEE
        cash += final_value - final_fee
    elif spot_quantity_funding > 0:  # Funding
        spot_exit_value = spot_quantity_funding * final_price * (1 - SLIPPAGE)
        spot_exit_fee = spot_exit_value * FEE
        cash += spot_exit_value - spot_exit_fee

    equity_df = pd.DataFrame(equity_curve)
    equity_df.set_index('date', inplace=True)

    # Metrics
    final_equity = equity_df['equity'].iloc[-1]
    initial_equity = 1_000_000

    days = (equity_df.index[-1] - equity_df.index[0]).days
    years = days / 365.25
    cagr = (pow(final_equity / initial_equity, 1 / years) - 1) * 100 if years > 0 else 0

    running_max = equity_df['equity'].expanding().max()
    drawdown = (equity_df['equity'] / running_max - 1) * 100
    mdd = drawdown.min()

    equity_df['daily_return'] = equity_df['equity'].pct_change()
    daily_returns = equity_df['daily_return'].dropna()
    sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365) if len(daily_returns) > 0 and daily_returns.std() > 0 else 0

    # Strategy stats
    vbo_days = len(equity_df[equity_df['strategy'] == 'VBO'])
    funding_days = len(equity_df[equity_df['strategy'] == 'FUNDING'])
    total_days = len(equity_df)

    return {
        'symbol': symbol,
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
        'final_equity': final_equity,
        'total_funding': total_funding_received,
        'vbo_days': vbo_days,
        'funding_days': funding_days,
        'total_days': total_days,
        'vbo_pct': vbo_days / total_days * 100 if total_days > 0 else 0,
        'funding_pct': funding_days / total_days * 100 if total_days > 0 else 0
    }, equity_df


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description='Backtest VBO+Funding Hybrid')
    parser.add_argument('--start', type=str, help='Start date')
    parser.add_argument('--end', type=str, help='End date')
    args = parser.parse_args()

    symbols = ['BTC', 'ETH']

    print("=" * 100)
    print("VBO + FUNDING ARBITRAGE HYBRID STRATEGY")
    print("=" * 100)
    print(f"\nStrategy:")
    print(f"  - Bull Market (BTC > MA{BTC_MA}): VBO (spot long)")
    print(f"  - Bear Market (BTC < MA{BTC_MA}): Funding Arbitrage (spot long + futures short)")
    print(f"\nBenefits:")
    print(f"  - VBO in bull: High returns from trends")
    print(f"  - Funding in bear: Stable returns + NO liquidation risk")
    print(f"  - All-weather strategy")
    if args.start or args.end:
        print(f"\nPeriod: {args.start or 'inception'} ~ {args.end or 'latest'}")
    print()

    results = []
    for symbol in symbols:
        print(f"{'='*100}")
        print(f"Testing {symbol}...")
        print(f"{'='*100}")
        try:
            metrics, equity_df = backtest_vbo_funding_hybrid(symbol, args.start, args.end)
            results.append(metrics)

            print(f"\n{symbol} Results:")
            print(f"  CAGR: {metrics['cagr']:.2f}%")
            print(f"  Sharpe: {metrics['sharpe']:.2f}")
            print(f"  MDD: {metrics['mdd']:.2f}%")
            print(f"  Final Equity: ${metrics['final_equity']:,.0f}")
            print(f"  Total Funding Profit: ${metrics['total_funding']:,.0f}")
            print(f"  VBO Days: {metrics['vbo_days']} ({metrics['vbo_pct']:.1f}%)")
            print(f"  Funding Days: {metrics['funding_days']} ({metrics['funding_pct']:.1f}%)")

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"\n{'Symbol':<10} {'CAGR':<12} {'MDD':<12} {'Sharpe':<12} {'Funding$':<15} {'VBO%':<10}")
    print("-" * 100)

    for r in results:
        print(f"{r['symbol']:<10} {r['cagr']:>10.2f}%  {r['mdd']:>10.2f}%  {r['sharpe']:>10.2f}  "
              f"${r['total_funding']:>12,.0f}  {r['vbo_pct']:>8.1f}%")

    print("-" * 100)

    if results:
        best = max(results, key=lambda x: x['sharpe'])
        print(f"\nBest: {best['symbol']} (Sharpe: {best['sharpe']:.2f}, CAGR: {best['cagr']:.2f}%)")
    print()


if __name__ == "__main__":
    main()
