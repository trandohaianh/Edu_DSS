#!/usr/bin/env bash
# EduDSS — khôi phục CSDL + volume appdata từ MỘT bản sao lưu hằng ngày (bước 9, 22/11/2026).
#   bash deploy/production/restore_daily.sh <DEPLOY_PATH> <backups/daily/<giờ>> [--replace]
#
# Dùng khi máy chủ mất dữ liệu (ổ hỏng, xoá nhầm volume, dữ liệu bị phá) và cần đưa hệ thống về đúng một ngày.
# Khôi phục CSDL và thư mục tệp CỦA CÙNG MỘT NGÀY (metadata mô hình trong tệp phải khớp CSDL).
#   1. Kiểm SHA-256 của bản dump CSDL và bản nén tệp TRƯỚC khi đụng vào dữ liệu đang chạy.
#   2. Dừng proxy + app (không ai ghi trong lúc khôi phục).
#   3. CSDL: chỉ ghi vào CSDL RỖNG. CSDL đang có bảng thì từ chối, trừ khi có --replace (xoá rồi tạo lại).
#      pg_restore một giao dịch, dừng ở lỗi đầu tiên; so số bảng/bảng có RLS với lúc sao lưu.
#   4. Tệp: python -m ops.restore_appdata (từ chối thư mục đang có dữ liệu nếu không có --replace).
#   5. Bật lại migrate + app + proxy, chờ MỌI bản app qua /readyz.
# --replace XOÁ dữ liệu hiện tại. Trước khi dùng, nếu còn đọc được dữ liệu hiện tại thì chạy scheduled_backup.sh
# một lần để giữ lại bản hiện trạng. Hướng dẫn: docs/operations/BACKUP_RECOVERY_RUNBOOK.md.
set -euo pipefail
DEPLOY_PATH="${1:?usage: restore_daily.sh <DEPLOY_PATH> <DAY_DIR> [--replace]}"
DAY_DIR="${2:?usage: restore_daily.sh <DEPLOY_PATH> <DAY_DIR> [--replace]}"
REPLACE="${3:-}"
case "$REPLACE" in ''|--replace) ;; *) echo "unknown option: $REPLACE" >&2; exit 2;; esac
cd "$DEPLOY_PATH"
DAY_DIR="$(cd "$DAY_DIR" && pwd)"
case "$DAY_DIR" in *.FAILED) echo "refusing a FAILED backup: $DAY_DIR" >&2; exit 2;; esac
ENV_FILE="${EDUDSS_ENV_FILE:-deploy/production/production.env}"
set -a; . "$ENV_FILE"; set +a
COMPOSE=(docker compose -f deploy/production/docker-compose.prod.yml --env-file "$ENV_FILE")
PG=("${COMPOSE[@]}" exec -T postgres)
START="$(date +%s)"
log() { echo "{\"event\":\"$1\",\"elapsed_s\":$(( $(date +%s) - START ))${2:+,$2}}"; }

# 1. Kiểm bản sao lưu
MANIFEST="$(ls "$DAY_DIR"/postgres/*.backup.json 2>/dev/null | head -1 || true)"
[ -n "$MANIFEST" ] || { echo "no database manifest in $DAY_DIR/postgres" >&2; exit 1; }
field() { sed -n "s/^ *\"$1\": *\"\{0,1\}\([^\",]*\)\"\{0,1\},\{0,1\}$/\1/p" "$MANIFEST"; }
ARCHIVE="$DAY_DIR/postgres/$(field archive)"
[ "$(sha256sum "$ARCHIVE" | cut -d' ' -f1)" = "$(field sha256)" ] || { echo "database dump checksum mismatch" >&2; exit 1; }
EXPECTED_TABLES_RLS="$(field tables_rls)"
[ -n "$(ls "$DAY_DIR"/files/*/data_root.tar.gz 2>/dev/null)" ] || { echo "no file backup in $DAY_DIR/files" >&2; exit 1; }
log restore_backup_checked "\"day\":\"$(basename "$DAY_DIR")\",\"alembic_revision\":\"$(field alembic_revision)\""

# 2. Dừng ghi
"${COMPOSE[@]}" stop proxy app >/dev/null 2>&1 || true
"${COMPOSE[@]}" up -d postgres >/dev/null
# Qua TCP, không qua socket (xem healthcheck postgres trong docker-compose.prod.yml).
for _ in $(seq 1 90); do "${PG[@]}" pg_isready -h 127.0.0.1 -U "$DB_OWNER_USER" -d postgres >/dev/null 2>&1 && break; sleep 2; done

# 3. CSDL
db_exists="$("${PG[@]}" psql -At -U "$DB_OWNER_USER" -d postgres -c "SELECT count(*) FROM pg_database WHERE datname = '$DB_NAME'" | tr -d '\r')"
if [ "$db_exists" = "1" ]; then
  tables="$("${PG[@]}" psql -At -U "$DB_OWNER_USER" -d "$DB_NAME" -c "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'" | tr -d '\r')"
else
  tables=0
fi
if [ "$tables" != "0" ] || [ "$db_exists" != "1" ]; then
  if [ "$tables" != "0" ] && [ "$REPLACE" != "--replace" ]; then
    echo "database $DB_NAME already has $tables tables; re-run with --replace to drop and replace it" >&2; exit 1
  fi
  "${PG[@]}" dropdb -U "$DB_OWNER_USER" --if-exists --force "$DB_NAME"
  "${PG[@]}" createdb -U "$DB_OWNER_USER" "$DB_NAME"
  # Quyền vào CSDL cho role app (postgres-init/01-app-role.sh chỉ chạy khi volume còn rỗng).
  "${PG[@]}" psql -q -v ON_ERROR_STOP=1 -U "$DB_OWNER_USER" -d "$DB_NAME" \
    -c "GRANT CONNECT ON DATABASE \"$DB_NAME\" TO \"$DB_APP_USER\"" >/dev/null
fi
"${PG[@]}" pg_restore --no-owner --exit-on-error --single-transaction -U "$DB_OWNER_USER" -d "$DB_NAME" < "$ARCHIVE"
COUNTS_SQL="SELECT count(*) || ' ' || count(*) FILTER (WHERE c.relrowsecurity) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'r' AND n.nspname = 'public'"
GOT="$("${PG[@]}" psql -At -U "$DB_OWNER_USER" -d "$DB_NAME" -c "$COUNTS_SQL" | tr -d '\r')"
if [ -n "$EXPECTED_TABLES_RLS" ] && [ "$GOT" != "$EXPECTED_TABLES_RLS" ]; then
  echo "restored tables/rls=$GOT, backup had $EXPECTED_TABLES_RLS" >&2; exit 1
fi
log restore_database_done "\"tables_rls\":\"$GOT\""

# 4. Tệp
HOST_FILES="$DAY_DIR/files"
# Git Bash trên Windows (diễn tập trên máy dev): Docker Desktop cần C:/..., không hiểu /c/...
if command -v cygpath >/dev/null 2>&1; then HOST_FILES="$(cygpath -m "$HOST_FILES")"; fi
"${COMPOSE[@]}" run --rm --no-deps -T -v "$HOST_FILES:/restore:ro" app \
  python -m ops.restore_appdata /restore ${REPLACE:+--replace}
log restore_files_done

# 5. Bật lại
"${COMPOSE[@]}" run --rm migrate
"${COMPOSE[@]}" up -d --no-deps app
"${COMPOSE[@]}" up -d proxy
REPLICAS="${EDUDSS_APP_REPLICAS:-3}"
for _ in $(seq 1 60); do
  ready=0
  for i in $(seq 1 "$REPLICAS"); do
    if "${COMPOSE[@]}" exec -T --index "$i" app python -m dss.core.health_server probe readyz >/dev/null 2>&1; then
      ready=$((ready + 1))
    fi
  done
  if [ "$ready" -eq "$REPLICAS" ]; then log restore_ready "\"replicas\":$REPLICAS"; exit 0; fi
  sleep 5
done
log restore_not_ready "\"replicas\":$REPLICAS"
exit 1
