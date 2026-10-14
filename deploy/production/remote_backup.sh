#!/usr/bin/env bash
# EduDSS pre-deploy backup, run ON the deployment host (C1.2).
#   bash remote_backup.sh <DEPLOY_PATH> <RUN_ID>
# Takes a pg_dump custom-format archive through the DB container's local socket (no
# password on any command line), writes a manifest in the ops/backup_recovery.py format
# (so `python -m ops.backup_recovery verify|restore --manifest ...` can consume it),
# verifies checksum + archive readability, and records the currently deployed image
# and Alembic revision so app and database can be rolled back together.
# Exit non-zero = the release must not proceed to migration.
set -euo pipefail
DEPLOY_PATH="$1"; RUN_ID="$2"
cd "$DEPLOY_PATH"
COMPOSE=(docker compose -f deploy/production/docker-compose.prod.yml --env-file deploy/production/production.env)
set -a; . deploy/production/production.env; set +a
BACKUP_DIR="${EDUDSS_BACKUP_DIR:-$DEPLOY_PATH/backups}"
mkdir -p "$BACKUP_DIR"; chmod 700 "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="${DB_NAME}-${STAMP}-predeploy-${RUN_ID}"
ARCHIVE="$BACKUP_DIR/$NAME.dump"
umask 077
"${COMPOSE[@]}" exec -T postgres pg_dump --format=custom --no-owner -U "$DB_OWNER_USER" -d "$DB_NAME" > "$ARCHIVE.partial"
[ -s "$ARCHIVE.partial" ] || { echo "empty archive"; rm -f "$ARCHIVE.partial"; exit 1; }
"${COMPOSE[@]}" exec -T postgres pg_restore --list < "$ARCHIVE.partial" > /dev/null
mv "$ARCHIVE.partial" "$ARCHIVE"
SHA="$(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
SIZE="$(stat -c %s "$ARCHIVE")"
REVISION="$("${COMPOSE[@]}" exec -T postgres psql -At -U "$DB_OWNER_USER" -d "$DB_NAME" -c 'SELECT version_num FROM alembic_version' 2>/dev/null || echo none)"
cat > "$BACKUP_DIR/$NAME.backup.json" <<JSON
{
  "archive": "$NAME.dump",
  "database": "$DB_NAME",
  "format": "pg_dump_custom",
  "sha256": "$SHA",
  "size_bytes": $SIZE,
  "timestamp_utc": "$STAMP",
  "predeploy": {"run_id": "$RUN_ID", "previous_image": "${EDUDSS_IMAGE:-}", "alembic_revision": "$REVISION"}
}
JSON
echo "{\"event\":\"predeploy_backup_verified\",\"archive\":\"$NAME.dump\",\"sha256\":\"$SHA\",\"size_bytes\":$SIZE,\"alembic_revision\":\"$REVISION\"}"
