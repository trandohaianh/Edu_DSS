"""Server-only bridge from authenticated EduDSS classes to the queued AI engine."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

_log = logging.getLogger(__name__)
_ROLE = {"Admin": "admin", "Giảng viên / CVHT": "instructor", "Sinh viên": "student"}


class EngineGatewayError(RuntimeError):
    pass


class EngineUnavailable(EngineGatewayError):
    def __init__(self, message, *, job_id=None, state=None, submission_status=None):
        super().__init__(message)
        self.job_id = job_id
        self.state = state
        self.submission_status = submission_status


class EngineNotReady(EngineGatewayError):
    pass


def enabled():
    """URL is the explicit cutover flag; incomplete enabled config fails closed."""
    return bool(os.environ.get("EDUDSS_ENGINE_URL", "").strip())


def _configuration():
    value = os.environ.get("EDUDSS_ENGINE_URL", "").strip().rstrip("/")
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise EngineGatewayError("Địa chỉ dịch vụ học tập chưa được cấu hình hợp lệ.")
    key = os.environ.get("EDUDSS_ENGINE_SIGNING_KEY", "")
    if len(key.encode("utf-8")) < 32:
        raise EngineGatewayError("Khóa kết nối dịch vụ học tập chưa được quản trị viên cấu hình.")
    return value, key


def _actor():
    from dss.platform.context import current_actor

    return current_actor()


def _classes(actor):
    from dss.services.classroom_service import list_my_classes

    return list_my_classes(actor)


def _authorize(course_id, roles=None):
    actor = _actor()
    if actor.role not in _ROLE:
        raise PermissionError("Vai trò hiện tại không được truy cập dịch vụ học tập.")
    if (
        not isinstance(course_id, str)
        or not course_id.strip()
        or len(course_id) > 128
        or course_id != course_id.strip()
    ):
        raise ValueError("Cần mã học phần hợp lệ.")
    if roles and _ROLE[actor.role] not in roles:
        raise PermissionError("Thao tác này không dành cho vai trò hiện tại.")
    if actor.role == "Sinh viên" and not actor.student_id:
        raise PermissionError("Tài khoản chưa có mã sinh viên được xác thực.")
    from dss.platform.models import School
    from dss.platform.store import platform_session

    with platform_session(actor.school_id, actor=actor) as session:
        if session.get(School, actor.school_id) is None:
            raise PermissionError("Trường chưa được đăng ký trong hệ thống.")
    if actor.role != "Admin" and not any(row["course_id"] == course_id for row in _classes(actor)):
        raise PermissionError("Bạn chưa được phân công hoặc ghi danh vào học phần này.")
    return actor


def _authorize_write(course_id, roles=None):
    actor = _authorize(course_id, roles)
    from dss.platform.store import platform_session
    from dss.services.classroom_service import require_school_writes

    with platform_session(actor.school_id, actor=actor) as session:
        require_school_writes(session, actor)
    if not any(row["course_id"] == course_id and row["status"] == "active" for row in _classes(actor)):
        raise PermissionError("Học phần chưa có lớp đang hoạt động được phép truy cập.")
    return actor


def available_courses():
    actor = _actor()
    if actor.role not in _ROLE:
        raise PermissionError("Vai trò hiện tại không được truy cập dịch vụ học tập.")
    courses = {row["course_id"] for row in _classes(actor)}
    if actor.role == "Admin":
        from dss.services.cms_lecture_repository import list_lessons

        courses.update(lesson.course_id for lesson in list_lessons())
    return sorted(courses)


def _b64(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _token(actor, *, bridge=False):
    """Interoperable HS256, never sent to a browser or persisted in a cache map."""
    _, key = _configuration()
    now = int(time.time())
    principal = (
        "legacy-bridge:" + hashlib.sha256(actor.username.encode()).hexdigest()[:40] if bridge else actor.username
    )
    payload = dict(
        iss="edudss-engine",
        aud="edudss-api",
        sub=principal,
        school=actor.school_id,
        role="admin" if bridge else _ROLE[actor.role],
        student_id=None if bridge else (actor.student_id or None),
        iat=now,
        exp=now + 120,
    )
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
    message = (header + "." + body).encode("ascii")
    signature = _b64(hmac.new(key.encode(), message, hashlib.sha256).digest())
    return header + "." + body + "." + signature


def _transport(method, url, headers, payload=None):
    encoded = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=encoded, headers=headers, method=method)
    try:
        with urlopen(request, timeout=8) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise EngineGatewayError("Phản hồi dịch vụ học tập vượt giới hạn.")
            return response.status, json.loads(raw.decode("utf-8"))
    except HTTPError as error:
        raw = error.read(65537)
        if len(raw) > 65536:
            return error.code, {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            payload = {}
        return error.code, payload if isinstance(payload, dict) else {}
    except (URLError, OSError, TimeoutError, ValueError):
        raise EngineUnavailable("Chưa kết nối được dịch vụ học tập. Không gọi AI trực tiếp thay thế.") from None


def _raw(actor, course_id, method, suffix, payload=None, *, bridge=False, params=None):
    base, _ = _configuration()
    url = base + "/v1/courses/" + quote(course_id, safe="") + suffix
    if params:
        url += "?" + urlencode(params)
    status, result = _transport(
        method,
        url,
        {
            "Authorization": "Bearer " + _token(actor, bridge=bridge),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        payload,
    )
    if status in {401, 403}:
        raise PermissionError("Dịch vụ học tập chưa xác nhận quyền truy cập của tài khoản.")
    if status == 404:
        raise EngineNotReady("Học phần chưa có mô hình hoặc học liệu đã chuẩn bị.")
    if status in {429, 503}:
        job_id = result.get("job_id")
        if not isinstance(job_id, str) or len(job_id) != 32 or any(char not in "0123456789abcdef" for char in job_id):
            job_id = None
        state = result.get("state")
        if not isinstance(state, str) or len(state) > 40:
            state = None
        submission_status = result.get("submission_status")
        if submission_status not in {"unknown", "not_submitted"}:
            submission_status = None
        raise EngineUnavailable(
            "Hàng đợi đang bận hoặc dịch vụ chưa sẵn sàng. Vui lòng thử lại sau.",
            job_id=job_id,
            state=state,
            submission_status=submission_status,
        )
    if not 200 <= status < 300 or not isinstance(result, dict):
        raise EngineGatewayError("Chưa hoàn tất thao tác dịch vụ học tập; quản trị viên cần kiểm tra cấu hình.")
    return result


# Đồng bộ thành viên sang engine: trước đây MỖI lệnh gọi của giảng viên/sinh viên đều tạo một JWT quyền admin để
# POST /members. Nay chỉ đồng bộ lại khi chưa đồng bộ trong MEMBER_SYNC_TTL_S giây (theo trường, người dùng, vai
# trò, mã SV, học phần). Quyền vẫn được kiểm ở phía Streamlit (``_authorize``) trước mọi lệnh gọi, nên bộ nhớ đệm
# không mở rộng quyền; gỡ khỏi lớp thì xoá mục đệm và gửi ``active=False`` (``deactivate_member``).
MEMBER_SYNC_TTL_S = 600
_member_synced: dict[tuple, float] = {}
_member_lock = threading.Lock()


def reset_member_cache():
    """Xoá bộ nhớ đệm đồng bộ thành viên (test; hoặc khi đổi cấu hình engine)."""
    with _member_lock:
        _member_synced.clear()


def _member_key(actor, course_id):
    return (actor.school_id, actor.username, _ROLE[actor.role], actor.student_id or None, course_id)


def _forget_member(school_id, course_id, principal_id=None, student_id=None):
    with _member_lock:
        for key in [
            k
            for k in _member_synced
            if k[0] == school_id
            and k[4] == course_id
            and ((principal_id and k[1] == principal_id) or (student_id and k[3] == student_id))
        ]:
            _member_synced.pop(key, None)


def _call(course_id, method, suffix, payload=None, *, roles=None, params=None):
    actor = _authorize(course_id, roles)
    if actor.role != "Admin":
        key, now = _member_key(actor, course_id), time.monotonic()
        with _member_lock:
            fresh = _member_synced.get(key, 0.0) > now
        if not fresh:
            # Only an identity already checked against this school's official class
            # assignments is mirrored. The elevated JWT stays inside this server.
            _raw(
                actor,
                course_id,
                "POST",
                "/members",
                dict(
                    principal_id=actor.username,
                    role=_ROLE[actor.role],
                    student_id=actor.student_id or None,
                    active=True,
                ),
                bridge=True,
            )
            if _authorize(course_id, roles) != actor:
                raise PermissionError("Phiên xác thực đã thay đổi; vui lòng thực hiện lại.")
            with _member_lock:
                if len(_member_synced) > 10_000:
                    _member_synced.clear()
                _member_synced[key] = now + MEMBER_SYNC_TTL_S
    return _raw(actor, course_id, method, suffix, payload, params=params)


def deactivate_member(admin_actor, course_id, principal_id, role, student_id=None):
    """Báo engine gỡ một thành viên khỏi học phần (``active=False``) sau khi quản trị thu hồi phân công/ghi danh.

    Không chặn thao tác cục bộ: quyền ở Streamlit đã bị thu hồi trong CSDL; lỗi kết nối chỉ ghi log (engine tự
    chặn khi đồng bộ lần sau vì người này không còn qua được ``_authorize``)."""
    _forget_member(admin_actor.school_id, course_id, principal_id=principal_id, student_id=student_id)
    if not enabled():
        return False
    if role == "student" and not student_id:
        return False
    try:
        _raw(
            admin_actor,
            course_id,
            "POST",
            "/members",
            dict(
                principal_id=principal_id, role=role, student_id=student_id if role == "student" else None, active=False
            ),
            bridge=True,
        )
        return True
    except (EngineGatewayError, PermissionError, ValueError):
        _log.warning("Không gỡ được thành viên khỏi engine (course=%s); sẽ bị chặn ở lần đồng bộ sau.", course_id)
        return False


def get_predictions(course_id):
    return _call(course_id, "GET", "/predictions", roles={"student"})


def get_recommendations(course_id, k=5):
    if type(k) is not int or not 1 <= k <= 20:
        raise ValueError("Số gợi ý cần nằm trong 1..20.")
    return _call(course_id, "GET", "/recommendations", roles={"student"}, params={"k": k})


def get_leaderboard(course_id):
    return _call(course_id, "GET", "/leaderboard", roles={"admin", "instructor"})


def get_class_risk(course_id, offset=0, limit=50):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Phân trang cần giới hạn 1..100 và vị trí không âm.")
    actor = _authorize(course_id, {"admin", "instructor"})
    result = _call(
        course_id, "GET", "/class-risk", roles={"admin", "instructor"}, params={"offset": offset, "limit": limit}
    )
    checked = _authorize(course_id, {"admin", "instructor"})
    if checked != actor:
        raise PermissionError("Phiên xác thực đã thay đổi.")
    if actor.role != "Admin":
        from dss.services.classroom_service import list_class_roster

        allowed = set()
        for classroom in _classes(actor):
            if classroom["course_id"] == course_id:
                allowed.update(row["student_code"] for row in list_class_roster(actor, classroom["id"]))
        result = dict(result)
        result["items"] = [row for row in result.get("items", []) if row.get("student_id") in allowed]
        # Pagination is over the engine's fitted population, so it can be sparse.
        # Do not report the entire course count as this teacher's own roster size.
        result["total"] = None
        result["population"] = "Current assigned-class roster entries present in this fitted-model page."
    return result


def get_queue(course_id):
    return _call(course_id, "GET", "/queue", roles={"admin"})


def request_advice(course_id, request_id, k=5):
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
        raise ValueError("Cần mã yêu cầu hợp lệ để tránh gửi trùng.")
    _authorize_write(course_id, {"student"})
    return _call(course_id, "POST", "/advice", {"request_id": request_id, "k": k}, roles={"student"})


def get_job(course_id, job_id):
    if not isinstance(job_id, str) or not 1 <= len(job_id) <= 128:
        raise ValueError("Cần mã tác vụ hợp lệ.")
    return _call(course_id, "GET", "/jobs/" + quote(job_id, safe=""))


def _mapping_path(actor, course_id, lesson_id):
    from dss.core.data_root import get_data_root

    key = hashlib.sha256(json.dumps([actor.school_id, course_id, lesson_id], ensure_ascii=False).encode()).hexdigest()
    return Path(get_data_root()) / "engine_bridge" / (key + ".json")


def _read_mapping(actor, course_id, lesson_id):
    path = _mapping_path(actor, course_id, lesson_id)
    try:
        if path.stat().st_size > 2 * 1024 * 1024:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _save_mapping(actor, course_id, lesson_id, value):
    path = _mapping_path(actor, course_id, lesson_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".bridge-", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def authorize_staff_course(course_id):
    return _authorize_write(course_id, {"admin", "instructor"})


def _approved(lesson, course_id):
    from dss.services.learning_plan_resources import approved_plan_resources

    return bool(
        lesson.ai_enabled
        and lesson.official_source
        and any(
            row.get("lesson_id") == lesson.lesson_id and row.get("document_id") == lesson.current_document_id
            for row in approved_plan_resources(course_id)
        )
    )


def _paragraphs(chunks, course_id, document_id):
    parts = []
    for chunk in chunks:
        value = chunk.to_dict() if hasattr(chunk, "to_dict") else chunk
        if (
            not isinstance(value, dict)
            or value.get("course_id") != course_id
            or value.get("document_id") != document_id
        ):
            raise PermissionError("Nội dung bài giảng không khớp học phần và phiên bản.")
        text = value.get("content", "")
        if not isinstance(text, str):
            raise ValueError("Nội dung bài giảng chưa hợp lệ.")
        for start in range(0, len(text), 2000):
            paragraph = text[start : start + 2000].strip()
            if paragraph:
                parts.append({"paragraph_id": f"p{len(parts):04d}", "text": paragraph})
    if not parts or len(parts) > 100:
        raise EngineGatewayError(
            "Bài giảng cần từ 1 đến 100 đoạn; hãy chia tài liệu lớn trước khi chuẩn bị giải thích."
        )
    return parts


def _lesson_source(course_id, lesson_id, *, require_approved=True, chunks=None):
    actor = _authorize(course_id)
    from dss.services import cms_lecture_repository as cms
    from dss.services import vector_store
    from dss.services.rag_namespaces import NAMESPACE_STUDENT_LEARNING

    lesson = cms.get_lesson(lesson_id)
    if not lesson or lesson.course_id != course_id or not lesson.current_document_id:
        raise PermissionError("Bài giảng hiện tại không thuộc học phần được phép.")
    if require_approved and not _approved(lesson, course_id):
        raise PermissionError("Bài giảng hiện tại chưa được duyệt hoặc đã ngừng cho phép giải thích.")
    if chunks is None:
        store = vector_store.get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING)
        chunks = store.get_document_chunks(lesson.current_document_id, course_id=course_id)
    paragraphs = _paragraphs(chunks, course_id, lesson.current_document_id)
    body = {"title": lesson.title, "paragraphs": paragraphs}
    body_hash = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return actor, lesson, paragraphs, body_hash


def _lecture_id(actor, course_id, lesson_id):
    return (
        "cms-"
        + hashlib.sha256(json.dumps([actor.school_id, course_id, lesson_id], ensure_ascii=False).encode()).hexdigest()
    )


def sync_lesson(course_id, lesson_id, *, chunks=None, retry_failed=False):
    """Explicit staff preparation; approval always uses the uploaded version CAS."""
    actor = authorize_staff_course(course_id)
    _, lesson, paragraphs, body_hash = _lesson_source(course_id, lesson_id, require_approved=False, chunks=chunks)
    if not lesson.ai_enabled:
        previous = _read_mapping(actor, course_id, lesson_id)
        if previous:
            _call(
                course_id,
                "PUT",
                "/lectures/" + previous["lecture_id"] + "/approval",
                {"approved": False, "version": previous["version"]},
                roles={"admin", "instructor"},
            )
        return {"state": "DISABLED", "approved": False, "jobs": []}
    lecture_id = _lecture_id(actor, course_id, lesson_id)
    uploaded = _call(
        course_id,
        "POST",
        "/lectures",
        {"lecture_id": lecture_id, "title": lesson.title, "paragraphs": paragraphs},
        roles={"admin", "instructor"},
    )
    version = uploaded.get("version")
    if not isinstance(version, str) or not version:
        raise EngineGatewayError("Dịch vụ chưa trả về phiên bản bài giảng hợp lệ.")
    # Re-read after network work so a replaced lesson cannot approve an old body.
    from dss.services import cms_lecture_repository as cms

    current = cms.get_lesson(lesson_id)
    if (
        not current
        or current.course_id != course_id
        or current.current_document_id != lesson.current_document_id
        or current.title != lesson.title
    ):
        _call(
            course_id,
            "PUT",
            "/lectures/" + lecture_id + "/approval",
            {"approved": False, "version": version},
            roles={"admin", "instructor"},
        )
        raise EngineGatewayError("Bài giảng vừa thay phiên bản. Vui lòng đồng bộ lại.")
    approved = _approved(current, course_id)
    _call(
        course_id,
        "PUT",
        "/lectures/" + lecture_id + "/approval",
        {"approved": approved, "version": version},
        roles={"admin", "instructor"},
    )
    if retry_failed:
        uploaded = _call(course_id, "POST", "/lectures/" + lecture_id + "/retry", roles={"admin", "instructor"})
        if uploaded.get("version") != version:
            raise EngineGatewayError("Phiên bản bài giảng đã đổi; hãy đồng bộ lại.")
    value = dict(
        lecture_id=lecture_id,
        version=version,
        document_id=lesson.current_document_id,
        body_hash=body_hash,
        approved=approved,
        paragraphs=paragraphs,
        title=lesson.title,
    )
    _save_mapping(actor, course_id, lesson_id, value)
    return {
        "state": "PREPARED" if approved else "AWAITING_APPROVAL",
        "approved": approved,
        "version": version,
        "jobs": uploaded.get("jobs", []),
    }


def auto_sync_upload(course_id, lesson_id, chunks):
    """CMS success remains valid if the optional queue is temporarily unavailable."""
    if not enabled():
        return None
    try:
        return sync_lesson(course_id, lesson_id, chunks=chunks)
    except Exception:
        from dss.core.logging_config import get_logger

        get_logger(__name__).warning(
            "CMS material was saved; queued explanation preparation needs an authorized staff retry."
        )
        return {"state": "SYNC_PENDING"}


def list_cached_paragraphs(course_id, lesson_id):
    actor, lesson, paragraphs, body_hash = _lesson_source(course_id, lesson_id)
    value = _read_mapping(actor, course_id, lesson_id)
    if (
        not value
        or value.get("document_id") != lesson.current_document_id
        or value.get("body_hash") != body_hash
        or not value.get("approved")
    ):
        return []
    return [{"paragraph_id": part["paragraph_id"], "preview": part["text"][:100]} for part in paragraphs]


def get_cached_explanation(course_id, lesson_id, paragraph_id=None):
    """Student reads only: no upload, approval, retry, enqueue or inline LLM call."""
    actor, lesson, paragraphs, body_hash = _lesson_source(course_id, lesson_id)
    value = _read_mapping(actor, course_id, lesson_id)
    pending = dict(
        state="PENDING",
        title=lesson.title,
        text="Giải thích đang được chuẩn bị hoặc cần giảng viên đồng bộ sau khi duyệt.",
    )
    if (
        not value
        or value.get("document_id") != lesson.current_document_id
        or value.get("body_hash") != body_hash
        or not value.get("approved")
    ):
        return pending
    selected = next(
        (part for part in paragraphs if part["paragraph_id"] == (paragraph_id or paragraphs[0]["paragraph_id"])), None
    )
    if selected is None:
        raise PermissionError("Đoạn bài giảng không thuộc phiên bản hiện tại.")
    suffix = "/lectures/" + value["lecture_id"] + "/paragraphs/" + selected["paragraph_id"]
    try:
        response = _call(course_id, "GET", suffix)
    except EngineNotReady:
        return pending
    # Revalidate legacy approval/version after fetching, including revocation races.
    checked_actor, checked_lesson, _, checked_hash = _lesson_source(course_id, lesson_id)
    if (
        checked_actor != actor
        or checked_hash != body_hash
        or checked_lesson.current_document_id != lesson.current_document_id
    ):
        raise PermissionError("Bài giảng hoặc quyền truy cập đã thay đổi.")
    if (
        response.get("version") != value["version"]
        or response.get("paragraph_id") != selected["paragraph_id"]
        or response.get("original_text") != selected["text"]
    ):
        return pending
    cached = response.get("explanation")
    if response.get("state") != "READY" or not isinstance(cached, dict) or not isinstance(cached.get("text"), str):
        return pending
    expected_hash = hashlib.sha256(selected["text"].encode()).hexdigest()
    if cached.get("text_hash") != expected_hash or cached.get("version") != value["version"]:
        return pending
    return dict(
        state="READY",
        title=lesson.title,
        text=cached["text"],
        original_text=selected["text"],
        paragraph_id=selected["paragraph_id"],
        demo=bool(cached.get("demo")),
        version=value["version"],
    )
