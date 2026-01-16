"""Common utilities for strategy backtesting.

Provides shared functionality used across all strategies:
- Data loading and filtering
- Technical indicator calculation
- Performance metrics (CAGR, MDD, Sharpe)
- Market regime detection
"""

from pathlib import Path
import numpy as np
import pandas as pd


# =============================================================================
# Data Loading
# =============================================================================
def load_data(symbol: str, data_dir: str = "data") -> pd.DataFrame:
    """Load OHLCV data for a single symbol.

    Args:
        symbol: Cryptocurrency symbol (e.g., 'BTC', 'ETH')
        data_dir: Directory containing CSV files

    Returns:
        DataFrame with datetime index and OHLCV columns

    Raises:
        FileNotFoundError: If data file doesn't exist
    """
    filepath = Path(data_dir) / f"{symbol}.csv"
    if not filepath.exists():
        raise FileNotFoundError(f"No data for {symbol}: {filepath}")

    df = pd.read_csv(filepath, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    df = df.sort_index()
    return df


def filter_date_range(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    """Filter dataframe by date range.

    Args:
        df: DataFrame with datetime index
        start: Start date (YYYY-MM-DD) or None for no start limit
        end: End date (YYYY-MM-DD) or None for no end limit

    Returns:
        Filtered DataFrame
    """
    if start:
        df = df[df.index >= pd.to_datetime(start)]
    if end:
        df = df[df.index <= pd.to_datetime(end)]
    return df


# =============================================================================
# Technical Indicators
# =============================================================================
def calculate_basic_indicators(
    df: pd.DataFrame,
    btc_df: pd.DataFrame,
    ma_short: int = 5,
    btc_ma: int = 20
) -> pd.DataFrame:
    """Calculate basic technical indicators for VBO strategy.

    Adds the following columns to df:
    - ma5: Short-term moving average
    - prev_high, prev_low, prev_close, prev_ma5: Previous day values
    - prev_btc_close, prev_btc_ma: Bitcoin indicators for market regime
    - market_regime: 'BULL' if BTC > BTC_MA, else 'BEAR'

    Args:
        df: OHLCV DataFrame for the coin
        btc_df: OHLCV DataFrame for Bitcoin
        ma_short: Short MA period (default: 5)
        btc_ma: Bitcoin MA period for market filter (default: 20)

    Returns:
        DataFrame with added indicator columns
    """
    df = df.copy()
    btc_df = btc_df.copy()

    # Align BTC data with coin data
    btc_aligned = btc_df.reindex(df.index, method='ffill')

    # Calculate coin MA
    df[f'ma{ma_short}'] = df['close'].rolling(window=ma_short).mean()

    # Calculate BTC MA
    btc_aligned[f'btc_ma{btc_ma}'] = btc_aligned['close'].rolling(window=btc_ma).mean()

    # Previous day values for coin
    df['prev_high'] = df['high'].shift(1)
    df['prev_low'] = df['low'].shift(1)
    df['prev_close'] = df['close'].shift(1)
    df[f'prev_ma{ma_short}'] = df[f'ma{ma_short}'].shift(1)

    # Previous day values for BTC
    df['prev_btc_close'] = btc_aligned['close'].shift(1)
    df[f'prev_btc_ma{btc_ma}'] = btc_aligned[f'btc_ma{btc_ma}'].shift(1)

    # Market regime detection
    df['market_regime'] = np.where(
        df['prev_btc_close'] > df[f'prev_btc_ma{btc_ma}'],
        'BULL',
        'BEAR'
    )

    return df


def calculate_vbo_targets(df: pd.DataFrame, noise_ratio: float = 0.5) -> pd.DataFrame:
    """Calculate VBO breakout target prices.

    Adds target_long and target_short columns for bidirectional strategies.
    For long-only VBO, use target_long.

    Args:
        df: DataFrame with prev_high and prev_low columns
        noise_ratio: Volatility multiplier (default: 0.5)

    Returns:
        DataFrame with target price columns
    """
    df = df.copy()

    # Long breakout: Open + (Prev High - Prev Low) * noise_ratio
    df['target_long'] = df['open'] + (df['prev_high'] - df['prev_low']) * noise_ratio

    # Short breakout: Open - (Prev High - Prev Low) * noise_ratio
    df['target_short'] = df['open'] - (df['prev_high'] - df['prev_low']) * noise_ratio

    return df


# =============================================================================
# Performance Metrics
# =============================================================================
def calculate_metrics(equity_df: pd.DataFrame, initial_equity: float = 1_000_000) -> dict:
    """Calculate comprehensive performance metrics.

    Args:
        equity_df: DataFrame with 'equity' column and datetime index
        initial_equity: Starting capital (default: 1M)

    Returns:
        dict containing:
        - total_return: Total return percentage
        - cagr: Compound Annual Growth Rate
        - mdd: Maximum Drawdown percentage
        - sharpe: Annualized Sharpe Ratio
        - final_equity: Final portfolio value
        - days: Number of trading days
        - years: Number of years
    """
    if len(equity_df) == 0:
        return {
            'total_return': 0.0,
            'cagr': 0.0,
            'mdd': 0.0,
            'sharpe': 0.0,
            'final_equity': initial_equity,
            'days': 0,
            'years': 0.0
        }

    final_equity = equity_df['equity'].iloc[-1]
    initial_equity = equity_df['equity'].iloc[0] if len(equity_df) > 0 else initial_equity

    # Total return
    total_return = (final_equity / initial_equity - 1) * 100

    # CAGR (Compound Annual Growth Rate)
    days = (equity_df.index[-1] - equity_df.index[0]).days
    years = days / 365.25
    cagr = (pow(final_equity / initial_equity, 1 / years) - 1) * 100 if years > 0 else 0

    # Maximum Drawdown
    running_max = equity_df['equity'].expanding().max()
    drawdown = (equity_df['equity'] / running_max - 1) * 100
    mdd = drawdown.min()

    # Sharpe Ratio (annualized)
    equity_df = equity_df.copy()
    equity_df['daily_return'] = equity_df['equity'].pct_change()
    daily_returns = equity_df['daily_return'].dropna()

    if len(daily_returns) > 0 and daily_returns.std() > 0:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365)
    else:
        sharpe = 0.0

    return {
        'total_return': total_return,
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
        'final_equity': final_equity,
        'days': days,
        'years': years
    }


def analyze_trades(trades: list[dict]) -> dict:
    """Analyze trade performance.

    Args:
        trades: List of trade dicts with 'profit' and 'profit_pct' keys

    Returns:
        dict containing:
        - total_trades: Number of trades
        - winning_trades: Number of profitable trades
        - win_rate: Percentage of winning trades
        - avg_profit: Average profit per trade
        - avg_profit_pct: Average profit percentage
        - total_profit: Sum of all profits
    """
    if not trades:
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'win_rate': 0.0,
            'avg_profit': 0.0,
            'avg_profit_pct': 0.0,
            'total_profit': 0.0
        }

    total_trades = len(trades)
    winning_trades = len([t for t in trades if t.get('profit', 0) > 0])
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

    profits = [t.get('profit', 0) for t in trades]
    profit_pcts = [t.get('profit_pct', 0) for t in trades]

    return {
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'win_rate': win_rate,
        'avg_profit': np.mean(profits) if profits else 0.0,
        'avg_profit_pct': np.mean(profit_pcts) if profit_pcts else 0.0,
        'total_profit': sum(profits)
    }


# =============================================================================
# Market Regime Analysis
# =============================================================================
def get_regime_stats(equity_df: pd.DataFrame) -> dict:
    """Calculate statistics by market regime.

    Args:
        equity_df: DataFrame with 'strategy' column indicating active strategy

    Returns:
        dict with regime statistics
    """
    if 'strategy' not in equity_df.columns:
        return {}

    total_days = len(equity_df)
    regime_counts = equity_df['strategy'].value_counts()

    stats = {'total_days': total_days}

    for regime, count in regime_counts.items():
        if regime is not None:
            stats[f'{regime.lower()}_days'] = count
            stats[f'{regime.lower()}_pct'] = (count / total_days * 100) if total_days > 0 else 0

    return stats
