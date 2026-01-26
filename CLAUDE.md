# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

VBO (Volatility Breakout) Strategy Backtest & Validation - A comprehensive research project analyzing VBO trading strategies across 5 major cryptocurrencies (BTC, ETH, XRP, TRX, ADA) with rigorous validation methodology.

## Core Research Files

### Main Backtest Scripts

1. **backtest_vbo_comparison.py** - Single coin VBO strategy comparison
   - Tests VBO strategy on 5 individual coins
   - Calculates correlation matrix between strategies
   - Output: CAGR, MDD, Sharpe, trades, win rate

2. **backtest_vbo_portfolio.py** - Portfolio combination backtests
   - Tests all 26 combinations (2, 3, 4, 5 coin portfolios)
   - Equal-weight allocation (1/N of equity per strategy)
   - Output: Best combinations by Sharpe, CAGR, MDD

3. **check_overfitting.py** - Overfitting validation
   - Train/Test split (2017-2021 vs 2022-2024)
   - Year-by-year consistency (2018-2025)
   - Identifies performance degradation

4. **test_parameter_sensitivity.py** - Parameter sensitivity analysis
   - Tests 20 parameter combinations (MA3-10 × BTC_MA10-30)
   - Measures stability near default parameters
   - Output: Parameter ranking, variation metrics

### Utility Scripts

- **fetcher.py** - Downloads OHLCV data from Upbit
- **bot.py** - Live trading bot (production-ready)

## Strategy Logic (V10)

### Entry Conditions (ALL must be true)
1. Daily high >= Target price (Open + (Prev High - Prev Low) × 0.5)
2. Previous BTC close > Previous BTC MA20

### Exit Conditions
1. Previous close < Previous MA5

### Execution Prices
- Buy: Target × (1 + 0.0005) slippage
- Sell: Open × (1 - 0.0005) slippage
- Fee: 0.05%

## Parameters

**Default (Validated):**
- MA_SHORT = 5 (coin MA, exit only)
- BTC_MA = 20 (Bitcoin market filter, entry only)
- NOISE_RATIO = 0.5 (VBO multiplier)

**Risk:**
- FEE = 0.0005 (0.05%)
- SLIPPAGE = 0.0005 (0.05%)

## Commands

```bash
# Install dependencies
pip install pandas numpy pyupbit

# Download data
python fetcher.py

# Run backtests
python backtest_vbo_comparison.py              # Single coins
python backtest_vbo_portfolio.py                # All portfolios
python check_overfitting.py                     # Validation
python test_parameter_sensitivity.py            # Parameter test

# Specific period
python backtest_vbo_portfolio.py --start 2020-01-01 --end 2024-12-31

# Live trading (requires .env)
python bot.py
```

## Key Research Findings

### Best Strategy: V10 with BTC+ETH Portfolio
- CAGR: 113.3% (full period)
- MDD: -21.2%
- Sharpe: 2.28 (highest risk-adjusted return)
- Win rate: 100% (all years positive, worst year +5.4%)

### Validation Results
✅ No look-ahead bias (all indicators use shift(1))
✅ Simpler than V5 (2 entry conditions vs 4)
✅ Better performance than V5 (+20% CAGR, +0.09 Sharpe)
✅ 100% win rate across all years

### Overfitting Risk: VERY LOW
- Simplest strategy among all versions (2 entry conditions)
- Traditional values (MA5, BTC MA20)
- No optimization performed
- Robust across all portfolio combinations

## Code Architecture

### Backtest Flow
1. Load data (CSV files from data/)
2. Calculate indicators (MA, target price)
3. Simulate trading (buy/sell logic)
4. Calculate metrics (CAGR, MDD, Sharpe)
5. Output results

### Key Design Decisions
- All technical indicators use shift(1) to prevent look-ahead bias
- Portfolio allocation calculated once at day start (no order dependency)
- Prices include slippage simulation
- Equity curve tracked daily for MDD calculation

### Common Pitfalls to Avoid
❌ Don't use current day data for signals
❌ Don't recalculate equity during buy loop
❌ Don't assume all data is aligned (use common dates)
❌ Don't ignore transaction costs

## Data Structure

```
data/
├── BTC.csv   # Bitcoin OHLCV
├── ETH.csv   # Ethereum OHLCV
├── XRP.csv   # Ripple OHLCV
├── TRX.csv   # Tron OHLCV
└── ADA.csv   # Cardano OHLCV

CSV format:
datetime,open,high,low,close,volume
2017-01-01 00:00:00,1000.0,1100.0,950.0,1050.0,1000000
...
```

## Testing & Validation

When making changes to strategy code:

1. **Check for look-ahead bias**
   - All signals must use shift(1)
   - No future data in decision making

2. **Verify order execution**
   - Buy at target price
   - Sell at open (next day)
   - Include slippage and fees

3. **Test on multiple periods**
   - Full period (inception~)
   - Test period (2022-2024)
   - Recent year (2025)

4. **Compare with baseline**
   - Single coin strategies
   - Buy & hold benchmark

## Performance Benchmarks

Expected results for V10 BTC+ETH portfolio (full period):
- CAGR: ~113%
- MDD: ~-21%
- Sharpe: ~2.28
- Win Rate: 100% (all years positive)

If results deviate significantly, check for bugs.

## Production Bot Setup

For live trading with bot.py:

1. Create `.env` file with Upbit API keys
2. Set SYMBOLS=BTC,ETH (recommended pair)
3. Set MA_SHORT=5, BTC_MA=20
4. Configure Telegram notifications
5. Test in paper trading first

See README.md for detailed .env configuration.
