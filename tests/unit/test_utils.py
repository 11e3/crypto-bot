"""Tests for bot.utils module."""

from unittest.mock import patch

import pytest

import bot.utils as utils_module
from bot.utils import send_telegram_error


class TestSendTelegramError:
    """Tests for send_telegram_error function."""

    @pytest.fixture(autouse=True)
    def reset_throttle(self) -> None:
        """Reset throttle state before each test."""
        utils_module._last_error_time = 0.0

    def test_sends_error_with_prefix(self) -> None:
        """Should send message with error prefix."""
        with patch("bot.utils.send_telegram", return_value=True) as mock_send:
            result = send_telegram_error("Test error")

            assert result is True
            mock_send.assert_called_once()
            msg = mock_send.call_args[0][0]
            assert "ERROR" in msg
            assert "Test error" in msg

    def test_throttle_blocks_rapid_calls(self) -> None:
        """Should block messages within cooldown period."""
        with (
            patch("bot.utils.send_telegram", return_value=True) as mock_send,
            patch("bot.utils.time") as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            send_telegram_error("First error")

            mock_time.time.return_value = 1100.0  # 100s later (< 300s cooldown)
            result = send_telegram_error("Second error")

            assert result is False
            assert mock_send.call_count == 1

    def test_throttle_allows_after_cooldown(self) -> None:
        """Should allow messages after cooldown expires."""
        with (
            patch("bot.utils.send_telegram", return_value=True) as mock_send,
            patch("bot.utils.time") as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            send_telegram_error("First error")

            mock_time.time.return_value = 1400.0  # 400s later (> 300s cooldown)
            result = send_telegram_error("Second error")

            assert result is True
            assert mock_send.call_count == 2

    def test_custom_cooldown(self) -> None:
        """Should respect custom cooldown value."""
        with (
            patch("bot.utils.send_telegram", return_value=True) as mock_send,
            patch("bot.utils.time") as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            send_telegram_error("First", cooldown=10.0)

            mock_time.time.return_value = 1005.0  # 5s later (< 10s cooldown)
            result = send_telegram_error("Second", cooldown=10.0)
            assert result is False

            mock_time.time.return_value = 1015.0  # 15s later (> 10s cooldown)
            result = send_telegram_error("Third", cooldown=10.0)
            assert result is True
            assert mock_send.call_count == 2
