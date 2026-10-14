# Canonicalization Plan — EduDSS Worktree/Branch Inventory

**Trạng thái: KẾ HOẠCH THAM KHẢO, CHƯA THỰC THI.** Không worktree/branch nào bị xóa, không `git clean`, không `git stash` trong quá trình lập kế hoạch này. Danh sách dưới đây liệt kê từ `git worktree list` chạy tại `D:\KLTN\edudss-final-candidate-v2` (nhánh `fix/ml-correctness`, commit `a62264e`) ngày 2026-09-25/26.

**Phạm vi đã xác minh**: chỉ commit HEAD + tên nhánh của từng worktree (qua `git log -1`). **CHƯA đọc nội dung/diff chi tiết của từng worktree** — quyết định keep/archive/remove dưới đây là ĐỀ XUẤT dựa trên tên nhánh + thời điểm commit, không phải kết luận cuối cùng. Người dùng PHẢI tự xác nhận trước khi archive/remove bất kỳ worktree nào.

## Phát hiện quan trọng nhất

`app/reports/production_readiness/` trong worktree `edudss-final-candidate-v2` ĐÃ CÓ SẴN ~50 file báo cáo lịch sử (`FINAL_*.md`, `PHASE*.md`, `WORKSTREAM_*.md`, các `.csv` "capability matrix") được tạo trong các phiên TRƯỚC (2026-09-22, không phải phiên hiện tại). Nhiều file trong số đó tuyên bố "FINAL"/"ACCEPTANCE" cho các năng lực (vd. `FINAL_CAPABILITY_MATRIX.csv`, `FINAL_SYSTEM_CAPABILITY_MATRIX.csv`, `FINAL_PERF_20K_ACCEPTANCE.md`) — đây chính xác là kiểu **"nhiều bản báo cáo trùng lặp claim khác nhau"** mà Phần 9 yêu cầu dọn dẹp. Tài liệu mới trong phiên này (`AI_DECISION_ARCHITECTURE_34Q_MATRIX.md`) có thể MÂU THUẪN với các file "FINAL_*" cũ đó (vd. file cũ có thể tuyên bố năng lực đã "ACCEPTANCE" trong khi audit độc lập ở đây kết luận `NOT_IMPLEMENTED`). **CHƯA đối chiếu nội dung 2 bên trong phiên này** — đây là việc cần làm TRƯỚC KHI dùng bất kỳ tài liệu "FINAL_*" cũ nào làm căn cứ cho luận văn/thuyết trình, để tránh 2 nguồn tự mâu thuẫn nhau.

## Bảng kiểm kê worktree

| Worktree | Branch | HEAD | Loại | Đề xuất | Lý do |
|---|---|---|---|---|---|
| `D:/KLTN/code` | `main` | `10b487d` (2026-09-21) | Nhánh chính | **KEEP** | Nhánh `main` chính thức — không đụng vào (đúng yêu cầu gốc "không sửa main") |
| `D:/KLTN/edudss-72h-simulation` | `simulation/72h-real-moodle-cms` | `72877d1` (2026-09-22) | Đang chạy thật | **KEEP — TUYỆT ĐỐI KHÔNG ĐỤNG** | Giả lập 72h đang chạy (7 container `Up 3 days`), là nguồn evidence vận hành thật đang thu thập |
| `D:/KLTN/edudss-final-candidate-v2` | `fix/ml-correctness` | `a62264e` (2026-09-25, phiên hiện tại) | Đang làm việc | **KEEP — canonical hiện tại** | Toàn bộ audit/sửa lỗi H-1/H-2/NHÓM F/34Q đều nằm ở đây |
| `D:/KLTN/edudss-final-candidate-v2-freshcheckout` | (detached) `6dd96b8` | Checkout tạm | **REVIEW → khả năng ARCHIVE** | Tên gợi ý "fresh checkout" để verify — kiểm tra xem có unique commit nào không trước khi archive |
| `D:/KLTN/edudss-abc-onboarding` | `integration/abc-onboarding` | `44dd46c` | Nhánh tích hợp | **REVIEW** | Cần xác nhận đã merge vào `main`/`edudss-phase16` chưa |
| `D:/KLTN/edudss-backup-recovery` | `reliability/phase13-backup-recovery` | `afa6c02` | Nhánh phase | **REVIEW** | Phase 13 — kiểm tra đã gộp vào `edudss-phase13-revalidated`/`edudss-phase14-*` chưa |
| `D:/KLTN/edudss-backup-recovery-fresh` | (detached) `a4533ba` | Checkout tạm | **REVIEW → khả năng ARCHIVE** | "-fresh" suffix — nghi là bản re-verify tạm thời của backup-recovery |
| `D:/KLTN/edudss-capability-audit` | `audit/phase0-15-capability-closure` | `584841b` | Nhánh audit | **REVIEW** | Có thể trùng mục đích với `AI_DECISION_ARCHITECTURE_34Q_MATRIX.md` mới — đối chiếu nội dung trước khi quyết định |
| `D:/KLTN/edudss-closure-a` | `closure/workstream-a-lms-cms-simulation` | `0fd1704` | Nhánh closure | **REVIEW** | Workstream A — kiểm tra đã phản ánh vào `edudss-72h-simulation` chưa |
| `D:/KLTN/edudss-closure-b`, `-b-final-fresh`, `-b-fresh` | `closure/workstream-b-persistence-domain` + 2 detached | `aef0028` / `aef0028` / `b7a33b0` | Nhánh + 2 checkout tạm | **REVIEW closure-b, ARCHIVE-candidate 2 "-fresh"** | 3 worktree cho CÙNG workstream B — dấu hiệu rõ nhất của sprawl cần gom |
| `D:/KLTN/edudss-closure-c`, `-c-fresh-checkout` | `closure/workstream-c-ml-ai-governance` + detached | `d1b17a4` / `5c38b46` | Nhánh + checkout tạm | **REVIEW closure-c, ARCHIVE-candidate fresh-checkout** | Workstream C (ML/AI governance) — nội dung có thể trùng lặp với NHÓM F + audit H-1/H-2 hiện tại; **đối chiếu kỹ trước khi archive** vì đây là workstream gần nhất với công việc phiên này |
| `D:/KLTN/edudss-closure-d` | `closure/workstream-d-scale-recovery` | `7679f97` | Nhánh closure | **REVIEW** | Liên quan Q34 (20K scale) — đối chiếu với `FINAL_PERF_20K_ACCEPTANCE.md` trước khi kết luận Q34 |
| `D:/KLTN/edudss-cpu-fresh-checkout` | (detached) `0dbc171` | Checkout tạm | **ARCHIVE-candidate** | Tên "fresh-checkout" — tạm thời |
| `D:/KLTN/edudss-docker-cpu` | `optimization/docker-cpu-only-pytorch` | `1254adb` | Nhánh optimization | **REVIEW** | Kiểm tra đã merge vào nhánh chính chưa |
| `D:/KLTN/edudss-integration`, `-integration-ab`, `-integration-ab-cpu-c` | `integration/*` (3 nhánh) | khác nhau | 3 nhánh tích hợp | **REVIEW — có thể gộp** | 3 điểm tích hợp riêng biệt, khả năng chồng lấn |
| `D:/KLTN/edudss-ml-data-pipeline-v2` | `fix/ml-data-pipeline-v2` | `06800b5` | Nhánh fix | **REVIEW** | Tên tương tự `fix/ml-correctness` (nhánh hiện tại) nhưng KHÁC nhánh — làm rõ quan hệ 2 nhánh "fix" này trước khi merge bất kỳ cái nào |
| `D:/KLTN/edudss-observability*` (7 worktree) | `observability-hardening`, `integration/observability-12a`, `integration/observability-12a-revalidated`, + 4 detached | khác nhau | Cụm 7 worktree | **REVIEW — gom về 1-2, ARCHIVE phần detached** | Cụm lớn nhất cho 1 chủ đề (observability) — rõ ràng cần canonical hóa |
| `D:/KLTN/edudss-performance` | `performance/20k-batch-remediation` | `5ad019a` | Nhánh performance | **REVIEW — quan trọng cho Q34** | Tên "20k-batch" — CHÍNH LÀ nguồn khả năng gây nhầm "20K batch = 20K concurrent" (Q34 cảnh báo) — đọc kỹ trước khi trích dẫn bất kỳ số liệu nào từ đây |
| `D:/KLTN/edudss-persistence-phase1c` | `persistence/phase1c-runtime-cutover` | `03add02` | Nhánh phase | **REVIEW** | — |
| `D:/KLTN/edudss-phase13-*` (5 worktree) | `integration/phase13-revalidated-on-phase1c` + 4 detached | khác nhau | Cụm phase13 | **REVIEW — gom về 1, ARCHIVE phần detached** | 5 worktree cho 1 phase — sprawl |
| `D:/KLTN/edudss-phase14-*` (4 worktree) | `release/phase14-cicd-final-gate` + 3 detached | khác nhau | Cụm phase14 | **REVIEW — gom về 1, ARCHIVE phần detached** | — |
| `D:/KLTN/edudss-phase1415-main-*` (2 worktree) | 2 detached | khác nhau | Checkout tạm | **ARCHIVE-candidate** | Tên gợi ý merge-verification tạm |
| `D:/KLTN/edudss-phase15-*` (3 worktree) | `testing/phase15-final-qa` + 2 detached | khác nhau | Cụm phase15 | **REVIEW — gom về 1, ARCHIVE phần detached** | — |
| `D:/KLTN/edudss-phase16` | `docs/phase16-release-package` | `f7d3690` | Nhánh docs | **REVIEW — có thể là điểm "release" gần nhất** | Tên "release-package" gợi ý đây là bản tổng hợp cuối các phase — cần xác nhận có bao gồm NHÓM F/H-1/H-2 (phiên sau này) hay không — CHẮC CHẮN CHƯA vì các sửa lỗi đó chỉ có trên `fix/ml-correctness` |
| `D:/KLTN/edudss-phase1c-merge-fresh` | (detached) `364bb17` | Checkout tạm | **ARCHIVE-candidate** | — |
| `D:/KLTN/edudss-security` | `security-hardening` | `c752f3a` | Nhánh security | **REVIEW** | — |
| `D:/KLTN/edudss-ui-redesign` | `redesign/ui-ux-and-cleanup` | `72877d1` (TRÙNG HEAD với `edudss-72h-simulation`) | Nhánh redesign | **REVIEW** | HEAD trùng với 72h-simulation base — kiểm tra đã tách nhánh đúng chưa hay là bản sao chưa có commit riêng |
| `D:/KLTN/edudss-university-onboarding` | `closure/university-onboarding` | `a3e8d82` | Nhánh closure | **REVIEW** | Liên quan Capability B (Q7-Q9, University/Program) — đối chiếu trước khi kết luận Q7-Q9 `NOT_IMPLEMENTED` tuyệt đối (có thể việc này đã làm ở đây nhưng chưa merge vào `fix/ml-correctness`) |
| `D:/KLTN/edudss-final-release` | `release/final-candidate-verification` | `a3a5dda` | Nhánh release | **REVIEW** | — |
| `D:/KLTN/edudss-final-staging` | `integration/final-staging-candidate` | `6068423` | Nhánh staging | **REVIEW** | — |

## Nguyên tắc canonical hóa đề xuất (CHƯA THỰC HIỆN)

1. **Canonical target theo yêu cầu gốc**: `D:\KLTN\code\app` — nhưng `D:\KLTN\code` hiện đang ở `main` @ `10b487d`, KHÔNG có bất kỳ sửa lỗi nào từ `fix/ml-correctness` (confidence bịa số, H-1, H-2, NHÓM F...). Merge cần đi qua review, KHÔNG thực hiện trong phiên này (đúng ràng buộc "không merge").
2. **Nhóm "-fresh"/"-fresh-checkout"/"detached HEAD" (≈15 worktree)**: nhiều khả năng là các lần checkout tạm để verify merge/build, không phải nhánh làm việc — ứng viên ARCHIVE mạnh nhất, nhưng PHẢI kiểm tra `git log <path> --all --not --remotes` (hoặc so sánh SHA với nhánh gốc) để xác nhận KHÔNG có commit riêng nào trước khi archive.
3. **Cụm nhiều worktree cho 1 chủ đề** (observability ×7, phase13 ×5, phase14 ×4, phase15 ×3, closure-b ×3): dấu hiệu rõ nhất của sprawl — nên gom về đúng 1 worktree "revalidated"/"final" mới nhất mỗi cụm, archive phần còn lại SAU KHI xác nhận không mất commit riêng.
4. **File báo cáo "FINAL_*.md"/"FINAL_*.csv" trong `production_readiness/`**: cần đối chiếu với `AI_DECISION_ARCHITECTURE_34Q_MATRIX.md` (phiên này) TRƯỚC khi dùng bất kỳ file nào cho luận văn — có khả năng mâu thuẫn (file cũ có thể lạc quan hơn audit độc lập mới).
5. **KHÔNG đề xuất xóa bất kỳ worktree/branch nào trong phiên này.** Bảng trên là đầu vào để người dùng tự quyết định, không phải hành động đã thực hiện.

## Bảo vệ dữ liệu người dùng

Xác nhận: KHÔNG chạy `git clean`, `git stash`, `git add -A`/`git add .` ở bất kỳ worktree nào trong phiên này. Các file untracked trong `D:\KLTN\code` (nếu có) không bị đụng tới — phiên này chỉ thao tác trong `D:\KLTN\edudss-final-candidate-v2`.
