"""Authentication + RBAC — Phase 1 của kế hoạch refactor EduDSS.

Thay thế HAI cơ chế "tự nhận danh tính" cũ (đã xác minh là lỗ hổng Critical
trong bản đánh giá kiến trúc):
    1. `render_role_switcher()` (dss/core/roles.py)      — tự chọn vai trò, không mật khẩu.
    2. `_render_student_login_gate()` (dss/main.py cũ)   — tự chọn student_id từ dropdown.

bằng MỘT cổng đăng nhập username/password thật, băm bằng PBKDF2-HMAC-SHA256
(thư viện chuẩn `hashlib`, không cần cài thêm dependency). Tài khoản lưu trong
1 file JSON cục bộ (`app/data_warehouse/users.json`) — vì hệ thống hiện chưa có
CSDL SQL thật (xem mục "Database" trong bản đánh giá kiến trúc); đây là mức
triển khai đơn giản phù hợp quy mô đồ án nhưng vẫn đúng luồng kiến trúc
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
from dss.core.persistence_config import repository_for
from dss.core.logging_config import get_logger

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

# Định dạng student_id do generate_data() sinh ra: f"SV{i:03d}" -> SV001..SV999.
_STUDENT_ID_PATTERN = re.compile(r"^SV\d{3}$", re.IGNORECASE)


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
            if not users:
                _seed_default_accounts_into(users)
            return users
    except Exception:
        return {}


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
    pass


class AccountLockedError(AuthenticationError):
    """Tài khoản tạm thời bị khóa do thử sai mật khẩu nhiều lần."""
    pass


def is_account_locked(username: str) -> tuple[bool, int]:
    """Kiểm tra tài khoản có đang bị khóa hay không. Trả về (is_locked, remaining_seconds)."""
    return _throttle.is_locked(username)


def _record_failed_attempt(username: str) -> None:
    key = username.strip().lower()
    if _throttle.record_failure(key):
        _logger.warning("Bảo mật Auth: Tài khoản %s đã bị tạm khóa %d giây do nhập sai quá %d lần.", key, _LOCKOUT_DURATION_SECONDS, _MAX_FAILED_ATTEMPTS)


def _reset_failed_attempts(username: str) -> None:
    _throttle.reset(username)


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


def verify_lms_sso_token(token: str) -> Optional[UserRecord]:
    """Ranh giới tích hợp LMS SSO / OAuth / Token (Mục 27).

    Trong môi trường tích hợp thực tế với Canvas / Moodle / Blackboard,
    hàm này giải mã và xác thực JWT token từ LMS SSO gateway.
    """
    if not token or len(token) < 16:
        return None
    # Trích xuất payload từ token demo/mock cho ranh giới LMS
    if token.startswith("lms_bearer_"):
        parts = token.split("_")
        if len(parts) >= 4:
            s_id = parts[2].upper()
            return {
                "username": s_id.lower(),
                "role": "Sinh viên",
                "student_id": s_id,
                "hash": "",
                "salt": "",
                "auto_provisioned": False,
            }
    return None


def authenticate(username: str, password: str) -> Optional[UserRecord]:
    """Xác thực username/password kèm kiểm tra rate limiting và khóa tài khoản."""
    if not username or not password:
        return None
    key = username.strip().lower()

    # Kiểm tra khóa tài khoản
    locked, rem = is_account_locked(key)
    if locked:
        raise AccountLockedError(f"Tài khoản '{key}' tạm thời bị khóa do nhập sai nhiều lần. Vui lòng thử lại sau {rem} giây.")

    repository = repository_for("IDENTITY")
    users = {key: repository.get_user_by_username(key)} if repository is not None else _load_users()

    if key in users and users[key] is not None:
        record = users[key]
        if record.get("is_active", True) is False:
            _logger.warning("Đăng nhập bị chặn cho tài khoản vô hiệu hóa: username=%s", key)
            return None
        if _verify_password(password, record["hash"], record["salt"]):
            _reset_failed_attempts(key)
            if password_needs_rehash(record["hash"]):
                # Nâng cấp băm cũ ngay khi có mật khẩu đúng trong tay (không lưu/ghi log mật khẩu).
                try:
                    if repository is not None:
                        repository.reset_password(key, password)
                    else:
                        record["hash"], record["salt"] = _hash_password(password)
                        users[key] = record
                        _save_users(users)
                except Exception:
                    _logger.warning("Không nâng cấp được băm mật khẩu cho tài khoản (giữ băm cũ, vẫn đăng nhập).")
            if repository is not None:
                repository.touch_last_login(key)
            _logger.info("Đăng nhập thành công: username=%s role=%s", key, record.get("role"))
            return record
        _record_failed_attempt(key)
        _logger.warning("Đăng nhập thất bại (sai mật khẩu): username=%s", key)
        return None

    # Auto-provision tài khoản Sinh viên (<mã>/<mã>123) — CHỈ ngoài production
    # (C1.1: trước đây chỉ chặn khi EDUDSS_MODE=REAL_LMS, bỏ sót EDUDSS_ENV=production).
    from dss.core.runtime_mode import student_autoprovision_allowed
    if student_autoprovision_allowed() and _STUDENT_ID_PATTERN.match(key) and password == f"{key}123":
        if repository is not None:
            record = repository.create_user(
                username=key, password=password, role_name="Sinh viên",
                student_id=key.upper(), auto_provisioned=True,
            )
        else:
            hash_hex, salt_hex = _hash_password(password)
            record: UserRecord = {
                "username": key,
                "role": "Sinh viên",
                "student_id": key.upper(),
                "hash": hash_hex,
                "salt": salt_hex,
                "auto_provisioned": True,
            }
            users[key] = record
            _save_users(users)
        _reset_failed_attempts(key)
        _logger.info("Tự động tạo + đăng nhập tài khoản Sinh viên mới (Demo): username=%s", key)
        return record

    _record_failed_attempt(key)
    _logger.warning("Đăng nhập thất bại (tài khoản không tồn tại): username=%s", key)
    return None



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
                    f"Vai trò '{role}' không có quyền gọi {func.__name__} "
                    f"(yêu cầu: {', '.join(allowed_roles)})"
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


def logout() -> None:
    for k in (
        "_authenticated", "_auth_username", "_auth_role", "_auth_student_id",
        "_workspace_ready_for", "_app_started", "_auto_bootstrap_done_for",
    ):
        st.session_state.pop(k, None)
    # Xoá luôn dữ liệu phiên làm việc cũ (kết quả huấn luyện/phân cụm/chat) —
    # người đăng nhập kế tiếp không được thừa hưởng state của người trước.
    for k in list(st.session_state.keys()):
        if k.startswith(("hub_", "cluster_", "llm_", "reminder_done_")):
            st.session_state.pop(k, None)
    # Xoá riêng các widget nhập API key/secrets (không theo prefix "llm_" ở
    # trên) — phòng trường hợp phiên trình duyệt (WebSocket session) được TÁI
    # SỬ DỤNG cho lượt đăng nhập kế tiếp với vai trò thấp hơn (vd. Admin đăng
    # xuất, Giảng viên đăng nhập cùng tab): không được để lại giá trị key cũ
    # trong session_state dù widget đó không còn được vẽ ra cho vai trò mới.
    for k in (
        "gemini_key_input", "groq_key_input", "openai_key_input",
        "hf_token_input", "ollama_url_input",
    ):
        st.session_state.pop(k, None)


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
        return existing

    _seed_default_accounts_if_missing()

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
            "<div class='dss-login-mini-card blue'><span class='label'>Accuracy</span><span class='value'>92.5%</span></div>"
            "<div class='dss-login-mini-card yellow'><span class='label'>F1</span><span class='value'>71.5%</span></div>"
            "<div class='dss-login-mini-card green'><span class='label'>R²</span><span class='value'>99.3%</span></div>"
            "</div>"
            "<div class='dss-login-footer'>Kết quả đánh giá trên 1.000 mẫu dữ liệu mô phỏng — không phải độ chính xác trên sinh viên thật.</div>"
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
                        if record is None:
                            st.error("Sai tên đăng nhập hoặc mật khẩu.")
                        else:
                            st.session_state["_authenticated"] = True
                            st.session_state["_auth_username"] = record["username"]
                            st.session_state["_auth_role"] = record["role"]
                            st.session_state["_auth_student_id"] = record.get("student_id")
                            st.rerun()
                    except AccountLockedError as ale:
                        st.error(str(ale))

            # Không có tự đăng ký: tài khoản do Trường cấp (C1.3 — trình bày đúng
            # luồng cấp tài khoản thay vì dựng 1 form đăng ký không nối vào đâu).
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
                    st.caption("Chỉ dành cho môi trường phát triển và đánh giá. Khi triển khai thật, tài khoản do "
                               "hệ thống quản lý học tập của Trường cấp.")
                    st.markdown(demo_credentials_html(), unsafe_allow_html=True)
    return None
