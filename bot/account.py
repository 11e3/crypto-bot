"""Trading account management."""

import logging
import time
from typing import Optional

import pyupbit

from .config import get_config
from .logger import TradeLogger, Trade
from .tracker import PositionTracker
from .utils import send_telegram

log = logging.getLogger("vbo")


class Account:
    """Upbit trading account."""

    def __init__(self, name: str, access_key: str, secret_key: str):
        self.name = name
        self._api = pyupbit.Upbit(access_key, secret_key)
        self.positions = PositionTracker(name)
        self._logger = TradeLogger(name)
        log.info(f"[{name}] Initialized")

    def balance(self, currency: str = "KRW") -> float:
        """Get balance."""
        try:
            bal = self._api.get_balance(currency)
            return float(bal) if bal else 0.0
        except Exception as e:
            log.error(f"[{self.name}] Balance error: {e}")
            return 0.0

    def _get_fill(self, uuid: str, fallback: float) -> tuple[float, float]:
        """Get fill price and quantity from order."""
        try:
            info = self._api.get_order(uuid)
            if info and info.get('state') in ('done', 'cancel'):
                trades = info.get('trades', [])
                if trades:
                    krw = sum(float(t['funds']) for t in trades)
                    qty = sum(float(t['volume']) for t in trades)
                    return (krw / qty if qty else fallback), qty
            return float(info.get('price', fallback)), float(info.get('executed_volume', 0))
        except Exception:
            return fallback, 0.0

    def buy(self, symbol: str, target: float, amount: float) -> bool:
        """Market buy with late entry protection."""
        cfg = get_config()
        if amount < cfg.MIN_ORDER_KRW:
            return False

        try:
            ticker = f"KRW-{symbol}"
            price = pyupbit.get_current_price(ticker)
            if not price:
                return False
            price = float(price)

            # Late entry check
            diff = (price / target - 1) * 100
            if abs(diff) > cfg.LATE_ENTRY_PCT:
                log.info(f"[{self.name}] {symbol}: price {price:,.0f} not near target {target:,.0f} ({diff:+.1f}%)")
                return False

            result = self._api.buy_market_order(ticker, amount)
            if not result:
                return False

            time.sleep(0.5)
            fill_price, fill_qty = self._get_fill(result.get('uuid'), price)
            if fill_qty <= 0:
                fill_qty = self.balance(symbol)
                fill_price = amount / fill_qty if fill_qty else price

            if fill_qty <= 0:
                return False

            self.positions.add(symbol, fill_qty, fill_price)
            self._logger.log(Trade.buy(symbol, fill_price, fill_qty, amount))

            log.info(f"[{self.name}] BUY {symbol}: {fill_qty:.8f} @ {fill_price:,.0f}")
            send_telegram(f"🟢 <b>BUY</b> [{self.name}] {symbol}\n{fill_qty:.8f} @ {fill_price:,.0f} KRW")
            return True

        except Exception as e:
            log.error(f"[{self.name}] Buy error {symbol}: {e}")
            return False

    def sell(self, symbol: str) -> bool:
        """Market sell bot's position."""
        pos = self.positions.get(symbol)
        if not pos:
            return False

        qty = self.balance(symbol)
        if qty <= 0:
            self.positions.remove(symbol)
            return False

        try:
            ticker = f"KRW-{symbol}"
            price = pyupbit.get_current_price(ticker)
            price = float(price) if price else pos.entry_price

            result = self._api.sell_market_order(ticker, qty)
            if not result:
                return False

            time.sleep(0.5)
            fill_price, _ = self._get_fill(result.get('uuid'), price)

            pnl_pct = (fill_price / pos.entry_price - 1) * 100 if pos.entry_price else 0
            pnl_krw = (fill_price - pos.entry_price) * qty if pos.entry_price else 0

            self.positions.remove(symbol)
            self._logger.log(Trade.sell(symbol, fill_price, qty, fill_price * qty, pnl_pct, pnl_krw))

            log.info(f"[{self.name}] SELL {symbol}: {qty:.8f} @ {fill_price:,.0f} ({pnl_pct:+.2f}%)")
            send_telegram(f"🔴 <b>SELL</b> [{self.name}] {symbol}\n{pnl_pct:+.2f}% ({pnl_krw:+,.0f} KRW)")
            return True

        except Exception as e:
            log.error(f"[{self.name}] Sell error {symbol}: {e}")
            return False
