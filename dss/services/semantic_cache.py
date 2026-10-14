"""Layered Semantic Cache & Invalidation Engine cho EduDSS LMS.

Mục 20 & 21 Yêu cầu:
- Triển khai kiến trúc bộ đệm phân tầng (Layered Cache):
  + ExactCache: Khớp chính xác chuỗi truy vấn đã chuẩn hóa
  + SemanticCache: Khớp ngữ nghĩa theo vector embedding của câu hỏi (cosine similarity >= threshold)
  + RAGRetrievalCache: Đệm kết quả truy xuất tài liệu theo (query_hash, course_id, KB_version)
  + StudentPlanCache: Đệm kế hoạch học tập cá nhân (theo student_state_hash, plan_version)
- Các chiều định danh cache (Cache Dimensions):
  normalized_query, query_embedding, student_state_hash, course_id, topic,
  KB_version, model_version, plan_version, permission_scope
- TUYỆT ĐỐI KHÔNG tái sử dụng đầu ra cá nhân hóa giữa các sinh viên khác nhau chỉ vì câu hỏi giống nhau.
- Phân loại phạm vi (Cache Classes):
  GLOBAL (câu hỏi chung, quy định), COURSE (tri thức môn học), STUDENT (kế hoạch, tư vấn)
- Cơ chế vô hiệu hóa (Cache Invalidation):
  Tự động hủy khi student state thay đổi, làm xong diagnostic, có điểm mới, KB thay đổi,
  Production model thay đổi, hoặc plan hết hạn. Không sinh lại plan trên mỗi lượt Streamlit rerun.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


CACHE_CLASS_GLOBAL = "GLOBAL"
CACHE_CLASS_COURSE = "COURSE"
CACHE_CLASS_STUDENT = "STUDENT"


@dataclass
class CacheEntry:
    key: str
    cache_class: str
    content: Any
    created_at: float
    expires_at: float
    dimensions: Dict[str, Any]
    hit_count: int = 0
    query_embedding: Optional[List[float]] = None


class ExactCache:
    """Bộ đệm khớp chính xác theo khóa băm chuỗi."""

    def __init__(self, default_ttl_seconds: int = 3600):
        self._store: Dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self.default_ttl = default_ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            if time.time() > entry.expires_at:
                del self._store[key]
                return None
            entry.hit_count += 1
            return entry.content

    def set(self, key: str, content: Any, cache_class: str, dimensions: Dict[str, Any], ttl_seconds: Optional[int] = None) -> None:
        with self._lock:
            now = time.time()
            ttl = ttl_seconds or self.default_ttl
            self._store[key] = CacheEntry(
                key=key,
                cache_class=cache_class,
                content=content,
                created_at=now,
                expires_at=now + ttl,
                dimensions=dimensions,
            )

    def invalidate_by_dimension(self, dim_name: str, dim_value: Any) -> int:
        """Hủy các bản ghi đệm khớp với giá trị chiều cho trước."""
        with self._lock:
            keys_to_delete = [
                k for k, v in self._store.items()
                if v.dimensions.get(dim_name) == dim_value
            ]
            for k in keys_to_delete:
                del self._store[k]
            return len(keys_to_delete)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class SemanticCache:
    """Bộ đệm khớp ngữ nghĩa theo vector embedding cho các câu hỏi phổ quát (GLOBAL / COURSE)."""

    def __init__(self, similarity_threshold: float = 0.92, default_ttl_seconds: int = 7200):
        self._entries: List[CacheEntry] = []
        self._lock = threading.Lock()
        self.similarity_threshold = similarity_threshold
        self.default_ttl = default_ttl_seconds

    def lookup(
        self,
        query_embedding: List[float] | np.ndarray,
        cache_class: str,
        course_id: Optional[str] = None,
    ) -> Optional[Tuple[Any, float]]:
        """Tìm câu trả lời trong đệm ngữ nghĩa nếu cosine similarity >= threshold.
        TUYỆT ĐỐI không áp dụng semantic cross-student cho STUDENT cache class."""
        if cache_class == CACHE_CLASS_STUDENT:
            return None  # Không dùng semantic cache dùng chung cho dữ liệu riêng tư của sinh viên

        q_vec = np.array(query_embedding, dtype=np.float32)
        norm_q = np.linalg.norm(q_vec)
        if norm_q == 0:
            return None

        with self._lock:
            now = time.time()
            best_entry: Optional[CacheEntry] = None
            best_score = -1.0

            for entry in list(self._entries):
                if now > entry.expires_at:
                    self._entries.remove(entry)
                    continue
                if entry.cache_class != cache_class:
                    continue
                if course_id and entry.dimensions.get("course_id") != course_id:
                    continue
                if entry.query_embedding is None:
                    continue

                e_vec = np.array(entry.query_embedding, dtype=np.float32)
                norm_e = np.linalg.norm(e_vec)
                if norm_e == 0:
                    continue

                score = float(np.dot(q_vec, e_vec) / (norm_q * norm_e))
                if score > best_score:
                    best_score = score
                    best_entry = entry

            if best_entry and best_score >= self.similarity_threshold:
                best_entry.hit_count += 1
                return best_entry.content, best_score

            return None

    def store(
        self,
        key: str,
        content: Any,
        query_embedding: List[float] | np.ndarray,
        cache_class: str,
        dimensions: Dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> None:
        if cache_class == CACHE_CLASS_STUDENT:
            return  # Không lưu đệm ngữ nghĩa mở cho cá nhân sinh viên

        with self._lock:
            now = time.time()
            ttl = ttl_seconds or self.default_ttl
            q_list = query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else list(query_embedding)
            self._entries.append(
                CacheEntry(
                    key=key,
                    cache_class=cache_class,
                    content=content,
                    created_at=now,
                    expires_at=now + ttl,
                    dimensions=dimensions,
                    query_embedding=q_list,
                )
            )


class LayeredSemanticCache:
    """Hệ thống cache phân tầng hoàn chỉnh tích hợp Invalidation Engine."""

    def __init__(self):
        self.exact_cache = ExactCache()
        self.semantic_cache = SemanticCache()
        self._stats = {"exact_hits": 0, "semantic_hits": 0, "misses": 0}
        self._lock = threading.Lock()

    def build_student_state_hash(self, profile_dict: Dict[str, Any]) -> str:
        """Tạo mã băm đại diện cho trạng thái học tập hiện tại của sinh viên."""
        academic = profile_dict.get("academic", {})
        q_lvl = profile_dict.get("question_level", {})
        traj = profile_dict.get("trajectory", {})

        state_repr = {
            "quiz_avg": academic.get("quiz_average"),
            "assign_avg": academic.get("assignment_average"),
            "acc_rate": q_lvl.get("accuracy_rate"),
            "baseline": traj.get("historical_baseline_score"),
            "trend": traj.get("score_trend"),
        }
        raw_bytes = json.dumps(state_repr, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw_bytes).hexdigest()[:16]

    def get_student_plan(self, student_pseudonym: str, state_hash: str) -> Optional[Any]:
        """Lấy kế hoạch học tập đã đệm, bảo đảm đúng trạng thái và không bị rerun đè."""
        key = f"plan::{student_pseudonym}::{state_hash}"
        content = self.exact_cache.get(key)
        with self._lock:
            if content is not None:
                self._stats["exact_hits"] += 1
            else:
                self._stats["misses"] += 1
        return content

    def set_student_plan(self, student_pseudonym: str, state_hash: str, plan_data: Any, ttl_seconds: int = 86400) -> None:
        key = f"plan::{student_pseudonym}::{state_hash}"
        dimensions = {
            "student_pseudonym": student_pseudonym,
            "student_state_hash": state_hash,
            "cache_class": CACHE_CLASS_STUDENT,
        }
        self.exact_cache.set(key, plan_data, CACHE_CLASS_STUDENT, dimensions, ttl_seconds=ttl_seconds)

    def invalidate_student(self, student_pseudonym: str) -> int:
        """Hủy toàn bộ cache của sinh viên khi có dữ liệu điểm mới hoặc bài test mới."""
        return self.exact_cache.invalidate_by_dimension("student_pseudonym", student_pseudonym)

    def invalidate_course_kb(self, course_id: str) -> int:
        """Hủy toàn bộ cache môn học khi tri thức course cập nhật."""
        c1 = self.exact_cache.invalidate_by_dimension("course_id", course_id)
        with self.semantic_cache._lock:
            before = len(self.semantic_cache._entries)
            self.semantic_cache._entries = [
                e for e in self.semantic_cache._entries
                if e.dimensions.get("course_id") != course_id
            ]
            c2 = before - len(self.semantic_cache._entries)
        return c1 + c2

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._stats)


# Singleton layered cache
layered_cache = LayeredSemanticCache()
