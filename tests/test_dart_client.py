import io
import os
import sys
import zipfile

import pytest
import responses

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dart.client import DART_API_BASE, DartApiRateLimited, DartClient


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Skip time.sleep in retry helper to keep tests fast."""
    monkeypatch.setattr("dart.client.time.sleep", lambda _s: None)


def _make_corp_code_zip(corps: list) -> bytes:
    """Create a ZIP containing corpCode.xml with given corps.
    corps: list of (corp_code, corp_name, stock_code)
    """
    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<result>"]
    for code, name, stock in corps:
        xml_lines.append(
            f"<list><corp_code>{code}</corp_code>"
            f"<corp_name>{name}</corp_name>"
            f"<stock_code>{stock}</stock_code></list>"
        )
    xml_lines.append("</result>")
    xml_content = "\n".join(xml_lines).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("corpCode.xml", xml_content)
    return buf.getvalue()


@responses.activate
def test_search_company(tmp_path):
    corps = [
        ("00126380", "삼성전자", "005930"),
        ("00126381", "삼성전자우", "005935"),
        ("00200100", "LG전자", "066570"),
    ]
    zip_data = _make_corp_code_zip(corps)

    responses.add(
        responses.GET,
        f"{DART_API_BASE}/corpCode.xml",
        body=zip_data,
        status=200,
    )

    client = DartClient("test_key", data_dir=str(tmp_path))
    results = client.search_company("삼성전자")

    assert len(results) == 2
    # Exact match should come first
    assert results[0][1] == "삼성전자"
    assert results[0][0] == "00126380"


@responses.activate
def test_search_company_no_results(tmp_path):
    zip_data = _make_corp_code_zip([("00126380", "삼성전자", "005930")])

    responses.add(
        responses.GET,
        f"{DART_API_BASE}/corpCode.xml",
        body=zip_data,
        status=200,
    )

    client = DartClient("test_key", data_dir=str(tmp_path))
    results = client.search_company("없는회사")
    assert results == []


@responses.activate
def test_get_latest_disclosures(tmp_path):
    # Pre-create cached XML so no ZIP download needed
    xml_content = '<?xml version="1.0"?><result><list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name><stock_code>005930</stock_code></list></result>'
    xml_path = tmp_path / "corp_codes.xml"
    xml_path.write_text(xml_content, encoding="utf-8")

    responses.add(
        responses.GET,
        f"{DART_API_BASE}/list.json",
        json={
            "status": "000",
            "message": "정상",
            "list": [
                {
                    "corp_code": "00126380",
                    "corp_name": "삼성전자",
                    "report_nm": "분기보고서",
                    "rcept_no": "20240101000001",
                    "flr_nm": "삼성전자",
                    "rcept_dt": "20240101",
                    "rm": "",
                }
            ],
        },
        status=200,
    )

    client = DartClient("test_key", data_dir=str(tmp_path))
    disclosures = client.get_latest_disclosures("00126380")
    assert len(disclosures) == 1
    assert disclosures[0].report_nm == "분기보고서"
    assert disclosures[0].rcept_no == "20240101000001"


@responses.activate
def test_get_latest_disclosures_no_data(tmp_path):
    xml_content = '<?xml version="1.0"?><result></result>'
    xml_path = tmp_path / "corp_codes.xml"
    xml_path.write_text(xml_content, encoding="utf-8")

    responses.add(
        responses.GET,
        f"{DART_API_BASE}/list.json",
        json={"status": "013", "message": "조회된 데이터가 없습니다."},
        status=200,
    )

    client = DartClient("test_key", data_dir=str(tmp_path))
    disclosures = client.get_latest_disclosures("99999999")
    assert disclosures == []


@responses.activate
def test_get_latest_disclosures_api_error(tmp_path):
    xml_content = '<?xml version="1.0"?><result></result>'
    xml_path = tmp_path / "corp_codes.xml"
    xml_path.write_text(xml_content, encoding="utf-8")

    responses.add(
        responses.GET,
        f"{DART_API_BASE}/list.json",
        body=responses.ConnectionError("Connection refused"),
    )

    client = DartClient("test_key", data_dir=str(tmp_path))
    disclosures = client.get_latest_disclosures("00126380")
    assert disclosures == []


# --- New: global polling + retry + rate limit tests ---


@responses.activate
def test_get_all_recent_disclosures_success(tmp_path):
    responses.add(
        responses.GET,
        f"{DART_API_BASE}/list.json",
        json={
            "status": "000",
            "message": "정상",
            "list": [
                {
                    "corp_code": "00126380",
                    "corp_name": "삼성전자",
                    "report_nm": "분기보고서",
                    "rcept_no": "20240101000001",
                    "flr_nm": "삼성전자",
                    "rcept_dt": "20240101",
                    "rm": "",
                },
                {
                    "corp_code": "00200100",
                    "corp_name": "LG전자",
                    "report_nm": "사업보고서",
                    "rcept_no": "20240101000002",
                    "flr_nm": "LG전자",
                    "rcept_dt": "20240101",
                    "rm": "",
                },
            ],
        },
        status=200,
    )

    client = DartClient("test_key", data_dir=str(tmp_path))
    results = client.get_all_recent_disclosures(bgn_de="20240101")
    assert len(results) == 2
    assert {r.corp_code for r in results} == {"00126380", "00200100"}


@responses.activate
def test_get_all_recent_disclosures_rate_limit_raises(tmp_path):
    responses.add(
        responses.GET,
        f"{DART_API_BASE}/list.json",
        json={"status": "020", "message": "사용한도를 초과하였습니다."},
        status=200,
    )

    client = DartClient("test_key", data_dir=str(tmp_path))
    with pytest.raises(DartApiRateLimited):
        client.get_all_recent_disclosures(bgn_de="20240101")


@responses.activate
def test_get_all_recent_disclosures_pagination_stops_on_partial_page(tmp_path):
    """When a page returns <page_count items, pagination stops early."""
    responses.add(
        responses.GET,
        f"{DART_API_BASE}/list.json",
        json={
            "status": "000",
            "list": [
                {
                    "corp_code": "00126380",
                    "corp_name": "삼성전자",
                    "report_nm": "x",
                    "rcept_no": "a",
                    "flr_nm": "x",
                    "rcept_dt": "20240101",
                    "rm": "",
                }
            ],
        },
        status=200,
    )
    client = DartClient("test_key", data_dir=str(tmp_path))
    results = client.get_all_recent_disclosures(
        bgn_de="20240101", page_count=100, max_pages=5
    )
    assert len(results) == 1
    # Only 1 HTTP call because page had < page_count items
    assert len(responses.calls) == 1


@responses.activate
def test_retry_on_network_error_then_success(tmp_path):
    """Transient failure followed by success should succeed without error."""
    responses.add(
        responses.GET,
        f"{DART_API_BASE}/list.json",
        body=responses.ConnectionError("transient"),
    )
    responses.add(
        responses.GET,
        f"{DART_API_BASE}/list.json",
        json={"status": "000", "list": []},
        status=200,
    )
    client = DartClient("test_key", data_dir=str(tmp_path))
    results = client.get_all_recent_disclosures(bgn_de="20240101")
    assert results == []
    # Confirms the retry actually happened (2 attempts)
    assert len(responses.calls) == 2


@responses.activate
def test_retry_gives_up_after_max_attempts(tmp_path):
    """After max_retries network failures, returns None (→ empty list)."""
    for _ in range(5):
        responses.add(
            responses.GET,
            f"{DART_API_BASE}/list.json",
            body=responses.ConnectionError("permanent"),
        )
    client = DartClient("test_key", data_dir=str(tmp_path))
    results = client.get_all_recent_disclosures(bgn_de="20240101")
    assert results == []
    # 3 retry attempts exhausted
    assert len(responses.calls) == 3
