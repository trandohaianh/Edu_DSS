"""Regulation Resolver — FINAL PRODUCTION GAP CLOSURE Phần 9.

Xác nhận trước khi xây: `AI_DECISION_ARCHITECTURE_34Q_MATRIX.md` (Q7-Q10)
kết luận NOT_IMPLEMENTED — hệ thống KHÔNG có mô hình University → Program →
Cohort → Regulation Version nào, không có cơ chế "resolve" quy chế đúng
phiên bản theo thời điểm. Đây là điểm bắt đầu "production-quality minimum"
theo đúng mô hình yêu cầu.

Kiến trúc (tách 2 tầng, giống `document_governance.py` + `vector_store.py`
đã dùng cho RAG governance — tách logic THUẦN khỏi tầng lưu trữ):
  1. `RegulationVersion` (dataclass) + `resolve_regulation()` — hàm THUẦN,
     không I/O, nhận vào danh sách ứng viên đã có sẵn (do tầng lưu trữ cung
     cấp) và chọn ĐÚNG 1 bản quy chế theo organization/program/cohort/thời
     điểm. Test được đầy đủ không cần DB.
  2. `LocalRegulationStore` — lưu trữ JSON cục bộ (cùng mẫu với
     `LocalVectorStore` trong vector_store.py — namespace hoá theo thư mục,
     KHÔNG cần Postgres). Backend Postgres thật (bảng `regulation_versions`
     + migration Alembic) là CÔNG VIỆC CHƯA LÀM trong đợt này — xem
     FINAL_PRODUCTION_GAP_REPORT.md — vì không thể runtime-verify migration
     mới trên DB thật trong phiên này (BLOCKED_BY_RUNNING_SIMULATION).

Nguyên tắc: `resolve_regulation()` là NƠI DUY NHẤT quyết định đúng phiên bản
quy chế — LLM/Agent KHÔNG BAO GIỜ tự chọn quy chế.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timezone
from typing import Any, Dict, List, Optional

STATUS_DRAFT = "DRAFT"
STATUS_PENDING_REVIEW = "PENDING_REVIEW"
STATUS_APPROVED = "APPROVED"
STATUS_RETIRED = "RETIRED"

_VALID_STATUSES = {STATUS_DRAFT, STATUS_PENDING_REVIEW, STATUS_APPROVED, STATUS_RETIRED}


@dataclass
class RegulationVersion:
    """1 phiên bản quy chế học vụ — tối thiểu theo đúng yêu cầu Phần 9."""

    regulation_id: str
    organization_id: str
    program_id: str
    cohort: str
    version: int
    effective_from: str  # ISO date "YYYY-MM-DD"
    effective_to: Optional[str]  # None = còn hiệu lực vô thời hạn
    status: str
    approved_by: Optional[str]
    source_document_id: Optional[str]
    rules: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegulationResolution:
    """Kết quả `resolve_regulation()` — LUÔN trả về, kể cả khi KHÔNG tìm
    thấy quy chế nào (status khác "ok"), không bao giờ raise cho các trường
    hợp nghiệp vụ bình thường (thiếu dữ liệu/hết hạn/chưa hiệu lực)."""

    status: str  # "ok" | "NOT_FOUND" | "EXPIRED_ONLY" | "FUTURE_ONLY" | "PENDING_ONLY"
    regulation: Optional[RegulationVersion]
    message: str
    candidates_considered: int


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def resolve_regulation(
    regulations: List[RegulationVersion],
    *,
    organization_id: str,
    program_id: str,
    cohort: str,
    at_date: Optional[str] = None,
) -> RegulationResolution:
    """Chọn ĐÚNG 1 phiên bản quy chế áp dụng cho `organization_id`/
    `program_id`/`cohort` tại thời điểm `at_date` (mặc định: hôm nay, UTC).

    Quy tắc (fail-closed, không đoán bừa):
    1. LỌC CỨNG theo organization_id — TUYỆT ĐỐI không trả quy chế của tổ
       chức khác dù program_id/cohort trùng tên (cross-tenant).
    2. LỌC theo program_id + cohort khớp CHÍNH XÁC.
    3. CHỈ xét status == APPROVED — DRAFT/PENDING_REVIEW/RETIRED không bao
       giờ được coi là quy chế áp dụng được (giống document_governance.py).
    4. CHỈ xét effective_from <= at_date VÀ (effective_to is None HOẶC
       at_date <= effective_to).
    5. Nếu nhiều bản cùng khớp (không nên xảy ra nếu dữ liệu đúng, nhưng
       không giả định) — chọn `version` LỚN NHẤT.
    6. Không tìm thấy bản nào khớp đủ điều kiện -> trả `NOT_FOUND` (hoặc
       phân loại rõ hơn: EXPIRED_ONLY/FUTURE_ONLY/PENDING_ONLY nếu có ứng
       viên cùng tenant/program/cohort nhưng bị loại vì lý do cụ thể — giúp
       Admin chẩn đoán nhanh, KHÔNG lộ dữ liệu của tenant khác).
    """
    resolve_date = _parse_date(at_date) or datetime.now(UTC).date()

    # Bước 1+2: lọc cứng tenant + program + cohort (KHÔNG lộ candidate của tenant khác
    # trong bất kỳ nhánh trả lời nào phía dưới).
    same_scope = [
        r
        for r in regulations
        if r.organization_id == organization_id and r.program_id == program_id and r.cohort == cohort
    ]

    if not same_scope:
        return RegulationResolution(
            status="NOT_FOUND",
            regulation=None,
            message=f"Không có quy chế nào cho program='{program_id}', cohort='{cohort}'.",
            candidates_considered=0,
        )

    approved = [r for r in same_scope if r.status == STATUS_APPROVED]
    if not approved:
        return RegulationResolution(
            status="PENDING_ONLY",
            regulation=None,
            message="Có quy chế cho phạm vi này nhưng CHƯA có bản nào ở trạng thái APPROVED.",
            candidates_considered=len(same_scope),
        )

    in_effect = [
        r
        for r in approved
        if _parse_date(r.effective_from) <= resolve_date
        and (_parse_date(r.effective_to) is None or resolve_date <= _parse_date(r.effective_to))
    ]

    if not in_effect:
        future = [r for r in approved if _parse_date(r.effective_from) > resolve_date]
        expired = [
            r
            for r in approved
            if _parse_date(r.effective_to) is not None and _parse_date(r.effective_to) < resolve_date
        ]
        if future and not expired:
            return RegulationResolution(
                status="FUTURE_ONLY",
                regulation=None,
                message=f"Quy chế cho phạm vi này chỉ có hiệu lực TỪ tương lai (sớm nhất: {min(f.effective_from for f in future)}).",
                candidates_considered=len(approved),
            )
        return RegulationResolution(
            status="EXPIRED_ONLY",
            regulation=None,
            message="Quy chế đã duyệt cho phạm vi này đều đã HẾT hiệu lực tại thời điểm yêu cầu.",
            candidates_considered=len(approved),
        )

    best = max(in_effect, key=lambda r: r.version)
    return RegulationResolution(
        status="ok",
        regulation=best,
        message=f"Áp dụng quy chế version={best.version} (hiệu lực từ {best.effective_from}).",
        candidates_considered=len(same_scope),
    )
