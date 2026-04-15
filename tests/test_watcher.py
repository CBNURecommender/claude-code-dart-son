import os
import sys
from unittest.mock import MagicMock


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from dart.parser import Disclosure
from monitor.watcher import Watcher


def _make_config():
    return Config(
        dart_api_key="test_key",
        telegram_bot_token="123:ABC",
        telegram_chat_id="999",
        poll_interval=1,
    )


def _make_disclosure(rcept_no="20240101000001", report_nm="분기보고서"):
    return Disclosure(
        corp_code="00126380",
        corp_name="삼성전자",
        report_nm=report_nm,
        rcept_no=rcept_no,
        flr_nm="삼성전자",
        rcept_dt="20240101",
        rm="",
    )


class TestWatcher:
    def test_first_run_no_notification(self, tmp_path):
        """First run should mark disclosures as sent without sending notifications."""
        config = _make_config()
        watcher = Watcher(config)
        watcher.company_store = MagicMock()
        watcher.company_store.list_all.return_value = {"00126380": "삼성전자"}

        disc = _make_disclosure()
        watcher.dart_client = MagicMock()
        watcher.dart_client.get_latest_disclosures.return_value = [disc]

        watcher.telegram_bot = MagicMock()
        watcher.sent_store = MagicMock()
        watcher.sent_store.is_sent.return_value = False

        watcher._first_run = True
        watcher._poll_once()

        # Should mark as sent but NOT send telegram
        watcher.sent_store.mark_sent.assert_called_once_with("20240101000001")
        watcher.telegram_bot.send_disclosure.assert_not_called()

    def test_new_disclosure_sends_notification(self, tmp_path):
        """New disclosure on subsequent run should trigger notification."""
        config = _make_config()
        watcher = Watcher(config)
        watcher.company_store = MagicMock()
        watcher.company_store.list_all.return_value = {"00126380": "삼성전자"}

        disc = _make_disclosure()
        watcher.dart_client = MagicMock()
        watcher.dart_client.get_latest_disclosures.return_value = [disc]

        watcher.telegram_bot = MagicMock()
        watcher.telegram_bot.send_disclosure.return_value = True
        watcher.sent_store = MagicMock()
        watcher.sent_store.is_sent.return_value = False

        watcher._first_run = False
        watcher._poll_once()

        watcher.telegram_bot.send_disclosure.assert_called_once_with(disc)
        watcher.sent_store.mark_sent.assert_called_once_with("20240101000001")

    def test_already_sent_skipped(self):
        """Already sent disclosures should be skipped."""
        config = _make_config()
        watcher = Watcher(config)
        watcher.company_store = MagicMock()
        watcher.company_store.list_all.return_value = {"00126380": "삼성전자"}

        disc = _make_disclosure()
        watcher.dart_client = MagicMock()
        watcher.dart_client.get_latest_disclosures.return_value = [disc]

        watcher.telegram_bot = MagicMock()
        watcher.sent_store = MagicMock()
        watcher.sent_store.is_sent.return_value = True

        watcher._first_run = False
        watcher._poll_once()

        watcher.telegram_bot.send_disclosure.assert_not_called()
        watcher.sent_store.mark_sent.assert_not_called()

    def test_error_skips_company(self):
        """Error polling a company should not crash the watcher."""
        config = _make_config()
        watcher = Watcher(config)
        watcher.company_store = MagicMock()
        watcher.company_store.list_all.return_value = {
            "00126380": "삼성전자",
            "00200100": "LG전자",
        }

        watcher.dart_client = MagicMock()
        watcher.dart_client.get_latest_disclosures.side_effect = [
            Exception("API Error"),
            [_make_disclosure(rcept_no="002", report_nm="사업보고서")],
        ]

        watcher.telegram_bot = MagicMock()
        watcher.telegram_bot.send_disclosure.return_value = True
        watcher.sent_store = MagicMock()
        watcher.sent_store.is_sent.return_value = False

        watcher._first_run = False
        watcher._poll_once()

        # Second company should still be processed
        watcher.telegram_bot.send_disclosure.assert_called_once()

    def test_no_companies(self):
        """No companies should result in no API calls."""
        config = _make_config()
        watcher = Watcher(config)
        watcher.company_store = MagicMock()
        watcher.company_store.list_all.return_value = {}
        watcher.dart_client = MagicMock()

        watcher._poll_once()

        watcher.dart_client.get_latest_disclosures.assert_not_called()
