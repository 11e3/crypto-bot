# Crypto Bot

Upbit KRW 페어 실매매 트레이딩 봇. VBO(Volatility Breakout) 전략, 멀티 계좌, 텔레그램 알림.

[crypto-lab](https://github.com/11e3/crypto-lab) / **[crypto-bot](https://github.com/11e3/crypto-bot)**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/Docker-slim-blue.svg)](https://hub.docker.com/)
[![GCP](https://img.shields.io/badge/GCP-e2--micro-yellow.svg)](https://cloud.google.com/)

---

## Live Trading Performance (Upbit)

<table>
  <tr>
    <td align="center"><b>2024</b><br>Return: 101.26%</td>
    <td align="center"><b>2025</b><br>Return: 19.28%</td>
    <td align="center"><b>2026 YTD</b><br>Return: 7.99%</td>
  </tr>
  <tr>
    <td><img src="images/KakaoTalk_20260208_142941894_01.jpg" width="333"/></td>
    <td><img src="images/KakaoTalk_20260208_142941894_02.jpg" width="333"/></td>
    <td><img src="images/KakaoTalk_20260208_142941894_03.jpg" width="333"/></td>
  </tr>
</table>

---

## Ecosystem

2개 repo가 GCS를 통해 느슨하게 결합. 코드 의존성 없이 데이터 아티팩트로만 통신.

```
┌─────────────────────────────────────────────────┐
│  crypto-bot (this repo)                         │
│                                                 │
│  Live Trading Bot (VBO V1.1)                    │
│  Upbit 실매매 · 멀티 계좌                          │
│  Docker / GCP e2-micro                          │
│                                                 │
│         trade logs ──── GCS 쓰기 ──────┐         │
└─────────────────────────────────────────┼───────┘
                                          │
                                          ▼
                                    ┌──────────┐
                                    │   GCS    │
                                    │  logs/   │
                                    └────┬─────┘
                                         │
                                         ▼
┌────────────────────────────────────────┼────────┐
│  crypto-lab                            │        │
│                                        │        │
│  Backtesting Engine ─── Strategy Framework      │
│  Streamlit Dashboard ── Bot Monitor ◄──┘        │
│  Data Pipeline ──────── Risk Management         │
│  Optimization ───────── WFA / Monte Carlo       │
└─────────────────────────────────────────────────┘
```

| Repo | 역할 | LOC | 상태 |
|------|------|-----|------|
| **crypto-bot** | Upbit 실매매 봇 (VBO) | ~850 | Active (독립 배포) |
| **[crypto-lab](https://github.com/11e3/crypto-lab)** | 백테스트, 대시보드, 데이터 파이프라인 | ~7,500 | Active |

---

## Strategy: VBO V1.1

Volatility Breakout + MA 필터. 로직 전체가 `bot/market.py` (125줄).

| Component | Rule |
|-----------|------|
| **Entry signal** | `open + prev_range * K` breakout (K=0.5) |
| **Entry filter** | BTC `close > MA20` (시장 레짐 필터) |
| **Exit signal** | `prev_close < prev_EMA5` |
| **Allocation** | `equity / N` per symbol |
| **Late entry** | 목표가 대비 ±1% 이상 이탈 시 거부 |

### Trading Cycle (Daily)

```
09:00 KST ─── 신호 재계산 (DailySignals)
              ├── Exit: prev_close < prev_EMA5 → 시장가 매도
              ├── Entry targets 계산
              └── Daily report (Telegram)

09:00~09:00 ─ 1초 간격 루프
              └── 현재가 ≥ 목표가 → 시장가 매수 (late entry 체크 포함)
```

---

## Quick Start

### Local

```bash
pip install .
cp .env.example .env   # API 키 입력
python bot.py
```

### Docker

```bash
docker-compose up -d --build

# Hot reload (rebuild 불필요)
git pull && docker-compose restart
```

### GCP e2-micro (Production)

```bash
# 1. Docker 설치
sudo apt update && sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER

# 2. 클론 & 설정
cd /opt && sudo git clone https://github.com/11e3/crypto-bot.git
cd crypto-bot && sudo cp .env.example .env
sudo nano .env  # API 키 입력

# 3. systemd 서비스
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

# 4. 시작
sudo systemctl daemon-reload
sudo systemctl enable bot
sudo systemctl start bot

# 5. GCS 로그 동기화 (crontab -e)
*/5 * * * * gsutil -m rsync -r /opt/crypto-bot/logs gs://bot-log/logs/
```

---

## Configuration

### Environment Variables (.env)

```env
# Exchange API (멀티 계좌 지원)
ACCOUNT_1_NAME=account1
ACCOUNT_1_ACCESS_KEY=your_access_key
ACCOUNT_1_SECRET_KEY=your_secret_key

ACCOUNT_2_NAME=account2
ACCOUNT_2_ACCESS_KEY=your_access_key_2
ACCOUNT_2_SECRET_KEY=your_secret_key_2

# Telegram 알림 (권장)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# 전략 파라미터
SYMBOLS=BTC,ETH
MA_SHORT=5
BTC_MA=20
NOISE_RATIO=0.5

# 로깅 (선택)
# LOG_FORMAT=json   # "json" 또는 "text" (기본: text)
```

### Trading Constants (config.py)

| Constant | Value | Description |
|----------|-------|-------------|
| `FEE` | 0.05% | Upbit 거래 수수료 |
| `MIN_ORDER_KRW` | 5,000 | 최소 주문 금액 |
| `LATE_ENTRY_PCT` | 1.0% | 목표가 대비 최대 이탈률 |
| `CHECK_INTERVAL_SEC` | 1 | 메인 루프 간격 |
| `ORDER_DELAY_SEC` | 0.2 | 연속 주문 사이 대기 |

---

## Architecture

```
bot.py (entry point, LOG_FORMAT 전환)
└── VBOBot (bot/bot.py)
    ├── DailySignals (bot/market.py)     # VBO 신호 계산, 9AM KST 캐싱
    ├── Account (bot/account.py)         # 시장가 주문 실행
    ├── PositionTracker (bot/tracker.py) # positions.json 영속성
    ├── TradeLogger (bot/logger.py)      # 날짜별 CSV 로깅
    ├── Telegram (bot/utils.py)          # HTML 포맷 알림 + 에러 스로틀
    └── Config (bot/config.py)           # RateLimiter, retry, JsonFormatter
```

**Core**: 849줄, 7개 모듈.

### Resilience

- **Position 영속성**: `positions.json`으로 재시작 시 포지션 복구
- **Signal 캐싱**: 9AM KST에 1회 계산, 루프마다 재계산하지 않음
- **Retry**: API 실패 시 exponential backoff (1s → 2s → 4s)
- **Rate Limiting**: Upbit API 제한 준수 (주문 8/s, 시세 25/s)
- **Graceful shutdown**: SIGINT/SIGTERM 핸들링
- **Docker HEALTHCHECK**: 30초 heartbeat 파일 기반 상태 확인
- **Error alerting**: Telegram 에러 알림 (5분 쿨다운 스로틀)
- **멀티 계좌**: `asyncio.gather()`로 동시 실행

---

## GCS Integration

Trade 로그를 `gsutil` cron으로 GCS에 동기화 (봇 내부에 GCS SDK 없음).

### Log Structure

```
logs/
├── {account1}/
│   ├── trades_2025-01-16.csv       # 날짜별 거래 로그
│   ├── trades_2025-01-17.csv
│   └── positions.json              # 현재 포지션 (재시작 안전)
└── {account2}/
    ├── trades_2025-01-16.csv
    └── positions.json
```

### Trade CSV Fields

`timestamp, date, action, symbol, price, quantity, amount, profit_pct, profit_krw`

crypto-lab Bot Monitor가 `gs://bot-log/logs/{account}/`에서 읽어 포지션, 거래 이력, 수익 차트 표시.

---

## Project Structure

```
crypto-bot/
├── bot.py                  # Entry point (LOG_FORMAT 전환)
├── bot/
│   ├── bot.py              # VBOBot: 멀티 계좌 트레이딩 루프 + 일일 리포트 + heartbeat
│   ├── config.py           # Config, RateLimiter, retry, JsonFormatter, .env 로더
│   ├── market.py           # DailySignals: VBO 신호 계산
│   ├── account.py          # Account: 주문 실행 (매수/매도)
│   ├── tracker.py          # PositionTracker: positions.json 영속성
│   ├── logger.py           # TradeLogger: 날짜별 CSV 로깅
│   └── utils.py            # Telegram 알림 + 에러 스로틀
├── tests/                  # 63 tests (unit + integration)
├── scripts/
│   └── liquidate.py        # 긴급 포지션 청산
├── Dockerfile              # Multi-stage python:3.12-slim + HEALTHCHECK
├── docker-compose.yml      # Volume mount + healthcheck + log rotation
└── pyproject.toml          # 의존성 + ruff/mypy/pytest 설정
```

---

## Monitoring

```bash
# Docker
docker-compose logs -f
docker-compose logs --tail=100

# Systemd
sudo systemctl status bot
sudo journalctl -u bot -f
```

### Daily Report (9AM KST, Telegram)

- 심볼별 목표가 vs 현재가
- 계좌 포지션 + 미실현 손익 %
- KRW 잔고 및 총 평가액

---

## Disclaimer

**투자 위험 경고**: 과거 수익률이 미래 수익을 보장하지 않습니다. 소액으로 먼저 테스트하세요. Upbit API 권한 필요: "자산 조회" + "주문하기". 모든 투자 판단과 손익은 본인 책임입니다.
