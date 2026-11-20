#!/usr/bin/env bash
# Cài EduDSS lên VM (chạy 2 lần: lần 1 tạo .env có bí mật tự sinh; lần 2 build + chạy + nối Caddy).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
rand() { openssl rand -hex "${1:-24}"; }

if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s|^EDUDSS_AUTH_COOKIE_SECRET=.*|EDUDSS_AUTH_COOKIE_SECRET=$(rand 32)|" .env
  sed -i "s|^EDUDSS_BOOTSTRAP_ADMIN_PASSWORD=.*|EDUDSS_BOOTSTRAP_ADMIN_PASSWORD=$(rand 12)|" .env
  sed -i "s|^EDUDSS_METRICS_TOKEN=.*|EDUDSS_METRICS_TOKEN=$(rand 24)|" .env
  chmod 600 .env
  log "Đã tạo deploy/cloud/.env. Điền EDUDSS_DOMAIN, EDUDSS_PUBLIC_URL, Google client rồi chạy lại script này."
  exit 0
fi
set -a; . ./.env; set +a
: "${EDUDSS_DOMAIN:?Điền EDUDSS_DOMAIN trong .env}"
[ -n "${EDUDSS_PUBLIC_URL:-}" ] || { sed -i "s|^EDUDSS_PUBLIC_URL=.*|EDUDSS_PUBLIC_URL=https://${EDUDSS_DOMAIN}|" .env; export EDUDSS_PUBLIC_URL="https://${EDUDSS_DOMAIN}"; }

log "1/4 Mạng docker dùng chung"
sudo docker network inspect edge >/dev/null 2>&1 || sudo docker network create edge
sed "s|__DOMAIN__|${EDUDSS_DOMAIN}|g" edudss.caddy > edudss.caddy.generated

log "2/4 Build image (lần đầu trên ARM mất ~15-25 phút: PyTorch, LightGBM...)"
EDUDSS_GIT_SHA="$(git -C ../.. rev-parse --short HEAD 2>/dev/null || echo unknown)" \
  sudo -E docker compose --env-file .env build edudss

log "3/4 Chạy app + worker"
if sudo docker ps --format '{{.Names}}' | grep -q '^fieldops-caddy-1$'; then
  sudo docker compose --env-file .env up -d edudss worker
  sudo mkdir -p /opt/edge/sites
  sudo cp edudss.caddy.generated /opt/edge/sites/edudss.caddy
  sudo docker exec fieldops-caddy-1 caddy reload --config /etc/caddy/Caddyfile
  echo "Đã nối vào Caddy của FieldOps (/opt/edge/sites/edudss.caddy)."
else
  sudo docker compose --env-file .env --profile standalone up -d
  echo "Không thấy Caddy của FieldOps: chạy Caddy riêng (profile standalone)."
fi

log "4/4 Smoke test"
for i in $(seq 1 60); do
  sudo docker compose --env-file .env exec -T edudss python -m dss.core.health_server probe livez >/dev/null 2>&1 && break
  sleep 5
done
bash ./smoke.sh "https://${EDUDSS_DOMAIN}"
echo
echo "Xong: https://${EDUDSS_DOMAIN}  — Admin: ${EDUDSS_BOOTSTRAP_ADMIN_USER} / (EDUDSS_BOOTSTRAP_ADMIN_PASSWORD trong .env)"
