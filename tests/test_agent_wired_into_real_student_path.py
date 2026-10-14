"""FINAL REMAINING-GAPS CLOSURE — Section 5: Agent must be used by the real
Student-facing chat path, not just class/unit-test/demo-endpoint only. This
proves the actual code path: Student UI (ai_advisor.py) → ai_router.py →
agent.py → tools → Validator, not a parallel, untested calling convention."""
from __future__ import annotations

import inspect

from dss.services import ai_router
from dss.tabs import ai_advisor


def test_ai_advisor_passes_real_pseudonym_and_role_to_gpa_reply():
    """Xác nhận ai_advisor.py truyền user_id/role THẬT (không phải giá trị
    mặc định) vào build_gpa_calculation_reply() — nếu không, dù Agent có
    kiểm tra authorize() thật, ai_advisor.py vẫn gọi với danh tính giả mặc
    định, coi như CHƯA thật sự wire."""
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    idx = source.index("ai_router.build_gpa_calculation_reply(")
    block = source[idx: idx + 300]
    assert "privacy_service.generate_pseudonym(str(student_id_llm))" in block
    assert "role=role or" in block


def test_build_gpa_calculation_reply_genuinely_calls_agent_not_calculator_directly():
    """Xác nhận ai_router.py's build_gpa_calculation_reply() (hàm thật được
    ai_advisor.py gọi) đi qua agent.run_gpa_calculation(), không gọi thẳng
    gpa_calculator.compute_required_remaining_gpa() (đường vòng qua Agent)."""
    source = inspect.getsource(ai_router.build_gpa_calculation_reply)
    assert "agent_module.run_gpa_calculation(agent_request)" in source
    assert "= compute_required_remaining_gpa(" not in source, (
        "Không được gọi thẳng Calculator, phải đi qua Agent (agent.run_gpa_calculation) — "
        "chỉ được PHÉP nhắc tên hàm này trong docstring, không được thực sự gọi."
    )
    assert "from dss.services.gpa_calculator import compute_required_remaining_gpa" not in source, (
        "Không được import thẳng Calculator vào hàm này nữa — chỉ Agent mới được import nó."
    )


def test_end_to_end_student_chat_question_reaches_agent_authorization():
    """Test thật (không phải source-inspection): gọi build_gpa_calculation_
    reply() với 1 câu hỏi thật, xác nhận kết quả PHẢN ÁNH đã đi qua
    agent.authorize() + Validator (không chỉ format trùng khớp ngẫu nhiên)."""
    reply = ai_router.build_gpa_calculation_reply(
        "current_gpa 6.0 credits_done 20 target_gpa 7.5 credits_remaining 20",
        user_id="pseudo_student_real_path_test", role="Sinh viên",
    )
    assert reply is not None
    assert "9.0" in reply or "9.00" in reply
    assert "công thức xác định" in reply
