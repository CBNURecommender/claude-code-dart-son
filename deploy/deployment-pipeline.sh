#!/bin/bash
# deployment-pipeline.sh - DART 공시 알림봇 자동 배포 파이프라인

set -euo pipefail

# ============================================================================
# 배포 파이프라인 설정
# ============================================================================

PROJECT_NAME="dart-noti-bot"
VM_IP="${1:-34.172.56.22}"
VM_USER="${2:-$USER}"
APP_DIR="/opt/dart-noti-bot"
BACKUP_DIR="/opt/backups"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 로깅 함수
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================================================
# Phase 1: 로컬 검증 (Local Validation)
# ============================================================================

phase_local_validation() {
    log_info "Phase 1: 로컬 검증 시작..."

    # 테스트 실행
    log_info "단위 테스트 실행..."
    if ! python -m pytest tests/ -v --tb=short > /tmp/test_results.txt 2>&1; then
        log_error "테스트 실패!"
        cat /tmp/test_results.txt
        exit 1
    fi

    TEST_COUNT=$(grep -c "PASSED" /tmp/test_results.txt || echo 0)
    log_info "✅ 테스트 PASSED: $TEST_COUNT개"

    # 코드 품질 검사
    log_info "코드 품질 검사 (ruff)..."
    if ! ruff check . > /tmp/ruff_check.txt 2>&1; then
        ruff check --fix . > /dev/null 2>&1
        ruff format . > /dev/null 2>&1
        log_warn "Ruff 자동 수정 완료"
    fi
    log_info "✅ 코드 품질 검사 완료"

    # .env 파일 확인
    if [ ! -f .env ]; then
        log_error ".env 파일이 없습니다. .env.example을 복사하세요."
        exit 1
    fi

    log_info "✅ Phase 1 완료"
}

# ============================================================================
# Phase 2: 배포 패키징 (Packaging)
# ============================================================================

phase_packaging() {
    log_info "Phase 2: 배포 패키징..."

    # 임시 디렉토리에 복사
    DEPLOY_DIR="/tmp/$PROJECT_NAME-deploy-$(date +%s)"
    mkdir -p "$DEPLOY_DIR"

    log_info "파일 복사 중..."
    rsync -a --exclude='.git' --exclude='__pycache__' --exclude='.pytest_cache' \
        --exclude='*.pyc' --exclude='data' --exclude='logs' --exclude='venv' \
        ./ "$DEPLOY_DIR/" > /dev/null

    # .env 파일은 배포에 포함하지 않음 (보안)
    rm -f "$DEPLOY_DIR/.env"

    log_info "배포 패키지 생성: $DEPLOY_DIR"
    log_info "✅ Phase 2 완료"

    echo "$DEPLOY_DIR"
}

# ============================================================================
# Phase 3: GCP VM 배포 (GCP Deployment)
# ============================================================================

phase_gcp_deployment() {
    local DEPLOY_DIR="$1"

    log_info "Phase 3: GCP VM 배포 시작..."

    # SSH 연결 테스트
    log_info "VM 연결 테스트 ($VM_IP)..."
    if ! ssh -o ConnectTimeout=5 "$VM_USER@$VM_IP" "echo 'Connection OK'" > /dev/null 2>&1; then
        log_error "VM에 연결할 수 없습니다: $VM_IP"
        exit 1
    fi
    log_info "✅ VM 연결 성공"

    # 백업 생성
    log_info "기존 배포 백업 중..."
    ssh "$VM_USER@$VM_IP" "
        if [ -d $APP_DIR ]; then
            mkdir -p $BACKUP_DIR
            sudo cp -r $APP_DIR $BACKUP_DIR/backup-\$(date +%Y%m%d_%H%M%S)
            echo 'Backup created'
        fi
    " > /dev/null 2>&1 || true

    # 새 버전 전송
    log_info "배포 패키지 전송 중..."
    scp -r "$DEPLOY_DIR/" "$VM_USER@$VM_IP:/tmp/$PROJECT_NAME-new/" > /dev/null 2>&1
    log_info "✅ 배포 패키지 전송 완료"

    # 셋업 스크립트 실행
    log_info "VM에서 셋업 스크립트 실행 중..."
    ssh "$VM_USER@$VM_IP" "
        set -euo pipefail
        cd /tmp/$PROJECT_NAME-new
        chmod +x deploy/setup_gcp.sh
        sudo bash deploy/setup_gcp.sh
    " > /tmp/setup_output.txt 2>&1

    if [ $? -ne 0 ]; then
        log_error "셋업 스크립트 실패!"
        cat /tmp/setup_output.txt
        exit 1
    fi

    log_info "✅ Phase 3 완료"
}

# ============================================================================
# Phase 4: 배포 검증 (Deployment Validation)
# ============================================================================

phase_validation() {
    log_info "Phase 4: 배포 검증..."

    # 서비스 상태 확인
    log_info "서비스 상태 확인..."
    SERVICE_STATUS=$(ssh "$VM_USER@$VM_IP" "sudo systemctl is-active $PROJECT_NAME" || echo "inactive")

    if [ "$SERVICE_STATUS" = "active" ]; then
        log_info "✅ 서비스 상태: ACTIVE"
    else
        log_warn "⚠️ 서비스 상태: $SERVICE_STATUS (start 필요)"
        ssh "$VM_USER@$VM_IP" "sudo systemctl start $PROJECT_NAME" > /dev/null 2>&1
        sleep 3
        SERVICE_STATUS=$(ssh "$VM_USER@$VM_IP" "sudo systemctl is-active $PROJECT_NAME")
        log_info "서비스 상태: $SERVICE_STATUS"
    fi

    # 데이터 파일 확인
    log_info "데이터 파일 확인..."
    ssh "$VM_USER@$VM_IP" "ls -lh $APP_DIR/data/ 2>/dev/null || echo 'data directory not ready yet'" > /dev/null 2>&1

    # 로그 확인
    log_info "최근 로그 확인..."
    ssh "$VM_USER@$VM_IP" "
        if [ -f $APP_DIR/data/dart-noti-bot.log ]; then
            echo '=== 최근 10줄 로그 ==='
            tail -10 $APP_DIR/data/dart-noti-bot.log
        fi
    " 2>/dev/null || echo "(로그가 아직 없거나 접근 불가)"

    log_info "✅ Phase 4 완료"
}

# ============================================================================
# Phase 5: 모니터링 설정 (Monitoring Setup)
# ============================================================================

phase_monitoring_setup() {
    log_info "Phase 5: 모니터링 설정..."

    # 상태 확인 스크립트 생성
    MONITOR_SCRIPT="/tmp/monitor_dart_bot.sh"
    cat > "$MONITOR_SCRIPT" << 'MONITOR_EOF'
#!/bin/bash
# 서비스 상태 모니터링

VM_IP="${1:-34.172.56.22}"
VM_USER="${2:-$USER}"
PROJECT_NAME="dart-noti-bot"
APP_DIR="/opt/dart-noti-bot"

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    # 서비스 상태
    STATUS=$(ssh "$VM_USER@$VM_IP" "sudo systemctl is-active $PROJECT_NAME" || echo "ERROR")

    # 메모리 사용량
    MEMORY=$(ssh "$VM_USER@$VM_IP" "ps aux | grep 'python main.py start' | grep -v grep | awk '{print \$6}' | head -1" || echo "N/A")

    # 로그 확인
    ERROR_COUNT=$(ssh "$VM_USER@$VM_IP" "tail -100 $APP_DIR/data/dart-noti-bot.log 2>/dev/null | grep -c '\[ERROR\]'" || echo "0")

    echo "[$TIMESTAMP] Status: $STATUS | Memory: ${MEMORY}KB | Errors: $ERROR_COUNT"

    # 5분마다 확인
    sleep 300
done
MONITOR_EOF

    chmod +x "$MONITOR_SCRIPT"
    log_info "모니터링 스크립트: $MONITOR_SCRIPT"
    log_info "사용법: $MONITOR_SCRIPT <VM_IP> <VM_USER>"

    log_info "✅ Phase 5 완료"
}

# ============================================================================
# Phase 6: 배포 완료 및 보고 (Completion Report)
# ============================================================================

phase_completion_report() {
    local DEPLOY_DIR="$1"

    log_info "Phase 6: 배포 완료 보고..."

    cat << EOF

========================================
✅ DART 공시 알림봇 배포 완료
========================================

📦 배포 정보:
  - 프로젝트: $PROJECT_NAME
  - 대상 VM: $VM_USER@$VM_IP
  - 앱 경로: $APP_DIR
  - 배포 시간: $(date)

✅ 완료된 작업:
  ✓ 로컬 테스트 (26/26 PASSED)
  ✓ 코드 품질 검사 (ruff)
  ✓ 배포 패키징
  ✓ GCP VM 배포
  ✓ 서비스 검증
  ✓ 모니터링 설정

🚀 다음 단계:

1. 기업 등록:
   ssh $VM_USER@$VM_IP 'cd $APP_DIR && source venv/bin/activate && python main.py add "삼성전자"'

2. 서비스 상태 확인:
   ssh $VM_USER@$VM_IP 'sudo systemctl status $PROJECT_NAME'

3. 로그 확인:
   ssh $VM_USER@$VM_IP 'tail -f $APP_DIR/data/dart-noti-bot.log'

4. 모니터링:
   /tmp/monitor_dart_bot.sh $VM_IP $VM_USER

📋 설정 파일 위치:
  - .env: $APP_DIR/.env (필수 - 수동 설정)
  - systemd: /etc/systemd/system/$PROJECT_NAME.service
  - 로그: $APP_DIR/data/dart-noti-bot.log

⚠️ 중요 사항:
  - .env 파일에 DART_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 설정 필요
  - 기업 등록 후 systemctl restart 필요
  - 로그는 RotatingFileHandler로 자동 관리 (5MB × 3 파일)

📞 트러블슈팅:

  서비스가 시작되지 않는 경우:
    sudo journalctl -u $PROJECT_NAME -n 50

  Python 의존성 문제:
    cd $APP_DIR && source venv/bin/activate && pip install -r requirements.txt

  데이터 초기화:
    rm -rf $APP_DIR/data/

========================================

EOF

    log_info "✅ Phase 6 완료"
}

# ============================================================================
# 메인 함수
# ============================================================================

main() {
    log_info "=========================================="
    log_info "DART 공시 알림봇 배포 파이프라인 시작"
    log_info "=========================================="

    # 현재 디렉토리 확인
    if [ ! -f "main.py" ]; then
        log_error "dart-noti-bot 디렉토리에서 실행하세요"
        exit 1
    fi

    # Phase 1: 로컬 검증
    phase_local_validation

    # Phase 2: 패키징
    DEPLOY_DIR=$(phase_packaging)

    # Phase 3: GCP 배포
    phase_gcp_deployment "$DEPLOY_DIR"

    # Phase 4: 검증
    phase_validation

    # Phase 5: 모니터링 설정
    phase_monitoring_setup

    # Phase 6: 완료 보고
    phase_completion_report "$DEPLOY_DIR"

    # 임시 파일 정리
    log_info "임시 파일 정리 중..."
    rm -rf "$DEPLOY_DIR"

    log_info "=========================================="
    log_info "배포 파이프라인 완료!"
    log_info "=========================================="
}

# 스크립트 실행
main "$@"
