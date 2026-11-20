"""Context Budget Manager — Quản lý và điều phối ngân sách token ngữ cảnh cho LLM.

Phân bổ rõ ràng:
- system_prompt: tối đa 500 tokens
- student_context: tối đa 300 tokens
- rag_context: tối đa 1,500 tokens
- chat_history: tối đa 800 tokens
- output_reserve: tối đa 1,000 tokens

Thay vì âm thầm để vượt quá giới hạn ngữ cảnh (dẫn tới bị model cắt ngang hoặc tốn chi phí),
hệ thống chủ động cắt tỉa (trim) và tóm lược các phần ngữ cảnh theo thứ tự ưu tiên.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TokenBudgetConfig:
    system_prompt: int = 500
    student_context: int = 300
    rag_context: int = 1500
    chat_history: int = 800
    output_reserve: int = 1000

    @property
    def total_input_budget(self) -> int:
        return self.system_prompt + self.student_context + self.rag_context + self.chat_history


def approximate_token_count(text: str) -> int:
    """Ước lượng số token của văn bản (áp dụng cho tiếng Việt và tiếng Anh).

    Tiếng Việt có nhiều từ đơn và dấu thanh nên tỷ lệ trung bình ~1.2 - 1.5 token / từ,
    hoặc xấp xỉ 1 token cho mỗi 3 - 4 ký tự.
    """
    if not text:
        return 0
    clean = str(text).strip()
    words = clean.split()
    # Ước lượng: max giữa (ký tự / 3.5) và (từ * 1.3)
    by_chars = len(clean) / 3.5
    by_words = len(words) * 1.3
    return max(1, int(round(max(by_chars, by_words))))


def trim_rag_chunks_to_budget(
    chunks: List[Dict[str, Any]],
    max_tokens: int = 1500,
) -> Tuple[List[Dict[str, Any]], int]:
    """Cắt tỉa danh sách chunks RAG (đã được sắp xếp theo độ liên quan giảm dần)

    để đảm bảo tổng số token không vượt quá ngân sách `max_tokens`.
    """
    selected_chunks = []
    current_tokens = 0

    for c in chunks:
        content = c.get("content", "")
        title = c.get("title", "")
        c_tokens = c.get("token_count") or approximate_token_count(f"{title} {content}")

        if current_tokens + c_tokens <= max_tokens:
            selected_chunks.append(c)
            current_tokens += c_tokens
        else:
            # Nếu còn dư ít nhất 150 tokens, có thể cắt bớt nội dung chunk này để nạp một phần
            remaining_budget = max_tokens - current_tokens
            if remaining_budget >= 150 and not selected_chunks:
                # Cắt gọn chunk đầu tiên nếu quá dài
                cutoff_chars = int(remaining_budget * 3.2)
                partial_chunk = dict(c)
                partial_chunk["content"] = content[:cutoff_chars] + "..."
                partial_chunk["token_count"] = remaining_budget
                selected_chunks.append(partial_chunk)
                current_tokens += remaining_budget
            break

    return selected_chunks, current_tokens


def trim_chat_history_to_budget(
    messages: List[Dict[str, str]],
    max_tokens: int = 800,
) -> Tuple[List[Dict[str, str]], int]:
    """Cắt tỉa lịch sử hội thoại: Giữ lại các tin nhắn MỚI NHẤT,

    bỏ các tin nhắn cũ phía trên khi vượt ngân sách token.
    """
    if not messages:
        return [], 0

    kept_messages = []
    current_tokens = 0

    # Duyệt ngược từ tin nhắn mới nhất về cũ nhất
    for msg in reversed(messages):
        msg_text = msg.get("content", "")
        t_count = approximate_token_count(msg_text)
        if current_tokens + t_count <= max_tokens:
            kept_messages.insert(0, msg)
            current_tokens += t_count
        else:
            break

    return kept_messages, current_tokens
