"""Privacy Service — Bảo vệ quyền riêng tư sinh viên và khử dữ liệu định danh (PII De-identification).

Tuân thủ nguyên tắc LMS-scale:
- Trước khi gọi Cloud LLM (Gemini, Groq, OpenAI), tự động loại bỏ hoặc mã hóa PII.
- Thay thế Họ và tên, Email, Số điện thoại, Địa chỉ bằng danh xưng trung tính hoặc mã ẩn danh giả lập.
- Chuyển đổi MSSV thật thành định danh giả danh có KHOÁ (HMAC theo từng trường, dss/security/pseudonymization.py) — nhất quán nhưng không thể dò ngược nếu không có khoá bí mật.
- Chỉ gửi các đặc trưng học tập cốt lõi cần thiết: Phân loại rủi ro, Điểm yếu môn học, Khoảng điểm GPA, Tỷ lệ điểm danh.
- Ghi log DANH MỤC DỮ LIỆU ĐÃ GỬI (data categories), KHÔNG ghi dữ liệu thô.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_REGEX = re.compile(r"(\+84|0)(3|5|7|8|9)[0-9]{8}\b")
_STUDENT_ID_REGEX = re.compile(r"\b(SV|sv|MSSV|mssv)?[0-9]{5,10}\b")
# FINAL REMAINING-GAPS CLOSURE (Section 7): _STUDENT_ID_REGEX đã tồn tại
# nhưng CHƯA BAO GIỜ được dùng trong sanitize_pii_from_text() — lỗ hổng
# thật, không phải chỉ lý thuyết (tự phát hiện khi audit conversation
# history). Thêm mẫu tự tiết lộ tên (thường gặp trong hội thoại tự do,
# KHÔNG bắt được bằng NER — chỉ bắt cụm từ tự giới thiệu phổ biến, không
# phải phát hiện tên chung).
_SELF_DISCLOSED_NAME_REGEX = re.compile(
    r"(?:tên (?:tôi|em|mình) là|tên là|my name is)\s+[^\.,\n!?]+",
    re.IGNORECASE,
)


def generate_pseudonym(student_id: str, salt: Optional[str] = None, organization_id: Optional[int] = None) -> str:
    """Mã giả danh nhất quán, có KHOÁ BÍ MẬT, theo từng trường (C1.1).

    Uỷ quyền cho dss.security.pseudonymization (HMAC-SHA256, khoá theo trường,
    100 bit). Tham số `salt` cũ KHÔNG còn được dùng (giữ chữ ký để tương thích):
    muối công khai trong mã nguồn chính là lỗ hổng đã được loại bỏ."""
    from dss.security.pseudonymization import pseudonymize

    return pseudonymize(student_id, organization_id=organization_id)


def sanitize_conversation_turn_for_provider(text: str) -> str:
    """FINAL REMAINING-GAPS CLOSURE (Section 7): khử PII MẠNH HƠN dành riêng
    cho lịch sử hội thoại tự do (nơi sinh viên có thể TỰ tiết lộ PII bất kỳ
    lúc nào, không như các trường có cấu trúc khác) — gồm email/SĐT (dùng
    lại `sanitize_pii_from_text`) CỘNG THÊM mã số sinh viên và tên tự giới
    thiệu. KHÔNG thay `sanitize_pii_from_text()` gốc (giữ nguyên hành vi cho
    các nơi gọi khác, vd. danh sách điểm yếu — tránh regression không cần
    thiết) — hàm này CHỈ áp dụng cho lịch sử hội thoại gửi tới provider."""
    if not text:
        return ""
    cleaned = sanitize_pii_from_text(text)
    cleaned = _STUDENT_ID_REGEX.sub("[MSSV_ẨN_DANH]", cleaned)
    cleaned = _SELF_DISCLOSED_NAME_REGEX.sub("[TÊN_ẨN_DANH]", cleaned)
    return cleaned


def sanitize_pii_from_text(text: str) -> str:
    """Xóa bỏ số điện thoại, email khỏi chuỗi văn bản tự do."""
    if not text:
        return ""
    cleaned = _EMAIL_REGEX.sub("[EMAIL_ẨN_DANH]", str(text))
    cleaned = _PHONE_REGEX.sub("[SĐT_ẨN_DANH]", cleaned)
    return cleaned


def gpa_band(predicted_gpa: Optional[float]) -> str:
    """Khoảng điểm (thang 10) — KHÔNG kèm giá trị chính xác (C1.1)."""
    if predicted_gpa is None:
        return "Chưa có dự đoán"
    try:
        gpa_val = float(predicted_gpa)
    except (TypeError, ValueError):
        return "Chưa có dự đoán"
    if gpa_val >= 8.5:
        return "Giỏi / Xuất sắc (GPA >= 8.5)"
    if gpa_val >= 7.0:
        return "Khá (7.0 <= GPA < 8.5)"
    if gpa_val >= 5.5:
        return "Trung bình (5.5 <= GPA < 7.0)"
    return "Cần cải thiện (GPA < 5.5)"


def attendance_bracket(value: Any) -> Optional[str]:
    """Nhóm chuyên cần thay vì tỷ lệ chính xác (C1.1)."""
    try:
        rate = float(str(value).strip().rstrip("%")) if not isinstance(value, (int, float)) else float(value)
    except (TypeError, ValueError):
        return None
    if rate > 1.0:
        rate /= 100.0
    if rate >= 0.9:
        return "cao (>= 90%)"
    if rate >= 0.75:
        return "trung bình (75-90%)"
    return "thấp (< 75%)"


_SCORE_PAIR_REGEX = re.compile(
    r"\(\s*SV:\s*\**\s*(-?\d+(?:[.,]\d+)?)\s*\**\s*,\s*TB lớp:\s*\**\s*(-?\d+(?:[.,]\d+)?)\s*\**\s*\)",
    re.IGNORECASE,
)


def generalize_score_pairs(text: str) -> str:
    """ "(SV: 6.20, TB lớp: 7.10)" -> "(thấp hơn TB lớp một chút)": giữ tín hiệu tương đối
    cần cho tư vấn, bỏ giá trị tuyệt đối của sinh viên khỏi payload gửi ra ngoài (C1.1)."""

    def _repl(m):
        try:
            gap = float(m.group(2).replace(",", ".")) - float(m.group(1).replace(",", "."))
        except ValueError:
            return "(so với trung bình lớp)"
        if gap >= 1.5:
            return "(thấp hơn TB lớp nhiều)"
        if gap > 0:
            return "(thấp hơn TB lớp một chút)"
        return "(không thấp hơn TB lớp)"

    return _SCORE_PAIR_REGEX.sub(_repl, text or "")


def build_anonymized_student_context(
    student_id: str,
    predicted_gpa: Optional[float],
    student_weaknesses: Optional[List[str]],
    student_profile: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Tạo chuỗi bối cảnh học tập gửi cho LLM BÊN NGOÀI và nhật ký danh mục dữ liệu.

    C1.1 — tối thiểu hoá dữ liệu:
    - KHÔNG gửi định danh nào (kể cả bí danh) — nhà cung cấp không cần biết đây là ai.
      Bí danh chỉ nằm trong audit_metadata nội bộ.
    - GPA chỉ gửi KHOẢNG, không kèm giá trị gần đúng (trước đây "(~7.3)" lộ gần như chính xác).
    - Chuyên cần gửi NHÓM, không gửi tỷ lệ chính xác.
    - Ghi chú tự do được khử PII bằng bộ lọc mạnh (email/SĐT/MSSV/tên tự giới thiệu).

    Trả về: (context_string, audit_metadata)
    """
    profile = student_profile or {}
    pseudonym = generate_pseudonym(student_id)
    risk_level = profile.get("risk_level", "trung bình")
    clean_weaknesses = [
        generalize_score_pairs(sanitize_conversation_turn_for_provider(str(w))) for w in (student_weaknesses or [])
    ]

    lines = [
        f"- Mức độ rủi ro học tập: {risk_level}",
        f"- Khoảng GPA dự báo: {gpa_band(predicted_gpa)}",
        f"- Các môn học / kỹ năng cần hỗ trợ: {', '.join(clean_weaknesses) if clean_weaknesses else 'Phương pháp học tập chung'}",
    ]
    categories = ["risk_level_category", "gpa_band", "weakness_topic_tags"]
    if "attendance_rate" in profile:
        bracket = attendance_bracket(profile["attendance_rate"])
        if bracket:
            lines.append(f"- Mức chuyên cần: {bracket}")
            categories.append("attendance_bracket")
    if profile.get("progress_note"):
        lines.append(
            f"- Nhận xét tiến độ học tập: {sanitize_conversation_turn_for_provider(str(profile['progress_note']))}"
        )
        categories.append("sanitized_progress_note")

    context_str = "\n".join(lines)

    # Nhật ký danh mục dữ liệu đã gửi — nội bộ, KHÔNG gửi ra ngoài, KHÔNG lưu PII
    audit_metadata = {
        "pseudonym": pseudonym,
        "categories_transmitted": categories,
        "has_identifier": False,
        "has_real_name": False,
        "has_email": False,
        "has_phone": False,
        "has_exact_gpa": False,
    }

    return context_str, audit_metadata


def build_quick_question_prompt(
    risk_level: Optional[str], predicted_value: Optional[float], weakest_factor: Optional[str], question: str
) -> str:
    """Prompt cho hộp "Hỏi nhanh AI" (Trang chủ Sinh viên) — cùng chính sách tối thiểu
    hoá với build_anonymized_student_context: không định danh, GPA theo khoảng,
    câu hỏi tự do được khử PII."""
    parts = [
        "Bạn là trợ lý học tập AI cho một sinh viên.",
        f"Mức rủi ro hiện tại: {risk_level or 'chưa rõ'}.",
        f"Khoảng điểm dự báo: {gpa_band(predicted_value)}.",
    ]
    if weakest_factor:
        parts.append(f"Yếu tố cần cải thiện nhất: {sanitize_conversation_turn_for_provider(str(weakest_factor))}.")
    parts.append(
        "Trả lời ngắn gọn, thân thiện, bằng tiếng Việt cho câu hỏi sau: "
        + sanitize_conversation_turn_for_provider(question.strip())
    )
    return " ".join(parts)


class PrivacyService:
    """Lớp dịch vụ bảo vệ quyền riêng tư và khử danh tính sinh viên."""

    @staticmethod
    def generate_pseudonym(student_id: str, salt: Optional[str] = None, organization_id: Optional[int] = None) -> str:
        return generate_pseudonym(student_id, organization_id=organization_id)

    @staticmethod
    def sanitize_pii_from_text(text: str) -> str:
        return sanitize_pii_from_text(text)

    @staticmethod
    def build_anonymized_student_context(
        student_id: str,
        predicted_gpa: Optional[float],
        student_weaknesses: Optional[List[str]],
        student_profile: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        return build_anonymized_student_context(student_id, predicted_gpa, student_weaknesses, student_profile)


privacy_service = PrivacyService()
