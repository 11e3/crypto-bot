#!/usr/bin/env python3
"""Funding Rate Arbitrage Strategy Backtest

시장중립 전략:
- 업비트 현물 매수 (Long)
- 바이낸스 선물 숏 (Short)
- 델타 중립: 가격 변동 영향 없음
- 8시간마다 펀딩비 수익

Usage:
    python backtest_funding_arbitrage.py
    python backtest_funding_arbitrage.py --start 2022-01-01 --end 2024-12-31
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


# =============================================================================
# Configuration
# =============================================================================
SPOT_FEE = 0.0005  # 업비트 현물 수수료 0.05%
FUTURES_FEE = 0.0004  # 바이낸스 선물 수수료 0.04%
SLIPPAGE = 0.0005

# Funding rate assumptions (8시간마다)
# 강세장: 0.01-0.03% (롱 많음 → 숏이 받음)
# 약세장: -0.01-0.01% (숏 많음 → 롱이 받음)
FUNDING_RATE_BULL = 0.0002  # 0.02% per 8h = ~21.9% APR
FUNDING_RATE_BEAR = 0.00005  # 0.005% per 8h = ~5.5% APR
FUNDING_RATE_NEUTRAL = 0.0001  # 0.01% per 8h = ~10.9% APR

# 레버리지 (선물)
FUTURES_LEVERAGE = 1  # 1배 = 안전
# FUTURES_LEVERAGE = 2  # 2배 = 자본 효율 증가, 청산 위험 증가


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
    """Calculate market regime for funding rate estimation."""
    df = df.copy()
    btc_df = btc_df.copy()

    # BTC regime
    btc_aligned = btc_df.reindex(df.index, method='ffill')
    btc_aligned['btc_ma20'] = btc_aligned['close'].rolling(window=20).mean()

    df['prev_btc_close'] = btc_aligned['close'].shift(1)
    df['prev_btc_ma20'] = btc_aligned['btc_ma20'].shift(1)

    # Market regime affects funding rate
    df['market_regime'] = np.where(df['prev_btc_close'] > df['prev_btc_ma20'], 'BULL', 'BEAR')

    return df


# =============================================================================
# Backtest
# =============================================================================
def backtest_funding_arbitrage(symbol: str, start: str | None = None, end: str | None = None) -> tuple[dict, pd.DataFrame]:
    """Backtest funding rate arbitrage strategy."""
    df = load_data(symbol)
    btc_df = load_data("BTC")

    df = filter_date_range(df, start, end)
    btc_df = filter_date_range(btc_df, start, end)

    df = calculate_indicators(df, btc_df)

    initial_capital = 1_000_000

    # 자본 배분
    # 현물: 50% (전액 사용)
    # 선물: 50% (증거금, 레버리지 적용)
    spot_capital = initial_capital * 0.5
    futures_margin = initial_capital * 0.5

    # 포지션 진입
    entry_price = df.iloc[0]['close'] * (1 + SLIPPAGE)  # 슬리피지 반영

    # 현물 매수
    spot_fee = spot_capital * SPOT_FEE
    spot_quantity = (spot_capital - spot_fee) / entry_price

    # 선물 숏 (델타 중립 위해 현물과 동일 수량)
    futures_quantity = spot_quantity
    futures_notional = futures_quantity * entry_price
    futures_fee = futures_notional * FUTURES_FEE
    futures_margin = futures_notional / FUTURES_LEVERAGE

    # 총 진입 비용 (수수료 포함)
    total_entry_fees = spot_fee + futures_fee
    total_used = spot_capital + futures_margin
    remaining_cash = initial_capital - total_used - total_entry_fees

    print(f"\n{symbol} Position Setup:")
    print(f"  Entry Price: ${entry_price:,.2f} (inc. slippage)")
    print(f"  Spot Long: {spot_quantity:.4f} coins (${spot_capital:,.0f})")
    print(f"  Futures Short: {futures_quantity:.4f} coins (${futures_notional:,.0f}, Margin: ${futures_margin:,.0f})")
    print(f"  Leverage: {FUTURES_LEVERAGE}x")
    print(f"  Entry Fees: ${total_entry_fees:,.0f} (Spot: ${spot_fee:,.0f} + Futures: ${futures_fee:,.0f})")
    print(f"  Delta: {abs(spot_quantity - futures_quantity):.6f} (neutral)")
    print(f"  Remaining Cash: ${remaining_cash:,.0f}\n")

    # 수익 추적
    equity_curve = []
    funding_payments = []
    total_funding_received = 0

    for date, row in df.iterrows():
        # 펀딩비 정산 (일별, 하루 3회 가정)
        regime = row['market_regime']

        # 시장 상황에 따른 펀딩비율 (8시간당)
        if regime == 'BULL':
            funding_rate_per_8h = FUNDING_RATE_BULL
        elif regime == 'BEAR':
            funding_rate_per_8h = FUNDING_RATE_BEAR
        else:
            funding_rate_per_8h = FUNDING_RATE_NEUTRAL

        # 하루 3회 펀딩비 (00:00, 08:00, 16:00 KST)
        daily_funding_rate = funding_rate_per_8h * 3
        funding_payment = futures_quantity * row['close'] * daily_funding_rate
        total_funding_received += funding_payment

        funding_payments.append({
            'date': date,
            'funding_rate': daily_funding_rate,
            'payment': funding_payment,
            'regime': regime
        })

        # Mark-to-Market Equity
        current_price = row['close']

        # 현물 가치 변화
        spot_value = spot_quantity * current_price
        spot_pnl = spot_value - spot_capital

        # 선물 PnL (숏)
        futures_pnl = futures_quantity * (entry_price - current_price)

        # 총 equity = 초기자본 + 현물PnL + 선물PnL + 누적펀딩비
        # (델타 중립이면 spot_pnl + futures_pnl ≈ 0, 펀딩비만 순수익)
        equity = initial_capital + spot_pnl + futures_pnl + total_funding_received

        equity_curve.append({
            'date': date,
            'equity': equity,
            'spot_value': spot_value,
            'futures_pnl': futures_pnl,
            'funding_total': total_funding_received
        })

    equity_df = pd.DataFrame(equity_curve)
    equity_df.set_index('date', inplace=True)

    # 청산 수수료 계산 (포지션 닫을 때)
    final_price = df.iloc[-1]['close']
    exit_price = final_price * (1 - SLIPPAGE)  # 슬리피지 반영

    # 현물 매도 수수료
    spot_exit_value = spot_quantity * exit_price
    spot_exit_fee = spot_exit_value * SPOT_FEE

    # 선물 커버 수수료
    futures_exit_notional = futures_quantity * exit_price
    futures_exit_fee = futures_exit_notional * FUTURES_FEE

    total_exit_fees = spot_exit_fee + futures_exit_fee

    # Metrics (청산 수수료 차감)
    final_equity_before_exit = equity_df['equity'].iloc[-1]
    final_equity = final_equity_before_exit - total_exit_fees
    initial_equity = initial_capital

    days = (equity_df.index[-1] - equity_df.index[0]).days
    years = days / 365.25
    cagr = (pow(final_equity / initial_equity, 1 / years) - 1) * 100 if years > 0 else 0

    running_max = equity_df['equity'].expanding().max()
    drawdown = (equity_df['equity'] / running_max - 1) * 100
    mdd = drawdown.min()

    equity_df['daily_return'] = equity_df['equity'].pct_change()
    daily_returns = equity_df['daily_return'].dropna()
    sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365) if len(daily_returns) > 0 and daily_returns.std() > 0 else 0

    # 펀딩비 통계
    funding_df = pd.DataFrame(funding_payments)
    total_funding_payments = len(funding_df)
    avg_funding_payment = funding_df['payment'].mean() if len(funding_df) > 0 else 0
    total_funding_profit = total_funding_received

    # 가격 변동 영향 (델타 중립 검증)
    price_change_pct = (equity_df['spot_value'].iloc[-1] / equity_df['spot_value'].iloc[0] - 1) * 100
    # 델타 중립 검증: spot_pnl + futures_pnl should be close to 0
    final_spot_pnl = equity_df['spot_value'].iloc[-1] - spot_capital
    final_futures_pnl = equity_df['futures_pnl'].iloc[-1]
    delta_neutrality_error = abs(final_spot_pnl + final_futures_pnl)

    return {
        'symbol': symbol,
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
        'total_funding': total_funding_profit,
        'funding_payments': total_funding_payments,
        'avg_funding': avg_funding_payment,
        'price_change': price_change_pct,
        'delta_error': delta_neutrality_error,
        'final_equity': final_equity,
        'entry_fees': total_entry_fees,
        'exit_fees': total_exit_fees,
        'total_fees': total_entry_fees + total_exit_fees
    }, equity_df


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description='Backtest Funding Rate Arbitrage')
    parser.add_argument('--start', type=str, help='Start date')
    parser.add_argument('--end', type=str, help='End date')
    args = parser.parse_args()

    symbols = ['BTC', 'ETH']  # 주요 코인만 (펀딩비 안정적)

    print("=" * 100)
    print("FUNDING RATE ARBITRAGE STRATEGY (시장중립)")
    print("=" * 100)
    print(f"\nStrategy:")
    print(f"  - Upbit Spot LONG + Binance Futures SHORT")
    print(f"  - Delta Neutral (price-independent)")
    print(f"  - Funding payment every 8 hours")
    print(f"  - Leverage: {FUTURES_LEVERAGE}x")
    print(f"\nFunding Rate Assumptions (per 8h):")
    print(f"  - Bull Market: {FUNDING_RATE_BULL*100:.3f}% × 3/day = {FUNDING_RATE_BULL*3*100:.2f}%/day (~{FUNDING_RATE_BULL*3*365*100:.1f}% APR)")
    print(f"  - Bear Market: {FUNDING_RATE_BEAR*100:.3f}% × 3/day = {FUNDING_RATE_BEAR*3*100:.2f}%/day (~{FUNDING_RATE_BEAR*3*365*100:.1f}% APR)")
    print(f"  - Neutral: {FUNDING_RATE_NEUTRAL*100:.3f}% × 3/day = {FUNDING_RATE_NEUTRAL*3*100:.2f}%/day (~{FUNDING_RATE_NEUTRAL*3*365*100:.1f}% APR)")
    if args.start or args.end:
        print(f"\nPeriod: {args.start or 'inception'} ~ {args.end or 'latest'}")
    print()

    results = []
    for symbol in symbols:
        print(f"{'='*100}")
        print(f"Testing {symbol}...")
        print(f"{'='*100}")
        try:
            metrics, equity_df = backtest_funding_arbitrage(symbol, args.start, args.end)
            results.append(metrics)

            print(f"\n{symbol} Results:")
            print(f"  CAGR: {metrics['cagr']:.2f}%")
            print(f"  Sharpe: {metrics['sharpe']:.2f}")
            print(f"  MDD: {metrics['mdd']:.2f}%")
            print(f"  Total Funding Profit: ${metrics['total_funding']:,.0f}")
            print(f"  Total Fees: ${metrics['total_fees']:,.0f} (Entry: ${metrics['entry_fees']:,.0f} + Exit: ${metrics['exit_fees']:,.0f})")
            print(f"  Net Profit: ${metrics['total_funding'] - metrics['total_fees']:,.0f}")
            print(f"  Funding Payments: {metrics['funding_payments']}")
            print(f"  Avg Funding: ${metrics['avg_funding']:.2f}")
            print(f"  Price Change: {metrics['price_change']:.2f}%")
            print(f"  Delta Neutrality Error: ${metrics['delta_error']:,.0f} (should be ~$0)")
            print(f"  Final Equity: ${metrics['final_equity']:,.0f}")

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"\n{'Symbol':<10} {'CAGR':<12} {'MDD':<12} {'Sharpe':<12} {'Funding':<15} {'Payments':<12}")
    print("-" * 100)

    for r in results:
        print(f"{r['symbol']:<10} {r['cagr']:>10.2f}%  {r['mdd']:>10.2f}%  {r['sharpe']:>10.2f}  "
              f"${r['total_funding']:>12,.0f}  {r['funding_payments']:>10}")

    print("-" * 100)

    if results:
        best = max(results, key=lambda x: x['sharpe'])
        print(f"\nBest: {best['symbol']} (Sharpe: {best['sharpe']:.2f}, CAGR: {best['cagr']:.2f}%)")

    print("\n" + "=" * 100)
    print("NOTE: 펀딩비율은 가정값입니다. 실제 바이낸스 펀딩비 데이터 사용 권장.")
    print("=" * 100)


if __name__ == "__main__":
    main()
