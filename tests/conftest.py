"""Pytest configuration and shared fixtures."""

import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def clean_env() -> Generator[None, None, None]:
    """Clean environment variables before and after each test."""
    # Store original env
    original_env = os.environ.copy()

    # Clear config-related env vars
    env_keys = [
        "SYMBOLS", "MA_SHORT", "BTC_MA", "NOISE_RATIO",
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    ]
    for key in env_keys:
        os.environ.pop(key, None)

    # Clear lru_cache for get_config
    from bot.config import get_config
    get_config.cache_clear()

    yield

    # Restore original env
    os.environ.clear()
    os.environ.update(original_env)
    get_config.cache_clear()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_upbit() -> Generator[MagicMock, None, None]:
    """Mock pyupbit module."""
    with patch("bot.market.pyupbit") as mock:
        yield mock


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Create sample OHLCV data for testing."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    data = {
        "open": [100 + i for i in range(30)],
        "high": [105 + i for i in range(30)],
        "low": [95 + i for i in range(30)],
        "close": [102 + i for i in range(30)],
        "volume": [1000 + i * 10 for i in range(30)],
    }
    df = pd.DataFrame(data, index=dates)
    return df


@pytest.fixture
def set_env():
    """Helper to set environment variables."""
    def _set_env(**kwargs: str) -> None:
        for key, value in kwargs.items():
            os.environ[key] = value

    return _set_env
