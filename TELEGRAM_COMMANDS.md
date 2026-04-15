# Telegram 명령어 기능 (양방향 봇)

**추가된 기능**: Telegram 메시지로 기업 추가/삭제/조회 가능
**상태**: ✅ 완성 (8개 테스트 PASSED + 기존 26개 PASSED = 34/34)

---

## 🎯 개선사항

### 기존 방식 (불편)
```
노트북/PC → SSH 접속 → GCP VM → python main.py add "삼성전자"
```

### 새로운 방식 (편함) ✨
```
텔레그램 채팅 → /add 삼성전자 → 자동 등록 + 공시 알림
```

---

## 📋 사용 가능한 명령어

### 1. `/add <회사명>` - 기업 추가

```
사용자: /add 삼성전자
봇응답: [OK] 삼성전자 [005930] 등록 완료 (코드: 00126380)
```

**검색 결과 1건인 경우** → 바로 등록
**검색 결과 0건인 경우** → 오류 메시지

```
사용자: /add 없는회사
봇응답: '없는회사' 검색 결과가 없습니다.
```

**검색 결과 여러 건인 경우** → 선택 요청

```
사용자: /add 삼성
봇응답: 검색 결과 (5건):
        1. 삼성전자 [005930]
        2. 삼성전자우 [005935]
        3. 삼성SDI [006400]
        번호를 입력하세요

사용자: 1
봇응답: [OK] 삼성전자 [005930] 등록 완료 (코드: 00126380)
```

---

### 2. `/remove <회사명>` - 기업 삭제

```
사용자: /remove 삼성전자
봇응답: [OK] 삼성전자 삭제 완료
```

등록되지 않은 기업인 경우:

```
사용자: /remove 없는회사
봇응답: '없는회사' 를 찾을 수 없습니다.
        등록된 기업:
          - SK하이닉스 (코드: 00164779)
```

---

### 3. `/list` - 등록 기업 목록 조회

```
사용자: /list
봇응답: 감시 중인 기업 (2개):
        - SK하이닉스 (코드: 00164779)
        - 삼성전자 (코드: 00126380)
```

등록된 기업이 없을 때:

```
사용자: /list
봇응답: 등록된 기업이 없습니다.
```

---

### 4. `/help` - 도움말

```
사용자: /help
봇응답: DART 공시 알림봇 명령어:

        /add <회사명>      - 회사 추가
          예: /add 삼성전자

        /remove <회사명>   - 회사 삭제
          예: /remove 삼성전자

        /list              - 등록된 회사 목록

        /help              - 도움말
```

---

## 🔧 구현 방식

### 아키텍처

```
┌─────────────────────────────────────────────────────┐
│  Watcher (main.py start)                            │
│                                                     │
│  ┌──────────────────┐    ┌──────────────────────┐  │
│  │ 공시 폴링 루프    │    │ Telegram 명령어 핸들 │  │
│  │ (30초 주기)      │    │ (2초 주기, 별도 스레드)│  │
│  │                  │    │                      │  │
│  │ DART API 조회    │    │ /add, /remove        │  │
│  │ → 신규 공시      │    │ /list, /help         │  │
│  │ → 텔레그램 발송  │    │                      │  │
│  └──────────────────┘    └──────────────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘
           ↓                     ↓
       Telegram Bot API    Telegram getUpdates API
```

### 새로 추가된 파일

| 파일 | 역할 |
|------|------|
| `telegram/handler.py` | TelegramCommandHandler 클래스 |
| `tests/test_telegram_handler.py` | 8개 테스트 케이스 |

### 수정된 파일

| 파일 | 변경 내용 |
|------|---------|
| `telegram/bot.py` | `_send_message_to_chat()` 메서드 추가 |
| `monitor/watcher.py` | 별도 스레드에서 handler 실행 |

---

## 📊 구현 세부사항

### TelegramCommandHandler 클래스

```python
class TelegramCommandHandler:
    def __init__(self, telegram_bot, dart_client, company_store)
    def start()              # Telegram 메시지 폴링 시작
    def stop()               # 폴링 중지
    def _get_updates()       # Telegram getUpdates API 호출
    def _send_reply()        # 사용자에게 응답 메시지 발송
    def _handle_message()    # 메시지 파싱 및 명령어 라우팅
    def _handle_add_command()         # /add 구현
    def _handle_remove_command()      # /remove 구현
    def _handle_list_command()        # /list 구현
    def _handle_help_command()        # /help 구현
    def _poll_once()         # 한 번의 폴링
```

### 동작 흐름

```
1. Watcher.start()
   ├─ TelegramCommandHandler 인스턴스 생성
   ├─ 별도 스레드에서 handler.start() 실행
   └─ 메인 스레드: 공시 폴링 루프 (30초 주기)

2. TelegramCommandHandler.start()
   └─ 무한 루프: getUpdates API 폴링 (2초 주기)
      ├─ 새 메시지 수신
      ├─ 명령어 파싱 (/add, /remove, /list, /help)
      ├─ 해당 핸들러 함수 호출
      └─ 응답 메시지 발송

3. 병렬 실행
   ├─ Main thread: 공시 폴링 (30초)
   └─ Handler thread: 명령어 폴링 (2초)
```

---

## 🧪 테스트 결과

### 새로운 테스트 (test_telegram_handler.py)

| 테스트 | 결과 | 설명 |
|-------|------|------|
| `test_add_single_result` | ✅ | 검색 결과 1건 → 바로 등록 |
| `test_add_no_results` | ✅ | 검색 결과 0건 → 오류 메시지 |
| `test_add_multiple_results` | ✅ | 검색 결과 여러 건 → 선택 요청 |
| `test_remove_command` | ✅ | 기업 삭제 정상 작동 |
| `test_list_command` | ✅ | 기업 목록 조회 정상 작동 |
| `test_list_empty` | ✅ | 등록 기업 없을 때 처리 |
| `test_help_command` | ✅ | 도움말 출력 정상 작동 |
| `test_invalid_command` | ✅ | 유효하지 않은 명령어 → 도움말 |

### 전체 테스트

```
✅ 34/34 PASSED
├─ 기존 테스트: 26개 (dart_client, telegram_bot, store, watcher)
└─ 새로운 테스트: 8개 (telegram_handler)
```

---

## 🚀 배포 후 사용법

### 1단계: VM에서 서비스 시작
```bash
sudo systemctl start dart-noti-bot
sudo systemctl status dart-noti-bot  # 확인
```

### 2단계: Telegram에서 명령어 입력

```
텔레그램 봇과의 채팅창에서:

/add SK하이닉스
/list
/help
```

### 3단계: 실시간 공시 알림 수신

SK하이닉스의 새 공시가 올라오면 자동으로 텔레그램 메시지 수신!

```
📢 새 공시 알림

🏢 기업: SK하이닉스
📄 제목: 주요사항보고서
📅 날짜: 20260325
👤 제출인: SK하이닉스

🔗 https://dart.fss.or.kr/dsaf001/main.do?rcpNo=...
```

---

## ⚙️ 기술 세부사항

### Telegram Polling 방식

```python
# getUpdates API를 2초마다 호출
updates = requests.get(
    f"https://api.telegram.org/bot{TOKEN}/getUpdates",
    params={"offset": update_id + 1, "timeout": 10}
)
```

### 멀티스레딩

```python
# Main thread: 공시 폴링 (30초 주기)
while running:
    _poll_once()  # 공시 조회 및 발송
    sleep(30)

# Handler thread: 명령어 폴링 (2초 주기, 별도 스레드)
handler_thread = threading.Thread(
    target=command_handler.start,
    daemon=True
)
handler_thread.start()
```

### 기업 검색

```python
# 사용자가 "/add 삼성" 입력
# 1. DART API에서 검색
results = dart_client.search_company("삼성")
# 2. 정확 매칭 확인
exact = [r for r in results if r[1] == "삼성전자"]
# 3. 결과 개수에 따라 처리
if exact:      # 정확 매칭 → 바로 등록
if 1건:        # 1건만 → 바로 등록
else:          # 여러 건 → 선택 요청
```

---

## 📝 주요 특징

✅ **실시간 반응**: 2초 주기 폴링으로 빠른 명령어 처리
✅ **병렬 실행**: 공시 감시와 명령어 처리가 독립적으로 동작
✅ **안정성**: 명령어 처리 오류가 공시 감시에 영향 없음
✅ **재시도 로직**: 모든 API 호출에 3회 재시도 적용
✅ **다중 사용자**: 같은 채팅이면 동일 기업 목록 공유

---

## 🔐 보안 고려사항

- API 키는 환경변수(.env)로 관리 → 코드에 노출 안 됨
- Telegram Chat ID는 하드코딩 → 다른 사용자가 명령어 실행 불가
- 모든 메시지는 로깅됨 → 감시 가능

---

## 🎓 다음 개선 사항 (Optional)

- [ ] 여러 Telegram 채팅 지원 (기업별로 다른 채팅)
- [ ] `/filter` 명령어로 공시 유형 필터링 (예: 주요사항보고서만)
- [ ] `/stats` 명령어로 감시 통계 조회
- [ ] Claude API 연동으로 자연어 명령어 지원
- [ ] 정기 리포트 (예: 매주 월요일 감시 기업 요약)

---

**최종 상태**: ✅ **PRODUCTION READY**

이제 GCP VM에 배포하고 Telegram 봇으로 언제 어디서든 기업을 관리할 수 있습니다!
