# PostgreSQL backup and recovery runbook

This procedure covers the PostgreSQL database, including pgvector columns in
`rag_chunks`, schema, indexes, constraints, RLS policies, ACLs, and Alembic
revision. It does **not** cover file-based model artifacts, datasets, CMS
uploads, JSON runtime stores, secrets, or off-site disaster recovery.

> Bước 9 (22/11/2026): sao lưu hằng ngày cả CSDL **và** volume tệp `appdata` trên máy chủ production, kèm diễn tập
> khôi phục: xem mục "Sao lưu hằng ngày trên máy chủ production" ở cuối tệp.

On the accepted Phase 1C architecture (Alembic `797f72d1c666`, 27 public
tables), PostgreSQL mode also covers users/authentication, user-facing
activity history, AI token usage and per-organization admin AI provider/model
configuration. API keys remain external secrets and are never DB payloads.

## Prerequisites

- PostgreSQL client utilities `pg_dump`, `pg_restore`, and `psql` compatible
  with the server, or a PostgreSQL database container containing them.
- A role allowed to dump the complete source and create schema/extension,
  policies and grants in a **separate empty** restore database.
- The application non-superuser role must already exist on the target server.
  Its grants are included in the archive, but PostgreSQL roles are cluster
  objects and are not created by a database dump.
- The pgvector extension package must be installed on the target server.
- A private backup directory on storage outside the repository, with
  restricted OS permissions, encryption at rest, and off-site replication
  arranged by operations. The script creates POSIX files with mode 0600 and
  a new directory with mode 0700; verify Windows ACLs separately.
- Set `DATABASE_URL` in the process environment. For restore also set
  `RESTORE_DATABASE_URL`. Do not put real credentials in shell history,
  command arguments, filenames, logs, or Git.

The local `--docker-container` mode runs PostgreSQL tools over the database
container's local socket. It uses the user/database components of the URLs,
not their host/port, and requires local socket authentication configured in
that container. It never passes a password to `docker exec -e`. For a remote
server, omit the flag and install client tools on the operator host.

## Backup and verify

From `app/`:

```sh
python ops/backup_recovery.py backup --dir /secure/edudss-backups
python ops/backup_recovery.py verify --manifest /secure/edudss-backups/NAME.backup.json
```

For the local Docker PostgreSQL service:

```sh
python ops/backup_recovery.py --docker-container DB_CONTAINER backup --dir backups
python ops/backup_recovery.py verify --manifest backups/NAME.backup.json
```

The backup command emits a timestamp, database identifier, elapsed time,
size and SHA-256, then creates a custom-format `.dump` and matching
`.backup.json` manifest. Both are sensitive and must travel together.
`app/backups/`, `*.dump`, and `*.backup.json` are Git-ignored. Store the
archive on encrypted, access-controlled, off-site storage; no operational
schedule or replication is configured by this phase.

## Restore into a clean, separate database

1. Declare an incident, stop writes or establish a consistent recovery
   point, and select the manifest. Keep the source database intact.
2. Create a **new empty database** with a different name. For local Docker,
   an operator can use `docker exec DB_CONTAINER createdb -U DB_OWNER NEW_DB`.
   Never run this against a database that contains business data.
3. Ensure the target server has the pgvector extension package and the
   application role. Set `RESTORE_DATABASE_URL` to the new database.
4. Run:

   ```sh
   python ops/backup_recovery.py restore --manifest /secure/edudss-backups/NAME.backup.json
   # Local database-container mode:
   python ops/backup_recovery.py --docker-container DB_CONTAINER restore --manifest backups/NAME.backup.json
   ```

   The script validates SHA-256 and size **before** connecting to the target,
   refuses matching source/target database names, refuses a target with user
   tables, and invokes `pg_restore --exit-on-error --single-transaction`.
   Failed restore returns non-zero. The script never drops or creates a DB.

5. Compare source and target tables/counts and deterministic records. Current
   Phase 1C recovery expects 27 public tables. Check
   `SELECT version_num FROM alembic_version` against the source/current
   migration head; do **not** blindly rerun migrations over the restored
   schema. Check `pg_policies`, `pg_class.relrowsecurity`, and
   `pg_class.relforcerowsecurity`.
6. Connect as the **non-superuser** application role. Set
   `SET LOCAL app.organization_id = '<tenant-id>'` inside each transaction.
   Confirm A sees only A, B sees only B, and cross-tenant UPDATE/DELETE
   affect zero rows while cross-tenant INSERT is rejected.
   Include real reads and cross-tenant write attempts for `users`,
   `activity_logs`, `ai_token_usage`, and `admin_ai_config`.
7. Query `vector_dims(embedding)` and run a real `PgVectorStore.search()`
   against known vectors. Compare ranking and document metadata with source.
8. Enable PostgreSQL identity and set the server-controlled organization ID.
   Authenticate a restored active test account through
   `auth_service.authenticate()`; verify wrong-password failure, role and
   organization. Never print the password/hash/salt.
9. Start a test application instance with `DATABASE_URL` pointing to the
   restored DB and the non-superuser role. Check HTTP 200,
   `/_stcore/health`, `readiness()` with pgvector required, and reads through
   the application repositories. Do not switch production traffic based on
   liveness alone.
10. Restore file-based artifacts and JSON/CMS/dataset state from their
   **separate** protected backups before full service cutover; this phase
   does not supply those backups. Check each model binary's SHA-256 and
   registry/version linkage; the DB only contains artifact paths/metadata.
11. If verification fails, keep traffic on the original database, preserve
    the failed target and logs for analysis, and escalate to the DB operator.
    Never overwrite the source to retry.

The real integration proof is `tests/test_backup_recovery_integration.py`.
It requires dedicated migrated source and empty target URLs via
`PHASE13_SOURCE_URL`, `PHASE13_RESTORE_URL`, `PHASE13_APP_ROLE_URL`, plus
optional `PHASE13_DOCKER_CONTAINER`. It creates only synthetic records and
does not drop databases.

## Retention and objectives

Example daily backup retention of 14 days is a **target policy**, not an
active schedule:

```sh
python ops/backup_recovery.py retention --dir /secure/edudss-backups --days 14
python ops/backup_recovery.py retention --dir /secure/edudss-backups --days 14 --execute
```

The first command is a dry-run. Execution only removes verified expired
archive/manifest pairs inside the configured real directory; symlink paths
and invalid pairs are refused/skipped. Review the selected list first.
Automation, monitoring, off-site replication, encryption/key management and
periodic restore drills must be configured and tested by operations before
claiming a service-level RPO/RTO.

Provisional target RPO: 24 hours **if** daily backups run successfully.
Provisional target RTO: 4 hours **if** database and external file restores
are operationalized. Neither is an SLA. The small synthetic DB restore timing
in the Phase 13 report is evidence for this fixture only.

## Sao lưu hằng ngày trên máy chủ production (bước 9, 22/11/2026)

Chủ dự án chốt ngày 22/11/2026:
- **RPO 24 giờ / RTO 4 giờ** (mức tạm, chưa phải cam kết dịch vụ).
- Giữ bản sao lưu **14 ngày**.
- **Chưa gửi bản sao ra ngoài máy chủ**, chờ luật sư trả lời câu hỏi chuyển dữ liệu (`docs/legal/PRIVACY_NOTICE_DRAFT.md`).

Hệ quả: nếu **cả máy chủ** hỏng (mất ổ đĩa), bản sao lưu mất theo. Đây là rủi ro đã được chấp nhận trong thời gian chờ.

`deploy/production/scheduled_backup.sh` chạy mỗi đêm lúc 02:30 giờ Việt Nam và tạo `backups/daily/<giờ UTC>/`:

| Phần | Nội dung | Kiểm tra ngay khi tạo |
|---|---|---|
| `postgres/*.dump` + `*.backup.json` | `pg_dump` toàn bộ CSDL, manifest theo định dạng `ops/backup_recovery.py` | Kiểm SHA-256; khôi phục thật vào CSDL nháp `edudss_drill_*`, so số bảng và số bảng có RLS với CSDL gốc, rồi xoá CSDL nháp |
| `files/<giờ>/data_root.tar.gz` + `manifest.json` | Volume `appdata`: mô hình, bộ dữ liệu, metadata, lịch sử, kho JSON (nhật ký token AI, CMS...). Bỏ qua `logs/`, `security/`, `locks/`, tệp `.lock` và tệp có tên chứa secret/credential | Giải nén vào thư mục tạm, kiểm SHA-256 từng tệp |
| `last_status.json` | `ok` hoặc `failed` và bước bị hỏng | — |

Lần chạy hỏng thì thư mục ngày được đổi tên thành `<giờ>.FAILED`, script trả mã lỗi khác 0, và systemd ghi lỗi vào
`journalctl -u edudss-backup`. Kết quả phần tệp cũng hiện ở **Báo cáo & giám sát → Pipeline vận hành**.

### Cài đặt (một lần, quyền root)

```sh
cp deploy/production/systemd/edudss-backup.service deploy/production/systemd/edudss-backup.timer /etc/systemd/system/
# sửa /opt/edudss trong edudss-backup.service nếu thư mục triển khai khác
systemctl daemon-reload
systemctl enable --now edudss-backup.timer
systemctl start edudss-backup.service      # chạy thử ngay một lần
cat /opt/edudss/backups/last_status.json   # phải là "status":"ok"
```

Biến môi trường (trong `production.env`, đều có giá trị mặc định):
- `EDUDSS_BACKUP_DIR`: thư mục sao lưu, mặc định `<DEPLOY_PATH>/backups`.
- `EDUDSS_BACKUP_KEEP_DAYS`: số ngày giữ, mặc định `14`.
- `EDUDSS_BACKUP_OFFSITE_CMD`: lệnh gửi bản sao ra ngoài. Để trống thì không gửi. Khi bật, lệnh nhận đường dẫn thư mục
  ngày làm tham số và **phải tự mã hoá** trước khi gửi.

### Khôi phục (một lệnh)

Dùng khi máy chủ mất dữ liệu (ổ hỏng, xoá nhầm volume, dữ liệu bị phá) và cần đưa **cả CSDL lẫn thư mục tệp** về
cùng một ngày. Metadata mô hình trong tệp phải khớp với CSDL, nên không khôi phục lệch ngày.

```sh
cd /opt/edudss
ls backups/daily/                                  # chọn ngày; bỏ qua thư mục *.FAILED
bash deploy/production/restore_daily.sh /opt/edudss backups/daily/<giờ>             # máy chủ mới / volume rỗng
bash deploy/production/restore_daily.sh /opt/edudss backups/daily/<giờ> --replace   # GHI ĐÈ dữ liệu đang có
```

Script làm theo thứ tự:
1. Kiểm SHA-256 bản dump và bản nén **trước** khi đụng vào dữ liệu đang chạy. Từ chối thư mục `*.FAILED`.
2. Dừng proxy và app, để không ai ghi trong lúc khôi phục.
3. CSDL: chỉ ghi vào CSDL rỗng. Nếu CSDL đang có bảng mà thiếu `--replace` thì dừng, không xoá gì. Có `--replace` thì
   xoá CSDL rồi tạo lại. `pg_restore` chạy trong một giao dịch và dừng ở lỗi đầu tiên. Sau đó so số bảng và số bảng có
   RLS với số ghi trong manifest lúc sao lưu.
4. Tệp: `python -m ops.restore_appdata` (từ chối thư mục đang có dữ liệu nếu thiếu `--replace`), kiểm lại SHA-256
   **từng tệp** sau khi chép.
5. Chạy migrate (chỉ kiểm, CSDL đã ở đúng phiên bản), bật app và proxy, chờ **mọi** bản app qua `/readyz`.

Mỗi bước in một dòng JSON có `elapsed_s`. Exit khác 0 thì **không** mở lại cho người dùng. Đọc dòng lỗi, sửa nguyên
nhân, rồi chạy lại. Script không bao giờ xoá thư mục sao lưu.

**Trước khi dùng `--replace`:** nếu dữ liệu hiện tại còn đọc được, chạy `scheduled_backup.sh` một lần để giữ lại hiện
trạng. Mọi thay đổi sau thời điểm sao lưu được chọn sẽ mất (RPO tối đa 24 giờ).

Muốn khôi phục sang một CSDL **khác tên** để so sánh mà không đụng bản đang chạy, dùng mục "Restore into a clean,
separate database" ở trên với `--manifest backups/daily/<giờ>/postgres/<tên>.backup.json`.

### Kết quả diễn tập khôi phục (máy dev, 22/11/2026)

Chạy bằng image production build từ mã nguồn (`docker build`, cùng Dockerfile với bản phát hành), đúng
`docker-compose.prod.yml` với 2 bản app và Caddy, dự án Docker riêng `edudss-drill`.

Dữ liệu mẫu: 301 tài khoản, 1 tổ chức, 1 bộ dữ liệu 20.000 dòng, 50 bản ghi nhật ký AI và hoạt động, 1 tệp mô hình 5 MB.

| Bước | Kết quả |
|---|---|
| Sao lưu thật (`scheduled_backup.sh`, không ở chế độ thử) khi app đang chạy | 30 giây, `status: ok`, 55 bảng / 50 RLS |
| **Mất sạch** (xoá cả volume CSDL và volume tệp) → `restore_daily.sh` | **54 giây** đến khi cả 2 bản app qua `/readyz` |
| **Dữ liệu bị phá** (xoá 100 tài khoản, ghi đè tệp mô hình) → `restore_daily.sh --replace` | **53 giây** |
| Thiếu `--replace` khi CSDL đang có 55 bảng | Từ chối, không xoá gì |
| So "dấu vân tay" trước/sau: số dòng + md5 từng bảng, RLS, SHA-256 từng tệp | **Khớp hoàn toàn** cả 2 lần (64 dòng) |
| Đăng nhập bằng role app (RLS bật) sau khôi phục | Đúng mật khẩu: vào được, đúng vai trò. Sai mật khẩu: bị từ chối |
| HTTPS qua Caddy (`/_stcore/health`) | 200 |

**Lỗi tìm thấy nhờ diễn tập (đã sửa):** trên volume rỗng, PostgreSQL chạy một bản tạm chỉ nghe socket để chạy
`postgres-init`, rồi mới khởi động lại. `pg_isready` qua socket báo "sẵn sàng" ngay khi bản tạm còn chạy, nên lệnh
tiếp theo gặp lỗi `the database system is starting up`. Lỗi này cũng có trong healthcheck của cả hai tệp compose:
**lần triển khai đầu tiên** trên máy chủ mới có thể hỏng ở bước migrate. Đã sửa bằng cách kiểm qua TCP
(`pg_isready -h 127.0.0.1`).

**Ước tính cho thí điểm:** CSDL cỡ thí điểm 124 MB (bước 8) khôi phục mất 17 giây. Cộng thời gian dựng máy chủ mới và
chép thư mục sao lưu về máy đó, vẫn nằm trong mục tiêu **RTO 4 giờ**. Riêng việc dựng lại máy chủ khi mất cả máy chưa
diễn tập được, vì chưa có máy chủ thí điểm, và vì bản sao lưu hiện chỉ nằm trên chính máy chủ đó.
