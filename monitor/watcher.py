import datetime
import logging
import os
import signal
import threading
import time
from typing import Optional

from config import Config
from dart.client import DartApiRateLimited, DartClient
from storage.store import CompanyStore, SentNoticeStore
from telegram.bot import TelegramBot
from telegram.handler import TelegramCommandHandler

logger = logging.getLogger(__name__)

KST = datetime.timezone(datetime.timedelta(hours=9))


class Watcher:
    RATE_LIMIT_BACKOFF_SECONDS = 30 * 60  # 30 minutes
    FAILURE_ALERT_THRESHOLD = 3  # consecutive poll failures before telegram alert

    def __init__(self, config: Config):
        self.config = config
        self.dart_client = DartClient(config.dart_api_key)
        self.telegram_bot = TelegramBot(
            config.telegram_bot_token, config.telegram_chat_id
        )
        self.company_store = CompanyStore()
        self.sent_store = SentNoticeStore()
        self._running = False
        # Baseline mode: on very first run (empty sent_store) we mark all
        # existing disclosures as sent without notifying, to avoid flooding
        # the subscriber with historical items. On restart, sent_store has
        # entries (90-day expiry), so we can safely catch up with missed
        # notifications during downtime.
        self._baseline_mode = self.sent_store.count() == 0
        self._backoff_until = 0.0
        self._consecutive_failures = 0
        self._alert_sent = False
        self._heartbeat_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "heartbeat.txt",
        )
        self._command_handler = TelegramCommandHandler(
            self.telegram_bot, self.dart_client, self.company_store
        )
        self._handler_thread: Optional[threading.Thread] = None

    def _handle_signal(self, signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        self._running = False

    @staticmethod
    def _today_kst() -> str:
        return datetime.datetime.now(KST).strftime("%Y%m%d")

    def _touch_heartbeat(self):
        """Write current unix timestamp. External healthcheck reads this."""
        try:
            with open(self._heartbeat_path, "w") as f:
                f.write(str(int(time.time())))
        except OSError as e:
            logger.error("Failed to write heartbeat: %s", e)

    def _record_failure(self, reason: str):
        self._consecutive_failures += 1
        logger.warning(
            "Poll failure #%d: %s", self._consecutive_failures, reason
        )
        if (
            self._consecutive_failures >= self.FAILURE_ALERT_THRESHOLD
            and not self._alert_sent
        ):
            try:
                self.telegram_bot.send_text(
                    "⚠️ DART 공시 봇 경고\n\n"
                    f"연속 {self._consecutive_failures}회 폴링 실패\n"
                    f"원인: {reason}\n\n"
                    "봇이 자동으로 재시도 중이지만, 공시 수신이 지연될 수 있습니다."
                )
                self._alert_sent = True
            except Exception as e:
                logger.error("Failed to send failure alert: %s", e)

    def _record_success(self):
        if self._consecutive_failures > 0:
            logger.info(
                "Recovered after %d consecutive failures",
                self._consecutive_failures,
            )
            if self._alert_sent:
                try:
                    self.telegram_bot.send_text(
                        "✅ DART 공시 봇 복구\n\n"
                        f"{self._consecutive_failures}회 실패 후 정상 폴링 재개."
                    )
                except Exception as e:
                    logger.error("Failed to send recovery alert: %s", e)
            self._consecutive_failures = 0
            self._alert_sent = False

    def _poll_once(self):
        now = time.time()
        if now < self._backoff_until:
            remaining = int(self._backoff_until - now)
            logger.debug("In rate-limit backoff (%ds remaining)", remaining)
            return

        companies = self.company_store.list_all()
        if not companies:
            logger.debug("No companies to watch")
            return

        try:
            all_disclosures = self.dart_client.get_all_recent_disclosures(
                bgn_de=self._today_kst(), page_count=100, max_pages=5
            )
        except DartApiRateLimited as e:
            logger.warning(
                "DART API rate limit hit: %s — backing off for %d minutes",
                e, self.RATE_LIMIT_BACKOFF_SECONDS // 60,
            )
            self._backoff_until = now + self.RATE_LIMIT_BACKOFF_SECONDS
            return
        except Exception as e:
            self._record_failure(f"poll exception: {e}")
            return

        self._record_success()
        matched = [d for d in all_disclosures if d.corp_code in companies]
        logger.debug(
            "Fetched %d disclosures (today), %d match watched companies",
            len(all_disclosures), len(matched),
        )

        for disc in matched:
            if self.sent_store.is_sent(disc.rcept_no):
                continue
            if self._baseline_mode:
                self.sent_store.mark_sent(disc.rcept_no)
                continue
            # Prefer the user-configured company name from our store
            disc.corp_name = companies.get(disc.corp_code, disc.corp_name)
            logger.info("New disclosure: %s - %s", disc.corp_name, disc.report_nm)
            sent_count = self.telegram_bot.broadcast_disclosure(disc)
            if sent_count > 0:
                self.sent_store.mark_sent(disc.rcept_no)
                logger.info("Broadcast sent to %d subscribers", sent_count)
            else:
                logger.error(
                    "Failed to send notification for %s", disc.rcept_no
                )

        if self._baseline_mode and all_disclosures:
            self._baseline_mode = False
            logger.info(
                "Baseline established (%d disclosures marked without notifying)",
                len(matched),
            )

    def start(self):
        self._running = True
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        subscriber_count = self.telegram_bot.subscriber_store.count()
        logger.info(
            "Watcher started (global polling, interval: %ds)",
            self.config.poll_interval,
        )
        logger.info("Watching %d companies", len(self.company_store.list_all()))
        logger.info("Broadcasting to %d subscribers", subscriber_count)
        if self._baseline_mode:
            logger.info(
                "Baseline mode ON: first successful poll will mark existing "
                "disclosures as sent without notifying"
            )

        self._handler_thread = threading.Thread(
            target=self._command_handler.start, daemon=True
        )
        self._handler_thread.start()
        logger.info("Telegram command handler started")

        while self._running:
            try:
                self._poll_once()
                self.sent_store.cleanup_expired()
            except Exception as e:
                logger.error("Poll cycle error: %s", e)
            self._touch_heartbeat()

            for _ in range(self.config.poll_interval):
                if not self._running:
                    break
                time.sleep(1)

        self._command_handler.stop()
        if self._handler_thread:
            self._handler_thread.join(timeout=5)

        logger.info("Watcher stopped")
