"""Market data and VBO signal calculation."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from datetime import time as dt_time

import pyupbit

from .config import get_config, retry

log = logging.getLogger("vbo")

CANDLE_RESET_HOUR = 9  # KST 09:00
KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class Signal:
    """VBO signal for a single symbol."""
    symbol: str
    target_price: float
    can_buy: bool      # MA conditions met
    should_sell: bool  # Exit conditions met


@retry(max_attempts=3, delay=0.5)
def _fetch_price(ticker: str) -> float:
    """Fetch price with retry."""
    price = pyupbit.get_current_price(ticker)
    if not price:
        raise ValueError(f"No price for {ticker}")
    return float(price)


def get_price(symbol: str) -> float | None:
    """Get current price."""
    try:
        return _fetch_price(f"KRW-{symbol}")
    except Exception as e:
        log.error(f"Price fetch failed for {symbol}: {e}")
        return None


class DailySignals:
    """Daily VBO signals calculator. Recalculates at 9AM KST."""

    def __init__(self):
        self._signals: dict[str, Signal] = {}
        self._date: str | None = None

    @staticmethod
    def _trading_date() -> str:
        """Get trading date (changes at 9AM KST)."""
        now = datetime.now(KST)
        if now.time() < dt_time(CANDLE_RESET_HOUR):
            now -= timedelta(days=1)
        return now.strftime("%Y-%m-%d")

    def _calculate(self) -> bool:
        """Fetch and calculate all signals (V1.1 strategy)."""
        cfg = get_config()
        bars = max(cfg.ma_short, cfg.btc_ma) + 5

        # BTC data (market filter for entry)
        try:
            btc = pyupbit.get_ohlcv("KRW-BTC", interval="day", count=bars)
            if btc is None or len(btc) < cfg.btc_ma + 1:
                log.error("BTC data insufficient")
                return False
            btc_ma = btc['close'].rolling(cfg.btc_ma).mean()
            btc_bull = btc['close'].iloc[-2] > btc_ma.iloc[-2]
        except Exception as e:
            log.error(f"BTC error: {e}")
            return False

        # Each symbol
        signals = {}
        for symbol in cfg.symbols:
            try:
                df = pyupbit.get_ohlcv(f"KRW-{symbol}", interval="day", count=bars)
                if df is None or len(df) < cfg.ma_short + 1:
                    continue

                ema_short = df['close'].ewm(span=cfg.ma_short, adjust=False).mean()
                prev_close = df['close'].iloc[-2]
                prev_ema_short = ema_short.iloc[-2]
                today_open = df['open'].iloc[-1]
                prev_range = df['high'].iloc[-2] - df['low'].iloc[-2]

                # V1.1: Entry = VBO + BTC, Exit = EMA5
                coin_ema5_bull = prev_close > prev_ema_short
                signals[symbol] = Signal(
                    symbol=symbol,
                    target_price=today_open + prev_range * cfg.noise_ratio,
                    can_buy=btc_bull,  # V1.1: only BTC filter for entry
                    should_sell=not coin_ema5_bull,  # V1.1: EMA5 for exit
                )
            except Exception as e:
                log.error(f"Signal calc failed for {symbol}: {e}")

        if not signals:
            return False

        self._signals = signals
        self._date = self._trading_date()
        log.info(f"Signals calculated: {list(signals.keys())}")
        return True

    def get(self, symbol: str) -> Signal | None:
        """Get signal for symbol, recalculate if needed."""
        if self._date != self._trading_date():
            self._calculate()
        return self._signals.get(symbol)

    def all(self) -> dict[str, Signal]:
        """Get all signals, recalculate if needed."""
        if self._date != self._trading_date():
            self._calculate()
        return self._signals
