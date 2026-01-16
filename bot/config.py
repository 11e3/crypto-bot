"""Configuration management."""

import os
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache, wraps
from typing import Callable, TypeVar

log = logging.getLogger("vbo")
T = TypeVar('T')


def load_env(path: str = ".env") -> None:
    """Load environment variables from .env file."""
    env_file = Path(path)
    if not env_file.exists():
        return

    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.split("#")[0].strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def retry(max_attempts: int = 3, delay: float = 1.0) -> Callable:
    """Retry decorator with exponential backoff."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_error = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_attempts - 1:
                        wait = delay * (2 ** attempt)
                        log.warning(f"{func.__name__} failed (attempt {attempt + 1}), retry in {wait}s: {e}")
                        time.sleep(wait)
            raise last_error
        return wrapper
    return decorator


@dataclass(frozen=True)
class Config:
    """Immutable bot configuration."""
    symbols: tuple[str, ...]
    ma_short: int
    btc_ma: int
    noise_ratio: float
    telegram_token: str
    telegram_chat_id: str

    # Trading constants
    FEE: float = 0.0005
    MIN_ORDER_KRW: int = 5000
    CHECK_INTERVAL_SEC: int = 1
    LATE_ENTRY_PCT: float = 1.0      # ±1% of target
    ORDER_DELAY_SEC: float = 0.2     # delay between orders
    API_RETRY_COUNT: int = 3
    API_RETRY_DELAY: float = 1.0

    def __post_init__(self):
        """Validate config values."""
        errors = []
        if not self.symbols:
            errors.append("symbols cannot be empty")
        if self.ma_short < 1:
            errors.append(f"ma_short must be >= 1, got {self.ma_short}")
        if self.btc_ma < 1:
            errors.append(f"btc_ma must be >= 1, got {self.btc_ma}")
        if not 0 < self.noise_ratio <= 1:
            errors.append(f"noise_ratio must be in (0, 1], got {self.noise_ratio}")
        if errors:
            raise ValueError(f"Invalid config: {'; '.join(errors)}")


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Get cached config instance (call after load_env)."""
    symbols = tuple(s.strip() for s in os.getenv("SYMBOLS", "BTC,ETH").split(",") if s.strip())
    return Config(
        symbols=symbols,
        ma_short=int(os.getenv("MA_SHORT", "5")),
        btc_ma=int(os.getenv("BTC_MA", "20")),
        noise_ratio=float(os.getenv("NOISE_RATIO", "0.5")),
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
    )
