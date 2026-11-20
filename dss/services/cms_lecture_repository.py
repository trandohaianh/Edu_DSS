"""CMS Lecture Repository — kho bài giảng của Giảng viên (Course Management
System, NỘI DUNG BÀI GIẢNG) làm nguồn tri thức CHÍNH cho AI Learning Explainer.

LƯU Ý ĐẶT TÊN: đây là module RIÊNG BIỆT với dss/services/cms_repository.py
(module đó phục vụ mục đích khác — ánh xạ course→skill/competency và khớp
tài nguyên cho Career Decision Support System). Hai module cùng tiền tố "CMS"
nhưng KHÔNG liên quan, KHÔNG được gộp lại — bài giảng (lesson content phục vụ
AI giải thích bài học) và khung năng lực nghề nghiệp là hai miền dữ liệu khác
nhau hoàn toàn.

Nguyên tắc bắt buộc:
- Mọi tài liệu phải gắn course_id/lesson_id/topic_id — retrieval PHẢI lọc đúng
  phạm vi này, tuyệt đối không lấy nhầm tài liệu môn/bài khác (Mục 3).
- Versioning: khi Giảng viên cập nhật bài giảng, bản CŨ không bị xoá (vẫn có
  thể tra lịch sử) nhưng KHÔNG còn là "current" — retrieval mặc định (và do đó
  citation) chỉ dùng bản MỚI NHẤT (Mục 15).
- Tái sử dụng HẠ TẦNG RAG đã có (document_ingestion.py, chunking_service.py,
  vector_store.py, rag_namespaces.py) — không xây một vector store/ingestion
  pipeline riêng cho CMS.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dss.core.data_root import get_data_root
from dss.core.observability import observed
from dss.services import document_ingestion, vector_store
from dss.services.rag_namespaces import NAMESPACE_STUDENT_LEARNING

_LOCK = threading.Lock()


def _current_organization_id() -> int:
    raw = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip()
    if not raw:
        raise RuntimeError("EDUDSS_ORGANIZATION_ID is required when EDUDSS_CMS_STORE=postgres")
    return int(raw)


def _registry_path() -> Path:
    """PERF-002: tính lại từ get_data_root() mỗi lần gọi (không cache thành
    hằng số mức module) để test/E2E set EDUDSS_DATA_ROOT luôn được tôn trọng."""
    return get_data_root() / "cms" / "lessons_registry.json"


@dataclass
class LessonVersion:
    document_id: str
    version: int
    uploaded_at: str
    uploaded_by: str
    source_file: str


@dataclass
class CMSLesson:
    lesson_id: str
    course_id: str
    topic_id: str
    lecturer_id: str
    title: str
    learning_outcome: str = ""
    difficulty: str = "Standard"  # Foundation | Standard | Advanced (độ khó GỐC do GV gắn, khác Explanation Level cá nhân hoá)
    ai_enabled: bool = True
    official_source: bool = True
    current_document_id: Optional[str] = None
    versions: List[LessonVersion] = field(default_factory=list)
    faq: List[Dict[str, str]] = field(default_factory=list)  # [{"question":..., "answer":...}]
    explanation_notes: List[str] = field(default_factory=list)  # ghi chú bổ sung của GV cho AI tham khảo
    # Chính sách AI theo bài học do Giảng viên cấu hình (Mục 11) — AI PHẢI tuân
    # thủ, không có mặc định "cho phép tất cả" ngầm định ở tầng service khác.
    supplementary_allowed: bool = False  # Sinh viên chỉ thấy nút "giải thích thêm" nếu GV bật
    socratic_allowed: bool = True
    quiz_allowed: bool = True
    quiz_requires_approval: bool = True
    excluded_document_ids: List[str] = field(default_factory=list)  # tài liệu bị loại khỏi retrieval dù còn trong versions
    preferred_terminology: List[Dict[str, str]] = field(default_factory=list)  # [{"term":..., "preferred":...}]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CMSLesson":
        versions = [LessonVersion(**v) for v in d.get("versions", [])]
        d = dict(d)
        d["versions"] = versions
        return cls(**d)


def _load_registry() -> Dict[str, Dict[str, Any]]:
    registry_path = _registry_path()
    if not registry_path.exists():
        return {}
    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_registry(registry: Dict[str, Dict[str, Any]]) -> None:
    registry_path = _registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = registry_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, registry_path)


def get_lesson(lesson_id: str) -> Optional[CMSLesson]:
    from dss.core.persistence_config import is_postgres_enabled
    if is_postgres_enabled("CMS"):
        from dss.db.repositories import cms_repository
        raw = cms_repository.get_lesson(_current_organization_id(), lesson_id)
        return CMSLesson.from_dict(raw) if raw else None
    registry = _load_registry()
    data = registry.get(lesson_id)
    return CMSLesson.from_dict(data) if data else None


def list_lessons(course_id: Optional[str] = None) -> List[CMSLesson]:
    from dss.core.persistence_config import is_postgres_enabled
    if is_postgres_enabled("CMS"):
        from dss.db.repositories import cms_repository
        return [CMSLesson.from_dict(x) for x in cms_repository.list_lessons(_current_organization_id(), course_id)]
    registry = _load_registry()
    lessons = [CMSLesson.from_dict(d) for d in registry.values()]
    if course_id:
        lessons = [l for l in lessons if l.course_id == course_id]
    return lessons


def _upsert_lesson(lesson: CMSLesson) -> None:
    from dss.core.persistence_config import is_postgres_enabled
    if is_postgres_enabled("CMS"):
        from dss.db.repositories import cms_repository
        cms_repository.upsert_lesson(_current_organization_id(), lesson.to_dict())
        return
    with _LOCK:
        registry = _load_registry()
        lesson.updated_at = datetime.now(timezone.utc).isoformat()
        registry[lesson.lesson_id] = lesson.to_dict()
        _save_registry(registry)


def create_or_get_lesson(
    course_id: str, lesson_id: str, topic_id: str, lecturer_id: str, title: str,
    learning_outcome: str = "", difficulty: str = "Standard",
) -> CMSLesson:
    existing = get_lesson(lesson_id)
    if existing:
        return existing
    lesson = CMSLesson(
        lesson_id=lesson_id, course_id=course_id, topic_id=topic_id, lecturer_id=lecturer_id,
        title=title, learning_outcome=learning_outcome, difficulty=difficulty,
    )
    _upsert_lesson(lesson)
    return lesson


def set_ai_enabled(lesson_id: str, enabled: bool) -> None:
    lesson = get_lesson(lesson_id)
    if lesson:
        lesson.ai_enabled = enabled
        _upsert_lesson(lesson)


def mark_official_source(lesson_id: str, official: bool) -> None:
    lesson = get_lesson(lesson_id)
    if lesson:
        lesson.official_source = official
        _upsert_lesson(lesson)


def add_faq(lesson_id: str, question: str, answer: str) -> None:
    lesson = get_lesson(lesson_id)
    if lesson:
        lesson.faq.append({"question": question, "answer": answer})
        _upsert_lesson(lesson)


def add_explanation_note(lesson_id: str, note: str) -> None:
    lesson = get_lesson(lesson_id)
    if lesson:
        lesson.explanation_notes.append(note)
        _upsert_lesson(lesson)


def update_difficulty(lesson_id: str, difficulty: str) -> None:
    lesson = get_lesson(lesson_id)
    if lesson:
        lesson.difficulty = difficulty
        _upsert_lesson(lesson)


def set_policy_flag(lesson_id: str, field_name: str, value: bool) -> None:
    """Bật/tắt 1 cờ chính sách AI theo bài học (Mục 11) — field_name phải là
    một trong các cờ bool khai báo trên CMSLesson (supplementary_allowed,
    socratic_allowed, quiz_allowed, quiz_requires_approval)."""
    allowed_fields = {"supplementary_allowed", "socratic_allowed", "quiz_allowed", "quiz_requires_approval"}
    if field_name not in allowed_fields:
        raise ValueError(f"field_name không hợp lệ: {field_name}")
    lesson = get_lesson(lesson_id)
    if lesson:
        setattr(lesson, field_name, value)
        _upsert_lesson(lesson)


def add_preferred_terminology(lesson_id: str, term: str, preferred: str) -> None:
    lesson = get_lesson(lesson_id)
    if lesson:
        lesson.preferred_terminology.append({"term": term, "preferred": preferred})
        _upsert_lesson(lesson)


def exclude_document(lesson_id: str, document_id: str) -> None:
    """Loại 1 document_id (thường là 1 phiên bản CŨ) khỏi retrieval mà không
    xoá khỏi lịch sử versions — dùng khi GV phát hiện 1 bản cụ thể có lỗi."""
    lesson = get_lesson(lesson_id)
    if lesson and document_id not in lesson.excluded_document_ids:
        lesson.excluded_document_ids.append(document_id)
        _upsert_lesson(lesson)


def list_archived_versions(lesson_id: str) -> List[LessonVersion]:
    """Mục 7 — Giảng viên có thể tra cứu các phiên bản CŨ (không phải current),
    kể cả khi chúng không còn được dùng cho retrieval của Sinh viên."""
    lesson = get_lesson(lesson_id)
    if not lesson:
        return []
    return [v for v in lesson.versions if v.document_id != lesson.current_document_id]


@observed("cms.ingest")
def ingest_lecture_material(
    file_bytes: bytes,
    file_name: str,
    title: str,
    course_id: str,
    lesson_id: str,
    topic_id: str,
    lecturer_id: str,
    llm_integration: Any,
    learning_outcome: str = "",
    difficulty: str = "Standard",
    content_type: str = "slide",  # slide | pdf | note | document | transcript | exercise | example
    page_or_section: str = "",
) -> CMSLesson:
    """Nạp 1 tài liệu bài giảng — TỰ ĐỘNG tăng version nếu lesson đã tồn tại
    (Mục 15: bản cũ vẫn lưu lại, chỉ không còn là 'current'). Tái sử dụng
    document_ingestion.ingest_document() + chunking_service (qua đó) +
    vector_store — không viết lại pipeline trích xuất/phân đoạn."""
    from dss.services import engine_gateway
    if engine_gateway.enabled():
        actor = engine_gateway.authorize_staff_course(course_id)
        existing = get_lesson(lesson_id)
        if existing is not None and existing.course_id != course_id:
            raise PermissionError("Mã bài học đã thuộc một học phần khác.")
        lecturer_id = actor.username
    lesson = create_or_get_lesson(course_id, lesson_id, topic_id, lecturer_id, title, learning_outcome, difficulty)
    next_version = len(lesson.versions) + 1

    ingested = document_ingestion.ingest_document(
        file_bytes=file_bytes,
        file_name=file_name,
        title=title,
        course_id=course_id,
        version=str(next_version),
        permission_scope=NAMESPACE_STUDENT_LEARNING,
        uploaded_by=lecturer_id,
        lesson_id=lesson_id,
        topic_id=topic_id,
        lecturer_id=lecturer_id,
        learning_outcome=learning_outcome,
        difficulty=difficulty,
        content_type=content_type,
        page_or_section=page_or_section,
        official_source=lesson.official_source,
    )

    for chunk in ingested.chunks:
        if llm_integration and hasattr(llm_integration, "get_embedding"):
            chunk.embedding = llm_integration.get_embedding(chunk.content)

    vstore = vector_store.get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING)
    vstore.add_chunks(ingested.chunks)

    lesson.versions.append(LessonVersion(
        document_id=ingested.document_id, version=next_version,
        uploaded_at=ingested.created_at, uploaded_by=lecturer_id, source_file=file_name,
    ))
    lesson.current_document_id = ingested.document_id  # bản MỚI NHẤT luôn là "current"
    _upsert_lesson(lesson)
    engine_gateway.auto_sync_upload(course_id, lesson_id, ingested.chunks)
    return lesson


def retrieve_lesson_content(
    llm_integration: Any,
    query_text: str,
    course_id: Optional[str] = None,
    lesson_id: Optional[str] = None,
    topic_id: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Truy xuất nội dung CMS đúng phạm vi môn/bài/chủ đề, CHỈ lấy chunk thuộc
    document_id là bản 'current' (mới nhất) của lesson đó — bản cũ bị loại
    khỏi kết quả dù vẫn còn trong Vector Store (Mục 15).

    Trả về [] TRUNG THỰC nếu không có nội dung phù hợp — KHÔNG bịa evidence."""
    if lesson_id:
        lesson = get_lesson(lesson_id)
        if not lesson or not lesson.ai_enabled or not lesson.current_document_id:
            return []
        if lesson.current_document_id in lesson.excluded_document_ids:
            return []  # GV đã loại chính bản current (vd phát hiện lỗi) — trung thực trả rỗng, không rơi về bản cũ hơn
        allowed_document_ids = {lesson.current_document_id}
    elif course_id:
        lessons = [l for l in list_lessons(course_id) if l.ai_enabled and l.current_document_id]
        allowed_document_ids = {
            l.current_document_id for l in lessons if l.current_document_id not in l.excluded_document_ids
        }
    else:
        allowed_document_ids = None  # không giới hạn thêm ngoài namespace (hiếm khi dùng)

    query_embedding = llm_integration.get_embedding(query_text) if llm_integration else None
    if query_embedding is None:
        return []

    vstore = vector_store.get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING)
    # Lọc theo document_ids NGAY TRONG search() (trước khi xếp hạng/cắt top_k) —
    # KHÔNG overfetch-rồi-lọc-sau: overfetch một hằng số cố định (vd. top_k*4) sẽ
    # ngày càng dễ bỏ sót đúng nội dung khi kho vector chung tích luỹ thêm tài
    # liệu của môn/bài khác theo thời gian (lỗi thật đã phát hiện qua test khi
    # kho tích luỹ nhiều tài liệu từ các bộ test/tính năng khác chạy trước đó).
    raw_results = vstore.search(query_embedding, top_k=top_k * 3, document_ids=allowed_document_ids)

    if not topic_id:
        return raw_results[:top_k]

    filtered = [c for c in raw_results if (c.get("metadata", {}) or {}).get("topic_id") == topic_id]
    return filtered[:top_k]
