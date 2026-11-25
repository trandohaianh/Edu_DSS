# Các quyết định kỹ thuật (Decision Log)

File này ghi lại các lựa chọn quan trọng của EduDSS. Mỗi quyết định có 5 phần: **vấn đề**, **các phương án đã cân nhắc**, **lý do chọn**, **ưu điểm và hạn chế**, **nếu làm tiếp sẽ đổi gì**.

Bối cảnh chung: dữ liệu là mô phỏng, nhưng ràng buộc thì thật — kết quả mô hình quyết định một sinh viên có được gọi lên hỗ trợ hay không.

---

## 1. Chỉ số chọn mô hình: F1-macro thay vì accuracy

**Vấn đề.** Trong bộ đánh giá 1.000 sinh viên mô phỏng, loại Yếu chỉ có 2 em. Một mô hình đoán "Khá" cho tất cả vẫn đạt accuracy rất cao trong khi bỏ sót đúng nhóm cần tìm.

**Các phương án đã cân nhắc.**
- Accuracy: dễ hiểu, nhưng bị lớp đông chi phối.
- F1 có trọng số (weighted F1): vẫn nghiêng theo số lượng mẫu của từng lớp.
- **F1-macro**: trung bình F1 của từng loại học lực, mỗi loại nặng ngang nhau.

**Lý do chọn.** F1-macro cho loại hiếm trọng lượng ngang loại đông và phạt nặng việc bỏ sót — đúng với mục tiêu "không để sót em cần giúp". Kèm theo, cân bằng lớp (SMOTE) được đặt **bên trong** vòng kiểm định chéo: nếu nhân bản mẫu trước khi chia fold thì bản sao của cùng một sinh viên nằm cả ở tập huấn luyện lẫn tập kiểm tra, điểm đẹp lên nhưng vô nghĩa.

**Ưu điểm và hạn chế.**
- Ưu: con số nói thật. Mô hình được chọn (LightGBM) có accuracy 0,91 nhưng F1-macro chỉ 0,70 trên 200 sinh viên kiểm tra — khoảng cách đó chính là thông tin.
- Hạn chế: với 2 mẫu Yếu, F1 của lớp này dao động mạnh giữa các lần chia; con số chưa ổn định thống kê.

**Nếu làm tiếp.** Đánh giá trên dữ liệu thật đã ẩn danh có đủ mẫu lớp hiếm; báo thêm recall của riêng nhóm nguy cơ và khoảng tin cậy; cân nhắc hiệu chỉnh xác suất (calibration) để đặt ngưỡng cảnh báo theo năng lực hỗ trợ của trường.

---

## 2. Cách đọc kết quả R² 0,99

**Vấn đề.** Mô hình hồi quy dự đoán điểm kỳ sau đạt R² 0,993 trên tập kiểm tra. Con số này quá đẹp để tin ngay.

**Các phương án đã cân nhắc.**
- Đưa R² 0,99 lên như thành tích.
- Bỏ con số đi cho đỡ bị hỏi.
- **Giữ con số nhưng ghi rõ nguồn gốc của nó.**

**Lý do chọn.** Trong bộ dữ liệu mô phỏng, điểm kỳ sau được sinh ra bằng một công thức tuyến tính của chính các đặc trưng đầu vào, cộng một nhiễu nhỏ. Mô hình chỉ đang tìm lại công thức đó. Giữ con số kèm giải thích cho thấy đường ống dữ liệu và huấn luyện chạy đúng, đồng thời không tuyên bố quá mức.

**Ưu điểm và hạn chế.**
- Ưu: trung thực, dùng được làm bài kiểm tra "đường ống có chạy đúng không".
- Hạn chế: không chứng minh được gì về độ chính xác với sinh viên thật.

**Nếu làm tiếp.** Sinh dữ liệu mô phỏng có quan hệ phi tuyến và nhiễu lớn hơn để thử độ bền; quan trọng hơn là đánh giá trên dữ liệu thật đã ẩn danh.

---

## 3. Duyệt mô hình trước khi đưa vào chạy

**Vấn đề.** Đổi mô hình là đổi danh sách sinh viên bị gắn cờ. Nếu ai vừa chạy huấn luyện gần nhất cũng tự đưa được mô hình vào dùng, danh sách đó có thể đổi mà không ai biết.

**Các phương án đã cân nhắc.**
- Tự động dùng mô hình mới nhất / mô hình có điểm cao nhất.
- Giảng viên tự đưa mô hình của mình vào dùng.
- **Vòng đời Chờ duyệt → Đang dùng → Lưu trữ, chỉ quản trị viên được chuyển trạng thái.**

**Lý do chọn.** Quyết định ảnh hưởng tới nhiều sinh viên nên phải thuộc về người có thẩm quyền và để lại dấu vết. Mô hình mới chỉ ở trạng thái chờ duyệt; đưa lên phải qua thao tác có kiểm tra quyền; bản cũ chuyển sang lưu trữ và quay lại được (rollback). Tệp mô hình có kiểm tra toàn vẹn SHA-256.

**Ưu điểm và hạn chế.**
- Ưu: tách người huấn luyện và người duyệt; trả lời được câu "vì sao em này bị gắn cờ, mô hình nào, ai duyệt".
- Hạn chế: thêm một bước thủ công; chưa có so sánh tự động mô hình mới với mô hình đang dùng trên cùng một tập trước khi duyệt.

**Nếu làm tiếp.** Thêm báo cáo so sánh "trước/sau" (bao nhiêu sinh viên vào/ra danh sách cảnh báo) hiển thị ngay lúc duyệt; theo dõi drift dữ liệu để biết khi nào cần huấn luyện lại.

---

## 4. Kiểm tra rò rỉ đặc trưng trước khi huấn luyện

**Vấn đề.** Một chỉ số quá đẹp thường là dấu hiệu rò rỉ (leakage) chứ không phải mô hình giỏi. Nếu một cột thực chất là đáp án đổi dạng, mô hình chỉ đang chép lại đáp án.

**Các phương án đã cân nhắc.**
- Tin vào việc người dùng tự chọn cột đúng.
- Kiểm tra thủ công một lần khi làm bộ dữ liệu.
- **Bước kiểm tra tự động `filter_leakage_features()` chạy trước mỗi lần huấn luyện.**

**Lý do chọn.** Giảng viên có thể tải lên bộ dữ liệu mới bất kỳ lúc nào, nên kiểm tra phải tự động. Hệ thống đối chiếu từng cột với cột cần dự đoán và loại những cột gần như trùng. Ở bộ dữ liệu này, bước đó loại ra ba cột dẫn xuất trực tiếp từ mục tiêu. Ngoài ra `train_test_split` chạy **trước** mọi bước tiền xử lý, và imputer/scaler/encoder/SMOTE nằm trong pipeline chỉ được fit trong các fold huấn luyện.

Một lỗi rò rỉ khó thấy hơn cũng đã được sửa: mã học kỳ bị sắp xếp như chuỗi chữ, nên điểm của kỳ sau lọt vào dữ liệu huấn luyện.

**Ưu điểm và hạn chế.**
- Ưu: chặn được lỗi rò rỉ phổ biến nhất mà không cần người dùng hiểu ML.
- Hạn chế: chỉ bắt được cột tương quan rất mạnh với mục tiêu; rò rỉ theo thời gian hoặc qua tổ hợp nhiều cột vẫn có thể lọt.

**Nếu làm tiếp.** Kiểm tra thứ tự thời gian một cách tường minh (đặc trưng không được muộn hơn thời điểm dự đoán); chia train/test theo học kỳ thay vì ngẫu nhiên.

---

## 5. Tính điểm tất định, không giao cho mô hình ngôn ngữ

**Vấn đề.** Điểm trung bình, điều kiện tốt nghiệp và cảnh báo học vụ phải đúng tuyệt đối và giải thích được theo điều khoản quy chế. Mô hình ngôn ngữ không bảo đảm được điều đó.

**Các phương án đã cân nhắc.**
- Để LLM đọc quy chế và tự tính.
- **Mã tường minh theo quy chế; LLM chỉ trả lời câu hỏi mở.**

**Lý do chọn.** Phần cần đúng tuyệt đối thì viết thành mã và kiểm thử được. LLM chỉ dùng cho câu hỏi mở, qua `llm_gateway` có kiểm tra tình trạng nhà cung cấp, retry (Tenacity) và giới hạn số yêu cầu đồng thời. Khi nhà cung cấp AI không gọi được, hệ thống hỏi người dùng trước khi chuyển sang chế độ mô phỏng có nhãn rõ ràng, không lặng lẽ trả lời bằng văn bản giả. RAG có ngưỡng tin cậy: dưới ngưỡng thì trả lời "không tìm thấy bằng chứng" thay vì trích dẫn yếu.

**Ưu điểm và hạn chế.**
- Ưu: kết quả lặp lại được, kiểm thử được, giải thích được theo quy chế.
- Hạn chế: khi quy chế đổi phải sửa mã; chất lượng câu trả lời mở vẫn phụ thuộc nhà cung cấp LLM bên ngoài.

**Nếu làm tiếp.** Đưa các tham số quy chế (ngưỡng điểm, số tín chỉ) ra file cấu hình có phiên bản để phòng đào tạo tự cập nhật; thêm bộ đánh giá câu trả lời RAG cố định để đo khi đổi mô hình LLM.

---

## 6. Kiểm soát truy cập ở tầng cơ sở dữ liệu (Row-Level Security)

**Vấn đề.** Ẩn nút trên giao diện chỉ ngăn người dùng bình thường. Nếu một truy vấn quên điều kiện lọc thì dữ liệu của tổ chức này lọt sang tổ chức khác.

**Các phương án đã cân nhắc.**
- Chỉ kiểm quyền ở giao diện.
- Chỉ lọc theo tổ chức trong code truy vấn.
- **Kết hợp kiểm quyền trong hàm nghiệp vụ và Row-Level Security của PostgreSQL.**

**Lý do chọn.** Với RLS, dù truy vấn viết thiếu, máy chủ dữ liệu vẫn không trả về dòng không thuộc tổ chức đang đăng nhập. Migration đầu tiên `cbae9b411ed5` bật RLS cho các bảng có cột tổ chức, các migration sau bật tiếp cho bảng mới; theo [docs/database/SCHEMA.md](database/SCHEMA.md), 50 trên 54 bảng có RLS (bảng con như `model_metrics`, `rag_chunks` được cô lập qua bảng cha). Ứng dụng phải chạy bằng một vai trò riêng không phải superuser để RLS có hiệu lực.

**Ưu điểm và hạn chế.**
- Ưu: thêm một lớp phòng thủ không phụ thuộc vào việc lập trình viên nhớ lọc.
- Hạn chế: chỉ có tác dụng ở chế độ PostgreSQL; ở chế độ file local thì không có lớp này. Cần cấu hình vai trò database đúng, nếu chạy bằng superuser thì RLS bị bỏ qua.

**Nếu làm tiếp.** Thêm kiểm tra lúc khởi động: từ chối chạy nếu ứng dụng kết nối bằng superuser (hiện chỉ có cảnh báo trong `dss/db/session.py` và tài liệu triển khai).

---

## 7. Streamlit, một tiến trình, gọi hàm trực tiếp

**Vấn đề.** Cần giao diện cho ba vai trò với nhiều biểu đồ và bảng dữ liệu, do một người phát triển trong thời gian khoá luận.

**Các phương án đã cân nhắc.**
- Tách frontend (React/Next.js) và backend API.
- Thêm hàng đợi tác vụ hoặc orchestrator (Airflow/Prefect) cho các bước chẩn đoán → gợi ý → kế hoạch học tập.
- **Streamlit một tiến trình, các bước nghiệp vụ là lời gọi hàm trực tiếp.**

**Lý do chọn.** Streamlit cho phép làm giao diện dữ liệu nhanh bằng Python, cùng ngôn ngữ với phần ML. Ở quy mô một trường, chuỗi bước nghiệp vụ ngắn và đồng bộ, nên orchestrator chỉ thêm độ phức tạp.

Monolith cũ `5.py` (gần 14.000 dòng) đã được tách thành gói `dss/` (`tabs/`, `services/`, `core/`, `db/`, `security/`) để mỗi trang và mỗi nghiệp vụ nằm ở file riêng, tránh phải sửa hai nơi.

**Ưu điểm và hạn chế.**
- Ưu: ít thành phần, dễ chạy, dễ kiểm thử E2E bằng Playwright.
- Hạn chế: Streamlit chạy lại script mỗi lần tương tác nên khó tối ưu cho nhiều người dùng đồng thời; một số file trang vẫn còn lớn (trên 1.500 dòng).

**Nếu làm tiếp.** Đây chính là hướng của bản SaaS: tách API (FastAPI) và giao diện web riêng để phục vụ nhiều trường; trong bản này thì tiếp tục chia nhỏ các file trang lớn.

---

## 8. PostgreSQL + pgvector, có dự phòng bằng file

**Vấn đề.** Cần lưu người dùng, lịch sử hoạt động, mô hình và vector tài liệu cho RAG, nhưng người chấm khoá luận cũng phải chạy được ứng dụng mà không cần dựng database.

**Các phương án đã cân nhắc.**
- Chỉ dùng file (JSON/CSV/joblib).
- PostgreSQL cho dữ liệu, thêm một vector database riêng (ví dụ Qdrant, Pinecone) cho RAG.
- **PostgreSQL + pgvector trong cùng một database, có dự phòng bằng file khi không cấu hình database.**

**Lý do chọn.** pgvector giữ dữ liệu quan hệ và vector ở cùng một nơi, dùng chung sao lưu, phân quyền và RLS, không thêm một dịch vụ phải vận hành. Dự phòng bằng file giúp chạy demo chỉ với `streamlit run`. Schema được quản lý bằng Alembic.

**Ưu điểm và hạn chế.**
- Ưu: một hệ quản trị dữ liệu duy nhất; chạy được cả khi không có database.
- Hạn chế: hai chế độ lưu trữ nghĩa là hai đường code phải giữ đồng bộ; bước 9 (22/11/2026) đã chuyển thêm các kho tệp còn lại (dự đoán, tư vấn, hoạt động, token AI, thuê bao, cấu hình AI) sang PostgreSQL, xem [docs/architecture/STEP9_FILE_STORES_TO_POSTGRES.md](architecture/STEP9_FILE_STORES_TO_POSTGRES.md); chế độ file vẫn còn cho bản demo.

**Nếu làm tiếp.** Tắt hẳn chế độ file ở môi trường production, chỉ giữ cho demo, để chỉ còn một đường code lưu dữ liệu.
