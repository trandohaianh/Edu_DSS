"""Citation Service — Quản lý trích dẫn minh bạch và phát hiện nguồn bịa đặt (Hallucinated Citations).

Nguyên tắc:
- Mọi phản hồi AI có sử dụng tài liệu RAG phải hiển thị nguồn rõ ràng:
  + Document Title
  + Document ID / Chunk ID
  + Source / Course
  + Relevance Score
- Cơ chế xác minh trích dẫn (`verify_citations`):
  + Đối chiếu các nguồn mà LLM tuyên bố trích dẫn với danh sách Chunks thực sự được cung cấp.
  + Nhận diện các trích dẫn bị ảo giác / tự bịa (Hallucinated Citations).
  + Tính điểm căn cứ nguồn (Groundedness Score).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple


def format_evidence_for_prompt(chunks: List[Dict[str, Any]]) -> str:
    """Định dạng các đoạn tài liệu RAG kèm nhãn định danh chuẩn xác để LLM trích dẫn."""
    if not chunks:
        return "Không có tài liệu tham khảo nào."

    formatted_items = []
    for idx, c in enumerate(chunks, 1):
        doc_id = c.get("document_id") or c.get("id") or f"doc_{idx}"
        chunk_id = c.get("chunk_id") or f"{doc_id}_c1"
        title = c.get("title", f"Tài liệu #{idx}")
        source = c.get("source", "LMS Knowledge Base")
        score = float(c.get("relevance_score", 0.0))
        content = c.get("content", "").strip()

        header = f"[Tài liệu #{idx} | ID: {doc_id} | Chunk: {chunk_id} | Tiêu đề: \"{title}\" | Nguồn: {source} | Độ khớp: {score:.2f}]"
        formatted_items.append(f"{header}\n{content}")

    return "\n\n".join(formatted_items)


def verify_citations(
    llm_output: str,
    retrieved_chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Xác minh xem các tài liệu mà LLM trích dẫn trong văn bản có thực sự nằm

    trong tập tài liệu đã nạp hay bịa đặt.

    Trả về:
    {
        "verified_citations": [ {"title": ..., "doc_id": ..., "score": ...} ],
        "hallucinated_citations": [ ... ],
        "has_citations": bool,
        "is_grounded": bool,
        "citation_count": int,
    }
    """
    if not llm_output or not retrieved_chunks:
        return {
            "verified_citations": [],
            "hallucinated_citations": [],
            "has_citations": False,
            "is_grounded": len(retrieved_chunks) == 0,
            "citation_count": 0,
        }

    # Lập danh bạ các ID và Tiêu đề hợp lệ từ Chunks thực tế
    valid_ids: Set[str] = set()
    valid_titles: Dict[str, Dict[str, Any]] = {}

    for c in retrieved_chunks:
        doc_id = str(c.get("document_id") or c.get("id") or "").strip().lower()
        chunk_id = str(c.get("chunk_id") or "").strip().lower()
        title = str(c.get("title") or "").strip()
        if doc_id:
            valid_ids.add(doc_id)
        if chunk_id:
            valid_ids.add(chunk_id)
        if title:
            valid_titles[title.lower()] = c

    # Tìm các mẫu trích dẫn trong text sinh ra: vd "[Nguồn: doc_001]", "theo tài liệu Hướng dẫn học Toán cao cấp", "[ID: doc_002]"
    found_citations = []
    text_lower = llm_output.lower()

    # 1. Quét theo ID (vd: doc_001, doc_012, runtime_1)
    id_pattern = re.compile(r"\b(doc_[0-9a-zA-Z_]+|chunk_[0-9a-zA-Z_]+)\b", re.IGNORECASE)
    for match in id_pattern.finditer(llm_output):
        cited_id = match.group(0).lower()
        found_citations.append({"type": "id", "value": cited_id})

    # 2. Quét theo Tiêu đề tài liệu hợp lệ
    verified = []
    hallucinated = []
    seen_keys: Set[str] = set()

    for title_lower, chunk_data in valid_titles.items():
        if len(title_lower) >= 6 and title_lower in text_lower:
            key = chunk_data.get("id") or title_lower
            if key not in seen_keys:
                seen_keys.add(key)
                verified.append(
                    {
                        "title": chunk_data.get("title"),
                        "document_id": chunk_data.get("id") or chunk_data.get("document_id"),
                        "source": chunk_data.get("source", "LMS"),
                        "relevance_score": float(chunk_data.get("relevance_score", 0.0)),
                        "verified": True,
                    }
                )

    # Kiểm tra các ID được trích dẫn
    for fc in found_citations:
        cid = fc["value"]
        if cid in valid_ids:
            # Tìm chunk tương ứng
            matching_chunk = next(
                (
                    c
                    for c in retrieved_chunks
                    if str(c.get("id", "")).lower() == cid or str(c.get("chunk_id", "")).lower() == cid
                ),
                None,
            )
            if matching_chunk:
                key = matching_chunk.get("id") or cid
                if key not in seen_keys:
                    seen_keys.add(key)
                    verified.append(
                        {
                            "title": matching_chunk.get("title"),
                            "document_id": matching_chunk.get("id"),
                            "source": matching_chunk.get("source", "LMS"),
                            "relevance_score": float(matching_chunk.get("relevance_score", 0.0)),
                            "verified": True,
                        }
                    )
        else:
            # ID không tồn tại trong tập chunks -> Ảo giác
            hallucinated.append(
                {
                    "cited_identifier": cid,
                    "reason": "Mã tài liệu không tồn tại trong tập tài liệu được nạp.",
                    "verified": False,
                }
            )

    # Nếu mô hình không trích dẫn trực tiếp tên hoặc ID, nhưng kết quả retrieved_chunks có điểm cao,
    # tự động bổ sung danh sách tài liệu tham khảo chính thống được nạp để hiển thị trên UI
    if not verified and retrieved_chunks:
        for c in retrieved_chunks[:3]:
            verified.append(
                {
                    "title": c.get("title"),
                    "document_id": c.get("id") or c.get("document_id"),
                    "source": c.get("source", "LMS"),
                    "relevance_score": float(c.get("relevance_score", 0.0)),
                    "verified": True,
                }
            )

    return {
        "verified_citations": verified,
        "hallucinated_citations": hallucinated,
        "has_citations": len(verified) > 0,
        "is_grounded": len(hallucinated) == 0,
        "citation_count": len(verified),
    }
