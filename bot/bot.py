"""VBO trading bot."""

import asyncio
import logging
import os
import signal
import sys

from .config import Config, get_config
from .market import DailySignals, get_price
from .account import Account
from .utils import send_telegram

log = logging.getLogger("vbo")


class VBOBot:
    """Multi-account VBO trading bot."""

    def __init__(self):
        self.accounts: list[Account] = []
        self.signals = DailySignals()
        self.running = False
        self._load_accounts()
        signal.signal(signal.SIGINT, lambda *_: setattr(self, 'running', False))
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, 'running', False))

    def _load_accounts(self):
        """Load accounts from env (ACCOUNT_N_NAME/ACCESS_KEY/SECRET_KEY)."""
        for i in range(1, 100):
            name = os.getenv(f"ACCOUNT_{i}_NAME")
            key = os.getenv(f"ACCOUNT_{i}_ACCESS_KEY")
            secret = os.getenv(f"ACCOUNT_{i}_SECRET_KEY")
            if not all([name, key, secret]):
                break
            self.accounts.append(Account(name, key, secret))

        if not self.accounts:
            log.error("No accounts configured")
            sys.exit(1)
        log.info(f"Loaded {len(self.accounts)} account(s)")

    async def _run_account(self, account: Account):
        """Trading loop for single account."""
        cfg = get_config()

        while self.running:
            try:
                sigs = self.signals.all()
                if not sigs:
                    await asyncio.sleep(10)
                    continue

                # Sell first
                for symbol in cfg.symbols:
                    sig = sigs.get(symbol)
                    if sig and account.positions.has(symbol) and sig.should_sell:
                        account.sell(symbol)

                # Collect buy candidates
                buys = []
                for symbol in cfg.symbols:
                    sig = sigs.get(symbol)
                    if not sig or not sig.can_buy or account.positions.has(symbol):
                        continue
                    price = get_price(symbol)
                    if price and price >= sig.target_price:
                        buys.append((symbol, sig.target_price))

                # Execute buys with portfolio allocation
                if buys:
                    cash = account.balance("KRW")
                    equity = cash + sum(
                        account.balance(s) * (get_price(s) or 0)
                        for s in cfg.symbols if account.positions.has(s)
                    )
                    alloc = equity / len(cfg.symbols)

                    for symbol, target in buys:
                        amount = min(alloc, cash * 0.99)
                        if amount <= 0:
                            continue
                        if account.buy(symbol, target, amount):
                            cash = account.balance("KRW")
                        await asyncio.sleep(cfg.ORDER_DELAY_SEC)

                await asyncio.sleep(cfg.CHECK_INTERVAL_SEC)

            except Exception as e:
                log.error(f"[{account.name}] Error: {e}")
                await asyncio.sleep(5)

    async def run(self):
        """Run bot."""
        self.running = True
        cfg = get_config()

        log.info("=" * 50)
        log.info(f"VBO Bot | {', '.join(cfg.symbols)} | MA{cfg.ma_short}/BTC{cfg.btc_ma}")
        log.info("=" * 50)

        send_telegram(
            f"🤖 <b>VBO Bot Started</b>\n"
            f"Symbols: {', '.join(cfg.symbols)}\n"
            f"Accounts: {len(self.accounts)}"
        )

        await asyncio.gather(*[self._run_account(a) for a in self.accounts])

        log.info("Bot stopped")
        send_telegram("🛑 <b>VBO Bot Stopped</b>")
