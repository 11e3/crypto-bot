"""VBO trading bot."""

import asyncio
import contextlib
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from datetime import time as dt_time
from pathlib import Path

from .account import Account
from .config import get_config
from .market import DailySignals, get_price
from .utils import send_telegram, send_telegram_error

log = logging.getLogger("vbo")
DAILY_REPORT_HOUR = 9  # KST 09:00
KST = timezone(timedelta(hours=9))
HEARTBEAT_PATH = Path("logs/.heartbeat")


class VBOBot:
    """Multi-account VBO trading bot."""

    def __init__(self) -> None:
        self.accounts: list[Account] = []
        self.signals = DailySignals()
        self.running = False
        self._load_accounts()
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "running", False))
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "running", False))

    def _load_accounts(self) -> None:
        """Load accounts from env (ACCOUNT_N_NAME/ACCESS_KEY/SECRET_KEY)."""
        for i in range(1, 100):
            name = os.getenv(f"ACCOUNT_{i}_NAME")
            key = os.getenv(f"ACCOUNT_{i}_ACCESS_KEY")
            secret = os.getenv(f"ACCOUNT_{i}_SECRET_KEY")
            if not all([name, key, secret]):
                break
            self.accounts.append(Account(name, key, secret))  # type: ignore[arg-type]

        if not self.accounts:
            log.error("No accounts configured")
            sys.exit(1)
        log.info(f"Loaded {len(self.accounts)} account(s)")

    async def _run_account(self, account: Account) -> None:
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
                        for s in cfg.symbols
                        if account.positions.has(s)
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
                send_telegram_error(f"[{account.name}] Loop error: {e}")
                await asyncio.sleep(5)

    def _daily_report(self) -> None:
        """Send daily status report via Telegram."""
        cfg = get_config()
        sigs = self.signals.all()

        lines = ["📊 <b>Daily Report</b>", ""]

        # Signals
        lines.append("<b>Signals:</b>")
        for symbol in cfg.symbols:
            sig = sigs.get(symbol)
            if sig:
                price = get_price(symbol) or 0
                lines.append(f"  {symbol}: target {sig.target_price:,.0f} / now {price:,.0f}")
        lines.append("")

        # Accounts
        for account in self.accounts:
            krw = account.balance("KRW")
            total = krw

            lines.append(f"<b>[{account.name}]</b>")

            positions = []
            for symbol in cfg.symbols:
                pos = account.positions.get(symbol)
                if pos:
                    price = get_price(symbol) or 0
                    qty = account.balance(symbol)
                    value = qty * price
                    total += value
                    pnl = (price / pos.entry_price - 1) * 100 if pos.entry_price else 0
                    positions.append(f"  {symbol}: {qty:.4f} ({pnl:+.2f}%)")

            if positions:
                lines.append("  Positions:")
                lines.extend(positions)
            else:
                lines.append("  Positions: None")

            lines.append(f"  KRW: {krw:,.0f}")
            lines.append(f"  Total: {total:,.0f}")
            lines.append("")

        send_telegram("\n".join(lines))
        log.info("Daily report sent")

    async def _heartbeat(self) -> None:
        """Write heartbeat timestamp for Docker healthcheck."""
        HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        while self.running:
            with contextlib.suppress(Exception):
                HEARTBEAT_PATH.write_text(str(time.time()))
            await asyncio.sleep(30)

    async def _daily_report_scheduler(self) -> None:
        """Schedule daily report at 9AM KST."""
        reported_today = False

        while self.running:
            now = datetime.now(KST)
            is_report_time = now.time() >= dt_time(DAILY_REPORT_HOUR) and now.time() < dt_time(
                DAILY_REPORT_HOUR, 1
            )

            if is_report_time and not reported_today:
                self._daily_report()
                reported_today = True
            elif now.time() >= dt_time(DAILY_REPORT_HOUR, 1):
                reported_today = False

            await asyncio.sleep(30)

    async def run(self) -> None:
        """Run bot."""
        self.running = True
        cfg = get_config()

        log.info("=" * 50)
        log.info(
            f"VBO Bot V1.1 | {', '.join(cfg.symbols)} | Exit EMA{cfg.ma_short} / Entry BTC{cfg.btc_ma}"
        )
        log.info("=" * 50)

        send_telegram(
            f"🤖 <b>VBO Bot Started</b>\n"
            f"Symbols: {', '.join(cfg.symbols)}\n"
            f"Accounts: {len(self.accounts)}"
        )

        await asyncio.gather(
            self._heartbeat(),
            self._daily_report_scheduler(),
            *[self._run_account(a) for a in self.accounts],
        )

        log.info("Bot stopped")
        send_telegram("🛑 <b>VBO Bot Stopped</b>")
