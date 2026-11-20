"""H-3 (phát hiện trong đợt "FINAL PRODUCTION GAP CLOSURE", tự audit AI error
handling — Phần 3): `MultiAIProvider.call_ai_provider()` KHÔNG BAO GIỜ raise
exception khi provider lỗi — nó BẮT lỗi nội bộ và `yield` một chuỗi thân
thiện (vd. "⚠️ Hệ thống AI (Gemini) hiện gặp sự cố...", "💳 ...hết hạn mức
thanh toán...", "⏳ ...bị giới hạn tần suất..."). Đây là thiết kế CÓ CHỦ Ý
(không lộ exception thô).

NHƯNG `LLMGateway.stream_generate()` (tầng fallback chain PRIMARY -> FALLBACK_1
-> FALLBACK_2 -> demo) chỉ coi 1 lần gọi là THẤT BẠI khi `call_ai_provider`
THỰC SỰ RAISE (khối `except Exception as call_err`). Vì `call_ai_provider`
không bao giờ raise, MỌI stream không rỗng (kể cả một stream CHỈ GỒM đúng 1
câu lỗi thân thiện) đều bị đánh dấu `success = True` và dừng fallback chain
NGAY TẠI ĐÓ — provider B (đang khoẻ mạnh, có key hợp lệ) KHÔNG BAO GIỜ được
thử, dù đó chính là mục đích của fallback chain. Người dùng nhận được câu
lỗi của provider A HIỂN THỊ NHƯ THỂ đó là câu trả lời cuối cùng — đúng loại
lỗi "'success' giả" mà audit yêu cầu tìm.

Bug này bị H-1 (đợt trước) LÀM LỘ RA: trước H-1, `stream_generate` hầu như
luôn đi qua nhánh `generate_personalized_advice` (nhánh đó tự có logic dò
lỗi ở first-chunk và tự "chữa lành" bằng kế hoạch demo) — nhánh
`call_ai_provider` thô hầu như không bao giờ chạy tới. Sau H-1 (routing
theo request_type), nhánh `call_ai_provider` chạy thật cho advisor_chat/
learning_explainer/home_quick_chat — làm lộ gap failover này."""

from __future__ import annotations

from dss.services.llm_gateway import LLMGateway


class _FriendlyErrorThenSuccessIntegration:
    """Fake llm_integration: provider 'gemini' LUÔN trả lỗi thân thiện (không
    raise, giống call_ai_provider thật khi hết quota/billing), provider 'groq'
    LUÔN trả lời thật thành công."""

    def __init__(self):
        self.attempts: list[str] = []

    def call_ai_provider(self, prompt, provider, model_name=None, **kwargs):
        self.attempts.append(provider)
        if provider == "gemini":
            yield "💳 Hệ thống AI (Gemini) hiện không thể dùng do tài khoản đã hết hạn mức thanh toán/tín dụng."
            return
        if provider == "groq":
            yield "Đây là câu trả lời thật từ Groq: "
            yield "kế hoạch học tập của bạn gồm 4 tuần..."
            return
        yield "🔒 Trợ lý AI hiện chưa khả dụng."

    def get_api_key_from_secrets(self, provider_name):
        return "fake-key-for-test"


def _patch_gateway_for_two_provider_chain(monkeypatch, fake_integration):
    """Bỏ qua toàn bộ logic phân giải provider thật (đọc admin config/secrets
    thật) — chỉ test riêng hành vi failover của stream_generate khi
    call_ai_provider trả lỗi thân thiện."""

    def _fake_resolve(self, requested_provider=None, requested_model=None, role="Sinh viên", explicit_api_key=None):
        return requested_provider, f"{requested_provider}-model", "fake-key"

    monkeypatch.setattr(LLMGateway, "resolve_active_provider_and_model", _fake_resolve)
    monkeypatch.setattr(LLMGateway, "_check_rate_limit", lambda self: None)
    monkeypatch.setenv("DSS_PRIMARY_PROVIDER", "gemini")
    monkeypatch.setenv("DSS_FALLBACK_1", "groq")
    monkeypatch.setenv("DSS_FALLBACK_2", "groq")
    monkeypatch.setenv("EDUDSS_MODE", "DEMO_SYNTHETIC")
    return LLMGateway(llm_integration=fake_integration)


def test_friendly_error_from_primary_provider_does_not_stop_failover(monkeypatch):
    fake = _FriendlyErrorThenSuccessIntegration()
    gateway = _patch_gateway_for_two_provider_chain(monkeypatch, fake)

    chunks = list(
        gateway.stream_generate(
            prompt="Kế hoạch học tập của tôi thế nào?",
            user_id="sv_test",
            role="Sinh viên",
            request_type="advisor_chat",
        )
    )
    full_answer = "".join(chunks)

    assert fake.attempts == ["gemini", "groq"], (
        f"Fallback chain phải thử 'groq' SAU KHI 'gemini' trả lỗi thân thiện — thực tế chỉ thử: {fake.attempts}"
    )
    assert "câu trả lời thật từ Groq" in full_answer, (
        "Người dùng phải nhận câu trả lời THẬT từ provider dự phòng (groq), "
        "không phải câu lỗi của provider chính (gemini) hiển thị như câu trả lời cuối cùng."
    )
    assert "hết hạn mức thanh toán" not in full_answer, (
        "Câu lỗi thân thiện của gemini không được hiển thị cho người dùng như thể "
        "đó là câu trả lời cuối cùng khi vẫn còn provider dự phòng khả dụng."
    )
