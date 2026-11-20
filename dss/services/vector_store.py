"""Vector Store — Kiến trúc lưu trữ Vector cho quy mô LMS (PostgreSQL + pgvector & Local fallback).

Nguyên tắc:
- Môi trường Sản xuất (Production LMS): Sử dụng PostgreSQL + pgvector với chỉ mục HNSW
  để tìm kiếm vector dưới 10ms trên tập dữ liệu hàng triệu chunks. Hỗ trợ Hybrid Search
  kết hợp vector cosine distance (<=>) và full-text search (tsvector).
- Môi trường Phát triển & Demo (Local/Dev): Sử dụng LocalVectorStore phân vùng theo namespace
  (NumPy + JSON metadata) để bảo toàn 100% khả năng chạy độc lập không cần database ngoài.
"""
from __future__ import annotations

import json
from copy import deepcopy
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from dss.core.data_root import get_data_root
from dss.core.observability import observed

from dss.services.chunking_service import DocumentChunk
from dss.services.rag_namespaces import NAMESPACE_STUDENT_LEARNING


def _ordered_document_chunks(chunks):
    def position(chunk):
        value = (chunk.get("metadata") or {}).get("chunk_index")
        if isinstance(value, int) and not isinstance(value, bool):
            return value, str(chunk.get("chunk_id", ""))
        suffix = str(chunk.get("chunk_id", "")).rsplit("#c", 1)[-1]
        return (int(suffix) if suffix.isdecimal() else 0), str(chunk.get("chunk_id", ""))
    return sorted(chunks, key=position)


class BaseVectorStore(ABC):
    """Giao diện chuẩn hóa cho các hệ thống Vector Store."""

    @abstractmethod
    def add_chunks(self, chunks: List[DocumentChunk], embedding_model_name: str = "all-MiniLM-L6-v2") -> int:
        pass

    @abstractmethod
    def search(
        self,
        query_embedding: np.ndarray | List[float],
        top_k: int = 5,
        filter_scope: Optional[str] = None,
        document_ids: Optional[set] = None,
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def delete_document(self, document_id: str) -> bool:
        pass

    @abstractmethod
    def list_documents(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        pass

    def get_document_chunks(self, document_id: str, *, course_id: str) -> List[Dict[str, Any]]:
        """Read exact document/course content without embeddings or model calls.

        Implementations enforce their namespace and school storage boundaries.
        Caller services must separately enforce enrollment and document approval.
        """
        raise NotImplementedError("Plain document reads are unavailable for this backend.")

    @abstractmethod
    def update_document_metadata(self, document_id: str, updates: Dict[str, Any]) -> bool:
        """NHÓM F: cập nhật (merge) metadata của TẤT CẢ chunk thuộc 1 tài liệu —
        dùng cho quy trình duyệt/từ chối (approve/reject) mà KHÔNG cần xóa rồi
        nạp lại (tốn tính embedding lại từ đầu). Trả False nếu không tìm thấy
        tài liệu."""
        pass


class LocalVectorStore(BaseVectorStore):
    """Vector Store cục bộ lưu trữ theo Namespace trong data_warehouse/vector_stores/{namespace}."""

    def __init__(self, base_dir: Optional[str] = None, namespace: str = NAMESPACE_STUDENT_LEARNING):
        if base_dir:
            self.base_path = Path(base_dir) / namespace
        else:
            # PERF-002: get_data_root() được gọi TẠI ĐÂY (lúc khởi tạo), không
            # phải hằng số mức module — tôn trọng EDUDSS_DATA_ROOT do test/E2E
            # set trước khi vector store đầu tiên được tạo trong tiến trình.
            self.base_path = get_data_root() / "vector_stores" / namespace
        self.namespace = namespace
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.meta_file = self.base_path / "chunks_metadata.json"
        self.vectors_file = self.base_path / "embeddings.npy"
        self._lock = threading.Lock()
        self._memory_chunks: List[Dict[str, Any]] = []
        self._memory_embeddings: Optional[np.ndarray] = None
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        with self._lock:
            if self.meta_file.exists():
                try:
                    with open(self.meta_file, "r", encoding="utf-8") as f:
                        self._memory_chunks = json.load(f)
                except Exception:
                    self._memory_chunks = []
            else:
                self._memory_chunks = []

            if self.vectors_file.exists():
                try:
                    self._memory_embeddings = np.load(self.vectors_file)
                except Exception:
                    self._memory_embeddings = None
            else:
                self._memory_embeddings = None

    def _save_to_disk(self) -> None:
        # Atomic write
        tmp_meta = self.meta_file.with_suffix(".tmp")
        with open(tmp_meta, "w", encoding="utf-8") as f:
            json.dump(self._memory_chunks, f, ensure_ascii=False, indent=2)
        os.replace(tmp_meta, self.meta_file)

        if self._memory_embeddings is not None:
            tmp_vec = self.vectors_file.with_suffix(".tmp.npy")
            np.save(tmp_vec, self._memory_embeddings)
            os.replace(tmp_vec, self.vectors_file)

    @observed("rag.index", metadata=lambda self, chunks, **kwargs: {"backend": "local", "batch_size": len(chunks)})
    def add_chunks(self, chunks: List[DocumentChunk], embedding_model_name: str = "all-MiniLM-L6-v2") -> int:
        if not chunks:
            return 0

        with self._lock:
            new_meta = []
            new_vectors = []

            for c in chunks:
                c_dict = c.to_dict()
                emb = c.embedding
                if emb is None:
                    # Nếu chưa có embedding, tạo vector giả định 384 chiều hoặc chờ nạp
                    continue

                emb_arr = np.array(emb, dtype=np.float32)
                # Chuẩn hóa L2 norm
                norm = np.linalg.norm(emb_arr)
                if norm > 0:
                    emb_arr = emb_arr / norm

                new_vectors.append(emb_arr)
                # Bỏ trường embedding khỏi JSON metadata để nhẹ đĩa
                c_dict["embedding"] = None
                c_dict["embedding_model"] = embedding_model_name
                c_dict["namespace"] = self.namespace
                new_meta.append(c_dict)

            if not new_meta:
                return 0

            new_vec_matrix = np.vstack(new_vectors)

            if self._memory_embeddings is None or len(self._memory_chunks) == 0:
                self._memory_embeddings = new_vec_matrix
                self._memory_chunks = new_meta
            else:
                self._memory_embeddings = np.vstack([self._memory_embeddings, new_vec_matrix])
                self._memory_chunks.extend(new_meta)

            self._save_to_disk()
            return len(new_meta)

    @observed("rag.vector_search", metadata=lambda self, *args, **kwargs: {
        "backend": "local", "top_k": args[1] if len(args) > 1 else kwargs.get("top_k", 5)})
    def search(
        self,
        query_embedding: np.ndarray | List[float],
        top_k: int = 5,
        filter_scope: Optional[str] = None,
        document_ids: Optional[set] = None,
    ) -> List[Dict[str, Any]]:
        """`document_ids` (tuỳ chọn): nếu truyền vào, CHỈ xét các chunk thuộc
        đúng tập document_id này TRƯỚC khi xếp hạng/cắt top_k — bắt buộc phải
        lọc trước khi cắt, không phải sau, để phạm vi (course/lesson) luôn
        đúng dù kho vector chung đã tích luỹ rất nhiều tài liệu của nơi khác
        (nếu lọc sau khi đã cắt top_k theo điểm tương đồng toàn kho, nội dung
        đúng phạm vi có thể bị các tài liệu điểm cao hơn ở phạm vi khác chiếm
        hết chỗ trong top_k — lỗi thật đã phát hiện qua test khi kho tích luỹ
        nhiều tài liệu từ nhiều bộ test/tính năng khác nhau)."""
        with self._lock:
            if self._memory_embeddings is None or len(self._memory_chunks) == 0:
                return []

            q_arr = np.array(query_embedding, dtype=np.float32).reshape(1, -1)
            norm = np.linalg.norm(q_arr)
            if norm > 0:
                q_arr = q_arr / norm

            # Tính Cosine Similarity toàn bộ matrix
            scores = cosine_similarity(q_arr, self._memory_embeddings)[0]

            results = []
            for idx, score in enumerate(scores):
                chunk = dict(self._memory_chunks[idx])
                if document_ids is not None and chunk.get("document_id") not in document_ids:
                    continue
                scope = chunk.get("metadata", {}).get("permission_scope") or chunk.get("permission_scope")
                if filter_scope and scope and scope != filter_scope:
                    continue

                chunk["relevance_score"] = float(score)
                chunk["source"] = chunk.get("metadata", {}).get("source", "local_vector_store")
                chunk["title"] = chunk.get("metadata", {}).get("title", "Tài liệu học tập")
                results.append(chunk)

            results.sort(key=lambda x: x["relevance_score"], reverse=True)
            return results[:top_k]

    def delete_document(self, document_id: str) -> bool:
        with self._lock:
            if not self._memory_chunks:
                return False

            keep_indices = [
                i for i, c in enumerate(self._memory_chunks) if c.get("document_id") != document_id
            ]
            if len(keep_indices) == len(self._memory_chunks):
                return False

            self._memory_chunks = [self._memory_chunks[i] for i in keep_indices]
            if self._memory_embeddings is not None:
                self._memory_embeddings = self._memory_embeddings[keep_indices]

            self._save_to_disk()
            return True

    def get_document_chunks(self, document_id: str, *, course_id: str) -> List[Dict[str, Any]]:
        if not isinstance(document_id, str) or not document_id.strip() or not isinstance(course_id, str) or not course_id.strip():
            raise ValueError("Exact document_id and course_id are required.")
        with self._lock:
            chunks = [
                deepcopy({key: value for key, value in chunk.items() if key != "embedding"})
                for chunk in self._memory_chunks
                if chunk.get("document_id") == document_id and chunk.get("course_id") == course_id
                and chunk.get("namespace", self.namespace) == self.namespace
            ]
        return _ordered_document_chunks(chunks)

    def list_documents(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            docs_map: Dict[str, Dict[str, Any]] = {}
            for c in self._memory_chunks:
                doc_id = c.get("document_id")
                if not doc_id or doc_id in docs_map:
                    continue
                meta = c.get("metadata", {})
                docs_map[doc_id] = {
                    "document_id": doc_id,
                    "title": meta.get("title", doc_id),
                    "course_id": c.get("course_id"),
                    "source": meta.get("source"),
                    "permission_scope": meta.get("permission_scope", self.namespace),
                    "total_chunks": meta.get("total_chunks", 1),
                    "created_at": meta.get("created_at"),
                    # NHÓM F: trường quản trị — trang "Chờ duyệt" và
                    # document_approval_service đọc các trường này để hiển thị/
                    # kiểm tra thẩm quyền duyệt.
                    "status": meta.get("status"),
                    "doc_type": meta.get("doc_type"),
                    "issuer": meta.get("issuer"),
                    "official_ref": meta.get("official_ref"),
                    "uploaded_by": meta.get("uploaded_by"),
                    "approved_by": meta.get("approved_by"),
                    "approved_at": meta.get("approved_at"),
                    "review_note": meta.get("review_note"),
                    "content_hash": meta.get("content_hash"),
                    "effective_from": meta.get("effective_from"),
                    "expires_at": meta.get("expires_at"),
                }
            return list(docs_map.values())

    def update_document_metadata(self, document_id: str, updates: Dict[str, Any]) -> bool:
        with self._lock:
            found = False
            for c in self._memory_chunks:
                if c.get("document_id") == document_id:
                    meta = dict(c.get("metadata") or {})
                    meta.update(updates)
                    c["metadata"] = meta
                    found = True
            if found:
                self._save_to_disk()
            return found


class PgVectorStore(BaseVectorStore):
    """Triển khai Vector Store THẬT bằng PostgreSQL + pgvector (Phase 1B,
    migration order item 12) — dùng chính bảng `rag_documents`/`rag_chunks`
    đã có sẵn trong schema Alembic (dss/db/models.py, cột `embedding` kiểu
    `pgvector.sqlalchemy.Vector(384)` thật, có RLS theo organization_id) —
    KHÔNG dùng `DDL_SCHEMA` cũ (đã xoá): bảng đó không có organization_id/RLS,
    trùng tên nhưng KHÔNG tương thích với schema Phase 1 đang chạy thật.

    Tìm kiếm tương đồng chạy THẬT trong PostgreSQL qua toán tử `<=>` (cosine
    distance) của pgvector — KHÔNG tải toàn bộ vector vào RAM Python rồi tính
    bằng sklearn (đó là cách LocalVectorStore làm, phù hợp cho demo/dev, NHƯNG
    không phải "pgvector production wiring" như yêu cầu Phase 1B).

    `organization_id` bắt buộc (constructor hoặc EDUDSS_ORGANIZATION_ID) —
    mọi thao tác đều chạy trong 1 transaction có `SET LOCAL
    app.organization_id`, cùng cơ chế RLS đã dùng cho các repository khác.
    """

    def __init__(self, connection_url: str, organization_id: Optional[int] = None, namespace: str = NAMESPACE_STUDENT_LEARNING):
        self.connection_url = connection_url
        self.namespace = namespace
        if organization_id is None:
            raw = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip()
            organization_id = int(raw) if raw else None
        self.organization_id = organization_id
        self._is_connected = False
        self._engine = None
        self._test_connection()

    def _test_connection(self) -> None:
        try:
            from sqlalchemy import create_engine, text as sa_text
            self._engine = create_engine(self.connection_url, pool_pre_ping=True, future=True)
            with self._engine.connect() as conn:
                conn.execute(sa_text("SELECT 1"))
            self._is_connected = True
        except Exception:
            self._is_connected = False

    def is_available(self) -> bool:
        return self._is_connected

    def _require_organization_id(self) -> int:
        if self.organization_id is None:
            raise RuntimeError(
                "PgVectorStore requires an organization_id (pass it explicitly or set "
                "EDUDSS_ORGANIZATION_ID) — RAG content is tenant-scoped data."
            )
        return self.organization_id

    @observed("rag.index", metadata=lambda self, chunks, **kwargs: {"backend": "pgvector", "batch_size": len(chunks)})
    def add_chunks(self, chunks: List[DocumentChunk], embedding_model_name: str = "all-MiniLM-L6-v2") -> int:
        if not self._is_connected:
            raise RuntimeError("PostgreSQL / pgvector không khả dụng.")
        if not chunks:
            return 0
        from sqlalchemy import text as sa_text

        org_id = self._require_organization_id()
        inserted = 0
        with self._engine.begin() as conn:
            conn.execute(sa_text("SET LOCAL app.organization_id = :oid"), {"oid": str(org_id)})
            for c in chunks:
                if c.embedding is None:
                    continue
                doc_row = conn.execute(
                    sa_text(
                        "SELECT id FROM rag_documents WHERE organization_id = :org_id AND document_id = :doc_id"
                    ),
                    {"org_id": org_id, "doc_id": c.document_id},
                ).fetchone()
                if doc_row:
                    doc_row_id = doc_row[0]
                else:
                    meta = c.metadata or {}
                    # NHÓM F: gieo metadata quản trị (doc_type/issuer/status/...)
                    # từ chunk đầu tiên vào rag_documents lúc TẠO document row.
                    # FIX (POST_72H_MASTER_PRODUCTION_CLOSURE, incremental-sync
                    # live-test tự phát hiện): không nơi gọi nào (vd.
                    # cms_rag_lifecycle.py::upsert_and_reindex) từng gán "status"
                    # vào metadata chunk — meta.get("status") luôn trả None, và
                    # None được bind THẲNG vào INSERT, GHI ĐÈ default cột
                    # 'PENDING_REVIEW' của rag_documents.status bằng NULL cứng ->
                    # crash NotNullViolation ngay lần đầu chạy thật với Postgres
                    # (dev/test trước đây chỉ chạy LocalVectorStore nên không lộ
                    # ra). Mặc định PENDING_REVIEW khi thiếu — ĐÚNG với mô hình
                    # document governance (nội dung đồng bộ từ CMS/LMS PHẢI chờ
                    # duyệt, không được tự động trở thành APPROVED).
                    doc_row_id = conn.execute(
                        sa_text(
                            "INSERT INTO rag_documents (organization_id, document_id, title, source_type, "
                            "namespace, course_code, version, is_current, doc_type, issuer, official_ref, status, "
                            "approved_by, approved_at, review_note, content_hash, effective_from, "
                            "expires_at, created_at, updated_at) "
                            "VALUES (:org_id, :doc_id, :title, :source_type, :namespace, :course_id, 1, true, :doc_type, "
                            ":issuer, :official_ref, :status, :approved_by, :approved_at, :review_note, "
                            ":content_hash, :effective_from, :expires_at, now(), now()) "
                            "RETURNING id"
                        ),
                        {
                            "org_id": org_id, "doc_id": c.document_id,
                            "title": meta.get("title", c.document_id),
                            "source_type": meta.get("source_type", "DEMO"),
                            "namespace": self.namespace,
                            "course_id": c.course_id,
                            "doc_type": meta.get("doc_type"),
                            "issuer": meta.get("issuer"),
                            "official_ref": meta.get("official_ref"),
                            "status": meta.get("status") or "PENDING_REVIEW",
                            "approved_by": meta.get("approved_by"),
                            "approved_at": meta.get("approved_at"),
                            "review_note": meta.get("review_note"),
                            "content_hash": meta.get("content_hash"),
                            "effective_from": meta.get("effective_from"),
                            "expires_at": meta.get("expires_at"),
                        },
                    ).scalar_one()

                embedding_literal = "[" + ",".join(repr(float(x)) for x in c.embedding) + "]"
                conn.execute(
                    sa_text(
                        "INSERT INTO rag_chunks (document_id, chunk_id, content, embedding, source, "
                        "chunk_metadata, version, embedding_model, created_at, updated_at) "
                        "VALUES (:document_id, :chunk_id, :content, CAST(:embedding AS vector), :source, "
                        "CAST(:chunk_metadata AS json), 1, :embedding_model, now(), now()) "
                        "ON CONFLICT (chunk_id) DO UPDATE SET content = EXCLUDED.content, "
                        "embedding = EXCLUDED.embedding, chunk_metadata = EXCLUDED.chunk_metadata, "
                        "document_id = EXCLUDED.document_id, source = EXCLUDED.source, "
                        "embedding_model = EXCLUDED.embedding_model, updated_at = now()"
                    ),
                    {
                        "document_id": doc_row_id, "chunk_id": c.chunk_id, "content": c.content,
                        "embedding": embedding_literal, "source": (c.metadata or {}).get("source"),
                        "chunk_metadata": json.dumps(c.metadata or {}), "embedding_model": embedding_model_name,
                    },
                )
                inserted += 1
        return inserted

    @observed("rag.vector_search", metadata=lambda self, *args, **kwargs: {
        "backend": "pgvector", "top_k": args[1] if len(args) > 1 else kwargs.get("top_k", 5)})
    def search(
        self,
        query_embedding: np.ndarray | List[float],
        top_k: int = 5,
        filter_scope: Optional[str] = None,
        document_ids: Optional[set] = None,
    ) -> List[Dict[str, Any]]:
        """Real pgvector `<=>` (cosine distance) search — filtering by
        `document_ids` happens IN THE SQL WHERE clause, before `ORDER BY
        ... LIMIT`, matching the same overfetch-then-filter correctness bug
        class LocalVectorStore's own docstring warns about (filtering after
        cutoff can silently drop the right content once the store
        accumulates chunks from other courses/tests)."""
        if not self._is_connected:
            raise RuntimeError("PostgreSQL / pgvector không khả dụng.")
        from sqlalchemy import text as sa_text

        org_id = self._require_organization_id()
        query_vec = list(query_embedding) if not isinstance(query_embedding, list) else query_embedding
        embedding_literal = "[" + ",".join(repr(float(x)) for x in query_vec) + "]"

        where_clauses = ["rd.organization_id = :org_id"]
        params: Dict[str, Any] = {"org_id": org_id, "embedding": embedding_literal, "top_k": top_k}
        if document_ids is not None:
            if not document_ids:
                return []  # empty allow-list — honest empty result, not "no filter"
            where_clauses.append("rd.document_id = ANY(:doc_ids)")
            params["doc_ids"] = list(document_ids)

        sql = sa_text(
            "SELECT rc.chunk_id, rc.content, rc.source, rc.chunk_metadata, rd.document_id, rd.title, "
            "rd.course_code AS course_id, (rc.embedding <=> CAST(:embedding AS vector)) AS distance "
            "FROM rag_chunks rc JOIN rag_documents rd ON rd.id = rc.document_id "
            f"WHERE {' AND '.join(where_clauses)} "
            "ORDER BY rc.embedding <=> CAST(:embedding AS vector) "
            "LIMIT :top_k"
        )
        with self._engine.begin() as conn:
            conn.execute(sa_text("SET LOCAL app.organization_id = :oid"), {"oid": str(org_id)})
            rows = conn.execute(sql, params).fetchall()

        results = []
        for row in rows:
            metadata = row.chunk_metadata or {}
            if filter_scope:
                scope = metadata.get("permission_scope")
                if scope and scope != filter_scope:
                    continue
            results.append({
                "chunk_id": row.chunk_id, "document_id": row.document_id, "content": row.content,
                "course_id": row.course_id, "metadata": metadata,
                "relevance_score": 1.0 - float(row.distance),  # cosine distance -> similarity
                "source": row.source or metadata.get("source", "pgvector"),
                "title": row.title or metadata.get("title", "Tài liệu học tập"),
            })
        return results

    def delete_document(self, document_id: str) -> bool:
        if not self._is_connected:
            return False
        from sqlalchemy import text as sa_text

        org_id = self._require_organization_id()
        with self._engine.begin() as conn:
            conn.execute(sa_text("SET LOCAL app.organization_id = :oid"), {"oid": str(org_id)})
            result = conn.execute(
                sa_text("DELETE FROM rag_documents WHERE organization_id = :org_id AND document_id = :doc_id"),
                {"org_id": org_id, "doc_id": document_id},
            )
            return result.rowcount > 0

    def get_document_chunks(self, document_id: str, *, course_id: str) -> List[Dict[str, Any]]:
        if not isinstance(document_id, str) or not document_id.strip() or not isinstance(course_id, str) or not course_id.strip():
            raise ValueError("Exact document_id and course_id are required.")
        if not self._is_connected:
            raise RuntimeError("PostgreSQL document storage is unavailable.")
        from sqlalchemy import text as sa_text
        organization_id = self._require_organization_id()
        with self._engine.begin() as connection:
            connection.execute(sa_text("SELECT set_config('app.organization_id', :scope, true)"),
                               {"scope": str(organization_id)})
            rows = connection.execute(sa_text(
                "SELECT rc.chunk_id, rc.content, rc.source, rc.chunk_metadata, rd.document_id, rd.course_code AS course_id, rd.title "
                "FROM rag_chunks rc JOIN rag_documents rd ON rd.id = rc.document_id "
                "WHERE rd.organization_id = :school AND rd.namespace = :namespace "
                "AND rd.document_id = :document AND rd.course_code = :course AND rd.is_current = true"
            ), {"school": organization_id, "namespace": self.namespace,
                "document": document_id, "course": course_id}).mappings().all()
        return _ordered_document_chunks([{
            "chunk_id": row["chunk_id"], "document_id": row["document_id"],
            "course_id": row["course_id"], "content": row["content"],
            "source": row["source"], "title": row["title"], "metadata": row["chunk_metadata"] or {},
        } for row in rows])

    def list_documents(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self._is_connected:
            return []
        from sqlalchemy import text as sa_text

        org_id = self._require_organization_id()
        ns = namespace or self.namespace
        with self._engine.begin() as conn:
            conn.execute(sa_text("SET LOCAL app.organization_id = :oid"), {"oid": str(org_id)})
            rows = conn.execute(
                sa_text(
                    "SELECT document_id, title, course_code AS course_id, namespace, source_type, created_at, "
                    "doc_type, issuer, official_ref, status, approved_by, approved_at, review_note, "
                    "content_hash, effective_from, expires_at "
                    "FROM rag_documents WHERE organization_id = :org_id AND namespace = :ns AND is_current = true"
                ),
                {"org_id": org_id, "ns": ns},
            ).fetchall()
        return [
            {
                "document_id": r.document_id, "title": r.title, "course_id": r.course_id,
                "permission_scope": r.namespace, "source": r.source_type,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "doc_type": r.doc_type, "issuer": r.issuer, "official_ref": r.official_ref,
                "status": r.status, "approved_by": r.approved_by,
                "approved_at": r.approved_at.isoformat() if r.approved_at else None,
                "review_note": r.review_note, "content_hash": r.content_hash,
                "effective_from": r.effective_from.isoformat() if r.effective_from else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            }
            for r in rows
        ]

    def update_document_metadata(self, document_id: str, updates: Dict[str, Any]) -> bool:
        """NHÓM F: UPDATE các cột quản trị trên `rag_documents` — CHƯA kiểm thử
        với PostgreSQL thật (không có DB trong môi trường này, xem REPORT.md).
        Chỉ nhận các khóa đã có cột tương ứng (xem migration NHÓM F); khóa lạ bị
        bỏ qua để tránh SQL injection qua tên cột động."""
        if not self._is_connected:
            return False
        from sqlalchemy import text as sa_text

        allowed_columns = {
            "status", "approved_by", "approved_at", "review_note",
            "doc_type", "issuer", "official_ref", "effective_from", "expires_at",
            "content_hash",
        }
        set_fields = {k: v for k, v in updates.items() if k in allowed_columns}
        if not set_fields:
            return False

        org_id = self._require_organization_id()
        set_clause = ", ".join(f"{k} = :{k}" for k in set_fields)
        params: Dict[str, Any] = dict(set_fields)
        params.update({"org_id": org_id, "doc_id": document_id})
        with self._engine.begin() as conn:
            conn.execute(sa_text("SET LOCAL app.organization_id = :oid"), {"oid": str(org_id)})
            result = conn.execute(
                sa_text(
                    f"UPDATE rag_documents SET {set_clause}, updated_at = now() "
                    "WHERE organization_id = :org_id AND document_id = :doc_id"
                ),
                params,
            )
            return result.rowcount > 0


def get_vector_store(
    namespace: str = NAMESPACE_STUDENT_LEARNING,
    force_local: bool = False,
) -> BaseVectorStore:
    """Resolve the explicitly selected backend; a PostgreSQL failure never selects local."""
    from dss.core.persistence_config import is_postgres_enabled

    if not force_local and is_postgres_enabled("RAG"):
        from dss.db.session import _resolve_database_url
        pg_url = os.environ.get("PGVECTOR_URL") or _resolve_database_url()
        pg_store = PgVectorStore(pg_url, namespace=namespace)
        if not pg_store.is_available():
            raise RuntimeError("The configured PostgreSQL document store is unavailable.")
        return pg_store
    return LocalVectorStore(namespace=namespace)
