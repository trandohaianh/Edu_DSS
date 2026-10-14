# Bài 24 — Kiểm thử (Testing) và Giới hạn hệ thống (Limitations)

## 1. Mục tiêu buổi học

Hiểu chính xác 445 test đã pass CHỨNG MINH điều gì, và — quan trọng không kém — 445 test
KHÔNG CHỨNG MINH điều gì. Đồng thời tổng hợp lại toàn bộ giới hạn thực tế của hệ thống đã
học rải rác qua các bài trước.

## 2. Kiến thức cần nhớ trước

Toàn bộ các bài trước — đây là bài tổng hợp.

## 3. Giải thích từ con số 0

Kiểm thử phần mềm (software testing) là quá trình chạy code với các đầu vào đã biết
trước và kiểm tra đầu ra có đúng như kỳ vọng không. Có nhiều LOẠI kiểm thử khác nhau:
- **Unit/Integration test (kiểm thử đơn vị/tích hợp)** — kiểm tra từng hàm/module hoặc
  sự phối hợp giữa vài module, chạy nhanh, không cần mở trình duyệt thật.
- **End-to-End (E2E) test (kiểm thử đầu-cuối)** — mô phỏng một người dùng thật thao tác
  trên trình duyệt thật (dùng công cụ Playwright), kiểm tra toàn bộ luồng từ giao diện
  đến kết quả cuối cùng.

## 4. Giải thích kỹ thuật

Baseline (mốc chuẩn) đã đóng băng của EduDSS: **417 test non-E2E + 28 test E2E = 445 test,
tất cả đều PASS** (trước lượt hoàn thiện trước bảo vệ ngày 2026-09-16, baseline là
403+23=426). Đây là kết quả kiểm thử tự động (pytest cho non-E2E, Playwright
cho E2E), cộng thêm một vòng kiểm thử thủ công (manual acceptance walkthrough) theo từng
vai trò với ảnh chụp màn hình và đo đạc DOM thực tế (ví dụ đo chiều cao thẻ bằng
`getBoundingClientRect()`).

**Điều 445 test CHỨNG MINH được:**
- Các hàm/luồng đã được kiểm tra hoạt động ĐÚNG như kỳ vọng THIẾT KẾ, tại THỜI ĐIỂM kiểm
  thử, với các trường hợp (test case) ĐÃ ĐƯỢC NGHĨ RA.
- Không có lỗi hồi quy (regression) — mỗi lỗi được sửa trong quá trình audit đều có một
  test tương ứng để đảm bảo lỗi đó không quay lại trong tương lai.

**Điều 445 test KHÔNG CHỨNG MINH được:**
- KHÔNG chứng minh "không có bug nào" — chỉ chứng minh "không có bug nào TRONG SỐ CÁC
  TRƯỜNG HỢP ĐÃ ĐƯỢC NGHĨ RA VÀ VIẾT THÀNH TEST." Vẫn có thể tồn tại lỗi ở những trường
  hợp chưa ai nghĩ đến viết test.
- KHÔNG tương đương với 100% code coverage (số test không phải phần trăm dòng code được
  chạy qua).
- KHÔNG chứng minh hệ thống hoạt động tốt dưới TẢI THỰC TẾ (chưa load-test, xem Bài 18).
- KHÔNG chứng minh chất lượng trên DỮ LIỆU THẬT (toàn bộ test dùng dữ liệu tổng hợp/demo,
  xem Bài 3).

## 5. Ví dụ cực dễ hiểu

Giống như một học sinh làm đúng 445/445 câu trong MỘT bộ đề ôn tập — điều đó chứng minh
học sinh nắm vững NHỮNG DẠNG BÀI đã ôn, nhưng không chứng minh học sinh sẽ làm đúng
TUYỆT ĐỐI MỌI câu hỏi có thể có trong kỳ thi thật, đặc biệt là những dạng bài chưa từng
xuất hiện trong bộ đề ôn tập.

## 6. Ví dụ trực tiếp trong EduDSS

Một ví dụ cụ thể về giá trị thực tế của test: khi sửa lỗi `CARD-HEIGHT-001` (chiều cao
thẻ không đều: 531/324/392px), việc đo đạc bằng `getBoundingClientRect()` TRƯỚC và SAU
khi sửa (kết quả sau: 531.25/531.25/531.25px đồng đều) là bằng chứng đo lường thực tế,
không phải phỏng đoán bằng mắt qua ảnh chụp màn hình.

## 7. Luồng xử lý thực tế trong project

```
Viết code / sửa lỗi
  → viết test tương ứng (pytest cho logic, Playwright cho luồng UI thật)
  → chạy toàn bộ 417 test non-E2E + 28 test E2E
  → nếu tất cả pass: coi là "an toàn để tiếp tục" (không có nghĩa là "hoàn hảo")
  → bổ sung kiểm thử thủ công (chụp màn hình, đo DOM) cho các khía cạnh UI khó tự động hóa
    hoàn toàn (ví dụ đánh giá trực quan về bố cục)
```

## 8. Công thức nếu có

Không có công thức toán — đây là bài về phương pháp luận kiểm thử (testing methodology).

## 9. Giải thích từng ký hiệu trong công thức

Không áp dụng.

## 10. Cách đọc kết quả

Khi thấy "445/445 PASS", đọc là: "Tại thời điểm đóng băng, toàn bộ các trường hợp kiểm
thử đã được nghĩ ra và viết thành test đều cho kết quả đúng như kỳ vọng." KHÔNG đọc là
"hệ thống hoàn hảo, không có lỗi."

## 11. Vì sao project dùng phương pháp này

Kết hợp test tự động (nhanh, lặp lại được, phát hiện lỗi hồi quy) với kiểm thử thủ công
có đo đạc thực tế (cho các khía cạnh khó tự động hóa như bố cục trực quan) tạo ra một quy
trình kiểm chứng đáng tin cậy hơn là chỉ dùng một loại kiểm thử duy nhất.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Đây là lớp "bảo hiểm chất lượng" bao trùm toàn bộ hệ thống — áp dụng cho mọi module đã
học từ Bài 1 đến Bài 23.

## 13. Input là gì

Code/tính năng cần kiểm chứng, cùng các trường hợp kiểm thử (test case) đã được thiết kế.

## 14. Output là gì

Kết quả PASS/FAIL cho từng test, tổng hợp thành báo cáo 445/445 PASS ở baseline đóng
băng.

## 15. Output được chuyển cho module nào tiếp theo

Không chuyển tiếp cho module xử lý nào — đây là điểm cuối của quy trình phát triển, quyết
định liệu một thay đổi có được coi là an toàn để giữ lại hay không.

## 16. Ưu điểm

Phát hiện sớm lỗi hồi quy, tạo niềm tin có căn cứ (không phải chỉ "cảm thấy ổn") về chất
lượng hệ thống tại một thời điểm cụ thể.

## 17. Nhược điểm

Không thể bao phủ MỌI trường hợp có thể xảy ra trong thực tế; test tốn thời gian duy trì
khi code thay đổi.

## 18. Limitation thực tế của project — TỔNG HỢP TOÀN BỘ GIỚI HẠN CỦA HỆ THỐNG

1. Toàn bộ dữ liệu là tổng hợp/demo, chưa dùng dữ liệu sinh viên thật (Bài 3).
2. Chưa có kết nối LMS/CMS ngoài thật (Bài 21).
3. PgVectorStore là stub, chưa hoạt động thật (Bài 21).
4. Knowledge Base: Create/Read/Delete có (Delete thêm từ 2026-09-16, chỉ cho backend
   đang hoạt động — LocalVectorStore), Update vẫn chưa có UI. Admin User Management chỉ
   có Create/Read, chưa có Update/Delete UI.
5. Concurrency (`MAX_CONCURRENT_REQUESTS=3`) chưa được load-test (Bài 18).
6. Accessibility mới được kiểm tra sơ bộ (spot-check), chưa có audit WCAG chính thức.
7. XGBoost Classifier không dùng GridSearchCV như 3 thuật toán còn lại (Bài 6).
8. R² cao trên tập dữ liệu mẫu là hiện tượng của cách sinh dữ liệu, không phải bằng chứng
   hiệu năng thực tế (Bài 3, 9).
9. Career Fit/Readiness là điểm số heuristic, không phải xác suất thống kê (Bài 20).
10. Cơ chế chống hallucination/prompt injection là heuristic, không phải bảo đảm hình
    thức tuyệt đối (Bài 17, 23).

## 19. Hội đồng có thể hỏi gì

"445 test pass có nghĩa là hệ thống không có lỗi đúng không?"

## 20. Câu trả lời ngắn 20–40 giây

"Không. 445 test pass có nghĩa là tất cả các trường hợp kiểm thử ĐÃ ĐƯỢC THIẾT KẾ đều
hoạt động đúng như kỳ vọng, và không có lỗi hồi quy nào xuất hiện lại. Nó KHÔNG phải bằng
chứng toán học rằng hệ thống hoàn toàn không có lỗi — vẫn có thể tồn tại các trường hợp
biên (edge case) chưa được nghĩ đến. 445 test cũng không tương đương 100% code coverage,
và toàn bộ được chạy trên dữ liệu tổng hợp, không phải dữ liệu thật."

## 21. Câu trả lời chi tiết

Dùng ví dụ "học sinh làm đúng bộ đề ôn tập" ở mục 5, liệt kê rõ điều test CHỨNG MINH được
và KHÔNG chứng minh được ở mục 4, và có thể tổng hợp toàn bộ 10 giới hạn ở mục 18 nếu
được hỏi "hệ thống còn thiếu gì."

## 22. Hội đồng có thể vặn tiếp thế nào

"Vậy làm sao thuyết phục hội đồng rằng hệ thống đủ tin cậy để bảo vệ, nếu còn nhiều giới
hạn như vậy?"

## 23. Cách trả lời câu vặn

"Giá trị khoa học của đồ án không nằm ở việc tuyên bố một hệ thống hoàn hảo không tì vết,
mà nằm ở việc CHỨNG MINH được một kiến trúc DSS đầy đủ, có phương pháp luận ML nghiêm
túc (chống leakage, GridSearchCV, so sánh đa thuật toán), một pipeline RAG có căn cứ, và
—quan trọng không kém— một quy trình audit trung thực đã tự phát hiện và ghi nhận rõ ràng
CHÍNH XÁC những gì còn hạn chế, thay vì che giấu chúng. Đây chính là điều một sản phẩm
nghiên cứu nghiêm túc cần thể hiện."

## 24. Những câu không được nói

- "445 test chứng minh hệ thống không có bug." (Sai.)
- "445 test tương đương 100% code coverage." (Sai.)
- "Hệ thống đã sẵn sàng triển khai production cho một trường đại học thật ngay bây giờ."
  (Sai — còn nhiều giới hạn đã liệt kê.)

## 25. 10 câu tự kiểm tra

1. Baseline test cuối cùng của EduDSS là bao nhiêu?
2. Test non-E2E và E2E khác nhau ở điểm nào?
3. 445 test CHỨNG MINH được điều gì?
4. 445 test KHÔNG chứng minh được điều gì?
5. Số lượng test có tương đương % code coverage không?
6. Kể tên ít nhất 5 giới hạn thực tế của hệ thống.
7. Vì sao vẫn cần kiểm thử thủ công (manual acceptance) dù đã có test tự động?
8. Ví dụ về đo đạc thực tế (không phải phỏng đoán) trong kiểm thử UI là gì?
9. Vì sao việc công khai giới hạn lại có giá trị khoa học?
10. Playwright dùng để làm gì trong quy trình kiểm thử của EduDSS?

## 26. Đáp án riêng

1. 417 non-E2E + 28 E2E = 445 (trước đó: 403+23=426) test, tất cả PASS.
2. Non-E2E kiểm tra từng hàm/module (nhanh, không cần trình duyệt); E2E mô phỏng người
   dùng thật trên trình duyệt thật.
3. Các trường hợp đã được thiết kế hoạt động đúng như kỳ vọng, không có lỗi hồi quy.
4. Không chứng minh không có bug tuyệt đối, không tương đương 100% coverage, không chứng
   minh hiệu năng dưới tải thực hoặc trên dữ liệu thật.
5. Không.
6. Ví dụ: dữ liệu tổng hợp, chưa có LMS/CMS thật, PgVectorStore stub, KB/User Management
   thiếu CRUD, chưa load-test.
7. Vì một số khía cạnh (bố cục trực quan, trải nghiệm thực tế) khó tự động hóa hoàn toàn
   bằng test script.
8. Đo chiều cao thẻ bằng `getBoundingClientRect()` trước/sau khi sửa lỗi CARD-HEIGHT-001.
9. Vì nó thể hiện tính trung thực khoa học và giúp người đọc/hội đồng đánh giá đúng phạm
   vi áp dụng thực tế của kết quả nghiên cứu.
10. Chạy các kịch bản kiểm thử E2E mô phỏng người dùng thật thao tác trên trình duyệt
    thật.

## 27. 5 CÂU PHẢI THUỘC

1. "445/445 test PASS: 417 non-E2E + 28 E2E, baseline hiện tại (trước đó là 426/426)."
2. "445 test KHÔNG chứng minh không có bug tuyệt đối — chỉ chứng minh không có lỗi trong
   các trường hợp đã được thiết kế."
3. "445 test không tương đương 100% code coverage."
4. "Toàn bộ test chạy trên dữ liệu tổng hợp, chưa kiểm chứng trên dữ liệu thật."
5. "Giá trị khoa học nằm ở tính trung thực khi công khai giới hạn, không phải ở việc
   tuyên bố hoàn hảo."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Unit/Integration test — Kiểm thử đơn vị/tích hợp
- End-to-End (E2E) test — Kiểm thử đầu-cuối
- Regression test — Kiểm thử hồi quy (chống lỗi cũ quay lại)
- Code coverage — Độ bao phủ mã nguồn
- Edge case — Trường hợp biên (chưa được lường trước)
