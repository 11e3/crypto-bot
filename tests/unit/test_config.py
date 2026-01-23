"""Tests for bot.config module."""

import os
from pathlib import Path

import pytest

from bot.config import Config, get_config, load_env, retry


class TestLoadEnv:
    """Tests for load_env function."""

    def test_load_env_file_not_exists(self) -> None:
        """Should handle missing .env file gracefully."""
        load_env("/nonexistent/.env")
        # Should not raise

    def test_load_env_parses_simple_values(self, temp_dir: Path) -> None:
        """Should parse simple key=value pairs."""
        env_file = temp_dir / ".env"
        env_file.write_text("TEST_KEY=test_value\n")

        load_env(str(env_file))

        assert os.environ.get("TEST_KEY") == "test_value"

    def test_load_env_ignores_comments(self, temp_dir: Path) -> None:
        """Should ignore comment lines."""
        env_file = temp_dir / ".env"
        env_file.write_text("# This is a comment\nVALID_KEY=valid_value\n")

        load_env(str(env_file))

        assert os.environ.get("VALID_KEY") == "valid_value"

    def test_load_env_strips_quotes(self, temp_dir: Path) -> None:
        """Should strip quotes from values."""
        env_file = temp_dir / ".env"
        env_file.write_text('QUOTED_KEY="quoted_value"\n')

        load_env(str(env_file))

        assert os.environ.get("QUOTED_KEY") == "quoted_value"

    def test_load_env_ignores_inline_comments(self, temp_dir: Path) -> None:
        """Should strip inline comments."""
        env_file = temp_dir / ".env"
        env_file.write_text("INLINE_KEY=value # inline comment\n")

        load_env(str(env_file))

        assert os.environ.get("INLINE_KEY") == "value"

    def test_load_env_does_not_override_existing(self, temp_dir: Path) -> None:
        """Should not override existing environment variables."""
        os.environ["EXISTING_KEY"] = "original"
        env_file = temp_dir / ".env"
        env_file.write_text("EXISTING_KEY=new_value\n")

        load_env(str(env_file))

        assert os.environ.get("EXISTING_KEY") == "original"


class TestRetryDecorator:
    """Tests for retry decorator."""

    def test_retry_success_first_attempt(self) -> None:
        """Should return on first successful attempt."""
        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def success_func() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        result = success_func()

        assert result == "success"
        assert call_count == 1

    def test_retry_success_after_failures(self) -> None:
        """Should retry and succeed after initial failures."""
        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def flaky_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"

        result = flaky_func()

        assert result == "success"
        assert call_count == 3

    def test_retry_all_attempts_fail(self) -> None:
        """Should raise last error after all attempts fail."""
        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError(f"Error {call_count}")

        with pytest.raises(ValueError, match="Error 3"):
            always_fails()

        assert call_count == 3


class TestConfig:
    """Tests for Config dataclass."""

    def test_config_valid(self) -> None:
        """Should create config with valid values."""
        config = Config(
            symbols=("BTC", "ETH"),
            ma_short=5,
            btc_ma=20,
            noise_ratio=0.5,
            telegram_token="token",
            telegram_chat_id="123",
        )

        assert config.symbols == ("BTC", "ETH")
        assert config.ma_short == 5
        assert config.btc_ma == 20
        assert config.noise_ratio == 0.5

    def test_config_empty_symbols_raises(self) -> None:
        """Should raise on empty symbols."""
        with pytest.raises(ValueError, match="symbols cannot be empty"):
            Config(
                symbols=(),
                ma_short=5,
                btc_ma=20,
                noise_ratio=0.5,
                telegram_token="",
                telegram_chat_id="",
            )

    def test_config_invalid_ma_short_raises(self) -> None:
        """Should raise on invalid ma_short."""
        with pytest.raises(ValueError, match="ma_short must be >= 1"):
            Config(
                symbols=("BTC",),
                ma_short=0,
                btc_ma=20,
                noise_ratio=0.5,
                telegram_token="",
                telegram_chat_id="",
            )

    def test_config_invalid_btc_ma_raises(self) -> None:
        """Should raise on invalid btc_ma."""
        with pytest.raises(ValueError, match="btc_ma must be >= 1"):
            Config(
                symbols=("BTC",),
                ma_short=5,
                btc_ma=0,
                noise_ratio=0.5,
                telegram_token="",
                telegram_chat_id="",
            )

    def test_config_invalid_noise_ratio_raises(self) -> None:
        """Should raise on invalid noise_ratio."""
        with pytest.raises(ValueError, match="noise_ratio must be in"):
            Config(
                symbols=("BTC",),
                ma_short=5,
                btc_ma=20,
                noise_ratio=0,
                telegram_token="",
                telegram_chat_id="",
            )

        with pytest.raises(ValueError, match="noise_ratio must be in"):
            Config(
                symbols=("BTC",),
                ma_short=5,
                btc_ma=20,
                noise_ratio=1.5,
                telegram_token="",
                telegram_chat_id="",
            )

    def test_config_is_frozen(self) -> None:
        """Should be immutable."""
        config = Config(
            symbols=("BTC",),
            ma_short=5,
            btc_ma=20,
            noise_ratio=0.5,
            telegram_token="",
            telegram_chat_id="",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            config.ma_short = 10  # type: ignore


class TestGetConfig:
    """Tests for get_config function."""

    def test_get_config_defaults(self) -> None:
        """Should return config with defaults."""
        config = get_config()

        assert config.symbols == ("BTC", "ETH")
        assert config.ma_short == 5
        assert config.btc_ma == 20
        assert config.noise_ratio == 0.5

    def test_get_config_from_env(self, set_env) -> None:
        """Should read config from environment."""
        set_env(
            SYMBOLS="XRP,TRX,SOL",
            MA_SHORT="10",
            BTC_MA="30",
            NOISE_RATIO="0.7",
            TELEGRAM_BOT_TOKEN="my_token",
            TELEGRAM_CHAT_ID="my_chat",
        )

        config = get_config()

        assert config.symbols == ("XRP", "TRX", "SOL")
        assert config.ma_short == 10
        assert config.btc_ma == 30
        assert config.noise_ratio == 0.7
        assert config.telegram_token == "my_token"
        assert config.telegram_chat_id == "my_chat"

    def test_get_config_caches_result(self, set_env) -> None:
        """Should cache config instance."""
        set_env(SYMBOLS="BTC")
        config1 = get_config()

        set_env(SYMBOLS="ETH")
        config2 = get_config()

        assert config1 is config2
        assert config1.symbols == ("BTC",)
