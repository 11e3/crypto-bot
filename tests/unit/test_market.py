"""Tests for bot.market module."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from bot.market import (
    KST,
    DailySignals,
    Signal,
    get_price,
)


class TestSignal:
    """Tests for Signal dataclass."""

    def test_signal_creation(self) -> None:
        """Should create signal with all fields."""
        signal = Signal(
            symbol="BTC",
            target_price=50000.0,
            can_buy=True,
            should_sell=False,
        )

        assert signal.symbol == "BTC"
        assert signal.target_price == 50000.0
        assert signal.can_buy is True
        assert signal.should_sell is False

    def test_signal_is_frozen(self) -> None:
        """Should be immutable."""
        signal = Signal(
            symbol="BTC",
            target_price=50000.0,
            can_buy=True,
            should_sell=False,
        )

        with pytest.raises(AttributeError):
            signal.target_price = 60000.0  # type: ignore


class TestGetPrice:
    """Tests for get_price function."""

    def test_get_price_success(self, mock_upbit: MagicMock) -> None:
        """Should return price on success."""
        mock_upbit.get_current_price.return_value = 50000.0

        price = get_price("BTC")

        assert price == 50000.0
        mock_upbit.get_current_price.assert_called_once_with("KRW-BTC")

    def test_get_price_returns_none_on_error(self, mock_upbit: MagicMock) -> None:
        """Should return None on error."""
        mock_upbit.get_current_price.side_effect = Exception("API Error")

        price = get_price("BTC")

        assert price is None

    def test_get_price_returns_none_on_no_data(self, mock_upbit: MagicMock) -> None:
        """Should return None when no price data."""
        mock_upbit.get_current_price.return_value = None

        price = get_price("BTC")

        assert price is None


class TestDailySignals:
    """Tests for DailySignals class."""

    @pytest.fixture
    def signals(self) -> DailySignals:
        """Create fresh DailySignals instance."""
        return DailySignals()

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Mock config."""
        with patch("bot.market.get_config") as mock:
            mock.return_value = MagicMock(
                symbols=("BTC", "ETH"),
                ma_short=5,
                btc_ma=20,
                noise_ratio=0.5,
            )
            yield mock

    def test_trading_date_before_9am(self) -> None:
        """Should return previous date before 9AM KST."""
        # 8:59 AM KST
        mock_time = datetime(2024, 1, 15, 8, 59, tzinfo=KST)

        with patch("bot.market.datetime") as mock_dt:
            mock_dt.now.return_value = mock_time

            result = DailySignals._trading_date()

        assert result == "2024-01-14"

    def test_trading_date_after_9am(self) -> None:
        """Should return current date after 9AM KST."""
        # 9:01 AM KST
        mock_time = datetime(2024, 1, 15, 9, 1, tzinfo=KST)

        with patch("bot.market.datetime") as mock_dt:
            mock_dt.now.return_value = mock_time

            result = DailySignals._trading_date()

        assert result == "2024-01-15"

    def test_calculate_success(
        self,
        signals: DailySignals,
        mock_upbit: MagicMock,
        mock_config: MagicMock,
        sample_ohlcv: pd.DataFrame,
    ) -> None:
        """Should calculate signals successfully."""
        mock_upbit.get_ohlcv.return_value = sample_ohlcv

        result = signals._calculate()

        assert result is True
        assert "BTC" in signals._signals
        assert "ETH" in signals._signals

    def test_calculate_btc_data_insufficient(
        self,
        signals: DailySignals,
        mock_upbit: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Should return False when BTC data insufficient."""
        mock_upbit.get_ohlcv.return_value = None

        result = signals._calculate()

        assert result is False

    def test_calculate_signal_values(
        self,
        signals: DailySignals,
        mock_upbit: MagicMock,
        mock_config: MagicMock,
        sample_ohlcv: pd.DataFrame,
    ) -> None:
        """Should calculate correct target price."""
        mock_upbit.get_ohlcv.return_value = sample_ohlcv

        signals._calculate()
        signal = signals._signals.get("BTC")

        assert signal is not None
        # target = today_open + (prev_high - prev_low) * noise_ratio
        # today_open = 129 (last row open)
        # prev_range = 133 - 123 = 10 (second to last row high - low)
        # target = 129 + 10 * 0.5 = 134
        expected_target = (
            sample_ohlcv["open"].iloc[-1]
            + (sample_ohlcv["high"].iloc[-2] - sample_ohlcv["low"].iloc[-2]) * 0.5
        )
        assert signal.target_price == expected_target

    def test_get_triggers_recalculate_on_new_day(
        self,
        signals: DailySignals,
        mock_upbit: MagicMock,
        mock_config: MagicMock,
        sample_ohlcv: pd.DataFrame,
    ) -> None:
        """Should recalculate when date changes."""
        mock_upbit.get_ohlcv.return_value = sample_ohlcv
        signals._date = "2024-01-01"  # Old date

        with patch.object(DailySignals, "_trading_date", return_value="2024-01-15"):
            signals.get("BTC")

        # Should have recalculated
        assert signals._date == "2024-01-15"

    def test_all_returns_all_signals(
        self,
        signals: DailySignals,
        mock_upbit: MagicMock,
        mock_config: MagicMock,
        sample_ohlcv: pd.DataFrame,
    ) -> None:
        """Should return all calculated signals."""
        mock_upbit.get_ohlcv.return_value = sample_ohlcv

        with patch.object(DailySignals, "_trading_date", return_value="2024-01-15"):
            result = signals.all()

        assert len(result) == 2
        assert "BTC" in result
        assert "ETH" in result

    def test_calculate_returns_false_on_btc_exception(
        self,
        signals: DailySignals,
        mock_upbit: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Should return False when BTC fetch raises exception."""
        mock_upbit.get_ohlcv.side_effect = RuntimeError("btc api down")

        result = signals._calculate()

        assert result is False

    def test_calculate_returns_false_when_all_symbol_data_missing(
        self,
        signals: DailySignals,
        mock_upbit: MagicMock,
        mock_config: MagicMock,
        sample_ohlcv: pd.DataFrame,
    ) -> None:
        """Should return False when no symbol signal is generated."""
        mock_upbit.get_ohlcv.side_effect = [sample_ohlcv, None, None]

        result = signals._calculate()

        assert result is False

    def test_calculate_continues_on_symbol_exception(
        self,
        signals: DailySignals,
        mock_upbit: MagicMock,
        mock_config: MagicMock,
        sample_ohlcv: pd.DataFrame,
    ) -> None:
        """Should continue when one symbol fails and still build others."""

        def _side_effect(ticker: str, **_: object):
            if ticker == "KRW-BTC":
                return sample_ohlcv
            if ticker == "KRW-ETH":
                raise RuntimeError("eth error")
            return sample_ohlcv

        mock_upbit.get_ohlcv.side_effect = _side_effect

        result = signals._calculate()

        assert result is True
        assert "BTC" in signals._signals

    def test_all_does_not_recalculate_when_date_unchanged(
        self,
        signals: DailySignals,
        mock_upbit: MagicMock,
        mock_config: MagicMock,
        sample_ohlcv: pd.DataFrame,
    ) -> None:
        """Should return cached signals when trading date unchanged."""
        mock_upbit.get_ohlcv.return_value = sample_ohlcv
        with patch.object(DailySignals, "_trading_date", return_value="2024-01-15"):
            signals._calculate()
            before = dict(signals._signals)
            result = signals.all()

        assert result == before

    def test_all_clears_stale_signals_when_recalculate_fails(self, signals: DailySignals) -> None:
        """Should fail-closed and clear stale signals on date rollover failure."""
        signals._date = "2024-01-14"
        signals._signals = {
            "BTC": Signal("BTC", 50000.0, can_buy=True, should_sell=False),
        }

        with (
            patch.object(DailySignals, "_trading_date", return_value="2024-01-15"),
            patch.object(DailySignals, "_calculate", return_value=False),
        ):
            result = signals.all()

        assert result == {}

    def test_all_applies_retry_backoff_after_failed_recalculate(self, signals: DailySignals) -> None:
        """Should avoid repeated recalc attempts within backoff window."""
        signals._date = "2024-01-14"

        with (
            patch.object(DailySignals, "_trading_date", return_value="2024-01-15"),
            patch.object(DailySignals, "_calculate", return_value=False) as mock_calc,
            patch("bot.market.time.time") as mock_time,
        ):
            mock_time.side_effect = [1000.0, 1005.0]
            signals.all()
            signals.all()

        assert mock_calc.call_count == 1
