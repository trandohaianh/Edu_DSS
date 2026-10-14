#!/usr/bin/env bash
# FINAL REMEDIATION PASS Mục 7 — validate migration Alembic mới
# (9f3a1c7d2e46_rag_document_approval_workflow) và luồng governance/PgVectorStore
# đầy đủ trên một container PostgreSQL MỚI, CÔ LẬP HOÀN TOÀN khỏi mọi môi trường
# đang chạy (72h simulation, closure-C).
#
# AN TOÀN (đọc kỹ trước khi chạy):
# - Tên container/volume/network/port DUY NHẤT, KHÔNG trùng bất kỳ container nào
#   trong docker-compose.yml của repo này hay môi trường 72h simulation.
# - KHÔNG dùng `docker compose` của repo (container_name trong docker-compose.yml
#   là "edudss-postgres" — TRÙNG với container đang chạy thật của giả lập 72h,
#   dùng lại sẽ collide tên/có thể ảnh hưởng môi trường đang chạy). Script này
#   dùng `docker run` độc lập, không đụng tới docker-compose.yml.
# - Cổng 55599 (khác hẳn 55530 của giả lập 72h và 55461 của closure-C).
# - Script tự dọn dẹp (`docker rm -f` + xoá volume) ở cuối, kể cả khi lỗi giữa chừng.
#
# Chạy: bash tools/validate_migration_isolated_postgres.sh
# (Chỉ chạy khi đã xác nhận đủ tài nguyên Docker rảnh — xem REPORT.md Mục 7 để
# biết kết quả `docker stats`/`docker system df` đã kiểm tra trước đó.)
set -euo pipefail

CONTAINER_NAME="edudss-remediation-validation-postgres"
VOLUME_NAME="edudss_remediation_validation_pgdata"
PORT=55599
DB_NAME="edudss_validation"
DB_USER="edudss_validation"
DB_PASSWORD="validation_only_$(date +%s)"

cleanup() {
    echo "--- Dọn dẹp: xoá container + volume cô lập ---"
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    docker volume rm "$VOLUME_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "--- Kiểm tra không trùng tên/cổng với container đang chạy ---"
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    echo "Container '$CONTAINER_NAME' đã tồn tại từ lần chạy trước — xoá trước khi tiếp tục."
    docker rm -f "$CONTAINER_NAME"
fi
if docker ps --format '{{.Ports}}' | grep -q ":$PORT->"; then
    echo "LỖI: cổng $PORT đang bị chiếm bởi container khác — dừng, không chạy tiếp." >&2
    exit 1
fi

echo "--- Khởi động container PostgreSQL cô lập ($CONTAINER_NAME, cổng $PORT) ---"
docker run -d \
    --name "$CONTAINER_NAME" \
    -e POSTGRES_DB="$DB_NAME" \
    -e POSTGRES_USER="$DB_USER" \
    -e POSTGRES_PASSWORD="$DB_PASSWORD" \
    -p "127.0.0.1:${PORT}:5432" \
    -v "${VOLUME_NAME}:/var/lib/postgresql/data" \
    pgvector/pgvector:pg16

echo "--- Đợi PostgreSQL sẵn sàng ---"
for i in $(seq 1 30); do
    if docker exec "$CONTAINER_NAME" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
        echo "PostgreSQL sẵn sàng sau ${i}s."
        break
    fi
    sleep 1
done

export DATABASE_URL="postgresql+psycopg2://${DB_USER}:${DB_PASSWORD}@127.0.0.1:${PORT}/${DB_NAME}"
export PGVECTOR_URL="$DATABASE_URL"

echo "--- Bật extension pgvector ---"
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "--- Chạy alembic upgrade head (áp toàn bộ 9 migration, gồm migration mới) ---"
python -m alembic upgrade head

echo "--- Xác nhận cột mới trên rag_documents ---"
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -c "\d rag_documents" | grep -E "doc_type|issuer|official_ref|status|approved_by|approved_at|review_note|content_hash|effective_from|expires_at"

echo "--- Chạy bộ test cần DATABASE_URL thật (trước đây SKIP vì thiếu DB) ---"
LOKY_MAX_CPU_COUNT=2 OMP_NUM_THREADS=2 PYTHONIOENCODING=utf-8 \
    python -m pytest tests -q -k "postgres or pgvector or db_" --ignore=tests/e2e --ignore=tests/load

echo "--- HOÀN TẤT — xem log ở trên để biết kết quả thật (migration + test DB) ---"
