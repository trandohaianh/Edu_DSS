#!/usr/bin/env bash
# Cập nhật EduDSS trên VM: backup (kèm diễn tập khôi phục) -> kéo code -> build -> chạy lại -> smoke test.
set -euo pipefail
APP_DIR="${APP_DIR:-$HOME/edudss}"
cd "$APP_DIR"
git fetch --prune origin
git reset --hard "origin/${DEPLOY_BRANCH:-main}"
cd app/deploy/cloud
set -a; . ./.env; set +a
sudo docker compose --env-file .env exec -T worker python -m ops.pipeline run backup >/dev/null || true
EDUDSS_GIT_SHA="$(git rev-parse --short HEAD)" sudo -E docker compose --env-file .env build edudss
sudo docker compose --env-file .env up -d edudss worker
for i in $(seq 1 60); do
  sudo docker compose --env-file .env exec -T edudss python -m dss.core.health_server probe livez >/dev/null 2>&1 && break
  sleep 5
done
bash ./smoke.sh "https://${EDUDSS_DOMAIN}"
