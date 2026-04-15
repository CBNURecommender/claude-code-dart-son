import argparse

from config import Config
from dart.client import DartClient
from storage.store import CompanyStore
from telegram.bot import TelegramBot
from monitor.watcher import Watcher


def _print(msg: str):
    """Print with UTF-8 encoding support."""
    try:
        print(msg)
    except UnicodeEncodeError:
        # Fallback for Windows console with limited encoding
        print(msg.encode("utf-8", errors="replace").decode("utf-8"))


def cmd_add(args, config: Config):
    """Add a company to watch list."""
    client = DartClient(config.dart_api_key)
    results = client.search_company(args.company_name)

    if not results:
        _print(f"'{args.company_name}' 검색 결과가 없습니다.")
        return

    # If exact match exists, use it directly
    exact = [r for r in results if r[1] == args.company_name]
    if exact:
        corp_code, corp_name, stock_code = exact[0]
    elif len(results) == 1:
        corp_code, corp_name, stock_code = results[0]
    else:
        _print(f"검색 결과 ({len(results)}건):")
        for i, (code, name, stock) in enumerate(results[:10], 1):
            stock_info = f" [{stock}]" if stock else ""
            _print(f"  {i}. {name}{stock_info} (코드: {code})")
        try:
            choice = int(input("선택 (번호): ")) - 1
            if 0 <= choice < len(results[:10]):
                corp_code, corp_name, stock_code = results[choice]
            else:
                _print("잘못된 선택입니다.")
                return
        except (ValueError, EOFError):
            _print("취소되었습니다.")
            return

    store = CompanyStore()
    store.add(corp_code, corp_name)
    stock_info = f" [{stock_code}]" if stock_code else ""
    _print(f"[OK] '{corp_name}'{stock_info} 등록 완료 (코드: {corp_code})")


def cmd_remove(args, config: Config):
    """Remove a company from watch list."""
    store = CompanyStore()
    if store.remove_by_name(args.company_name):
        _print(f"[OK] '{args.company_name}' 삭제 완료")
    else:
        _print(f"'{args.company_name}' 를 찾을 수 없습니다.")
        companies = store.list_all()
        if companies:
            _print("등록된 기업:")
            for code, name in companies.items():
                _print(f"  - {name} ({code})")


def cmd_list(args, config: Config):
    """List watched companies."""
    store = CompanyStore()
    companies = store.list_all()
    if not companies:
        _print("등록된 기업이 없습니다.")
        return
    _print(f"감시 중인 기업 ({len(companies)}개):")
    for code, name in companies.items():
        _print(f"  - {name} (코드: {code})")


def cmd_test_telegram(args, config: Config):
    """Test Telegram bot connection."""
    bot = TelegramBot(config.telegram_bot_token, config.telegram_chat_id)
    username = bot.ping()
    if username:
        _print(f"[OK] 봇 연결 성공: @{username}")
        if bot.send_text("DART 공시 알림봇 테스트 메시지입니다."):
            _print("[OK] 테스트 메시지 전송 완료")
        else:
            _print("[FAIL] 메시지 전송 실패")
    else:
        _print("[FAIL] 봇 연결 실패. TELEGRAM_BOT_TOKEN을 확인하세요.")


def cmd_start(args, config: Config):
    """Start the disclosure watcher."""
    watcher = Watcher(config)
    watcher.start()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DART 공시 텔레그램 알림봇")
    subparsers = parser.add_subparsers(dest="command", help="사용 가능한 명령어")

    add_parser = subparsers.add_parser("add", help="감시할 기업 추가")
    add_parser.add_argument("company_name", help="기업명")

    remove_parser = subparsers.add_parser("remove", help="감시 기업 삭제")
    remove_parser.add_argument("company_name", help="기업명")

    subparsers.add_parser("list", help="감시 기업 목록")
    subparsers.add_parser("test-telegram", help="텔레그램 봇 연결 테스트")
    subparsers.add_parser("start", help="공시 감시 시작")

    return parser


COMMANDS = {
    "add": cmd_add,
    "remove": cmd_remove,
    "list": cmd_list,
    "test-telegram": cmd_test_telegram,
    "start": cmd_start,
}
