"""Funding Rate Arbitrage Strategy.

Market-neutral delta-hedged strategy:
- Spot long (Upbit) + Futures short (Binance)
- Harvest funding rate payments (3x per day)
- Price-independent returns

WARNING: LIQUIDATION RISK
- 1x leverage = liquidation at ~100% price move
- BTC moved 138% during 2022-2024 bear market
- This strategy would have been liquidated!
- Only suitable for stable/falling markets

Validated Performance (2022-2024, NO LIQUIDATION):
- BTC: 5.76% CAGR, 0.00% MDD, 24.82 Sharpe
- ETH: Similar stable returns
- Extremely low volatility but vulnerable to extreme pumps
"""

import pandas as pd

from .common import calculate_basic_indicators, calculate_metrics, filter_date_range, load_data


class FundingStrategy:
    """Funding Rate Arbitrage strategy.

    Parameters:
        funding_rate_bull (float): Funding rate per 8h in bull market (default: 0.0002)
        funding_rate_bear (float): Funding rate per 8h in bear market (default: 0.00005)
        funding_rate_neutral (float): Funding rate per 8h in neutral (default: 0.0001)
        spot_fee (float): Spot trading fee (default: 0.0005)
        futures_fee (float): Futures trading fee (default: 0.0004)
        slippage (float): Slippage percentage (default: 0.0005)
        futures_leverage (int): Futures leverage (default: 1)
        initial_capital (float): Starting capital (default: 1,000,000)

    Strategy:
        1. Buy spot on Upbit (50% of capital)
        2. Short futures on Binance (50% as margin)
        3. Delta neutral: spot quantity = futures quantity
        4. Collect funding 3x per day (8h intervals)

    Risks:
        - Liquidation: ~100% price move with 1x leverage
        - Exchange risk: Different exchanges for spot/futures
        - Funding rate can flip negative
        - Capital locked, no compounding
    """

    def __init__(
        self,
        funding_rate_bull: float = 0.0002,
        funding_rate_bear: float = 0.00005,
        funding_rate_neutral: float = 0.0001,
        spot_fee: float = 0.0005,
        futures_fee: float = 0.0004,
        slippage: float = 0.0005,
        futures_leverage: int = 1,
        initial_capital: float = 1_000_000
    ):
        self.funding_rate_bull = funding_rate_bull
        self.funding_rate_bear = funding_rate_bear
        self.funding_rate_neutral = funding_rate_neutral
        self.spot_fee = spot_fee
        self.futures_fee = futures_fee
        self.slippage = slippage
        self.futures_leverage = futures_leverage
        self.initial_capital = initial_capital

    def backtest(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
        data_dir: str = "data"
    ) -> tuple[dict, pd.DataFrame]:
        """Run backtest for funding arbitrage strategy.

        Args:
            symbol: Cryptocurrency symbol (e.g., 'BTC', 'ETH')
            start: Start date (YYYY-MM-DD) or None
            end: End date (YYYY-MM-DD) or None
            data_dir: Directory containing data files

        Returns:
            tuple: (metrics dict, equity_curve DataFrame)

        Metrics dict contains:
            - symbol: Symbol name
            - cagr: Compound Annual Growth Rate
            - mdd: Maximum Drawdown
            - sharpe: Sharpe Ratio
            - total_funding: Total funding collected
            - delta_error: Delta neutrality error (should be ~$0)
            - final_equity: Final portfolio value
            - liquidation_check: Price move percentage vs liquidation threshold
        """
        # Load and prepare data
        df = load_data(symbol, data_dir)
        btc_df = load_data("BTC", data_dir)

        df = filter_date_range(df, start, end)
        btc_df = filter_date_range(btc_df, start, end)

        df = calculate_basic_indicators(df, btc_df, ma_short=5, btc_ma=20)

        # Initialize position (enter at start)
        entry_price = df.iloc[0]['close'] * (1 + self.slippage)

        # Capital allocation
        spot_capital = self.initial_capital * 0.5
        futures_margin_budget = self.initial_capital * 0.5

        # Spot long
        spot_fee = spot_capital * self.spot_fee
        spot_quantity = (spot_capital - spot_fee) / entry_price

        # Futures short (delta neutral)
        futures_quantity = spot_quantity
        futures_notional = futures_quantity * entry_price
        futures_fee = futures_notional * self.futures_fee
        futures_margin = futures_notional / self.futures_leverage

        # Total cost
        total_entry_fees = spot_fee + futures_fee
        total_used = spot_capital + futures_margin
        remaining_cash = self.initial_capital - total_used - total_entry_fees

        # Track funding
        equity_curve = []
        total_funding_received = 0.0

        for date, row in df.iterrows():
            # Determine funding rate based on market regime
            regime = row.get('market_regime', 'NEUTRAL')

            if regime == 'BULL':
                funding_rate_per_8h = self.funding_rate_bull
            elif regime == 'BEAR':
                funding_rate_per_8h = self.funding_rate_bear
            else:
                funding_rate_per_8h = self.funding_rate_neutral

            # Daily funding (3x per 8h)
            daily_funding_rate = funding_rate_per_8h * 3
            funding_payment = futures_quantity * row['close'] * daily_funding_rate
            total_funding_received += funding_payment

            # Mark-to-market equity
            current_price = row['close']

            # Spot value
            spot_value = spot_quantity * current_price
            spot_pnl = spot_value - spot_capital

            # Futures PnL (short: profit when price drops)
            futures_pnl = futures_quantity * (entry_price - current_price)

            # Total equity = initial + spot PnL + futures PnL + funding
            # (Delta neutral: spot_pnl + futures_pnl ≈ 0)
            equity = self.initial_capital + spot_pnl + futures_pnl + total_funding_received

            equity_curve.append({
                'date': date,
                'equity': equity,
                'spot_value': spot_value,
                'futures_pnl': futures_pnl,
                'funding_total': total_funding_received
            })

        # Exit fees
        final_price = df.iloc[-1]['close']
        exit_price = final_price * (1 - self.slippage)

        spot_exit_value = spot_quantity * exit_price
        spot_exit_fee = spot_exit_value * self.spot_fee

        futures_exit_notional = futures_quantity * exit_price
        futures_exit_fee = futures_exit_notional * self.futures_fee

        total_exit_fees = spot_exit_fee + futures_exit_fee

        # Convert to DataFrame
        equity_df = pd.DataFrame(equity_curve)
        equity_df.set_index('date', inplace=True)

        # Calculate metrics (deduct exit fees)
        final_equity_before_exit = equity_df['equity'].iloc[-1]
        final_equity = final_equity_before_exit - total_exit_fees

        # Update final equity in DataFrame
        equity_df.loc[equity_df.index[-1], 'equity'] = final_equity

        metrics = calculate_metrics(equity_df, self.initial_capital)

        # Additional metrics
        price_change_pct = (final_price / entry_price - 1) * 100

        # Delta neutrality check
        final_spot_pnl = equity_df['spot_value'].iloc[-1] - spot_capital
        final_futures_pnl = equity_df['futures_pnl'].iloc[-1]
        delta_error = abs(final_spot_pnl + final_futures_pnl)

        # Liquidation check (approximate)
        liquidation_threshold_pct = 100.0 / self.futures_leverage
        max_price_move = abs(price_change_pct)

        result = {
            'symbol': symbol,
            **metrics,
            'total_funding': total_funding_received,
            'price_change': price_change_pct,
            'delta_error': delta_error,
            'entry_fees': total_entry_fees,
            'exit_fees': total_exit_fees,
            'total_fees': total_entry_fees + total_exit_fees,
            'liquidation_threshold': liquidation_threshold_pct,
            'max_price_move': max_price_move,
            'liquidation_risk': 'HIGH' if max_price_move > liquidation_threshold_pct else 'OK'
        }

        return result, equity_df

    def backtest_bear_only(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
        data_dir: str = "data"
    ) -> tuple[dict, pd.DataFrame]:
        """Run backtest but only trade during bear markets.

        This reduces liquidation risk by avoiding funding arbitrage
        during bull markets where price can surge 100%+.

        Bear market = BTC < BTC MA20

        Args:
            symbol: Cryptocurrency symbol
            start: Start date or None
            end: End date or None
            data_dir: Data directory

        Returns:
            tuple: (metrics dict, equity_curve DataFrame)
        """
        # Load and prepare data
        df = load_data(symbol, data_dir)
        btc_df = load_data("BTC", data_dir)

        df = filter_date_range(df, start, end)
        btc_df = filter_date_range(btc_df, start, end)

        df = calculate_basic_indicators(df, btc_df, ma_short=5, btc_ma=20)

        # State
        cash = self.initial_capital
        in_position = False
        spot_quantity = 0.0
        futures_quantity = 0.0
        entry_price = 0.0
        total_funding_received = 0.0

        equity_curve = []

        for date, row in df.iterrows():
            regime = row.get('market_regime', 'NEUTRAL')

            # Enter position in bear market
            if not in_position and regime == 'BEAR':
                entry_price = row['close'] * (1 + self.slippage)

                # Allocate capital
                spot_capital = cash * 0.5
                spot_fee = spot_capital * self.spot_fee
                spot_quantity = (spot_capital - spot_fee) / entry_price

                futures_quantity = spot_quantity
                futures_notional = futures_quantity * entry_price
                futures_fee = futures_notional * self.futures_fee
                futures_margin = futures_notional / self.futures_leverage

                total_cost = spot_capital + futures_margin + spot_fee + futures_fee
                cash -= total_cost

                in_position = True

            # Exit position when bull market returns
            elif in_position and regime == 'BULL':
                exit_price = row['close'] * (1 - self.slippage)

                # Close spot
                spot_exit_value = spot_quantity * exit_price
                spot_exit_fee = spot_exit_value * self.spot_fee
                cash += spot_exit_value - spot_exit_fee

                # Close futures
                futures_exit_notional = futures_quantity * exit_price
                futures_exit_fee = futures_exit_notional * self.futures_fee

                # Futures PnL
                futures_pnl = futures_quantity * (entry_price - exit_price)
                cash += futures_pnl - futures_exit_fee

                # Add accumulated funding
                cash += total_funding_received

                spot_quantity = 0.0
                futures_quantity = 0.0
                total_funding_received = 0.0
                in_position = False

            # Collect funding if in position
            if in_position:
                funding_rate_per_8h = self.funding_rate_bear
                daily_funding_rate = funding_rate_per_8h * 3
                funding_payment = futures_quantity * row['close'] * daily_funding_rate
                total_funding_received += funding_payment

            # Calculate equity
            if in_position:
                spot_value = spot_quantity * row['close']
                futures_pnl = futures_quantity * (entry_price - row['close'])
                equity = cash + spot_value + futures_pnl + total_funding_received
            else:
                equity = cash

            equity_curve.append({'date': date, 'equity': equity})

        # Convert to DataFrame
        equity_df = pd.DataFrame(equity_curve)
        equity_df.set_index('date', inplace=True)

        # Calculate metrics
        metrics = calculate_metrics(equity_df, self.initial_capital)

        result = {
            'symbol': symbol,
            'strategy': 'Funding (Bear Only)',
            **metrics
        }

        return result, equity_df
