import logging
import time
import urllib3
from typing import List, Optional

import requests

from dart.parser import Disclosure
from storage.store import SubscriberStore

logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"


class TelegramBot:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = TELEGRAM_API_BASE.format(token=token)
        self.subscriber_store = SubscriberStore()
        # Ensure the owner is always subscribed
        self.subscriber_store.add(chat_id, "owner")

    def _send_message_to_chat(self, chat_id: str, text: str) -> bool:
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, timeout=10, verify=False)
                if resp.status_code == 200:
                    return True
                logger.warning(
                    "Telegram sendMessage failed (attempt %d): %s %s",
                    attempt + 1, resp.status_code, resp.text,
                )
            except requests.RequestException as e:
                logger.warning(
                    "Telegram request error (attempt %d): %s", attempt + 1, e
                )
            if attempt < 2:
                time.sleep(2 ** attempt)
        logger.error("Failed to send Telegram message after 3 attempts")
        return False

    def _send_message(self, text: str) -> bool:
        return self._send_message_to_chat(self.chat_id, text)

    def send_disclosure(self, disclosure: Disclosure) -> bool:
        message = disclosure.to_telegram_message()
        return self._send_message(message)

    def broadcast_disclosure(self, disclosure: Disclosure) -> int:
        """Send disclosure to all subscribers. Returns number of successful sends."""
        message = disclosure.to_telegram_message()
        chat_ids = self.subscriber_store.get_all_chat_ids()
        success_count = 0
        for cid in chat_ids:
            if self._send_message_to_chat(cid, message):
                success_count += 1
            else:
                logger.warning("Failed to send to subscriber %s", cid)
        return success_count

    def send_text(self, text: str) -> bool:
        return self._send_message(text)

    def ping(self) -> Optional[str]:
        url = f"{self.base_url}/getMe"
        try:
            resp = requests.get(url, timeout=10, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return data["result"].get("username")
            logger.error("Telegram getMe failed: %s", resp.text)
        except requests.RequestException as e:
            logger.error("Telegram getMe error: %s", e)
        return None
