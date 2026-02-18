"""Tests for bot.tracker module."""

import json
from pathlib import Path
from threading import Lock
from unittest.mock import patch

import pytest

from bot.tracker import Position, PositionTracker


class TestPosition:
    """Tests for Position dataclass."""

    def test_position_creation(self) -> None:
        """Should create position with all fields."""
        position = Position(
            symbol="BTC",
            quantity=0.5,
            entry_price=50000.0,
            entry_time="2024-01-15T10:00:00+09:00",
        )

        assert position.symbol == "BTC"
        assert position.quantity == 0.5
        assert position.entry_price == 50000.0
        assert position.entry_time == "2024-01-15T10:00:00+09:00"


class TestPositionTracker:
    """Tests for PositionTracker class."""

    @pytest.fixture
    def tracker(self, temp_dir: Path) -> PositionTracker:
        """Create tracker with temp directory."""
        with patch.object(PositionTracker, "__init__", lambda self, account: None):
            tracker = PositionTracker.__new__(PositionTracker)
            tracker.account = "test_account"
            tracker._path = temp_dir / "logs" / "test_account" / "positions.json"
            tracker._path.parent.mkdir(parents=True, exist_ok=True)
            tracker._lock = Lock()
            tracker._positions = {}
            return tracker

    def test_add_position(self, tracker: PositionTracker) -> None:
        """Should add and save position."""
        tracker.add("BTC", 0.5, 50000.0)

        assert tracker.has("BTC")
        position = tracker.get("BTC")
        assert position is not None
        assert position.quantity == 0.5
        assert position.entry_price == 50000.0

    def test_remove_position(self, tracker: PositionTracker) -> None:
        """Should remove position."""
        tracker.add("BTC", 0.5, 50000.0)
        tracker.remove("BTC")

        assert not tracker.has("BTC")
        assert tracker.get("BTC") is None

    def test_remove_nonexistent_position(self, tracker: PositionTracker) -> None:
        """Should handle removing nonexistent position."""
        tracker.remove("NONEXISTENT")
        # Should not raise

    def test_update_quantity_preserves_entry_metadata(self, tracker: PositionTracker) -> None:
        """Should update quantity without changing entry price/time."""
        tracker.add("BTC", 0.5, 50000.0)
        original = tracker.get("BTC")
        assert original is not None

        tracker.update_quantity("BTC", 0.2)
        updated = tracker.get("BTC")

        assert updated is not None
        assert updated.quantity == 0.2
        assert updated.entry_price == original.entry_price
        assert updated.entry_time == original.entry_time

    def test_update_quantity_removes_when_non_positive(self, tracker: PositionTracker) -> None:
        tracker.add("BTC", 0.5, 50000.0)

        tracker.update_quantity("BTC", 0.0)

        assert tracker.get("BTC") is None

    def test_get_nonexistent_position(self, tracker: PositionTracker) -> None:
        """Should return None for nonexistent position."""
        result = tracker.get("NONEXISTENT")

        assert result is None

    def test_has_position(self, tracker: PositionTracker) -> None:
        """Should check position existence."""
        assert not tracker.has("BTC")

        tracker.add("BTC", 0.5, 50000.0)

        assert tracker.has("BTC")

    def test_symbols_property(self, tracker: PositionTracker) -> None:
        """Should return list of tracked symbols."""
        tracker.add("BTC", 0.5, 50000.0)
        tracker.add("ETH", 1.0, 3000.0)

        symbols = tracker.symbols

        assert set(symbols) == {"BTC", "ETH"}

    def test_save_creates_json_file(self, tracker: PositionTracker) -> None:
        """Should save positions to JSON file."""
        tracker.add("BTC", 0.5, 50000.0)

        assert tracker._path.exists()
        data = json.loads(tracker._path.read_text())
        assert "BTC" in data
        assert data["BTC"]["quantity"] == 0.5

    def test_save_atomic_write_leaves_no_tmp_file(self, tracker: PositionTracker) -> None:
        """Should persist via temp file replacement without leftover tmp file."""
        tracker.add("BTC", 0.5, 50000.0)

        tmp_path = tracker._path.with_suffix(f"{tracker._path.suffix}.tmp")
        assert tracker._path.exists()
        assert not tmp_path.exists()

    def test_load_existing_positions(self, temp_dir: Path) -> None:
        """Should load existing positions from file."""
        # Create positions file
        positions_dir = temp_dir / "logs" / "test_account"
        positions_dir.mkdir(parents=True)
        positions_file = positions_dir / "positions.json"
        positions_file.write_text(
            json.dumps(
                {
                    "BTC": {
                        "symbol": "BTC",
                        "quantity": 0.5,
                        "entry_price": 50000.0,
                        "entry_time": "2024-01-15T10:00:00+09:00",
                    }
                }
            )
        )

        # Create tracker
        with patch("bot.tracker.Path") as mock_path:
            mock_path.return_value = positions_file

            tracker = PositionTracker.__new__(PositionTracker)
            tracker.account = "test_account"
            tracker._path = positions_file
            tracker._lock = Lock()
            tracker._positions = tracker._load()

        assert tracker.has("BTC")
        assert tracker.get("BTC").quantity == 0.5

    def test_load_handles_corrupted_file(self, temp_dir: Path) -> None:
        """Should handle corrupted positions file."""
        positions_dir = temp_dir / "logs" / "test_account"
        positions_dir.mkdir(parents=True)
        positions_file = positions_dir / "positions.json"
        positions_file.write_text("invalid json{{{")

        tracker = PositionTracker.__new__(PositionTracker)
        tracker.account = "test_account"
        tracker._path = positions_file
        tracker._lock = Lock()
        tracker._positions = tracker._load()

        assert len(tracker._positions) == 0

    def test_load_handles_missing_file(self, temp_dir: Path) -> None:
        """Should handle missing positions file."""
        positions_file = temp_dir / "logs" / "test_account" / "positions.json"

        tracker = PositionTracker.__new__(PositionTracker)
        tracker.account = "test_account"
        tracker._path = positions_file
        tracker._lock = Lock()
        tracker._positions = tracker._load()

        assert len(tracker._positions) == 0

    def test_init_sets_path_and_loads_positions(self, temp_dir: Path) -> None:
        """Should initialize path and load existing positions."""
        logs_dir = temp_dir / "logs" / "real_account"
        logs_dir.mkdir(parents=True)
        positions_file = logs_dir / "positions.json"
        positions_file.write_text(
            json.dumps(
                {
                    "BTC": {
                        "symbol": "BTC",
                        "quantity": 1.0,
                        "entry_price": 40000.0,
                        "entry_time": "2024-01-01T00:00:00+09:00",
                    }
                }
            )
        )

        with patch("bot.tracker.Path", return_value=positions_file):
            tracker = PositionTracker("real_account")

        assert tracker.account == "real_account"
        assert tracker._path == positions_file
        assert tracker.has("BTC")

    def test_save_handles_write_error(self, tracker: PositionTracker) -> None:
        """Should swallow save errors and keep process alive."""
        tracker._positions["BTC"] = Position("BTC", 0.1, 50000.0, "t")
        with patch("pathlib.Path.write_text", side_effect=RuntimeError("disk error")):
            tracker._save()  # should not raise
