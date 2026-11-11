#!/usr/bin/env bash
# Провижининг чистого Ubuntu-сервера под Hostme: firewall + Webinoly (-php режим, без MySQL).
# Черновик ручного провижининга сервера по SSH: `hostme server init` делает это сам.
#
# Использование:
#   ./scripts/provision-server.sh <ssh-host-alias-или-user@host>
#
# Идемпотентен: повторный запуск не ломает уже настроенный сервер.

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Использование: $0 <ssh-host>" >&2
  exit 1
fi

TARGET="$1"

echo "==> Провижининг $TARGET"

ssh "$TARGET" bash -s <<'REMOTE_SCRIPT'
set -euo pipefail

echo "--- Firewall (ufw) ---"
if ! command -v ufw >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq ufw
fi

# Входящие порты по требованиям Webinoly (docs/webinoly.md):
# 22 SSH, 80/443 HTTP(S), 443/UDP (HTTP/3), 22222 админ-панель Webinoly.
# Исходящие (25, 587, 11371) не трогаем — ufw по умолчанию разрешает весь исходящий трафик.
ufw allow 22/tcp comment 'SSH' || true
ufw allow 80/tcp comment 'HTTP' || true
ufw allow 443/tcp comment 'HTTPS' || true
ufw allow 443/udp comment 'HTTP3' || true
ufw allow 22222/tcp comment 'Webinoly admin tools' || true

ufw default allow outgoing
ufw default deny incoming

if ! ufw status | grep -q "Status: active"; then
  ufw --force enable
fi
ufw status verbose

echo "--- Webinoly ---"
if command -v webinoly >/dev/null 2>&1 || [[ -d /opt/webinoly ]]; then
  echo "Webinoly уже установлен, пропускаю установку."
  webinoly -version || true
else
  cd /root
  wget -qO weby qrok.es/wy
  bash weby -php
fi

echo "--- SFTP для www-data ---"
webinoly -sftp=on || true

echo "==> Готово"
REMOTE_SCRIPT
