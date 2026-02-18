"""Tests for bot.utils module."""

from unittest.mock import patch

import pytest

import bot.utils as utils_module
from bot.utils import send_telegram, send_telegram_error


class TestSendTelegramError:
    """Tests for send_telegram_error function."""

    @pytest.fixture(autouse=True)
    def reset_throttle(self) -> None:
        """Reset throttle state before each test."""
        utils_module._last_error_times.clear()

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

    def test_different_keys_do_not_block_each_other(self) -> None:
        """Should throttle independently per key."""
        with (
            patch("bot.utils.send_telegram", return_value=True) as mock_send,
            patch("bot.utils.time") as mock_time,
        ):
            mock_time.time.return_value = 1000.0
            send_telegram_error("First", key="a")

            mock_time.time.return_value = 1001.0
            result = send_telegram_error("Second", key="b")

            assert result is True
            assert mock_send.call_count == 2


class TestSendTelegram:
    """Tests for send_telegram function."""

    def test_returns_false_without_token_or_chat_id(self) -> None:
        with patch("bot.utils.get_config") as mock_cfg:
            mock_cfg.return_value = type("Cfg", (), {"telegram_token": "", "telegram_chat_id": ""})()
            assert send_telegram("hello") is False

    def test_send_success(self) -> None:
        with (
            patch("bot.utils.get_config") as mock_cfg,
            patch("bot.utils.urllib.request.urlopen") as mock_urlopen,
        ):
            mock_cfg.return_value = type(
                "Cfg",
                (),
                {"telegram_token": "token", "telegram_chat_id": "chat"},
            )()
            mock_urlopen.return_value = object()
            assert send_telegram("hello") is True

    def test_send_handles_exception(self) -> None:
        with (
            patch("bot.utils.get_config") as mock_cfg,
            patch("bot.utils.urllib.request.urlopen", side_effect=RuntimeError("boom")),
        ):
            mock_cfg.return_value = type(
                "Cfg",
                (),
                {"telegram_token": "token", "telegram_chat_id": "chat"},
            )()
            assert send_telegram("hello") is False
