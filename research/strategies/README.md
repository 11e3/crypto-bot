# Trading Strategies Module

Modular, reusable cryptocurrency trading strategy implementations.

## Overview

This package provides clean, well-tested strategy classes that share common utilities and eliminate code duplication. Each strategy is self-contained with clear interfaces.

## Installation

```bash
pip install pandas numpy
```

## Quick Start

```python
from strategies import VBOStrategy, FundingStrategy, BidirectionalVBOStrategy

# VBO strategy (recommended)
vbo = VBOStrategy()
metrics, equity_df = vbo.backtest('BTC', start='2022-01-01', end='2024-12-31')
print(f"CAGR: {metrics['cagr']:.2f}%, Sharpe: {metrics['sharpe']:.2f}")

# Portfolio backtest
metrics, equity_df = vbo.backtest_portfolio(['BTC', 'ETH'], start='2022-01-01')
```

## Available Strategies

### 1. VBOStrategy - Volatility Breakout (RECOMMENDED)

**Best risk-adjusted returns with lowest drawdown.**

```python
strategy = VBOStrategy(
    ma_short=5,        # MA period for trend
    btc_ma=20,         # BTC MA for market regime
    noise_ratio=0.5,   # Volatility multiplier
    fee=0.0005,        # 0.05% trading fee
    slippage=0.0005    # 0.05% slippage
)

# Single coin
metrics, equity_df = strategy.backtest('ETH')

# Portfolio (recommended)
metrics, equity_df = strategy.backtest_portfolio(['BTC', 'ETH'])
```

**Performance (2022-2024):**
- BTC: 58.60% CAGR, -13.02% MDD, 2.03 Sharpe
- ETH: 43.12% CAGR, -19.73% MDD, 1.43 Sharpe
- BTC+ETH: 51.92% CAGR, -14.95% MDD, 1.92 Sharpe

**Entry:** Price breaks above volatility target in bull market
**Exit:** Trend reversal or BTC regime change
**Validation:** 8/8 years profitable, low parameter sensitivity

---

### 2. FundingStrategy - Funding Rate Arbitrage

**Market-neutral strategy with extreme liquidation risk.**

```python
strategy = FundingStrategy(
    funding_rate_bull=0.0002,    # 0.02% per 8h in bull
    funding_rate_bear=0.00005,   # 0.005% per 8h in bear
    spot_fee=0.0005,             # Upbit spot fee
    futures_fee=0.0004,          # Binance futures fee
    futures_leverage=1           # 1x leverage (safer)
)

# Always-on arbitrage
metrics, equity_df = strategy.backtest('BTC')

# Bear-only (safer)
metrics, equity_df = strategy.backtest_bear_only('BTC')
```

**Performance (2022-2024):**
- BTC: 5.76% CAGR, 0.00% MDD, 24.82 Sharpe
- Extremely stable but low absolute returns

**Strategy:** Delta-neutral spot long + futures short
**Income:** Collect funding 3x per day (8h intervals)

**⚠️ CRITICAL RISK:**
- **Liquidation at ~100% price move with 1x leverage**
- **BTC moved 138% during 2022-2024 → would liquidate!**
- Only suitable for stable/falling markets or with active risk management

---

### 3. BidirectionalVBOStrategy - Long/Short VBO

**Higher returns but significantly higher drawdowns.**

```python
strategy = BidirectionalVBOStrategy(
    ma_short=5,
    btc_ma=20,
    noise_ratio=0.5,
    fee=0.0005,
    slippage=0.0005
)

metrics, equity_df = strategy.backtest('BTC')
```

**Performance (2022-2024):**
- BTC: 85.03% CAGR, -48.23% MDD, 1.34 Sharpe
- ETH: 78.66% CAGR, -37.63% MDD, 1.60 Sharpe

**Strategy:** VBO long in bull, VBO short in bear

**⚠️ WARNING:**
- **Shorts underperform dramatically (1/7 profit of longs)**
- **Much higher MDD than VBO alone (-48% vs -13%)**
- Consider VBO + hold cash instead

---

## Module Structure

```
strategies/
├── __init__.py              # Package exports
├── common.py                # Shared utilities
│   ├── load_data()          # Data loading
│   ├── filter_date_range()  # Date filtering
│   ├── calculate_indicators()  # Technical indicators
│   ├── calculate_metrics()  # Performance metrics
│   └── analyze_trades()     # Trade statistics
├── vbo.py                   # VBO strategy
├── funding.py               # Funding arbitrage
└── bidirectional_vbo.py     # Bidirectional VBO
```

## Common Utilities

All strategies share these utilities from `strategies.common`:

```python
from strategies.common import (
    load_data,
    filter_date_range,
    calculate_basic_indicators,
    calculate_metrics,
    analyze_trades
)

# Load data
df = load_data('BTC', data_dir='data')
df = filter_date_range(df, start='2022-01-01', end='2024-12-31')

# Calculate indicators
btc_df = load_data('BTC')
df = calculate_basic_indicators(df, btc_df, ma_short=5, btc_ma=20)

# Calculate metrics from equity curve
metrics = calculate_metrics(equity_df)
# Returns: cagr, mdd, sharpe, total_return, etc.

# Analyze trades
trade_stats = analyze_trades(trades_list)
# Returns: total_trades, win_rate, avg_profit, etc.
```

## Return Values

All `backtest()` methods return:

```python
(metrics: dict, equity_df: pd.DataFrame)
```

**Metrics dict contains:**
- `symbol`: Cryptocurrency symbol
- `cagr`: Compound Annual Growth Rate (%)
- `mdd`: Maximum Drawdown (%)
- `sharpe`: Annualized Sharpe Ratio
- `total_return`: Total return (%)
- `final_equity`: Final portfolio value
- `total_trades`: Number of trades
- `win_rate`: Percentage of winning trades
- Additional strategy-specific metrics

**Equity DataFrame:**
- Index: datetime
- Columns: equity, (strategy-specific columns)

## Examples

See `example_modular_backtest.py` for comprehensive usage examples:

```bash
# Test all strategies
python example_modular_backtest.py

# Test specific strategy
python example_modular_backtest.py --strategy vbo
python example_modular_backtest.py --strategy funding
python example_modular_backtest.py --strategy bidirectional

# Compare all strategies
python example_modular_backtest.py --strategy all
```

## Recommendations

### For Most Users: VBO (BTC+ETH Portfolio)

```python
vbo = VBOStrategy()
metrics, equity_df = vbo.backtest_portfolio(['BTC', 'ETH'])
```

**Why:**
- ✓ Best risk-adjusted returns (Sharpe: 1.92)
- ✓ Lowest drawdown (-14.95%)
- ✓ 100% positive years
- ✓ Simple, robust, validated
- ✓ No liquidation risk

### For Advanced Users: Custom Combinations

You can extend the base classes or combine strategies:

```python
class MyCustomStrategy(VBOStrategy):
    def backtest(self, symbol, start=None, end=None):
        # Custom logic here
        metrics, equity_df = super().backtest(symbol, start, end)
        # Post-process
        return metrics, equity_df
```

## Data Requirements

Strategies expect CSV files in `data/` directory:

```
data/
├── BTC.csv
├── ETH.csv
├── XRP.csv
├── TRX.csv
└── ADA.csv
```

CSV format:
```csv
datetime,open,high,low,close,volume
2017-01-01 00:00:00,1000.0,1100.0,950.0,1050.0,1000000
```

Use `fetcher.py` to download data from Upbit.

## Testing

All strategies have been validated with:
- ✓ Look-ahead bias check (all indicators use shift(1))
- ✓ Train/test split validation
- ✓ Year-by-year consistency (2018-2025)
- ✓ Parameter sensitivity analysis
- ✓ Out-of-sample testing (2025)

See `check_overfitting.py` and `test_parameter_sensitivity.py` for details.

## Performance Comparison

| Strategy | CAGR | MDD | Sharpe | Risk Level |
|----------|------|-----|--------|------------|
| VBO (BTC+ETH) | 51.92% | -14.95% | 1.92 | Low |
| VBO (BTC) | 58.60% | -13.02% | 2.03 | Low |
| Bidirectional (BTC) | 85.03% | -48.23% | 1.34 | High |
| Funding (BTC) | 5.76% | 0.00% | 24.82 | **EXTREME** |

*Performance: 2022-2024 period*

## Contributing

When adding new strategies:

1. Extend the base pattern in existing strategies
2. Use shared utilities from `common.py`
3. Follow the same return format: `(metrics, equity_df)`
4. Add comprehensive docstrings
5. Validate against look-ahead bias
6. Test on multiple time periods
7. Document risks clearly

## License

Same as main repository.
