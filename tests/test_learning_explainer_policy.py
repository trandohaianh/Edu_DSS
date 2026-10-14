"""Unit test cho lớp policy tất định của AI Learning Explainer (Mục 2).

Đây là kiểm chứng ĐỘC LẬP với system prompt — không gọi LLM, chỉ kiểm tra các
hàm rule-based trong learning_explainer_policy.py trực tiếp trên chuỗi input
giả lập câu trả lời của LLM (cả câu trả lời tuân thủ đúng và vi phạm).
"""
from __future__ import annotations

from dss.services import learning_explainer_policy as policy


# ---------------------------------------------------------------------------
# Rule A + E — CMS_ONLY traceability / no-fabrication khi retrieval rỗng
# ---------------------------------------------------------------------------
def test_rule_e_no_cms_content_and_answer_is_honest_message_passes():
    result = policy.validate_cms_only(policy.NO_CMS_CONTENT_MESSAGE, has_cms_content=False, hallucinated_citations=[])
    assert result.is_valid
    assert result.repaired_answer is None


def test_rule_e_no_cms_content_but_answer_fabricates_gets_repaired():
    fabricated = "K-Means là thuật toán phân cụm phổ biến, hoạt động bằng cách gán điểm vào centroid gần nhất."
    result = policy.validate_cms_only(fabricated, has_cms_content=False, hallucinated_citations=[])
    assert not result.is_valid
    assert any(v.rule == "E_NO_FABRICATION" for v in result.violations)
    assert result.repaired_answer == policy.NO_CMS_CONTENT_MESSAGE


def test_rule_d_hallucinated_citation_flagged_even_with_cms_content():
    result = policy.validate_cms_only(
        "K-Means gán điểm vào centroid gần nhất [Slide 3].", has_cms_content=True,
        hallucinated_citations=[{"citation": "[Slide 3]"}],
    )
    assert not result.is_valid
    assert any(v.rule == "D_CITATION_UNSUPPORTED" for v in result.violations)
    assert result.repaired_answer is None  # citation sai không tự sửa được nội dung, chỉ cảnh báo


def test_rule_a_valid_cms_backed_answer_passes_clean():
    result = policy.validate_cms_only("K-Means là thuật toán phân cụm không giám sát.", has_cms_content=True, hallucinated_citations=[])
    assert result.is_valid
    assert result.violations == []


# ---------------------------------------------------------------------------
# Rule B — CMS_PLUS_SUPPLEMENTARY phải tách nhãn rõ 2 phần
# ---------------------------------------------------------------------------
def test_rule_b_supplementary_mode_without_labels_violates():
    blended = "K-Means gán điểm vào centroid gần nhất, và trên thực tế nó cũng liên quan tới thuật toán EM."
    result = policy.validate_supplementary_separation(blended, mode=policy.CMS_PLUS_SUPPLEMENTARY, supplementary_requested=True)
    assert not result.is_valid
    assert result.violations[0].rule == "B_MUST_LABEL_SUPPLEMENTARY"


def test_rule_b_supplementary_mode_with_both_labels_passes():
    labeled = "**Từ bài giảng:** K-Means gán điểm vào centroid gần nhất.\n\n**Kiến thức bổ sung:** Ngoài ra còn có DBSCAN."
    result = policy.validate_supplementary_separation(labeled, mode=policy.CMS_PLUS_SUPPLEMENTARY, supplementary_requested=True)
    assert result.is_valid


def test_rule_b_cms_only_mode_never_triggers_this_rule():
    blended = "K-Means gán điểm vào centroid gần nhất, và cũng liên quan tới EM."
    result = policy.validate_supplementary_separation(blended, mode=policy.CMS_ONLY, supplementary_requested=False)
    assert result.is_valid


def test_rule_b_not_requested_skips_check_even_in_supplementary_mode():
    blended = "K-Means gán điểm vào centroid gần nhất."
    result = policy.validate_supplementary_separation(blended, mode=policy.CMS_PLUS_SUPPLEMENTARY, supplementary_requested=False)
    assert result.is_valid


# ---------------------------------------------------------------------------
# Rule C — Socratic không tiết lộ đáp án ngay
# ---------------------------------------------------------------------------
def test_rule_c_immediate_answer_at_start_violates():
    leaked = "Đáp án là centroid gần nhất."
    result = policy.validate_socratic_no_immediate_answer(leaked, is_final_synthesis_step=False)
    assert not result.is_valid
    assert result.violations[0].rule == "C_SOCRATIC_LEAKED_ANSWER"


def test_rule_c_guiding_question_passes():
    guiding = "Theo em, nếu một điểm dữ liệu nằm giữa 2 centroid thì nó sẽ được gán vào đâu?"
    result = policy.validate_socratic_no_immediate_answer(guiding, is_final_synthesis_step=False)
    assert result.is_valid


def test_rule_c_no_question_at_all_violates():
    flat = "Centroid là tâm của một cụm dữ liệu."
    result = policy.validate_socratic_no_immediate_answer(flat, is_final_synthesis_step=False)
    assert not result.is_valid
    assert result.violations[0].rule == "C_SOCRATIC_MISSING_QUESTION"


def test_rule_c_final_synthesis_step_allows_immediate_answer():
    final = "Đáp án là centroid gần nhất — tổng kết lại toàn bộ quá trình ta vừa thảo luận."
    result = policy.validate_socratic_no_immediate_answer(final, is_final_synthesis_step=True)
    assert result.is_valid


# ---------------------------------------------------------------------------
# Điểm gọi tổng hợp validate_explanation_response
# ---------------------------------------------------------------------------
def test_combined_repairs_fabrication_and_ignores_socratic_when_no_cms_content():
    fabricated = "K-Means hoạt động bằng cách gán điểm vào centroid gần nhất."
    result = policy.validate_explanation_response(
        fabricated, has_cms_content=False, hallucinated_citations=[], mode=policy.CMS_ONLY,
        socratic_mode=True, is_final_synthesis_step=False,
    )
    assert not result.is_valid
    assert result.repaired_answer == policy.NO_CMS_CONTENT_MESSAGE


def test_combined_valid_cms_only_socratic_answer_passes():
    guiding = "Theo em, một điểm nằm giữa 2 centroid sẽ được gán vào cụm nào?"
    result = policy.validate_explanation_response(
        guiding, has_cms_content=True, hallucinated_citations=[], mode=policy.CMS_ONLY,
        socratic_mode=True, is_final_synthesis_step=False,
    )
    assert result.is_valid
    assert result.repaired_answer is None


def test_combined_supplementary_and_socratic_violations_both_reported():
    blended_and_flat = "Đáp án là centroid gần nhất, và trên thực tế nó cũng liên quan tới DBSCAN."
    result = policy.validate_explanation_response(
        blended_and_flat, has_cms_content=True, hallucinated_citations=[], mode=policy.CMS_PLUS_SUPPLEMENTARY,
        supplementary_requested=True, socratic_mode=True, is_final_synthesis_step=False,
    )
    assert not result.is_valid
    rules = {v.rule for v in result.violations}
    assert "B_MUST_LABEL_SUPPLEMENTARY" in rules
    assert "C_SOCRATIC_LEAKED_ANSWER" in rules
