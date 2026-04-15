import json
import os
import time
from typing import Dict, List, Optional

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _atomic_write(path: str, data: dict):
    """Write JSON atomically using a temp file + rename."""
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # On Windows, need to remove target first if exists
    if os.path.exists(path):
        os.replace(tmp_path, path)
    else:
        os.rename(tmp_path, path)


class CompanyStore:
    """Manages watched companies (corp_code -> corp_name mapping)."""

    def __init__(self, path: Optional[str] = None):
        _ensure_data_dir()
        self.path = path or os.path.join(DATA_DIR, "companies.json")
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self.companies: Dict[str, str] = json.load(f)
        else:
            self.companies = {}

    def _save(self):
        _atomic_write(self.path, self.companies)

    def add(self, corp_code: str, corp_name: str):
        self.companies[corp_code] = corp_name
        self._save()

    def remove(self, corp_code: str) -> bool:
        if corp_code in self.companies:
            del self.companies[corp_code]
            self._save()
            return True
        return False

    def remove_by_name(self, corp_name: str) -> bool:
        code = self.find_code_by_name(corp_name)
        if code:
            return self.remove(code)
        return False

    def find_code_by_name(self, corp_name: str) -> Optional[str]:
        for code, name in self.companies.items():
            if name == corp_name:
                return code
        return None

    def list_all(self) -> Dict[str, str]:
        return dict(self.companies)

    def get_corp_codes(self) -> List[str]:
        return list(self.companies.keys())


class SentNoticeStore:
    """Tracks sent notice IDs to avoid duplicates. Entries expire after 90 days."""

    EXPIRY_SECONDS = 90 * 24 * 3600  # 90 days

    def __init__(self, path: Optional[str] = None):
        _ensure_data_dir()
        self.path = path or os.path.join(DATA_DIR, "sent_notices.json")
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self.notices: Dict[str, float] = json.load(f)
        else:
            self.notices = {}

    def _save(self):
        _atomic_write(self.path, self.notices)

    def is_sent(self, rcept_no: str) -> bool:
        return rcept_no in self.notices

    def mark_sent(self, rcept_no: str):
        self.notices[rcept_no] = time.time()
        self._save()

    def cleanup_expired(self):
        now = time.time()
        expired = [k for k, v in self.notices.items() if now - v > self.EXPIRY_SECONDS]
        for k in expired:
            del self.notices[k]
        if expired:
            self._save()

    def count(self) -> int:
        return len(self.notices)


class SubscriberStore:
    """Manages subscriber chat IDs for broadcast notifications."""

    def __init__(self, path: Optional[str] = None):
        _ensure_data_dir()
        self.path = path or os.path.join(DATA_DIR, "subscribers.json")
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.subscribers: Dict[str, str] = data if isinstance(data, dict) else {}
        else:
            self.subscribers = {}

    def _save(self):
        _atomic_write(self.path, self.subscribers)

    def add(self, chat_id: str, username: str = "") -> bool:
        """Add a subscriber. Returns True if newly added."""
        if chat_id in self.subscribers:
            return False
        self.subscribers[chat_id] = username
        self._save()
        return True

    def remove(self, chat_id: str) -> bool:
        """Remove a subscriber. Returns True if removed."""
        if chat_id in self.subscribers:
            del self.subscribers[chat_id]
            self._save()
            return True
        return False

    def is_subscribed(self, chat_id: str) -> bool:
        return chat_id in self.subscribers

    def get_all_chat_ids(self) -> List[str]:
        return list(self.subscribers.keys())

    def count(self) -> int:
        return len(self.subscribers)
