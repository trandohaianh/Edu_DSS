# EduDSS — Thông báo xử lý dữ liệu cá nhân (BẢN NHÁP KỸ THUẬT)

> ⚠️ **Chưa được luật sư duyệt. Không dùng cho thí điểm cho tới khi được duyệt.**
> Bản nháp do đội kỹ thuật soạn ngày 21/11/2026 (bước 7, nhóm B). Phần mô tả **dữ liệu nào đi đâu** khớp với code;
> phần **căn cứ pháp lý, thời hạn, quyền và thủ tục** cần luật sư và nhà trường xác nhận.
> Văn bản hiển thị trong app nằm ở `dss/services/privacy_notice.py` (`NOTICE_VERSION = 2026-11-21-draft1`).
> Sửa nội dung thì **tăng `NOTICE_VERSION`**: mọi người dùng sẽ được hỏi đồng ý lại.

## 1. Cách hoạt động trong app

- Ngay sau khi đăng nhập, người dùng phải đọc thông báo, tick "đã đọc và đồng ý" rồi bấm **Đồng ý và tiếp tục**.
  Nếu chọn **Không đồng ý** thì bị đăng xuất.
- Bằng chứng đồng ý gồm người dùng, phiên bản thông báo và thời điểm. Bằng chứng được ghi vào sổ kiểm toán của
  nền tảng (bảng `lp_audit_events`, hành động `privacy.notice_accepted`).
- Không ghi được bằng chứng thì không cho vào app (fail closed).
- Bật mặc định khi dùng dữ liệu thật. Bản demo dữ liệu mô phỏng không hỏi.
  Có thể ghi đè bằng biến `EDUDSS_PRIVACY_CONSENT_REQUIRED`.

## 2. Dữ liệu gửi cho nhà cung cấp AI ở nước ngoài

Các nhà cung cấp: OpenAI, Google Gemini, Groq. Máy chủ chủ yếu ở Hoa Kỳ; **cần xác minh** theo hợp đồng của từng
nhà cung cấp. Dữ liệu chỉ được gửi khi người dùng dùng trợ lý AI.

| Gửi | Ở đâu trong code | Ghi chú |
|---|---|---|
| Mức rủi ro học tập (cao/trung bình/thấp) | `privacy_service.build_anonymized_student_context`, `build_quick_question_prompt` | |
| Khoảng điểm dự đoán | `privacy_service.gpa_band` | Không gửi điểm chính xác |
| Môn/kỹ năng cần cải thiện | `build_anonymized_student_context` | Đã lọc PII |
| Nhóm chuyên cần | `privacy_service.attendance_bracket` | Không gửi tỷ lệ chính xác |
| Nhận xét tiến độ (nếu có) | `build_anonymized_student_context` | Đã lọc PII |
| Câu hỏi + lịch sử chat | `sanitize_conversation_turn_for_provider` | Đã xoá email, SĐT, mã SV, tên tự giới thiệu. **Sinh viên vẫn có thể tự gõ thông tin nhạy cảm khác** |

**Không gửi:** họ tên, mã sinh viên, email, số điện thoại, điểm chính xác từng môn. Bí danh chỉ dùng nội bộ để đếm hạn mức.

## 3. Câu hỏi cho luật sư

1. Có cần **hồ sơ đánh giá tác động chuyển dữ liệu cá nhân ra nước ngoài** không, theo Nghị định 13/2023/NĐ-CP và
   Luật Bảo vệ dữ liệu cá nhân 2025 (hiệu lực 1/1/2026)? Dữ liệu ở §2 đã bỏ định danh trực tiếp, nhưng vẫn có thể là
   dữ liệu cá nhân, vì nhà trường ghép lại được.
2. Căn cứ xử lý là **sự đồng ý** hay **nhiệm vụ đào tạo của nhà trường**? Nếu là đồng ý, sinh viên từ chối thì có còn
   dùng được các chức năng không dùng AI không? Thiết kế hiện tại: từ chối thì không vào được app. Có thể đổi thành
   "vào được nhưng tắt AI".
3. Thời hạn lưu trữ ở §4 có phù hợp quy định lưu trữ hồ sơ đào tạo không?
4. Người dưới 18 tuổi (nếu có) có cần cha mẹ đồng ý không?
5. Ai là bên kiểm soát dữ liệu, ai là bên xử lý? Có cần ký hợp đồng xử lý dữ liệu (DPA) với OpenAI/Google/Groq không?

## 4. Lưu trữ và quyền của chủ thể dữ liệu (theo code `dss/services/data_lifecycle.py`)

| Loại | Thời hạn mặc định | Khi sinh viên yêu cầu xoá |
|---|---|---|
| Hội thoại AI | 365 ngày | Xoá |
| Kết quả dự đoán, gợi ý | 365 ngày | Xoá |
| Họ tên, mã, tài khoản | — | Ẩn danh |
| Điểm, chuyên cần, hồ sơ học tập | Theo quy định nhà trường | Giữ, gắn vào hồ sơ đã ẩn danh |
| Nhật ký hệ thống | 5 năm | Giữ dòng, xoá nội dung cá nhân |
| Bộ đếm dùng AI (bí danh) | 400 ngày | Giữ |

- Admin thực hiện yêu cầu ở trang **Người dùng → "Yêu cầu về dữ liệu cá nhân của sinh viên"**: tải bản sao JSON,
  hoặc xoá (phải gõ lại mã SV và tick xác nhận). Mỗi lần xoá ghi một dòng kiểm toán, chỉ chứa số lượng bản ghi.
- **Giới hạn đã biết:**
  - Bản sao lưu vẫn chứa dữ liệu đã xoá cho tới khi bản sao lưu hết hạn.
  - Lần đồng bộ LMS sau có thể tạo lại sinh viên nếu không xoá cả ở hệ thống nguồn.
  - Chức năng chỉ chạy trên PostgreSQL. 8 kho dữ liệu dạng tệp (xem bước 9) chưa nằm trong phạm vi xoá.
