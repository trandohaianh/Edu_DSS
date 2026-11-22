#!/usr/bin/env bash
# EduDSS — sao lưu HẰNG NGÀY trên máy chủ production (bước 9, 22/11/2026).
#   bash deploy/production/scheduled_backup.sh <DEPLOY_PATH>
# Chạy bởi systemd timer (deploy/production/systemd/edudss-backup.timer, 02:30 giờ Việt Nam).
#
# Mỗi lần chạy tạo <BACKUP_DIR>/daily/<STAMP>/ gồm:
#   1. postgres/  : pg_dump (qua socket nội bộ của container postgres, không lộ mật khẩu) + manifest
#                   theo định dạng ops/backup_recovery.py (verify/restore --manifest dùng được ngay).
#   2. Diễn tập khôi phục CSDL: pg_restore vào một CSDL nháp trong chính container postgres, đếm số bảng
#                   và số bảng có RLS, rồi xoá CSDL nháp.
#   3. files/     : nén volume appdata (mô hình, bộ dữ liệu, kho JSON...) bằng chính image app
#                   (`python -m ops.pipeline run backup`), giải nén thử và kiểm SHA-256 từng tệp.
#   4. Xoá thư mục daily cũ hơn EDUDSS_BACKUP_KEEP_DAYS (mặc định 14 — quyết định chủ dự án 22/11/2026).
#   5. Bản sao ngoài máy chủ: CHƯA BẬT (quyết định 22/11/2026, chờ luật sư trả lời về chuyển dữ liệu). Khi bật,
#      đặt EDUDSS_BACKUP_OFFSITE_CMD — lệnh nhận đường dẫn thư mục ngày làm tham số và PHẢI tự mã hoá trước khi gửi.
# Kết quả cuối ghi vào <BACKUP_DIR>/last_status.json. Exit khác 0 = bản sao lưu hôm nay không dùng được.
#
# Mục tiêu tạm (chủ dự án chốt 22/11/2026): RPO 24 giờ, RTO 4 giờ. Cách khôi phục: docs/operations/BACKUP_RECOVERY_RUNBOOK.md.
set -euo pipefail
DEPLOY_PATH="${1:?usage: scheduled_backup.sh <DEPLOY_PATH>}"
cd "$DEPLOY_PATH"
ENV_FILE="${EDUDSS_ENV_FILE:-deploy/production/production.env}"
set -a; . "$ENV_FILE"; set +a

# Các lệnh chạm vào container — đổi được khi kiểm thử (tests/test_step9_scheduled_backup.py).
if [ -z "${EDUDSS_BACKUP_TEST_MODE:-}" ]; then
  COMPOSE=(docker compose -f deploy/production/docker-compose.prod.yml --env-file "$ENV_FILE")
  PG_EXEC=("${COMPOSE[@]}" exec -T postgres)
  files_backup() {  # $1 = thư mục đích trên máy chủ
    # Container app chạy bằng user hệ thống `edudss` (không phải root): cho user đó ghi vào thư mục đích.
    local ids
    ids="$("${COMPOSE[@]}" run --rm --no-deps -T --entrypoint sh app -c 'echo "$(id -u):$(id -g)"' | tr -d '\r')"
    chown "$ids" "$1"
    "${COMPOSE[@]}" run --rm --no-deps -T -e DATABASE_URL= -e EDUDSS_BACKUP_DIR=/backups \
      -v "$1:/backups" app python -m ops.pipeline run backup
  }
else
  read -r -a PG_EXEC <<< "$EDUDSS_BACKUP_TEST_PG_EXEC"
  files_backup() {  # Git Bash trên Windows: Python Windows cần đường dẫn C:\..., không phải /c/...
    local dir="$1"; if command -v cygpath >/dev/null 2>&1; then dir="$(cygpath -w "$1")"; fi
    EDUDSS_BACKUP_DIR="$dir" DATABASE_URL= "$EDUDSS_BACKUP_TEST_PYTHON" -m ops.pipeline run backup
  }
fi

BACKUP_DIR="${EDUDSS_BACKUP_DIR:-$DEPLOY_PATH/backups}"
KEEP_DAYS="${EDUDSS_BACKUP_KEEP_DAYS:-14}"
case "$KEEP_DAYS" in ''|*[!0-9]*) echo "EDUDSS_BACKUP_KEEP_DAYS must be a whole number" >&2; exit 2;; esac
[ "$KEEP_DAYS" -ge 1 ] || { echo "EDUDSS_BACKUP_KEEP_DAYS must be >= 1" >&2; exit 2; }

umask 077
mkdir -p "$BACKUP_DIR/daily"; chmod 700 "$BACKUP_DIR"
# Không cho hai lần chạy chồng nhau (timer + chạy tay).
if command -v flock >/dev/null 2>&1; then
  exec 9>"$BACKUP_DIR/.scheduled_backup.lock"
  flock -n 9 || { echo '{"event":"backup_skipped","reason":"another run in progress"}'; exit 0; }
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DAY_DIR="$BACKUP_DIR/daily/$STAMP"
mkdir -p "$DAY_DIR/postgres" "$DAY_DIR/files"
STATUS="failed"; STEP="start"
DRILL_DB=""
write_status() {
  if [ -n "$DRILL_DB" ] && declare -F drop_drill >/dev/null; then drop_drill; fi
  printf '{"status":"%s","step":"%s","stamp":"%s","dir":"%s","finished_utc":"%s"}\n' \
    "$STATUS" "$STEP" "$STAMP" "$DAY_DIR" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$BACKUP_DIR/last_status.json"
  if [ "$STATUS" != "ok" ]; then
    # Đổi tên để không ai nhầm thư mục dở dang là bản sao lưu dùng được; hạn giữ vẫn dọn nó như thường.
    mv "$DAY_DIR" "$DAY_DIR.FAILED" 2>/dev/null || true
    echo "{\"event\":\"backup_failed\",\"step\":\"$STEP\",\"dir\":\"$DAY_DIR.FAILED\"}" >&2
  fi
}
trap write_status EXIT

# 1. PostgreSQL
STEP="pg_dump"
NAME="${DB_NAME}-${STAMP}-daily"
ARCHIVE="$DAY_DIR/postgres/$NAME.dump"
"${PG_EXEC[@]}" pg_dump --format=custom --no-owner -U "$DB_OWNER_USER" -d "$DB_NAME" > "$ARCHIVE.partial"
[ -s "$ARCHIVE.partial" ] || { echo "empty archive" >&2; exit 1; }
"${PG_EXEC[@]}" pg_restore --list < "$ARCHIVE.partial" > /dev/null
mv "$ARCHIVE.partial" "$ARCHIVE"
SHA="$(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
SIZE="$(wc -c < "$ARCHIVE" | tr -d ' ')"
REVISION="$("${PG_EXEC[@]}" psql -At -U "$DB_OWNER_USER" -d "$DB_NAME" -c 'SELECT version_num FROM alembic_version' 2>/dev/null || echo none)"

# 2. Diễn tập khôi phục CSDL vào CSDL nháp (xoá ngay sau khi kiểm).
STEP="db_restore_drill"
DRILL_DB="edudss_drill_$(date -u +%Y%m%d%H%M%S)"
drop_drill() { "${PG_EXEC[@]}" dropdb -U "$DB_OWNER_USER" --if-exists "$DRILL_DB" >/dev/null 2>&1 || true; }
"${PG_EXEC[@]}" createdb -U "$DB_OWNER_USER" "$DRILL_DB"
"${PG_EXEC[@]}" pg_restore --no-owner --exit-on-error -U "$DB_OWNER_USER" -d "$DRILL_DB" < "$ARCHIVE"
COUNTS_SQL="SELECT count(*) || ' ' || count(*) FILTER (WHERE c.relrowsecurity) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'r' AND n.nspname = 'public'"
SRC="$("${PG_EXEC[@]}" psql -At -U "$DB_OWNER_USER" -d "$DB_NAME" -c "$COUNTS_SQL")"
DST="$("${PG_EXEC[@]}" psql -At -U "$DB_OWNER_USER" -d "$DRILL_DB" -c "$COUNTS_SQL")"
drop_drill; DRILL_DB=""
[ "$SRC" = "$DST" ] || { echo "restore drill mismatch: source tables/rls=$SRC restored=$DST" >&2; exit 1; }
# Manifest ghi sau diễn tập: kèm số bảng/bảng có RLS để restore_daily.sh đối chiếu.
cat > "$DAY_DIR/postgres/$NAME.backup.json" <<JSON
{
  "archive": "$NAME.dump",
  "database": "$DB_NAME",
  "format": "pg_dump_custom",
  "sha256": "$SHA",
  "size_bytes": $SIZE,
  "timestamp_utc": "$STAMP",
  "alembic_revision": "$REVISION",
  "tables_rls": "$DST"
}
JSON

# 3. Volume appdata (kèm diễn tập giải nén + kiểm SHA-256 trong ops.pipeline).
STEP="files_backup"
files_backup "$DAY_DIR/files" > "$DAY_DIR/files/pipeline_result.json"

# 4. Hạn giữ
STEP="retention"
find "$BACKUP_DIR/daily" -mindepth 1 -maxdepth 1 -type d -mtime +"$KEEP_DAYS" -exec rm -rf {} +

# 5. Bản sao ngoài máy chủ (chưa bật mặc định)
if [ -n "${EDUDSS_BACKUP_OFFSITE_CMD:-}" ]; then
  STEP="offsite"
  $EDUDSS_BACKUP_OFFSITE_CMD "$DAY_DIR"
fi

STEP="done"; STATUS="ok"
echo "{\"event\":\"daily_backup_verified\",\"dir\":\"$DAY_DIR\",\"db_sha256\":\"$SHA\",\"db_size_bytes\":$SIZE,\"alembic_revision\":\"$REVISION\",\"tables_rls\":\"$DST\",\"keep_days\":$KEEP_DAYS}"
