import io
import os
import sys
import zipfile

import responses

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dart.client import DartClient, DART_API_BASE


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
