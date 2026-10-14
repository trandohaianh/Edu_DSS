"""Chunking Service — Đường ống phân đoạn ngữ nghĩa (Semantic Chunking Pipeline).

Cấu trúc mỗi đoạn (Chunk):
- chunk_id: Định danh duy nhất ({document_id}#c{index})
- document_id: Mã tài liệu cha
- course_id: Mã khóa học liên kết
- content: Nội dung đoạn văn bản
- token_count: Số lượng token ước tính
- metadata: Thông tin nguồn, tiêu đề, số thứ tự đoạn, phạm vi quyền
- embedding: Vector đại diện (nếu đã tính toán)

Thuật toán phân đoạn đệ quy tôn trọng ranh giới ngữ nghĩa:
Đoạn văn (\n\n) -> Câu (. / ? / !) -> Từ với độ chồng lặp (overlap) tùy chỉnh.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from dss.services.context_budget import approximate_token_count


@dataclass
class DocumentChunk:
    chunk_id: str
    document_id: str
    course_id: str
    content: str
    token_count: int
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


class SemanticChunker:
    """Bộ phân đoạn văn bản thông minh theo ngữ nghĩa cho tài liệu học tập LMS."""

    def __init__(self, chunk_size: int = 400, chunk_overlap: int = 80):
        if chunk_overlap >= chunk_size:
            chunk_overlap = chunk_size // 4
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def _split_into_paragraphs(self, text: str) -> List[str]:
        # Tách theo đoạn văn (\n\n hoặc nhiều dòng trống)
        paras = re.split(r"\n\s*\n", text.strip())
        return [p.strip() for p in paras if p.strip()]

    def _split_into_sentences(self, text: str) -> List[str]:
        # Tách theo câu kết thúc bằng dấu chấm, hỏi, than hoặc chấm phẩy
        sentences = re.split(r"(?<=[.?!;])\s+", text.strip())
        return [s.strip() for s in sentences if s.strip()]

    def chunk_text(
        self,
        text: str,
        document_id: str,
        course_id: str = "GEN_COURSE",
        base_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentChunk]:
        """Thực hiện phân đoạn văn bản thành danh sách DocumentChunk."""
        if not text or not str(text).strip():
            return []

        base_meta = dict(base_metadata or {})
        clean_text = str(text).strip()

        # Nếu văn bản ngắn hơn kích thước 1 chunk, giữ nguyên làm 1 chunk duy nhất
        if len(clean_text) <= self.chunk_size:
            chunk_id = f"{document_id}#c1"
            t_count = approximate_token_count(clean_text)
            meta = dict(base_meta)
            meta["chunk_index"] = 1
            meta["total_chunks"] = 1
            return [
                DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    course_id=course_id,
                    content=clean_text,
                    token_count=t_count,
                    metadata=meta,
                )
            ]

        # Phân đoạn đệ quy với sliding window và độ chồng lặp (overlap)
        raw_chunks: List[str] = []
        paragraphs = self._split_into_paragraphs(clean_text)

        current_piece = ""
        for para in paragraphs:
            # Nếu đoạn văn quá dài, chia nhỏ theo câu
            if len(para) > self.chunk_size:
                sentences = self._split_into_sentences(para)
                for sent in sentences:
                    if len(current_piece) + len(sent) + 1 <= self.chunk_size:
                        current_piece = f"{current_piece} {sent}".strip()
                    else:
                        if current_piece:
                            raw_chunks.append(current_piece)
                            # Tạo phần overlap từ đuôi của current_piece
                            overlap_start = max(0, len(current_piece) - self.chunk_overlap)
                            current_piece = current_piece[overlap_start:].strip()
                        if len(sent) > self.chunk_size:
                            # Cắt cưỡng bức nếu 1 câu dài hơn cả chunk_size
                            for idx in range(0, len(sent), self.chunk_size - self.chunk_overlap):
                                sub = sent[idx : idx + self.chunk_size].strip()
                                if sub:
                                    raw_chunks.append(sub)
                            current_piece = ""
                        else:
                            current_piece = f"{current_piece} {sent}".strip()
            else:
                if len(current_piece) + len(para) + 2 <= self.chunk_size:
                    current_piece = f"{current_piece}\n\n{para}".strip()
                else:
                    if current_piece:
                        raw_chunks.append(current_piece)
                        overlap_start = max(0, len(current_piece) - self.chunk_overlap)
                        current_piece = current_piece[overlap_start:].strip()
                    current_piece = f"{current_piece}\n\n{para}".strip()

        if current_piece and current_piece not in raw_chunks:
            raw_chunks.append(current_piece)

        # Đóng gói thành đối tượng DocumentChunk
        results = []
        total_chunks = len(raw_chunks)
        for idx, chunk_str in enumerate(raw_chunks, 1):
            chunk_id = f"{document_id}#c{idx}"
            t_count = approximate_token_count(chunk_str)
            meta = dict(base_meta)
            meta["chunk_index"] = idx
            meta["total_chunks"] = total_chunks

            results.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    course_id=course_id,
                    content=chunk_str,
                    token_count=t_count,
                    metadata=meta,
                )
            )

        return results
