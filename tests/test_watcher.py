import os
import sys
from unittest.mock import MagicMock


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from dart.client import DartApiRateLimited
from dart.parser import Disclosure
from monitor.watcher import Watcher


def _make_config():
    return Config(
        dart_api_key="test_key",
        telegram_bot_token="123:ABC",
        telegram_chat_id="999",
        poll_interval=1,
    )


def _make_disclosure(
    rcept_no="20240101000001", report_nm="분기보고서", corp_code="00126380"
):
    return Disclosure(
        corp_code=corp_code,
        corp_name="삼성전자",
        report_nm=report_nm,
        rcept_no=rcept_no,
        flr_nm="삼성전자",
        rcept_dt="20240101",
        rm="",
    )


def _fresh_watcher():
    """Construct a Watcher with all external deps mocked and baseline off."""
    watcher = Watcher(_make_config())
    watcher.company_store = MagicMock()
    watcher.dart_client = MagicMock()
    watcher.telegram_bot = MagicMock()
    watcher.sent_store = MagicMock()
    watcher.sent_store.is_sent.return_value = False
    watcher.sent_store.count.return_value = 5
    watcher._baseline_mode = False
    return watcher


class TestWatcher:
    def test_baseline_marks_without_notifying(self):
        watcher = _fresh_watcher()
        watcher._baseline_mode = True
        watcher.company_store.list_all.return_value = {"00126380": "삼성전자"}
        disc = _make_disclosure()
        watcher.dart_client.get_all_recent_disclosures.return_value = [disc]

        watcher._poll_once()

        watcher.sent_store.mark_sent.assert_called_once_with("20240101000001")
        watcher.telegram_bot.broadcast_disclosure.assert_not_called()
        assert watcher._baseline_mode is False

    def test_new_disclosure_sends_notification(self):
        watcher = _fresh_watcher()
        watcher.company_store.list_all.return_value = {"00126380": "삼성전자"}
        disc = _make_disclosure()
        watcher.dart_client.get_all_recent_disclosures.return_value = [disc]
        watcher.telegram_bot.broadcast_disclosure.return_value = 1

        watcher._poll_once()

        watcher.telegram_bot.broadcast_disclosure.assert_called_once_with(disc)
        watcher.sent_store.mark_sent.assert_called_once_with("20240101000001")

    def test_unwatched_company_ignored(self):
        watcher = _fresh_watcher()
        watcher.company_store.list_all.return_value = {"00126380": "삼성전자"}
        other = _make_disclosure(corp_code="99999999", rcept_no="other")
        watcher.dart_client.get_all_recent_disclosures.return_value = [other]

        watcher._poll_once()

        watcher.telegram_bot.broadcast_disclosure.assert_not_called()
        watcher.sent_store.mark_sent.assert_not_called()

    def test_already_sent_skipped(self):
        watcher = _fresh_watcher()
        watcher.company_store.list_all.return_value = {"00126380": "삼성전자"}
        disc = _make_disclosure()
        watcher.dart_client.get_all_recent_disclosures.return_value = [disc]
        watcher.sent_store.is_sent.return_value = True

        watcher._poll_once()

        watcher.telegram_bot.broadcast_disclosure.assert_not_called()
        watcher.sent_store.mark_sent.assert_not_called()

    def test_rate_limit_triggers_backoff(self):
        watcher = _fresh_watcher()
        watcher.company_store.list_all.return_value = {"00126380": "삼성전자"}
        watcher.dart_client.get_all_recent_disclosures.side_effect = (
            DartApiRateLimited("quota exceeded")
        )

        assert watcher._backoff_until == 0.0
        watcher._poll_once()

        assert watcher._backoff_until > 0
        watcher.telegram_bot.broadcast_disclosure.assert_not_called()
        assert watcher._consecutive_failures == 0

    def test_poll_while_in_backoff_is_noop(self):
        import time as _time

        watcher = _fresh_watcher()
        watcher.company_store.list_all.return_value = {"00126380": "삼성전자"}
        watcher._backoff_until = _time.time() + 1000

        watcher._poll_once()

        watcher.dart_client.get_all_recent_disclosures.assert_not_called()

    def test_exception_increments_failure_counter(self):
        watcher = _fresh_watcher()
        watcher.company_store.list_all.return_value = {"00126380": "삼성전자"}
        watcher.dart_client.get_all_recent_disclosures.side_effect = Exception(
            "network blip"
        )

        watcher._poll_once()

        assert watcher._consecutive_failures == 1
        watcher.telegram_bot.send_text.assert_not_called()

    def test_consecutive_failures_trigger_alert(self):
        watcher = _fresh_watcher()
        watcher.company_store.list_all.return_value = {"00126380": "삼성전자"}
        watcher.dart_client.get_all_recent_disclosures.side_effect = Exception(
            "boom"
        )

        for _ in range(Watcher.FAILURE_ALERT_THRESHOLD):
            watcher._poll_once()

        assert watcher._alert_sent is True
        watcher.telegram_bot.send_text.assert_called_once()

    def test_recovery_sends_recovery_alert(self):
        watcher = _fresh_watcher()
        watcher.company_store.list_all.return_value = {"00126380": "삼성전자"}
        watcher._consecutive_failures = Watcher.FAILURE_ALERT_THRESHOLD
        watcher._alert_sent = True
        watcher.dart_client.get_all_recent_disclosures.return_value = []

        watcher._poll_once()

        assert watcher._consecutive_failures == 0
        assert watcher._alert_sent is False
        watcher.telegram_bot.send_text.assert_called_once()

    def test_no_companies_no_api_call(self):
        watcher = _fresh_watcher()
        watcher.company_store.list_all.return_value = {}

        watcher._poll_once()

        watcher.dart_client.get_all_recent_disclosures.assert_not_called()
