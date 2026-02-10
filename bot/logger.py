"""Trade logging to CSV."""

import csv
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))

log = logging.getLogger("vbo")


@dataclass
class Trade:
    """Single trade record."""
    timestamp: str
    date: str
    action: str  # BUY or SELL
    symbol: str
    price: float
    quantity: float
    amount: float
    profit_pct: float | None = None
    profit_krw: float | None = None

    @classmethod
    def buy(cls, symbol: str, price: float, qty: float, amount: float) -> "Trade":
        return cls(
            timestamp=datetime.now(KST).isoformat(),
            date=datetime.now(KST).strftime("%Y-%m-%d"),
            action="BUY", symbol=symbol, price=price, quantity=qty, amount=amount
        )

    @classmethod
    def sell(cls, symbol: str, price: float, qty: float, amount: float,
             profit_pct: float, profit_krw: float) -> "Trade":
        return cls(
            timestamp=datetime.now(KST).isoformat(),
            date=datetime.now(KST).strftime("%Y-%m-%d"),
            action="SELL", symbol=symbol, price=price, quantity=qty, amount=amount,
            profit_pct=profit_pct, profit_krw=profit_krw
        )


class TradeLogger:
    """CSV trade logger."""
    FIELDS = ["timestamp", "date", "action", "symbol", "price", "quantity",
              "amount", "profit_pct", "profit_krw"]

    def __init__(self, account: str):
        self.account = account
        self.log_dir = Path(f"logs/{account}")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, date: str) -> Path:
        """Get CSV path for a specific date."""
        return self.log_dir / f"trades_{date}.csv"

    def _ensure_file(self, path: Path):
        """Create CSV with header if it doesn't exist."""
        if not path.exists():
            with open(path, 'w', newline='') as f:
                csv.DictWriter(f, self.FIELDS).writeheader()

    def log(self, trade: Trade):
        """Append trade to date-specific CSV."""
        path = self._get_path(trade.date)
        self._ensure_file(path)
        with open(path, 'a', newline='') as f:
            csv.DictWriter(f, self.FIELDS).writerow(asdict(trade))
        log.info(f"[{self.account}] {trade.action} {trade.symbol} logged")
