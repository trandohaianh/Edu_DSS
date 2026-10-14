# Bài 13 — SHAP (Giải thích mô hình)

## 1. Mục tiêu buổi học

Hiểu SHAP giải thích cái gì, phân biệt local explanation và global explanation, và khắc
sâu nguyên tắc: **SHAP KHÔNG CHỨNG MINH NHÂN QUẢ** — đây là câu bạn sẽ phải lặp lại nhiều
lần trong buổi bảo vệ.

## 2. Kiến thức cần nhớ trước

Bài 6 (Classification), Bài 8 (Regression) — SHAP giải thích cho các mô hình này.

## 3. Giải thích từ con số 0

Các mô hình như Random Forest hay XGBoost thường bị gọi là "hộp đen" (black box) — chúng
đưa ra dự đoán chính xác nhưng khó biết TẠI SAO chúng đưa ra dự đoán đó. **SHAP (SHapley
Additive exPlanations)** là một kỹ thuật giúp "mở hộp đen" ra một phần — nó cho biết mỗi
feature đầu vào đã đóng góp bao nhiêu vào một dự đoán cụ thể, theo hướng làm tăng hay
giảm kết quả dự đoán so với mức "trung bình" (baseline).

## 4. Giải thích kỹ thuật

SHAP dựa trên khái niệm toán học từ lý thuyết trò chơi hợp tác (cooperative game theory)
gọi là **giá trị Shapley (Shapley value)** — ý tưởng gốc: nếu nhiều "người chơi" (ở đây
là các feature) cùng hợp tác tạo ra một "phần thưởng" (ở đây là kết quả dự đoán), thì
đóng góp công bằng của mỗi người chơi được tính bằng cách xét TRUNG BÌNH đóng góp của họ
qua MỌI THỨ TỰ tham gia có thể có.

Có 2 loại giải thích:
- **Local explanation (giải thích cục bộ)**: giải thích cho MỘT dự đoán cụ thể — ví dụ
  "vì sao sinh viên A được dự đoán rủi ro cao?"
- **Global explanation (giải thích toàn cục)**: tổng hợp mức độ quan trọng trung bình của
  từng feature trên TOÀN BỘ tập dữ liệu — ví dụ "nhìn chung, feature nào ảnh hưởng nhiều
  nhất đến dự đoán của mô hình?"

## 5. Ví dụ cực dễ hiểu

Giống như một nhóm 3 người cùng nấu một nồi lẩu ngon (kết quả dự đoán). Để biết ai đóng
góp bao nhiêu vào độ ngon đó một cách công bằng, ta thử tưởng tượng mọi thứ tự có thể họ
tham gia bếp: nếu người A vào bếp một mình thì lẩu ra sao, thêm B vào thì cải thiện bao
nhiêu, thêm C nữa thì cải thiện tiếp bao nhiêu — làm vậy với MỌI thứ tự có thể (A→B→C,
B→A→C, C→B→A...) rồi lấy trung bình đóng góp riêng của từng người. Đó chính là ý tưởng
Shapley value.

## 6. Ví dụ trực tiếp trong EduDSS

Khi Giảng viên xem một dự đoán rủi ro cho sinh viên cụ thể (Classification, Bài 6), tab
SHAP hiển thị biểu đồ: "tỷ lệ điểm danh thấp" kéo dự đoán về phía RỦI RO CAO (+0.15), còn
"điểm dự án cao" kéo dự đoán về phía AN TOÀN (-0.10) — đây là local explanation cho đúng
1 sinh viên đó, KHÔNG áp dụng chung cho mọi sinh viên khác.

## 7. Luồng xử lý thực tế trong project

```
Mô hình đã huấn luyện (Classification/Regression) + một điểm dữ liệu cụ thể
  → dss/services/model_service.py::compute_shap_local_explanation()
  → tính giá trị Shapley cho từng feature của điểm dữ liệu đó
  → hiển thị biểu đồ đóng góp (feature nào kéo dự đoán lên/xuống, mức độ bao nhiêu)
  → (tùy chọn) tổng hợp trên nhiều điểm để ra global explanation
```

## 8. Công thức nếu có

```
φ_j = Σ_{S⊆F\{j}} [|S|!(|F|-|S|-1)! / |F|!] * [f(S∪{j}) - f(S)]
```

## 9. Giải thích từng ký hiệu trong công thức

- `φ_j` — giá trị Shapley của feature j — chính là "mức đóng góp công bằng" cần tìm.
- `F` — tập hợp toàn bộ các feature.
- `S` — một tập con bất kỳ của các feature, KHÔNG chứa feature j.
- `f(S)` — kết quả dự đoán của mô hình khi chỉ "biết" các feature trong tập S (các
  feature khác bị ẩn/thay bằng giá trị trung bình).
- `f(S∪{j}) - f(S)` — mức thay đổi kết quả dự đoán khi thêm feature j vào tập S — đây là
  "đóng góp biên" (marginal contribution) của feature j trong ngữ cảnh cụ thể của tập S.
- `|S|!(|F|-|S|-1)! / |F|!` — trọng số đảm bảo công thức tính trung bình công bằng qua
  MỌI thứ tự có thể các feature được "thêm vào" từng bước một.
- Tổng `Σ_{S⊆F\{j}}` — lấy trung bình đóng góp biên của feature j qua tất cả các tập con
  S có thể có.

## 10. Cách đọc kết quả

Giá trị `φ_j` dương → feature đó đẩy dự đoán TĂNG lên (so với baseline). Giá trị `φ_j`
âm → feature đó kéo dự đoán GIẢM xuống. Độ lớn `|φ_j|` → mức độ ảnh hưởng mạnh hay yếu.
**Đọc là "đóng góp vào con số dự đoán của MÔ HÌNH NÀY", không đọc là "nguyên nhân thực sự
trong đời thực."**

## 11. Vì sao project dùng phương pháp này

SHAP là phương pháp giải thích mô hình được công nhận rộng rãi trong ngành, có nền tảng
lý thuyết toán học chặt chẽ (Shapley value), và tương thích tốt với các mô hình cây
(Random Forest, XGBoost, LightGBM) mà EduDSS đang sử dụng.

## 12. Nó nằm ở đâu trong toàn bộ hệ thống

Nằm ngay sau Classification/Regression (Bài 6, 8) trong Chuỗi 1: `Prediction → SHAP →
Diagnosis Engine → Recommendation → Learning Plan`. SHAP là cầu nối biến một con số dự
đoán "vô tri" thành bằng chứng có thể diễn giải, làm đầu vào cho Diagnosis Engine.

## 13. Input là gì

Mô hình đã huấn luyện và một (hoặc nhiều) điểm dữ liệu cụ thể cần giải thích.

## 14. Output là gì

Danh sách các feature kèm giá trị đóng góp (φ_j) của chúng vào dự đoán.

## 15. Output được chuyển cho module nào tiếp theo

Chuyển cho Diagnosis Engine (Bài 14) như một phần "bằng chứng" (evidence) để chẩn đoán
nguyên nhân rủi ro.

## 16. Ưu điểm

Có nền tảng toán học chặt chẽ, công bằng (dựa trên trung bình mọi thứ tự đóng góp), áp
dụng được cho cả local và global explanation.

## 17. Nhược điểm

Tính toán tốn kém (số tập con S tăng theo cấp số mũ với số feature — trong thực tế dùng
các thuật toán xấp xỉ như TreeSHAP để tăng tốc); global SHAP summary có thể chậm với mẫu
lớn.

## 18. Limitation thực tế của project

SHAP chỉ giải thích được cái mà MÔ HÌNH đã học — nếu mô hình học sai hoặc học từ dữ liệu
tổng hợp có thiên lệch (Bài 3), SHAP sẽ trung thực phản ánh lại đúng cái thiên lệch đó,
chứ không "sửa" hay "phát hiện" ra sai lầm của mô hình.

## 19. Hội đồng có thể hỏi gì

"SHAP cho thấy feature X đóng góp lớn nhất — vậy có nghĩa là feature X là NGUYÊN NHÂN
gây ra rủi ro học tập không?"

## 20. Câu trả lời ngắn 20–40 giây

"Không. SHAP chỉ cho biết feature X đóng góp bao nhiêu vào KẾT QUẢ DỰ ĐOÁN của mô hình
này — đây là một phép phân rã đóng góp thống kê dựa trên giá trị Shapley, không phải một
phép kiểm định nhân quả (causal inference). Để khẳng định X thực sự GÂY RA rủi ro, cần
những phương pháp khác như thí nghiệm có đối chứng (randomized controlled trial) hoặc
các mô hình nhân quả chuyên biệt — điều đó nằm ngoài phạm vi của SHAP và ngoài phạm vi đồ
án này."

## 21. Câu trả lời chi tiết

Trình bày công thức Shapley value ở mục 8-9, nhấn mạnh nó chỉ đo "đóng góp biên trung
bình vào output của một hàm f cụ thể (chính là mô hình đã huấn luyện)" — hoàn toàn không
liên quan đến cơ chế nhân quả trong thế giới thực.

## 22. Hội đồng có thể vặn tiếp thế nào

"Vậy SHAP có giá trị gì nếu nó không chứng minh được nguyên nhân thật sự?"

## 23. Cách trả lời câu vặn

"Giá trị của SHAP nằm ở tính MINH BẠCH và KHẢ NĂNG KIỂM TRA — nó giúp Giảng viên hiểu mô
hình đang 'dựa vào' điều gì để đưa ra dự đoán, từ đó có thể phát hiện nếu mô hình đang
dựa vào một feature không hợp lý (ví dụ thiên lệch), và giúp việc chẩn đoán ở bước sau
(Diagnosis Engine) có bằng chứng cụ thể để tham khảo — chứ không phải để khẳng định quan
hệ nhân quả tuyệt đối."

## 24. Những câu không được nói

- "SHAP chứng minh feature X gây ra kết quả Y." (Sai — đây là câu tuyệt đối không được
  nói.)
- "SHAP hoạt động như một phép kiểm định thống kê nhân quả." (Sai.)

## 25. 10 câu tự kiểm tra

1. SHAP là viết tắt của gì?
2. Shapley value bắt nguồn từ lĩnh vực nào?
3. Local explanation khác global explanation ở điểm nào?
4. Công thức Shapley value là gì?
5. `f(S∪{j}) - f(S)` nghĩa là gì?
6. Giá trị φ_j dương/âm nghĩa là gì?
7. SHAP có chứng minh nhân quả không? Vì sao?
8. SHAP dùng để giải thích cho những mô hình nào trong EduDSS?
9. Output của SHAP được chuyển cho module nào tiếp theo?
10. Nhược điểm tính toán của SHAP là gì?

## 26. Đáp án riêng

1. SHapley Additive exPlanations.
2. Lý thuyết trò chơi hợp tác (cooperative game theory).
3. Local giải thích cho 1 dự đoán cụ thể; global tổng hợp mức độ quan trọng trên toàn bộ
   dữ liệu.
4. `φ_j = Σ_{S⊆F\{j}} [|S|!(|F|-|S|-1)!/|F|!] * [f(S∪{j})-f(S)]`.
5. Mức thay đổi kết quả dự đoán khi thêm feature j vào tập con S.
6. Dương → đẩy dự đoán tăng; âm → kéo dự đoán giảm, so với baseline.
7. Không — nó chỉ phân rã đóng góp thống kê vào output của mô hình, không phải kiểm định
   nhân quả.
8. Classification và Regression (Random Forest, XGBoost, LightGBM...).
9. Diagnosis Engine (Bài 14).
10. Tính toán tốn kém, số tập con tăng theo cấp số mũ với số feature.

## 27. 5 CÂU PHẢI THUỘC

1. "SHAP giải thích đóng góp của từng feature vào MỘT dự đoán cụ thể của MÔ HÌNH, dựa
   trên giá trị Shapley từ lý thuyết trò chơi."
2. "SHAP KHÔNG CHỨNG MINH NHÂN QUẢ — chỉ phân rã đóng góp thống kê."
3. "Local explanation giải thích 1 dự đoán; global explanation tổng hợp trên toàn bộ dữ
   liệu."
4. "Giá trị φ_j dương đẩy dự đoán tăng, âm kéo dự đoán giảm."
5. "SHAP là đầu vào bằng chứng cho Diagnosis Engine, không phải kết luận cuối cùng về
   nguyên nhân thực tế."

## 28. 5 TỪ KHÓA PHẢI NHỚ

- SHAP — Giải thích cộng dồn dựa trên giá trị Shapley
- Shapley value — Giá trị Shapley
- Local explanation — Giải thích cục bộ
- Global explanation — Giải thích toàn cục
- Causality (KHÔNG phải SHAP) — Quan hệ nhân quả
