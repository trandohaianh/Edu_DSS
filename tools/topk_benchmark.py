"""FINAL REMAINING-GAPS CLOSURE Section 17 — bounded top-k benchmark.
Reuses the SAME 23-query/19-document standard benchmark set and the SAME
CURRENT PRODUCTION embedding model (all-MiniLM-L6-v2, already cached from
the prior pass's embedding benchmark - no new network download needed) to
compare k=3/5/8 on real, representative Vietnamese queries - not one
hand-picked example.

Run: PYTHONIOENCODING=utf-8 python tools/topk_benchmark.py
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

MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # current production model
K_VALUES = [3, 5, 8]


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def main():
    provider = MultiAIProvider()
    docs = provider._init_enhanced_knowledge_base()["documents"]
    print(
        f"Tổng số tài liệu: {len(docs)} | Tổng số truy vấn benchmark: {len(rag_evaluator.STANDARD_RAG_BENCHMARK_SET)}"
    )

    t0 = time.monotonic()
    doc_embeddings = {}
    for d in docs:
        text = f"{d['title']} {d['content']}"
        emb = provider.get_embedding(text, embedding_model_name=MODEL)
        if emb is not None:
            doc_embeddings[d["id"]] = np.array(emb)
    print(f"Đã tính embedding cho {len(doc_embeddings)}/{len(docs)} tài liệu trong {time.monotonic() - t0:.1f}s.")

    def _retrieval_fn(query_text: str, top_k: int):
        q_emb = provider.get_embedding(query_text, embedding_model_name=MODEL)
        if q_emb is None:
            return []
        q_emb = np.array(q_emb)
        scored = [{"id": doc_id, "score": _cosine(q_emb, doc_emb)} for doc_id, doc_emb in doc_embeddings.items()]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    print(f"\n=== TOP-K SWEEP (model={MODEL}) ===")
    print(
        f"{'k':>3s} {'Recall@k':>10s} {'Precision@k':>12s} {'MRR':>8s} {'nDCG@k':>8s} {'AvgLatency(ms)':>16s} {'IrrelevantChunks/query(avg)':>28s}"
    )
    all_results = {}
    for k in K_VALUES:
        result = rag_evaluator.evaluate_retrieval_pipeline(_retrieval_fn, k=k)
        s = result["summary"]
        # Irrelevant chunks per query at this k = k - (relevant hits within top-k, averaged)
        avg_irrelevant = k - (s["mean_recall_at_k"] * k if s["mean_recall_at_k"] <= 1 else k)
        all_results[k] = result
        print(
            f"{k:>3d} {s['mean_recall_at_k']:>10.4f} {s['mean_precision_at_k']:>12.4f} {s['mrr']:>8.4f} {s['mean_ndcg_at_k']:>8.4f} {s['avg_latency_ms']:>16.2f} {avg_irrelevant:>28.2f}"
        )

    print("\n=== CONTEXT SIZE IMPACT (ước lượng ký tự, không phải token thật) ===")
    avg_chunk_chars = sum(len(d.get("content", "")) for d in docs) / max(len(docs), 1)
    for k in K_VALUES:
        print(
            f"k={k}: ước lượng context ~{avg_chunk_chars * k:.0f} ký tự ({k} chunks x {avg_chunk_chars:.0f} ký tự/chunk trung bình)"
        )


if __name__ == "__main__":
    main()
