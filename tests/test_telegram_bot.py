import os
import sys

import responses

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram.bot import TelegramBot, TELEGRAM_API_BASE
from dart.parser import Disclosure


TOKEN = "123456:ABC-DEF"
CHAT_ID = "999"
BASE_URL = TELEGRAM_API_BASE.format(token=TOKEN)


@responses.activate
def test_send_disclosure_success():
    responses.add(
        responses.POST,
        f"{BASE_URL}/sendMessage",
        json={"ok": True, "result": {"message_id": 1}},
        status=200,
    )

    bot = TelegramBot(TOKEN, CHAT_ID)
    disc = Disclosure(
        corp_code="00126380",
        corp_name="삼성전자",
        report_nm="분기보고서",
        rcept_no="20240101000001",
        flr_nm="삼성전자",
        rcept_dt="20240101",
        rm="",
    )
    assert bot.send_disclosure(disc) is True
    assert len(responses.calls) == 1


@responses.activate
def test_send_message_retry_on_failure():
    # First two attempts fail, third succeeds
    responses.add(responses.POST, f"{BASE_URL}/sendMessage", status=500)
    responses.add(responses.POST, f"{BASE_URL}/sendMessage", status=500)
    responses.add(
        responses.POST,
        f"{BASE_URL}/sendMessage",
        json={"ok": True, "result": {"message_id": 1}},
        status=200,
    )

    bot = TelegramBot(TOKEN, CHAT_ID)
    assert bot.send_text("test") is True
    assert len(responses.calls) == 3


@responses.activate
def test_send_message_all_retries_fail():
    responses.add(responses.POST, f"{BASE_URL}/sendMessage", status=500)
    responses.add(responses.POST, f"{BASE_URL}/sendMessage", status=500)
    responses.add(responses.POST, f"{BASE_URL}/sendMessage", status=500)

    bot = TelegramBot(TOKEN, CHAT_ID)
    assert bot.send_text("test") is False
    assert len(responses.calls) == 3


@responses.activate
def test_ping_success():
    responses.add(
        responses.GET,
        f"{BASE_URL}/getMe",
        json={"ok": True, "result": {"username": "test_bot", "id": 123}},
        status=200,
    )

    bot = TelegramBot(TOKEN, CHAT_ID)
    assert bot.ping() == "test_bot"


@responses.activate
def test_ping_failure():
    responses.add(
        responses.GET,
        f"{BASE_URL}/getMe",
        json={"ok": False, "description": "Unauthorized"},
        status=401,
    )

    bot = TelegramBot(TOKEN, CHAT_ID)
    assert bot.ping() is None
