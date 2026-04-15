import io
import logging
import os
import time
import xml.etree.ElementTree as ET
import zipfile
from typing import Dict, List, Optional, Tuple

import requests

from dart.parser import Disclosure

logger = logging.getLogger(__name__)

DART_API_BASE = "https://opendart.fss.or.kr/api"
CORP_CODE_CACHE_TTL = 24 * 3600  # 24 hours


class DartClient:
    def __init__(self, api_key: str, data_dir: Optional[str] = None):
        self.api_key = api_key
        self.data_dir = data_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
        )
        os.makedirs(self.data_dir, exist_ok=True)
        self._corp_cache: Optional[Dict[str, Tuple[str, str]]] = (
            None  # corp_name -> (corp_code, stock_code)
        )

    def _corp_code_xml_path(self) -> str:
        return os.path.join(self.data_dir, "corp_codes.xml")

    def _is_cache_valid(self) -> bool:
        path = self._corp_code_xml_path()
        if not os.path.exists(path):
            return False
        age = time.time() - os.path.getmtime(path)
        return age < CORP_CODE_CACHE_TTL

    def _download_corp_codes(self):
        """Download and extract corpCode.xml from DART ZIP."""
        logger.info("Downloading DART corp code list...")
        url = f"{DART_API_BASE}/corpCode.xml"
        resp = requests.get(
            url, params={"crtfc_key": self.api_key}, timeout=60, verify=False
        )  # verify=False for development
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            # The ZIP contains a single XML file
            xml_name = zf.namelist()[0]
            xml_data = zf.read(xml_name)

        xml_path = self._corp_code_xml_path()
        with open(xml_path, "wb") as f:
            f.write(xml_data)
        logger.info("Corp code list saved to %s", xml_path)

    def _load_corp_codes(self) -> Dict[str, Tuple[str, str]]:
        """Parse corp_codes.xml into {corp_name: (corp_code, stock_code)}."""
        if self._corp_cache is not None:
            return self._corp_cache

        if not self._is_cache_valid():
            self._download_corp_codes()

        tree = ET.parse(self._corp_code_xml_path())
        root = tree.getroot()

        result = {}
        for item in root.iter("list"):
            corp_name = item.findtext("corp_name", "")
            corp_code = item.findtext("corp_code", "")
            stock_code = item.findtext("stock_code", "")
            if corp_name and corp_code:
                result[corp_name] = (corp_code, stock_code or "")

        self._corp_cache = result
        logger.info("Loaded %d corp codes", len(result))
        return result

    def search_company(self, query: str) -> List[Tuple[str, str, str]]:
        """Search companies by name. Returns [(corp_code, corp_name, stock_code)]."""
        corp_codes = self._load_corp_codes()
        results = []
        for name, (code, stock) in corp_codes.items():
            if query in name:
                results.append((code, name, stock))
        # Sort: exact match first, then listed companies, then alphabetical
        results.sort(key=lambda x: (x[1] != query, x[2] == "", x[1]))
        return results[:20]

    def get_latest_disclosures(
        self, corp_code: str, page_count: int = 1
    ) -> List[Disclosure]:
        """Fetch latest disclosures for a company from DART list.json API."""
        url = f"{DART_API_BASE}/list.json"
        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "page_count": str(page_count),
            "page_no": "1",
        }
        try:
            resp = requests.get(
                url, params=params, timeout=30, verify=False
            )  # verify=False for development
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            logger.error("DART API error for %s: %s", corp_code, e)
            return []

        if data.get("status") != "000":
            if data.get("status") == "013":
                # No data
                return []
            logger.warning(
                "DART API status %s: %s", data.get("status"), data.get("message")
            )
            return []

        items = data.get("list", [])
        return [Disclosure.from_api(item) for item in items]
