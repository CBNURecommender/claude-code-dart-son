#!/bin/bash
# DART noti bot external healthcheck — alerts via telegram if the bot
# heartbeat is stale or the systemd service is inactive.
set -euo pipefail

HEARTBEAT=/opt/dart-noti-bot/data/heartbeat.txt
STATE=/opt/dart-noti-bot/data/healthcheck_state.txt
ENV_FILE=/opt/dart-noti-bot/.env
MAX_AGE_SECONDS=600   # 10 minutes

# Load telegram credentials
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

alert() {
    local msg="$1"
    curl -sS -X POST \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=${msg}" > /dev/null || true
}

set_state() {
    echo "$1" > "$STATE"
}

current_state() {
    [[ -f "$STATE" ]] && cat "$STATE" || echo "ok"
}

now=$(date +%s)

# First: is the service even active?
if ! systemctl is-active --quiet dart-noti-bot.service; then
    if [[ "$(current_state)" != "service_down" ]]; then
        alert "🚨 DART 봇 비상: systemd 서비스가 비활성 상태입니다. 즉시 확인 필요."
        set_state "service_down"
    fi
    exit 0
fi

# Service is active; check heartbeat
if [[ ! -f "$HEARTBEAT" ]]; then
    # Fresh start; give it time
    exit 0
fi

hb=$(cat "$HEARTBEAT")
age=$((now - hb))

if (( age > MAX_AGE_SECONDS )); then
    if [[ "$(current_state)" != "stale" ]]; then
        alert "🚨 DART 봇 비상: 마지막 폴링 $((age / 60))분 전. 프로세스가 멈춘 것 같습니다. 로그 확인: journalctl -u dart-noti-bot -n 100"
        set_state "stale"
    fi
else
    if [[ "$(current_state)" != "ok" ]]; then
        alert "✅ DART 봇 복구: 정상 폴링 재개."
        set_state "ok"
    fi
fi
