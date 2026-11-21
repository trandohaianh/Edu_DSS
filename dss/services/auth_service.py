"""Authentication + RBAC — Phase 1 của kế hoạch refactor EduDSS.

Thay thế HAI cơ chế "tự nhận danh tính" cũ (đã xác minh là lỗ hổng Critical
trong bản đánh giá kiến trúc):
    1. `render_role_switcher()` (dss/core/roles.py)      — tự chọn vai trò, không mật khẩu.
    2. `_render_student_login_gate()` (dss/main.py cũ)   — tự chọn student_id từ dropdown.

bằng MỘT cổng đăng nhập username/password thật, băm bằng PBKDF2-HMAC-SHA256
(thư viện chuẩn `hashlib`, không cần cài thêm dependency). Nơi lưu tài khoản
chọn bằng biến môi trường `EDUDSS_IDENTITY_STORE` (xem
`dss/core/persistence_config.py::repository_for`):
    - `local` (mặc định, môi trường dev): file JSON cục bộ `users.json` trong
      thư mục dữ liệu (`get_data_root()`, mặc định `data_warehouse/`).
    - `postgres` (bản production, `deploy/production/docker-compose.prod.yml`):
      bảng `users` trong PostgreSQL qua `UserRepository`, có Row Level Security
      theo `organization_id`.
Luồng kiến trúc giữ nguyên ở cả hai chế độ
(authenticate -> identify user -> identify role -> create session).

GIỚI HẠN ĐÃ BIẾT (ghi rõ để không ai nhầm là bảo mật cấp production thật):
    - Tài khoản Sinh viên có thể được HỆ THỐNG TỰ CẤP ("auto-provision") ngay
      lần đăng nhập đầu tiên nếu username khớp định dạng mã số sinh viên trong
      dữ liệu giả lập (SVxxx) VÀ mật khẩu đúng quy ước demo (`<mã số>123`) —
      mô phỏng việc LMS thật sẽ tự cấp tài khoản cho từng sinh viên, tránh phải
      biết trước danh sách toàn bộ sinh viên khi seed. Khi nối LMS thật, thay
      hoàn toàn bước này bằng xác thực qua token/session LMS (xem `authenticate`).
    - Đây KHÔNG phải SSO/OAuth thật, chỉ là auth nội bộ tối thiểu cho phạm vi
      đồ án — nhưng vẫn chặn đúng lỗ hổng "ai cũng chọn được ID người khác".
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from typing import Optional, TypedDict

import streamlit as st

from dss.core.data_root import get_data_root
from dss.core.logging_config import get_logger
from dss.core.persistence_config import repository_for

_logger = get_logger(__name__)
# C1.1: 600.000 vòng cho PBKDF2-HMAC-SHA256 (khuyến nghị OWASP hiện hành) — băm
# mới lưu dạng tự mô tả "pbkdf2_sha256$<vòng>$<hex>"; băm cũ (hex trần, 200.000
# vòng) vẫn xác minh được và được NÂNG CẤP tự động ở lần đăng nhập đúng kế tiếp.
_PBKDF2_ITERATIONS = 600_000
_LEGACY_PBKDF2_ITERATIONS = 200_000
_HASH_SCHEME = "pbkdf2_sha256"


def _users_path() -> Path:
    """PERF-002: tính lại mỗi lần gọi, không cache mức module (xem dss/core/data_root.py)."""
    return get_data_root() / "users.json"


# Định dạng student_id do generate_data() sinh ra: f"SV{i:03d}". Phần {i:03d} ĐỆM TỐI THIỂU 3 chữ
# số chứ không giới hạn ở 3: bộ dữ liệu demo của app là 20.000 sinh viên (dss/main.py), nên mã chạy
# từ SV001 tới SV20000 — tức 3 đến 5 chữ số. Mẫu cũ `^SV\d{3}$` chỉ khớp đúng 999 mã đầu, khiến
# 19.001 sinh viên trong chính bộ dữ liệu demo không đăng nhập được. Nới tới 6 chữ số để còn chỗ
# cho bộ dữ liệu lớn hơn mà vẫn không nhận những chuỗi dài bất thường.
_STUDENT_ID_PATTERN = re.compile(r"^SV\d{3,6}$", re.IGNORECASE)


class UserRecord(TypedDict, total=False):
    username: str
    role: str
    student_id: Optional[str]
    hash: str
    salt: str
    auto_provisioned: bool


# ---------------------------------------------------------------------------
# Băm mật khẩu — không hard-code, không log mật khẩu ở đâu cả.
# ---------------------------------------------------------------------------
def _hash_password(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{_HASH_SCHEME}${_PBKDF2_ITERATIONS}${digest.hex()}", salt.hex()


def _parse_hash(stored: str) -> tuple[int, str]:
    """(số vòng, hex) cho cả định dạng mới lẫn băm hex trần cũ."""
    if stored.startswith(_HASH_SCHEME + "$"):
        _, iterations, hex_digest = stored.split("$", 2)
        return int(iterations), hex_digest
    return _LEGACY_PBKDF2_ITERATIONS, stored


def _verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    iterations, expected = _parse_hash(hash_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations)
    return hmac.compare_digest(digest.hex(), expected)


def password_needs_rehash(stored_hash: str) -> bool:
    iterations, _ = _parse_hash(stored_hash)
    return not stored_hash.startswith(_HASH_SCHEME + "$") or iterations < _PBKDF2_ITERATIONS


# ---------------------------------------------------------------------------
# Kho tài khoản (JSON cục bộ) — key hóa theo username viết thường.
# ---------------------------------------------------------------------------
def _seed_default_accounts_into(users: dict) -> bool:
    """Tạo sẵn 2 tài khoản demo (Giảng viên, Admin) trong môi trường phát triển / demo.

    MỤC 27: Tuyệt đối KHÔNG tự động seed các tài khoản demo này nếu đang ở chế độ REAL_LMS.
    """
    if repository_for("IDENTITY") is not None:
        return False
    from dss.core.runtime_mode import demo_accounts_seed_allowed

    if not demo_accounts_seed_allowed():
        _logger.info("Chế độ REAL_LMS / PRODUCTION: Bỏ qua việc tự động tạo tài khoản demo mặc định.")
        return False

    seed_defaults = {
        "admin": ("admin123", "Admin", None),
        "giangvien": ("gv123", "Giảng viên / CVHT", None),
    }
    changed = False
    for username, (password, role, student_id) in seed_defaults.items():
        if username not in users:
            hash_hex, salt_hex = _hash_password(password)
            users[username] = {
                "username": username,
                "role": role,
                "student_id": student_id,
                "hash": hash_hex,
                "salt": salt_hex,
                "auto_provisioned": False,
            }
            changed = True
    if changed:
        _save_users(users)
    return changed


def _load_users() -> dict[str, UserRecord]:
    repository = repository_for("IDENTITY")
    if repository is not None:
        users: dict[str, UserRecord] = {}
        offset = 0
        while True:
            batch = repository.list_users(limit=1000, offset=offset)
            users.update(batch)
            if len(batch) < 1000:
                break
            offset += 1000
        return users
    users_path = _users_path()
    if not users_path.exists():
        users: dict[str, UserRecord] = {}
        _seed_default_accounts_into(users)
        return users
    try:
        with open(users_path, encoding="utf-8") as f:
            users = json.load(f)
    except Exception as exc:
        # Trước đây trả {}: nơi gọi tạo lại 2 tài khoản mặc định rồi GHI ĐÈ tệp hỏng, mất mọi tài khoản khác.
        _logger.error(
            "users.json không đọc được (%s); từ chối ghi đè. Khôi phục tệp từ bản sao lưu.", type(exc).__name__
        )
        raise AccountStoreCorrupted(
            "Kho tài khoản bị hỏng. Liên hệ quản trị viên để khôi phục từ bản sao lưu."
        ) from exc
    if not isinstance(users, dict):
        raise AccountStoreCorrupted("Kho tài khoản không đúng định dạng. Liên hệ quản trị viên.")
    if not users:
        _seed_default_accounts_into(users)
    return users


def count_users_by_role() -> dict[str, int]:
    """Đếm số tài khoản thật theo vai trò — dùng cho KPI Admin (Báo cáo hệ
    thống/Dashboard), KHÔNG hard-code số liệu. Đọc trực tiếp `_load_users()`
    (nguồn sự thật duy nhất về tài khoản), chỉ đếm — không sửa/ghi gì."""
    repository = repository_for("IDENTITY")
    if repository is not None:
        return repository.count_users_by_role()
    users = _load_users()
    counts: dict[str, int] = {}
    for record in users.values():
        role = record.get("role", "unknown")
        counts[role] = counts.get(role, 0) + 1
    return counts


def _save_users(users: dict[str, UserRecord]) -> None:
    """Lưu danh sách tài khoản bằng phương thức atomic write để chống hỏng file."""
    if repository_for("IDENTITY") is not None:
        raise RuntimeError("PostgreSQL accounts must be changed through the repository")
    users_path = _users_path()
    users_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = users_path.with_suffix(f".tmp_{os.urandom(6).hex()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, users_path)
    except Exception as e:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        _logger.error("Ghi atomic file users thất bại: %s", e, exc_info=True)
        raise


# Quản lý khóa tài khoản do brute-force đăng nhập (Mục 27). C1.1: trạng thái lưu
# BỀN VỮNG (tệp + khoá tiến trình, dss/security/login_throttle.py) thay vì bộ nhớ
# tiến trình — không mất khi khởi động lại, dùng chung giữa các worker cùng máy.
from dss.security import login_throttle as _throttle

_MAX_FAILED_ATTEMPTS = _throttle.MAX_FAILED_ATTEMPTS
_LOCKOUT_DURATION_SECONDS = _throttle.LOCKOUT_SECONDS


class AuthenticationError(Exception):
    """Lỗi xác thực chung."""


class AccountStoreCorrupted(AuthenticationError):
    """users.json không đọc được: dừng lại thay vì ghi đè và làm mất tài khoản."""


class AccountLockedError(AuthenticationError):
    """Tài khoản tạm thời bị khóa do thử sai mật khẩu nhiều lần."""


def _client_id() -> Optional[str]:
    """Máy khách của phiên đăng nhập, để khoá theo (tài khoản, máy khách) thay vì cả tài khoản.

    Mặc định lấy IP của kết nối WebSocket (``st.context.ip_address``) — không giả mạo được. Sau reverse proxy thì
    đó là IP của proxy (mọi người chung một giá trị → hành vi như khoá theo tài khoản, không kém an toàn hơn trước);
    khi proxy GHI ĐÈ một header IP (Caddy/Nginx), đặt ``EDUDSS_CLIENT_IP_HEADER`` (VD ``X-Real-IP``) để dùng nó.
    Không đọc được thì trả None (khoá cả tài khoản như cũ)."""
    try:
        import streamlit as st

        ctx = st.context
        header = os.environ.get("EDUDSS_CLIENT_IP_HEADER", "").strip()
        value = None
        if header:
            raw = (ctx.headers or {}).get(header) or ""
            value = raw.split(",")[-1].strip() or None  # giá trị proxy tin cậy thêm cuối cùng
        if not value:
            value = getattr(ctx, "ip_address", None)
        value = (str(value).strip()[:64]) if value else None
        return value or None
    except Exception:  # noqa: BLE001 - ngoài phiên Streamlit (test, script)
        return None


def is_account_locked(username: str, client: Optional[str] = None) -> tuple[bool, int]:
    """Kiểm tra tài khoản có đang bị khóa (với máy khách này) hay không. Trả về (is_locked, remaining_seconds)."""
    return _throttle.is_locked(username, client)


def _record_failed_attempt(username: str, client: Optional[str] = None) -> None:
    key = username.strip().lower()
    if _throttle.record_failure(key, client):
        _logger.warning(
            "Bảo mật Auth: Tài khoản %s đã bị tạm khóa %d giây do nhập sai quá %d lần%s.",
            key,
            _LOCKOUT_DURATION_SECONDS,
            _MAX_FAILED_ATTEMPTS,
            " (từ một máy khách)" if client else "",
        )


def _reset_failed_attempts(username: str, client: Optional[str] = None) -> None:
    _throttle.reset(username, client)


def _seed_default_accounts_if_missing() -> None:
    """Tạo sẵn 2 tài khoản demo (Giảng viên, Admin) trong môi trường phát triển / demo.

    MỤC 27: Tuyệt đối KHÔNG tự động seed các tài khoản demo này nếu đang ở chế độ REAL_LMS.
    """
    if repository_for("IDENTITY") is not None:
        return
    from dss.core.runtime_mode import demo_accounts_seed_allowed

    if not demo_accounts_seed_allowed():
        _logger.info("Chế độ REAL_LMS / PRODUCTION: Bỏ qua việc tự động tạo tài khoản demo mặc định.")
        return

    with _local_accounts_lock:
        _seed_defaults_locked()


def _seed_defaults_locked() -> None:
    users = _load_users()
    changed = False
    seed_defaults = {
        "admin": ("admin123", "Admin", None),
        "giangvien": ("gv123", "Giảng viên / CVHT", None),
    }
    for username, (password, role, student_id) in seed_defaults.items():
        if username not in users:
            hash_hex, salt_hex = _hash_password(password)
            users[username] = {
                "username": username,
                "role": role,
                "student_id": student_id,
                "hash": hash_hex,
                "salt": salt_hex,
                "auto_provisioned": False,
            }
            changed = True
    if changed:
        _save_users(users)


def authenticate(username: str, password: str) -> Optional[UserRecord]:
    """Xác thực username/password kèm kiểm tra rate limiting và khóa tài khoản."""
    if not username or not password:
        return None
    key = username.strip().lower()
    client = _client_id()

    # Kiểm tra khóa tài khoản (theo máy khách nếu biết, xem login_throttle)
    locked, rem = is_account_locked(key, client)
    if locked:
        raise AccountLockedError(
            f"Tài khoản '{key}' tạm thời bị khóa do nhập sai nhiều lần. Vui lòng thử lại sau {rem} giây."
        )

    repository = repository_for("IDENTITY")
    users = {key: repository.get_user_by_username(key)} if repository is not None else _load_users()

    if key in users and users[key] is not None:
        record = users[key]
        if record.get("is_active", True) is False:
            _logger.warning("Đăng nhập bị chặn cho tài khoản vô hiệu hóa: username=%s", key)
            return None
        candidate = password
        if record.get("auto_provisioned") and password.strip().lower() == f"{key}123":
            # Mật khẩu lần đầu "<mã>123" không phân biệt hoa/thường (đã hứa ở màn đăng nhập). Băm mới lưu dạng
            # chữ thường; băm cũ có thể là dạng hoa đã gõ lúc tạo, nên thử cả hai.
            candidate = f"{key}123"
        ok = _verify_password(candidate, record["hash"], record["salt"]) or (
            candidate != password and _verify_password(password, record["hash"], record["salt"])
        )
        if ok:
            _reset_failed_attempts(key, client)
            if password_needs_rehash(record["hash"]):
                # Nâng cấp băm cũ ngay khi có mật khẩu đúng trong tay (không lưu/ghi log mật khẩu).
                try:
                    if repository is not None:
                        repository.reset_password(key, password)
                    else:
                        with _local_accounts_lock:  # đọc lại dưới khoá: không ghi đè thay đổi của Admin
                            fresh = _load_users()
                            if key in fresh and fresh[key].get("hash") == record["hash"]:
                                fresh[key]["hash"], fresh[key]["salt"] = _hash_password(candidate)
                                _save_users(fresh)
                                record = fresh[key]
                except Exception:
                    _logger.warning("Không nâng cấp được băm mật khẩu cho tài khoản (giữ băm cũ, vẫn đăng nhập).")
            if repository is not None:
                repository.touch_last_login(key)
            _logger.info("Đăng nhập thành công: username=%s role=%s", key, record.get("role"))
            return record
        _record_failed_attempt(key, client)
        _logger.warning("Đăng nhập thất bại (sai mật khẩu): username=%s", key)
        return None

    # Auto-provision tài khoản Sinh viên (<mã>/<mã>123) — CHỈ ngoài production
    # (C1.1: trước đây chỉ chặn khi EDUDSS_MODE=REAL_LMS, bỏ sót EDUDSS_ENV=production).
    from dss.core.runtime_mode import student_autoprovision_allowed

    # Quy ước mật khẩu lần đầu là "<mã sinh viên>123". `key` đã được hạ chữ thường ở trên, nên so
    # sánh nguyên văn sẽ bắt sinh viên gõ mã thường ("sv001123") dù màn đăng nhập hiển thị mã hoa
    # ("SV001"). Hạ chữ thường cả hai vế để quy ước đúng như nó được viết ra cho người dùng.
    if student_autoprovision_allowed() and _STUDENT_ID_PATTERN.match(key) and password.strip().lower() == f"{key}123":
        if repository is not None:
            record = repository.create_user(
                username=key,
                password=password,
                role_name="Sinh viên",
                student_id=key.upper(),
                auto_provisioned=True,
            )
        else:
            with _local_accounts_lock:
                fresh = _load_users()
                if key in fresh:
                    # Vừa được tạo ở phiên/tiến trình khác (hoặc Admin vừa tạo): không ghi đè, xác thực như thường.
                    existing = fresh[key]
                    if existing.get("is_active", True) is False or not _verify_password(
                        f"{key}123", existing["hash"], existing["salt"]
                    ):
                        _record_failed_attempt(key, client)
                        return None
                    _reset_failed_attempts(key, client)
                    return existing
                hash_hex, salt_hex = _hash_password(f"{key}123")
                record = {
                    "username": key,
                    "role": "Sinh viên",
                    "student_id": key.upper(),
                    "hash": hash_hex,
                    "salt": salt_hex,
                    "auto_provisioned": True,
                }
                fresh[key] = record
                _save_users(fresh)
        _reset_failed_attempts(key, client)
        _logger.info("Tự động tạo + đăng nhập tài khoản Sinh viên mới (Demo): username=%s", key)
        return record

    # Tốn đúng một lần PBKDF2 như khi tài khoản tồn tại: thời gian phản hồi không tiết lộ tên đăng nhập nào có thật.
    _verify_password(password, *_dummy_credentials())
    _record_failed_attempt(key, client)
    _logger.warning("Đăng nhập thất bại (tài khoản không tồn tại): username=%s", key)
    return None


_DUMMY: list = []


def _dummy_credentials() -> tuple[str, str]:
    if not _DUMMY:
        _DUMMY.extend(_hash_password(_secrets.token_hex(16)))
    return _DUMMY[0], _DUMMY[1]


def require_role(*allowed_roles: str):
    """Decorator chặn NGAY TẦNG SERVICE (không chỉ ẩn nút trên UI) — dùng cho
    các hàm nghiệp vụ nhạy cảm (train model, đổi model production...). Ví dụ:

        @require_role("Admin")
        def train_new_model(config): ...
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            role = st.session_state.get("_auth_role")
            if role not in allowed_roles:
                raise PermissionError(
                    f"Vai trò '{role}' không có quyền gọi {func.__name__} (yêu cầu: {', '.join(allowed_roles)})"
                )
            return func(*args, **kwargs)

        wrapper.__name__ = getattr(func, "__name__", "wrapped")
        return wrapper

    return decorator


def current_user() -> Optional[UserRecord]:
    """Danh tính đã xác thực của phiên hiện tại, hoặc None nếu chưa đăng nhập."""
    if not st.session_state.get("_authenticated"):
        return None
    return {
        "username": st.session_state.get("_auth_username"),
        "role": st.session_state.get("_auth_role"),
        "student_id": st.session_state.get("_auth_student_id"),
    }


_KEEP_ON_LOGOUT = frozenset({"dss_theme"})


def logout() -> None:
    was_google = st.session_state.get("_auth_method") == "google"
    for k in (
        "_authenticated",
        "_auth_username",
        "_auth_role",
        "_auth_student_id",
        "_auth_method",
        "_workspace_ready_for",
        "_app_started",
        "_auto_bootstrap_done_for",
    ):
        st.session_state.pop(k, None)
    # Xoá TOÀN BỘ dữ liệu phiên (dataset đã tải, kết quả huấn luyện, lịch sử chat AI, lựa chọn sinh viên...) —
    # người đăng nhập kế tiếp trên cùng trình duyệt không được thừa hưởng gì của người trước. Chỉ giữ giao diện sáng/tối.
    for k in list(st.session_state.keys()):
        if k not in _KEEP_ON_LOGOUT:
            st.session_state.pop(k, None)
    # Xoá riêng các widget nhập API key/secrets (không theo prefix "llm_" ở
    # trên) — phòng trường hợp phiên trình duyệt (WebSocket session) được TÁI
    # SỬ DỤNG cho lượt đăng nhập kế tiếp với vai trò thấp hơn (vd. Admin đăng
    # xuất, Giảng viên đăng nhập cùng tab): không được để lại giá trị key cũ
    # trong session_state dù widget đó không còn được vẽ ra cho vai trò mới.
    for k in (
        "gemini_key_input",
        "groq_key_input",
        "openai_key_input",
        "hf_token_input",
        "ollama_url_input",
    ):
        st.session_state.pop(k, None)
    if was_google:
        # Xoá cả cookie OIDC của Streamlit, nếu không lần tải trang sau sẽ tự đăng nhập lại.
        from dss.services import google_signin

        google_signin.logout()


# ---------------------------------------------------------------------------
# Google Sign-In (OIDC native của Streamlit: st.login / st.user) + quản trị tài khoản
# ---------------------------------------------------------------------------
# Google chỉ xác minh "người này sở hữu email X". Quyền trong EduDSS vẫn do tài khoản
# quyết định: email phải được Admin GẮN vào một tài khoản có sẵn. Ngoại lệ duy nhất là bản
# demo công khai trên dữ liệu mô phỏng (runtime_mode.google_self_signup_allowed): email lạ
# được cấp 1 tài khoản Sinh viên gắn với 1 sinh viên MÔ PHỎNG chưa ai nhận — không bao giờ
# Giảng viên/Admin, không bao giờ trong production.
import secrets as _secrets
import threading as _threading

ASSIGNABLE_ROLES = ("Sinh viên", "Giảng viên / CVHT", "Admin")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_MIN_ADMIN_SET_PASSWORD = 10


class _AccountsLock:
    """Khoá mọi lần đọc-sửa-ghi users.json: khoá luồng (RLock, cho phép lồng nhau) và khoá tệp của hệ điều hành
    (nhiều tiến trình Streamlit cùng dùng một tệp). Trước đây authenticate() và việc tạo tài khoản mặc định ghi
    không khoá, nên có thể ghi đè thay đổi (khoá tài khoản, đặt lại mật khẩu) vừa được Admin lưu."""

    def __init__(self) -> None:
        self._thread = _threading.RLock()
        self._depth = 0
        self._file = None

    def __enter__(self):
        self._thread.acquire()
        try:
            if self._depth == 0 and repository_for("IDENTITY") is None:
                from dss.security.login_throttle import _os_lock

                path = _users_path()
                path.parent.mkdir(parents=True, exist_ok=True)
                self._file = open(path.with_suffix(".lock"), "a+")
                _os_lock(self._file)
        except BaseException:
            self._thread.release()
            raise
        self._depth += 1
        return self

    def __exit__(self, *exc) -> bool:
        self._depth -= 1
        try:
            if self._depth == 0 and self._file is not None:
                from dss.security.login_throttle import _os_unlock

                try:
                    _os_unlock(self._file)
                finally:
                    self._file.close()
                    self._file = None
        finally:
            self._thread.release()
        return False


_local_accounts_lock = _AccountsLock()


class GoogleSignInRejected(AuthenticationError):
    """Google đã xác thực email nhưng EduDSS không cho đăng nhập (lý do an toàn để hiển thị)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def normalize_email(email) -> str:
    value = str(email or "").strip().lower()
    return value if _EMAIL_RE.fullmatch(value) and len(value) <= 255 else ""


def find_user_by_email(email: str) -> Optional[UserRecord]:
    """Tài khoản DUY NHẤT có email này (không khớp hoặc trùng nhiều tài khoản -> None)."""
    key = normalize_email(email)
    if not key:
        return None
    repository = repository_for("IDENTITY")
    if repository is not None:
        return repository.get_user_by_email(key)
    matches = [r for r in _load_users().values() if normalize_email(r.get("email")) == key]
    return matches[0] if len(matches) == 1 else None


def _claims_email_verified(claims: dict) -> bool:
    value = claims.get("email_verified")
    return value is True or str(value).strip().lower() == "true"


def _demo_student_pool_size() -> int:
    try:
        return max(1, min(int(os.environ.get("EDUDSS_DEMO_STUDENT_POOL", "1000")), 99999))
    except ValueError:
        return 1000


def _google_username(email: str) -> str:
    return "g_" + hashlib.sha256(email.encode("utf-8")).hexdigest()[:12]


def _create_google_student(email: str) -> UserRecord:
    """Bản demo công khai: cấp 1 tài khoản Sinh viên gắn với 1 sinh viên mô phỏng chưa ai nhận.

    Mật khẩu là chuỗi ngẫu nhiên không ai biết — tài khoản chỉ đăng nhập được bằng Google."""
    username = _google_username(email)
    with _local_accounts_lock:
        users = _load_users()
        claimed = {str(r.get("student_id") or "").upper() for r in users.values()}
        pool = [f"SV{i:03d}" for i in range(1, _demo_student_pool_size() + 1) if f"SV{i:03d}" not in claimed]
        if not pool:
            raise GoogleSignInRejected(
                "pool_exhausted", "Bản demo đã hết sinh viên mô phỏng để cấp. Vui lòng liên hệ quản trị viên."
            )
        student_id = _secrets.choice(pool)
        password = _secrets.token_urlsafe(32)
        repository = repository_for("IDENTITY")
        if repository is not None:
            repository.create_user(
                username=username,
                password=password,
                role_name="Sinh viên",
                student_id=student_id,
                auto_provisioned=True,
            )
            record = repository.update_user(username, email=email)
        else:
            hash_hex, salt_hex = _hash_password(password)
            record = {
                "username": username,
                "role": "Sinh viên",
                "student_id": student_id,
                "hash": hash_hex,
                "salt": salt_hex,
                "auto_provisioned": True,
                "email": email,
                "auth_provider": "google",
            }
            users[username] = record
            _save_users(users)
    _logger.info("Google: cấp tài khoản Sinh viên demo username=%s student_id=%s", username, student_id)
    return record


def resolve_google_user(claims: dict) -> UserRecord:
    """Ánh xạ danh tính Google (st.user) sang tài khoản EduDSS, hoặc raise GoogleSignInRejected."""
    from dss.core.runtime_mode import google_self_signup_allowed

    email = normalize_email((claims or {}).get("email"))
    if not email:
        raise GoogleSignInRejected("no_email", "Tài khoản Google không cung cấp email hợp lệ.")
    if not _claims_email_verified(claims):
        raise GoogleSignInRejected("email_unverified", "Email Google chưa được xác minh.")
    record = find_user_by_email(email)
    if record is not None:
        if record.get("is_active", True) is False:
            raise GoogleSignInRejected("disabled", "Tài khoản gắn với email này đang bị khoá. Liên hệ quản trị viên.")
        repository = repository_for("IDENTITY")
        if repository is not None:
            repository.touch_last_login(record["username"])
        _logger.info("Đăng nhập Google thành công: username=%s role=%s", record["username"], record.get("role"))
        return record
    if google_self_signup_allowed():
        return _create_google_student(email)
    raise GoogleSignInRejected(
        "not_linked",
        "Email này chưa được gắn với tài khoản EduDSS nào. Quản trị viên cần gắn email vào tài khoản "
        "của bạn (trang Người dùng) trước khi bạn đăng nhập bằng Google.",
    )


SESSION_RECHECK_SECONDS = 30


def _session_still_valid(identity: UserRecord) -> bool:
    """Kiểm lại tài khoản sau mỗi SESSION_RECHECK_SECONDS giây: Admin khoá tài khoản hoặc hạ quyền thì phiên đang mở
    kết thúc ở lần tương tác kế tiếp, không chờ người dùng tự đăng xuất."""
    import time as _time

    now = _time.time()
    if now - float(st.session_state.get("_auth_checked_at", 0) or 0) < SESSION_RECHECK_SECONDS:
        return True
    username = identity.get("username")
    try:
        repository = repository_for("IDENTITY")
        record = repository.get_user_by_username(username) if repository is not None else _load_users().get(username)
    except Exception:  # noqa: BLE001 - không đọc được kho tài khoản: đóng phiên (fail closed)
        _logger.warning("Không kiểm lại được tài khoản của phiên; đăng xuất để an toàn.")
        return False
    if (
        not record
        or record.get("is_active", True) is False
        or record.get("role") != identity.get("role")
        or (record.get("student_id") or None) != (identity.get("student_id") or None)
    ):
        _logger.info("Phiên bị đóng vì tài khoản đã đổi: username=%s", username)
        return False
    st.session_state["_auth_checked_at"] = now
    return True


def establish_session(record: UserRecord, method: str = "password") -> None:
    import time as _time

    st.session_state["_auth_checked_at"] = _time.time()
    st.session_state["_authenticated"] = True
    st.session_state["_auth_username"] = record["username"]
    st.session_state["_auth_role"] = record["role"]
    st.session_state["_auth_student_id"] = record.get("student_id")
    st.session_state["_auth_method"] = method


def _validate_new_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < _MIN_ADMIN_SET_PASSWORD:
        raise ValueError(f"Mật khẩu phải có ít nhất {_MIN_ADMIN_SET_PASSWORD} ký tự.")


def _check_email_free(email: str, username: str) -> None:
    other = find_user_by_email(email)
    if other is not None and other.get("username") != username:
        raise ValueError("Email này đã gắn với một tài khoản khác.")


def _audit_local(action: str, username: str, details: dict) -> None:
    actor = st.session_state.get("_auth_username") or "system"
    _logger.info(
        "AUDIT %s target=%s actor=%s details=%s",
        action,
        username,
        actor,
        {k: v for k, v in details.items() if k not in {"hash", "salt", "password"}},
    )


def _org_id(repository) -> int:
    return int(repository.organization_id)


@require_role("Admin")
def admin_create_account(
    username: str, password: str, role: str, *, email: Optional[str] = None, student_id: Optional[str] = None
) -> UserRecord:
    """Admin tạo tài khoản (Giảng viên/Admin/Sinh viên). Ghi nhật ký kiểm toán."""
    key = (username or "").strip().lower()
    if not _USERNAME_RE.fullmatch(key):
        raise ValueError("Tên đăng nhập 3-64 ký tự: chữ thường, số, dấu chấm, gạch dưới, gạch ngang.")
    if role not in ASSIGNABLE_ROLES:
        raise ValueError("Vai trò không hợp lệ.")
    _validate_new_password(password)
    mail = normalize_email(email) if email else ""
    if email and not mail:
        raise ValueError("Email không hợp lệ.")
    sid = (student_id or "").strip().upper() or None
    if role == "Sinh viên" and not sid:
        raise ValueError("Tài khoản Sinh viên cần mã sinh viên.")
    if mail:
        _check_email_free(mail, key)
    repository = repository_for("IDENTITY")
    if repository is not None:
        from dss.services import user_management_service

        if repository.get_user_by_username(key) is not None:
            raise ValueError("Tên đăng nhập đã tồn tại.")
        record = user_management_service.create_user(_org_id(repository), key, password, role, student_id=sid)
        if mail:
            record = user_management_service.update_user(_org_id(repository), key, email=mail)
        return record
    with _local_accounts_lock:
        users = _load_users()
        if key in users:
            raise ValueError("Tên đăng nhập đã tồn tại.")
        hash_hex, salt_hex = _hash_password(password)
        users[key] = {
            "username": key,
            "role": role,
            "student_id": sid,
            "hash": hash_hex,
            "salt": salt_hex,
            "auto_provisioned": False,
            "email": mail or None,
            "is_active": True,
        }
        _save_users(users)
    _audit_local("user.created", key, {"role": role, "email": mail, "student_id": sid})
    return users[key]


@require_role("Admin")
def admin_update_account(
    username: str, *, email: Optional[str] = None, active: Optional[bool] = None, role: Optional[str] = None
) -> UserRecord:
    """Gắn/đổi email (để đăng nhập Google), khoá/mở khoá, đổi vai trò."""
    key = (username or "").strip().lower()
    if key == (st.session_state.get("_auth_username") or "") and (active is False or (role and role != "Admin")):
        raise ValueError("Không thể tự khoá hoặc tự hạ quyền tài khoản đang đăng nhập.")
    mail = None
    if email is not None:
        mail = normalize_email(email) if email.strip() else ""
        if email.strip() and not mail:
            raise ValueError("Email không hợp lệ.")
        if mail:
            _check_email_free(mail, key)
    if role is not None and role not in ASSIGNABLE_ROLES:
        raise ValueError("Vai trò không hợp lệ.")
    repository = repository_for("IDENTITY")
    if repository is not None:
        from dss.services import user_management_service

        org = _org_id(repository)
        record = repository.get_user_by_username(key)
        if record is None:
            raise ValueError("Không tìm thấy tài khoản.")
        if mail is not None:
            record = user_management_service.update_user(org, key, email=mail)
        if active is not None:
            record = user_management_service.set_user_active(org, key, active)
        if role is not None and role != record.get("role"):
            record = user_management_service.change_role(org, key, role)
        return record
    with _local_accounts_lock:
        users = _load_users()
        if key not in users:
            raise ValueError("Không tìm thấy tài khoản.")
        record = users[key]
        if mail is not None:
            record["email"] = mail or None
        if active is not None:
            record["is_active"] = bool(active)
        if role is not None:
            record["role"] = role
        _save_users(users)
    _audit_local("user.updated", key, {"email": mail, "active": active, "role": role})
    return record


@require_role("Admin")
def admin_reset_password(username: str, new_password: str) -> None:
    key = (username or "").strip().lower()
    _validate_new_password(new_password)
    repository = repository_for("IDENTITY")
    if repository is not None:
        from dss.services import user_management_service

        user_management_service.reset_password(_org_id(repository), key, new_password)
        return
    with _local_accounts_lock:
        users = _load_users()
        if key not in users:
            raise ValueError("Không tìm thấy tài khoản.")
        users[key]["hash"], users[key]["salt"] = _hash_password(new_password)
        _save_users(users)
    _reset_failed_attempts(key)
    _audit_local("user.password_reset", key, {})


def bootstrap_admin_from_env() -> bool:
    """Tạo tài khoản Admin đầu tiên từ EDUDSS_BOOTSTRAP_ADMIN_USER/PASSWORD[/EMAIL] (một lần).

    Dùng cho bản triển khai không có tài khoản demo (EDUDSS_PUBLIC_DEMO). Không bao giờ ghi đè
    tài khoản đã có; mật khẩu tối thiểu 12 ký tự."""
    username = (os.environ.get("EDUDSS_BOOTSTRAP_ADMIN_USER") or "").strip().lower()
    password = os.environ.get("EDUDSS_BOOTSTRAP_ADMIN_PASSWORD") or ""
    if not username or not password:
        return False
    if len(password) < 12 or not _USERNAME_RE.fullmatch(username):
        _logger.warning("EDUDSS_BOOTSTRAP_ADMIN_*: bỏ qua (tên không hợp lệ hoặc mật khẩu < 12 ký tự).")
        return False
    email = normalize_email(os.environ.get("EDUDSS_BOOTSTRAP_ADMIN_EMAIL")) or None
    repository = repository_for("IDENTITY")
    if repository is not None:
        if repository.get_user_by_username(username) is not None:
            return False
        repository.create_user(username=username, password=password, role_name="Admin")
        if email:
            repository.update_user(username, email=email)
    else:
        with _local_accounts_lock:
            users = _load_users()
            if username in users:
                return False
            hash_hex, salt_hex = _hash_password(password)
            users[username] = {
                "username": username,
                "role": "Admin",
                "student_id": None,
                "hash": hash_hex,
                "salt": salt_hex,
                "auto_provisioned": False,
                "email": email,
                "is_active": True,
            }
            _save_users(users)
    _logger.info("Đã tạo tài khoản Admin ban đầu từ biến môi trường: username=%s", username)
    return True


def demo_credentials_html() -> str:
    """HTML của hộp tài khoản demo — chỉ được gọi khi runtime_mode.demo_credentials_visible()."""
    return (
        "<div class='dss-login-demo-row'><span>Giảng viên</span><code>giangvien / gv123</code></div>"
        "<div class='dss-login-demo-row'><span>Admin</span><code>admin / admin123</code></div>"
        "<div class='dss-login-demo-row'><span>Sinh viên</span><code>SV001..SV999 / &lt;mã số&gt;123</code></div>"
    )


def render_login_gate() -> Optional[UserRecord]:
    """Cổng đăng nhập DUY NHẤT cho cả 3 vai trò (đúng yêu cầu "một cổng chung,
    không phải 3 login độc lập"). Nếu đã đăng nhập, trả về danh tính ngay
    (không vẽ lại form). Nếu chưa, vẽ form và trả về None — nơi gọi phải
    `st.stop()` ngay sau khi nhận None để chặn phần còn lại của trang."""
    existing = current_user()
    if existing is not None:
        if _session_still_valid(existing):
            return existing
        logout()
        st.warning("Phiên đăng nhập đã kết thúc vì tài khoản bị khoá hoặc đổi quyền. Vui lòng đăng nhập lại.")

    try:
        bootstrap_admin_from_env()
    except Exception:
        _logger.warning("Không tạo được tài khoản Admin ban đầu từ biến môi trường.", exc_info=True)
    _seed_default_accounts_if_missing()

    # Vừa quay lại từ Google (st.user đã đăng nhập): ánh xạ sang tài khoản EduDSS rồi vào thẳng.
    from dss.services import google_signin

    google_record = google_signin.pending_identity()
    if google_record is not None:
        establish_session(google_record, "google")
        st.rerun()

    # C1.3 — trang đăng nhập 2 cột: TRÁI = giới thiệu ngắn gọn sản phẩm (chữ
    # tĩnh, KHÔNG có số liệu minh hoạ giả như "GPA dự đoán 6.8" trước đây);
    # PHẢI = thẻ đăng nhập thật (widget Streamlit). Marker `.dss-login-marker`
    # cho CSS ẩn sidebar và căn bố cục riêng màn hình này.
    col_intro, col_card = st.columns([1.3, 1.05], gap="large")

    with col_intro:
        # Marker riêng 1 phần tử (CSS ẩn phần tử chứa marker).
        st.markdown("<div class='dss-marker dss-login-marker'></div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='dss-login-intro'>"
            "<div class='dss-login-brand'><span class='dss-login-logo'>ED</span>"
            "<div><div class='dss-login-brand-name'>EduDSS</div>"
            "<div class='dss-login-brand-tag'>Hệ thống hỗ trợ quyết định học tập</div></div></div>"
            "<div class='dss-login-product-panel'>"
            "<div class='dss-login-badges'>"
            "<span class='dss-login-badge blue'>AI</span><span class='dss-login-badge yellow'>ML</span><span class='dss-login-badge green'>Giáo dục</span>"
            "</div>"
            "<div class='dss-login-illustration'>"
            "<div class='dss-edu-orb blue'></div>"
            "<div class='dss-edu-orb yellow'></div>"
            "<div class='dss-edu-book'>"
            "<span></span><span></span><span></span>"
            "</div>"
            "</div>"
            "<h1 class='dss-login-headline'>Hỗ trợ quyết định học tập bằng AI</h1>"
            "<p class='dss-login-lead'>Dự đoán kết quả học tập, cảnh báo sớm sinh viên cần hỗ trợ và tư vấn học tập có dẫn nguồn — cho Sinh viên, Giảng viên và Quản trị viên.</p>"
            "<div class='dss-login-points'>"
            "<div class='dss-login-point-item'><span class='dss-login-point-mark'>1</span><div><strong>Phân tích tiến độ học tập</strong><small>Nhận diện sinh viên có nguy cơ học tập và gợi ý can thiệp sớm.</small></div></div>"
            "<div class='dss-login-point-item'><span class='dss-login-point-mark'>2</span><div><strong>Hỗ trợ giảng viên</strong><small>Nhìn tổng quan lớp học, điểm yếu và tương tác theo từng nhóm.</small></div></div>"
            "<div class='dss-login-point-item'><span class='dss-login-point-mark'>3</span><div><strong>Trợ lý có dẫn nguồn</strong><small>Trả lời dựa trên dữ liệu, quy chế và tiến độ học tập đã có trong hệ thống.</small></div></div>"
            "</div>"
            "<div class='dss-login-mini-cards'>"
            # Số liệu lấy từ lượt eval 16/11/2026 (evals/README.md:26-27, ngưỡng ở evals/thresholds.json).
            # Đổi mô hình/dữ liệu thì cập nhật cùng README — xem ACCEPTANCE_CRITERIA AC-ML-01/02.
            "<div class='dss-login-mini-card blue'><span class='label'>Accuracy</span><span class='value'>95,7%</span></div>"
            "<div class='dss-login-mini-card yellow'><span class='label'>Macro-F1</span><span class='value'>0,817</span></div>"
            "<div class='dss-login-mini-card green'><span class='label'>R²</span><span class='value'>0,992</span></div>"
            "</div>"
            "<div class='dss-login-footer'>Kết quả đánh giá trên 1.000 sinh viên mô phỏng độc lập (eval 16/11/2026) — "
            "không phải độ chính xác trên sinh viên thật.</div>"
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    with col_card:
        with st.container(key="login_card"):
            st.markdown(
                "<h2 class='dss-login-card-title'>Đăng nhập</h2>"
                "<p class='dss-login-card-subtitle'>Dùng tài khoản do Trường cấp.</p>",
                unsafe_allow_html=True,
            )
            with st.form("login_form", border=False, enter_to_submit=True):
                username = st.text_input(
                    "Tên đăng nhập / Mã số sinh viên",
                    placeholder="Ví dụ: sv001",
                    autocomplete="username",
                )
                password = st.text_input(
                    "Mật khẩu",
                    type="password",
                    placeholder="Nhập mật khẩu",
                    autocomplete="current-password",
                )
                submitted = st.form_submit_button("Đăng nhập", type="primary", width="stretch")
            if submitted:
                if not (username or "").strip() or not password:
                    st.error("Vui lòng nhập tên đăng nhập và mật khẩu.")
                else:
                    try:
                        with st.spinner("Đang xác thực…"):
                            record = authenticate(username, password)
                        from dss.core import metrics

                        if record is None:
                            metrics.record_login("password", "failed")
                            st.error("Sai tên đăng nhập hoặc mật khẩu.")
                        else:
                            metrics.record_login("password", "success")
                            establish_session(record, "password")
                            st.rerun()
                    except AccountLockedError as ale:
                        from dss.core import metrics

                        metrics.record_login("password", "locked")
                        st.error(str(ale))
                    except AuthenticationError as ae:  # VD kho tài khoản hỏng: báo rõ, không traceback
                        st.error(str(ae))

            google_signin.render_button()

            # Không có tự đăng ký: tài khoản do Trường cấp (C1.3 — trình bày đúng
            # luồng cấp tài khoản thay vì dựng 1 form đăng ký không nối vào đâu).
            from dss.core.runtime_mode import google_self_signup_allowed

            if google_signin.configured() and google_self_signup_allowed():
                st.markdown(
                    "<div class='dss-login-help'><strong>Bản demo công khai.</strong> Đăng nhập bằng Google để "
                    "nhận một tài khoản Sinh viên gắn với một sinh viên <em>mô phỏng</em> (không phải dữ liệu "
                    "thật). Tài khoản Giảng viên/Quản trị do Quản trị viên cấp.</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<div class='dss-login-help'><strong>Chưa có tài khoản?</strong> "
                    "EduDSS không hỗ trợ tự đăng ký. Tài khoản sinh viên được cấp từ hệ thống quản lý học tập "
                    "của Trường; tài khoản giảng viên do Quản trị viên cấp. Quên mật khẩu hoặc tài khoản bị khoá, "
                    "vui lòng liên hệ Phòng Đào tạo / Quản trị hệ thống.</div>",
                    unsafe_allow_html=True,
                )

            # C1.1: thông tin tài khoản demo KHÔNG BAO GIỜ hiện trong production; ngoài
            # production chỉ hiện khi bật tường minh EDUDSS_SHOW_DEMO_CREDENTIALS=1.
            from dss.core.runtime_mode import demo_credentials_visible

            if demo_credentials_visible():
                with st.expander("Tài khoản dùng thử (môi trường đánh giá)", expanded=False, icon=None):
                    st.caption(
                        "Chỉ dành cho môi trường phát triển và đánh giá. Khi triển khai thật, tài khoản do "
                        "hệ thống quản lý học tập của Trường cấp."
                    )
                    st.markdown(demo_credentials_html(), unsafe_allow_html=True)
    return None
