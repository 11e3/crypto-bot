"""Bidirectional VBO Strategy.

Long-short VBO strategy that adapts to market regime:
- Bull market (BTC > MA20): VBO Long (breakout upward)
- Bear market (BTC < MA20): VBO Short (breakout downward)

Requires futures trading (Binance).

WARNING: Short trades underperform significantly
- Longs: 2.59% avg profit per trade (2022-2024)
- Shorts: 0.38% avg profit per trade (1/7 of longs!)
- Shorts have 1/7 the efficiency in bear markets
- Consider VBO long-only or hold cash in bear instead

Validated Performance (2022-2024):
- BTC: 85.03% CAGR, -48.23% MDD, 1.34 Sharpe
- ETH: 78.66% CAGR, -37.63% MDD, 1.60 Sharpe
- Higher returns than long-only but MUCH higher drawdowns
"""

import pandas as pd
from .common import (
    load_data,
    filter_date_range,
    calculate_basic_indicators,
    calculate_vbo_targets,
    calculate_metrics,
    analyze_trades
)


class BidirectionalVBOStrategy:
    """Bidirectional VBO trading strategy.

    Parameters:
        ma_short (int): Short MA period for trend (default: 5)
        btc_ma (int): Bitcoin MA period for regime (default: 20)
        noise_ratio (float): Volatility multiplier (default: 0.5)
        fee (float): Trading fee percentage (default: 0.0005)
        slippage (float): Slippage percentage (default: 0.0005)
        initial_capital (float): Starting capital (default: 1,000,000)

    Long Entry (Bull Market):
        - High >= Target Long
        - Prev Close > Prev MA5
        - Prev BTC Close > Prev BTC MA20

    Long Exit:
        - Prev Close < Prev MA5 OR
        - Prev BTC Close < Prev BTC MA20

    Short Entry (Bear Market):
        - Low <= Target Short
        - Prev Close < Prev MA5
        - Prev BTC Close < Prev BTC MA20

    Short Exit:
        - Prev Close > Prev MA5 OR
        - Prev BTC Close > Prev BTC MA20

    Target Prices:
        - Long: Open + (Prev High - Prev Low) × noise_ratio
        - Short: Open - (Prev High - Prev Low) × noise_ratio
    """

    def __init__(
        self,
        ma_short: int = 5,
        btc_ma: int = 20,
        noise_ratio: float = 0.5,
        fee: float = 0.0005,
        slippage: float = 0.0005,
        initial_capital: float = 1_000_000
    ):
        self.ma_short = ma_short
        self.btc_ma = btc_ma
        self.noise_ratio = noise_ratio
        self.fee = fee
        self.slippage = slippage
        self.initial_capital = initial_capital

    def backtest(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
        data_dir: str = "data"
    ) -> tuple[dict, pd.DataFrame]:
        """Run backtest for bidirectional VBO strategy.

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
            - total_trades: Number of trades
            - win_rate: Percentage of winning trades
            - long_trades: Number of long trades
            - short_trades: Number of short trades
            - final_equity: Final portfolio value
        """
        # Load and prepare data
        df = load_data(symbol, data_dir)
        btc_df = load_data("BTC", data_dir)

        df = filter_date_range(df, start, end)
        btc_df = filter_date_range(btc_df, start, end)

        df = calculate_basic_indicators(df, btc_df, self.ma_short, self.btc_ma)
        df = calculate_vbo_targets(df, self.noise_ratio)

        # Initialize backtest state
        cash = self.initial_capital
        position = 0.0  # Positive = long, Negative = short
        position_entry_price = 0.0
        position_type = None  # 'LONG' or 'SHORT'
        trades = []
        equity_curve = []

        # Main backtest loop
        for date, row in df.iterrows():
            # Skip if indicators not ready
            if pd.isna(row[f'prev_ma{self.ma_short}']) or pd.isna(row[f'prev_btc_ma{self.btc_ma}']):
                equity = cash + position * row['close']
                equity_curve.append({'date': date, 'equity': equity})
                continue

            regime = row['market_regime']

            # === SELL/COVER LOGIC ===
            if position != 0:
                sell_signal = False

                if position_type == 'LONG':
                    # Long exit
                    sell_signal = (
                        row['prev_close'] < row[f'prev_ma{self.ma_short}'] or
                        row['prev_btc_close'] < row[f'prev_btc_ma{self.btc_ma}']
                    )

                    if sell_signal:
                        exit_price = row['open'] * (1 - self.slippage)
                        exit_value = position * exit_price
                        exit_fee = exit_value * self.fee
                        cash += exit_value - exit_fee
                        profit = exit_value - position * position_entry_price - exit_fee
                        profit_pct = (exit_price / position_entry_price - 1) * 100

                else:  # SHORT
                    # Short cover
                    sell_signal = (
                        row['prev_close'] > row[f'prev_ma{self.ma_short}'] or
                        row['prev_btc_close'] > row[f'prev_btc_ma{self.btc_ma}']
                    )

                    if sell_signal:
                        exit_price = row['open'] * (1 + self.slippage)
                        exit_notional = abs(position) * exit_price
                        exit_fee = exit_notional * self.fee
                        entry_notional = abs(position) * position_entry_price
                        profit = entry_notional - exit_notional - exit_fee
                        cash += profit
                        profit_pct = (position_entry_price / exit_price - 1) * 100

                if sell_signal:
                    trades.append({
                        'date': date,
                        'type': position_type,
                        'entry_price': position_entry_price,
                        'exit_price': exit_price,
                        'profit': profit,
                        'profit_pct': profit_pct
                    })

                    position = 0.0
                    position_entry_price = 0.0
                    position_type = None

            # === BUY/SHORT LOGIC ===
            if position == 0:
                if regime == 'BULL':
                    # Long entry
                    buy_signal = (
                        row['high'] >= row['target_long'] and
                        row['prev_close'] > row[f'prev_ma{self.ma_short}'] and
                        row['prev_btc_close'] > row[f'prev_btc_ma{self.btc_ma}']
                    )

                    if buy_signal:
                        entry_price = max(row['target_long'], row['open']) * (1 + self.slippage)
                        entry_value = cash
                        entry_fee = entry_value * self.fee
                        position = (entry_value - entry_fee) / entry_price
                        position_entry_price = entry_price
                        cash = 0.0
                        position_type = 'LONG'

                else:  # BEAR
                    # Short entry
                    short_signal = (
                        row['low'] <= row['target_short'] and
                        row['prev_close'] < row[f'prev_ma{self.ma_short}'] and
                        row['prev_btc_close'] < row[f'prev_btc_ma{self.btc_ma}']
                    )

                    if short_signal:
                        entry_price = min(row['target_short'], row['open']) * (1 - self.slippage)
                        entry_value = cash
                        entry_fee = entry_value * self.fee
                        position = -(entry_value - entry_fee) / entry_price
                        position_entry_price = entry_price
                        position_type = 'SHORT'
                        # Note: cash stays as is for short (it's collateral)

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
                final_value = position * final_price * (1 - self.slippage)
                final_fee = final_value * self.fee
                cash += final_value - final_fee
            else:  # Short
                exit_notional = abs(position) * final_price * (1 + self.slippage)
                exit_fee = exit_notional * self.futures_fee if hasattr(self, 'futures_fee') else exit_notional * self.fee
                entry_notional = abs(position) * position_entry_price
                pnl = entry_notional - exit_notional - exit_fee
                cash += pnl

        # Convert to DataFrame
        equity_df = pd.DataFrame(equity_curve)
        equity_df.set_index('date', inplace=True)

        # Calculate metrics
        metrics = calculate_metrics(equity_df, self.initial_capital)
        trade_stats = analyze_trades(trades)

        # Position type breakdown
        long_trades = len([t for t in trades if t['type'] == 'LONG'])
        short_trades = len([t for t in trades if t['type'] == 'SHORT'])

        # Long vs Short performance
        long_trades_list = [t for t in trades if t['type'] == 'LONG']
        short_trades_list = [t for t in trades if t['type'] == 'SHORT']

        long_avg_profit = (
            sum(t['profit_pct'] for t in long_trades_list) / len(long_trades_list)
            if long_trades_list else 0.0
        )
        short_avg_profit = (
            sum(t['profit_pct'] for t in short_trades_list) / len(short_trades_list)
            if short_trades_list else 0.0
        )

        # Combine results
        result = {
            'symbol': symbol,
            **metrics,
            **trade_stats,
            'long_trades': long_trades,
            'short_trades': short_trades,
            'long_avg_profit_pct': long_avg_profit,
            'short_avg_profit_pct': short_avg_profit
        }

        return result, equity_df
