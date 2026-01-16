"""VBO (Volatility Breakout) Strategy.

Long-only trend-following strategy:
- Entry: Price breaks above volatility-adjusted target in bull market
- Exit: Trend reversal detected by MA or BTC regime change

Validated Performance (2022-2024):
- BTC: 61.72% CAGR, -34.86% MDD, 1.50 Sharpe
- ETH: 42.03% CAGR, -29.34% MDD, 1.12 Sharpe
- Portfolio (BTC+ETH): 51.92% CAGR, -21.17% MDD, 2.15 Sharpe
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


class VBOStrategy:
    """VBO (Volatility Breakout) trading strategy.

    Parameters:
        ma_short (int): Short MA period for trend detection (default: 5)
        btc_ma (int): Bitcoin MA period for market regime (default: 20)
        noise_ratio (float): Volatility multiplier for breakout (default: 0.5)
        fee (float): Trading fee percentage (default: 0.0005)
        slippage (float): Slippage percentage (default: 0.0005)
        initial_capital (float): Starting capital (default: 1,000,000)

    Entry Conditions (ALL must be true):
        1. Daily high >= Target price
        2. Previous close > Previous MA5
        3. Previous BTC close > Previous BTC MA20

    Exit Conditions (ANY triggers exit):
        1. Previous close < Previous MA5
        2. Previous BTC close < Previous BTC MA20

    Target Price:
        Open + (Previous High - Previous Low) × noise_ratio
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
        """Run backtest for the VBO strategy.

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
        position = 0.0
        position_entry_price = 0.0
        trades = []
        equity_curve = []

        # Main backtest loop
        for date, row in df.iterrows():
            # Skip if indicators not ready
            if pd.isna(row[f'prev_ma{self.ma_short}']) or pd.isna(row[f'prev_btc_ma{self.btc_ma}']):
                equity = cash + position * row['close']
                equity_curve.append({'date': date, 'equity': equity})
                continue

            # === SELL LOGIC ===
            if position > 0:
                sell_signal = (
                    row['prev_close'] < row[f'prev_ma{self.ma_short}'] or
                    row['prev_btc_close'] < row[f'prev_btc_ma{self.btc_ma}']
                )

                if sell_signal:
                    sell_price = row['open'] * (1 - self.slippage)
                    sell_value = position * sell_price
                    sell_fee = sell_value * self.fee
                    cash += sell_value - sell_fee

                    # Record trade
                    profit = sell_value - position * position_entry_price - sell_fee
                    profit_pct = (sell_price / position_entry_price - 1) * 100

                    trades.append({
                        'date': date,
                        'entry_price': position_entry_price,
                        'exit_price': sell_price,
                        'profit': profit,
                        'profit_pct': profit_pct,
                        'action': 'sell'
                    })

                    position = 0.0
                    position_entry_price = 0.0

            # === BUY LOGIC ===
            if position == 0:
                buy_signal = (
                    row['high'] >= row['target_long'] and
                    row['prev_close'] > row[f'prev_ma{self.ma_short}'] and
                    row['prev_btc_close'] > row[f'prev_btc_ma{self.btc_ma}']
                )

                if buy_signal:
                    buy_price = max(row['target_long'], row['open']) * (1 + self.slippage)
                    buy_value = cash
                    buy_fee = buy_value * self.fee
                    position = (buy_value - buy_fee) / buy_price
                    position_entry_price = buy_price
                    cash = 0.0

            # Record equity
            equity = cash + position * row['close']
            equity_curve.append({'date': date, 'equity': equity})

        # Close final position
        if position > 0:
            final_price = df.iloc[-1]['close']
            final_value = position * final_price * (1 - self.slippage)
            final_fee = final_value * self.fee
            cash += final_value - final_fee

        # Convert to DataFrame
        equity_df = pd.DataFrame(equity_curve)
        equity_df.set_index('date', inplace=True)

        # Calculate metrics
        metrics = calculate_metrics(equity_df, self.initial_capital)
        trade_stats = analyze_trades(trades)

        # Combine results
        result = {
            'symbol': symbol,
            **metrics,
            **trade_stats
        }

        return result, equity_df

    def backtest_portfolio(
        self,
        symbols: list[str],
        start: str | None = None,
        end: str | None = None,
        data_dir: str = "data"
    ) -> tuple[dict, pd.DataFrame]:
        """Run portfolio backtest with multiple symbols.

        Allocates capital equally (1/N) across all strategies.

        Args:
            symbols: List of cryptocurrency symbols
            start: Start date (YYYY-MM-DD) or None
            end: End date (YYYY-MM-DD) or None
            data_dir: Directory containing data files

        Returns:
            tuple: (metrics dict, equity_curve DataFrame)
        """
        # Load and prepare data for all symbols
        data = {}
        btc_df = load_data("BTC", data_dir)
        btc_df = filter_date_range(btc_df, start, end)

        for symbol in symbols:
            df = load_data(symbol, data_dir)
            df = filter_date_range(df, start, end)
            df = calculate_basic_indicators(df, btc_df, self.ma_short, self.btc_ma)
            df = calculate_vbo_targets(df, self.noise_ratio)
            data[symbol] = df

        # Get common dates
        all_dates = set(data[list(symbols)[0]].index)
        for df in data.values():
            all_dates &= set(df.index)
        all_dates = sorted(all_dates)

        if not all_dates:
            raise ValueError("No common dates across all symbols")

        # Initialize portfolio
        cash = self.initial_capital
        positions = {symbol: 0.0 for symbol in symbols}
        equity_curve = []
        n_strategies = len(symbols)

        # Main backtest loop
        for date in all_dates:
            prices = {symbol: data[symbol].loc[date] for symbol in symbols}

            # Check if indicators ready
            valid = all(
                not pd.isna(prices[s][f'prev_ma{self.ma_short}']) and
                not pd.isna(prices[s][f'prev_btc_ma{self.btc_ma}'])
                for s in symbols
            )

            if not valid:
                equity = cash + sum(positions[s] * prices[s]['close'] for s in symbols)
                equity_curve.append({'date': date, 'equity': equity})
                continue

            # === SELL LOGIC ===
            for symbol in symbols:
                if positions[symbol] > 0:
                    row = prices[symbol]
                    sell_signal = (
                        row['prev_close'] < row[f'prev_ma{self.ma_short}'] or
                        row['prev_btc_close'] < row[f'prev_btc_ma{self.btc_ma}']
                    )

                    if sell_signal:
                        sell_price = row['open'] * (1 - self.slippage)
                        sell_value = positions[symbol] * sell_price
                        sell_fee = sell_value * self.fee
                        cash += sell_value - sell_fee
                        positions[symbol] = 0.0

            # === BUY LOGIC ===
            total_equity_start = cash + sum(positions[s] * prices[s]['open'] for s in symbols)
            target_allocation = total_equity_start / n_strategies

            for symbol in symbols:
                if positions[symbol] == 0:
                    row = prices[symbol]
                    buy_signal = (
                        row['high'] >= row['target_long'] and
                        row['prev_close'] > row[f'prev_ma{self.ma_short}'] and
                        row['prev_btc_close'] > row[f'prev_btc_ma{self.btc_ma}']
                    )

                    if buy_signal:
                        buy_value = min(target_allocation, cash)
                        if buy_value > 0:
                            buy_price = max(row['target_long'], row['open']) * (1 + self.slippage)
                            buy_fee = buy_value * self.fee
                            positions[symbol] = (buy_value - buy_fee) / buy_price
                            cash -= buy_value

            # Record equity
            equity = cash + sum(positions[s] * prices[s]['close'] for s in symbols)
            equity_curve.append({'date': date, 'equity': equity})

        # Convert to DataFrame
        equity_df = pd.DataFrame(equity_curve)
        equity_df.set_index('date', inplace=True)

        # Calculate metrics
        metrics = calculate_metrics(equity_df, self.initial_capital)

        result = {
            'symbols': symbols,
            'symbols_str': '+'.join(symbols),
            'n_coins': len(symbols),
            **metrics
        }

        return result, equity_df
