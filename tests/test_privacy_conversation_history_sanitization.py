"""FINAL REMAINING-GAPS CLOSURE — Section 7: conversation-history PII was
found unsanitized in the prior pass's audit. This closes it. Also confirms
a genuine, previously-latent bug: `_STUDENT_ID_REGEX` existed in
privacy_service.py but was NEVER applied anywhere — a real dead pattern,
not just a theoretical gap."""

from __future__ import annotations

from dss.services import privacy_service


def test_email_is_redacted_from_conversation_turn():
    text = "My email is student123@example.com, can you help?"
    result = privacy_service.sanitize_conversation_turn_for_provider(text)
    assert "student123@example.com" not in result
    assert "[EMAIL_ẨN_DANH]" in result


def test_phone_is_redacted_from_conversation_turn():
    text = "My phone number is 0912345678, please call me"
    result = privacy_service.sanitize_conversation_turn_for_provider(text)
    assert "0912345678" not in result
    assert "[SĐT_ẨN_DANH]" in result


def test_student_id_is_redacted_from_conversation_turn():
    """_STUDENT_ID_REGEX ton tai tu truoc nhung CHUA BAO GIO duoc goi trong
    sanitize_pii_from_text() - loi that, khong chi ly thuyet."""
    text = "My student ID is MSSV20210045, please check my record"
    result = privacy_service.sanitize_conversation_turn_for_provider(text)
    assert "20210045" not in result
    assert "[MSSV_ẨN_DANH]" in result


def test_self_disclosed_name_is_redacted_from_conversation_turn():
    text_vi = "Tên em là Nguyễn Văn A, em muốn hỏi về điểm số"
    result_vi = privacy_service.sanitize_conversation_turn_for_provider(text_vi)
    assert "Nguyễn Văn A" not in result_vi
    assert "[TÊN_ẨN_DANH]" in result_vi

    text_en = "My name is John Smith and I need help"
    result_en = privacy_service.sanitize_conversation_turn_for_provider(text_en)
    assert "John Smith" not in result_en
    assert "[TÊN_ẨN_DANH]" in result_en


def test_all_four_pii_categories_redacted_in_one_turn():
    text = "Tên em là Trần Thị B, MSSV20210099, email b@example.com, SĐT 0987654321. Em muốn hỏi về học phí."
    result = privacy_service.sanitize_conversation_turn_for_provider(text)
    assert "Trần Thị B" not in result
    assert "20210099" not in result
    assert "b@example.com" not in result
    assert "0987654321" not in result
    # Cau hoi thuc su (khong phai PII) van con lai trong ket qua
    assert "học phí" in result


def test_does_not_destroy_non_pii_facts_needed_for_the_answer():
    """Khong duoc pha huy du kien can thiet de tra loi (vd. GPA/mon hoc)."""
    text = "GPA của em hiện tại là 3.5, em muốn hỏi về môn Toán"
    result = privacy_service.sanitize_conversation_turn_for_provider(text)
    assert "3.5" in result
    assert "Toán" in result


def test_original_sanitize_pii_from_text_unchanged_behavior():
    """sanitize_pii_from_text() goc KHONG duoc doi hanh vi (van dung cho cac
    noi goi khac, vd. danh sach diem yeu) - chi email/SDT, KHONG bao gom
    MSSV/ten (tranh regression khong can thiet cho cac loi goi da co)."""
    text = "MSSV20210045 Nguyễn Văn A"
    result = privacy_service.sanitize_pii_from_text(text)
    assert result == text, "Ham goc khong duoc thay doi hanh vi."
