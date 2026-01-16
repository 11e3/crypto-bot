# Crypto Bot

**Lightweight live trading bot for the Crypto Quant Ecosystem.**

Part of: `crypto-quant-system` → `bt` → **`crypto-bot`** ← `crypto-regime-classifier-ml`

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
├── Docker (python:3.11-slim)
├── Swap: 2GB configured
├── Process: systemd managed
└── Logs: → GCS bucket
```

### Resource Optimization

| Component | Optimization |
|-----------|--------------|
| Base image | `python:3.11-slim` (~150MB) |
| Dependencies | Minimal (pandas, pyupbit) |
| Memory | 2GB swap for ML model loading |
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
# Build optimized image
docker build -t crypto-bot:slim .

# Run container
docker run -d \
  --name crypto-bot \
  --env-file .env \
  --restart unless-stopped \
  crypto-bot:slim
```

### GCP Deployment

```bash
# 1. Create e2-micro instance
gcloud compute instances create crypto-bot \
  --machine-type=e2-micro \
  --zone=asia-northeast3-a

# 2. Setup swap (required for ML models)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 3. Install and run via systemd
sudo systemctl enable crypto-bot
sudo systemctl start crypto-bot
```

## GCS Integration

### Log Upload

```python
# Bot automatically uploads logs to GCS
# Viewable in crypto-quant-system dashboard

from google.cloud import storage

def upload_log(local_path: str, gcs_path: str):
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(local_path)
```

### ML Model Loading

```python
# Load regime classifier from GCS
from google.cloud import storage
import pickle

def load_model(model_name: str):
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(f"models/{model_name}.pkl")
    
    with blob.open("rb") as f:
        return pickle.load(f)

# Usage
regime_model = load_model("regime_classifier_v1")
current_regime = regime_model.predict(features)
```

## Configuration

### Environment Variables (.env)

```env
# Exchange API (required)
ACCOUNT_1_NAME=Main
ACCOUNT_1_ACCESS_KEY=your_access_key
ACCOUNT_1_SECRET_KEY=your_secret_key

# GCS (required for ecosystem)
GCS_BUCKET=your-bucket-name
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

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
│   ├── config.py       # Configuration & GCS setup
│   ├── market.py       # VBO signal calculation
│   ├── account.py      # Order execution
│   ├── tracker.py      # Position tracking
│   ├── logger.py       # Trade logging → GCS
│   ├── regime.py       # ML model integration
│   └── utils.py        # Telegram notifications
├── Dockerfile          # Optimized slim image
├── docker-compose.yml
└── systemd/
    └── crypto-bot.service
```

## Features

- ✅ Multiple account support
- ✅ Late entry protection (±1% threshold)
- ✅ Exponential backoff retry
- ✅ Position persistence (restart-safe)
- ✅ GCS log upload for dashboard
- ✅ ML regime model integration
- ✅ Telegram notifications

## Monitoring

### View Logs (via crypto-quant-system)

Logs uploaded to GCS are viewable in the crypto-quant-system dashboard.

### Direct Log Access

```bash
# Local logs
tail -f bot.log

# GCS logs
gsutil cat gs://your-bucket/logs/bot_2025-01-16.log
```

### Systemd Status

```bash
sudo systemctl status crypto-bot
sudo journalctl -u crypto-bot -f
```

## Disclaimer

⚠️ **Investment Risk Warning**

- Past performance does not guarantee future results
- Start with small amounts for testing
- API permissions: "View assets" + "Place orders" required
- Investment decisions and P&L are your own responsibility

---

**Version**: 1.0.0 | **Ecosystem**: Crypto Quant System | **Runtime**: GCP e2-micro
