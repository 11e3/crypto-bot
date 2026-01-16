"""Hybrid VBO + Funding Strategy.

Adaptive strategy that switches based on market regime:
- Bull market (BTC > MA20): VBO long (high returns)
- Bear market (BTC < MA20): Funding arbitrage (stable returns + no liquidation risk)

Benefits:
- VBO captures bull market trends
- Funding generates income in bear markets
- No liquidation risk (funding only active during downtrends)
- All-weather strategy
"""

import pandas as pd
import numpy as np
from .common import (
    load_data,
    filter_date_range,
    calculate_basic_indicators,
    calculate_vbo_targets,
    calculate_metrics
)


class HybridVBOFundingStrategy:
    """Hybrid VBO + Funding Arbitrage strategy.

    Simple approach:
    - In bull market: Run VBO strategy
    - In bear market: Run funding arbitrage strategy
    - On regime change: Close current position, switch to new strategy
    """

    def __init__(
        self,
        ma_short: int = 5,
        btc_ma: int = 20,
        noise_ratio: float = 0.5,
        fee: float = 0.0005,
        slippage: float = 0.0005,
        funding_rate_bear: float = 0.00005,
        futures_leverage: int = 1,
        initial_capital: float = 1_000_000
    ):
        self.ma_short = ma_short
        self.btc_ma = btc_ma
        self.noise_ratio = noise_ratio
        self.fee = fee
        self.slippage = slippage
        self.funding_rate_bear = funding_rate_bear
        self.futures_leverage = futures_leverage
        self.initial_capital = initial_capital

    def backtest(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
        data_dir: str = "data"
    ) -> tuple[dict, pd.DataFrame]:
        """Run hybrid backtest."""
        # Load data
        df = load_data(symbol, data_dir)
        btc_df = load_data("BTC", data_dir)
        df = filter_date_range(df, start, end)
        btc_df = filter_date_range(btc_df, start, end)
        df = calculate_basic_indicators(df, btc_df, self.ma_short, self.btc_ma)
        df = calculate_vbo_targets(df, self.noise_ratio)

        # State
        cash = self.initial_capital

        # VBO state
        vbo_qty = 0.0
        vbo_entry = 0.0

        # Funding state
        funding_spot_qty = 0.0
        funding_futures_qty = 0.0
        funding_entry = 0.0
        funding_collected = 0.0

        equity_curve = []
        trades = []

        for date, row in df.iterrows():
            if pd.isna(row[f'prev_ma{self.ma_short}']) or pd.isna(row[f'prev_btc_ma{self.btc_ma}']):
                equity_curve.append({'date': date, 'equity': cash, 'strategy': None})
                continue

            regime = row['market_regime']

            # === BULL MARKET ===
            if regime == 'BULL':
                # Close funding if active
                if funding_spot_qty > 0:
                    close_price = row['close'] * (1 - self.slippage)
                    spot_value = funding_spot_qty * close_price
                    spot_fee = spot_value * self.fee
                    futures_pnl = funding_futures_qty * (funding_entry - close_price)
                    futures_fee = abs(futures_pnl) * self.fee if futures_pnl < 0 else 0
                    cash += spot_value - spot_fee + futures_pnl - futures_fee + funding_collected

                    trades.append({'date': date, 'strategy': 'FUNDING', 'action': 'exit'})
                    funding_spot_qty = 0.0
                    funding_futures_qty = 0.0
                    funding_entry = 0.0
                    funding_collected = 0.0

                # Run VBO logic
                # Exit VBO
                if vbo_qty > 0:
                    exit_signal = (
                        row['prev_close'] < row[f'prev_ma{self.ma_short}'] or
                        row['prev_btc_close'] < row[f'prev_btc_ma{self.btc_ma}']
                    )
                    if exit_signal:
                        exit_price = row['open'] * (1 - self.slippage)
                        exit_value = vbo_qty * exit_price
                        exit_fee = exit_value * self.fee
                        cash += exit_value - exit_fee
                        trades.append({'date': date, 'strategy': 'VBO', 'action': 'exit'})
                        vbo_qty = 0.0
                        vbo_entry = 0.0

                # Enter VBO
                if vbo_qty == 0 and cash > 0:
                    entry_signal = (
                        row['high'] >= row['target_long'] and
                        row['prev_close'] > row[f'prev_ma{self.ma_short}'] and
                        row['prev_btc_close'] > row[f'prev_btc_ma{self.btc_ma}']
                    )
                    if entry_signal:
                        entry_price = max(row['target_long'], row['open']) * (1 + self.slippage)
                        entry_fee = cash * self.fee
                        vbo_qty = (cash - entry_fee) / entry_price
                        vbo_entry = entry_price
                        cash = 0.0
                        trades.append({'date': date, 'strategy': 'VBO', 'action': 'entry'})

            # === BEAR MARKET ===
            else:
                # Close VBO if active
                if vbo_qty > 0:
                    close_price = row['open'] * (1 - self.slippage)
                    close_value = vbo_qty * close_price
                    close_fee = close_value * self.fee
                    cash += close_value - close_fee
                    trades.append({'date': date, 'strategy': 'VBO', 'action': 'exit'})
                    vbo_qty = 0.0
                    vbo_entry = 0.0

                # Run Funding logic
                if funding_spot_qty > 0:
                    # Collect funding
                    daily_funding = self.funding_rate_bear * 3 * funding_futures_qty * row['close']
                    funding_collected += daily_funding
                else:
                    # Enter funding
                    if cash > 1000:  # Minimum cash requirement
                        entry_price = row['close'] * (1 + self.slippage)

                        # Spot allocation
                        spot_budget = cash * 0.5
                        spot_fee = spot_budget * self.fee
                        spot_qty_temp = (spot_budget - spot_fee) / entry_price

                        # Futures allocation (delta neutral)
                        futures_qty_temp = spot_qty_temp
                        futures_notional = futures_qty_temp * entry_price
                        futures_fee = futures_notional * self.fee
                        futures_margin = futures_notional / self.futures_leverage

                        # Total cost
                        total_cost = spot_budget + futures_margin + futures_fee

                        # Only commit if we have enough cash
                        if total_cost <= cash:
                            funding_spot_qty = spot_qty_temp
                            funding_futures_qty = futures_qty_temp
                            funding_entry = entry_price
                            cash -= total_cost
                            trades.append({'date': date, 'strategy': 'FUNDING', 'action': 'entry'})

            # Calculate equity
            if vbo_qty > 0:
                equity = cash + vbo_qty * row['close']
                strategy = 'VBO'
            elif funding_spot_qty > 0:
                spot_val = funding_spot_qty * row['close']
                futures_pnl = funding_futures_qty * (funding_entry - row['close'])
                equity = cash + spot_val + futures_pnl + funding_collected
                strategy = 'FUNDING'
            else:
                equity = cash
                strategy = None

            equity_curve.append({'date': date, 'equity': equity, 'strategy': strategy})

        # Close final positions
        final_price = df.iloc[-1]['close']
        if vbo_qty > 0:
            cash += vbo_qty * final_price * (1 - self.slippage - self.fee)
        elif funding_spot_qty > 0:
            cash += funding_spot_qty * final_price * (1 - self.slippage - self.fee)
            cash += funding_futures_qty * (funding_entry - final_price) * (1 - self.fee)
            cash += funding_collected

        # Build results
        equity_df = pd.DataFrame(equity_curve).set_index('date')
        equity_df.loc[equity_df.index[-1], 'equity'] = float(cash)

        metrics = calculate_metrics(equity_df, self.initial_capital)

        vbo_days = len(equity_df[equity_df['strategy'] == 'VBO'])
        funding_days = len(equity_df[equity_df['strategy'] == 'FUNDING'])
        total_days = len(equity_df)

        return {
            'symbol': symbol,
            'strategy': 'Hybrid',
            **metrics,
            'vbo_days': vbo_days,
            'funding_days': funding_days,
            'total_days': total_days,
            'vbo_pct': (vbo_days / total_days * 100) if total_days > 0 else 0,
            'funding_pct': (funding_days / total_days * 100) if total_days > 0 else 0,
            'total_funding': funding_collected,
            'total_trades': len(trades)
        }, equity_df
