import json
import os
import sys
import time


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.store import CompanyStore, SentNoticeStore


class TestCompanyStore:
    def test_add_and_list(self, tmp_path):
        store = CompanyStore(path=str(tmp_path / "companies.json"))
        store.add("00126380", "삼성전자")
        store.add("00200100", "LG전자")

        companies = store.list_all()
        assert len(companies) == 2
        assert companies["00126380"] == "삼성전자"
        assert companies["00200100"] == "LG전자"

    def test_remove(self, tmp_path):
        store = CompanyStore(path=str(tmp_path / "companies.json"))
        store.add("00126380", "삼성전자")
        assert store.remove("00126380") is True
        assert store.list_all() == {}

    def test_remove_nonexistent(self, tmp_path):
        store = CompanyStore(path=str(tmp_path / "companies.json"))
        assert store.remove("99999999") is False

    def test_remove_by_name(self, tmp_path):
        store = CompanyStore(path=str(tmp_path / "companies.json"))
        store.add("00126380", "삼성전자")
        assert store.remove_by_name("삼성전자") is True
        assert store.list_all() == {}

    def test_get_corp_codes(self, tmp_path):
        store = CompanyStore(path=str(tmp_path / "companies.json"))
        store.add("00126380", "삼성전자")
        store.add("00200100", "LG전자")
        codes = store.get_corp_codes()
        assert set(codes) == {"00126380", "00200100"}

    def test_persistence(self, tmp_path):
        path = str(tmp_path / "companies.json")
        store1 = CompanyStore(path=path)
        store1.add("00126380", "삼성전자")

        store2 = CompanyStore(path=path)
        assert store2.list_all() == {"00126380": "삼성전자"}

    def test_atomic_write(self, tmp_path):
        path = str(tmp_path / "companies.json")
        store = CompanyStore(path=path)
        store.add("00126380", "삼성전자")

        # Verify the file is valid JSON
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data == {"00126380": "삼성전자"}
        # No .tmp file should remain
        assert not os.path.exists(path + ".tmp")


class TestSentNoticeStore:
    def test_mark_and_check(self, tmp_path):
        store = SentNoticeStore(path=str(tmp_path / "sent.json"))
        assert store.is_sent("20240101000001") is False
        store.mark_sent("20240101000001")
        assert store.is_sent("20240101000001") is True

    def test_count(self, tmp_path):
        store = SentNoticeStore(path=str(tmp_path / "sent.json"))
        store.mark_sent("001")
        store.mark_sent("002")
        assert store.count() == 2

    def test_cleanup_expired(self, tmp_path):
        store = SentNoticeStore(path=str(tmp_path / "sent.json"))
        # Add an entry with a very old timestamp
        store.notices["old_entry"] = time.time() - (91 * 24 * 3600)
        store.notices["new_entry"] = time.time()
        store._save()

        store.cleanup_expired()
        assert "old_entry" not in store.notices
        assert "new_entry" in store.notices

    def test_persistence(self, tmp_path):
        path = str(tmp_path / "sent.json")
        store1 = SentNoticeStore(path=path)
        store1.mark_sent("20240101000001")

        store2 = SentNoticeStore(path=path)
        assert store2.is_sent("20240101000001") is True
