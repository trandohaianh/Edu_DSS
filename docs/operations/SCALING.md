# Chạy nhiều tiến trình app (bước 9, 22/11/2026)

Chủ dự án duyệt ngày 22/11/2026 (đề xuất (a) trong `docs/testing/STEP8_SYSTEM_TEST_REPORT.md` §4).

## Vì sao phải chạy nhiều tiến trình

Một tiến trình Streamlit chỉ dùng được khoảng một nhân CPU, vì phần lớn code Python tranh nhau một khoá chung (GIL).
Mỗi phiên đăng nhập tốn khoảng 4 giây CPU. Vì vậy 50 người đăng nhập cùng lúc phải xếp hàng khoảng 3 phút, và thuê
máy mạnh hơn mà vẫn chạy một tiến trình thì không nhanh hơn.

## Cách làm

```
Trình duyệt ──443──▶ Caddy ──cookie edudss_lb──▶ app #1 ┐
                                              ├─▶ app #2 ├─▶ PostgreSQL (RLS) + volume appdata (dùng chung)
                                              └─▶ app #3 ┘
```

| Thành phần | Thay đổi | Tệp |
|---|---|---|
| Số bản app | `deploy.replicas: ${EDUDSS_APP_REPLICAS:-3}` | `deploy/production/docker-compose.prod.yml` |
| Caddy tìm các bản | `dynamic a app 8501`: DNS của Docker trả IP của mọi bản đang chạy, hỏi lại mỗi 10 giây | `deploy/production/Caddyfile` |
| Giữ phiên | `lb_policy cookie edudss_lb`. Phiên Streamlit (WebSocket, trạng thái đăng nhập, tệp tải xuống) nằm trong bộ nhớ của một tiến trình, nên mỗi trình duyệt phải luôn về đúng bản đó. Cookie là mã băm HMAC (`EDUDSS_LB_COOKIE_SECRET`), không lộ IP nội bộ | `deploy/production/Caddyfile` |
| Một bản dừng | Caddy bỏ qua bản đó 30 giây (`fail_duration`) và chuyển người dùng sang bản khác. Người dùng đó phải đăng nhập lại | `deploy/production/Caddyfile` |
| Triển khai | Chỉ báo sẵn sàng khi **mọi** bản qua `/readyz` | `deploy/production/remote_deploy.sh` |
| Kho JSON dùng chung | Các kho đọc-sửa-ghi trước đây chỉ khoá trong một tiến trình, nay khoá bằng tệp của hệ điều hành (`InterProcessLock`) | `dss/core/file_lock.py` |

### Các kho đã được khoá giữa các tiến trình

| Kho | Trước | Sau |
|---|---|---|
| Nhật ký token AI (`ai_token_usage.json`, dùng cho trần chi phí AI) | `threading.Lock` | `InterProcessLock` |
| CMS: nhật ký tương tác, hàng duyệt quiz, lỗi hiểu sai, danh mục bài giảng | `threading.Lock` | `InterProcessLock` |
| Quy chế học vụ, thuê bao | `threading.Lock` | `InterProcessLock`. Thuê bao trước đây có thể **treo** khi tệp chưa tồn tại, vì khoá bị lấy lồng nhau; khoá mới cho phép lồng |
| Lịch sử trong kho dữ liệu (`history/*.json`, `activities.json`) | Không khoá, ghi đè trực tiếp | Khoá + ghi nguyên tử. Trước đây một người đọc gặp tệp đang ghi dở sẽ coi lịch sử là rỗng, rồi ghi đè **mất toàn bộ** |
| Con trỏ Production của mô hình | Không khoá | Khoá |
| Tài khoản (`users.json`), khoá đăng nhập | Đã có khoá tệp từ trước | Giữ nguyên |

Production dùng PostgreSQL cho tài khoản, kế hoạch học tập, nền tảng, CMS và RAG (`EDUDSS_*_STORE=postgres`), nên các
kho đó không phụ thuộc phần khoá tệp này. Phần khoá tệp bảo vệ những kho vẫn nằm trong volume `appdata`.

**Bằng chứng:** `tests/test_step9_multiprocess_stores.py`. Test chạy 4 tiến trình, mỗi tiến trình ghi 25 lượt cùng lúc,
và kiểm tra đủ 100/100 bản ghi. Khi thay lại khoá cũ (chỉ khoá trong một tiến trình), cùng kịch bản chỉ giữ được
**35/100 bản ghi** và 3/4 tiến trình bị lỗi.

## Kết quả đo (máy dev, 22/11/2026)

Máy dev có 4 nhân (8 luồng). Chạy 3 tiến trình Streamlit dùng chung một thư mục dữ liệu, đặt sau Caddy 2.10.2 với
cùng chính sách cookie. Dữ liệu mô phỏng 20.000 sinh viên. Mọi phiên bắt đầu cùng một giây.

| Lần chạy | Phiên | Lỗi | Đăng nhập p50 / p95 | Mở trang đăng nhập p95 | Tổng thời gian |
|---|---|---|---|---|---|
| 1 tiến trình, đo lại cùng lúc với lần dưới | 25 | 0 | 65,9 / 79,1 s | 108,4 s | 117 s |
| **3 tiến trình + Caddy** | 25 | 0 | **28,2 / 53,1 s** | 47,4 s | 82 s |
| 1 tiến trình (bước 8) | 50 | 0 | 57,5–77,6 / 87,9–116,7 s | 126–144 s | — |
| **3 tiến trình + Caddy** | 50 | **0** | **51,2 / 76,6 s** | 88,7 s | 151 s |

Kiểm tra cookie trong Docker, dùng chính `deploy/production/Caddyfile` với 3 bản `app`:
- 8 trình duyệt mới được chia ra cả 3 bản.
- Một trình duyệt gửi 8 yêu cầu đều về cùng một bản.
- Dừng bản đó thì đúng 1 yêu cầu lỗi, sau đó trình duyệt được chuyển sang bản khác và ở lại bản mới.

**Cách đọc kết quả:** trên máy dev, 3 tiến trình chưa nhanh gấp 3, vì 25–50 trình duyệt kiểm thử chạy **trên cùng
máy** chiếm phần lớn 4 nhân CPU. Mỗi tiến trình app chỉ dùng khoảng 0,7 nhân, tức chưa đến giới hạn của nó. Trên máy
chủ thật, trình duyệt nằm ở máy người dùng, nên mỗi bản có trọn một nhân. **Cần đo lại trên máy chủ thí điểm**, chạy
`tools/browser_load_test.py` từ một máy khác.

## Chọn số bản và cấu hình máy chủ

RAM đo được của mỗi tiến trình: khoảng 0,6–0,75 GB khi nghỉ, **đỉnh 1,6–2,1 GB** khi 50 phiên đăng nhập cùng lúc.

| Máy chủ | `EDUDSS_APP_REPLICAS` | Ghi chú |
|---|---|---|
| 2 nhân / 4 GB | 1 | Không đủ RAM cho 2 bản lúc cao điểm |
| **4 nhân / 8 GB** (đề xuất cho thí điểm) | **3** | Còn khoảng 1 nhân cho PostgreSQL và Caddy; đỉnh RAM khoảng 6 GB |
| 8 nhân / 16 GB | 4–6 | |

Quy tắc: số bản ≤ số nhân − 1, và số bản × 2 GB + 1,5 GB (PostgreSQL, Caddy, hệ điều hành) ≤ RAM.

## Giới hạn còn lại

- **Khi một bản dừng hoặc khởi động lại (cập nhật phiên bản), người dùng trên bản đó phải đăng nhập lại.** Nên triển
  khai ngoài giờ học. Quy định thời điểm triển khai: `docs/operations/RELEASE_PROCESS.md` §6.
- Giới hạn gọi AI trong `llm_gateway` (60 lượt/phút và số cuộc gọi đồng thời) nằm trong bộ nhớ của **từng tiến trình**.
  Với 3 bản, mức chung của cả hệ thống thành 180 lượt/phút. Bộ ngắt mạch khi nhà cung cấp AI lỗi cũng tính riêng
  từng bản. Trần chi phí AI theo ngày/tháng tính từ kho dùng chung, nên vẫn đúng cho cả hệ thống.
- Hai bản kiểm tra trần chi phí cùng lúc có thể vượt trần một lượt gọi. Đây là mức nhỏ so với trần 5 USD/tháng.
- Bản demo công khai (`deploy/cloud`, `deploy/standalone`) vẫn chạy 1 bản, vì máy chủ miễn phí giới hạn RAM.
