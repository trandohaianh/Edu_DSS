"""Test Suite: search_service.py (tìm kiếm sinh viên toàn cục trên topbar).

Phủ đúng yêu cầu Part A/A2/A6/A9 của lượt "UI/RAG consistency pass — Part 2":
khớp chính xác, khớp một phần, trạng thái rỗng trung thực, và quan trọng nhất
— RBAC phải chặn TRƯỚC khi trả kết quả (Sinh viên không được cấp quyền tìm
kiếm sinh viên khác, bất kể query khớp gì)."""
from __future__ import annotations

import pandas as pd
import pytest

from dss.services import search_service


@pytest.fixture
def sample_df():
    return pd.DataFrame(
        {
            "student_id": ["SV001", "SV002", "SV010", "SV020"],
            "diem_ky_nay": [7.75, 6.79, 8.10, 5.55],
            "ty_le_diem_danh": [0.67, 0.64, 0.90, 0.40],
            "so_gio_hoc_tuan": [13.4, 11.2, 20.0, 5.0],
        }
    )


def test_exact_match_returns_single_result(sample_df):
    results = search_service.search_students(sample_df, "SV002", role="Admin")
    assert len(results) == 1
    assert results[0].student_id == "SV002"


def test_exact_match_ranked_before_partial_match(sample_df):
    """"SV01" khớp một phần với SV001 và SV010 — nhưng nếu người dùng gõ đúng
    "SV001", kết quả khớp CHÍNH XÁC phải đứng đầu danh sách."""
    results = search_service.search_students(sample_df, "SV001", role="Admin")
    assert results[0].student_id == "SV001"


def test_partial_match_case_insensitive(sample_df):
    results = search_service.search_students(sample_df, "sv0", role="Admin")
    ids = {r.student_id for r in results}
    assert "SV001" in ids
    assert "SV010" in ids


def test_no_result_returns_empty_list_not_dataframe(sample_df):
    results = search_service.search_students(sample_df, "SV999", role="Admin")
    assert results == []


def test_empty_state_message_format():
    msg = search_service.format_empty_state_message("SV999")
    assert msg == 'Không tìm thấy kết quả phù hợp với "SV999".'


def test_student_role_never_gets_results_even_on_exact_match(sample_df):
    """RBAC phải chặn TRƯỚC khi trả kết quả — không phải lọc sau khi đã trả
    toàn bộ dữ liệu về client."""
    results = search_service.search_students(sample_df, "SV002", role="Sinh viên")
    assert results == []


def test_lecturer_role_can_search_same_scope_as_admin(sample_df):
    admin_results = search_service.search_students(sample_df, "SV002", role="Admin")
    lecturer_results = search_service.search_students(sample_df, "SV002", role="Giảng viên / CVHT")
    assert len(admin_results) == len(lecturer_results) == 1
    assert admin_results[0].student_id == lecturer_results[0].student_id


def test_unknown_role_defaults_to_no_access(sample_df):
    results = search_service.search_students(sample_df, "SV002", role="Vai trò lạ")
    assert results == []


def test_none_dataframe_returns_empty(sample_df):
    results = search_service.search_students(None, "SV002", role="Admin")
    assert results == []


def test_empty_query_returns_empty(sample_df):
    results = search_service.search_students(sample_df, "", role="Admin")
    assert results == []
    results = search_service.search_students(sample_df, "   ", role="Admin")
    assert results == []


def test_results_include_humanized_metric_labels_not_raw_column_names(sample_df):
    results = search_service.search_students(sample_df, "SV002", role="Admin")
    labels = [label for label, _ in results[0].metrics]
    assert "diem_ky_nay" not in labels
    assert "ty_le_diem_danh" not in labels
    assert any(label for label in labels)  # có ít nhất 1 nhãn đã làm đẹp


def test_results_limited_to_max_five(sample_df):
    big_df = pd.DataFrame({"student_id": [f"SV{i:03d}" for i in range(50)], "diem_ky_nay": list(range(50))})
    results = search_service.search_students(big_df, "SV0", role="Admin")
    assert len(results) <= 5
