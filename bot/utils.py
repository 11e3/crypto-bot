"""Utility functions."""

import logging
import time
import urllib.parse
import urllib.request

from .config import get_config

log = logging.getLogger("vbo")

_last_error_time: float = 0.0


def send_telegram(message: str) -> bool:
    """Send telegram notification. Returns success status."""
    cfg = get_config()
    if not cfg.telegram_token or not cfg.telegram_chat_id:
        return False

    try:
        url = f"https://api.telegram.org/bot{cfg.telegram_token}/sendMessage"
        data = urllib.parse.urlencode(
            {"chat_id": cfg.telegram_chat_id, "text": message, "parse_mode": "HTML"}
        ).encode()
        urllib.request.urlopen(urllib.request.Request(url, data), timeout=10)
        return True
    except Exception as e:
        log.warning(f"Telegram failed: {e}")
        return False


def send_telegram_error(message: str, cooldown: float = 300.0) -> bool:
    """Send error notification via Telegram (throttled to prevent spam)."""
    global _last_error_time  # noqa: PLW0603
    now = time.time()
    if now - _last_error_time < cooldown:
        return False
    _last_error_time = now
    return send_telegram(f"\u26a0\ufe0f <b>ERROR</b>\n{message}")
