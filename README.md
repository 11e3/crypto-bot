# Crypto Bot

**Lightweight live trading bot for the Crypto Quant Ecosystem.**

Part of: [crypto-quant-system](https://github.com/11e3/crypto-quant-system) → [bt](https://github.com/11e3/bt) → **[crypto-bot](https://github.com/11e3/crypto-bot)** → [crypto-regime-classifier-ml](https://github.com/11e3/crypto-regime-classifier-ml)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/Docker-slim-blue.svg)](https://hub.docker.com/)
[![GCP](https://img.shields.io/badge/GCP-e2--micro-yellow.svg)](https://cloud.google.com/)

## Ecosystem Role

```
┌─────────────────────────────────────────────────────────────────┐
│                    Crypto Quant Ecosystem                       │
├─────────────────────────────────────────────────────────────────┤
│  crypto-quant-system     │  Dashboard & data pipeline          │
│    └── Bot log viewer    │  - Reads logs from GCS ◄────────┐   │
├──────────────────────────┼─────────────────────────────────┤   │
│  bt                      │  Backtesting engine             │   │
│    └── Strategy dev      │  - Strategies validated here    │   │
├──────────────────────────┼─────────────────────────────────┤   │
│  crypto-bot (this repo)  │  Live trading bot               │   │
│    ├── Auto trading      │  - Executes validated strategies│   │
│    ├── GCS log upload    │  - Uploads logs to GCS ─────────┘   │
│    └── ML model load     │  - Loads .pkl from GCS ◄────────┐   │
├──────────────────────────┼─────────────────────────────────┤   │
│  crypto-regime-ml        │  Market regime classifier       │   │
│    └── Model export      │  - Uploads .pkl to GCS ─────────┘   │
└──────────────────────────┴──────────────────────────────────────┘
```

## Strategy Performance

VBO (Volatility Breakout) with MA filters, validated via `bt` framework:

| Period | CAGR | MDD | Sharpe |
|--------|------|-----|--------|
| Full (2017~) | 91.1% | -21.1% | 2.15 |
| Test (2022-2024) | 51.9% | -15.0% | 1.92 |
| 2025 OOS | 12.1% | -12.4% | 0.76 |

**Overfitting Risk: VERY LOW** ✅ (8/8 years profitable)

## Infrastructure

### Deployment Stack

```
GCP e2-micro (free tier)
├── Docker (python:3.12-slim)
├── Volume: ./bot, ./bot.py (hot reload)
├── Process: systemd managed
└── Logs: → GCS bucket (gsutil cron)
```

### Resource Optimization

| Component | Optimization |
|-----------|--------------|
| Base image | `python:3.12-slim` (~150MB) |
| Dependencies | Minimal (pandas, pyupbit) |
| Hot reload | Code mounted as volume |
| Restart | systemd auto-restart on failure |

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Setup API keys
cp .env.example .env
nano .env

# Run bot
python bot.py
```

### Docker Deployment

```bash
# Build and run with docker-compose
docker-compose up -d --build

# Hot reload (no rebuild needed for code changes)
git pull && docker-compose restart
```

### GCP Deployment

```bash
# 1. Install Docker
sudo apt update && sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER

# 2. Clone and setup
cd /opt && sudo git clone https://github.com/11e3/crypto-bot.git
cd crypto-bot && sudo cp .env.example .env
sudo nano .env  # Add API keys

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

# 4. Start bot
sudo systemctl daemon-reload
sudo systemctl enable bot
sudo systemctl start bot

# 5. Setup GCS log sync (optional)
# Add to crontab: */5 * * * * gsutil -m rsync -r /opt/crypto-bot/logs gs://your-bucket/logs/
```

## GCS Integration

### Log Sync (gsutil cron)

```bash
# Logs are stored locally in logs/{account_name}/ folder
# Sync to GCS via cron for lightweight Docker image

# Add to crontab
crontab -e

# Sync every 5 minutes
*/5 * * * * gsutil -m rsync -r /opt/crypto-bot/logs gs://your-bucket/bot-logs/
```

### Log Structure

```
logs/
├── Account1/
│   ├── trades.csv      # Trade history
│   └── positions.json  # Current positions
└── Account2/
    ├── trades.csv
    └── positions.json
```

## Configuration

### Environment Variables (.env)

```env
# Exchange API (required, supports multiple accounts)
ACCOUNT_1_NAME=Main
ACCOUNT_1_ACCESS_KEY=your_access_key
ACCOUNT_1_SECRET_KEY=your_secret_key

ACCOUNT_2_NAME=Sub
ACCOUNT_2_ACCESS_KEY=your_access_key_2
ACCOUNT_2_SECRET_KEY=your_secret_key_2

# Telegram (recommended)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Strategy parameters
SYMBOLS=BTC,ETH
MA_SHORT=5
BTC_MA=20
NOISE_RATIO=0.5
```

## Project Structure

```
crypto-bot/
├── bot.py              # Entry point
├── bot/
│   ├── bot.py          # Main trading loop + daily report
│   ├── config.py       # Configuration
│   ├── market.py       # VBO signal calculation
│   ├── account.py      # Order execution
│   ├── tracker.py      # Position tracking
│   ├── logger.py       # Trade logging (CSV)
│   └── utils.py        # Telegram notifications
├── Dockerfile          # Multi-stage slim build
├── docker-compose.yml  # Hot reload enabled
├── .dockerignore
└── logs/               # Mounted volume
    └── {account}/
        ├── trades.csv
        └── positions.json
```

## Features

- ✅ Multiple account support
- ✅ Late entry protection (±1% threshold)
- ✅ Exponential backoff retry
- ✅ Position persistence (restart-safe)
- ✅ Daily report at 9AM KST (Telegram)
- ✅ Hot reload (no rebuild for code changes)
- ✅ Telegram notifications (buy/sell/report)

## Monitoring

### Docker Logs

```bash
# Live logs
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100
```

### Systemd Status

```bash
sudo systemctl status bot
sudo journalctl -u bot -f
```

### Daily Report (9AM KST)

Bot sends daily Telegram report including:
- Today's target prices vs current prices
- Account positions with P&L %
- Account balance (KRW + total)

## Disclaimer

⚠️ **Investment Risk Warning**

- Past performance does not guarantee future results
- Start with small amounts for testing
- API permissions: "View assets" + "Place orders" required
- Investment decisions and P&L are your own responsibility

---

**Version**: 1.1.0 | **Ecosystem**: Crypto Quant System | **Runtime**: GCP e2-micro
