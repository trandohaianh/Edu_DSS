"""OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE — Phần 7: Semantic/Exact Cache
audit. P0 tự phát hiện: `cache_key` trong `LLMGateway.stream_generate()`
(dss/services/llm_gateway.py) TRƯỚC KHI SỬA chỉ băm `prompt + role`, KHÔNG
gồm `user_id` — nếu 2 sinh viên KHÁC NHAU (2 user_id khác nhau) gửi prompt
trùng CHUỖI KÝ TỰ (hoàn toàn có thể xảy ra: dataset mô phỏng có ít giá trị
phân loại nên nhiều hồ sơ context giống hệt nhau, hoặc câu hỏi không kèm
theo ngữ cảnh cá nhân hóa nào), sinh viên B sẽ nhận được CÂU TRẢ LỜI ĐÃ
CACHE của sinh viên A — rò rỉ dữ liệu cá nhân hóa (điểm số, cảnh báo học vụ,
tư vấn riêng) CHÉO giữa 2 người dùng khác nhau. Đây đúng là rủi ro P0 mà đề
bài cảnh báo rõ: "Semantic Cache must be scoped by ... user ... — must
NEVER leak Student A's response to Student B"."""

from __future__ import annotations

import pytest

from dss.services import circuit_breaker as cb
from dss.services.llm_gateway import LLMGateway
from dss.services.semantic_cache import layered_cache


@pytest.fixture(autouse=True)
def _reset_breaker():
    cb.reset_all()
    yield
    cb.reset_all()


class _RespondsWithUserSpecificMarker:
    def __init__(self):
        self.calls: list[str] = []

    def call_ai_provider(self, prompt, provider, model_name=None, **kwargs):
        self.calls.append(prompt)
        yield "CÂU TRẢ LỜI CÁ NHÂN HÓA CHO SINH VIÊN A: GPA của bạn là 2.1, bạn đang bị cảnh báo học vụ."

    def get_api_key_from_secrets(self, provider_name):
        return "fake-key"


def _patch_chain(monkeypatch, fake_integration, chain=("gemini", "gemini", "gemini")):
    def _fake_resolve(self, requested_provider=None, requested_model=None, role="Sinh viên", explicit_api_key=None):
        return requested_provider, f"{requested_provider}-model", "fake-key"

    monkeypatch.setattr(LLMGateway, "resolve_active_provider_and_model", _fake_resolve)
    monkeypatch.setattr(LLMGateway, "_check_rate_limit", lambda self: None)
    monkeypatch.setenv("DSS_PRIMARY_PROVIDER", chain[0])
    monkeypatch.setenv("DSS_FALLBACK_1", chain[1])
    monkeypatch.setenv("DSS_FALLBACK_2", chain[2])
    return LLMGateway(llm_integration=fake_integration)


def test_cross_user_same_prompt_text_does_not_leak_cached_personalized_answer(monkeypatch):
    """2 user_id KHÁC NHAU, prompt CÙNG CHUỖI KÝ TỰ -> PHẢI là 2 cache entry
    RIÊNG BIỆT (cache MISS cho user thứ 2), không được phục vụ chéo."""
    fake = _RespondsWithUserSpecificMarker()
    gateway = _patch_chain(monkeypatch, fake)

    shared_prompt = "Prompt-giong-het-nhau-ve-chuoi-ky-tu-test-cross-user-isolation"
    answer_a = "".join(
        gateway.stream_generate(
            prompt=shared_prompt,
            user_id="pseudo_student_A",
            role="Sinh viên",
            request_type="advisor_chat",
        )
    )
    assert "SINH VIÊN A" in answer_a

    fake.calls.clear()
    answer_b = "".join(
        gateway.stream_generate(
            prompt=shared_prompt,
            user_id="pseudo_student_B",
            role="Sinh viên",
            request_type="advisor_chat",
        )
    )
    assert fake.calls, (
        "Với user_id KHÁC, PHẢI là cache MISS (provider được gọi lại) — "
        "KHÔNG được trả thẳng câu trả lời cá nhân hóa đã cache của sinh viên A "
        "cho sinh viên B."
    )
    assert answer_b == answer_a, (
        "Fake provider trả lời giống hệt (không phân biệt input) — chỉ xác nhận KHÔNG phục vụ từ cache, không xác nhận nội dung khác nhau."
    )


def test_same_user_same_prompt_still_benefits_from_cache(monkeypatch):
    """Fix KHÔNG được vô tình tắt cache cho ĐÚNG 1 user hỏi lại chính câu đó
    — vẫn phải cache HIT khi user_id GIỐNG NHAU."""
    fake = _RespondsWithUserSpecificMarker()
    gateway = _patch_chain(monkeypatch, fake)

    shared_prompt = "Prompt-rieng-cho-test-same-user-cache-hit"
    "".join(
        gateway.stream_generate(
            prompt=shared_prompt,
            user_id="pseudo_student_C",
            role="Sinh viên",
            request_type="advisor_chat",
        )
    )
    fake.calls.clear()
    "".join(
        gateway.stream_generate(
            prompt=shared_prompt,
            user_id="pseudo_student_C",
            role="Sinh viên",
            request_type="advisor_chat",
        )
    )
    assert not fake.calls, "CÙNG 1 user_id hỏi lại CÙNG prompt vẫn phải là cache HIT (không gọi lại provider)."


def test_invalidate_student_now_actually_clears_entries_cached_via_stream_generate(monkeypatch):
    """Trước fix dimensions ({"role": role} thiếu "student_pseudonym"),
    layered_cache.invalidate_student(pseudonym) KHÔNG BAO GIỜ khớp được entry
    nào tạo từ stream_generate() — cache cá nhân hóa không bao giờ bị hủy khi
    có điểm/dữ liệu mới, chỉ hết hạn theo TTL (tới 1 giờ). Test này xác nhận
    invalidate_student() giờ THẬT SỰ có tác dụng trên cache do
    stream_generate() tạo ra."""
    fake = _RespondsWithUserSpecificMarker()
    gateway = _patch_chain(monkeypatch, fake)

    prompt = "Prompt-rieng-cho-test-invalidate-student"
    "".join(
        gateway.stream_generate(
            prompt=prompt,
            user_id="pseudo_student_D",
            role="Sinh viên",
            request_type="advisor_chat",
        )
    )
    fake.calls.clear()
    "".join(
        gateway.stream_generate(
            prompt=prompt,
            user_id="pseudo_student_D",
            role="Sinh viên",
            request_type="advisor_chat",
        )
    )
    assert not fake.calls, "Trước khi invalidate, vẫn phải là cache HIT."

    cleared = layered_cache.invalidate_student("pseudo_student_D")
    assert cleared >= 1, "invalidate_student() phải khớp được entry vừa cache (dimension student_pseudonym)."

    fake.calls.clear()
    "".join(
        gateway.stream_generate(
            prompt=prompt,
            user_id="pseudo_student_D",
            role="Sinh viên",
            request_type="advisor_chat",
        )
    )
    assert fake.calls, "Sau invalidate_student(), lượt hỏi lại PHẢI là cache MISS (gọi lại provider)."
