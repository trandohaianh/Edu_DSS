# Bài 5 — Train/Test Split, Cross-Validation, và Data Leakage

## 1. Mục tiêu buổi học

Đây là bài **quan trọng bậc nhất** để trả lời trôi chảy câu hỏi hội đồng hay hỏi nhất:
"Làm sao bạn đảm bảo không có data leakage?" Bạn phải thuộc lòng thứ tự xử lý thật trong
code, không phải lý thuyết chung chung.

## 2. Kiến thức cần nhớ trước

Bài 3 (feature/target), Bài 4 (tiền xử lý).

## 3. Giải thích từ con số 0

Khi huấn luyện một mô hình, bạn cần biết mô hình đó có thực sự "học được quy luật" hay
chỉ đang "học thuộc lòng" đúng những gì nó đã thấy. Để kiểm tra, người ta chia dữ liệu
thành hai phần: **tập huấn luyện (training set)** — mô hình được học từ đây, và **tập
kiểm tra (test set)** — mô hình chưa từng thấy, dùng để đánh giá khách quan. Nếu bất kỳ
thông tin nào từ tập test "rò rỉ" vào quá trình huấn luyện, kết quả đánh giá sẽ bị thổi
phồng giả tạo — đây gọi là **data leakage (rò rỉ dữ liệu)**, một trong những lỗi nghiêm
trọng và phổ biến nhất trong machine learning.

**Cross-validation (kiểm định chéo)** là một cách đánh giá chắc chắn hơn: thay vì chỉ chia
1 lần, chia dữ liệu train thành k phần (fold) bằng nhau, lần lượt dùng k-1 phần để học và
1 phần còn lại để kiểm tra, lặp lại k lần rồi lấy trung bình kết quả — giúp giảm rủi ro
"may mắn" hoặc "xui" chỉ vì một cách chia ngẫu nhiên.

## 4. Giải thích kỹ thuật

Thứ tự CHÍNH XÁC được xác minh trực tiếp trong `dss/core/trainers.py`:

1. `filter_leakage_features()` chạy ĐẦU TIÊN — loại bỏ các cột có tương quan quá cao với
   target (ví dụ nếu vô tình có một cột gần như sao chép giá trị target).
2. `train_test_split()` chạy TIẾP THEO — chia dữ liệu thành train/test, TRƯỚC bất kỳ bước
   tiền xử lý nào.
3. Pipeline (KNNImputer → StandardScaler → OneHotEncoder → SMOTE) chỉ được fit **bên
   trong từng fold train của `GridSearchCV`** (5-fold) — nghĩa là ngay cả trong quá trình
   tìm tham số tốt nhất, phần dữ liệu "test nội bộ" của mỗi fold cũng không bao giờ được
   dùng để fit tiền xử lý.
4. Tập test cuối cùng (hold-out test set) hoàn toàn không tham gia vào bất kỳ bước fit
   nào — chỉ được dùng transform (áp dụng tham số đã học) và đánh giá.

## 5. Ví dụ cực dễ hiểu

Giống như thi học kỳ: nếu thầy giáo cho học sinh xem trước đề thi để "luyện tập" (tập
train) rồi hôm sau thi lại đúng đề đó (tập test), điểm số học sinh đạt được sẽ rất cao
nhưng không phản ánh đúng năng lực thật — đó là "rò rỉ đề thi." Ngược lại, nếu đề thi
hoàn toàn mới, độc lập với các câu đã luyện tập, điểm số phản ánh đúng thực lực hơn.

## 6. Ví dụ trực tiếp trong EduDSS

Trong `ClassificationTrainer.train_and_evaluate()`: bước gọi `filter_leakage_features()`
diễn ra ngay dòng đầu hàm; ngay sau đó là `train_test_split(X, y, ...)`; Pipeline chứa
SMOTE chỉ được truyền vào làm `estimator` của `GridSearchCV(pipeline, param_grid,
cv=5,...)` — cơ chế nội bộ của `GridSearchCV` tự động đảm bảo pipeline chỉ fit trên phần
train của mỗi fold.

## 7. Luồng xử lý thực tế trong project

```
Dữ liệu đầy đủ
  → filter_leakage_features() [loại cột rò rỉ tiềm ẩn]
  → train_test_split() [chia train/test — KHÔNG preprocessing gì trước bước này]
  → GridSearchCV(Pipeline([Imputer, Scaler, Encoder, SMOTE, Model]), cv=5)
      → với mỗi fold: fit Pipeline CHỈ trên phần train của fold đó
      → đánh giá trên phần validation của fold đó (đã transform, không fit lại)
  → chọn bộ tham số tốt nhất theo trung bình 5 fold
  → fit lại Pipeline tốt nhất trên TOÀN BỘ tập train ban đầu
  → đánh giá cuối cùng trên tập test (hold-out), transform-only
```

## 8. Công thức nếu có

Không có công thức toán riêng — đây là bài về **quy trình (procedure)**, không phải công
thức số học. Công thức Z-score/SMOTE đã học ở Bài 4 vẫn áp dụng bên trong quy trình này.

## 9. Giải thích từng ký hiệu trong công thức

Không áp dụng — xem lại Bài 4 cho ký hiệu Z-score và SMOTE.

## 10. Cách đọc kết quả

Khi hội đồng hỏi về leakage, bạn không trả lời bằng lý thuyết chung — bạn trả lời bằng
đúng 4 bước ở mục 4, chứng minh bạn đã đọc code thật, không chỉ học thuộc khái niệm.

## 11. Vì sao project dùng phương pháp này

Đây là thực hành chuẩn (best practice) bắt buộc trong machine learning nghiêm túc — không
tuân thủ sẽ khiến mọi con số đánh giá (Accuracy, R², v.v.) trở nên vô nghĩa vì bị thổi
phồng giả tạo.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Đây là "luật chơi" bao trùm toàn bộ khâu huấn luyện — áp dụng cho cả Classification
(Bài 6) và Regression (Bài 8), là tiền đề cho GridSearchCV (Bài 10).

## 13. Input là gì

Dữ liệu đã qua `filter_leakage_features()`, sẵn sàng để chia.

## 14. Output là gì

Một mô hình đã huấn luyện với các chỉ số đánh giá đáng tin cậy trên tập test độc lập.

## 15. Output được chuyển cho module nào tiếp theo

Mô hình đã huấn luyện được lưu vào Model Registry với trạng thái `candidate` (Bài 22).

## 16. Ưu điểm

Đảm bảo con số đánh giá phản ánh đúng khả năng tổng quát hóa (generalization) của mô
hình, không bị thổi phồng.

## 17. Nhược điểm

Tốn nhiều thời gian tính toán hơn (mỗi fold phải fit lại toàn bộ pipeline từ đầu); với
dữ liệu nhỏ, chia train/test có thể làm giảm lượng dữ liệu học được.

## 18. Limitation thực tế của project

Cơ chế chống rò rỉ này giải quyết đúng vấn đề kỹ thuật (leakage trong quy trình), nhưng
KHÔNG giải quyết vấn đề khác: bản thân tập dữ liệu mẫu là tổng hợp và có target được tính
từ công thức tuyến tính (Bài 3) — đây là hai vấn đề độc lập, đừng nhầm lẫn khi trả lời.

## 19. Hội đồng có thể hỏi gì

"Bạn làm sao đảm bảo không có data leakage trong pipeline huấn luyện?"

## 20. Câu trả lời ngắn 20–40 giây

"Em đảm bảo bằng 3 lớp: một, `train_test_split` luôn chạy trước bất kỳ bước tiền xử lý
nào; hai, toàn bộ Imputer/Scaler/Encoder/SMOTE được gói trong một Pipeline chỉ fit bên
trong từng fold train của GridSearchCV, không bao giờ chạm vào phần test; ba, có một bước
lọc riêng gọi là `filter_leakage_features()` loại các cột tương quan bất thường với target
trước khi huấn luyện bắt đầu."

## 21. Câu trả lời chi tiết

Trình bày đầy đủ 4 bước ở mục 4, có thể vẽ sơ đồ luồng ở mục 7 lên bảng nếu được yêu cầu.

## 22. Hội đồng có thể vặn tiếp thế nào

"Nếu vậy tại sao R² của mô hình regression vẫn rất cao? Chẳng phải leakage vẫn xảy ra ở
đâu đó sao?"

## 23. Cách trả lời câu vặn

"Đây là câu hỏi rất hay, và em muốn tách rõ hai vấn đề khác nhau. Cơ chế chống leakage
trong quy trình huấn luyện là đúng đắn và đã được em xác minh trực tiếp trong code. R²
cao không đến từ leakage trong quy trình, mà đến từ cách TẬP DỮ LIỆU MẪU được sinh ra —
target của nó là một công thức tuyến tính có trọng số từ chính các feature khác cộng
nhiễu rất nhỏ (em đã trình bày chi tiết ở Bài 3). Đây là đặc điểm của dữ liệu tổng hợp,
không phải lỗi của quy trình huấn luyện."

## 24. Những câu không được nói

- "Không có leakage vì em không có thời gian kiểm tra kỹ." (Sai — phải trả lời bằng cơ
  chế cụ thể.)
- "R² cao vì mô hình rất chính xác." (Nhầm lẫn nguy hiểm — xem mục 23.)

## 25. 10 câu tự kiểm tra

1. Data leakage là gì?
2. Cross-validation giải quyết vấn đề gì?
3. Thứ tự đúng giữa `train_test_split` và tiền xử lý là gì?
4. `filter_leakage_features()` chạy ở bước nào?
5. Pipeline chứa SMOTE được fit ở đâu trong GridSearchCV?
6. Tập test cuối cùng có bao giờ được dùng để fit tiền xử lý không?
7. Nếu tiền xử lý fit trước khi chia train/test, hậu quả gì xảy ra?
8. Data leakage trong quy trình và R² cao do dữ liệu tổng hợp có phải cùng một vấn đề
   không?
9. 5-fold CV nghĩa là gì?
10. Vì sao phải fit lại pipeline tốt nhất trên toàn bộ tập train sau khi GridSearchCV
    chọn được tham số tốt nhất?

## 26. Đáp án riêng

1. Thông tin từ tập test (hoặc tương lai) vô tình ảnh hưởng đến quá trình huấn luyện,
   làm đánh giá bị thổi phồng giả tạo.
2. Đánh giá mô hình ổn định hơn, giảm rủi ro do một cách chia dữ liệu ngẫu nhiên may/rủi.
3. Chia train/test trước, tiền xử lý sau.
4. Ngay đầu tiên, trước cả `train_test_split`.
5. Chỉ bên trong từng fold train, không bao giờ chạm vào fold validation/test.
6. Không — chỉ transform, không fit.
7. Đánh giá mô hình bị lạc quan giả, không phản ánh đúng khả năng tổng quát hóa.
8. Không — đây là hai vấn đề độc lập (quy trình vs. bản chất dữ liệu mẫu).
9. Chia dữ liệu train thành 5 phần, lần lượt dùng 4 phần học và 1 phần kiểm tra, lặp 5
   lần rồi lấy trung bình.
10. Để tận dụng tối đa dữ liệu train có sẵn khi huấn luyện mô hình cuối cùng, thay vì chỉ
    dùng 4/5 dữ liệu như trong mỗi fold.

## 27. 5 CÂU PHẢI THUỘC

1. "`train_test_split` luôn chạy trước tiền xử lý — đây là nguyên tắc bất biến trong
   toàn bộ pipeline."
2. "Pipeline tiền xử lý chỉ fit bên trong fold train của GridSearchCV, không bao giờ
   chạm vào tập test."
3. "`filter_leakage_features()` chạy đầu tiên, loại các cột tương quan bất thường với
   target."
4. "Data leakage trong quy trình và R² cao do dữ liệu tổng hợp là hai vấn đề hoàn toàn
   khác nhau."
5. "Đây là 3 lớp bảo vệ độc lập: lọc leakage feature, thứ tự split-trước-preprocess, và
   pipeline fit-trong-fold."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- Train/test split — Chia tập huấn luyện/kiểm tra
- Cross-validation (CV) — Kiểm định chéo
- Data leakage — Rò rỉ dữ liệu
- Fold — Phần dữ liệu con trong kiểm định chéo
- Hold-out test set — Tập kiểm tra độc lập không tham gia huấn luyện
