"""OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE — Phần 4-6, 34: AI Intent/
Complexity Router. Test dùng ĐÚNG các ví dụ nêu trong đề bài (Phần 6 "Router
Safety" và Phần 34 "End-to-end questions" A-H) — không tự bịa ví dụ khác để
dễ pass."""

from __future__ import annotations

from dss.services import ai_router


def test_A_current_score_lookup_routes_to_direct_data_lookup_not_llm():
    """A. 'Điểm hiện tại của em là bao nhiêu?' -> DIRECT_DATA_LOOKUP, KHÔNG
    cần LLM lớn (đúng yêu cầu Phần 6: '"GPA của em là bao nhiêu?" must not
    require large LLM')."""
    d = ai_router.classify("Điểm hiện tại của em là bao nhiêu?")
    assert d.intent == ai_router.INTENT_DIRECT_DATA_LOOKUP
    assert d.requires_llm is False
    assert d.tier == ai_router.TIER_1


def test_B_gpa_target_question_routes_to_calculator():
    """B. 'GPA 3.05, em muốn lên 3.20 thì cần bao nhiêu?' -> Calculator."""
    d = ai_router.classify("GPA 3.05, em muốn lên 3.20 thì cần bao nhiêu?")
    assert d.intent == ai_router.INTENT_GPA_CALCULATION
    assert d.requires_calculator is True
    assert d.requires_llm is False
    assert d.wired_to_real_behavior is True, (
        "GPA_CALCULATION phải là route ĐÃ wire vào hành vi thật (không chỉ nhãn phân loại)"
    )


def test_C_course_registration_eligibility_routes_to_rule_engine():
    """C. 'Em có được đăng ký môn B không?' -> Regulation Resolver + Rule Engine."""
    d = ai_router.classify("Em có được đăng ký môn B không?")
    assert d.intent == ai_router.INTENT_ACADEMIC_RULE_CHECK
    assert d.requires_rules is True
    assert d.requires_llm is False


def test_D_thesis_eligibility_routes_to_rule_engine():
    """D. 'Em có đủ điều kiện làm khóa luận không?' -> Rule Engine."""
    d = ai_router.classify("Em có đủ điều kiện làm khóa luận không?")
    assert d.intent == ai_router.INTENT_ACADEMIC_RULE_CHECK
    assert d.requires_rules is True


def test_E_why_at_risk_routes_to_learning_explanation():
    """E. 'Tại sao hệ thống đánh giá em có nguy cơ?' -> ML result + SHAP/
    evidence + LLM explanation."""
    d = ai_router.classify("Tại sao hệ thống đánh giá em có nguy cơ?")
    assert d.intent == ai_router.INTENT_LEARNING_EXPLANATION
    assert d.requires_llm is True, (
        "Vẫn cần LLM để DIỄN GIẢI kết quả ML/chẩn đoán đã có (không phải LLM tự bịa nguyên nhân)"
    )


def test_E_alt_phrasing_passive_voice_also_routes_to_learning_explanation():
    """Biến thể ví dụ mẫu (thể bị động) 'Tại sao em bị đánh giá có nguy cơ?'
    (POST_72H_MASTER_PRODUCTION_CLOSURE, Section 14) — PHẢI vẫn khớp
    LEARNING_EXPLANATION, không được rơi về ADVISOR_CHAT chung chung dù cả
    2 route đều an toàn (đều requires_llm=True + RAG)."""
    d = ai_router.classify("Tại sao em bị đánh giá có nguy cơ?")
    assert d.intent == ai_router.INTENT_LEARNING_EXPLANATION
    assert d.requires_llm is True


def test_F_which_regulation_applies_routes_to_regulation_resolver():
    """F. 'Quy chế nào đang áp dụng cho em?' -> Regulation Resolver."""
    d = ai_router.classify("Quy chế nào đang áp dụng cho em?")
    assert d.intent == ai_router.INTENT_REGULATION_LOOKUP
    assert d.requires_llm is False, "Regulation Resolver quyết định phiên bản quy chế — LLM không được tự chọn"


def test_G_create_plan_routes_to_advisor_plan():
    """G. 'Hãy lập kế hoạch học kỳ tới.' -> ADVISOR_PLAN."""
    d = ai_router.classify("Hãy lập kế hoạch học kỳ tới.")
    assert d.intent == ai_router.INTENT_ADVISOR_PLAN
    assert d.requires_llm is True


def test_H_please_explain_again_routes_to_learning_explanation():
    """H. 'Em không hiểu kết quả này, giải thích lại.' -> LEARNING_EXPLANATION."""
    d = ai_router.classify("Em không hiểu kết quả này, giải thích lại.")
    assert d.intent == ai_router.INTENT_LEARNING_EXPLANATION


def test_router_safety_summarize_document_routes_to_rag_not_bare_llm():
    """'Tóm tắt tài liệu này' -> RAG/content path."""
    d = ai_router.classify("Tóm tắt tài liệu này")
    assert d.intent == ai_router.INTENT_RAG_QA
    assert d.requires_rag is True


def test_router_safety_vague_feedback_falls_through_to_llm_safely():
    """'Em cảm thấy kế hoạch này chưa phù hợp, giải thích giúp em' -> có thể
    cần LLM — không được rơi vào UNKNOWN bế tắc, phải có route AN TOÀN."""
    d = ai_router.classify("Em cảm thấy kế hoạch này chưa phù hợp, giải thích giúp em")
    assert d.intent != ai_router.INTENT_UNKNOWN, "UNKNOWN phải có route an toàn, không được để trống xử lý"
    assert d.requires_llm is True


def test_unknown_gibberish_input_has_safe_route_not_silently_dropped():
    d = ai_router.classify("asdkjhaskjdh 12903 !!! ???")
    # Không khớp mẫu cụ thể nào -> rơi về ADVISOR_CHAT (đường LLM đầy đủ, đã
    # có RAG+citation verification) — KHÔNG được là None/crash/bỏ qua.
    assert d.intent in (ai_router.INTENT_ADVISOR_CHAT, ai_router.INTENT_UNKNOWN)
    assert d.requires_llm is True


def test_empty_question_does_not_crash_router():
    d = ai_router.classify("")
    assert d.intent == ai_router.INTENT_UNKNOWN
    assert d.requires_llm is True


def test_gpa_calculation_requires_at_least_two_numbers_not_one():
    """Chỉ 1 số (không đủ để tính required_remaining_gpa: cần current_gpa VÀ
    target_gpa) -> KHÔNG được nhận nhầm là GPA_CALCULATION."""
    d = ai_router.classify("Điểm của em là 7.5")
    assert d.intent != ai_router.INTENT_GPA_CALCULATION


def test_only_behavior_changing_routes_flag_is_honest():
    """Chỉ ĐÚNG những route thực sự có code thay đổi hành vi runtime mới
    được đánh dấu wired_to_real_behavior=True — không tự nhận đã 'wire' cho
    route chưa có Rule Engine/Validator đứng sau.

    CẬP NHẬT (Phần 10, sau khi wire `build_regulation_lookup_reply` vào
    `ai_advisor.py`): REGULATION_LOOKUP nay ĐÃ có hành vi runtime thật —
    chặn LLM tự đoán quy chế và trả lời trung thực rằng cần liên hệ Phòng
    Đào tạo (không tra cứu được đầy đủ vì thiếu ánh xạ organization_id/
    program_id/cohort cho sinh viên demo — xem docstring đầu ai_router.py) —
    nên wired_to_real_behavior phải là True, không còn False như trước khi
    wire.

    CẬP NHẬT (Phần 12, sau khi wire `build_academic_rule_check_reply` +
    `rule_engine.py` vào `ai_advisor.py`): ACADEMIC_RULE_CHECK CŨNG nay đã
    có hành vi runtime thật — cùng lý do với REGULATION_LOOKUP (chặn LLM tự
    quyết định ALLOW/DENY, trả lời trung thực khi thiếu dữ liệu) — nên cũng
    phải là True."""
    rule_check = ai_router.classify("Em có được đăng ký môn B không?")
    assert rule_check.wired_to_real_behavior is True, (
        "ACADEMIC_RULE_CHECK đã wire build_academic_rule_check_reply() vào "
        "ai_advisor.py (chặn LLM tự quyết định ALLOW/DENY) — phải là True."
    )
    regulation_lookup = ai_router.classify("Quy chế nào đang áp dụng cho em?")
    assert regulation_lookup.wired_to_real_behavior is True, (
        "REGULATION_LOOKUP đã wire build_regulation_lookup_reply() vào "
        "ai_advisor.py (chặn LLM tự đoán quy chế) — phải là True."
    )
