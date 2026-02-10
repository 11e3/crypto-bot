# Crypto Bot

**Lightweight live trading bot for KRW crypto pairs on Upbit.**

Part of: [crypto-quant-system](https://github.com/11e3/crypto-quant-system) / **[crypto-bot](https://github.com/11e3/crypto-bot)** / [crypto-regime-classifier-ml](https://github.com/11e3/crypto-regime-classifier-ml)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/Docker-slim-blue.svg)](https://hub.docker.com/)
[![GCP](https://img.shields.io/badge/GCP-e2--micro-yellow.svg)](https://cloud.google.com/)

## Ecosystem

```
crypto-quant-system          Dashboard & backtester
  └── Bot Monitor            Reads trade logs from GCS ◄──────┐
                                                               │
crypto-bot (this repo)       Live trading bot                  │
  ├── Auto trading           Executes VBO strategy             │
  └── GCS log sync           Uploads logs via gsutil ──────────┘

crypto-regime-classifier-ml  Market regime classifier
  └── Model export           Uploads .pkl to GCS
```

## Strategy

**VBO V1.1** (Volatility Breakout with MA filters)

| Component | Rule |
|-----------|------|
| Entry signal | `open + prev_range * K` breakout (`K=0.5`) |
| Entry filter | BTC `close > MA20` (market regime) |
| Exit signal | Coin `prev_close < prev_EMA5` |
| Allocation | `equity / N` per symbol |
| Late entry | Reject if price deviates > ±1% from target |

Strategy logic is in `bot/market.py` (121 lines). Research and backtesting iterations are in `research/`.

## Quick Start

### Local

```bash
pip install -r requirements.txt
cp .env.example .env   # add API keys
python bot.py
```

### Docker

```bash
docker-compose up -d --build

# Hot reload (no rebuild needed)
git pull && docker-compose restart
```

### GCP e2-micro

```bash
# 1. Install Docker
sudo apt update && sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER

# 2. Clone and configure
cd /opt && sudo git clone https://github.com/11e3/crypto-bot.git
cd crypto-bot && sudo cp .env.example .env
sudo nano .env  # add API keys

# 3. Create systemd service
sudo tee /etc/systemd/system/bot.service << 'EOF'
[Unit]
Description=VBO Trading Bot
After=docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/opt/crypto-bot
ExecStart=/usr/bin/docker-compose up
ExecStop=/usr/bin/docker-compose down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 4. Start
sudo systemctl daemon-reload
sudo systemctl enable bot
sudo systemctl start bot

# 5. GCS log sync (crontab -e)
*/5 * * * * gsutil -m rsync -r /opt/crypto-bot/logs gs://bot-log/logs/
```

## Configuration

### Environment Variables (.env)

```env
# Exchange API (supports multiple accounts)
ACCOUNT_1_NAME=account1
ACCOUNT_1_ACCESS_KEY=your_access_key
ACCOUNT_1_SECRET_KEY=your_secret_key

ACCOUNT_2_NAME=account2
ACCOUNT_2_ACCESS_KEY=your_access_key_2
ACCOUNT_2_SECRET_KEY=your_secret_key_2

# Telegram notifications (recommended)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Strategy parameters
SYMBOLS=BTC,ETH
MA_SHORT=5
BTC_MA=20
NOISE_RATIO=0.5
```

### Trading Constants (config.py)

| Constant | Value | Description |
|----------|-------|-------------|
| `FEE` | 0.05% | Upbit trading fee |
| `MIN_ORDER_KRW` | 5,000 | Minimum order size |
| `LATE_ENTRY_PCT` | 1.0% | Max deviation from target |
| `CHECK_INTERVAL_SEC` | 1 | Main loop interval |

## GCS Integration

Trade logs are synced to GCS via `gsutil` cron (no GCS SDK in the bot).

### Log Structure

```
logs/
├── {account1}/
│   ├── trades_2025-01-16.csv   # Date-specific trade log
│   ├── trades_2025-01-17.csv
│   └── positions.json          # Current positions (restart-safe)
└── {account2}/
    ├── trades_2025-01-16.csv
    └── positions.json
```

### Trade CSV Fields

`timestamp, date, action, symbol, price, quantity, amount, profit_pct, profit_krw`

CQS Bot Monitor reads these files from `gs://bot-log/logs/{account}/` to display positions, trade history, and return charts.

## Project Structure

```
crypto-bot/
├── bot.py                  # Entry point (asyncio)
├── bot/
│   ├── bot.py              # VBOBot: multi-account trading loop + daily report
│   ├── config.py           # Config dataclass, retry decorator, .env loader
│   ├── market.py           # DailySignals: VBO signal calculation
│   ├── account.py          # Account: order execution (buy/sell)
│   ├── tracker.py          # PositionTracker: positions.json persistence
│   ├── logger.py           # TradeLogger: date-specific CSV logging
│   └── utils.py            # Telegram notifications
├── tests/                  # 54 tests (unit + integration)
├── research/               # Strategy research & backtesting
│   ├── v0/                 # Early iterations
│   └── v1/                 # Current strategy validation
├── Dockerfile              # Multi-stage python:3.12-slim
├── docker-compose.yml      # Hot reload via volume mount
└── requirements.txt        # pyupbit, pandas
```

**Core**: 722 lines across 7 modules.

## Features

- Multi-account concurrent trading (asyncio)
- Late entry protection (±1% threshold)
- Exponential backoff retry on API failures
- Position persistence via `positions.json` (restart-safe)
- Daily report at 9AM KST (Telegram)
- Hot reload (code mounted as Docker volume, no rebuild needed)
- Telegram notifications (buy/sell/errors/daily report)
- Signal caching (recalculates once per trading day at 9AM KST)

## Monitoring

```bash
# Docker logs
docker-compose logs -f
docker-compose logs --tail=100

# Systemd
sudo systemctl status bot
sudo journalctl -u bot -f
```

### Daily Report (9AM KST via Telegram)

- Target prices vs current prices per symbol
- Account positions with unrealized P&L %
- KRW balance and total equity

## Disclaimer

**Investment Risk Warning**: Past performance does not guarantee future results. Start with small amounts for testing. API permissions required: "View assets" + "Place orders". All investment decisions and P&L are your own responsibility.
