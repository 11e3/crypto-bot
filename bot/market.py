"""Market data and VBO signal calculation."""

import logging
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Optional

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


def get_price(symbol: str) -> Optional[float]:
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
        self._date: Optional[str] = None

    @staticmethod
    def _trading_date() -> str:
        """Get trading date (changes at 9AM KST)."""
        now = datetime.now(KST)
        if now.time() < dt_time(CANDLE_RESET_HOUR):
            now -= timedelta(days=1)
        return now.strftime("%Y-%m-%d")

    def _calculate(self) -> bool:
        """Fetch and calculate all signals."""
        cfg = get_config()
        bars = max(cfg.ma_short, cfg.btc_ma) + 5

        # BTC data (market filter)
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

                ma = df['close'].rolling(cfg.ma_short).mean()
                prev_close, prev_ma = df['close'].iloc[-2], ma.iloc[-2]
                today_open = df['open'].iloc[-1]
                prev_range = df['high'].iloc[-2] - df['low'].iloc[-2]

                coin_bull = prev_close > prev_ma
                signals[symbol] = Signal(
                    symbol=symbol,
                    target_price=today_open + prev_range * cfg.noise_ratio,
                    can_buy=coin_bull and btc_bull,
                    should_sell=not coin_bull or not btc_bull,
                )
            except Exception as e:
                log.error(f"Signal calc failed for {symbol}: {e}")

        if not signals:
            return False

        self._signals = signals
        self._date = self._trading_date()
        log.info(f"Signals calculated: {list(signals.keys())}")
        return True

    def get(self, symbol: str) -> Optional[Signal]:
        """Get signal for symbol, recalculate if needed."""
        if self._date != self._trading_date():
            self._calculate()
        return self._signals.get(symbol)

    def all(self) -> dict[str, Signal]:
        """Get all signals, recalculate if needed."""
        if self._date != self._trading_date():
            self._calculate()
        return self._signals
