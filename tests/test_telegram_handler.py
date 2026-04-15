import os
import sys
from unittest.mock import MagicMock


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram.handler import TelegramCommandHandler
from dart.client import DartClient
from storage.store import CompanyStore
from telegram.bot import TelegramBot


def _make_handler(tmp_path):
    bot = TelegramBot("123:ABC", "999")
    client = DartClient("test_key", data_dir=str(tmp_path))
    store = CompanyStore(path=str(tmp_path / "companies.json"))
    return TelegramCommandHandler(bot, client, store)


class TestTelegramCommandHandler:
    def test_add_single_result(self, tmp_path):
        """Test /add with single search result."""
        handler = _make_handler(tmp_path)
        handler._send_reply = MagicMock(return_value=True)

        # Mock search result
        handler.dart_client.search_company = MagicMock(
            return_value=[("00126380", "삼성전자", "005930")]
        )

        message = {
            "chat": {"id": "999"},
            "text": "/add 삼성전자",
        }

        handler._handle_message(message)

        # Should register company and send success message
        handler._send_reply.assert_called_once()
        assert "[OK]" in handler._send_reply.call_args[0][1]
        assert "삼성전자" in handler._send_reply.call_args[0][1]

    def test_add_no_results(self, tmp_path):
        """Test /add with no search results."""
        handler = _make_handler(tmp_path)
        handler._send_reply = MagicMock(return_value=True)
        handler.dart_client.search_company = MagicMock(return_value=[])

        message = {
            "chat": {"id": "999"},
            "text": "/add 없는회사",
        }

        handler._handle_message(message)

        handler._send_reply.assert_called_once()
        assert "검색 결과가 없습니다" in handler._send_reply.call_args[0][1]

    def test_add_multiple_results(self, tmp_path):
        """Test /add with multiple search results."""
        handler = _make_handler(tmp_path)
        handler._send_reply = MagicMock(return_value=True)

        results = [
            ("00126380", "삼성전자", "005930"),
            ("00126381", "삼성전자우", "005935"),
        ]
        handler.dart_client.search_company = MagicMock(return_value=results)

        message = {
            "chat": {"id": "999"},
            "text": "/add 삼성",
        }

        handler._handle_message(message)

        handler._send_reply.assert_called_once()
        msg = handler._send_reply.call_args[0][1]
        assert "검색 결과" in msg
        assert "1. 삼성전자" in msg
        assert "2. 삼성전자우" in msg

    def test_remove_command(self, tmp_path):
        """Test /remove command."""
        handler = _make_handler(tmp_path)
        handler._send_reply = MagicMock(return_value=True)

        # First add a company
        handler.store.add("00126380", "삼성전자")

        message = {
            "chat": {"id": "999"},
            "text": "/remove 삼성전자",
        }

        handler._handle_message(message)

        handler._send_reply.assert_called_once()
        assert "[OK]" in handler._send_reply.call_args[0][1]
        assert "삭제 완료" in handler._send_reply.call_args[0][1]

    def test_list_command(self, tmp_path):
        """Test /list command."""
        handler = _make_handler(tmp_path)
        handler._send_reply = MagicMock(return_value=True)

        # Add companies
        handler.store.add("00126380", "삼성전자")
        handler.store.add("00164779", "SK하이닉스")

        message = {
            "chat": {"id": "999"},
            "text": "/list",
        }

        handler._handle_message(message)

        handler._send_reply.assert_called_once()
        msg = handler._send_reply.call_args[0][1]
        assert "감시 중인 기업" in msg
        assert "삼성전자" in msg
        assert "SK하이닉스" in msg

    def test_list_empty(self, tmp_path):
        """Test /list when no companies registered."""
        handler = _make_handler(tmp_path)
        handler._send_reply = MagicMock(return_value=True)

        message = {
            "chat": {"id": "999"},
            "text": "/list",
        }

        handler._handle_message(message)

        handler._send_reply.assert_called_once()
        assert "등록된 기업이 없습니다" in handler._send_reply.call_args[0][1]

    def test_help_command(self, tmp_path):
        """Test /help command."""
        handler = _make_handler(tmp_path)
        handler._send_reply = MagicMock(return_value=True)

        message = {
            "chat": {"id": "999"},
            "text": "/help",
        }

        handler._handle_message(message)

        handler._send_reply.assert_called_once()
        msg = handler._send_reply.call_args[0][1]
        assert "/add" in msg
        assert "/remove" in msg
        assert "/list" in msg

    def test_invalid_command(self, tmp_path):
        """Test invalid command."""
        handler = _make_handler(tmp_path)
        handler._send_reply = MagicMock(return_value=True)

        message = {
            "chat": {"id": "999"},
            "text": "안녕하세요",
        }

        handler._handle_message(message)

        # Should show help
        handler._send_reply.assert_called_once()
        msg = handler._send_reply.call_args[0][1]
        assert "명령어" in msg
