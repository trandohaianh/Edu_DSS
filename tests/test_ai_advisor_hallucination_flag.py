"""NHÓM F mục 5: câu trả lời chat có trích dẫn không khớp tài liệu đã nạp
(verify_citations phát hiện hallucinated_citations) trước đây CHỈ được nối
thêm 1 câu cảnh báo vào nội dung, nhưng vẫn lưu vào lịch sử chat như MỌI câu
trả lời khác — không có cách nào phân biệt "đã xác minh" với "chưa xác minh"
khi xem lại lịch sử. Giờ mỗi tin nhắn lưu kèm cờ `hallucinated` rõ ràng."""
from __future__ import annotations

import inspect

from dss.tabs import ai_advisor


def test_chat_history_entry_carries_hallucinated_flag():
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert '"hallucinated": _chat_has_hallucination' in source


def test_chat_render_shows_warning_for_hallucinated_messages():
    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert 'if _msg.get("hallucinated"):' in source
