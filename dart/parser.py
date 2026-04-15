from dataclasses import dataclass


DART_BASE_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="


@dataclass
class Disclosure:
    corp_code: str
    corp_name: str
    report_nm: str
    rcept_no: str
    flr_nm: str
    rcept_dt: str
    rm: str

    @classmethod
    def from_api(cls, item: dict) -> "Disclosure":
        return cls(
            corp_code=item.get("corp_code", ""),
            corp_name=item.get("corp_name", ""),
            report_nm=item.get("report_nm", ""),
            rcept_no=item.get("rcept_no", ""),
            flr_nm=item.get("flr_nm", ""),
            rcept_dt=item.get("rcept_dt", ""),
            rm=item.get("rm", ""),
        )

    def dart_url(self) -> str:
        return f"{DART_BASE_URL}{self.rcept_no}"

    MARKET_CODES = {
        "유": "유가증권시장(KOSPI)",
        "코": "코스닥(KOSDAQ)",
        "넥": "코넥스(KONEX)",
    }

    def _market_name(self) -> str:
        return self.MARKET_CODES.get(self.rm, self.rm)

    def to_telegram_message(self) -> str:
        lines = [
            "📢 새 공시 알림",
            "",
            f"🏢 기업: {self.corp_name}",
            f"📄 제목: {self.report_nm}",
            f"📅 날짜: {self.rcept_dt}",
            f"👤 제출인: {self.flr_nm}",
        ]
        if self.rm:
            lines.append(f"📌 시장: {self._market_name()}")
        lines.append("")
        lines.append(f"🔗 {self.dart_url()}")
        return "\n".join(lines)
