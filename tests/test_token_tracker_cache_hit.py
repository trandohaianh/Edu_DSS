"""P1 (tự phát hiện, OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE — trong lúc viết
test tích hợp Circuit Breaker): `llm_gateway.py::stream_generate()` LUÔN gọi
`token_tracker.record_usage(..., cache_hit=True)` khi phục vụ 1 câu trả lời
từ cache (nhánh "MỤC 20: Kiểm tra Cache trước khi gọi inference") — nhưng
`record_usage()` KHÔNG nhận tham số `cache_hit`, nên MỌI lượt cache-hit đều
làm hàm này raise `TypeError` NGAY SAU KHI đã `yield` xong câu trả lời cache
cho người dùng. Nếu nơi gọi `stream_generate()` gom hết chunk bằng
`"".join(...)` TRƯỚC KHI hiển thị (đúng mẫu `ai_advisor.py` dùng cho luồng
chat: `_answer = "".join(_stream)`), exception này làm MẤT câu trả lời cache
đã có sẵn (nhanh, đúng) và bị outer try/except thay bằng thông báo lỗi
chung — trong khi AI thực ra đã trả lời thành công, chỉ 1 dòng ghi log
token bị lỗi. Đây chính là loại lỗi "hệ thống báo lỗi trong khi thực ra đã
làm việc" mà đợt audit này yêu cầu tìm."""

from __future__ import annotations

from dss.services import token_tracker


def test_record_usage_accepts_cache_hit_without_raising():
    record = token_tracker.record_usage(
        user_id="sv_test",
        role="Sinh viên",
        request_type="advisor_chat",
        provider="cache",
        model="cache_hit",
        input_tokens=10,
        output_tokens=20,
        cache_hit=True,
    )
    assert record.cache_hit is True


def test_cache_hit_usage_has_zero_cost_not_real_provider_pricing():
    """Lượt cache-hit không gọi provider thật -> KHÔNG được tính phí như thể
    đã gọi 1 model đắt tiền (vd. gpt-4o) — nếu không sẽ báo cáo chi phí sai
    (cao hơn thực tế) cho mọi lượt phục vụ từ cache."""
    record = token_tracker.record_usage(
        user_id="sv_test",
        role="Sinh viên",
        request_type="advisor_chat",
        provider="openai",
        model="gpt-4o",
        input_tokens=10_000,
        output_tokens=10_000,
        cache_hit=True,
    )
    assert record.estimated_cost == 0.0


def test_non_cache_hit_usage_still_computes_real_cost():
    """Không phá hành vi cũ: lượt KHÔNG phải cache-hit vẫn tính phí bình
    thường như trước (cache_hit mặc định False)."""
    record = token_tracker.record_usage(
        user_id="sv_test",
        role="Sinh viên",
        request_type="advisor_chat",
        provider="openai",
        model="gpt-4o",
        input_tokens=10_000,
        output_tokens=10_000,
    )
    assert record.cache_hit is False
    assert record.estimated_cost > 0.0


def test_stream_generate_cache_hit_path_does_not_crash(monkeypatch):
    """Test tích hợp thật qua LLMGateway.stream_generate(): gọi 2 lần với
    CÙNG prompt+role (lần 2 phải trúng cache) — lần 2 KHÔNG được raise."""
    from dss.services.llm_gateway import LLMGateway

    class _FakeIntegration:
        def call_ai_provider(self, prompt, provider, model_name=None, **kwargs):
            yield "Câu trả lời thật, sẽ được lưu vào cache."

        def get_api_key_from_secrets(self, provider_name):
            return "fake-key"

    def _fake_resolve(self, requested_provider=None, requested_model=None, role="Sinh viên", explicit_api_key=None):
        return "groq", "groq-model", "fake-key"

    monkeypatch.setattr(LLMGateway, "resolve_active_provider_and_model", _fake_resolve)
    monkeypatch.setattr(LLMGateway, "_check_rate_limit", lambda self: None)
    monkeypatch.setenv("DSS_PRIMARY_PROVIDER", "groq")

    gateway = LLMGateway(llm_integration=_FakeIntegration())
    unique_prompt = "Câu hỏi test cache-hit duy nhất cho lượt chạy này"

    first = "".join(
        gateway.stream_generate(
            prompt=unique_prompt,
            user_id="sv_cache_test",
            role="Sinh viên",
            request_type="advisor_chat",
        )
    )
    assert "Câu trả lời thật" in first

    # Lần 2: CÙNG prompt+role -> phải trúng cache (llm_exact::<hash(prompt+role)>)
    # -> không được raise TypeError, phải trả về ĐÚNG câu trả lời đã cache.
    second = "".join(
        gateway.stream_generate(
            prompt=unique_prompt,
            user_id="sv_cache_test",
            role="Sinh viên",
            request_type="advisor_chat",
        )
    )
    assert second == first, "Lượt cache-hit phải trả về ĐÚNG câu trả lời đã cache, không phải thông báo lỗi thay thế."
