#!/usr/bin/env python3
"""VBO Trading Bot Entry Point."""

import asyncio
import logging
import sys

try:
    from bot import load_env, VBOBot
except ImportError as e:
    print(f"Import error: {e}")
    print("Run: pip install pyupbit pandas")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)


def main():
    load_env()
    try:
        asyncio.run(VBOBot().run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
