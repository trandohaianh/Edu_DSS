"""Document Ingestion Service — Đường ống tiếp nhận và xử lý tài liệu đa định dạng cho LMS.

Hỗ trợ các định dạng thực tế:
- PDF (qua pypdf nếu có, hoặc bộ bóc tách stream PDF chuẩn)
- DOCX (qua python-docx)
- PPTX (qua python-pptx hoặc xml slide parser)
- TXT / Markdown (UTF-8 plain text)
- LMS Course Content (JSON có cấu trúc: syllabus, bài giảng, bài tập, câu hỏi ôn tập)

Metadata chuẩn hóa:
- document_id, course_id, semester, title, source, version, permission_scope, uploaded_by, created_at, updated_at
- Bộ tài liệu mẫu 19 bài được lưu giữ dưới dạng DEMO knowledge.
"""

from __future__ import annotations

import io
import json
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dss.core.observability import observed
from dss.services import document_governance
from dss.services.chunking_service import DocumentChunk, SemanticChunker
from dss.services.rag_namespaces import (
    NAMESPACE_ADMIN_OPERATIONS,
    NAMESPACE_LECTURER_SUPPORT,
    NAMESPACE_STUDENT_LEARNING,
    validate_student_profile_not_in_knowledge,
)


@dataclass
class IngestedDocument:
    document_id: str
    course_id: str
    semester: str
    title: str
    source: str
    version: str
    permission_scope: str
    uploaded_by: str
    created_at: str
    updated_at: str
    raw_text: str
    chunks: List[DocumentChunk]


def extract_text_from_txt_or_md(file_bytes: bytes) -> str:
    """Đọc văn bản từ file TXT hoặc Markdown."""
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1", errors="ignore")


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Đọc văn bản từ file DOCX."""
    try:
        import docx

        doc = docx.Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        # Đọc thêm dữ liệu trong bảng
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    paragraphs.append(row_text)
        return "\n\n".join(paragraphs)
    except Exception:
        # Fallback XML parsing nếu docx gặp sự cố
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                xml_content = z.read("word/document.xml")
                tree = ET.fromstring(xml_content)
                text_pieces = [node.text for node in tree.iter() if node.text]
                return " ".join(text_pieces)
        except Exception as e:
            return f"Lỗi đọc DOCX: {e}"


def extract_text_from_pptx(file_bytes: bytes) -> str:
    """Đọc slide văn bản từ file PPTX."""
    try:
        # Thử import pptx
        from pptx import Presentation

        prs = Presentation(io.BytesIO(file_bytes))
        slides_text = []
        for idx, slide in enumerate(prs.slides, 1):
            slide_content = []
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    slide_content.append(shape.text.strip())
            if slide_content:
                slides_text.append(f"--- Slide {idx} ---\n" + "\n".join(slide_content))
        return "\n\n".join(slides_text)
    except ImportError:
        # Fallback bằng zip parser cho .pptx
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                slide_texts = []
                slide_files = sorted(
                    [f for f in z.namelist() if f.startswith("ppt/slides/slide") and f.endswith(".xml")]
                )
                for idx, sfile in enumerate(slide_files, 1):
                    xml_content = z.read(sfile)
                    tree = ET.fromstring(xml_content)
                    texts = [node.text for node in tree.iter() if node.text and node.text.strip()]
                    if texts:
                        slide_texts.append(f"--- Slide {idx} ---\n" + "\n".join(texts))
                return "\n\n".join(slide_texts)
        except Exception as e:
            return f"Lỗi đọc PPTX: {e}"


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Đọc văn bản từ file PDF."""
    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for idx, page in enumerate(reader.pages, 1):
            t = page.extract_text() or ""
            if t.strip():
                pages_text.append(f"--- Trang {idx} ---\n{t.strip()}")
        return "\n\n".join(pages_text)
    except ImportError:
        # Fallback stream parser cho PDF cơ bản
        try:
            raw = file_bytes.decode("latin-1", errors="ignore")
            import re

            # Lấy các khối text dạng (Hello world) Tj
            matches = re.findall(r"\((.*?)\)\s*Tj", raw)
            if matches:
                return " ".join(matches)
            return "Tài liệu PDF (Yêu cầu cài pypdf để trích xuất đầy đủ nội dung)."
        except Exception as e:
            return f"Lỗi đọc PDF: {e}"


def extract_text_from_lms_json(file_bytes: bytes) -> Tuple[str, Dict[str, Any]]:
    """Phân tích nội dung khóa học LMS dạng JSON (syllabus, module, bài học)."""
    try:
        data = json.loads(file_bytes.decode("utf-8"))
        parts = []
        title = data.get("title") or data.get("course_name") or "Khóa học LMS"
        parts.append(f"# {title}")

        if "description" in data:
            parts.append(f"Mô tả: {data['description']}")

        modules = data.get("modules") or data.get("lessons") or []
        for m in modules:
            m_title = m.get("title") or m.get("name") or "Chủ đề"
            parts.append(f"## {m_title}")
            if "content" in m:
                parts.append(str(m["content"]))
            if "objectives" in m:
                parts.append(f"Mục tiêu: {', '.join(m['objectives'])}")

        return "\n\n".join(parts), data
    except Exception as e:
        return f"Lỗi đọc LMS JSON: {e}", {}


@observed("rag.ingest")
def ingest_document(
    file_bytes: bytes,
    file_name: str,
    title: str,
    course_id: str = "GEN_COURSE",
    semester: str = "2026.1",
    version: str = "1.0",
    permission_scope: str = NAMESPACE_STUDENT_LEARNING,
    uploaded_by: str = "admin",
    chunk_size: int = 400,
    chunk_overlap: int = 80,
    doc_type: Optional[str] = None,
    issuer: str = "",
    official_ref: Optional[str] = None,
    effective_from: Optional[str] = None,
    expires_at: Optional[str] = None,
    **extra_metadata: Any,
) -> IngestedDocument:
    """Hàm chính tiếp nhận, kiểm tra bảo mật, bóc tách và phân đoạn tài liệu."""
    doc_id = f"doc_{uuid.uuid4().hex[:10]}"
    now_iso = datetime.now(UTC).isoformat()

    # Kiểm tra an toàn: Tuyệt đối không cho phép nạp hồ sơ sinh viên vào Vector Store
    validate_student_profile_not_in_knowledge({"title": title, "id": doc_id})

    ext = Path(file_name).suffix.lower()
    raw_text = ""

    if ext in (".txt", ".md"):
        raw_text = extract_text_from_txt_or_md(file_bytes)
    elif ext == ".docx":
        raw_text = extract_text_from_docx(file_bytes)
    elif ext == ".pptx":
        raw_text = extract_text_from_pptx(file_bytes)
    elif ext == ".pdf":
        raw_text = extract_text_from_pdf(file_bytes)
    elif ext == ".json":
        raw_text, _ = extract_text_from_lms_json(file_bytes)
    else:
        # Fallback text
        raw_text = extract_text_from_txt_or_md(file_bytes)

    # Phân đoạn ngữ nghĩa
    chunker = SemanticChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    base_meta = {
        "document_id": doc_id,
        "title": title,
        "course_id": course_id,
        "semester": semester,
        "version": version,
        "permission_scope": permission_scope,
        "source": file_name,
        "uploaded_by": uploaded_by,
        "created_at": now_iso,
    }
    # Cho phép người gọi (vd. CMS Repository — dss/services/cms_repository.py) đính
    # kèm metadata mở rộng (lesson_id, topic_id, lecturer_id, learning_outcome,
    # difficulty, official_source...) mà KHÔNG phải sửa chữ ký hàm mỗi khi có nhu
    # cầu mới — mọi chunk sinh ra đều mang theo các trường này để retrieval/citation
    # lọc/hiển thị đúng phạm vi (môn/bài/chủ đề) sau này.
    base_meta.update(extra_metadata)
    # NHÓM F (F-0c): mọi tài liệu tải lên PHẢI bắt đầu ở PENDING_REVIEW — không có
    # đường nào (kể cả qua **extra_metadata ở trên) để tự "duyệt" ngay lúc tải lên.
    # Áp dụng SAU extra_metadata.update() để ép đè bất kỳ giá trị status/approved_*
    # nào người gọi cố truyền vào.
    base_meta.update(
        document_governance.default_governance_metadata(
            doc_type=doc_type,
            issuer=issuer,
            official_ref=official_ref,
            content_hash=document_governance.compute_content_hash(raw_text),
            effective_from=effective_from,
            expires_at=expires_at,
        )
    )
    chunks = chunker.chunk_text(
        text=raw_text,
        document_id=doc_id,
        course_id=course_id,
        base_metadata=base_meta,
    )

    return IngestedDocument(
        document_id=doc_id,
        course_id=course_id,
        semester=semester,
        title=title,
        source=file_name,
        version=version,
        permission_scope=permission_scope,
        uploaded_by=uploaded_by,
        created_at=now_iso,
        updated_at=now_iso,
        raw_text=raw_text,
        chunks=chunks,
    )
