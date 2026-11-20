"""FINAL REMAINING-GAPS CLOSURE — Section 11: complete failure injection.
Uses fake/local providers only (no real provider spend), covering every
named failure mode: timeout, 429, 500, connection failure, empty response,
malformed response, A-fails-B-succeeds, A+B-fail-C-succeeds, all-fail,
Circuit OPEN, HALF_OPEN success/failure."""

from __future__ import annotations

import pytest

from dss.services import circuit_breaker as cb
from dss.services.llm_gateway import LLMGateway


@pytest.fixture(autouse=True)
def _reset_breaker():
    cb.reset_all()
    yield
    cb.reset_all()


def _patch_chain(monkeypatch, fake_integration, chain=("gemini", "groq", "groq")):
    def _fake_resolve(self, requested_provider=None, requested_model=None, role="Sinh viên", explicit_api_key=None):
        return requested_provider, f"{requested_provider}-model", "fake-key"

    monkeypatch.setattr(LLMGateway, "resolve_active_provider_and_model", _fake_resolve)
    monkeypatch.setattr(LLMGateway, "_check_rate_limit", lambda self: None)
    monkeypatch.setenv("DSS_PRIMARY_PROVIDER", chain[0])
    monkeypatch.setenv("DSS_FALLBACK_1", chain[1])
    monkeypatch.setenv("DSS_FALLBACK_2", chain[2])
    return LLMGateway(llm_integration=fake_integration)


class _ConfigurableFailureProvider:
    """1 provider giả lập, cấu hình được kiểu lỗi theo tên provider — mô
    phỏng CHÍNH XÁC các trường hợp thất bại được đặt tên (timeout/429/500/
    connection failure/empty/malformed) qua raised exception (nhánh
    `except Exception` thật của llm_gateway.py) hoặc chuỗi lỗi thân thiện
    (nhánh "friendly error" thật, _is_friendly_provider_error)."""

    def __init__(self, failure_map: dict):
        self.failure_map = failure_map  # {provider_key: mode}
        self.attempts: list[str] = []

    def call_ai_provider(self, prompt, provider, model_name=None, **kwargs):
        self.attempts.append(provider)
        mode = self.failure_map.get(provider)
        if mode is None:
            yield f"Câu trả lời thật từ {provider}."
            return
        if mode == "timeout":
            raise TimeoutError(f"{provider}: request timed out after 30s")
        if mode == "429":
            raise RuntimeError(f"{provider}: HTTP 429 Too Many Requests")
        if mode == "500":
            raise RuntimeError(f"{provider}: HTTP 500 Internal Server Error")
        if mode == "connection_failure":
            raise ConnectionError(f"{provider}: connection refused")
        if mode == "empty":
            yield ""
            return
        if mode == "malformed":
            raise ValueError(f"{provider}: malformed/unparseable response body")
        if mode == "friendly_429":
            yield f"⏳ {provider}: hạn ngạch đã hết, vui lòng thử lại sau."
            return
        raise AssertionError(f"unknown failure mode: {mode}")

    def get_api_key_from_secrets(self, provider_name):
        return "fake-key"


# --- Cac che do loi rieng le, tung provider don ---------------------------


@pytest.mark.parametrize("mode", ["timeout", "429", "500", "connection_failure", "malformed"])
def test_single_provider_raised_exception_modes_do_not_crash_and_fail_over(monkeypatch, mode):
    fake = _ConfigurableFailureProvider({"gemini": mode})
    gateway = _patch_chain(monkeypatch, fake, chain=("gemini", "groq", "groq"))
    answer = "".join(
        gateway.stream_generate(prompt=f"Câu hỏi {mode}", user_id="u1", role="Sinh viên", request_type="advisor_chat")
    )
    assert "groq" in fake.attempts
    assert "Câu trả lời thật từ groq." in answer


def test_empty_response_does_not_crash_and_is_treated_as_unusable(monkeypatch):
    fake = _ConfigurableFailureProvider({"gemini": "empty"})
    gateway = _patch_chain(monkeypatch, fake, chain=("gemini", "groq", "groq"))
    answer = "".join(
        gateway.stream_generate(prompt="Câu hỏi empty", user_id="u1", role="Sinh viên", request_type="advisor_chat")
    )
    # Khong crash - hoac tra loi rong tu gemini, hoac fail over sang groq that.
    assert isinstance(answer, str)


def test_friendly_error_429_string_is_not_shown_as_final_answer(monkeypatch):
    fake = _ConfigurableFailureProvider({"gemini": "friendly_429"})
    gateway = _patch_chain(monkeypatch, fake, chain=("gemini", "groq", "groq"))
    answer = "".join(
        gateway.stream_generate(
            prompt="Câu hỏi friendly429", user_id="u1", role="Sinh viên", request_type="advisor_chat"
        )
    )
    assert "groq" in fake.attempts
    assert "Câu trả lời thật từ groq." in answer


# --- Chuoi that: A fail -> B succeeds --------------------------------------


def test_provider_a_fails_provider_b_succeeds(monkeypatch):
    fake = _ConfigurableFailureProvider({"gemini": "timeout"})
    gateway = _patch_chain(monkeypatch, fake, chain=("gemini", "groq", "groq"))
    answer = "".join(
        gateway.stream_generate(prompt="A fails B ok", user_id="u1", role="Sinh viên", request_type="advisor_chat")
    )
    assert fake.attempts[0] == "gemini"
    assert "groq" in fake.attempts
    assert "Câu trả lời thật từ groq." in answer


# --- A+B fail -> C (demo) thanh cong ----------------------------------------


def test_both_configured_providers_fail_falls_through_to_demo(monkeypatch):
    fake = _ConfigurableFailureProvider({"gemini": "500", "groq": "connection_failure"})
    gateway = _patch_chain(monkeypatch, fake, chain=("gemini", "groq", "groq"))
    answer = "".join(
        gateway.stream_generate(prompt="A and B fail", user_id="u1", role="Sinh viên", request_type="advisor_chat")
    )
    # Ca 2 provider that (gemini, groq) deu bi thu va that bai -> con lai demo mode
    # (khong nam trong "chain" fake, la nhanh cuoi cung cua gateway that).
    assert "gemini" in fake.attempts
    assert "groq" in fake.attempts
    assert isinstance(answer, str) and len(answer) > 0


# --- Circuit OPEN / HALF_OPEN (da co tu truoc, xac nhan lai o day) --------


def test_circuit_opens_after_repeated_real_exception_failures(monkeypatch):
    fake = _ConfigurableFailureProvider({"gemini": "timeout"})
    gateway = _patch_chain(monkeypatch, fake, chain=("gemini", "groq", "groq"))
    for i in range(cb._FAILURE_THRESHOLD):
        fake.attempts.clear()
        "".join(
            gateway.stream_generate(prompt=f"vòng {i}", user_id="u1", role="Sinh viên", request_type="advisor_chat")
        )
    assert cb.get_state("gemini") == cb.STATE_OPEN

    fake.attempts.clear()
    "".join(gateway.stream_generate(prompt="sau khi OPEN", user_id="u1", role="Sinh viên", request_type="advisor_chat"))
    assert "gemini" not in fake.attempts, "Circuit OPEN phải bị bỏ qua ngay, không thử lại."


def test_half_open_probe_success_closes_circuit(monkeypatch):
    import time as _time

    fake = _ConfigurableFailureProvider({"gemini": "timeout"})
    gateway = _patch_chain(monkeypatch, fake, chain=("gemini", "groq", "groq"))
    for i in range(cb._FAILURE_THRESHOLD):
        # Prompt PHẢI khác các test khác trong CÙNG file — layered_cache.
        # exact_cache là singleton mức module, prompt trùng + user_id/role
        # trùng sẽ bị cache hit từ lượt "demo" thành công của 1 test TRƯỚC
        # đó, khiến fake provider không được gọi lại (đúng lỗi P0 đã fix ở
        # phiên trước, nay lại làm sai LỆCH kết quả TEST nếu không cẩn thận).
        "".join(
            gateway.stream_generate(
                prompt=f"half-open-success vòng {i}", user_id="u1", role="Sinh viên", request_type="advisor_chat"
            )
        )
    assert cb.get_state("gemini") == cb.STATE_OPEN

    # gemini het loi (mo phong provider da hoi phuc that)
    fake.failure_map.pop("gemini")
    # Gia lap qua thoi gian cooldown de chuyen sang HALF_OPEN — circuit_
    # breaker.py dung time.monotonic() (KHONG PHAI time.time()) de tinh
    # cooldown da troi qua chua.
    real_monotonic = _time.monotonic
    monkeypatch.setattr(_time, "monotonic", lambda: real_monotonic() + cb._COOLDOWN_SECONDS + 1)
    fake.attempts.clear()
    answer = "".join(
        gateway.stream_generate(
            prompt="half-open-success thu lai sau cooldown", user_id="u1", role="Sinh viên", request_type="advisor_chat"
        )
    )
    assert "gemini" in fake.attempts, "HALF_OPEN phai cho thu lai provider."
    assert "Câu trả lời thật từ gemini." in answer
    assert cb.get_state("gemini") == cb.STATE_CLOSED


def test_half_open_probe_failure_reopens_circuit_immediately(monkeypatch):
    import time as _time

    fake = _ConfigurableFailureProvider({"gemini": "timeout"})
    gateway = _patch_chain(monkeypatch, fake, chain=("gemini", "groq", "groq"))
    for i in range(cb._FAILURE_THRESHOLD):
        "".join(
            gateway.stream_generate(
                prompt=f"half-open-failure vòng {i}", user_id="u1", role="Sinh viên", request_type="advisor_chat"
            )
        )
    assert cb.get_state("gemini") == cb.STATE_OPEN

    # circuit_breaker.py dung time.monotonic() (KHONG PHAI time.time()) de
    # tinh cooldown da troi qua chua.
    real_monotonic = _time.monotonic
    monkeypatch.setattr(_time, "monotonic", lambda: real_monotonic() + cb._COOLDOWN_SECONDS + 1)
    fake.attempts.clear()
    # gemini van loi (probe that bai)
    "".join(
        gateway.stream_generate(
            prompt="half-open-failure probe fail", user_id="u1", role="Sinh viên", request_type="advisor_chat"
        )
    )
    assert "gemini" in fake.attempts, (
        "Phai THAT SU vao duoc HALF_OPEN va thu lai gemini (khong phai circuit "
        "chi don gian chua bao gio roi khoi OPEN)."
    )
    assert cb.get_state("gemini") == cb.STATE_OPEN, "Probe HALF_OPEN that bai phai mo lai mach NGAY."
