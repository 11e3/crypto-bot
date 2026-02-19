# Crypto Bot

Upbit KRW 마켓 실매매용 VBO(Volatility Breakout) 봇입니다.
현재 코드는 멀티 계좌, 일일 시그널 캐시, 포지션 영속화, Telegram 알림, Docker 헬스체크를 포함합니다.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/Docker-slim-blue.svg)](https://hub.docker.com/)

## 핵심 기능

- Upbit KRW 페어 실매매 (`pyupbit`)
- 멀티 계좌 동시 실행 (`ACCOUNT_1..N`)
- 전략 시그널 09:00 KST 기준 일일 재계산 (`DailySignals`)
- 계좌별 상태 파일 영속화
- Telegram 체결/오류 알림 (키 기반 쿨다운 스로틀)
- Docker heartbeat 기반 헬스체크

## 전략 요약 (VBO V1.1)

전략 핵심은 `bot/market.py`와 `bot/bot.py`에 구현되어 있습니다.

| 항목 | 규칙 |
|---|---|
| Entry target | `today_open + (prev_high - prev_low) * NOISE_RATIO` |
| Entry filter | 전일 BTC 종가 `> BTC_MA` |
| Buy trigger | 현재가 `>= target_price` |
| Late entry 보호 | 현재가-목표가 괴리가 `±LATE_ENTRY_PCT` 초과 시 매수 거부 |
| Exit signal | 전일 코인 종가 `<= EMA(MA_SHORT)` |
| 자금 배분 | `equity / symbol_count` 기준, 주문 시 `min(alloc, cash * 0.99)` |

## 런타임 동작

`bot.py` 실행 시:

1. `.env` 로드 (`load_env`)
2. 로깅 포맷 설정 (`LOG_FORMAT=text|json`)
3. `VBOBot().run()` 시작

메인 루프(계좌별, 기본 1초 간격):

1. 미해결 매수(pending buy) 복구 시도
2. 당일 시그널 조회 (필요 시 재계산)
3. 매도 조건 충족 포지션 우선 청산
4. 매수 후보 수집 후 시장가 매수

스케줄러:

- 09:00~09:01 KST: 일일 리포트 1회 전송
- 30초 간격: `logs/.heartbeat` 업데이트

## Quick Start

### 1) 로컬 실행

```bash
pip install .
cp .env.example .env
python bot.py
```

### 2) Docker 실행

```bash
docker compose up -d --build
docker compose logs -f
```

코드만 갱신할 때:

```bash
git pull
docker compose restart
```

## 환경 변수 (`.env`)

전체 예시는 `.env.example`에 있습니다.

### 계좌 (필수: 최소 1개)

```env
ACCOUNT_1_NAME=Main
ACCOUNT_1_ACCESS_KEY=...
ACCOUNT_1_SECRET_KEY=...
```

`ACCOUNT_2_*`, `ACCOUNT_3_*` ... 형태로 추가 가능합니다.

### 전략/알림/로깅

```env
SYMBOLS=BTC,ETH
MA_SHORT=5
BTC_MA=20
NOISE_RATIO=0.5

TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# LOG_FORMAT=json
```

### 코드 상수 (`bot/config.py`)

- `MIN_ORDER_KRW=5000`
- `FEE=0.0005`
- `CHECK_INTERVAL_SEC=1`
- `ORDER_DELAY_SEC=0.2`
- `LATE_ENTRY_PCT=1.0`
- `API_RETRY_COUNT=3`, `API_RETRY_DELAY=1.0`

## 상태 파일 / 로그 구조

```text
logs/
├── .heartbeat
├── {account}/
│   ├── positions.json
│   ├── runtime_state.json
│   └── trades_YYYY-MM-DD.csv
```

- `positions.json`: 봇이 관리하는 포지션만 저장
- `runtime_state.json`: pending buy, buy cooldown 등 런타임 상태
- `trades_*.csv`: 체결 로그

CSV 필드:
`timestamp,date,action,symbol,price,quantity,amount,profit_pct,profit_krw`

## 운영 안정성 포인트

- 거래 API 호출 rate limit 분리 적용
  - 주문: `8 req/s`
  - 시세: `25 req/s`
- API 실패 시 exponential backoff retry
- 시그널 재계산 실패 시 fail-closed (새 거래일 stale signal 미사용)
- `SIGINT`/`SIGTERM` 처리
- 체결 수량 불명확 매수는 pending 상태로 저장 후 재복구
- 매도 시 "지갑 전체"가 아니라 "봇 추적 수량"만 청산

## 테스트 / 품질

```bash
pip install .[dev]
pytest
ruff check .
mypy bot
```

현재 코드베이스에서 `pytest --collect-only -q` 기준 126개 테스트가 수집됩니다.

## 긴급 청산 스크립트

```bash
# 시뮬레이션(기본)
python scripts/liquidate.py

# 실제 시장가 청산
python scripts/liquidate.py --execute
```

## 프로젝트 구조

```text
crypto-bot/
├── bot.py
├── bot/
│   ├── account.py
│   ├── bot.py
│   ├── config.py
│   ├── logger.py
│   ├── market.py
│   ├── tracker.py
│   └── utils.py
├── scripts/
│   └── liquidate.py
├── tests/
│   ├── unit/
│   └── integration/
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## 주의사항

- 실거래 전 소액으로 충분히 검증하세요.
- Upbit API 키에는 최소한 "자산 조회", "주문하기" 권한이 필요합니다.
- 모든 투자 판단과 손익 책임은 사용자에게 있습니다.
