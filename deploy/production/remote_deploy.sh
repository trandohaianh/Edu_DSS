#!/usr/bin/env bash
# EduDSS deploy of ONE immutable image, run ON the deployment host (C1.2).
#   bash remote_deploy.sh <IMAGE@sha256:...> <DEPLOY_PATH>
# 1. pin EDUDSS_IMAGE in production.env (previous value kept in .release-history)
# 2. pull the exact digest
# 3. migration service: precheck (refuses unknown/newer revision) -> upgrade -> verify
# 4. start app on the same digest; wait for /readyz (never depends on optional AI)
# Rollback of the app = run this script again with the previous digest from
# .release-history (see docs/operations/RELEASE_PROCESS.md; DB rollback = restore the
# pre-deploy backup, because downgrade migrations drop data).
set -euo pipefail
IMAGE="$1"; DEPLOY_PATH="$2"
case "$IMAGE" in *@sha256:*) ;; *) echo "refusing mutable image reference: $IMAGE"; exit 2;; esac
cd "$DEPLOY_PATH"
ENV_FILE=deploy/production/production.env
COMPOSE=(docker compose -f deploy/production/docker-compose.prod.yml --env-file "$ENV_FILE")
PREVIOUS="$(sed -n 's/^EDUDSS_IMAGE=//p' "$ENV_FILE")"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) previous=${PREVIOUS:-none} next=$IMAGE" >> .release-history
if grep -q '^EDUDSS_IMAGE=' "$ENV_FILE"; then
  sed -i "s|^EDUDSS_IMAGE=.*|EDUDSS_IMAGE=$IMAGE|" "$ENV_FILE"
else
  echo "EDUDSS_IMAGE=$IMAGE" >> "$ENV_FILE"
fi
"${COMPOSE[@]}" pull migrate app
"${COMPOSE[@]}" up -d postgres
"${COMPOSE[@]}" run --rm migrate
"${COMPOSE[@]}" up -d --no-deps app
"${COMPOSE[@]}" up -d proxy
for attempt in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T app python -m dss.core.health_server probe readyz > /tmp/edudss-readyz.json; then
    echo "{\"event\":\"deploy_ready\",\"image\":\"$IMAGE\"}"; exit 0
  fi
  sleep 5
done
cat /tmp/edudss-readyz.json || true
echo "{\"event\":\"deploy_not_ready\",\"image\":\"$IMAGE\",\"previous\":\"${PREVIOUS:-none}\"}"
exit 1
