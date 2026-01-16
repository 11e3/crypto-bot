# VBO Strategy Backtest & Live Trading Bot

업비트 암호화폐 VBO (Volatility Breakout) 전략의 백테스트, 검증, 실거래 봇.

## 📊 전략 개요

### 전략 로직

**매수 조건 (모두 충족):**
- 당일 고가 >= 매수 타겟가 (시가 + (전일고가 - 전일저가) × 0.5)
- 전일 종가 > 전일 MA5
- 전일 비트코인 종가 > 전일 비트코인 MA20

**매도 조건 (하나라도 충족):**
- 전일 종가 < 전일 MA5
- 전일 비트코인 종가 < 전일 비트코인 MA20

**매수/매도가:**
- 매수: 타겟가 + 슬리피지 0.05%
- 매도: 당일 시가 - 슬리피지 0.05%
- 수수료: 0.05%

### 검증된 성과 (BTC+ETH 포트폴리오)

| 기간 | CAGR | MDD | Sharpe |
|------|------|-----|--------|
| 전체 (2017~) | 91.1% | -21.1% | 2.15 |
| Test (2022-2024) | 51.9% | -15.0% | 1.92 |
| 2025년 | 12.1% | -12.4% | 0.76 |

## 🚀 빠른 시작

### 설치

```bash
# 의존성 설치
pip install -r requirements.txt

# 또는 직접 설치
pip install pandas numpy pyupbit

# 데이터 다운로드
python fetcher.py
```

### 실거래 봇 실행

```bash
# 1. API 키 설정
cp .env.example .env
nano .env  # API 키 입력

# 2. 봇 실행
python bot.py

# 백그라운드 실행
nohup python bot.py > bot.log 2>&1 &
```

### 백테스트 실행

```bash
# 포트폴리오 조합 백테스트
python research/backtest_vbo_portfolio.py

# 단일 코인 전략 비교
python research/backtest_vbo_comparison.py

# 오버피팅 검증
python research/check_overfitting.py

# 파라미터 민감성 테스트
python research/test_parameter_sensitivity.py

# 특정 기간 지정
python research/backtest_vbo_portfolio.py --start 2022-01-01 --end 2024-12-31
```

## 🤖 실거래 봇

### 주요 기능

- ✅ 다중 계정 지원 (무제한)
- ✅ 검증된 VBO 전략 (CAGR 91%, Sharpe 2.15)
- ✅ 텔레그램 실시간 알림
- ✅ Late entry 보호 (±1% 이내만 진입)
- ✅ 안전한 에러 처리 (retry + exponential backoff)
- ✅ 24/7 무인 운영
- ✅ 포지션 파일로 상태 추적 (재시작 안전)

### 봇 구조

```
bot/
├── __init__.py    # 패키지 exports
├── config.py      # 설정 관리
├── market.py      # VBO 시그널 계산
├── account.py     # 주문 실행
├── tracker.py     # 포지션 추적
├── logger.py      # 거래 로그
├── utils.py       # 텔레그램 알림
└── bot.py         # 메인 봇 로직
```

### 포지션 관리

- 봇이 **직접 산 코인만** 관리
- 기존 보유 코인은 무시 (안전)
- 재시작 시 `.positions_{계정명}.json`에서 복원
- 거래 기록: `trades_{계정명}.csv`

### 설정 (.env)

```env
# 계정 설정 (필수)
ACCOUNT_1_NAME=Main
ACCOUNT_1_ACCESS_KEY=your_access_key
ACCOUNT_1_SECRET_KEY=your_secret_key

# 텔레그램 (권장)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# 전략 파라미터 (기본값 권장)
SYMBOLS=BTC,ETH
MA_SHORT=5
BTC_MA=20
NOISE_RATIO=0.5
```

### 주의사항

- ⚠️ 처음엔 **소액으로 테스트**
- ⚠️ API 권한: "자산 조회" + "주문하기" 필수
- ⚠️ 과거 수익이 미래 수익을 보장하지 않음
- ⚠️ 투자 판단과 손익은 본인 책임

## 📈 연구 결과

### 포트폴리오 조합 성과

| 순위 | 조합 | CAGR | MDD | Sharpe |
|------|------|------|-----|--------|
| 🥇 | **BTC+ETH** | 91.1% | **-21.1%** | **2.15** |
| 🥈 | BTC+ETH+XRP | 101.0% | -23.6% | 1.98 |
| 🥉 | BTC+XRP | 101.9% | -36.6% | 1.74 |

**핵심 발견:**
- **BTC+ETH 조합이 최고** (Sharpe 2.15, MDD -21.1%)
- 2개 조합이 가장 효율적 (높은 Sharpe, 낮은 MDD)
- BTC-ETH 상관관계 0.73으로 적절한 분산 효과

### 전략 개선 시도 결과

여러 개선안을 테스트했으나 **현재 전략이 최선**:

| 시도 | 결과 | 비고 |
|------|------|------|
| 순수 VBO (MA필터 제거) | ❌ CAGR 31%, MDD -57% | 필터 필수 |
| BTC 필터만 | ❌ MDD -41% (2배 악화) | 코인MA 필수 |
| 거래량 필터 추가 | ❌ CAGR -32% | 기회 손실 큼 |
| ATR 포지션 사이징 | △ Sharpe +0.02 | 효과 미미 |
| Trailing Stop -3% | ❌ 과적합 (4H봉 검증 실패) | 일봉 착시 |
| 4시간봉 전략 | ❌ CAGR 44%, Sharpe 1.57 | 일봉이 우월 |

**결론:** MA5 + BTC_MA20 조합이 이미 최적화되어 있음

## ✅ 검증 결과

### 오버피팅 검증

| 기간 | CAGR | Sharpe | 평가 |
|------|------|--------|------|
| Train (2017-2021) | 154.9% | 2.53 | 학습 |
| Test (2022-2024) | 51.9% | 1.92 | ✅ 검증 |
| 2025년 | 12.1% | 0.76 | ✅ OOS |

- Sharpe 하락 24% (허용 범위 내)
- **8/8년 수익** (100% 승률)
- 파라미터 민감성 < 10%

### 검증 체크리스트

| 항목 | 결과 |
|------|------|
| ✅ Look-ahead bias 없음 | 모든 지표 shift(1) |
| ✅ 백테스트-봇 로직 일치 | 코드 리뷰 완료 |
| ✅ Train/Test 일관성 | Sharpe 하락 24% |
| ✅ 연도별 일관성 | 8/8년 양수 |
| ✅ 파라미터 단순성 | 2개만 사용 |
| ✅ 4시간봉 교차검증 | 일봉 우월 확인 |

**오버피팅 위험: 매우 낮음** ✅

## 📁 프로젝트 구조

```
├── bot.py                  # 실거래 봇 진입점
├── bot/                    # 봇 패키지
│   ├── __init__.py
│   ├── config.py           # 설정 관리
│   ├── market.py           # VBO 시그널 계산
│   ├── account.py          # 주문 실행
│   ├── tracker.py          # 포지션 추적
│   ├── logger.py           # 거래 로그
│   ├── utils.py            # 텔레그램
│   └── bot.py              # 메인 봇 로직
├── research/               # 백테스트 연구
│   ├── backtest_vbo_portfolio.py
│   ├── backtest_vbo_comparison.py
│   ├── check_overfitting.py
│   └── test_parameter_sensitivity.py
├── data/                   # OHLCV 데이터
│   ├── BTC.csv
│   ├── ETH.csv
│   └── ...
├── fetcher.py              # 데이터 수집
├── liquidate.py            # 긴급 청산
└── legacy/                 # 이전 연구
```

## 🔬 백테스트 설정

- **기간**: 2017-01-01 ~ 현재
- **수수료**: 0.05%
- **슬리피지**: 0.05%
- **초기 자본**: 1,000,000 KRW
- **포트폴리오**: 총자산 / N 균등 분배

## ⚠️ 면책사항

- 과거 수익이 미래 수익을 보장하지 않음
- 시장 환경 변화로 전략 효과 감소 가능
- 극단적 변동성에서 체결 실패 가능
- 투자 원금 손실 위험 존재

**투자 판단은 본인 책임입니다.**

---

**Last Updated**: 2025-01-15
