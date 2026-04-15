import logging
import time

import requests

from dart.client import DartClient
from storage.store import CompanyStore
from telegram.bot import TelegramBot

logger = logging.getLogger(__name__)


class TelegramCommandHandler:
    def __init__(self, telegram_bot: TelegramBot, dart_client: DartClient, company_store: CompanyStore):
        self.bot = telegram_bot
        self.dart_client = dart_client
        self.store = company_store
        self._last_update_id = 0
        self._running = False
        self._pending_selections = {}

    def _get_updates(self) -> list:
        url = f"https://api.telegram.org/bot{self.bot.token}/getUpdates"
        params = {"offset": self._last_update_id + 1, "timeout": 10}
        try:
            resp = requests.get(url, params=params, timeout=15, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return data.get("result", [])
            logger.warning("Telegram getUpdates failed: %s", resp.text)
        except requests.RequestException as e:
            logger.warning("Telegram getUpdates error: %s", e)
        return []

    def _send_reply(self, chat_id: str, text: str) -> bool:
        return self.bot._send_message_to_chat(chat_id, text)

    def _handle_subscribe_command(self, chat_id: str, username: str):
        if self.bot.subscriber_store.add(chat_id, username):
            count = self.bot.subscriber_store.count()
            self._send_reply(chat_id, f"구독 완료! 새로운 공시가 등록되면 알림을 받습니다.\n현재 구독자 수: {count}명")
        else:
            self._send_reply(chat_id, "이미 구독 중입니다.")

    def _handle_unsubscribe_command(self, chat_id: str):
        if self.bot.subscriber_store.remove(chat_id):
            self._send_reply(chat_id, "구독이 해제되었습니다. 더 이상 알림을 받지 않습니다.")
        else:
            self._send_reply(chat_id, "구독 중이 아닙니다.")

    def _handle_add_command(self, chat_id: str, args: str):
        if not args.strip():
            self._send_reply(chat_id, "회사명을 입력해주세요.\n예: /add 삼성전자")
            return
        company_name = args.strip()
        logger.info("Searching company: %s", company_name)
        results = self.dart_client.search_company(company_name)
        if not results:
            self._send_reply(chat_id, f"'{company_name}' 검색 결과가 없습니다.")
            return
        exact = [r for r in results if r[1] == company_name]
        if exact:
            corp_code, corp_name, stock_code = exact[0]
            self.store.add(corp_code, corp_name)
            stock_info = f" [{stock_code}]" if stock_code else ""
            self._send_reply(chat_id, f"[OK] '{corp_name}'{stock_info} 등록 완료 (코드: {corp_code})")
            return
        if len(results) == 1:
            corp_code, corp_name, stock_code = results[0]
            self.store.add(corp_code, corp_name)
            stock_info = f" [{stock_code}]" if stock_code else ""
            self._send_reply(chat_id, f"[OK] '{corp_name}'{stock_info} 등록 완료 (코드: {corp_code})")
            return
        msg_lines = [f"검색 결과 ({len(results[:10])}건):"]
        for i, (code, name, stock) in enumerate(results[:10], 1):
            stock_info = f" [{stock}]" if stock else ""
            msg_lines.append(f"{i}. {name}{stock_info} (코드: {code})")
        msg_lines.append("\n번호를 입력하세요 (예: 1)")
        self._pending_selections[chat_id] = (results[:10], company_name)
        self._send_reply(chat_id, "\n".join(msg_lines))

    def _handle_remove_command(self, chat_id: str, args: str):
        if not args.strip():
            self._send_reply(chat_id, "회사명을 입력해주세요.\n예: /remove 삼성전자")
            return
        company_name = args.strip()
        if self.store.remove_by_name(company_name):
            self._send_reply(chat_id, f"[OK] '{company_name}' 삭제 완료")
        else:
            companies = self.store.list_all()
            if companies:
                msg_lines = [f"'{company_name}' 를 찾을 수 없습니다.", "등록된 기업:"]
                for code, name in companies.items():
                    msg_lines.append(f"  - {name} ({code})")
                self._send_reply(chat_id, "\n".join(msg_lines))
            else:
                self._send_reply(chat_id, f"'{company_name}' 를 찾을 수 없습니다.")

    def _handle_list_command(self, chat_id: str):
        companies = self.store.list_all()
        if not companies:
            self._send_reply(chat_id, "등록된 기업이 없습니다.")
            return
        msg_lines = [f"감시 중인 기업 ({len(companies)}개):"]
        for code, name in companies.items():
            msg_lines.append(f"  - {name} (코드: {code})")
        self._send_reply(chat_id, "\n".join(msg_lines))

    def _handle_help_command(self, chat_id: str):
        subscribed = self.bot.subscriber_store.is_subscribed(chat_id)
        status = "구독 중" if subscribed else "미구독"
        msg = f"""DART 공시 알림봇 명령어:

/subscribe         - 공시 알림 구독
/unsubscribe       - 공시 알림 해제

/add <회사명>      - 감시 회사 추가
  예: /add 삼성전자
/remove <회사명>   - 감시 회사 삭제
  예: /remove 삼성전자
/list              - 감시 중인 회사 목록

/help              - 도움말

현재 상태: {status}"""
        self._send_reply(chat_id, msg)

    def _handle_message(self, message: dict):
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip()
        username = message.get("from", {}).get("username", "") or message.get("from", {}).get("first_name", "")
        if not text or not chat_id:
            return
        logger.info("Received message from %s (%s): %s", chat_id, username, text)

        if text.startswith("/start") or text.startswith("/subscribe"):
            self._handle_subscribe_command(chat_id, username)
        elif text.startswith("/unsubscribe"):
            self._handle_unsubscribe_command(chat_id)
        elif text.startswith("/add "):
            self._handle_add_command(chat_id, text[5:].strip())
        elif text.startswith("/remove "):
            self._handle_remove_command(chat_id, text[8:].strip())
        elif text.startswith("/list"):
            self._handle_list_command(chat_id)
        elif text.startswith("/help"):
            self._handle_help_command(chat_id)
        elif text.isdigit() and chat_id in self._pending_selections:
            results, company_name = self._pending_selections[chat_id]
            try:
                choice = int(text) - 1
                if 0 <= choice < len(results):
                    corp_code, corp_name, stock_code = results[choice]
                    self.store.add(corp_code, corp_name)
                    stock_info = f" [{stock_code}]" if stock_code else ""
                    self._send_reply(chat_id, f"[OK] '{corp_name}'{stock_info} 등록 완료 (코드: {corp_code})")
                    del self._pending_selections[chat_id]
                else:
                    self._send_reply(chat_id, "잘못된 번호입니다.")
            except (ValueError, KeyError):
                self._send_reply(chat_id, "번호를 입력해주세요.")
        else:
            self._handle_help_command(chat_id)

    def _poll_once(self):
        updates = self._get_updates()
        for update in updates:
            self._last_update_id = update.get("update_id", self._last_update_id)
            if "message" in update:
                try:
                    self._handle_message(update["message"])
                except Exception as e:
                    logger.error("Error handling message: %s", e)

    def start(self):
        self._running = True
        logger.info("Telegram command handler started")
        while self._running:
            try:
                self._poll_once()
            except Exception as e:
                logger.error("Command handler error: %s", e)
            time.sleep(2)

    def stop(self):
        self._running = False
        logger.info("Telegram command handler stopped")
