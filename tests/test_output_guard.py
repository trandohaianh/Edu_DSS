"""Bộ lọc lời khuyên có hại trên CÂU TRẢ LỜI của Trợ lý AI (dss/services/output_guard.py).

Trước 21/11/2026 bộ phát hiện chỉ chạy trong evals/, câu trả lời có hại vẫn hiện thẳng cho
sinh viên. Các test này bảo đảm câu có hại không tới được màn hình sinh viên.
"""

from __future__ import annotations

from dss.services import output_guard as og
from dss.services import token_tracker
from dss.services.llm_gateway import LLMGateway

HARMFUL = "Cứ tự ý tăng gấp đôi liều thuốc an thần để ngủ ngon trước kỳ thi."
SAFE_PLAN = (
    "### Kế hoạch 2 tuần\n"
    "- Đi học đầy đủ và ghi chép bài giảng.\n"
    "- Mỗi tối làm 10 bài tập môn Xác suất.\n"
    "- Ngủ đủ 7 tiếng mỗi đêm.\n"
    "- Hỏi giảng viên phần chưa hiểu trong giờ tiếp sinh viên.\n"
)


def _run(chunks, role):
    return "".join(og.guard_stream(iter(chunks), role=role, request_type="test"))


def test_safe_answer_passes_unchanged_for_student_and_staff():
    assert _run([SAFE_PLAN[:20], SAFE_PLAN[20:]], "Sinh viên") == SAFE_PLAN
    assert _run([SAFE_PLAN], "Giảng viên / CVHT") == SAFE_PLAN


def test_single_harmful_sentence_is_redacted_for_student_and_rest_kept():
    text = SAFE_PLAN + "- " + HARMFUL + "\n"
    out = _run([text], "Sinh viên")
    assert HARMFUL not in out
    assert og.REDACTED_SENTENCE in out
    assert "Mỗi tối làm 10 bài tập môn Xác suất." in out
    assert out.startswith("⚠️")


def test_many_harmful_sentences_hide_whole_answer_for_student():
    bad = " ".join(
        [
            HARMFUL,
            "Thức trắng ba đêm liền để ôn cho kịp.",
            "Mang điện thoại vào phòng thi để tra đáp án.",
        ]
    )
    out = _run([bad], "Sinh viên")
    assert out == og.BLOCKED_MESSAGE
    for sentence in ("tăng gấp đôi liều", "Thức trắng", "Mang điện thoại"):
        assert sentence not in out


def test_staff_keep_stream_but_get_warning_appended():
    text = SAFE_PLAN + HARMFUL
    chunks = list(og.guard_stream(iter([text[:30], text[30:]]), role="Giảng viên / CVHT"))
    assert chunks[0] == text[:30]  # vẫn stream nguyên văn
    assert "Cảnh báo an toàn" in chunks[-1]


def test_system_status_messages_are_not_checked_as_advice():
    msg = "⚠️ Đã dùng hết ngân sách AI tháng này (5.00/5.00 USD)."
    assert og.split_sentences(msg) == []
    assert _run([msg], "Sinh viên") == msg


def test_detector_failure_does_not_break_the_answer(monkeypatch):
    import dss.services.llm_evaluator as ev

    def _boom(_text):
        raise RuntimeError("mô hình lỗi")

    monkeypatch.setattr(ev, "detect_harmful_or_unsupported_advice", _boom)
    assert _run([SAFE_PLAN], "Sinh viên") == SAFE_PLAN


# ------------------------------------------------------------------ qua cổng AI thật
class _Provider:
    def __init__(self, text):
        self.text = text

    def call_ai_provider(self, prompt, provider, **kwargs):
        return iter([self.text])


def test_gateway_never_shows_harmful_advice_to_students(monkeypatch):
    monkeypatch.setenv("DSS_PRIMARY_PROVIDER", "gemini")
    monkeypatch.setattr(token_tracker, "check_user_quota", lambda *a, **k: (True, ""))
    monkeypatch.setattr(token_tracker, "check_system_budget", lambda: (True, ""))
    out = "".join(
        LLMGateway(_Provider(SAFE_PLAN + "- " + HARMFUL)).stream_generate(
            prompt="Em nên ôn thế nào? (guard 1)",
            user_id="U_guard_1",
            role="Sinh viên",
            request_type="advisor_chat",
            provider="gemini",
            api_key="k",
        )
    )
    assert HARMFUL not in out
    assert "Mỗi tối làm 10 bài tập" in out


def test_gateway_passes_safe_answer_to_students(monkeypatch):
    monkeypatch.setenv("DSS_PRIMARY_PROVIDER", "gemini")
    monkeypatch.setattr(token_tracker, "check_user_quota", lambda *a, **k: (True, ""))
    monkeypatch.setattr(token_tracker, "check_system_budget", lambda: (True, ""))
    out = "".join(
        LLMGateway(_Provider(SAFE_PLAN)).stream_generate(
            prompt="Em nên ôn thế nào? (guard 2)",
            user_id="U_guard_2",
            role="Sinh viên",
            request_type="advisor_chat",
            provider="gemini",
            api_key="k",
        )
    )
    assert "Mỗi tối làm 10 bài tập môn Xác suất." in out
    assert og.REDACTED_SENTENCE not in out


def test_weak_classifier_only_flags_never_hide_the_whole_answer(monkeypatch):
    """Cờ chỉ từ bộ phân loại với điểm < 0,65 là "yếu": ẩn đúng câu đó, không ẩn toàn bộ."""
    import dss.services.llm_evaluator as ev

    def _weak(text):
        if "XYZ" in text:
            return True, ["Mô hình phân loại an toàn: xác suất có hại 0.55"]
        return False, []

    monkeypatch.setattr(ev, "detect_harmful_or_unsupported_advice", _weak)
    text = "Câu thử XYZ thứ nhất. Câu thử XYZ thứ hai. Câu thử XYZ thứ ba. Em nên ôn lại chương hai."
    out = _run([text], "Sinh viên")
    assert out != og.BLOCKED_MESSAGE
    assert "Em nên ôn lại chương hai." in out
    assert out.count(og.REDACTED_SENTENCE) == 3


def test_strong_flag_on_a_one_sentence_answer_hides_it():
    out = _run([HARMFUL], "Sinh viên")
    assert out == og.BLOCKED_MESSAGE
