"""H-1 (CRITICAL, phát hiện trong đợt review kiến trúc thương mại): `LLMGateway.
stream_generate()` (dss/services/llm_gateway.py) định tuyến tới
`self.llm_integration.generate_personalized_advice(...)` MỘT CÁCH KHÔNG ĐIỀU
KIỆN bất cứ khi nào `llm_integration` có phương thức đó (`hasattr(...)`) —
BẤT KỂ `request_type` là gì. `MultiAIProvider` (llm_integration thật duy nhất
trong hệ thống) LUÔN có phương thức này, nên nhánh `elif
hasattr(self.llm_integration, "call_ai_provider")` — nơi `prompt` thực sự
được dùng — KHÔNG BAO GIỜ được chạy tới trong thực tế.

Hệ quả: MỌI lời gọi `stream_generate(prompt=<câu hỏi/prompt thật>, ...)` mà
KHÔNG có mục đích sinh "kế hoạch học tập" (advisor_chat, learning_explainer,
home_quick_chat) đều bị ÂM THẦM BỎ QUA `prompt` — thay vào đó
`generate_personalized_advice` tự xây MỘT prompt HOÀN TOÀN KHÁC (kế hoạch
học tập chung, `student_weaknesses=[]`, `predicted_gpa=0.0` vì các call site
này không truyền 2 tham số đó). Người dùng gõ câu hỏi X nhưng AI trả lời cho
một câu hỏi khác hẳn (Y) mà họ chưa từng hỏi — lỗi CORRECTNESS mức P0.

Test dưới đây đi qua PUBLIC API `LLMGateway.stream_generate()`, dùng fake
provider ghi lại CHÍNH XÁC những gì nó nhận được, để chứng minh prompt thật
có tới nơi hay không — không kiểm tra qua mock nội bộ dễ bị "giả xanh"."""

from __future__ import annotations

import pytest

from dss.services.llm_gateway import LLMGateway


@pytest.fixture(autouse=True)
def _no_safety_classifier_on_fake_answers(monkeypatch):
    """Test này kiểm cache/định tuyến của LLMGateway với câu trả lời GIẢ (ECHO::..., chữ in hoa).
    Từ 21/11/2026 câu trả lời đi qua bộ lọc an toàn (dss/services/output_guard.py); bộ phân loại
    học được cho các chuỗi giả này điểm ~0,55 nên tắt riêng nó ở đây (lớp từ khoá vẫn chạy)."""
    monkeypatch.setenv("EDUDSS_SAFETY_CLASSIFIER", "0")


class _RecordingLLMIntegration:
    """Fake llm_integration ghi lại đúng những gì mỗi phương thức nhận được,
    để phân biệt rạch ròi đường "chat/raw-prompt" (call_ai_provider) với
    đường "planning" (generate_personalized_advice) — 2 đường PHẢI tách biệt
    theo request_type, không phải theo `hasattr`."""

    def __init__(self):
        self.call_ai_provider_prompts: list[str] = []
        self.generate_personalized_advice_calls: list[tuple] = []

    def call_ai_provider(self, prompt, provider, model_name=None, **kwargs):
        self.call_ai_provider_prompts.append(prompt)
        yield f"ECHO::{prompt}"

    def generate_personalized_advice(
        self, student_weaknesses, predicted_gpa, provider, model_name=None, api_key=None, **kwargs
    ):
        self.generate_personalized_advice_calls.append((tuple(student_weaknesses or []), predicted_gpa))
        yield "GENERIC_STUDY_PLAN_TEXT_KHONG_LIEN_QUAN_TOI_CAU_HOI_THAT"

    def get_api_key_from_secrets(self, provider_name):
        return None


def test_advisor_chat_prompt_reaches_provider_verbatim():
    """Test 1 (bắt buộc theo yêu cầu): prompt = 'CÂU HỎI THỬ XYZ', request_type
    = 'advisor_chat' -> provider PHẢI nhận đúng prompt chứa 'CÂU HỎI THỬ XYZ'.
    Test này PHẢI FAIL trên code lỗi (trước khi sửa)."""
    fake = _RecordingLLMIntegration()
    gateway = LLMGateway(llm_integration=fake)

    chunks = list(
        gateway.stream_generate(
            prompt="CÂU HỎI THỬ XYZ",
            user_id="sv_test",
            role="Sinh viên",
            request_type="advisor_chat",
            provider="ollama",
            model="llama3",
        )
    )
    full_answer = "".join(chunks)

    assert fake.call_ai_provider_prompts, (
        "call_ai_provider() KHÔNG được gọi — prompt thật của người dùng bị bỏ qua "
        "(stream_generate đã rơi nhầm vào nhánh generate_personalized_advice)."
    )
    assert "CÂU HỎI THỬ XYZ" in fake.call_ai_provider_prompts[0]
    assert "CÂU HỎI THỬ XYZ" in full_answer
    assert not fake.generate_personalized_advice_calls, (
        "generate_personalized_advice() KHÔNG được gọi cho request_type='advisor_chat' "
        "— đây là đường dành riêng cho 'advisor_plan'."
    )


def test_two_different_chat_prompts_reach_provider_as_two_different_prompts():
    """Test 2 (bắt buộc): 2 câu hỏi chat khác nhau -> provider nhận 2 prompt khác nhau."""
    fake = _RecordingLLMIntegration()
    gateway = LLMGateway(llm_integration=fake)

    answer_1 = "".join(
        gateway.stream_generate(
            prompt="Làm sao để cải thiện điểm Toán?",
            user_id="sv_test",
            role="Sinh viên",
            request_type="advisor_chat",
            provider="ollama",
            model="llama3",
        )
    )
    answer_2 = "".join(
        gateway.stream_generate(
            prompt="Kỳ sau tôi nên đăng ký môn gì?",
            user_id="sv_test",
            role="Sinh viên",
            request_type="advisor_chat",
            provider="ollama",
            model="llama3",
        )
    )

    assert answer_1 != answer_2
    assert "Làm sao để cải thiện điểm Toán?" in answer_1
    assert "Kỳ sau tôi nên đăng ký môn gì?" in answer_2
    assert fake.call_ai_provider_prompts == [
        "Làm sao để cải thiện điểm Toán?",
        "Kỳ sau tôi nên đăng ký môn gì?",
    ]


def test_advisor_plan_still_uses_personalized_planning_path():
    """Test 3 (bắt buộc): request_type='advisor_plan' vẫn PHẢI đi đúng đường
    sinh kế hoạch cá nhân hóa (generate_personalized_advice), không phải
    call_ai_provider thô — hành vi ĐÚNG hiện có không được phá vỡ."""
    fake = _RecordingLLMIntegration()
    gateway = LLMGateway(llm_integration=fake)

    chunks = list(
        gateway.stream_generate(
            prompt="ngữ cảnh ước lượng token (không phải prompt thật gửi LLM cho đường này)",
            user_id="sv_test",
            role="Sinh viên",
            request_type="advisor_plan",
            provider="ollama",
            model="llama3",
            student_weaknesses=["toán", "lập trình"],
            predicted_gpa=6.5,
            use_rag=True,
            student_profile={"risk_level": "trung bình"},
        )
    )
    assert "".join(chunks) == "GENERIC_STUDY_PLAN_TEXT_KHONG_LIEN_QUAN_TOI_CAU_HOI_THAT"
    assert fake.generate_personalized_advice_calls == [(("toán", "lập trình"), 6.5)]
    assert not fake.call_ai_provider_prompts


def test_learning_explainer_prompt_reaches_provider_verbatim():
    """learning_explainer.py xây prompt đầy đủ rồi gọi stream_generate() giống
    hệt kiểu advisor_chat (không truyền student_weaknesses/predicted_gpa) —
    cùng lỗi H-1 nếu không sửa tại gốc (routing theo request_type, không phải
    theo hasattr)."""
    fake = _RecordingLLMIntegration()
    gateway = LLMGateway(llm_integration=fake)

    chunks = list(
        gateway.stream_generate(
            prompt="Giải thích khái niệm đệ quy trong bài giảng Lập trình 1",
            user_id="sv_test",
            role="Sinh viên",
            request_type="learning_explainer",
            provider="ollama",
            model="llama3",
        )
    )
    assert "Giải thích khái niệm đệ quy" in "".join(chunks)
    assert fake.call_ai_provider_prompts
    assert not fake.generate_personalized_advice_calls


def test_home_quick_chat_prompt_reaches_provider_verbatim():
    """Hộp hỏi nhanh ở Trang chủ (home.py) — cùng kiểu raw-prompt, cùng lỗi H-1."""
    fake = _RecordingLLMIntegration()
    gateway = LLMGateway(llm_integration=fake)

    chunks = list(
        gateway.stream_generate(
            prompt="Tôi có nên học thêm buổi tối không?",
            user_id="sv_test",
            role="Sinh viên",
            request_type="home_quick_chat",
            provider="ollama",
            model="llama3",
        )
    )
    assert "Tôi có nên học thêm buổi tối không?" in "".join(chunks)
    assert fake.call_ai_provider_prompts
    assert not fake.generate_personalized_advice_calls
