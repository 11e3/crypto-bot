"""Trade logging to CSV."""

import csv
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

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
    profit_pct: Optional[float] = None
    profit_krw: Optional[float] = None

    @classmethod
    def buy(cls, symbol: str, price: float, qty: float, amount: float) -> "Trade":
        return cls(
            timestamp=datetime.now().isoformat(),
            date=datetime.now().strftime("%Y-%m-%d"),
            action="BUY", symbol=symbol, price=price, quantity=qty, amount=amount
        )

    @classmethod
    def sell(cls, symbol: str, price: float, qty: float, amount: float,
             profit_pct: float, profit_krw: float) -> "Trade":
        return cls(
            timestamp=datetime.now().isoformat(),
            date=datetime.now().strftime("%Y-%m-%d"),
            action="SELL", symbol=symbol, price=price, quantity=qty, amount=amount,
            profit_pct=profit_pct, profit_krw=profit_krw
        )


class TradeLogger:
    """CSV trade logger."""
    FIELDS = ["timestamp", "date", "action", "symbol", "price", "quantity",
              "amount", "profit_pct", "profit_krw"]

    def __init__(self, account: str):
        self.account = account
        self.path = Path(f"logs/{account}/trades.csv")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_file()

    def _init_file(self):
        if not self.path.exists():
            with open(self.path, 'w', newline='') as f:
                csv.DictWriter(f, self.FIELDS).writeheader()

    def log(self, trade: Trade):
        """Append trade to CSV."""
        with open(self.path, 'a', newline='') as f:
            csv.DictWriter(f, self.FIELDS).writerow(asdict(trade))
        log.info(f"[{self.account}] {trade.action} {trade.symbol} logged")
