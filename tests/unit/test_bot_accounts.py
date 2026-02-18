"""Tests for account loading in bot.bot."""

from unittest.mock import MagicMock, patch

import pytest

from bot.bot import VBOBot


class TestLoadAccounts:
    """Tests for VBOBot._load_accounts."""

    def test_load_accounts_skips_missing_index(self) -> None:
        """Should load later accounts even if an index is empty."""
        bot = VBOBot.__new__(VBOBot)
        bot.accounts = []

        with patch("bot.bot.os.getenv") as mock_getenv:
            env = {
                "ACCOUNT_1_NAME": "main",
                "ACCOUNT_1_ACCESS_KEY": "k1",
                "ACCOUNT_1_SECRET_KEY": "s1",
                "ACCOUNT_3_NAME": "sub",
                "ACCOUNT_3_ACCESS_KEY": "k3",
                "ACCOUNT_3_SECRET_KEY": "s3",
            }
            mock_getenv.side_effect = lambda key: env.get(key)

            with patch("bot.bot.Account") as mock_account:
                mock_account.side_effect = [MagicMock(), MagicMock()]
                VBOBot._load_accounts(bot)

        assert len(bot.accounts) == 2

    def test_load_accounts_skips_incomplete_credentials(self) -> None:
        """Should skip partially configured account entries."""
        bot = VBOBot.__new__(VBOBot)
        bot.accounts = []

        with patch("bot.bot.os.getenv") as mock_getenv:
            env = {
                "ACCOUNT_1_NAME": "main",
                "ACCOUNT_1_ACCESS_KEY": "k1",
                "ACCOUNT_1_SECRET_KEY": "s1",
                "ACCOUNT_2_NAME": "broken",
                "ACCOUNT_2_ACCESS_KEY": "k2",
                # missing ACCOUNT_2_SECRET_KEY
            }
            mock_getenv.side_effect = lambda key: env.get(key)

            with patch("bot.bot.Account") as mock_account:
                mock_account.side_effect = [MagicMock()]
                VBOBot._load_accounts(bot)

        assert len(bot.accounts) == 1

    def test_load_accounts_exits_when_none_configured(self) -> None:
        """Should exit when no account is configured."""
        bot = VBOBot.__new__(VBOBot)
        bot.accounts = []

        with patch("bot.bot.os.getenv", return_value=None), pytest.raises(SystemExit):
            VBOBot._load_accounts(bot)
