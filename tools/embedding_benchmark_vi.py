"""FINAL REMEDIATION PASS Mục 6 — Benchmark truy xuất tiếng Việt: so sánh model
embedding hiện tại (sentence-transformers/all-MiniLM-L6-v2, chủ yếu tiếng Anh)
với ứng viên đa ngôn ngữ (sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)
trên tập 23 truy vấn tiếng Việt (dss/services/rag_evaluator.py::STANDARD_RAG_BENCHMARK_SET),
đo trên 19 tài liệu mẫu thật (MultiAIProvider._init_enhanced_knowledge_base).

Chạy: PYTHONIOENCODING=utf-8 python tools/embedding_benchmark_vi.py
(cần tải model qua mạng nếu chưa có trong cache HF — đã xin phép người dùng
trước khi chạy, xem REPORT.md Mục "FINAL REMEDIATION PASS" phần Mục 6).

KHÔNG tự động đổi model production dù kết quả thế nào — chỉ đo và báo cáo.
"""

from __future__ import annotations

import sys
import time
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")

import numpy as np

from dss.core.models import MultiAIProvider
from dss.services import rag_evaluator

MODELS = [
    "sentence-transformers/all-MiniLM-L6-v2",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
]


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def run_for_model(provider: MultiAIProvider, model_name: str, docs: list[dict], k: int = 5):
    print(f"\n=== Model: {model_name} ===")
    t0 = time.monotonic()
    doc_embeddings = {}
    for d in docs:
        text = f"{d['title']} {d['content']}"
        emb = provider.get_embedding(text, embedding_model_name=model_name)
        if emb is not None:
            doc_embeddings[d["id"]] = np.array(emb)
    load_time = time.monotonic() - t0
    print(
        f"Đã tính embedding cho {len(doc_embeddings)}/{len(docs)} tài liệu trong {load_time:.1f}s (bao gồm thời gian tải model lần đầu nếu cần)."
    )

    def _retrieval_fn(query_text: str, top_k: int):
        q_emb = provider.get_embedding(query_text, embedding_model_name=model_name)
        if q_emb is None:
            return []
        q_emb = np.array(q_emb)
        scored = [{"id": doc_id, "score": _cosine(q_emb, doc_emb)} for doc_id, doc_emb in doc_embeddings.items()]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    result = rag_evaluator.evaluate_retrieval_pipeline(_retrieval_fn, k=k)
    return result


def main():
    provider = MultiAIProvider()
    docs = provider._init_enhanced_knowledge_base()["documents"]
    print(
        f"Tổng số tài liệu: {len(docs)} | Tổng số truy vấn benchmark: {len(rag_evaluator.STANDARD_RAG_BENCHMARK_SET)}"
    )

    all_results = {}
    for model_name in MODELS:
        all_results[model_name] = run_for_model(provider, model_name, docs)

    print("\n\n=== TỔNG HỢP (K=5) ===")
    print(f"{'Model':60s} {'Recall@5':>10s} {'Precision@5':>12s} {'MRR':>8s} {'nDCG@5':>8s} {'Avg latency(ms)':>16s}")
    for model_name, result in all_results.items():
        s = result["summary"]
        print(
            f"{model_name:60s} {s['mean_recall_at_k']:>10.4f} {s['mean_precision_at_k']:>12.4f} {s['mrr']:>8.4f} {s['mean_ndcg_at_k']:>8.4f} {s['avg_latency_ms']:>16.2f}"
        )

    print("\n=== CHI TIẾT THEO TRUY VẤN ===")
    for model_name, result in all_results.items():
        print(f"\n--- {model_name} ---")
        for d in result["details"]:
            status = "OK" if d["hits"] else "MISS"
            print(
                f"[{status}] {d['query_id']:28s} recall={d['recall']:.2f} mrr={d['mrr']:.2f} retrieved_top1={d['retrieved_ids'][0] if d['retrieved_ids'] else '—'} expected={d['expected_ids']}"
            )


if __name__ == "__main__":
    main()
