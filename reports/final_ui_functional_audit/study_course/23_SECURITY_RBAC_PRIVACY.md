# Bài 23 — Bảo mật, RBAC, và Quyền riêng tư

## 1. Mục tiêu buổi học

Hiểu 4 lớp bảo vệ của EduDSS: xác thực (authentication), phân quyền (RBAC), ẩn danh hóa
dữ liệu trước khi vào prompt AI (privacy), và chống tấn công chèn lệnh (prompt injection).

## 2. Kiến thức cần nhớ trước

Bài 1 (3 vai trò), Bài 16-18 (RAG, LLM Gateway — nơi dữ liệu đi vào prompt).

## 3. Giải thích từ con số 0

Có 2 câu hỏi bảo mật cơ bản với bất kỳ hệ thống nào: **"Bạn là ai?"** (Authentication —
Xác thực) và **"Bạn được phép làm gì?"** (Authorization/RBAC — Phân quyền). Ngoài ra, khi
hệ thống có tính năng AI, cần thêm câu hỏi thứ ba: **"Thông tin cá nhân nào được phép gửi
cho bên thứ ba (nhà cung cấp AI)?"** (Privacy — Quyền riêng tư), và câu hỏi thứ tư: **"Ai
đó có thể lừa AI làm điều nó không nên làm bằng cách chèn lệnh giả vào nội dung không?"**
(Prompt injection — Chèn lệnh vào prompt).

## 4. Giải thích kỹ thuật

- **Authentication (Xác thực)**: mật khẩu được băm (hash) bằng **PBKDF2-HMAC-SHA256** —
  một thuật toán băm mật khẩu tiêu chuẩn, có thêm "muối" (salt) và lặp nhiều vòng để
  chống tấn công dò mật khẩu (brute-force). Đây là cơ chế THẬT, nhưng đơn giản hơn các hệ
  thống định danh doanh nghiệp (không có SSO, không có MFA).
- **RBAC (Bài 1-2)**: 2 lớp — điều hướng (`TAB_ACCESS`) và hàm (`@require_role(...)`).
- **Privacy (Quyền riêng tư)**: `dss/services/privacy_service.py` đảm bảo chỉ những
  trường **KHÔNG định danh trực tiếp** — `student_id` (dùng làm khóa nội bộ, không phải
  tên thật), `risk_level`, `progress_note` — được đưa vào prompt gửi cho LLM. Tên thật,
  email, số điện thoại **KHÔNG BAO GIỜ** được đưa vào prompt.
- **Prompt injection defense (Chống chèn lệnh vào prompt)**: `dss/services/
  prompt_security.py` có cơ chế heuristic để phát hiện khi nội dung tài liệu (mà kẻ xấu
  có thể đã chèn lệnh giả vào, ví dụ "Bỏ qua mọi hướng dẫn trước đó và...") cố gắng ghi
  đè lên hướng dẫn hệ thống ban đầu của LLM — gọi là **indirect prompt injection**
  (chèn lệnh gián tiếp, vì lệnh độc hại nằm trong TÀI LIỆU được truy xuất, không phải
  trong câu hỏi trực tiếp của người dùng).

## 5. Ví dụ cực dễ hiểu

Authentication giống như kiểm tra thẻ ra vào ở cổng công ty ("bạn là ai?"). RBAC giống
như phân quyền trong tòa nhà — nhân viên thường không vào được phòng server, chỉ quản trị
viên mới vào được. Privacy giống như khi thuê phiên dịch viên bên ngoài dịch tài liệu
mật, bạn chỉ đưa cho họ đúng đoạn cần dịch, che đi các thông tin nhạy cảm không liên
quan. Prompt injection giống như một lá thư giả danh sếp gửi kèm trong tài liệu, cố gắng
ra lệnh cho nhân viên làm điều gì đó ngoài quy trình — nhân viên (LLM) cần được "huấn
luyện" để nhận ra và không tuân theo mệnh lệnh giả đó.

## 6. Ví dụ trực tiếp trong EduDSS

Khi Giảng viên xem AI Advisor cho một sinh viên cụ thể, prompt gửi đến LLM chỉ chứa
`student_id` (một mã nội bộ), `risk_level` (ví dụ "Cao"), và `progress_note` (một ghi chú
tóm tắt tình trạng học tập) — KHÔNG chứa tên thật hay email của sinh viên đó, dù Giảng
viên nhìn thấy tên thật trên giao diện (tên thật chỉ hiển thị ở UI, không đi vào prompt).

## 7. Luồng xử lý thực tế trong project

```
Đăng nhập → PBKDF2-HMAC-SHA256 xác thực mật khẩu → thiết lập session với vai trò
  → mọi request tiếp theo → kiểm tra TAB_ACCESS (điều hướng) + @require_role (hàm)
  → khi cần gọi AI (Bài 18) → privacy_service.py lọc chỉ giữ trường an toàn trước khi
    đưa vào prompt
  → khi RAG truy xuất tài liệu (Bài 16) → prompt_security.py kiểm tra nội dung tài liệu
    có dấu hiệu chèn lệnh độc hại không, trước khi đưa vào ngữ cảnh gửi LLM
```

## 8. Công thức nếu có

Không có công thức số học riêng — PBKDF2 là một thuật toán lặp hàm băm nhiều vòng, không
cần trình bày công thức toán chi tiết trong buổi bảo vệ trừ khi được hỏi sâu.

## 9. Giải thích từng ký hiệu trong công thức

Không áp dụng theo nghĩa công thức số học — nhưng cần nhớ: "salt" (muối) là một chuỗi
ngẫu nhiên thêm vào trước khi băm mật khẩu, giúp hai mật khẩu giống nhau của hai người
dùng khác nhau vẫn cho ra kết quả băm khác nhau, chống lại kiểu tấn công "rainbow table."

## 10. Cách đọc kết quả

Khi kiểm tra log hoặc prompt gửi đi, nếu chỉ thấy `student_id`/`risk_level`/
`progress_note` mà KHÔNG thấy tên/email/số điện thoại — đó là bằng chứng cơ chế privacy
hoạt động đúng.

## 11. Vì sao project dùng phương pháp này

Tách biệt rõ ràng "dữ liệu hiển thị cho người dùng nội bộ" (Giảng viên/Admin, có thể thấy
tên thật) và "dữ liệu gửi ra bên ngoài" (nhà cung cấp AI, chỉ thấy mã định danh nội bộ)
giúp giảm rủi ro rò rỉ thông tin cá nhân qua bên thứ ba.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Đây là các "mối quan tâm xuyên suốt" (cross-cutting concerns, Bài 2) — áp dụng cho MỌI
lớp, đặc biệt quan trọng tại điểm giao giữa hệ thống nội bộ và LLM Gateway (Bài 18, nơi
dữ liệu "rời khỏi" hệ thống để đến nhà cung cấp AI bên ngoài).

## 13. Input là gì

Thông tin đăng nhập (authentication); yêu cầu truy cập tài nguyên (RBAC); dữ liệu hồ sơ
sinh viên trước khi vào prompt (privacy); nội dung tài liệu được truy xuất (prompt
injection defense).

## 14. Output là gì

Quyết định cho phép/từ chối truy cập; một prompt đã được lọc an toàn; một cảnh báo nếu
phát hiện dấu hiệu chèn lệnh độc hại.

## 15. Output được chuyển cho module nào tiếp theo

Prompt đã lọc an toàn được chuyển cho LLM Gateway (Bài 18) để gọi AI.

## 16. Ưu điểm

Có nhiều lớp bảo vệ độc lập, có test coverage riêng cho từng lớp (xác thực, RBAC, privacy,
prompt injection).

## 17. Nhược điểm

Không có SSO/MFA (xác thực đa yếu tố); cơ chế chống prompt injection là heuristic, không
phải bảo đảm hình thức tuyệt đối.

## 18. Limitation thực tế của project

Xác thực phù hợp quy mô đồ án, không phải cấp độ doanh nghiệp; chưa có audit log dạng
SIEM (hệ thống quản lý sự kiện bảo mật chuyên nghiệp), chỉ là log JSON dạng phẳng
(flat-file).

## 19. Hội đồng có thể hỏi gì

"Làm sao bạn đảm bảo thông tin cá nhân của sinh viên không bị lộ ra ngoài qua AI?"

## 20. Câu trả lời ngắn 20–40 giây

"Em có một tầng lọc riêng (`privacy_service.py`) đảm bảo chỉ những trường KHÔNG định
danh trực tiếp — mã sinh viên nội bộ, mức độ rủi ro, ghi chú tiến độ — được đưa vào
prompt gửi cho nhà cung cấp AI bên ngoài. Tên thật, email, số điện thoại không bao giờ
xuất hiện trong nội dung gửi đi, dù chúng vẫn hiển thị bình thường trên giao diện nội bộ
cho Giảng viên/Admin xem."

## 21. Câu trả lời chi tiết

Trình bày cả 4 lớp bảo vệ ở mục 4, và ví dụ cụ thể ở mục 6 — nhấn mạnh sự tách biệt giữa
"hiển thị nội bộ" và "dữ liệu gửi ra ngoài."

## 22. Hội đồng có thể vặn tiếp thế nào

"Cơ chế chống prompt injection có đảm bảo tuyệt đối không bị vượt qua không?"

## 23. Cách trả lời câu vặn

"Không, và em không tuyên bố như vậy. Đây là một cơ chế heuristic — nó phát hiện được
các mẫu tấn công phổ biến đã biết, có test coverage riêng để xác minh, nhưng không phải
một bảo đảm hình thức (formal guarantee) chống lại mọi kỹ thuật tấn công có thể có trong
tương lai. Đây là một giới hạn thực tế em công khai thừa nhận."

## 24. Những câu không được nói

- "Hệ thống miễn nhiễm hoàn toàn với mọi kỹ thuật prompt injection."
- "Xác thực đạt chuẩn bảo mật doanh nghiệp (SSO/MFA)." (Sai — chưa có.)
- "Tên/email sinh viên có thể xuất hiện trong prompt gửi AI." (Sai — không bao giờ.)

## 25. 10 câu tự kiểm tra

1. Mật khẩu được băm bằng thuật toán nào?
2. RBAC có mấy lớp kiểm soát?
3. Những trường nào được phép đưa vào prompt gửi LLM?
4. Trường nào KHÔNG BAO GIỜ được đưa vào prompt?
5. Prompt injection gián tiếp (indirect) khác gì với trực tiếp?
6. `prompt_security.py` làm gì?
7. Salt trong băm mật khẩu dùng để làm gì?
8. Hệ thống có SSO/MFA không?
9. Cơ chế chống prompt injection có phải bảo đảm tuyệt đối không?
10. Log hoạt động trong EduDSS ở dạng gì?

## 26. Đáp án riêng

1. PBKDF2-HMAC-SHA256.
2. 2 lớp: điều hướng (TAB_ACCESS) và hàm (@require_role).
3. `student_id`, `risk_level`, `progress_note`.
4. Tên thật, email, số điện thoại.
5. Gián tiếp là lệnh độc hại nằm trong TÀI LIỆU được truy xuất, không phải trong câu hỏi
   trực tiếp của người dùng.
6. Phát hiện heuristic các dấu hiệu chèn lệnh độc hại trong nội dung tài liệu trước khi
   đưa vào ngữ cảnh gửi LLM.
7. Chống tấn công dò mật khẩu kiểu rainbow table, đảm bảo hai mật khẩu giống nhau vẫn cho
   kết quả băm khác nhau.
8. Không.
9. Không — là cơ chế heuristic, không phải bảo đảm hình thức tuyệt đối.
10. Dạng file JSON phẳng (flat-file), không phải hệ thống SIEM chuyên nghiệp.

## 27. 5 CÂU PHẢI THUỘC

1. "Mật khẩu băm bằng PBKDF2-HMAC-SHA256 — thật nhưng đơn giản, không có SSO/MFA."
2. "Chỉ student_id/risk_level/progress_note vào prompt AI — không bao giờ có tên/email/
   số điện thoại."
3. "Prompt injection gián tiếp: lệnh độc hại ẩn trong tài liệu được truy xuất, không phải
   trong câu hỏi trực tiếp."
4. "Cơ chế chống prompt injection là heuristic, có test coverage, KHÔNG phải bảo đảm tuyệt
   đối."
5. "RBAC có 2 lớp: điều hướng và hàm xử lý — đã xác minh không có route nào bị bỏ sót."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Authentication — Xác thực
- Authorization/RBAC — Phân quyền
- Privacy/Pseudonymization — Quyền riêng tư/Ẩn danh hóa
- Prompt injection (indirect) — Chèn lệnh vào prompt (gián tiếp)
- PBKDF2-HMAC-SHA256 — Thuật toán băm mật khẩu
