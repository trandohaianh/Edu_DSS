# Bộ đánh giá EduDSS

```bash
python evals/run_evals.py              # ML + RAG + an toàn AI (~3-5 phút trên 2 CPU)
python evals/run_evals.py --skip-ml    # RAG + an toàn AI (vài giây)
python evals/run_evals.py --update-baseline
```

Cổng chặn nằm ở `thresholds.json`. Ngoài ra không chỉ số nào được tụt quá 0,03 so với
`baselines/{full,fast}.json`. Kết quả ghi vào `reports/evals/` (JSON, Markdown, `history.jsonl`) và
tóm tắt trong CI. Workflow `.github/workflows/edudss-fullstack.yml` chạy bản đầy đủ, có cả RAG
embedding thật vì runner truy cập được Hugging Face.

## Đo gì

| Phần | Cách đo |
|---|---|
| **ML** | Trainer của chính app học trên cohort mô phỏng seed 42 (2.000 SV), chấm trên cohort **độc lập** seed 7 (1.000 SV). Đo: xếp loại (accuracy, macro-F1, so với dummy), điểm kỳ sau (MAE, R²), sàng lọc rủi ro (điểm kỳ sau < 6,0), và kiểm tra rò rỉ: cố tình đưa bản sao của nhãn làm đặc trưng, trainer phải loại nó. |
| **RAG** | 23 truy vấn có nhãn trên 19 tài liệu. Baseline TF-IDF luôn chạy. Embedding production chạy khi tải được mô hình. |
| **An toàn AI** | Bộ golden viết tay (lời khuyên có hại/an toàn, prompt injection tiếng Anh + tiếng Việt), cộng **bộ holdout** viết sau khi đã chỉnh bộ lọc và không bao giờ dùng để chỉnh. |

## Kết quả 16/11/2026 (Linux, Python 3.11, không có Hugging Face nên chưa chạy RAG embedding)

| Chỉ số | Giá trị |
|---|---|
| Xếp loại: accuracy / macro-F1 (dummy: 48,6%) | 95,7% / 0,817 |
| Điểm kỳ sau: MAE / R² (dummy MAE: 0,736) | 0,064 / 0,992 |
| Sàng lọc rủi ro (17,3% SV dưới 6,0): recall / precision | 96,5% / 91,8% |
| Rò rỉ nhãn bị chặn | Có |
| RAG TF-IDF: recall@5 / MRR | 95,7% / 0,957 |
| Golden: lời khuyên có hại bắt được / an toàn bị gắn nhầm | 100% / 0% |
| Golden: chặn prompt injection / làm hỏng câu hợp lệ | 100% / 0% |
| **Holdout:** lời khuyên có hại bắt được / an toàn bị gắn nhầm | **12,5% / 16,7%** |
| **Holdout:** chặn prompt injection | **50%** |

**Bộ eval tìm ra lỗi thật, đã sửa:**
- Bộ lọc injection chỉ có mẫu tiếng Anh nên chặn được 50% bộ golden; mọi câu tấn công tiếng Việt lọt
  qua. Đã thêm mẫu tiếng Việt, nay đạt 100%.
- Bộ phát hiện lời khuyên có hại gắn cờ nhầm câu *cảnh báo* gian lận ("Quy chế coi gian lận là vi
  phạm..."). Đã thêm xét ngữ cảnh cấm/phủ định, và thêm các mẫu thuê người làm hộ, nghe đáp án qua tai nghe.

## Cập nhật: bộ phân loại an toàn, dữ liệu học sinh thật, embedding đa ngôn ngữ

**Bộ phân loại an toàn học được** (`dss/services/safety_classifier.py`):
- Mô hình TF-IDF n-gram ký tự + từ, Logistic Regression, chạy sau bộ lọc từ khoá.
- Học từ `dss/resources/safety_train_v1.json`: 283 lời khuyên và 236 câu chèn lệnh, có các câu cấm
  đoán để mô hình học ngữ cảnh phủ định. Test kiểm tra tập này không trùng câu nào với tập đánh giá.
- Ngưỡng chọn bằng cross-validation trên tập train. Tắt được bằng `EDUDSS_SAFETY_CLASSIFIER=0`.

| Tập | Chỉ từ khoá | Từ khoá + bộ phân loại |
|---|---|---|
| Holdout v1: lời khuyên có hại bắt được / an toàn bị gắn nhầm | 12,5% / 16,7% | **75% / 16,7%** |
| Holdout v2 (viết trước khi huấn luyện): có hại / gắn nhầm | 10% / 0% | **65% / 0%** |
| Holdout v1: chặn chèn lệnh / làm hỏng câu hợp lệ | 50% / 0% | **100% / 0%** |
| Holdout v2: chặn chèn lệnh / làm hỏng câu hợp lệ | 26,7% / 0% | **93,3% / 0%** |

Lưu ý khi đọc bảng:
- Lần chạy đầu, bộ chèn lệnh gắn nhầm câu hỏi tiếng Anh và câu có chữ "hệ thống / bỏ qua / hướng
  dẫn". Tôi đã thêm câu hợp lệ dạng tổng quát vào **tập train** (không chép câu đánh giá), nên số
  liệu chèn lệnh trên holdout là **lạc quan**.
- Mọi tập do cùng một người viết. Trước khi đưa số liệu cho khách hàng cần một tập do bên thứ ba
  viết.
- Câu chèn lệnh bị phát hiện được **gắn nhãn cảnh báo, không bị xoá**, để báo nhầm không làm mất
  nội dung.

**Dữ liệu học sinh thật** (`ml_real`, xem `datasets/uci_student/README.md`):
- Bộ dữ liệu UCI Student Performance, 649 học sinh, giấy phép CC BY 4.0. Cảnh báo trượt khi G3 < 10
  (15,4% học sinh). Chạy 5 lần chia train/test khác nhau.

| Thời điểm cảnh báo | AUC | Recall / precision (ngưỡng chọn trên train) | Quy tắc đơn giản | ECE |
|---|---|---|---|---|
| Đầu kỳ (chưa có điểm) | 0,79 | 82% / 28% (cảnh báo 45% lớp) | "từng trượt môn": 45% / 52% | 0,065 |
| Giữa kỳ (có G1) | 0,92 | 82% / 54% (cảnh báo 24% lớp) | "G1 < 10": **88% / 58%** | 0,069 |

Phát hiện quan trọng:
- **Ngưỡng 0,5 mặc định chỉ bắt được 27–58% học sinh có nguy cơ.** Ngưỡng này tối ưu accuracy chứ
  không tối ưu việc không bỏ sót em nào, nên sai mục tiêu với hệ cảnh báo sớm. Eval nay chọn ngưỡng
  theo recall mục tiêu bằng xác suất out-of-fold trên tập train.
- **Ở giữa kỳ, mô hình không thắng quy tắc "G1 < 10".** Mọi màn hình cảnh báo phải hiện quy tắc
  này cạnh kết quả mô hình.
- Chênh lệch recall giữa nam/nữ và thành thị/nông thôn khoảng 0,11–0,20. Mỗi nhóm chỉ có 10–30 học
  sinh có nguy cơ mỗi lần chia nên phần lớn là nhiễu. Cổng chặn đặt ≤ 0,25.

**Embedding đa ngôn ngữ:**
- `EDUDSS_EMBEDDING_MODEL` cho phép đổi sang `paraphrase-multilingual-MiniLM-L12-v2`. Mô hình này
  cùng 384 chiều nên dùng chung bảng vector, nhưng phải re-index khi đổi.
- Eval đo cả hai mô hình (`rag_semantic_*` và `rag_semantic_multilingual_*`) trong CI, nơi có cache
  HuggingFace. Môi trường hiện tại không tải được mô hình nên **chưa có số đo**; mặc định vẫn là mô
  hình cũ cho tới khi CI cho thấy mô hình đa ngôn ngữ tốt hơn.

**Connector Moodle thật** (`dss/services/moodle_connector.py`):
- Gọi Moodle Web Services REST. Token gửi trong thân POST; tự thử lại khi gặp lỗi 5xx; báo rõ hàm nào
  chưa được bật trên Moodle.
- Ánh xạ sinh viên qua `idnumber` hoặc `username`; điểm quy về thang 10; tiến độ tính từ trạng thái
  hoàn thành hoạt động.
- Đã test với Moodle giả lập (11 test trong CI), **chưa test với Moodle thật của trường**.

**Chưa đạt, ghi nhận trung thực:**
- Bộ holdout cho thấy lọc theo từ khoá **không tổng quát hoá**. Đây chỉ là một lớp phụ; lớp bảo vệ
  chính vẫn là:
  - prompt có ranh giới XML;
  - chính sách hệ thống của mô hình;
  - phân quyền phía server (AI không bao giờ nhận dữ liệu của sinh viên khác).

  Bộ phân loại học được ở trên đã nâng holdout lên 65–75%. Muốn cao hơn cần mô hình đa ngôn ngữ đã
  tinh chỉnh hoặc LLM chấm.
- Dữ liệu mô phỏng gần như tuyến tính (R² 0,99), nên số liệu ML trên đó chỉ cho thấy pipeline đúng.
  Số liệu trên học sinh thật nằm ở phần `ml_real` phía trên (học sinh Bồ Đào Nha, không phải sinh
  viên Việt Nam).
