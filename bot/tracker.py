"""Position tracking for bot-managed positions."""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

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

    def _save(self):
        try:
            data = {k: asdict(v) for k, v in self._positions.items()}
            self._path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.error(f"[{self.account}] Position save failed: {e}")

    def add(self, symbol: str, qty: float, price: float):
        """Record new position."""
        self._positions[symbol] = Position(
            symbol=symbol, quantity=qty, entry_price=price,
            entry_time=datetime.now(KST).isoformat()
        )
        self._save()
        log.info(f"[{self.account}] Position added: {symbol}")

    def remove(self, symbol: str):
        """Remove position."""
        if symbol in self._positions:
            del self._positions[symbol]
            self._save()
            log.info(f"[{self.account}] Position removed: {symbol}")

    def get(self, symbol: str) -> Optional[Position]:
        """Get position or None."""
        return self._positions.get(symbol)

    def has(self, symbol: str) -> bool:
        """Check if position exists."""
        return symbol in self._positions

    @property
    def symbols(self) -> list[str]:
        """All tracked symbols."""
        return list(self._positions.keys())
