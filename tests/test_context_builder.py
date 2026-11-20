"""FINAL REMAINING-GAPS CLOSURE — Section 6: Context Builder. Written before
`dss/services/context_builder.py` existed (TDD), per this engagement's
established convention for genuinely new modules."""

from __future__ import annotations

from dss.services import context_builder


def test_gpa_intent_keeps_only_required_fields_drops_pii():
    raw_row = {
        "current_gpa": 6.0,
        "credits_done": 20,
        "target_gpa": 7.5,
        "credits_remaining": 20,
        "gpa_scale": 10,
        "name": "Nguyễn Văn A",
        "email": "a@example.com",
        "phone": "0912345678",
        "full_transcript": [1, 2, 3],
        "full_chat_history": ["..."],
    }
    result = context_builder.build_context("GPA_CALCULATION", raw_row)
    assert result.status == "ok"
    assert "name" not in result.context
    assert "email" not in result.context
    assert "phone" not in result.context
    assert "full_transcript" not in result.context
    assert "full_chat_history" not in result.context
    assert result.context["current_gpa"] == 6.0
    assert result.dropped_forbidden_fields == {"name", "email", "phone", "full_transcript", "full_chat_history"}


def test_gpa_intent_reports_missing_required_fields_honestly():
    raw_row = {"current_gpa": 6.0, "name": "X"}
    result = context_builder.build_context("GPA_CALCULATION", raw_row)
    assert result.status == "MISSING_REQUIRED"
    assert "target_gpa" in result.missing_required_fields
    assert "credits_done" in result.missing_required_fields


def test_learning_explanation_intent_keeps_prediction_and_shap_drops_pii():
    raw_row = {
        "prediction": 7.2,
        "model_version": "v3",
        "relevant_features": ["diem_giua_ky"],
        "shap_evidence": {"diem_giua_ky": 0.4},
        "name": "Y",
        "email": "y@example.com",
    }
    result = context_builder.build_context("LEARNING_EXPLANATION", raw_row)
    assert result.status == "ok"
    assert "shap_evidence" in result.context
    assert "name" not in result.context


def test_regulation_lookup_intent_requires_tenant_scope_fields():
    raw_row = {"organization_id": "org-1", "program_id": "cntt", "cohort": "k66"}
    result = context_builder.build_context("REGULATION_LOOKUP", raw_row)
    assert result.status == "MISSING_REQUIRED"
    assert "regulation_version" in result.missing_required_fields
    assert "approved_evidence" in result.missing_required_fields


def test_advisor_plan_intent_allows_optional_ml_and_rag_evidence():
    raw_row = {
        "authorized_academic_summary": "GPA 7.0, 80 tín chỉ",
        "goals": "tăng GPA",
        "ml_results": {"risk": "trung bình"},
        "rag_evidence": ["doc1"],
        "name": "Z",
    }
    result = context_builder.build_context("ADVISOR_PLAN", raw_row)
    assert result.status == "ok"
    assert "ml_results" in result.context
    assert "name" not in result.context


def test_unknown_intent_fails_safe_never_passes_raw_row_through():
    """Intent khong co hop dong rieng -> KHONG duoc de nguyen row lot qua -
    it nhat phai loc bo cac truong PII pho bien (fail-safe theo mac dinh)."""
    raw_row = {"random_field": 1, "name": "Should Be Dropped", "email": "x@example.com"}
    result = context_builder.build_context("SOME_UNKNOWN_INTENT", raw_row)
    assert "name" not in result.context
    assert "email" not in result.context
    assert "random_field" in result.context


def test_never_passes_a_raw_object_reference_only_plain_dict_fields():
    """Xac nhan ket qua la dict THUAN (khong phai reference toi object/row
    goc) - dam bao khong ai vo tinh sua context roi anh huong nguoc lai du
    lieu goc."""
    raw_row = {"current_gpa": 6.0, "credits_done": 20, "target_gpa": 7.5, "credits_remaining": 20, "gpa_scale": 10}
    result = context_builder.build_context("GPA_CALCULATION", raw_row)
    result.context["current_gpa"] = 999
    assert raw_row["current_gpa"] == 6.0, "Sua context KHONG duoc anh huong nguoc lai raw_row goc."
