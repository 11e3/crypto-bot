#!/usr/bin/env python3
"""VBO Trading Bot Entry Point."""

import asyncio
import contextlib
import logging
import os
import sys

try:
    from bot import VBOBot, load_env
    from bot.config import JsonFormatter
except ImportError as e:
    print(f"Import error: {e}")
    print("Run: pip install pyupbit pandas")
    sys.exit(1)


def _setup_logging() -> None:
    """Configure logging based on LOG_FORMAT env var."""
    if os.getenv("LOG_FORMAT", "text").lower() == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logging.root.addHandler(handler)
        logging.root.setLevel(logging.INFO)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )


def main():
    load_env()
    _setup_logging()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(VBOBot().run())


if __name__ == "__main__":
    main()
