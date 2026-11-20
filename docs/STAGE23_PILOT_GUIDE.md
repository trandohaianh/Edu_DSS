# Chạy thử lớp học và chương trình cấp phát

Bản ngày 26/10/2026. Phạm vi: phần mềm chạy thử tại trường và quản lý chương
trình cấp phát. Kết nối HLU, mua sắm và triển khai diện rộng chưa được nghiệm thu.

## Chạy tại một trường

Từ thư mục `app`, dùng Python của môi trường hiện có:

```powershell
$env:EDUDSS_ENV="development"
$env:EDUDSS_MODE="LOCAL_OFFLINE"
$env:EDUDSS_PLATFORM_STORE="local"
$env:EDUDSS_ORGANIZATION_ID="1"
$env:EDUDSS_REQUIRE_PROGRAM_ALLOCATION="0"
python -m streamlit run run_dss.py
```

Đặt `EDUDSS_DATA_ROOT` riêng để tách dữ liệu thử. Lớp học dùng
`learning_platform.sqlite3` trong thư mục đó. LOCAL_OFFLINE không tự tạo bộ
điểm ML; luồng lớp học, đánh giá và đọc học liệu đã lưu không cần khóa API AI.

Admin tạo lớp bằng mã lớp, học phần và học kỳ; phân công tên đăng nhập giảng
viên, ghi danh mã sinh viên trùng với tài khoản sinh viên. Giảng viên chỉ được
truy cập lớp được phân công; sinh viên chỉ được truy cập lớp đã ghi danh.
Đóng lớp giữ lịch sử kết quả và kế hoạch theo quyền hiện có.

Admin có thể nhập danh sách CSV UTF-8/UTF-8 BOM, tối đa 1.000 dòng:

```csv
student_code
SV001
SV002
```

Xem trước rồi xác nhận. Nhập ghi danh thực hiện trong một giao dịch: dòng
không hợp lệ hoặc vượt suất sẽ hủy cả lần nhập. Chỉ dùng tệp trường cho phép xuất.

Giảng viên soạn bằng biểu mẫu câu hỏi, chủ đề, lựa chọn và số thứ tự đáp án, lưu nháp rồi xuất bản. Nhập JSON chỉ dành cho bộ câu hỏi hàng loạt. JSON mỗi câu có:
`question_id`, `topic_id`, `text`, `options` (2–8 lựa chọn),
`correct_answer_index` (bắt đầu từ 0), `explanation` tùy chọn.
Nội dung đã xuất bản được giữ nguyên; chỉnh sửa tạo phiên bản nháp mới.
Giới hạn lượt làm được tính theo sinh viên và phiên bản bài đánh giá.

Sinh viên nộp bài để lưu điểm từng chủ đề và một phiên bản kế hoạch trong cùng
giao dịch. Nộp lại cùng khóa gửi không tạo lượt trùng; đổi nội dung với khóa cũ bị từ chối. Checkbox hoàn thành là thông tin tự báo cáo, không phải kết quả học.
Chủ đề chưa đo không nhận điểm 0 thay thế. Giảng viên xem tiến độ, thời điểm
quan sát và lưu hoạt động hỗ trợ của lớp mình.

## Học liệu

Admin mở **Học liệu của trường**, nạp tài liệu bằng quy trình CMS hiện có,
gắn đúng mã học phần/chủ đề và hoàn tất duyệt. Kế hoạch chỉ gắn học liệu hợp lệ đúng học phần/chủ đề. Nếu thiếu học liệu, hệ thống đề nghị giảng viên lựa chọn.

Sinh viên bấm **Đọc học liệu** trong kế hoạch. Hệ thống kiểm tra lại quyền lớp, chủ sở hữu, phiên bản và trạng thái duyệt. Tài liệu bị thu hồi, loại trừ hoặc
thay phiên bản không tiếp tục hiển thị từ kế hoạch cũ. Đọc nội dung đã lưu
không gọi LLM hoặc tìm kiếm embedding.

## Chương trình cấp cho các trường

Mỗi tiến trình ứng dụng phục vụ một trường theo cấu hình máy chủ
`EDUDSS_ORGANIZATION_ID`. Các trường dùng cùng image, cấu hình và kho tệp
riêng; cần dùng chung PostgreSQL chương trình với RLS để nhận cùng cấp phát. SQLite chỉ dùng thử một bản chạy. Bản này chưa hỗ trợ đăng nhập
chọn nhiều trường trong cùng tiến trình. Mã registry `lp_schools.id` phải
trùng `organizations.id` của hệ thống tài khoản.

**Platform Admin** đăng ký trường, tạo chương trình và giao quyền cho đúng
cặp mã trường quản lý tài khoản + tên đăng nhập. Quyền `manager` quản lý
cấp phát/báo cáo; `analyst` chỉ xem báo cáo. Quyền kỹ thuật không tự cấp
quyền đọc báo cáo hoặc phân bổ suất.

Tổng cấp phát phải nằm trong quỹ chương trình. Không giảm số suất trường
xuống dưới số sinh viên đang sử dụng. Một sinh viên tham gia nhiều lớp trong
trường chỉ chiếm một suất. Nếu có nhiều cấp phát đang hoạt động, giới hạn
hiệu lực là mức thấp nhất trong các cấp phát đó.

Đặt `EDUDSS_REQUIRE_PROGRAM_ALLOCATION=1` ở bản chạy do chương trình quản lý.
Thiếu cấp phát hoạt động sẽ chặn hoạt động học tập mới. Cấp phát bị dừng/thu
hồi không tự chuyển về chế độ độc lập khi tắt cờ. Lịch sử vẫn được giữ để đọc.

Ngân sách AI hiện là **thông tin phân bổ**, được kiểm tra theo quỹ chương trình;
chưa đo token, chặn yêu cầu nhà cung cấp hoặc tính phí tiêu thụ.

Admin trường bấm **Gửi báo cáo tổng hợp**. Snapshot có thời điểm và trạng thái
chưa báo cáo/cũ/ẩn nhóm nhỏ/hiện hành. Ngưỡng tối thiểu là 5; ô có nhóm nhỏ
phải bị ẩn. Không đưa mã sinh viên, đáp án, hội thoại hay từng kế hoạch vào
báo cáo trung tâm. Quyền chương trình không cấp quyền đọc dữ liệu học tập thô.
Manager/analyst có thể tải JSON báo cáo tổng hợp.

## Tài khoản đầu tiên và PostgreSQL

Dùng role owner cho migration/khởi tạo, role ứng dụng không phải superuser
và không có BYPASSRLS. Áp dụng migration `d2e3a6102601` trước khi chạy bản mới:
thêm 13 bảng `lp_*` và cột mã học phần ngoài rag_documents.course_code; giữ nguyên khóa số course_id hiện có. Downgrade xóa dữ liệu các
bảng mới; chỉ thực hiện khi có phương án giữ dữ liệu phù hợp.

Tạo tài khoản đầu tiên bằng công cụ vận hành, không chạy demo seed trên dữ liệu thật:

```powershell
# Cấp DATABASE_URL của role owner cho phiên vận hành bằng môi trường.
python -m ops.bootstrap_identity --org-code PROGRAM_OFFICE --org-name "Đơn vị quản lý chương trình" --username ministry.operator --role "Platform Admin"
```

Nhập kín mật khẩu hai lần; không truyền mật khẩu qua dòng lệnh.
Công cụ từ chối ghi đè tài khoản. Dùng `--role Admin` để tạo quản trị trường.
Ghi lại mã tổ chức trả về và dùng làm cấu hình máy chủ. Chạy thử cục bộ có
`--local`; sản xuất từ chối chế độ này.

Phần mới yêu cầu `EDUDSS_PLATFORM_STORE=postgres`,
`EDUDSS_IDENTITY_STORE=postgres`, `EDUDSS_LEARNING_PLANS_STORE=postgres`, `EDUDSS_CMS_STORE=postgres`, `EDUDSS_RAG_STORE=postgres`,
mã tổ chức dương, privacy key và kết nối PostgreSQL. Compose sản xuất đã nối
các biến này. Giữ kho tệp của các trường riêng; PostgreSQL lỗi không tự đổi SQLite.

Chạy kiểm thử cơ sở dữ liệu cô lập từ `app`:

```powershell
python tools/run_stage23_acceptance.py
```

Cần Docker đang chạy và image PostgreSQL/pgvector. Công cụ tạo container mới,
cổng loopback, role owner/app riêng, chạy migration và kiểm thử, rồi dọn đúng
container có nhãn của lần chạy. Không dùng database phát triển có sẵn.

## HLU và phạm vi còn lại

Địa chỉ được cung cấp là [cổng sinh viên HLU](https://sv.hlu.edu.vn/sinh-vien-dang-nhap.html).
Dự án chưa nhận đặc tả API, tài khoản tích hợp, SSO hoặc tệp xuất chính thức.
Không suy ra sản phẩm LMS hay bịa endpoint từ trang đăng nhập. Hiện có thể
nhập danh sách lớp qua CSV trường cấp. Đồng bộ điểm, đăng ký học và SSO
cần hợp đồng dữ liệu, định danh, quyền truy cập và kiểm thử với trường.

Thay toàn bộ LMS còn cần đối chiếu yêu cầu như bài nộp tệp, sổ điểm chính thức,
SCORM/LTI, lịch học, thông báo và khảo thí. Chưa xác nhận các chức năng đó qua
bản này. Triển khai diện rộng cần thêm kiểm thử nhiều phiên trình duyệt,
vận hành, khôi phục và nghiệm thu tại trường/đơn vị mua.
