"""Position tracking for bot-managed positions."""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

KST = timezone(timedelta(hours=9))

log = logging.getLogger("vbo")


@dataclass
class Position:
    """Bot position info."""

    symbol: str
    quantity: float
    entry_price: float
    entry_time: str


class PositionTracker:
    """Track bot's positions (ignores manual positions)."""

    def __init__(self, account: str):
        self.account = account
        self._path = Path(f"logs/{account}/positions.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._positions: dict[str, Position] = self._load()

    def _load(self) -> dict[str, Position]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text())
            return {k: Position(**v) for k, v in data.items()}
        except Exception as e:
            log.warning(f"[{self.account}] Position load failed: {e}")
            return {}

    def _save(self) -> None:
        try:
            data = {k: asdict(v) for k, v in self._positions.items()}
            payload = json.dumps(data, indent=2)
            tmp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
            tmp_path.write_text(payload)
            tmp_path.replace(self._path)
        except Exception as e:
            log.error(f"[{self.account}] Position save failed: {e}")

    def add(self, symbol: str, qty: float, price: float) -> None:
        """Record new position."""
        with self._lock:
            self._positions[symbol] = Position(
                symbol=symbol,
                quantity=qty,
                entry_price=price,
                entry_time=datetime.now(KST).isoformat(),
            )
            self._save()
        log.info(f"[{self.account}] Position added: {symbol}")

    def remove(self, symbol: str) -> None:
        """Remove position."""
        with self._lock:
            if symbol in self._positions:
                del self._positions[symbol]
                self._save()
                log.info(f"[{self.account}] Position removed: {symbol}")

    def update_quantity(self, symbol: str, qty: float) -> None:
        """Update tracked quantity while preserving entry metadata."""
        with self._lock:
            pos = self._positions.get(symbol)
            if not pos:
                return
            if qty <= 0:
                del self._positions[symbol]
                self._save()
                log.info(f"[{self.account}] Position removed: {symbol}")
                return
            self._positions[symbol] = Position(
                symbol=symbol,
                quantity=qty,
                entry_price=pos.entry_price,
                entry_time=pos.entry_time,
            )
            self._save()
        log.info(f"[{self.account}] Position updated: {symbol} qty={qty:.8f}")

    def get(self, symbol: str) -> Position | None:
        """Get position or None."""
        with self._lock:
            return self._positions.get(symbol)

    def has(self, symbol: str) -> bool:
        """Check if position exists."""
        with self._lock:
            return symbol in self._positions

    @property
    def symbols(self) -> list[str]:
        """All tracked symbols."""
        with self._lock:
            return list(self._positions.keys())
