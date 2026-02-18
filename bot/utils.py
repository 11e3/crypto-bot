"""Utility functions."""

import logging
import time
import urllib.parse
import urllib.request

from .config import get_config

log = logging.getLogger("vbo")

_last_error_times: dict[str, float] = {}


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


def send_telegram_error(message: str, cooldown: float = 300.0, key: str = "global") -> bool:
    """Send error notification via Telegram (keyed throttle)."""
    now = time.time()
    last = _last_error_times.get(key, 0.0)
    if now - last < cooldown:
        return False
    _last_error_times[key] = now
    return send_telegram(f"\u26a0\ufe0f <b>ERROR</b>\n{message}")
