"""RAG Evaluator — Bộ đánh giá định lượng chất lượng truy xuất thông tin (IR Metrics).

Đo lường:
- Recall@K: Tỷ lệ tài liệu liên quan được tìm thấy trong Top-K
- Precision@K: Tỷ lệ tài liệu trong Top-K thực sự phù hợp
- MRR (Mean Reciprocal Rank): Nghịch đảo vị trí xuất hiện đầu tiên của tài liệu chuẩn
- nDCG@K (Normalized Discounted Cumulative Gain): Đánh giá chất lượng xếp hạng có trọng số vị trí
- Retrieval Latency (ms): Thời gian phản hồi trung bình của bước truy xuất

Kèm tập truy vấn kiểm thử chuẩn hóa có gán nhãn (Labeled Ground-Truth Query Set).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class RAGTestCase:
    query_id: str
    query_text: str
    expected_doc_ids: List[str]
    topic: str
    description: str


# Tập truy vấn kiểm thử chuẩn hóa (Ground-Truth Test Set) cho EduDSS LMS
STANDARD_RAG_BENCHMARK_SET: List[RAGTestCase] = [
    RAGTestCase(
        query_id="q01_math",
        query_text="phương pháp học toán cao cấp đại số và giải tích",
        expected_doc_ids=["doc_001"],
        topic="Toán cao cấp",
        description="Truy vấn về tài liệu hướng dẫn học Toán cao cấp",
    ),
    RAGTestCase(
        query_id="q02_coding",
        query_text="cải thiện kỹ năng lập trình coding debug thực hành",
        expected_doc_ids=["doc_002"],
        topic="Lập trình",
        description="Truy vấn về cải thiện điểm và kỹ năng lập trình",
    ),
    RAGTestCase(
        query_id="q03_time",
        query_text="kỹ năng quản lý thời gian học tập pomodoro hàng tuần",
        expected_doc_ids=["doc_003"],
        topic="Kỹ năng mềm",
        description="Truy vấn về quản lý thời gian và Pomodoro",
    ),
    RAGTestCase(
        query_id="q04_methods",
        query_text="phương pháp học feynman và sơ đồ tư duy hiệu quả",
        expected_doc_ids=["doc_004"],
        topic="Phương pháp học",
        description="Truy vấn về phương pháp học Feynman",
    ),
    RAGTestCase(
        query_id="q05_stats",
        query_text="học tốt môn xác suất thống kê và phân tích số liệu mẫu",
        expected_doc_ids=["doc_014"],
        topic="Xác suất thống kê",
        description="Truy vấn về môn xác suất thống kê",
    ),
    RAGTestCase(
        query_id="q06_exam",
        query_text="kỹ năng làm bài kiểm tra thi cử trắc nghiệm và tự luận",
        expected_doc_ids=["doc_011"],
        topic="Kỹ năng thi cử",
        description="Truy vấn về kỹ năng làm bài kiểm tra và thi cử",
    ),
    RAGTestCase(
        query_id="q07_ml",
        query_text="machine learning học máy mô hình dự đoán overfitting",
        expected_doc_ids=["doc_019"],
        topic="Machine Learning",
        description="Truy vấn về Machine Learning căn bản",
    ),
    RAGTestCase(
        query_id="q08_stress",
        query_text="áp lực học tập căng thẳng tâm lý burnout và mất ngủ",
        expected_doc_ids=["doc_012"],
        topic="Sức khỏe tinh thần",
        description="Truy vấn về quản lý stress và tâm lý học tập",
    ),
    # FINAL REMEDIATION PASS Mục 6 (2026-09): mở rộng từ 8 lên 23 truy vấn để
    # phủ đủ 19/19 tài liệu mẫu (trước đây chỉ 8/19 có truy vấn kiểm thử) và
    # thêm 4 truy vấn "diễn đạt khác" (không dùng từ khóa trùng tiêu đề tài
    # liệu) để đo đúng khả năng hiểu ngữ nghĩa tiếng Việt, không phải chỉ
    # trùng khớp từ khóa bề mặt.
    RAGTestCase(
        query_id="q09_physics",
        query_text="học vật lý đại cương hiểu bản chất hiện tượng thí nghiệm",
        expected_doc_ids=["doc_005"],
        topic="Vật lý",
        description="Truy vấn về cải thiện điểm Vật lý",
    ),
    RAGTestCase(
        query_id="q10_chemistry",
        query_text="học hóa học bảng tuần hoàn phản ứng hóa học công thức",
        expected_doc_ids=["doc_006"],
        topic="Hóa học",
        description="Truy vấn về học tốt môn Hóa học",
    ),
    RAGTestCase(
        query_id="q11_reading",
        query_text="luyện kỹ năng đọc hiểu văn bản tóm tắt nội dung từ vựng",
        expected_doc_ids=["doc_007"],
        topic="Đọc hiểu",
        description="Truy vấn về cải thiện kỹ năng đọc hiểu",
    ),
    RAGTestCase(
        query_id="q12_history",
        query_text="học tốt môn lịch sử ghi nhớ sự kiện dòng thời gian",
        expected_doc_ids=["doc_008"],
        topic="Lịch sử",
        description="Truy vấn về học tốt môn Lịch sử",
    ),
    RAGTestCase(
        query_id="q13_english",
        query_text="học tiếng anh ngoại ngữ nghe nói đọc viết từ vựng ngữ pháp",
        expected_doc_ids=["doc_009"],
        topic="Tiếng Anh",
        description="Truy vấn về cải thiện Tiếng Anh / ngoại ngữ",
    ),
    RAGTestCase(
        query_id="q14_biology",
        query_text="học sinh học cơ chế quang hợp hô hấp tế bào di truyền",
        expected_doc_ids=["doc_010"],
        topic="Sinh học",
        description="Truy vấn về học tốt môn Sinh học",
    ),
    RAGTestCase(
        query_id="q15_presentation",
        query_text="kỹ năng thuyết trình trước đám đông và làm việc nhóm hiệu quả",
        expected_doc_ids=["doc_013"],
        topic="Kỹ năng mềm",
        description="Truy vấn về thuyết trình và làm việc nhóm",
    ),
    RAGTestCase(
        query_id="q16_writing",
        query_text="viết luận báo cáo học thuật luận điểm rõ ràng trích dẫn",
        expected_doc_ids=["doc_015"],
        topic="Kỹ năng viết",
        description="Truy vấn về viết luận và báo cáo học thuật",
    ),
    RAGTestCase(
        query_id="q17_selfstudy",
        query_text="phương pháp tự học nghiên cứu tài liệu ghi chú ôn tập",
        expected_doc_ids=["doc_016"],
        topic="Tự học",
        description="Truy vấn về kỹ năng tự học và nghiên cứu tài liệu",
    ),
    RAGTestCase(
        query_id="q18_database",
        query_text="học cơ sở dữ liệu truy vấn SQL phân tích dữ liệu làm sạch",
        expected_doc_ids=["doc_017"],
        topic="Cơ sở dữ liệu",
        description="Truy vấn về cơ sở dữ liệu và phân tích dữ liệu",
    ),
    RAGTestCase(
        query_id="q19_visualization",
        query_text="trực quan hóa dữ liệu chọn loại biểu đồ phù hợp",
        expected_doc_ids=["doc_018"],
        topic="Trực quan hóa dữ liệu",
        description="Truy vấn về trực quan hóa dữ liệu (Data Visualization)",
    ),
    # --- Truy vấn "diễn đạt khác" (paraphrase, không trùng từ khóa tiêu đề) ---
    RAGTestCase(
        query_id="q20_paraphrase_time",
        query_text="hay bị trễ deadline không biết sắp xếp việc học sao cho hợp lý",
        expected_doc_ids=["doc_003"],
        topic="Kỹ năng mềm (diễn đạt khác)",
        description="Paraphrase của q03 — không dùng từ 'quản lý thời gian'/'pomodoro'",
    ),
    RAGTestCase(
        query_id="q21_paraphrase_coding",
        query_text="code chạy sai suốt gỡ lỗi mãi không ra phải làm thế nào",
        expected_doc_ids=["doc_002"],
        topic="Lập trình (diễn đạt khác)",
        description="Paraphrase của q02 — không dùng từ 'kỹ năng lập trình'/'debug'",
    ),
    RAGTestCase(
        query_id="q22_paraphrase_stress",
        query_text="dạo này học nhiều quá mất ngủ và cảm thấy kiệt sức",
        expected_doc_ids=["doc_012"],
        topic="Sức khỏe tinh thần (diễn đạt khác)",
        description="Paraphrase của q08 — không dùng từ 'stress'/'áp lực học tập'",
    ),
    RAGTestCase(
        query_id="q23_paraphrase_ml",
        query_text="mô hình dự đoán học thuộc lòng dữ liệu huấn luyện không tổng quát được",
        expected_doc_ids=["doc_019"],
        topic="Machine Learning (diễn đạt khác)",
        description="Paraphrase của q07 — diễn giải 'overfitting' bằng lời thường, không dùng thuật ngữ",
    ),
]


def calculate_ndcg_at_k(retrieved_ids: List[str], expected_ids: Set[str], k: int = 5) -> float:
    """Tính toán nDCG@K với binary relevance (1 nếu nằm trong expected_ids, 0 nếu không)."""
    k_actual = min(k, len(retrieved_ids))
    if k_actual == 0 or not expected_ids:
        return 0.0

    # DCG
    dcg = 0.0
    for i in range(k_actual):
        doc_id = retrieved_ids[i]
        rel = 1.0 if doc_id in expected_ids else 0.0
        dcg += rel / math.log2(i + 2)  # vị trí i bắt đầu từ 0 -> log2(2), log2(3)...

    # IDCG (Ideal DCG)
    ideal_hits = min(k_actual, len(expected_ids))
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))

    return (dcg / idcg) if idcg > 0.0 else 0.0


def evaluate_retrieval_pipeline(
    retrieval_fn: Callable[[str, int], List[Dict[str, Any]]],
    test_cases: Optional[List[RAGTestCase]] = None,
    k: int = 5,
) -> Dict[str, Any]:
    """Hàm đánh giá toàn diện pipeline truy xuất RAG trên tập benchmark chuẩn."""
    cases = test_cases or STANDARD_RAG_BENCHMARK_SET
    total_cases = len(cases)
    if total_cases == 0:
        return {"error": "Tập test rỗng"}

    recalls = []
    precisions = []
    mrrs = []
    ndcgs = []
    latencies = []
    detailed_results = []

    for tc in cases:
        t0 = time.monotonic()
        results = retrieval_fn(tc.query_text, k)
        latency_ms = (time.monotonic() - t0) * 1000.0
        latencies.append(latency_ms)

        retrieved_ids = []
        for r in results:
            doc_id = str(r.get("document_id") or r.get("id") or "").strip()
            retrieved_ids.append(doc_id)

        expected_set = set(tc.expected_doc_ids)

        # 1. Recall@K: |Retrieved ∩ Expected| / |Expected|
        hits = [rid for rid in retrieved_ids if rid in expected_set]
        recall = len(hits) / float(len(expected_set)) if expected_set else 0.0
        recalls.append(recall)

        # 2. Precision@K: |Retrieved ∩ Expected| / K
        precision = len(hits) / float(k) if k > 0 else 0.0
        precisions.append(precision)

        # 3. MRR: 1 / rank của hit đầu tiên
        mrr = 0.0
        for rank, rid in enumerate(retrieved_ids, 1):
            if rid in expected_set:
                mrr = 1.0 / rank
                break
        mrrs.append(mrr)

        # 4. nDCG@K
        ndcg = calculate_ndcg_at_k(retrieved_ids, expected_set, k=k)
        ndcgs.append(ndcg)

        detailed_results.append({
            "query_id": tc.query_id,
            "query_text": tc.query_text,
            "expected_ids": tc.expected_doc_ids,
            "retrieved_ids": retrieved_ids,
            "hits": hits,
            "recall": round(recall, 4),
            "precision": round(precision, 4),
            "mrr": round(mrr, 4),
            "ndcg": round(ndcg, 4),
            "latency_ms": round(latency_ms, 2),
        })

    return {
        "summary": {
            "total_queries": total_cases,
            "k": k,
            "mean_recall_at_k": round(sum(recalls) / total_cases, 4),
            "mean_precision_at_k": round(sum(precisions) / total_cases, 4),
            "mrr": round(sum(mrrs) / total_cases, 4),
            "mean_ndcg_at_k": round(sum(ndcgs) / total_cases, 4),
            "avg_latency_ms": round(sum(latencies) / total_cases, 2),
            "p95_latency_ms": round(sorted(latencies)[int(0.95 * total_cases)], 2),
        },
        "details": detailed_results,
    }
