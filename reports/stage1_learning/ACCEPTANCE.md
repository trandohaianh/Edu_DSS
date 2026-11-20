# Nghiệm thu phần nền giai đoạn 1 — EduDSS

Ngày: 20/10/2026. Phạm vi: code và kiểm thử tại workspace; chưa phải nghiệm thu
thí điểm với trường hoặc triển khai cấp Bộ.

## Đã triển khai

- Đăng nhập chỉ nạp mô hình đã duyệt, không huấn luyện/phân cụm ngầm.
  Silhouette khi chạy thủ công lấy mẫu có thể lặp lại, tối đa 2.000 dòng.
- Hồ sơ giữ dữ liệu thiếu/sai ở trạng thái chưa biết, phân biệt với số 0 hợp lệ.
  Chẩn đoán cần đủ các quan sát hỗ trợ; dữ liệu thiếu không được coi là điểm yếu.
- Đọc điểm chủ đề/kỹ năng từ đối tượng JSON, kể cả JSON trong cột CSV.
  Điểm chủ đề dùng thang 0–10; tỷ lệ thành thạo dùng 0–1.
- Kế hoạch chọn học liệu đúng môn/chủ đề. Nguồn CMS phải là bản hiện hành,
  được duyệt, còn hiệu lực và chưa bị loại. Nội dung mẫu bị loại ở production.
- Sinh viên tạo kế hoạch không cần LLM hoặc cột GPA; xem lịch sử và đánh dấu
  tiến độ ở phiên mới. Khi production chưa có dataset LMS, lịch sử vẫn có thể mở.
- Phiên bản kế hoạch độc lập theo trường/sinh viên/học phần; lưu lại cùng plan_id
  không nhân bản; lưu đồng thời không trùng version. Tiến độ riêng cho mỗi plan.
- Kiểm quyền chủ sở hữu ở service; Platform Admin không mặc nhiên đọc hồ sơ.
  Khóa lưu cục bộ phân biệt cả mã sinh viên khác chữ hoa/thường.
- Production dùng PostgreSQL qua bảng recommendations có sẵn; lỗi DB không
  chuyển sang SQLite. Không cần migration mới cho phần lịch sử kế hoạch.

## Dùng thử

Đăng nhập tài khoản sinh viên → Trợ lý AI → Kế hoạch học tập →
“Kế hoạch và tiến độ đã lưu”.

Dataset cần student_id và course_id hoặc course_code. Một pilot dành riêng một
học phần có thể cấu hình EDUDSS_COURSE_ID ở phía quản trị. Nếu trùng bản ghi
sinh viên/học phần, đối soát trước khi lập kế hoạch.

Ví dụ giá trị cột topic_scores trong CSV: {"loops": 3.5, "functions": 7.0}.
Thời lượng/tần suất chưa đủ căn cứ sẽ để chưa xác định. Học liệu chưa phù hợp
sẽ yêu cầu giảng viên bổ sung. Đánh dấu hoàn thành là tự báo cáo, không chứng
minh đã đạt chuẩn đầu ra.

Development dùng EDUDSS_DATA_ROOT/learning_plans.sqlite3.
Production cần EDUDSS_LEARNING_PLANS_STORE=postgres,
EDUDSS_ORGANIZATION_ID hợp lệ, kết nối DB và khóa giả danh đã cấu hình.

## Kiểm chứng

Lượt hồi quy rộng:

    python -m pytest tests --ignore=tests/e2e --ignore=tests/load -q

Kết quả: 1.138 passed, 166 skipped, không failed; 735,62 giây.
Sau đó bổ sung khóa lưu phân biệt chính xác mã sinh viên và kiểm tra lại:

    python -m pytest tests/test_stage1_plan_history.py tests/test_stage1_plan_workspace_ui.py -q

Kết quả: 13 passed, không failed; 13,23 giây.
git diff --check không có lỗi khoảng trắng.

Kiểm thử giao diện dùng Streamlit AppTest, bao gồm phiên production chưa có
dataset, không tạo dữ liệu giả; tạo/mở lại kế hoạch và phục hồi tiến độ qua phiên mới.

Hai kiểm thử PostgreSQL mới yêu cầu database thí nghiệm đã migrate và role
ứng dụng không phải superuser. Máy hiện chưa chạy Docker, không có URL DB
thí nghiệm nên chưa chạy trực tiếp hai kiểm thử này. Không suy từ SQLite
sang kết luận PostgreSQL/RLS đã được nghiệm thu cho code mới.

Chưa chạy Playwright E2E, kiểm thử tải hoặc xác minh tích hợp LMS của trường.
Các kiểm thử phụ thuộc dịch vụ/cấu hình bên ngoài nằm trong nhóm skipped.

Một test xếp hạng cũ giả định Accuracy/F1 luôn chọn hai model khác nhau.
Fixture đã được thay bằng trường hợp metric bất đồng rõ ràng; kiểm tra lựa
chọn thống nhất vẫn được giữ. Không sửa thuật toán ML hay các thay đổi
auth/trainers/model_registry/model_service đã có trước công việc này.

## Phạm vi tiếp theo

Giai đoạn 2: lớp học phần, phân công giảng viên, enrollment, attempt theo phiên
bản câu hỏi, bằng chứng theo chủ đề, can thiệp và tích hợp LMS thật; triển khai
lặp lại tại nhiều trường với cùng codebase.

Giai đoạn 3: chương trình cấp Bộ, cấp quyền/hạn mức cho từng trường và báo cáo
tổng hợp. Quyền cấp phát tách khỏi quyền đọc dữ liệu cá nhân. Chi tiết tại
docs/architecture/EDUDSS_MINISTRY_ROADMAP.md.
