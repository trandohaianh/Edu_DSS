"""The bridge uses authenticated class assignments and never generates on reads."""
import base64
import hashlib
import hmac
import json
from urllib.parse import urlparse

import pytest
from streamlit.testing.v1 import AppTest

from dss.platform.context import Actor
from dss.platform.models import School
from dss.platform.store import platform_session, reset_platform_engines
from dss.services import classroom_service as classes
from dss.services import cms_lecture_repository as cms
from dss.services import engine_gateway as gateway
from dss.services import vector_store
from dss.services.chunking_service import DocumentChunk

KEY = "bridge-test-signing-key-at-least-thirty-two-bytes"


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    for key, value in {
        "EDUDSS_ENV": "test", "EDUDSS_MODE": "DEMO_SYNTHETIC",
        "EDUDSS_PLATFORM_STORE": "local", "EDUDSS_DATA_ROOT": str(tmp_path),
        "EDUDSS_ORGANIZATION_ID": "1", "EDUDSS_REQUIRE_PROGRAM_ALLOCATION": "0",
        "EDUDSS_CMS_STORE": "local", "EDUDSS_RAG_STORE": "local",
        "EDUDSS_ENGINE_URL": "http://engine.invalid",
        "EDUDSS_ENGINE_SIGNING_KEY": KEY,
    }.items():
        monkeypatch.setenv(key, value)
    reset_platform_engines()
    gateway.reset_member_cache()
    admin = Actor("1", "admin", classes.ADMIN)
    teacher = Actor("1", "teacher", classes.TEACHER)
    student = Actor("1", "student", classes.STUDENT, "SV1")
    classroom = classes.create_class(admin, "LAW01", "LAW101", "Foundations", "2026")
    classes.assign_teacher(admin, classroom["id"], teacher.username)
    classes.enroll_student(admin, classroom["id"], student.student_id)
    monkeypatch.setattr(gateway, "_actor", lambda: student)
    lesson = cms.CMSLesson(lesson_id="l1", course_id="LAW101", topic_id="sources",
        lecturer_id="teacher", title="Official sources", current_document_id="d1")
    cms._upsert_lesson(lesson)
    text = "Approved source: foundational principles."
    vector_store.get_vector_store().add_chunks([DocumentChunk(
        chunk_id="d1#c0", document_id="d1", course_id="LAW101", content=text,
        token_count=10, embedding=[1.0, 0.0],
        metadata={"title": lesson.title, "status": "APPROVED", "approved_by": "teacher", "chunk_index": 0})])
    records, remote = [], {"version": "v1", "approved": False}
    def transport(method, url, headers, payload=None):
        path = urlparse(url).path
        token = headers["Authorization"].split()[1]
        record = dict(method=method, path=path, payload=payload, token=token)
        records.append(record)
        if path.endswith("/members"):
            return 200, {"active": True}
        if method == "POST" and path.endswith("/lectures"):
            remote["paragraphs"] = payload["paragraphs"]
            return 202, {"version": remote["version"], "jobs": [{"job_id": "pregen", "state": "QUEUED"}]}
        if path.endswith("/approval"):
            assert payload["version"] == remote["version"]
            remote["approved"] = payload["approved"]
            return 200, {"version": remote["version"], "approved": remote["approved"]}
        if "/paragraphs/" in path:
            part = remote["paragraphs"][0]
            return 200, dict(state="READY", version=remote["version"],
                paragraph_id=part["paragraph_id"], original_text=part["text"],
                explanation=dict(text="Prepared explanation", version=remote["version"],
                    text_hash=hashlib.sha256(part["text"].encode()).hexdigest(), demo=True))
        if path.endswith("/advice"):
            return 202, {"job": {"job_id": "advice", "state": "QUEUED"}}
        return 200, {}
    monkeypatch.setattr(gateway, "_transport", transport)
    yield dict(admin=admin, teacher=teacher, student=student, classroom=classroom,
               lesson=lesson, records=records, remote=remote, text=text)
    reset_platform_engines()


def _as(monkeypatch, workspace, role):
    monkeypatch.setattr(gateway, "_actor", lambda: workspace[role])


def _sync(monkeypatch, workspace):
    _as(monkeypatch, workspace, "teacher")
    result = gateway.sync_lesson("LAW101", "l1")
    assert result["approved"]
    return result


def test_bridge_jwt_has_verified_scope_and_server_only_elevation(workspace, monkeypatch):
    gateway.get_predictions("LAW101")
    member, read = workspace["records"]
    def decode(token):
        encoded_header, encoded_body, signature = token.split(".")
        assert hmac.compare_digest(
            base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4)),
            hmac.new(KEY.encode(), (encoded_header + "." + encoded_body).encode(), hashlib.sha256).digest())
        return json.loads(base64.urlsafe_b64decode(encoded_body + "=" * (-len(encoded_body) % 4)))
    assert member["path"].endswith("/members")
    elevated = decode(member["token"])
    ordinary = decode(read["token"])
    assert elevated["role"] == "admin" and elevated["school"] == "1"
    assert elevated["sub"].startswith("legacy-bridge:")
    assert ordinary["role"] == "student" and ordinary["student_id"] == "SV1"
    assert ordinary["sub"] == "student" and ordinary["exp"] - ordinary["iat"] == 120
    assert ordinary["iss"] == "edudss-engine" and ordinary["aud"] == "edudss-api"


def test_removed_enrollment_or_unassigned_course_never_calls_engine(workspace):
    with platform_session("1", write=True, actor=workspace["admin"]) as session:
        from dss.platform.models import ClassEnrollment
        row = session.query(ClassEnrollment).filter_by(student_code="SV1").one()
        row.active = False
    with pytest.raises(PermissionError):
        gateway.get_predictions("LAW101")
    with pytest.raises(PermissionError):
        gateway.get_predictions("FOREIGN")
    assert workspace["records"] == []


def test_school_pause_blocks_new_advice_but_allows_authorized_cached_reads(workspace):
    with platform_session("1", write=True, actor=workspace["admin"]) as session:
        session.get(School, "1").active = False
    with pytest.raises(PermissionError):
        gateway.request_advice("LAW101", "one")
    assert workspace["records"] == []
    gateway.get_predictions("LAW101")
    assert workspace["records"][-1]["method"] == "GET"


def test_closed_class_blocks_new_advice_but_retains_existing_reads(workspace):
    classes.set_class_status(workspace["admin"], workspace["classroom"]["id"], "closed")
    with pytest.raises(PermissionError):
        gateway.request_advice("LAW101", "one")
    gateway.get_job("LAW101", "existing")
    assert workspace["records"][-1]["path"].endswith("/jobs/existing")


def test_enabled_without_signing_key_fails_closed(workspace, monkeypatch):
    monkeypatch.setenv("EDUDSS_ENGINE_SIGNING_KEY", "")
    assert gateway.enabled()
    with pytest.raises(gateway.EngineGatewayError):
        gateway.get_predictions("LAW101")
    assert workspace["records"] == []


def test_student_cannot_upload_prepare_or_read_staff_reports(workspace):
    for callback in [
        lambda: gateway.sync_lesson("LAW101", "l1"),
        lambda: gateway.get_leaderboard("LAW101"),
        lambda: gateway.get_class_risk("LAW101"),
        lambda: gateway.get_queue("LAW101"),
    ]:
        with pytest.raises(PermissionError):
            callback()
    assert workspace["records"] == []


def test_staff_sync_is_versioned_and_student_reads_never_queue(workspace, monkeypatch):
    result = _sync(monkeypatch, workspace)
    assert result["version"] == "v1"
    _as(monkeypatch, workspace, "student")
    workspace["records"].clear()
    paragraphs = gateway.list_cached_paragraphs("LAW101", "l1")
    assert paragraphs[0]["paragraph_id"] == "p0000"
    cached = gateway.get_cached_explanation("LAW101", "l1", "p0000")
    assert cached["text"] == "Prepared explanation" and cached["demo"]
    assert [(r["method"], r["path"].rsplit("/", 1)[-1]) for r in workspace["records"]] == [
        ("POST", "members"), ("GET", "p0000")]
    assert not any("/advice" in row["path"] or row["path"].endswith("/lectures") for row in workspace["records"])


def test_unprepared_or_replaced_lesson_read_is_pending_with_no_remote_requests(workspace, monkeypatch):
    assert gateway.get_cached_explanation("LAW101", "l1")["state"] == "PENDING"
    assert workspace["records"] == []
    _sync(monkeypatch, workspace)
    _as(monkeypatch, workspace, "student")
    lesson = cms.get_lesson("l1")
    lesson.title = "Replaced title"
    cms._upsert_lesson(lesson)
    workspace["records"].clear()
    assert gateway.get_cached_explanation("LAW101", "l1")["state"] == "PENDING"
    assert workspace["records"] == []


def test_revoked_approval_or_mismatched_cache_never_exposes_text(workspace, monkeypatch):
    _sync(monkeypatch, workspace)
    _as(monkeypatch, workspace, "student")
    workspace["remote"]["version"] = "different"
    assert gateway.get_cached_explanation("LAW101", "l1")["state"] == "PENDING"
    cms.mark_official_source("l1", False)
    workspace["records"].clear()
    with pytest.raises(PermissionError):
        gateway.get_cached_explanation("LAW101", "l1")
    assert workspace["records"] == []


def test_legacy_explainer_uses_cache_without_direct_provider_or_retrieval(workspace, monkeypatch):
    from dss.services import learning_explainer
    _sync(monkeypatch, workspace)
    _as(monkeypatch, workspace, "student")
    monkeypatch.setattr(cms, "retrieve_lesson_content",
        lambda *args, **kwargs: pytest.fail("enabled cache read must not embed, retrieve or call provider"))
    result = learning_explainer.generate_explanation(None, "Question?", "LAW101", "l1", None, "Standard",
                                                     socratic_mode=True)
    assert result.answer == "Prepared explanation" and not result.used_socratic_mode


def test_enabled_cms_upload_authorizes_before_writing_and_uses_authenticated_lecturer(workspace, monkeypatch):
    with pytest.raises(PermissionError):
        cms.ingest_lecture_material(b"test", "test.txt", "Test", "LAW101", "new", "t", "forged", None)
    assert cms.get_lesson("new") is None
    _as(monkeypatch, workspace, "teacher")
    synced = []
    monkeypatch.setattr(gateway, "auto_sync_upload", lambda course, lesson_id, chunks: synced.append((course, lesson_id, chunks)))
    lesson = cms.ingest_lecture_material(
        b"Original teacher material.", "test.txt", "Test", "LAW101", "new", "t", "forged", None)
    assert lesson.lecturer_id == "teacher" and lesson.versions[0].uploaded_by == "teacher"
    assert synced[0][:2] == ("LAW101", "new") and synced[0][2]


def _render():
    from dss.tabs.engine_advisor import engine_advisor_tab
    engine_advisor_tab()


def test_student_ui_only_queues_on_explicit_request_and_renders_polled_result(workspace, monkeypatch):
    monkeypatch.setattr(gateway, "get_predictions", lambda course: dict(
        grade=6.25, source="synthetic", reference_at="2025-01-01", stale_data=True))
    monkeypatch.setattr(gateway, "get_recommendations", lambda course: dict(
        items=[dict(item_id="A1", topic_id="sources", reason="Foundation")]))
    requested = []
    monkeypatch.setattr(gateway, "request_advice", lambda course, request_id: (
        requested.append(request_id) or {"job": {"job_id": "job"}}))
    monkeypatch.setattr(gateway, "get_job", lambda course, job: dict(
        state="SUCCEEDED", result={"text": "Prepared study plan"}, demo=True))
    app = AppTest.from_function(_render, default_timeout=30).run()
    assert not app.exception and not app.error
    assert requested == []
    next(b for b in app.button if b.label == "Tạo tư vấn học tập").click().run()
    assert not app.exception and not app.error
    assert len(requested) == 1
    assert any(item.value == "Prepared study plan" for item in app.markdown)
    next(b for b in app.button if b.label == "Cập nhật tư vấn").click().run()
    assert len(requested) == 1


def test_student_ui_reuses_request_id_after_ambiguous_publish(workspace, monkeypatch):
    monkeypatch.setattr(gateway, "get_predictions", lambda course: dict(
        grade=None, source="TEST_FIXTURE", reference_at="2025-01-01", stale_data=False))
    monkeypatch.setattr(gateway, "get_recommendations", lambda course: dict(items=[]))
    request_ids = []
    def request_advice(course, request_id):
        request_ids.append(request_id)
        if len(request_ids) == 1:
            raise gateway.EngineUnavailable(
                "queue uncertain", job_id="a" * 32, state="DISPATCH_UNCERTAIN",
                submission_status="unknown")
        return {"job": {"job_id": "a" * 32}}
    monkeypatch.setattr(gateway, "request_advice", request_advice)
    monkeypatch.setattr(gateway, "get_job", lambda course, job_id: dict(
        job_id=job_id, state="DISPATCH_UNCERTAIN"))
    app = AppTest.from_function(_render, default_timeout=30).run()
    next(button for button in app.button if button.label == "Tạo tư vấn học tập").click().run()
    assert not app.exception and not app.error
    assert len(request_ids) == 1
    next(button for button in app.button if button.label == "Gửi lại yêu cầu chưa xác nhận").click().run()
    assert not app.exception and not app.error
    assert len(request_ids) == 2 and request_ids[0] == request_ids[1]


def test_student_ui_reads_one_selected_paragraph_without_queueing(workspace, monkeypatch):
    _sync(monkeypatch, workspace)
    _as(monkeypatch, workspace, "student")
    app = AppTest.from_function(_render, default_timeout=30).run()
    # The default advice view may legitimately have no model in this fixture.
    app.radio[0].set_value("Giải thích bài học")
    workspace["records"].clear()
    app.run()
    assert not app.exception and not app.error
    assert any(item.value == "Prepared explanation" for item in app.markdown)
    assert sum("/paragraphs/" in row["path"] for row in workspace["records"]) == 1
    assert not any(row["path"].endswith("/advice") for row in workspace["records"])


def test_teacher_ui_can_view_course_risk_but_queue_requires_admin(workspace, monkeypatch):
    _as(monkeypatch, workspace, "teacher")
    monkeypatch.setattr(gateway, "get_class_risk", lambda course, offset=0, limit=50: dict(
        reference_at="2025-01-01", items=[{"student_id": "SV1", "grade": 4.2, "risk": 2, "stale_data": True}]))
    app = AppTest.from_function(_render, default_timeout=30).run()
    assert not app.exception and not app.error
    assert not any("hàng đợi học phần" in button.label for button in app.button)
    next(button for button in app.button if button.label == "Xem dự báo của học phần").click().run()
    assert not app.exception and not app.error
    assert any("Mã sinh viên" in frame.value.columns for frame in app.dataframe)
    with pytest.raises(PermissionError):
        gateway.get_queue("LAW101")


def test_admin_ui_can_inspect_scoped_queue(workspace, monkeypatch):
    _as(monkeypatch, workspace, "admin")
    monkeypatch.setattr(gateway, "get_queue", lambda course: dict(pending=3, jobs=[
        {"job_id": "one", "kind": "paragraph", "state": "QUEUED"}]))
    app = AppTest.from_function(_render, default_timeout=30).run()
    next(button for button in app.button if button.label == "Xem trạng thái hàng đợi học phần").click().run()
    assert not app.exception and not app.error
    assert any(metric.value == "3" for metric in app.metric)


def test_unregistered_school_admin_cannot_read_or_write_engine(workspace, monkeypatch):
    monkeypatch.setattr(gateway, "_actor", lambda: Actor("2", "admin", classes.ADMIN))
    with pytest.raises(PermissionError):
        gateway.get_queue("LAW101")
    assert workspace["records"] == []

def test_enabled_upload_cannot_overwrite_another_course_lesson_id(workspace, monkeypatch):
    other = classes.create_class(workspace["admin"], "OTHER", "OTHER101", "Other", "2026")
    classes.assign_teacher(workspace["admin"], other["id"], workspace["teacher"].username)
    _as(monkeypatch, workspace, "teacher")
    with pytest.raises(PermissionError):
        cms.ingest_lecture_material(b"Overwrite", "test.txt", "Foreign", "OTHER101", "l1", "t", "forged", None)
    current = cms.get_lesson("l1")
    assert current.course_id == "LAW101" and current.current_document_id == "d1"
    assert workspace["records"] == []

def test_teacher_risk_rows_are_filtered_to_assigned_class_rosters(workspace, monkeypatch):
    _as(monkeypatch, workspace, "teacher")
    foreign = classes.create_class(workspace["admin"], "LAW02", "LAW101", "Other cohort", "2026")
    classes.enroll_student(workspace["admin"], foreign["id"], "OTHER_STUDENT")
    previous = gateway._transport
    def transport(method, url, headers, payload=None):
        if urlparse(url).path.endswith("/class-risk"):
            return 200, {"items": [{"student_id": "SV1", "grade": 6}, {"student_id": "OTHER_STUDENT", "grade": 2}],
                         "offset": 0, "limit": 50, "total": 2}
        return previous(method, url, headers, payload)
    monkeypatch.setattr(gateway, "_transport", transport)
    response = gateway.get_class_risk("LAW101")
    assert [row["student_id"] for row in response["items"]] == ["SV1"]
    assert response["total"] is None


# ------------------------------------------------------------------ audit 17/11/2026: đồng bộ thành viên
def _members(workspace):
    return [r for r in workspace["records"] if r["path"].endswith("/members")]


def test_member_is_synced_once_not_on_every_call(workspace, monkeypatch):
    for _ in range(3):
        gateway.get_predictions("LAW101")
    assert len(_members(workspace)) == 1                     # trước đây: 3 JWT admin, 3 lần POST /members
    monkeypatch.setattr(gateway.time, "monotonic", lambda real=gateway.time.monotonic: real() + gateway.MEMBER_SYNC_TTL_S + 1)
    gateway.get_predictions("LAW101")
    assert len(_members(workspace)) == 2                     # hết hạn thì đồng bộ lại


def test_unenroll_sends_inactive_member_and_forgets_cache(workspace, monkeypatch):
    from dss.services import auth_service
    monkeypatch.setattr(auth_service, "_load_users", lambda: {"student": {"student_id": "SV1"}, "x": {"student_id": "SV9"}})
    gateway.get_predictions("LAW101")
    workspace["records"].clear()
    classes.unenroll_student(workspace["admin"], workspace["classroom"]["id"], "SV1")
    sent = _members(workspace)
    assert [m["payload"] for m in sent] == [dict(principal_id="student", role="student", student_id="SV1", active=False)]
    assert not gateway._member_synced
    with pytest.raises(PermissionError):                     # quyền cục bộ đã bị thu hồi
        gateway.get_predictions("LAW101")


def test_revoke_teacher_sends_inactive_only_when_no_other_class_of_the_course(workspace, monkeypatch):
    admin, teacher = workspace["admin"], workspace["teacher"]
    other = classes.create_class(admin, "LAW02", "LAW101", "Foundations B", "2026")
    classes.assign_teacher(admin, other["id"], teacher.username)
    workspace["records"].clear()
    classes.revoke_teacher(admin, workspace["classroom"]["id"], teacher.username)
    assert _members(workspace) == []                         # vẫn dạy LAW101 ở lớp LAW02
    classes.revoke_teacher(admin, other["id"], teacher.username)
    assert [m["payload"]["active"] for m in _members(workspace)] == [False]
    assert _members(workspace)[0]["payload"]["principal_id"] == "teacher"


def test_engine_outage_never_blocks_local_revocation(workspace, monkeypatch):
    def down(*args, **kwargs):
        raise gateway.EngineUnavailable("down")
    monkeypatch.setattr(gateway, "_transport", down)
    out = classes.revoke_teacher(workspace["admin"], workspace["classroom"]["id"], "teacher")
    assert out["active"] is False
