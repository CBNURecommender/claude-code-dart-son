import logging
import signal
import threading
import time
from typing import Optional

from config import Config
from dart.client import DartClient
from storage.store import CompanyStore, SentNoticeStore
from telegram.bot import TelegramBot
from telegram.handler import TelegramCommandHandler

logger = logging.getLogger(__name__)


class Watcher:
    def __init__(self, config: Config):
        self.config = config
        self.dart_client = DartClient(config.dart_api_key)
        self.telegram_bot = TelegramBot(
            config.telegram_bot_token, config.telegram_chat_id
        )
        self.company_store = CompanyStore()
        self.sent_store = SentNoticeStore()
        self._running = False
        self._first_run = True
        self._command_handler = TelegramCommandHandler(
            self.telegram_bot, self.dart_client, self.company_store
        )
        self._handler_thread: Optional[threading.Thread] = None

    def _handle_signal(self, signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        self._running = False

    def _poll_once(self):
        """Poll all watched companies for new disclosures."""
        companies = self.company_store.list_all()
        if not companies:
            logger.debug("No companies to watch")
            return

        for corp_code, corp_name in companies.items():
            try:
                disclosures = self.dart_client.get_latest_disclosures(
                    corp_code, page_count=10
                )
                for disc in disclosures:
                    if self.sent_store.is_sent(disc.rcept_no):
                        continue
                    if self._first_run:
                        self.sent_store.mark_sent(disc.rcept_no)
                        continue
                    # New disclosure found - broadcast to all subscribers
                    logger.info("New disclosure: %s - %s", corp_name, disc.report_nm)
                    sent_count = self.telegram_bot.broadcast_disclosure(disc)
                    if sent_count > 0:
                        self.sent_store.mark_sent(disc.rcept_no)
                        logger.info(
                            "Broadcast sent to %d subscribers", sent_count
                        )
                    else:
                        logger.error(
                            "Failed to send notification for %s", disc.rcept_no
                        )
            except Exception as e:
                logger.error("Error polling %s (%s): %s", corp_name, corp_code, e)

    def start(self):
        """Start the polling loop and command handler."""
        self._running = True
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        subscriber_count = self.telegram_bot.subscriber_store.count()
        logger.info("Watcher started (poll interval: %ds)", self.config.poll_interval)
        logger.info("Watching %d companies", len(self.company_store.list_all()))
        logger.info("Broadcasting to %d subscribers", subscriber_count)

        # Start Telegram command handler in separate thread
        self._handler_thread = threading.Thread(
            target=self._command_handler.start, daemon=True
        )
        self._handler_thread.start()
        logger.info("Telegram command handler started")

        while self._running:
            try:
                self._poll_once()
                if self._first_run:
                    self._first_run = False
                    logger.info("First run complete - baseline established")
                self.sent_store.cleanup_expired()
            except Exception as e:
                logger.error("Poll cycle error: %s", e)

            for _ in range(self.config.poll_interval):
                if not self._running:
                    break
                time.sleep(1)

        self._command_handler.stop()
        if self._handler_thread:
            self._handler_thread.join(timeout=5)

        logger.info("Watcher stopped")
