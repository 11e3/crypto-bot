"""Tests for bot.account module."""

import time as py_time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bot.account import Account
from bot.tracker import Position


class TestAccount:
    """Tests for Account behavior."""

    def _make_account(self) -> Account:
        account = Account.__new__(Account)
        account.name = "test"
        account._api = MagicMock()
        account._api.get_balance.return_value = 0.0
        account.positions = MagicMock()
        account._logger = MagicMock()
        account._zero_balance_counts = {}
        account._buy_block_until = {}
        account._pending_buys = {}
        account._state_path = Path("logs/test/runtime_state.json")
        account._save_runtime_state = MagicMock()
        return account

    def test_balance_returns_float(self) -> None:
        account = self._make_account()
        account._api.get_balance.return_value = "1234.5"

        assert account.balance("KRW") == 1234.5

    def test_balance_handles_error(self) -> None:
        account = self._make_account()
        account._api.get_balance.side_effect = RuntimeError("boom")

        assert account.balance("KRW") == 0.0

    def test_buy_rejects_under_min_order(self) -> None:
        account = self._make_account()
        with patch("bot.account.get_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(MIN_ORDER_KRW=5000, LATE_ENTRY_PCT=1.0)
            assert account.buy("BTC", target=50000.0, amount=1000.0) is False

    def test_buy_success(self) -> None:
        account = self._make_account()
        account._api.buy_market_order.return_value = {"uuid": "buy-uuid"}
        account._get_fill = MagicMock(return_value=(50000.0, 0.1))

        with (
            patch("bot.account.get_config") as mock_cfg,
            patch("bot.account.get_price", return_value=50000.0),
            patch("bot.account.time.sleep"),
            patch("bot.account.send_telegram"),
        ):
            mock_cfg.return_value = MagicMock(MIN_ORDER_KRW=5000, LATE_ENTRY_PCT=1.0)
            result = account.buy("BTC", target=50000.0, amount=5000.0)

        assert result is True
        account.positions.add.assert_called_once()
        call_args = account.positions.add.call_args[0]
        assert call_args[0] == "BTC"
        assert call_args[1] == pytest.approx(0.1)
        assert call_args[2] == pytest.approx(50000.0)
        account._logger.log.assert_called_once()

    def test_buy_handles_exception_and_reports(self) -> None:
        account = self._make_account()
        account._api.buy_market_order.side_effect = RuntimeError("order fail")

        with (
            patch("bot.account.get_config") as mock_cfg,
            patch("bot.account.get_price", return_value=50000.0),
            patch("bot.account.send_telegram_error") as mock_error,
        ):
            mock_cfg.return_value = MagicMock(MIN_ORDER_KRW=5000, LATE_ENTRY_PCT=1.0)
            result = account.buy("BTC", target=50000.0, amount=5000.0)

        assert result is False
        mock_error.assert_called_once()

    def test_sell_returns_false_when_no_position(self) -> None:
        account = self._make_account()
        account.positions.get.return_value = None
        assert account.sell("BTC") is False

    def test_sell_keeps_position_when_balance_zero(self) -> None:
        account = self._make_account()
        account.positions.get.return_value = Position("BTC", 0.1, 50000.0, "t")
        account._api.get_balance.return_value = 0.0

        with patch("bot.account.send_telegram_error") as mock_error:
            assert account.sell("BTC") is False

        account.positions.remove.assert_not_called()
        mock_error.assert_called_once()
        assert account._zero_balance_counts.get("BTC") == 1

    def test_sell_removes_position_after_consecutive_zero_balances(self) -> None:
        account = self._make_account()
        account.positions.get.return_value = Position("BTC", 0.1, 50000.0, "t")
        account._api.get_balance.return_value = 0.0

        with patch("bot.account.send_telegram_error"):
            assert account.sell("BTC") is False
            assert account.sell("BTC") is False
            assert account.sell("BTC") is False

        account.positions.remove.assert_called_once_with("BTC")
        assert "BTC" not in account._zero_balance_counts

    def test_sell_does_not_remove_position_when_balance_call_fails(self) -> None:
        account = self._make_account()
        account.positions.get.return_value = Position("BTC", 0.1, 50000.0, "t")
        account._api.get_balance.side_effect = RuntimeError("balance fail")

        with patch("bot.account.send_telegram_error") as mock_error:
            assert account.sell("BTC") is False

        account.positions.remove.assert_not_called()
        mock_error.assert_called_once()

    def test_sell_uses_tracked_position_qty_not_full_balance(self) -> None:
        """Should sell only bot-tracked quantity."""
        account = self._make_account()
        account.positions.get.return_value = Position("BTC", 0.1, 50000.0, "t")
        account._api.get_balance.return_value = 0.5  # wallet has extra manual position
        account._api.sell_market_order.return_value = {"uuid": "order-uuid"}
        account._get_fill = MagicMock(return_value=(55000.0, 0.1))

        with (
            patch("bot.account.get_price", return_value=55000.0),
            patch("bot.account.time.sleep"),
            patch("bot.account.send_telegram"),
        ):
            result = account.sell("BTC")

        assert result is True
        account._api.sell_market_order.assert_called_once_with("KRW-BTC", 0.1)
        account.positions.remove.assert_called_once_with("BTC")

    def test_sell_partial_fill_updates_remaining_position(self) -> None:
        account = self._make_account()
        account.positions.get.return_value = Position("BTC", 0.5, 50000.0, "t")
        account._api.get_balance.return_value = 0.1
        account._api.sell_market_order.return_value = {"uuid": "order-uuid"}
        account._get_fill = MagicMock(return_value=(55000.0, 0.1))

        with (
            patch("bot.account.get_price", return_value=55000.0),
            patch("bot.account.time.sleep"),
            patch("bot.account.send_telegram"),
        ):
            result = account.sell("BTC")

        assert result is True
        account.positions.remove.assert_not_called()
        account.positions.update_quantity.assert_called_once_with("BTC", pytest.approx(0.4))

    def test_sell_handles_exception_and_reports(self) -> None:
        account = self._make_account()
        account.positions.get.return_value = Position("BTC", 0.1, 50000.0, "t")
        account._api.get_balance.return_value = 0.1
        account._api.sell_market_order.side_effect = RuntimeError("sell fail")

        with (
            patch("bot.account.get_price", return_value=55000.0),
            patch("bot.account.send_telegram_error") as mock_error,
        ):
            result = account.sell("BTC")

        assert result is False
        mock_error.assert_called_once()

    def test_init_wires_dependencies(self) -> None:
        with (
            patch("bot.account.pyupbit.Upbit") as mock_upbit,
            patch("bot.account.PositionTracker") as mock_tracker,
            patch("bot.account.TradeLogger") as mock_logger,
        ):
            account = Account("acc", "key", "secret")

        mock_upbit.assert_called_once_with("key", "secret")
        mock_tracker.assert_called_once_with("acc")
        mock_logger.assert_called_once_with("acc")
        assert account.name == "acc"

    def test_get_fill_uses_trade_list_when_done(self) -> None:
        account = self._make_account()
        account._api.get_order.return_value = {
            "state": "done",
            "trades": [{"funds": "10000", "volume": "0.2"}],
        }

        price, qty = account._get_fill("uuid", 50000.0)

        assert qty == 0.2
        assert price == 50000.0

    def test_get_fill_uses_order_fields_without_trades(self) -> None:
        account = self._make_account()
        account._api.get_order.return_value = {"price": "51000", "executed_volume": "0.1"}

        price, qty = account._get_fill("uuid", 50000.0)

        assert price == 51000.0
        assert qty == 0.1

    def test_get_fill_returns_fallback_on_error(self) -> None:
        account = self._make_account()
        account._api.get_order.side_effect = RuntimeError("boom")

        price, qty = account._get_fill("uuid", 50000.0)

        assert price == 50000.0
        assert qty == 0.0

    def test_buy_returns_false_when_no_current_price(self) -> None:
        account = self._make_account()
        with (
            patch("bot.account.get_config") as mock_cfg,
            patch("bot.account.get_price", return_value=None),
        ):
            mock_cfg.return_value = MagicMock(MIN_ORDER_KRW=5000, LATE_ENTRY_PCT=1.0)
            assert account.buy("BTC", target=50000.0, amount=5000.0) is False

    def test_buy_returns_false_on_late_entry(self) -> None:
        account = self._make_account()
        with (
            patch("bot.account.get_config") as mock_cfg,
            patch("bot.account.get_price", return_value=52000.0),
        ):
            mock_cfg.return_value = MagicMock(MIN_ORDER_KRW=5000, LATE_ENTRY_PCT=1.0)
            assert account.buy("BTC", target=50000.0, amount=5000.0) is False

    def test_buy_returns_false_when_order_fails(self) -> None:
        account = self._make_account()
        account._api.buy_market_order.return_value = None
        with (
            patch("bot.account.get_config") as mock_cfg,
            patch("bot.account.get_price", return_value=50000.0),
        ):
            mock_cfg.return_value = MagicMock(MIN_ORDER_KRW=5000, LATE_ENTRY_PCT=1.0)
            assert account.buy("BTC", target=50000.0, amount=5000.0) is False

    def test_buy_returns_false_when_fill_unavailable(self) -> None:
        account = self._make_account()
        account._api.buy_market_order.return_value = {"uuid": "buy-uuid"}
        account._get_fill = MagicMock(return_value=(50000.0, 0.0))
        account._get_balance_value = MagicMock(side_effect=[0.0, 0.0])
        with (
            patch("bot.account.get_config") as mock_cfg,
            patch("bot.account.get_price", return_value=50000.0),
            patch("bot.account.time.sleep"),
            patch("bot.account.send_telegram_error") as mock_error,
        ):
            mock_cfg.return_value = MagicMock(MIN_ORDER_KRW=5000, LATE_ENTRY_PCT=1.0)
            assert account.buy("BTC", target=50000.0, amount=5000.0) is False
        mock_error.assert_called_once()
        assert account._buy_block_until.get("BTC", 0.0) > 0.0
        assert account._pending_buys["BTC"]["uuid"] == "buy-uuid"

    def test_buy_blocked_during_cooldown(self) -> None:
        account = self._make_account()
        account._buy_block_until["BTC"] = 2000.0

        with (
            patch("bot.account.time.time", return_value=1000.0),
            patch("bot.account.get_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(MIN_ORDER_KRW=5000, LATE_ENTRY_PCT=1.0)
            assert account.buy("BTC", target=50000.0, amount=5000.0) is False

        account._api.buy_market_order.assert_not_called()

    def test_buy_blocked_when_pending_exists(self) -> None:
        account = self._make_account()
        account._pending_buys["BTC"] = {
            "uuid": "u",
            "amount": 5000.0,
            "fallback_price": 50000.0,
            "pre_qty": 0.0,
            "created_at": 1000.0,
        }
        with patch("bot.account.get_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(MIN_ORDER_KRW=5000, LATE_ENTRY_PCT=1.0)
            assert account.buy("BTC", target=50000.0, amount=5000.0) is False
        account._api.buy_market_order.assert_not_called()

    def test_reconcile_pending_buy_creates_position(self) -> None:
        account = self._make_account()
        account._pending_buys["BTC"] = {
            "uuid": "u-1",
            "amount": 5000.0,
            "fallback_price": 50000.0,
            "pre_qty": 0.0,
            "created_at": 1000.0,
        }
        account._get_fill = MagicMock(return_value=(50000.0, 0.1))

        with patch("bot.account.send_telegram"):
            account.reconcile_pending_buys()

        account.positions.add.assert_called_once_with("BTC", 0.1, 50000.0)
        assert "BTC" not in account._pending_buys
        trade = account._logger.log.call_args[0][0]
        assert trade.amount == pytest.approx(5000.0)

    def test_reconcile_pending_buy_logs_filled_amount(self) -> None:
        account = self._make_account()
        account._pending_buys["BTC"] = {
            "uuid": "u-2",
            "amount": 5000.0,
            "fallback_price": 50000.0,
            "pre_qty": 0.0,
            "created_at": 1000.0,
        }
        account._get_fill = MagicMock(return_value=(55000.0, 0.05))

        with patch("bot.account.send_telegram"):
            account.reconcile_pending_buys()

        trade = account._logger.log.call_args[0][0]
        assert trade.amount == pytest.approx(2750.0)

    def test_reconcile_pending_buy_expires_and_clears_block(self) -> None:
        account = self._make_account()
        account._pending_buys["BTC"] = {
            "uuid": "u-3",
            "amount": 5000.0,
            "fallback_price": 50000.0,
            "pre_qty": 0.0,
            "created_at": 0.0,
        }
        account._buy_block_until["BTC"] = 9999.0
        account._get_fill = MagicMock(return_value=(50000.0, 0.0))
        account._is_order_closed_without_fill = MagicMock(return_value=False)

        with patch("bot.account.send_telegram_error") as mock_error:
            account.reconcile_pending_buys()

        assert "BTC" not in account._pending_buys
        assert "BTC" not in account._buy_block_until
        mock_error.assert_called_once()

    def test_reconcile_pending_buy_clears_when_order_closed_without_fill(self) -> None:
        account = self._make_account()
        account._pending_buys["BTC"] = {
            "uuid": "u-4",
            "amount": 5000.0,
            "fallback_price": 50000.0,
            "pre_qty": 0.0,
            "created_at": py_time.time(),
        }
        account._buy_block_until["BTC"] = 9999.0
        account._get_fill = MagicMock(return_value=(50000.0, 0.0))
        account._is_order_closed_without_fill = MagicMock(return_value=True)

        with patch("bot.account.send_telegram_error") as mock_error:
            account.reconcile_pending_buys()

        assert "BTC" not in account._pending_buys
        assert "BTC" not in account._buy_block_until
        mock_error.assert_called_once()

    def test_buy_fallback_uses_balance_delta_not_total_balance(self) -> None:
        account = self._make_account()
        account._api.buy_market_order.return_value = {"uuid": "buy-uuid"}
        account._get_fill = MagicMock(return_value=(50000.0, 0.0))
        account._get_balance_value = MagicMock(side_effect=[0.4, 0.5])  # existing manual 0.4 + bought 0.1

        with (
            patch("bot.account.get_config") as mock_cfg,
            patch("bot.account.get_price", return_value=50000.0),
            patch("bot.account.time.sleep"),
            patch("bot.account.send_telegram"),
        ):
            mock_cfg.return_value = MagicMock(MIN_ORDER_KRW=5000, LATE_ENTRY_PCT=1.0)
            result = account.buy("BTC", target=50000.0, amount=5000.0)

        assert result is True
        account.positions.add.assert_called_once()
        call_args = account.positions.add.call_args[0]
        assert call_args[0] == "BTC"
        assert call_args[1] == pytest.approx(0.1)
        assert call_args[2] == pytest.approx(50000.0)

    def test_sell_returns_false_when_tracked_qty_zero(self) -> None:
        account = self._make_account()
        account.positions.get.return_value = Position("BTC", 0.0, 50000.0, "t")
        account._api.get_balance.return_value = 0.5
        with patch("bot.account.get_price", return_value=55000.0):
            assert account.sell("BTC") is False

    def test_sell_returns_false_when_order_fails(self) -> None:
        account = self._make_account()
        account.positions.get.return_value = Position("BTC", 0.1, 50000.0, "t")
        account._api.get_balance.return_value = 0.1
        account._api.sell_market_order.return_value = None
        with patch("bot.account.get_price", return_value=55000.0):
            assert account.sell("BTC") is False
