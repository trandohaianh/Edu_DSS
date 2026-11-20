"""Circuit Breaker — OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE Phần 16.

Hoàn thiện chuỗi resilience AI (Timeout → Retry → Circuit Breaker → Failover
→ Safe Fallback → UI Error State) — trước đợt này chỉ có Retry (Tenacity) và
Failover (H-3, đợt trước): khi 1 provider lỗi, hệ thống LUÔN thử gọi lại
provider đó ở lượt request TIẾP THEO (không nhớ nó vừa lỗi) — lãng phí thời
gian chờ/quota cho 1 provider đang biết chắc là hỏng (vd. hết hạn mức thanh
toán — sẽ còn lỗi trong nhiều phút/giờ tới, không phải lỗi tạm thời).

Circuit Breaker = mạch ngắt tạm dừng gửi request tới 1 provider đang lỗi
liên tục, để hệ thống tự động BỎ QUA nó (nhảy thẳng sang provider dự phòng)
thay vì lãng phí 1 lượt gọi + chờ timeout mỗi lần.

3 trạng thái (đúng mô hình chuẩn):
- CLOSED: bình thường, cho gọi provider.
- OPEN: provider vừa lỗi liên tiếp đủ ngưỡng — TỪ CHỐI gọi (coi như thất bại
  ngay, không tốn thời gian chờ) cho tới khi hết thời gian nghỉ (cooldown).
- HALF_OPEN: hết cooldown, cho phép ĐÚNG 1 lượt thử — thành công thì đóng
  mạch lại (CLOSED), thất bại thì mở lại (OPEN), reset cooldown.

Theo dõi RIÊNG BIỆT cho từng provider (`provider_key`) — 1 provider lỗi
KHÔNG được làm tắt AI toàn hệ thống (đúng yêu cầu Phần 16: "Không được tắt
toàn bộ AI chỉ vì 1 provider lỗi").

Lưu trạng thái trong bộ nhớ tiến trình (module-level dict + lock) — CÙNG mẫu
`_REQUEST_TIMESTAMPS`/`_RATE_LIMIT_LOCK` đã có trong `llm_gateway.py`. Không
sống sót qua khởi động lại tiến trình (chấp nhận được — giống hạn chế đã biết
của rate-limit lockout, xem `FINAL_CAPABILITY_MATRIX.csv` cũ)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

STATE_CLOSED = "CLOSED"
STATE_OPEN = "OPEN"
STATE_HALF_OPEN = "HALF_OPEN"

# Ngưỡng số lỗi LIÊN TIẾP để mở mạch — chọn 3 (không quá nhạy với 1 lỗi mạng
# thoáng qua, nhưng đủ nhanh để không lãng phí nhiều lượt gọi cho provider
# đã rõ ràng đang hỏng).
_FAILURE_THRESHOLD = 3
# Thời gian nghỉ trước khi cho thử lại (giây) — đủ ngắn để không "quên" 1
# provider đã hồi phục quá lâu, đủ dài để không dội request liên tục vào 1
# provider đang lỗi thật (billing/quota thường không tự hồi phục trong vài giây).
_COOLDOWN_SECONDS = 30.0


@dataclass
class _BreakerState:
    state: str = STATE_CLOSED
    consecutive_failures: int = 0
    opened_at: Optional[float] = None


_breakers: Dict[str, _BreakerState] = {}
_lock = threading.Lock()


def reset_all() -> None:
    """Chỉ dùng cho test — xóa toàn bộ trạng thái mạch để mỗi test bắt đầu
    từ CLOSED, không phụ thuộc thứ tự chạy test khác."""
    with _lock:
        _breakers.clear()


def _get_or_create(provider_key: str) -> _BreakerState:
    if provider_key not in _breakers:
        _breakers[provider_key] = _BreakerState()
    return _breakers[provider_key]


def allow_request(provider_key: str, *, now: Optional[float] = None) -> bool:
    """True nếu được phép gọi `provider_key` ngay bây giờ. False nếu mạch
    đang OPEN và chưa hết cooldown — nơi gọi PHẢI coi đây là thất bại tức
    thì và chuyển sang provider dự phòng, KHÔNG được tự ý bỏ qua Circuit
    Breaker để vẫn gọi provider đang mở mạch."""
    now = now if now is not None else time.monotonic()
    with _lock:
        b = _get_or_create(provider_key)
        if b.state == STATE_CLOSED:
            return True
        if b.state == STATE_OPEN:
            if b.opened_at is not None and (now - b.opened_at) >= _COOLDOWN_SECONDS:
                # Hết cooldown -> chuyển HALF_OPEN, cho phép ĐÚNG 1 lượt thử.
                b.state = STATE_HALF_OPEN
                return True
            return False
        # HALF_OPEN: đã có 1 lượt thử đang chờ kết quả — không cho thêm lượt
        # thứ 2 chồng lên (tránh nhiều request đồng thời cùng "thử" 1 lúc).
        return False


def record_success(provider_key: str) -> None:
    """Gọi provider thành công — đóng mạch lại, xóa hết bộ đếm lỗi."""
    with _lock:
        b = _get_or_create(provider_key)
        b.state = STATE_CLOSED
        b.consecutive_failures = 0
        b.opened_at = None


def record_failure(provider_key: str, *, now: Optional[float] = None) -> None:
    """Gọi provider thất bại — tăng bộ đếm lỗi liên tiếp; mở mạch nếu đã đạt
    ngưỡng (hoặc nếu đang HALF_OPEN — 1 lượt thử lại thất bại thì mở lại
    NGAY, không cần đếm lại từ đầu)."""
    now = now if now is not None else time.monotonic()
    with _lock:
        b = _get_or_create(provider_key)
        if b.state == STATE_HALF_OPEN:
            b.state = STATE_OPEN
            b.opened_at = now
            b.consecutive_failures = _FAILURE_THRESHOLD
            return
        b.consecutive_failures += 1
        if b.consecutive_failures >= _FAILURE_THRESHOLD:
            b.state = STATE_OPEN
            b.opened_at = now


def get_state(provider_key: str) -> str:
    with _lock:
        return _get_or_create(provider_key).state
