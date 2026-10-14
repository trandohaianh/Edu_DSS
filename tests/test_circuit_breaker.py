"""OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE — Phần 16: Circuit Breaker.
Hoàn thiện chuỗi resilience AI: Timeout → Retry → Circuit Breaker → Failover
→ Safe Fallback → UI Error State. Trạng thái CLOSED/OPEN/HALF_OPEN, theo dõi
RIÊNG từng provider (1 provider lỗi không được tắt AI toàn hệ thống)."""
from __future__ import annotations

import pytest

from dss.services import circuit_breaker as cb


@pytest.fixture(autouse=True)
def _reset():
    cb.reset_all()
    yield
    cb.reset_all()


def test_starts_closed_and_allows_requests():
    assert cb.get_state("gemini") == cb.STATE_CLOSED
    assert cb.allow_request("gemini") is True


def test_opens_after_threshold_consecutive_failures():
    for _ in range(cb._FAILURE_THRESHOLD):
        cb.record_failure("gemini", now=0.0)
    assert cb.get_state("gemini") == cb.STATE_OPEN
    assert cb.allow_request("gemini", now=1.0) is False, "Mạch OPEN phải từ chối request ngay, không đợi timeout thật"


def test_one_failing_provider_does_not_open_other_providers():
    """1 provider lỗi liên tục KHÔNG được làm tắt AI cho provider khác —
    đúng yêu cầu 'không được tắt toàn bộ AI chỉ vì 1 provider lỗi'."""
    for _ in range(cb._FAILURE_THRESHOLD):
        cb.record_failure("gemini", now=0.0)
    assert cb.get_state("gemini") == cb.STATE_OPEN
    assert cb.get_state("groq") == cb.STATE_CLOSED
    assert cb.allow_request("groq") is True


def test_success_resets_failure_count():
    cb.record_failure("gemini", now=0.0)
    cb.record_failure("gemini", now=0.0)
    cb.record_success("gemini")
    assert cb.get_state("gemini") == cb.STATE_CLOSED
    # Sau khi thành công, cần lại ĐỦ ngưỡng lỗi liên tiếp mới mở mạch (không
    # cộng dồn từ trước khi thành công).
    for _ in range(cb._FAILURE_THRESHOLD - 1):
        cb.record_failure("gemini", now=0.0)
    assert cb.get_state("gemini") == cb.STATE_CLOSED


def test_transitions_to_half_open_after_cooldown():
    for _ in range(cb._FAILURE_THRESHOLD):
        cb.record_failure("gemini", now=0.0)
    assert cb.allow_request("gemini", now=cb._COOLDOWN_SECONDS + 1) is True
    assert cb.get_state("gemini") == cb.STATE_HALF_OPEN


def test_half_open_success_closes_circuit():
    for _ in range(cb._FAILURE_THRESHOLD):
        cb.record_failure("gemini", now=0.0)
    cb.allow_request("gemini", now=cb._COOLDOWN_SECONDS + 1)
    assert cb.get_state("gemini") == cb.STATE_HALF_OPEN
    cb.record_success("gemini")
    assert cb.get_state("gemini") == cb.STATE_CLOSED
    assert cb.allow_request("gemini") is True


def test_half_open_failure_reopens_circuit_immediately():
    for _ in range(cb._FAILURE_THRESHOLD):
        cb.record_failure("gemini", now=0.0)
    cb.allow_request("gemini", now=cb._COOLDOWN_SECONDS + 1)
    assert cb.get_state("gemini") == cb.STATE_HALF_OPEN
    cb.record_failure("gemini", now=cb._COOLDOWN_SECONDS + 1)
    assert cb.get_state("gemini") == cb.STATE_OPEN
    assert cb.allow_request("gemini", now=cb._COOLDOWN_SECONDS + 2) is False


def test_half_open_does_not_allow_concurrent_double_trial():
    for _ in range(cb._FAILURE_THRESHOLD):
        cb.record_failure("gemini", now=0.0)
    assert cb.allow_request("gemini", now=cb._COOLDOWN_SECONDS + 1) is True
    # Lượt thứ 2 trong cùng thời điểm HALF_OPEN không được cho phép thêm
    # (tránh nhiều request đồng thời cùng "thử" 1 lúc).
    assert cb.allow_request("gemini", now=cb._COOLDOWN_SECONDS + 1) is False
