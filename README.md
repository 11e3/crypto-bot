# VBO Strategy Backtest & Live Trading Bot

Upbit cryptocurrency VBO (Volatility Breakout) strategy with backtesting, validation, and live trading bot.

## 📊 Strategy Overview

### Strategy Logic

**Buy Conditions (ALL must be true):**
- Daily high >= Target price (Open + (Prev High - Prev Low) × 0.5)
- Previous close > Previous MA5
- Previous BTC close > Previous BTC MA20

**Sell Conditions (ANY triggers exit):**
- Previous close < Previous MA5
- Previous BTC close < Previous BTC MA20

**Execution Prices:**
- Buy: Target price + 0.05% slippage
- Sell: Daily open - 0.05% slippage
- Fee: 0.05%

### Validated Performance (BTC+ETH Portfolio)

| Period | CAGR | MDD | Sharpe |
|--------|------|-----|--------|
| Full (2017~) | 91.1% | -21.1% | 2.15 |
| Test (2022-2024) | 51.9% | -15.0% | 1.92 |
| 2025 | 12.1% | -12.4% | 0.76 |

## 🚀 Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Or install directly
pip install pandas numpy pyupbit

# Download data
python fetcher.py
```

### Run Live Trading Bot

```bash
# 1. Setup API keys
cp .env.example .env
nano .env  # Enter your API keys

# 2. Run bot
python bot.py

# Run in background
nohup python bot.py > bot.log 2>&1 &
```

### Run Backtests

```bash
# Portfolio combination backtest
python research/backtest_vbo_portfolio.py

# Single coin strategy comparison
python research/backtest_vbo_comparison.py

# Overfitting validation
python research/check_overfitting.py

# Parameter sensitivity test
python research/test_parameter_sensitivity.py

# Specify custom period
python research/backtest_vbo_portfolio.py --start 2022-01-01 --end 2024-12-31
```

## 🤖 Live Trading Bot

### Key Features

- ✅ Multiple account support (unlimited)
- ✅ Validated VBO strategy (CAGR 91%, Sharpe 2.15)
- ✅ Real-time Telegram notifications
- ✅ Late entry protection (only enter within ±1%)
- ✅ Safe error handling (retry + exponential backoff)
- ✅ 24/7 unattended operation
- ✅ Position tracking with file persistence (restart-safe)

### Bot Structure

```
bot/
├── __init__.py    # Package exports
├── config.py      # Configuration management
├── market.py      # VBO signal calculation
├── account.py     # Order execution
├── tracker.py     # Position tracking
├── logger.py      # Trade logging
├── utils.py       # Telegram notifications
└── bot.py         # Main bot logic
```

### Position Management

- Bot only manages **coins it bought itself**
- Existing holdings are ignored (safe)
- Restored from `.positions_{account_name}.json` on restart
- Trade history: `trades_{account_name}.csv`

### Configuration (.env)

```env
# Account settings (required)
ACCOUNT_1_NAME=Main
ACCOUNT_1_ACCESS_KEY=your_access_key
ACCOUNT_1_SECRET_KEY=your_secret_key

# Telegram (recommended)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Strategy parameters (defaults recommended)
SYMBOLS=BTC,ETH
MA_SHORT=5
BTC_MA=20
NOISE_RATIO=0.5
```

### Important Notes

- ⚠️ Start with **small amounts for testing**
- ⚠️ API permissions: "View assets" + "Place orders" required
- ⚠️ Past performance does not guarantee future results
- ⚠️ Investment decisions and P&L are your own responsibility

## 📈 Research Results

### Portfolio Combination Performance

| Rank | Combination | CAGR | MDD | Sharpe |
|------|-------------|------|-----|--------|
| 🥇 | **BTC+ETH** | 91.1% | **-21.1%** | **2.15** |
| 🥈 | BTC+ETH+XRP | 101.0% | -23.6% | 1.98 |
| 🥉 | BTC+XRP | 101.9% | -36.6% | 1.74 |

**Key Findings:**
- **BTC+ETH combination is optimal** (Sharpe 2.15, MDD -21.1%)
- 2-coin portfolios are most efficient (highest Sharpe, lowest MDD)
- BTC-ETH correlation 0.73 provides proper diversification

### Strategy Improvement Attempts

Multiple improvements were tested, but **current strategy is already optimal**:

| Attempt | Result | Notes |
|---------|--------|-------|
| Pure VBO (remove MA filters) | ❌ CAGR 31%, MDD -57% | Filters essential |
| BTC filter only | ❌ MDD -41% (2x worse) | Coin MA essential |
| Volume filter added | ❌ CAGR -32% | Too many missed opportunities |
| ATR position sizing | △ Sharpe +0.02 | Marginal improvement |
| Trailing Stop -3% | ❌ Overfitted (4H validation failed) | Daily timeframe illusion |
| 4-hour timeframe | ❌ CAGR 44%, Sharpe 1.57 | Daily superior |

**Conclusion:** MA5 + BTC_MA20 combination is already optimized

## ✅ Validation Results

### Overfitting Validation

| Period | CAGR | Sharpe | Assessment |
|--------|------|--------|------------|
| Train (2017-2021) | 154.9% | 2.53 | Training |
| Test (2022-2024) | 51.9% | 1.92 | ✅ Validated |
| 2025 | 12.1% | 0.76 | ✅ OOS |

- Sharpe degradation 24% (within acceptable range)
- **8/8 years profitable** (100% win rate)
- Parameter sensitivity < 10%

### Validation Checklist

| Item | Result |
|------|--------|
| ✅ No look-ahead bias | All indicators use shift(1) |
| ✅ Backtest-bot logic match | Code review complete |
| ✅ Train/Test consistency | Sharpe degradation 24% |
| ✅ Year-by-year consistency | 8/8 years positive |
| ✅ Parameter simplicity | Only 2 parameters |
| ✅ 4-hour cross-validation | Daily timeframe superior |

**Overfitting Risk: VERY LOW** ✅

## 📁 Project Structure

```
├── bot.py                  # Live trading bot entry point
├── bot/                    # Bot package
│   ├── __init__.py
│   ├── config.py           # Configuration management
│   ├── market.py           # VBO signal calculation
│   ├── account.py          # Order execution
│   ├── tracker.py          # Position tracking
│   ├── logger.py           # Trade logging
│   ├── utils.py            # Telegram utilities
│   └── bot.py              # Main bot logic
├── research/               # Backtest research
│   ├── backtest_vbo_portfolio.py
│   ├── backtest_vbo_comparison.py
│   ├── check_overfitting.py
│   └── test_parameter_sensitivity.py
├── data/                   # OHLCV data
│   ├── BTC.csv
│   ├── ETH.csv
│   └── ...
├── fetcher.py              # Data collection
├── liquidate.py            # Emergency liquidation
└── legacy/                 # Previous research
```

## 🔬 Backtest Settings

- **Period**: 2017-01-01 ~ Present
- **Fee**: 0.05%
- **Slippage**: 0.05%
- **Initial Capital**: 1,000,000 KRW
- **Portfolio**: Equal weight (Total equity / N)

## ⚠️ Disclaimer

- Past performance does not guarantee future results
- Strategy effectiveness may decrease due to market regime changes
- Order execution may fail during extreme volatility
- Risk of principal loss exists

**Investment decisions are your own responsibility.**

---

**Last Updated**: 2025-01-15
