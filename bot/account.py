"""Trading account management."""

import json
import logging
import time
from pathlib import Path

import pyupbit

from .config import get_config, order_limiter
from .logger import Trade, TradeLogger
from .market import get_price
from .tracker import PositionTracker
from .utils import send_telegram, send_telegram_error

log = logging.getLogger("vbo")


class Account:
    """Upbit trading account."""

    ZERO_BALANCE_RETRY_LIMIT = 3
    BUY_RETRY_COOLDOWN_SEC = 300.0
    PENDING_BUY_TIMEOUT_SEC = 1800.0

    def __init__(self, name: str, access_key: str, secret_key: str):
        self.name = name
        self._api = pyupbit.Upbit(access_key, secret_key)
        self.positions = PositionTracker(name)
        self._logger = TradeLogger(name)
        self._zero_balance_counts: dict[str, int] = {}
        self._buy_block_until: dict[str, float] = {}
        self._pending_buys: dict[str, dict[str, float | str | None]] = {}
        self._state_path = Path(f"logs/{name}/runtime_state.json")
        self._load_runtime_state()
        log.info(f"[{name}] Initialized")

    def can_attempt_buy(self, symbol: str) -> bool:
        """Check whether symbol buy attempts are temporarily blocked."""
        if symbol in self._pending_buys:
            return False
        return time.time() >= self._buy_block_until.get(symbol, 0.0)

    def _load_runtime_state(self) -> None:
        if not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text())
            block = data.get("buy_block_until", {})
            pending = data.get("pending_buys", {})
            if isinstance(block, dict):
                self._buy_block_until = {
                    str(k): float(v) for k, v in block.items() if isinstance(v, (int, float))
                }
            if isinstance(pending, dict):
                clean: dict[str, dict[str, float | str | None]] = {}
                for symbol, payload in pending.items():
                    if not isinstance(payload, dict):
                        continue
                    uuid = payload.get("uuid")
                    amount = payload.get("amount")
                    fallback_price = payload.get("fallback_price")
                    pre_qty = payload.get("pre_qty")
                    created_at = payload.get("created_at")
                    if not isinstance(uuid, str) or not isinstance(amount, (int, float)):
                        continue
                    if not isinstance(fallback_price, (int, float)) or not isinstance(
                        created_at, (int, float)
                    ):
                        continue
                    clean[str(symbol)] = {
                        "uuid": uuid,
                        "amount": float(amount),
                        "fallback_price": float(fallback_price),
                        "pre_qty": float(pre_qty) if isinstance(pre_qty, (int, float)) else None,
                        "created_at": float(created_at),
                    }
                self._pending_buys = clean
        except Exception as e:
            log.warning(f"[{self.name}] Runtime state load failed: {e}")

    def _save_runtime_state(self) -> None:
        try:
            payload = {
                "buy_block_until": self._buy_block_until,
                "pending_buys": self._pending_buys,
            }
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2))
            tmp.replace(self._state_path)
        except Exception as e:
            log.warning(f"[{self.name}] Runtime state save failed: {e}")

    def _set_buy_block(self, symbol: str, cooldown: float | None = None) -> None:
        until = time.time() + (cooldown if cooldown is not None else self.BUY_RETRY_COOLDOWN_SEC)
        self._buy_block_until[symbol] = until
        self._save_runtime_state()

    def _clear_buy_block(self, symbol: str) -> None:
        self._buy_block_until.pop(symbol, None)
        self._save_runtime_state()

    def reconcile_pending_buys(self) -> None:
        """Try to resolve pending buys and materialize positions safely."""
        if not self._pending_buys:
            return
        now = time.time()
        for symbol, pending in list(self._pending_buys.items()):
            uuid = pending.get("uuid")
            amount = pending.get("amount")
            fallback_price = pending.get("fallback_price")
            pre_qty = pending.get("pre_qty")
            created_at = pending.get("created_at")
            if not isinstance(uuid, str) or not isinstance(amount, (int, float)):
                continue
            if not isinstance(fallback_price, (int, float)):
                continue
            fill_price, fill_qty = self._get_fill(uuid, float(fallback_price))
            if fill_qty <= 0:
                post_qty = self._get_balance_value(symbol, log_error=False)
                if isinstance(pre_qty, (int, float)) and post_qty is not None:
                    fill_qty = max(0.0, post_qty - float(pre_qty))
                    fill_price = float(amount) / fill_qty if fill_qty else float(fallback_price)
            if fill_qty <= 0:
                pending_age = now - float(created_at) if isinstance(created_at, (int, float)) else 0.0
                if pending_age >= self.PENDING_BUY_TIMEOUT_SEC or self._is_order_closed_without_fill(
                    uuid
                ):
                    self._pending_buys.pop(symbol, None)
                    self._clear_buy_block(symbol)
                    self._save_runtime_state()
                    send_telegram_error(
                        f"[{self.name}] Pending buy expired/closed without fill {symbol}",
                        key=f"{self.name}:pending-expire:{symbol}",
                    )
                continue
            self.positions.add(symbol, fill_qty, fill_price)
            self._zero_balance_counts.pop(symbol, None)
            self._pending_buys.pop(symbol, None)
            self._clear_buy_block(symbol)
            self._logger.log(Trade.buy(symbol, fill_price, fill_qty, fill_price * fill_qty))
            send_telegram(
                f"🟢 <b>BUY RECOVERED</b> [{self.name}] {symbol}\n{fill_qty:.8f} @ {fill_price:,.0f} KRW"
            )
            log.info(f"[{self.name}] BUY recovered {symbol}: {fill_qty:.8f} @ {fill_price:,.0f}")
            self._save_runtime_state()

    def _is_order_closed_without_fill(self, uuid: str) -> bool:
        """Return True when order is terminal and has no executed quantity."""
        try:
            order_limiter.wait()
            info = self._api.get_order(uuid)
        except Exception:
            return False
        if not isinstance(info, dict):
            return False

        state = info.get("state")
        if state not in ("done", "cancel"):
            return False

        try:
            trades = info.get("trades", [])
            if isinstance(trades, list) and trades:
                qty = sum(float(t.get("volume", 0) or 0) for t in trades if isinstance(t, dict))
                return qty <= 0
            executed = float(info.get("executed_volume", 0) or 0)
            return executed <= 0
        except Exception:
            return False

    def balance(self, currency: str = "KRW") -> float:
        """Get balance."""
        bal = self._get_balance_value(currency)
        return bal if bal is not None else 0.0

    def _get_balance_value(self, currency: str, *, log_error: bool = True) -> float | None:
        """Get balance value. Returns None on API failure."""
        try:
            order_limiter.wait()
            bal = self._api.get_balance(currency)
            return float(bal) if bal else 0.0
        except Exception as e:
            if log_error:
                log.error(f"[{self.name}] Balance error ({currency}): {e}")
            return None

    def _get_fill(self, uuid: str, fallback: float) -> tuple[float, float]:
        """Get fill price and quantity from order."""
        try:
            order_limiter.wait()
            info = self._api.get_order(uuid)
            if info and info.get("state") in ("done", "cancel"):
                trades = info.get("trades", [])
                if trades:
                    krw = sum(float(t["funds"]) for t in trades)
                    qty = sum(float(t["volume"]) for t in trades)
                    return (krw / qty if qty else fallback), qty
            return float(info.get("price", fallback)), float(info.get("executed_volume", 0))
        except Exception:
            return fallback, 0.0

    def buy(self, symbol: str, target: float, amount: float) -> bool:
        """Market buy with late entry protection."""
        cfg = get_config()
        if amount < cfg.MIN_ORDER_KRW:
            return False
        if not self.can_attempt_buy(symbol):
            return False

        try:
            ticker = f"KRW-{symbol}"
            price = get_price(symbol)
            if not price:
                return False
            pre_qty = self._get_balance_value(symbol, log_error=False)

            # Late entry check
            diff = (price / target - 1) * 100
            if abs(diff) > cfg.LATE_ENTRY_PCT:
                log.info(
                    f"[{self.name}] {symbol}: price {price:,.0f} not near target {target:,.0f} ({diff:+.1f}%)"
                )
                return False

            order_limiter.wait()
            result = self._api.buy_market_order(ticker, amount)
            if not result:
                return False

            time.sleep(0.5)
            fill_price, fill_qty = self._get_fill(result.get("uuid"), price)
            for _ in range(2):
                if fill_qty > 0:
                    break
                time.sleep(0.5)
                fill_price, fill_qty = self._get_fill(result.get("uuid"), price)
            if fill_qty <= 0:
                post_qty = self._get_balance_value(symbol, log_error=False)
                if pre_qty is not None and post_qty is not None:
                    delta_qty = max(0.0, post_qty - pre_qty)
                    fill_qty = delta_qty
                    fill_price = amount / fill_qty if fill_qty else price

            if fill_qty <= 0:
                order_uuid = result.get("uuid") if isinstance(result, dict) else None
                if isinstance(order_uuid, str) and order_uuid:
                    self._pending_buys[symbol] = {
                        "uuid": order_uuid,
                        "amount": amount,
                        "fallback_price": price,
                        "pre_qty": pre_qty,
                        "created_at": time.time(),
                    }
                    self._save_runtime_state()
                send_telegram_error(
                    f"[{self.name}] Buy filled but quantity unresolved {symbol}",
                    key=f"{self.name}:buy-fill:{symbol}",
                )
                self._set_buy_block(symbol)
                return False

            self.positions.add(symbol, fill_qty, fill_price)
            self._zero_balance_counts.pop(symbol, None)
            self._pending_buys.pop(symbol, None)
            self._clear_buy_block(symbol)
            self._logger.log(Trade.buy(symbol, fill_price, fill_qty, amount))

            log.info(f"[{self.name}] BUY {symbol}: {fill_qty:.8f} @ {fill_price:,.0f}")
            send_telegram(
                f"🟢 <b>BUY</b> [{self.name}] {symbol}\n{fill_qty:.8f} @ {fill_price:,.0f} KRW"
            )
            return True

        except Exception as e:
            log.error(f"[{self.name}] Buy error {symbol}: {e}")
            send_telegram_error(
                f"[{self.name}] Buy failed {symbol}: {e}",
                key=f"{self.name}:buy:{symbol}",
            )
            return False

    def sell(self, symbol: str) -> bool:
        """Market sell bot's position."""
        pos = self.positions.get(symbol)
        if not pos:
            return False

        try:
            balance_qty = self._get_balance_value(symbol)
            if balance_qty is None:
                raise RuntimeError("balance unavailable")
        except Exception as e:
            send_telegram_error(
                f"[{self.name}] Balance failed {symbol}: {e}",
                key=f"{self.name}:balance:{symbol}",
            )
            return False

        if balance_qty <= 0:
            zero_count = self._zero_balance_counts.get(symbol, 0) + 1
            self._zero_balance_counts[symbol] = zero_count
            if zero_count >= self.ZERO_BALANCE_RETRY_LIMIT:
                log.warning(
                    f"[{self.name}] {symbol} balance stayed zero ({zero_count}x), removing tracked position"
                )
                self.positions.remove(symbol)
                self._zero_balance_counts.pop(symbol, None)
                return False

            log.warning(
                f"[{self.name}] {symbol} balance is zero ({zero_count}/{self.ZERO_BALANCE_RETRY_LIMIT}), keeping tracked position"
            )
            send_telegram_error(
                f"[{self.name}] {symbol} balance is zero while position exists",
                key=f"{self.name}:balance-zero:{symbol}",
            )
            return False
        self._zero_balance_counts.pop(symbol, None)

        try:
            ticker = f"KRW-{symbol}"
            price = get_price(symbol) or pos.entry_price

            # Only liquidate bot-tracked quantity, not full wallet balance.
            qty = min(balance_qty, pos.quantity)
            if qty <= 0:
                return False

            order_limiter.wait()
            result = self._api.sell_market_order(ticker, qty)
            if not result:
                return False

            time.sleep(0.5)
            fill_price, fill_qty = self._get_fill(result.get("uuid"), price)
            filled_qty = min(qty, fill_qty) if fill_qty > 0 else 0.0
            if filled_qty <= 0:
                post_qty = self._get_balance_value(symbol, log_error=False)
                if post_qty is not None:
                    filled_qty = max(0.0, balance_qty - post_qty)

            if filled_qty <= 0:
                send_telegram_error(
                    f"[{self.name}] Sell filled qty unresolved {symbol}",
                    key=f"{self.name}:sell-fill:{symbol}",
                )
                return False

            pnl_pct = (fill_price / pos.entry_price - 1) * 100 if pos.entry_price else 0
            pnl_krw = (fill_price - pos.entry_price) * filled_qty if pos.entry_price else 0

            remaining_qty = max(0.0, pos.quantity - filled_qty)
            if remaining_qty <= 0:
                self.positions.remove(symbol)
            else:
                self.positions.update_quantity(symbol, remaining_qty)
            self._zero_balance_counts.pop(symbol, None)
            self._logger.log(
                Trade.sell(
                    symbol,
                    fill_price,
                    filled_qty,
                    fill_price * filled_qty,
                    pnl_pct,
                    pnl_krw,
                )
            )

            log.info(
                f"[{self.name}] SELL {symbol}: {filled_qty:.8f} @ {fill_price:,.0f} ({pnl_pct:+.2f}%)"
            )
            send_telegram(
                f"🔴 <b>SELL</b> [{self.name}] {symbol}\n{pnl_pct:+.2f}% ({pnl_krw:+,.0f} KRW)"
            )
            return True

        except Exception as e:
            log.error(f"[{self.name}] Sell error {symbol}: {e}")
            send_telegram_error(
                f"[{self.name}] Sell failed {symbol}: {e}",
                key=f"{self.name}:sell:{symbol}",
            )
            return False
