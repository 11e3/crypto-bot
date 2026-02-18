"""Tests for runtime helpers in bot.bot."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.bot import KST, VBOBot
from bot.market import Signal


class TestVBOBotRuntime:
    """Tests for runtime paths in VBOBot."""

    def _make_bot(self) -> VBOBot:
        bot = VBOBot.__new__(VBOBot)
        bot.accounts = []
        bot.signals = MagicMock()
        bot.running = True
        return bot

    @pytest.mark.asyncio
    async def test_run_account_sleeps_when_no_signals(self) -> None:
        bot = self._make_bot()
        account = MagicMock()
        account.name = "acc1"
        bot.signals.all.return_value = {}

        cfg = MagicMock(symbols=("BTC",), ORDER_DELAY_SEC=0, CHECK_INTERVAL_SEC=0)

        async def stop_sleep(_: float) -> None:
            bot.running = False

        with (
            patch("bot.bot.get_config", return_value=cfg),
            patch("bot.bot.asyncio.sleep", new=AsyncMock(side_effect=stop_sleep)),
        ):
            await bot._run_account(account)

    @pytest.mark.asyncio
    async def test_run_account_executes_sell_and_buy_paths(self) -> None:
        bot = self._make_bot()
        cfg = MagicMock(symbols=("BTC", "ETH"), ORDER_DELAY_SEC=0, CHECK_INTERVAL_SEC=1)
        bot.signals.all.return_value = {
            "BTC": Signal("BTC", 100.0, can_buy=False, should_sell=True),
            "ETH": Signal("ETH", 100.0, can_buy=True, should_sell=False),
        }

        account = MagicMock()
        account.name = "acc1"
        account.positions.has.side_effect = lambda s: s == "BTC"
        account.balance.side_effect = lambda c: 100000.0 if c == "KRW" else 0.0
        account.buy.return_value = True
        account.sell.return_value = True

        async def fake_sleep(seconds: float) -> None:
            if seconds == 1:
                bot.running = False

        async def direct_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch("bot.bot.get_config", return_value=cfg),
            patch("bot.bot.get_price", return_value=120.0),
            patch("bot.bot.asyncio.sleep", new=AsyncMock(side_effect=fake_sleep)),
            patch("bot.bot.asyncio.to_thread", new=AsyncMock(side_effect=direct_to_thread)),
        ):
            await bot._run_account(account)

        account.sell.assert_called_once_with("BTC")
        account.buy.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_account_skips_buy_when_price_below_target(self) -> None:
        bot = self._make_bot()
        cfg = MagicMock(symbols=("BTC",), ORDER_DELAY_SEC=0, CHECK_INTERVAL_SEC=1)
        bot.signals.all.return_value = {
            "BTC": Signal("BTC", 200.0, can_buy=True, should_sell=False),
        }

        account = MagicMock()
        account.name = "acc1"
        account.positions.has.return_value = False

        async def fake_sleep(seconds: float) -> None:
            if seconds == 1:
                bot.running = False

        async def direct_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch("bot.bot.get_config", return_value=cfg),
            patch("bot.bot.get_price", return_value=100.0),
            patch("bot.bot.asyncio.sleep", new=AsyncMock(side_effect=fake_sleep)),
            patch("bot.bot.asyncio.to_thread", new=AsyncMock(side_effect=direct_to_thread)),
        ):
            await bot._run_account(account)

        account.buy.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_account_skips_buy_when_amount_non_positive(self) -> None:
        bot = self._make_bot()
        cfg = MagicMock(symbols=("BTC",), ORDER_DELAY_SEC=0, CHECK_INTERVAL_SEC=1)
        bot.signals.all.return_value = {
            "BTC": Signal("BTC", 100.0, can_buy=True, should_sell=False),
        }

        account = MagicMock()
        account.name = "acc1"
        account.positions.has.return_value = False
        account.balance.return_value = 0.0

        async def fake_sleep(seconds: float) -> None:
            if seconds == 1:
                bot.running = False

        async def direct_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch("bot.bot.get_config", return_value=cfg),
            patch("bot.bot.get_price", return_value=120.0),
            patch("bot.bot.asyncio.sleep", new=AsyncMock(side_effect=fake_sleep)),
            patch("bot.bot.asyncio.to_thread", new=AsyncMock(side_effect=direct_to_thread)),
        ):
            await bot._run_account(account)

        account.buy.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_account_does_not_refresh_cash_when_buy_fails(self) -> None:
        bot = self._make_bot()
        cfg = MagicMock(symbols=("BTC",), ORDER_DELAY_SEC=0, CHECK_INTERVAL_SEC=1)
        bot.signals.all.return_value = {
            "BTC": Signal("BTC", 100.0, can_buy=True, should_sell=False),
        }

        account = MagicMock()
        account.name = "acc1"
        account.positions.has.return_value = False
        account.balance.side_effect = [100000.0]
        account.buy.return_value = False

        async def fake_sleep(seconds: float) -> None:
            if seconds == 1:
                bot.running = False

        async def direct_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch("bot.bot.get_config", return_value=cfg),
            patch("bot.bot.get_price", return_value=120.0),
            patch("bot.bot.asyncio.sleep", new=AsyncMock(side_effect=fake_sleep)),
            patch("bot.bot.asyncio.to_thread", new=AsyncMock(side_effect=direct_to_thread)),
        ):
            await bot._run_account(account)

        assert account.balance.call_count == 1

    @pytest.mark.asyncio
    async def test_run_account_error_path_reports(self) -> None:
        bot = self._make_bot()
        account = MagicMock()
        account.name = "acc1"
        bot.signals.all.side_effect = RuntimeError("loop boom")
        cfg = MagicMock(symbols=("BTC",), ORDER_DELAY_SEC=0, CHECK_INTERVAL_SEC=1)

        async def fake_sleep(seconds: float) -> None:
            if seconds == 5:
                bot.running = False

        with (
            patch("bot.bot.get_config", return_value=cfg),
            patch("bot.bot.asyncio.sleep", new=AsyncMock(side_effect=fake_sleep)),
            patch("bot.bot.send_telegram_error") as mock_error,
        ):
            await bot._run_account(account)

        mock_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_account_reports_pending_reconcile_error(self) -> None:
        bot = self._make_bot()
        account = MagicMock()
        account.name = "acc1"
        account.reconcile_pending_buys.side_effect = RuntimeError("pending boom")
        bot.signals.all.return_value = {}
        cfg = MagicMock(symbols=("BTC",), ORDER_DELAY_SEC=0, CHECK_INTERVAL_SEC=1)

        async def stop_sleep(_: float) -> None:
            bot.running = False

        async def direct_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch("bot.bot.get_config", return_value=cfg),
            patch("bot.bot.asyncio.sleep", new=AsyncMock(side_effect=stop_sleep)),
            patch("bot.bot.asyncio.to_thread", new=AsyncMock(side_effect=direct_to_thread)),
            patch("bot.bot.send_telegram_error") as mock_error,
        ):
            await bot._run_account(account)

        assert mock_error.call_count >= 1

    def test_daily_report_sends_message(self) -> None:
        bot = self._make_bot()
        account = MagicMock()
        account.name = "acc1"
        account.balance.side_effect = lambda symbol: 100000.0 if symbol == "KRW" else 0.1
        account.positions.get.return_value = MagicMock(entry_price=50000.0)
        bot.accounts = [account]
        bot.signals.all.return_value = {
            "BTC": Signal(symbol="BTC", target_price=52000.0, can_buy=True, should_sell=False)
        }

        cfg = MagicMock(symbols=("BTC",))

        with (
            patch("bot.bot.get_config", return_value=cfg),
            patch("bot.bot.get_price", return_value=55000.0),
            patch("bot.bot.send_telegram") as mock_send,
        ):
            bot._daily_report()

        assert mock_send.called
        msg = mock_send.call_args[0][0]
        assert "Daily Report" in msg
        assert "BTC" in msg

    def test_daily_report_handles_empty_positions(self) -> None:
        bot = self._make_bot()
        account = MagicMock()
        account.name = "acc1"
        account.balance.return_value = 100000.0
        account.positions.get.return_value = None
        bot.accounts = [account]
        bot.signals.all.return_value = {}
        cfg = MagicMock(symbols=("BTC", "ETH"))

        with (
            patch("bot.bot.get_config", return_value=cfg),
            patch("bot.bot.send_telegram") as mock_send,
        ):
            bot._daily_report()

        msg = mock_send.call_args[0][0]
        assert "Positions: None" in msg

    @pytest.mark.asyncio
    async def test_heartbeat_writes_once(self, temp_dir) -> None:
        bot = self._make_bot()
        heartbeat_path = temp_dir / "logs" / ".heartbeat"

        async def stop_sleep(_: float) -> None:
            bot.running = False

        with (
            patch("bot.bot.HEARTBEAT_PATH", heartbeat_path),
            patch("bot.bot.asyncio.sleep", new=AsyncMock(side_effect=stop_sleep)),
        ):
            await bot._heartbeat()

        assert heartbeat_path.exists()

    @pytest.mark.asyncio
    async def test_daily_report_scheduler_calls_report(self) -> None:
        bot = self._make_bot()
        bot._daily_report = MagicMock()
        report_time = datetime(2026, 1, 1, 9, 0, 30, tzinfo=KST)

        async def stop_sleep(_: float) -> None:
            bot.running = False

        with (
            patch("bot.bot.datetime") as mock_dt,
            patch("bot.bot.asyncio.sleep", new=AsyncMock(side_effect=stop_sleep)),
            patch("bot.bot.asyncio.to_thread", new=AsyncMock(return_value=None)) as mock_to_thread,
        ):
            mock_dt.now.return_value = report_time
            await bot._daily_report_scheduler()

        assert mock_to_thread.called

    @pytest.mark.asyncio
    async def test_daily_report_scheduler_resets_after_window(self) -> None:
        bot = self._make_bot()
        bot._daily_report = MagicMock()
        times = iter(
            [
                datetime(2026, 1, 1, 9, 0, 30, tzinfo=KST),
                datetime(2026, 1, 1, 9, 1, 10, tzinfo=KST),
            ]
        )

        async def fake_sleep(_: float) -> None:
            if not bot._daily_report.called:
                return
            bot.running = False

        with (
            patch("bot.bot.datetime") as mock_dt,
            patch("bot.bot.asyncio.sleep", new=AsyncMock(side_effect=fake_sleep)),
            patch("bot.bot.asyncio.to_thread", new=AsyncMock(side_effect=lambda f, *a: f(*a))),
        ):
            mock_dt.now.side_effect = lambda *_: next(times)
            await bot._daily_report_scheduler()

        bot._daily_report.assert_called_once()

    @pytest.mark.asyncio
    async def test_daily_report_scheduler_executes_reset_branch(self) -> None:
        bot = self._make_bot()
        bot._daily_report = MagicMock()
        times = iter(
            [
                datetime(2026, 1, 1, 9, 0, 10, tzinfo=KST),
                datetime(2026, 1, 1, 9, 1, 10, tzinfo=KST),
                datetime(2026, 1, 1, 9, 1, 20, tzinfo=KST),
            ]
        )
        sleep_calls = {"n": 0}

        async def fake_sleep(_: float) -> None:
            sleep_calls["n"] += 1
            if sleep_calls["n"] >= 2:
                bot.running = False

        async def direct_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch("bot.bot.datetime") as mock_dt,
            patch("bot.bot.asyncio.sleep", new=AsyncMock(side_effect=fake_sleep)),
            patch("bot.bot.asyncio.to_thread", new=AsyncMock(side_effect=direct_to_thread)),
        ):
            mock_dt.now.side_effect = lambda *_: next(times)
            await bot._daily_report_scheduler()

        bot._daily_report.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_sends_start_and_stop_notifications(self) -> None:
        bot = self._make_bot()
        bot.accounts = [MagicMock(name="acc1")]
        bot._heartbeat = AsyncMock(return_value=None)
        bot._daily_report_scheduler = AsyncMock(return_value=None)
        bot._run_account = AsyncMock(return_value=None)
        cfg = MagicMock(symbols=("BTC",), ma_short=5, btc_ma=20)

        with (
            patch("bot.bot.get_config", return_value=cfg),
            patch("bot.bot.send_telegram") as mock_send,
        ):
            await bot.run()

        assert mock_send.call_count == 2

    def test_init_sets_signal_handlers(self) -> None:
        with (
            patch.object(VBOBot, "_load_accounts"),
            patch("bot.bot.DailySignals"),
            patch("bot.bot.signal.signal") as mock_signal,
        ):
            bot = VBOBot()

        assert bot.running is False
        assert mock_signal.call_count == 2
