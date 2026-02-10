"""Tests for bot.logger module."""

import csv
from pathlib import Path
from unittest.mock import patch

import pytest

from bot.logger import Trade, TradeLogger


class TestTrade:
    """Tests for Trade dataclass."""

    def test_trade_creation(self) -> None:
        """Should create trade with all fields."""
        trade = Trade(
            timestamp="2024-01-15T10:00:00+09:00",
            date="2024-01-15",
            action="BUY",
            symbol="BTC",
            price=50000.0,
            quantity=0.5,
            amount=25000.0,
        )

        assert trade.action == "BUY"
        assert trade.symbol == "BTC"
        assert trade.price == 50000.0
        assert trade.profit_pct is None
        assert trade.profit_krw is None

    def test_trade_buy_factory(self) -> None:
        """Should create buy trade via factory method."""
        with patch("bot.logger.datetime") as mock_dt:
            mock_now = mock_dt.now.return_value
            mock_now.isoformat.return_value = "2024-01-15T10:00:00+09:00"
            mock_now.strftime.return_value = "2024-01-15"

            trade = Trade.buy(
                symbol="BTC",
                price=50000.0,
                qty=0.5,
                amount=25000.0,
            )

        assert trade.action == "BUY"
        assert trade.symbol == "BTC"
        assert trade.price == 50000.0
        assert trade.quantity == 0.5
        assert trade.amount == 25000.0
        assert trade.profit_pct is None
        assert trade.profit_krw is None

    def test_trade_sell_factory(self) -> None:
        """Should create sell trade via factory method."""
        with patch("bot.logger.datetime") as mock_dt:
            mock_now = mock_dt.now.return_value
            mock_now.isoformat.return_value = "2024-01-15T10:00:00+09:00"
            mock_now.strftime.return_value = "2024-01-15"

            trade = Trade.sell(
                symbol="BTC",
                price=55000.0,
                qty=0.5,
                amount=27500.0,
                profit_pct=10.0,
                profit_krw=2500.0,
            )

        assert trade.action == "SELL"
        assert trade.symbol == "BTC"
        assert trade.price == 55000.0
        assert trade.quantity == 0.5
        assert trade.amount == 27500.0
        assert trade.profit_pct == 10.0
        assert trade.profit_krw == 2500.0


class TestTradeLogger:
    """Tests for TradeLogger class."""

    @pytest.fixture
    def logger(self, temp_dir: Path) -> TradeLogger:
        """Create logger with temp directory."""
        with patch.object(TradeLogger, "__init__", lambda self, account: None):
            logger = TradeLogger.__new__(TradeLogger)
            logger.account = "test_account"
            logger.log_dir = temp_dir / "logs" / "test_account"
            logger.log_dir.mkdir(parents=True, exist_ok=True)
            return logger

    def test_log_creates_date_csv_with_header(self, logger: TradeLogger) -> None:
        """Should create date-specific CSV file with headers on first log."""
        trade = Trade(
            timestamp="2024-01-15T10:00:00+09:00",
            date="2024-01-15",
            action="BUY",
            symbol="BTC",
            price=50000.0,
            quantity=0.5,
            amount=25000.0,
        )

        logger.log(trade)

        path = logger.log_dir / "trades_2024-01-15.csv"
        assert path.exists()

        with open(path) as f:
            reader = csv.reader(f)
            header = next(reader)

        assert header == TradeLogger.FIELDS

    def test_log_appends_trade(self, logger: TradeLogger) -> None:
        """Should append trade to date-specific CSV."""
        trade = Trade(
            timestamp="2024-01-15T10:00:00+09:00",
            date="2024-01-15",
            action="BUY",
            symbol="BTC",
            price=50000.0,
            quantity=0.5,
            amount=25000.0,
        )

        logger.log(trade)

        path = logger.log_dir / "trades_2024-01-15.csv"
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["action"] == "BUY"
        assert rows[0]["symbol"] == "BTC"
        assert float(rows[0]["price"]) == 50000.0

    def test_log_multiple_trades_same_date(self, logger: TradeLogger) -> None:
        """Should append multiple trades to same date file."""
        trade1 = Trade(
            timestamp="2024-01-15T10:00:00+09:00",
            date="2024-01-15",
            action="BUY",
            symbol="BTC",
            price=50000.0,
            quantity=0.5,
            amount=25000.0,
        )
        trade2 = Trade(
            timestamp="2024-01-15T11:00:00+09:00",
            date="2024-01-15",
            action="SELL",
            symbol="BTC",
            price=55000.0,
            quantity=0.5,
            amount=27500.0,
            profit_pct=10.0,
            profit_krw=2500.0,
        )

        logger.log(trade1)
        logger.log(trade2)

        path = logger.log_dir / "trades_2024-01-15.csv"
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["action"] == "BUY"
        assert rows[1]["action"] == "SELL"
        assert float(rows[1]["profit_pct"]) == 10.0

    def test_log_different_dates_creates_separate_files(self, logger: TradeLogger) -> None:
        """Should create separate CSV files for different dates."""
        trade1 = Trade(
            timestamp="2024-01-15T10:00:00+09:00",
            date="2024-01-15",
            action="BUY",
            symbol="BTC",
            price=50000.0,
            quantity=0.5,
            amount=25000.0,
        )
        trade2 = Trade(
            timestamp="2024-01-16T10:00:00+09:00",
            date="2024-01-16",
            action="BUY",
            symbol="ETH",
            price=3000.0,
            quantity=1.0,
            amount=3000.0,
        )

        logger.log(trade1)
        logger.log(trade2)

        assert (logger.log_dir / "trades_2024-01-15.csv").exists()
        assert (logger.log_dir / "trades_2024-01-16.csv").exists()

    def test_does_not_overwrite_existing(self, logger: TradeLogger) -> None:
        """Should not overwrite existing date CSV file."""
        path = logger.log_dir / "trades_2024-01-14.csv"

        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, TradeLogger.FIELDS)
            writer.writeheader()
            writer.writerow({
                "timestamp": "2024-01-14T10:00:00+09:00",
                "date": "2024-01-14",
                "action": "BUY",
                "symbol": "ETH",
                "price": 3000.0,
                "quantity": 1.0,
                "amount": 3000.0,
                "profit_pct": "",
                "profit_krw": "",
            })

        # Log another trade on same date
        trade = Trade(
            timestamp="2024-01-14T15:00:00+09:00",
            date="2024-01-14",
            action="SELL",
            symbol="ETH",
            price=3200.0,
            quantity=1.0,
            amount=3200.0,
            profit_pct=6.67,
            profit_krw=200.0,
        )
        logger.log(trade)

        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["symbol"] == "ETH"
        assert rows[0]["action"] == "BUY"
        assert rows[1]["action"] == "SELL"
