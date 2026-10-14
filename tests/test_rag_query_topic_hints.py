"""A-3: Bảng gợi ý chủ đề RAG (_COLUMN_RAG_TOPIC_HINTS) tra theo TÊN CỘT kỹ
thuật (vd. 'ty_le_diem_danh'), nhưng điểm yếu thật sự do ai_advisor.py tạo ra
có dạng "**Tỷ lệ điểm danh** (SV: x, TB lớp: y)" — NHÃN TIẾNG VIỆT, không bao
giờ trùng khóa kỹ thuật -> bảng gợi ý là code chết trong luồng Tư vấn AI thật."""
from __future__ import annotations

from dss.core.models import MultiAIProvider


def _build(weaknesses):
    advisor = MultiAIProvider.__new__(MultiAIProvider)
    return advisor._build_rag_query_from_weaknesses(weaknesses)


def test_real_format_weakness_label_matches_topic_hint():
    # Đúng định dạng THẬT do ai_advisor.py tạo (xem dss/tabs/ai_advisor.py, mục
    # "2. Bổ sung các chỉ số học thuật tụt hậu...").
    weakness = "**Tỷ lệ điểm danh** (SV: **0.65**, TB lớp: **0.80**)"
    query = _build([weakness])
    assert "động lực học tập" in query, query


def test_real_format_weakness_label_matches_topic_hint_for_project_score():
    weakness = "**Điểm dự án** (SV: **5.50**, TB lớp: **7.00**)"
    query = _build([weakness])
    assert "làm dự án" in query, query


def test_raw_column_name_still_works_backward_compatible():
    query = _build(["ty_le_diem_danh"])
    assert "động lực học tập" in query, query
