"""Thông báo xử lý dữ liệu cá nhân + ghi nhận đồng ý (bước 7, nhóm B — 21/11/2026).

NỘI DUNG LÀ BẢN NHÁP KỸ THUẬT, CHƯA ĐƯỢC LUẬT SƯ DUYỆT. Danh sách dữ liệu gửi cho AI khớp với code
(`privacy_service.build_anonymized_student_context`, `build_quick_question_prompt`); phần căn cứ pháp lý,
thời hạn và quyền của chủ thể dữ liệu phải được luật sư/nhà trường xác nhận trước khi chạy thí điểm.
Bản đầy đủ: docs/legal/PRIVACY_NOTICE_DRAFT.md. Đổi nội dung thì tăng NOTICE_VERSION — mọi người sẽ được
hỏi đồng ý lại.

Bằng chứng đồng ý ghi vào sổ kiểm toán của nền tảng (`lp_audit_events`, action `privacy.notice_accepted`):
- Bật mặc định khi dùng dữ liệu thật (không phải bản demo dữ liệu mô phỏng). Ghi đè: EDUDSS_PRIVACY_CONSENT_REQUIRED.
- Không ghi được bằng chứng thì KHÔNG cho vào (fail closed).
"""

from __future__ import annotations

import os

from dss.core.logging_config import get_logger

_logger = get_logger(__name__)
NOTICE_VERSION = "2026-11-21-draft1"
CONSENT_ACTION = "privacy.notice_accepted"

# Dữ liệu gửi tới nhà cung cấp AI ngoài (OpenAI / Google Gemini / Groq) — đúng theo code hiện tại.
DATA_SENT_TO_AI = (
    "Mức rủi ro học tập (cao / trung bình / thấp)",
    "Khoảng điểm dự đoán (ví dụ 6,5–7,0), không gửi điểm chính xác",
    "Tên môn học hoặc kỹ năng cần cải thiện",
    "Nhóm chuyên cần (ví dụ \"đi học đều\"), không gửi tỷ lệ chính xác",
    "Câu hỏi và lịch sử trò chuyện với trợ lý AI, sau khi đã xoá email, số điện thoại, mã sinh viên và tên tự giới thiệu",
)
DATA_NOT_SENT_TO_AI = ("Họ tên", "Mã sinh viên", "Email", "Số điện thoại", "Điểm chính xác từng môn")


def consent_required() -> bool:
    raw = os.environ.get("EDUDSS_PRIVACY_CONSENT_REQUIRED", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    from dss.core.runtime_mode import synthetic_data_allowed

    return not synthetic_data_allowed()


def notice_markdown(role: str) -> str:
    sent = "\n".join(f"- {item}" for item in DATA_SENT_TO_AI)
    not_sent = ", ".join(DATA_NOT_SENT_TO_AI)
    student_part = (
        "\n**Trợ lý AI dùng dịch vụ của bên thứ ba ở nước ngoài** (OpenAI, Google Gemini hoặc Groq, máy chủ "
        "chủ yếu ở Hoa Kỳ). Khi bạn dùng trợ lý AI, hệ thống chỉ gửi:\n\n"
        f"{sent}\n\n"
        f"Hệ thống **không** gửi: {not_sent}. Bạn có thể không dùng trợ lý AI; các chức năng khác vẫn hoạt động.\n"
    )
    return (
        "EduDSS là hệ thống hỗ trợ học tập của nhà trường. Hệ thống xử lý dữ liệu học tập "
        "(điểm, chuyên cần, hoạt động trên hệ thống học trực tuyến) để dự đoán kết quả, cảnh báo sớm và gợi ý cách học.\n\n"
        "**Ai xem được dữ liệu của sinh viên:** chính sinh viên; giảng viên / cố vấn học tập của lớp được gán; "
        "quản trị viên của trường. Kết quả dự đoán chỉ để tham khảo, không thay quyết định của nhà trường.\n"
        f"{student_part}"
        "\n**Lưu trữ:** hội thoại với AI và kết quả dự đoán được xoá sau 365 ngày; nhật ký hệ thống giữ 5 năm; "
        "điểm và hồ sơ học tập theo quy định lưu trữ của nhà trường.\n\n"
        "**Quyền của bạn:** xem, nhận bản sao, yêu cầu sửa hoặc xoá dữ liệu, rút lại đồng ý. "
        "Liên hệ phòng quản lý đào tạo hoặc quản trị viên EduDSS của trường để thực hiện.\n\n"
        f"_Phiên bản thông báo: {NOTICE_VERSION}._"
    )


def has_accepted(username: str) -> bool:
    from sqlalchemy import select

    from dss.platform.context import current_actor
    from dss.platform.models import AuditEvent
    from dss.platform.store import platform_session

    actor = current_actor()
    if actor.username != username:
        return False
    with platform_session(actor.school_id, actor=actor) as session:
        row = session.scalar(
            select(AuditEvent.id)
            .where(
                AuditEvent.actor == f"{actor.school_id}:{actor.username}",
                AuditEvent.action == CONSENT_ACTION,
                AuditEvent.entity_id == NOTICE_VERSION,
            )
            .limit(1)
        )
        return row is not None


def record_acceptance(username: str) -> None:
    from dss.platform.context import current_actor
    from dss.platform.store import audit, platform_session

    actor = current_actor()
    if actor.username != username:
        raise PermissionError("Chỉ chính người dùng đang đăng nhập mới đồng ý được.")
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        audit(
            session,
            actor,
            CONSENT_ACTION,
            NOTICE_VERSION,
            school_id=actor.school_id,
            details={"role": actor.role, "ai_data_categories": len(DATA_SENT_TO_AI)},
        )


def render_consent_gate(user: dict) -> bool:
    """True = được vào app. False = đang hiện thông báo (nơi gọi phải st.stop())."""
    import streamlit as st

    if not consent_required():
        return True
    cache_key = f"_privacy_ok::{user.get('username')}::{NOTICE_VERSION}"
    if st.session_state.get(cache_key):
        return True
    try:
        if has_accepted(user["username"]):
            st.session_state[cache_key] = True
            return True
    except Exception:  # noqa: BLE001 - không kiểm được: hỏi lại, không cho qua
        _logger.warning("Không đọc được bằng chứng đồng ý; hiển thị lại thông báo.", exc_info=True)

    st.markdown("### Thông báo về xử lý dữ liệu cá nhân")
    with st.container(border=True):
        st.markdown(notice_markdown(user.get("role", "")))
    agreed = st.checkbox("Tôi đã đọc và đồng ý với cách xử lý dữ liệu nêu trên.", key="privacy_notice_ack")
    col_ok, col_out = st.columns([1, 1])
    with col_ok:
        if st.button("Đồng ý và tiếp tục", type="primary", disabled=not agreed, key="privacy_notice_accept"):
            try:
                record_acceptance(user["username"])
            except Exception:  # noqa: BLE001 - không lưu được bằng chứng thì không cho vào
                _logger.exception("Không ghi được bằng chứng đồng ý.")
                st.error("Không lưu được xác nhận của bạn. Vui lòng thử lại sau hoặc báo quản trị viên.")
            else:
                st.session_state[cache_key] = True
                st.rerun()
    with col_out:
        if st.button("Không đồng ý, đăng xuất", key="privacy_notice_decline"):
            from dss.services import auth_service

            auth_service.logout()
            st.rerun()
    return False
