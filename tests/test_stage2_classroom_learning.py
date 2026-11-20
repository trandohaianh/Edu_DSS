"""Executable Stage 2 evidence, ownership, immutable versions and concurrency checks."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from sqlalchemy import func, select

from dss.platform.context import Actor
from dss.platform.models import Attempt, ClassPlan, School
from dss.platform.store import platform_session, reset_platform_engines
from dss.services import classroom_learning_service as learning
from dss.services import classroom_service as classes
from dss.services.learning_plan import learning_plan_generator


@pytest.fixture
def context(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUDSS_ENV", "test")
    monkeypatch.setenv("EDUDSS_MODE", "DEMO_SYNTHETIC")
    monkeypatch.setenv("EDUDSS_PLATFORM_STORE", "local")
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", "1")
    monkeypatch.setenv("EDUDSS_REQUIRE_PROGRAM_ALLOCATION", "0")
    reset_platform_engines()
    admin = Actor("1", "admin", "Admin")
    teacher = Actor("1", "teacher", "Giảng viên / CVHT")
    student = Actor("1", "student", "Sinh viên", "SV1")
    other = Actor("1", "student2", "Sinh viên", "SV2")
    classroom = classes.create_class(admin, "LAW01", "LAW101", "Foundations", "2026")
    classes.assign_teacher(admin, classroom["id"], teacher.username)
    for actor in (student, other):
        classes.enroll_student(admin, classroom["id"], actor.student_id)
    monkeypatch.setattr(learning, "_load_resources", lambda actor, course_id: [])
    yield {"admin": admin, "teacher": teacher, "student": student, "other": other, "class": classroom}
    reset_platform_engines()


@pytest.fixture
def questions():
    return [
        {"question_id": "Q1", "topic_id": "sources", "text": "Teacher approved question 1",
         "options": ["Option A", "Option B"], "correct_answer_index": 0,
         "explanation": "Approved explanation 1"},
        {"question_id": "Q2", "topic_id": "cases", "text": "Teacher approved question 2",
         "options": ["Option A", "Option B"], "correct_answer_index": 1,
         "explanation": "Approved explanation 2"},
    ]


def publish(context, questions, *, maximum=3):
    draft = learning.create_assessment(context["teacher"], context["class"]["id"], "Assessment", questions,
                                       max_attempts=maximum)
    return learning.publish_assessment(context["teacher"], draft["id"])


def submit(context, assessment, answers=None, key="first", **kwargs):
    return learning.submit_attempt(context["student"], assessment["id"],
                                   [1, 0] if answers is None else answers, key, **kwargs)


def test_drafts_and_answer_keys_are_staff_only(context, questions):
    draft = learning.create_assessment(context["teacher"], context["class"]["id"], "Assessment", questions)
    assert learning.list_assessments(context["student"], context["class"]["id"]) == []
    with pytest.raises(PermissionError):
        learning.get_assessment(context["student"], draft["id"])
    learning.publish_assessment(context["teacher"], draft["id"])
    for dto in [learning.get_assessment(context["student"], draft["id"]),
                learning.list_assessments(context["student"], context["class"]["id"])[0]]:
        assert dto["question_count"] == 2
        assert dto["questions"][0]["options"] == questions[0]["options"]
        assert "correct_answer_index" not in dto["questions"][0]
        assert "explanation" not in dto["questions"][0]
    assert learning.get_assessment(context["teacher"], draft["id"])["questions"] == questions
    with pytest.raises(PermissionError):
        learning.create_assessment(context["student"], context["class"]["id"], "Not staff", questions)


def test_cross_school_and_unassigned_teacher_cannot_read_or_mutate(context, questions):
    assessment = publish(context, questions)
    outsider = Actor("1", "unassigned", "Giảng viên / CVHT")
    foreign = Actor("2", "admin", "Admin")
    operator = Actor("1", "operator", "Platform Admin")
    for actor in (outsider, foreign, operator):
        with pytest.raises(PermissionError):
            learning.list_assessments(actor, context["class"]["id"])
        with pytest.raises(PermissionError):
            learning.get_assessment(actor, assessment["id"])
        with pytest.raises(PermissionError):
            learning.publish_assessment(actor, assessment["id"])
        with pytest.raises(PermissionError):
            learning.get_class_progress(actor, context["class"]["id"])


def test_score_zero_is_measured_and_missing_behavior_does_not_become_a_schedule(context, questions):
    assessment = publish(context, questions)
    result = submit(context, assessment)
    attempt, record = result["attempt"], result["plan"]
    assert (attempt["score"], attempt["correct_count"], attempt["total_count"]) == (0, 0, 2)
    assert attempt["topic_scores"] == {"sources": 0, "cases": 0}
    assert attempt["response_times"] is None
    plan = record["plan"]
    assert plan["source_attempt_id"] == attempt["id"]
    assert plan["source_assessment"]["version"] == 1
    assert plan["course_id"] == context["class"]["course_id"]
    assert sorted(plan["priority_topics"]) == ["cases", "sources"]
    assert all(activity["duration_minutes"] is None and activity["frequency_per_week"] is None
               and activity["approved_resource_ids"] == [] for activity in plan["activities"])
    assert not plan["success_metrics"]
    assert not any("behavioral" in key or "trajectory" in key for key in plan["evidence_sources"])
    assert all(attempt["id"] in source for source in plan["evidence_sources"].values())


def test_retest_retains_prior_plan_and_completion_only_changes_selected_version(context, questions):
    assessment = publish(context, questions)
    first = submit(context, assessment)
    assert learning.set_plan_activity_completed(context["student"], first["plan"]["id"], 0, True)["completion"] == {"0": True}
    second = submit(context, assessment, [0, 1], "retest")
    assert second["attempt"]["score"] == 10
    assert second["plan"]["version"] == 2
    assert second["plan"]["completion"] == {}
    history = learning.list_my_plans(context["student"], context["class"]["id"])
    assert [item["version"] for item in history] == [2, 1]
    assert history[1]["plan"] == first["plan"]["plan"]
    assert history[1]["completion"] == {"0": True}
    assert learning.get_my_plan(context["student"], context["class"]["id"]) == second["plan"]
    reset_platform_engines()
    assert learning.list_my_plans(context["student"], context["class"]["id"])[1]["completion"] == {"0": True}


def test_revision_preserves_published_snapshot_and_previous_evidence(context, questions):
    assessment = publish(context, questions)
    first = submit(context, assessment)
    changed = deepcopy(questions)
    changed[0]["text"] = "Revised question"
    with pytest.raises(ValueError, match="immutable"):
        learning.update_assessment_draft(context["teacher"], assessment["id"], changed)
    revision = learning.revise_assessment(context["teacher"], assessment["id"], changed)
    assert revision["version"] == 2 and revision["status"] == "draft"
    assert learning.revise_assessment(context["teacher"], assessment["id"], changed)["id"] == revision["id"]
    assert learning.get_assessment(context["teacher"], assessment["id"])["questions"] == questions
    learning.publish_assessment(context["teacher"], revision["id"])
    assert learning.get_assessment(context["teacher"], assessment["id"])["status"] == "closed"
    assert submit(context, assessment) == first
    with pytest.raises(ValueError, match="published"):
        submit(context, assessment, key="new-after-close")
    second = submit(context, revision, [0, 1], "revised")
    assert second["plan"]["plan"]["source_assessment"]["version"] == 2
    assert learning.list_my_plans(context["student"], context["class"]["id"])[1]["plan"]["source_assessment"]["version"] == 1


def test_submission_idempotency_requires_identical_assessment_answers_and_times(context, questions):
    assessment = publish(context, questions)
    first = submit(context, assessment, response_times=[0, 2])
    assert submit(context, assessment, response_times=[0, 2]) == first
    with pytest.raises(ValueError, match="different response"):
        submit(context, assessment, [0, 1], response_times=[0, 2])
    with pytest.raises(ValueError, match="different response"):
        submit(context, assessment, response_times=[0, 3])
    another = publish(context, questions)
    with pytest.raises(ValueError, match="different response"):
        submit(context, another, response_times=[0, 2])
    assert len(learning.list_my_attempts(context["student"], context["class"]["id"])) == 1


@pytest.mark.parametrize("same_key", [False, True])
def test_concurrent_requests_cannot_exceed_attempt_quota_or_duplicate_plan(context, questions, same_key):
    assessment = publish(context, questions, maximum=1)
    def run(index):
        try:
            return submit(context, assessment, key="same" if same_key else f"request-{index}")
        except ValueError as error:
            return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(run, range(2)))
    successful = [response for response in responses if isinstance(response, dict)]
    assert len(successful) == (2 if same_key else 1)
    if same_key:
        assert successful[0] == successful[1]
    else:
        assert "maximum" in str(next(item for item in responses if isinstance(item, ValueError)))
    assert len(learning.list_my_attempts(context["student"], context["class"]["id"])) == 1
    assert len(learning.list_my_plans(context["student"], context["class"]["id"])) == 1


def test_failed_plan_generation_rolls_back_attempt_and_version(context, questions, monkeypatch):
    assessment = publish(context, questions)
    original = learning_plan_generator.generate_plan
    def fail(*args, **kwargs):
        raise RuntimeError("plan failure")
    monkeypatch.setattr(learning_plan_generator, "generate_plan", fail)
    with pytest.raises(RuntimeError, match="plan failure"):
        submit(context, assessment)
    assert learning.list_my_attempts(context["student"], context["class"]["id"]) == []
    assert learning.get_my_plan(context["student"], context["class"]["id"]) is None
    with platform_session("1", actor=context["admin"]) as session:
        assert session.scalar(select(func.count(Attempt.id))) == 0
        assert session.scalar(select(func.count(ClassPlan.id))) == 0
    monkeypatch.setattr(learning_plan_generator, "generate_plan", original)
    assert submit(context, assessment)["plan"]["version"] == 1


def test_cms_failures_surface_without_saving_a_misleading_empty_resource_plan(context, questions, monkeypatch):
    assessment = publish(context, questions)
    def fail(*args):
        raise RuntimeError("CMS database unavailable")
    monkeypatch.setattr(learning, "_load_resources", fail)
    with pytest.raises(RuntimeError, match="CMS database"):
        submit(context, assessment)
    assert learning.list_my_attempts(context["student"], context["class"]["id"]) == []


def test_completion_enforces_student_ownership_and_current_enrollment(context, questions):
    assessment = publish(context, questions)
    result = submit(context, assessment)
    for actor in [context["other"], context["teacher"], Actor("2", "student", "Sinh viên", "SV1")]:
        with pytest.raises(PermissionError):
            learning.set_plan_activity_completed(actor, result["plan"]["id"], 0, True)
    assert learning.list_my_plans(context["other"], context["class"]["id"]) == []
    classes.unenroll_student(context["admin"], context["class"]["id"], "SV1")
    for operation in [
        lambda: learning.list_my_attempts(context["student"], context["class"]["id"]),
        lambda: learning.list_my_plans(context["student"], context["class"]["id"]),
        lambda: learning.set_plan_activity_completed(context["student"], result["plan"]["id"], 0, True),
        lambda: submit(context, assessment, key="unenrolled"),
    ]:
        with pytest.raises(PermissionError):
            operation()


def test_revoking_teacher_assignment_removes_assessment_and_progress_access(context, questions):
    assessment = publish(context, questions)
    classes.revoke_teacher(context["admin"], context["class"]["id"], context["teacher"].username)
    with pytest.raises(PermissionError):
        learning.publish_assessment(context["teacher"], assessment["id"])
    with pytest.raises(PermissionError):
        learning.get_class_progress(context["teacher"], context["class"]["id"])


@pytest.mark.parametrize("index,completed", [(-1, True), (True, True), (100, True), (0, 1), (0, "true")])
def test_completion_rejects_invalid_activity_index_or_value(context, questions, index, completed):
    result = submit(context, publish(context, questions))
    with pytest.raises(ValueError):
        learning.set_plan_activity_completed(context["student"], result["plan"]["id"], index, completed)


def test_staff_progress_uses_latest_observations_with_explicit_unknowns(context, questions):
    assessment = publish(context, questions)
    submit(context, assessment)
    progress = learning.get_class_progress(context["teacher"], context["class"]["id"])
    assert (progress["student_count"], progress["assessed_students"], progress["attempt_count"]) == (2, 1, 1)
    measured, unknown = progress["students"]
    assert measured["student_code"] == "SV1" and measured["latest_score"] == 0 and measured["needs_review"]
    assert unknown["student_code"] == "SV2" and unknown["latest_score"] is None and unknown["topic_scores"] == {}
    assert unknown["plan_version"] is None and not unknown["needs_review"]
    assert progress["topic_summary"]["sources"] == {"average_score": 0, "observed_students": 1}
    submit(context, assessment, [0, 1], "second")
    progress = learning.get_class_progress(context["teacher"], context["class"]["id"])
    assert progress["students"][0]["latest_score"] == 10
    assert progress["topic_summary"]["sources"]["average_score"] == 10
    assert progress["attempt_count"] == 2
    with pytest.raises(PermissionError):
        learning.get_class_progress(context["student"], context["class"]["id"])


def test_school_pause_keeps_history_and_existing_progress_but_blocks_new_attempts(context, questions):
    assessment = publish(context, questions)
    saved = submit(context, assessment)
    with platform_session("1", write=True, actor=context["admin"]) as session:
        session.get(School, "1").active = False
    assert submit(context, assessment) == saved
    assert learning.get_my_plan(context["student"], context["class"]["id"])["id"] == saved["plan"]["id"]
    assert learning.set_plan_activity_completed(context["student"], saved["plan"]["id"], 0, True)["completion"]["0"]
    with pytest.raises(PermissionError):
        submit(context, assessment, key="paused")
    with pytest.raises(PermissionError):
        learning.create_assessment(context["teacher"], context["class"]["id"], "Blocked", questions)


@pytest.mark.parametrize("answers,times", [
    ([True, 0], None), ([0], None), ([2, 0], None), ([0, None], None),
    ([0, 1], [-1, 1]), ([0, 1], [float("nan"), 1]), ([0, 1], [float("inf"), 1]),
    ([0, 1], [True, 1]), ([0, 1], [1]),
])
def test_submission_validation_rejects_incomplete_or_invalid_observations(context, questions, answers, times):
    assessment = publish(context, questions)
    with pytest.raises(ValueError):
        learning.submit_attempt(context["student"], assessment["id"], answers, "invalid", response_times=times)
    assert learning.list_my_attempts(context["student"], context["class"]["id"]) == []


def test_zero_response_time_is_retained_as_client_reported_observation(context, questions, monkeypatch):
    assessment = publish(context, questions)
    original = learning_plan_generator.generate_plan
    observed = []
    def capture(profile, *args, **kwargs):
        observed.append(profile)
        return original(profile, *args, **kwargs)
    monkeypatch.setattr(learning_plan_generator, "generate_plan", capture)
    result = submit(context, assessment, response_times=[0, 0])
    assert result["attempt"]["response_times"] == [0, 0]
    assert observed[0].question_level.average_response_time_seconds == 0
    assert "client_reported_timing" in result["plan"]["plan"]["evidence_sources"]["question_level.average_response_time_seconds"]
    assert observed[0].behavioral.practice_frequency_per_week is None
    assert observed[0].trajectory.learning_velocity is None


@pytest.mark.parametrize("change", [
    {"correct_answer_index": True}, {"correct_answer_index": 9}, {"options": ["same", "same"]},
    {"topic_id": ""}, {"text": ""}, {"explanation": 42},
])
def test_teacher_question_validation(context, questions, change):
    questions[0].update(change)
    with pytest.raises(ValueError):
        learning.create_assessment(context["teacher"], context["class"]["id"], "Invalid", questions)


def test_question_ids_and_arbitrary_private_fields_are_validated(context, questions):
    questions[1]["question_id"] = "Q1"
    with pytest.raises(ValueError):
        learning.create_assessment(context["teacher"], context["class"]["id"], "Invalid", questions)
    questions[1]["question_id"] = "Q2"
    questions[0]["hidden_answer"] = "must never persist"
    assessment = publish(context, questions)
    assert "hidden_answer" not in assessment["questions"][0]
    assert "hidden_answer" not in learning.get_assessment(context["student"], assessment["id"])["questions"][0]


def test_two_schools_with_same_student_code_have_independent_evidence_and_pseudonyms(context, questions):
    school2 = dict(context)
    school2["admin"] = Actor("2", "admin", "Admin")
    school2["teacher"] = Actor("2", "teacher", "Giảng viên / CVHT")
    school2["student"] = Actor("2", "student", "Sinh viên", "SV1")
    school2["class"] = classes.create_class(school2["admin"], "LAW01", "LAW101", "Foundations", "2026")
    classes.assign_teacher(school2["admin"], school2["class"]["id"], "teacher")
    classes.enroll_student(school2["admin"], school2["class"]["id"], "SV1")
    first = submit(context, publish(context, questions))
    second = submit(school2, publish(school2, questions), [0, 1])
    assert first["plan"]["version"] == second["plan"]["version"] == 1
    assert first["plan"]["plan"]["student_pseudonym"] != second["plan"]["plan"]["student_pseudonym"]
    with pytest.raises(PermissionError):
        learning.list_my_attempts(context["student"], school2["class"]["id"])
    with pytest.raises(PermissionError):
        learning.set_plan_activity_completed(school2["student"], first["plan"]["id"], 0, True)


def test_plan_only_exposes_school_approved_exact_topic_resources(context, questions, monkeypatch):
    resources = [
        {"resource_id": "cms:sources", "status": "APPROVED", "source_kind": "cms_lesson", "verified_cms": True,
         "course_id": "LAW101", "topic_id": "sources", "title": "Official approved lesson"},
        {"resource_id": "cms:wrong-course", "status": "APPROVED", "source_kind": "cms_lesson", "verified_cms": True,
         "course_id": "LAW999", "topic_id": "cases", "title": "Another course"},
    ]
    monkeypatch.setattr(learning, "_load_resources", lambda actor, course_id: resources)
    plan = submit(context, publish(context, questions))["plan"]["plan"]
    approved = [rid for activity in plan["activities"] for rid in activity["approved_resource_ids"]]
    assert approved == ["cms:sources"]
    assert plan["resource_details"] == {"cms:sources": {"title": "Official approved lesson"}}


def test_progress_retains_latest_evidence_per_topic_when_new_test_is_partial(context, questions):
    first_assessment = publish(context, questions)
    first = submit(context, first_assessment)
    partial = publish(context, [questions[0]])
    second = submit(context, partial, [0], "partial")
    progress = learning.get_class_progress(context["teacher"], context["class"]["id"])["students"][0]
    assert progress["latest_score"] == 10
    assert progress["topic_scores"] == {"sources": 10, "cases": 0}
    assert progress["topic_observations"]["sources"]["attempt_id"] == second["attempt"]["id"]
    assert progress["topic_observations"]["cases"]["attempt_id"] == first["attempt"]["id"]
    assert progress["needs_review"] is True


def test_topic_score_denominator_uses_questions_in_that_topic(context, questions):
    third = deepcopy(questions[0])
    third["question_id"] = "Q3"
    questions.append(third)
    result = submit(context, publish(context, questions), [0, 1, 1])
    assert result["attempt"]["score"] == pytest.approx(6.6667)
    assert result["attempt"]["topic_scores"] == {"sources": 5, "cases": 10}


def test_classroom_plan_excludes_unscoped_global_catalogue(context, questions, monkeypatch):
    from dss.services.resource_catalog import ResourceItem, resource_catalog
    unscoped = ResourceItem(
        resource_id="another-school-resource", title="Another school's lesson",
        type="lms_material", provider="Other School", url="https://other.example/lesson",
        course="LAW101", topic="sources", level="Beginner", language="vi", duration="20",
        verified_at="2026-10-26", reviewed_by="Other Teacher", status="APPROVED",
    )
    monkeypatch.setattr(resource_catalog, "_resources", {unscoped.resource_id: unscoped})
    plan = submit(context, publish(context, questions))["plan"]["plan"]
    assert all(activity["approved_resource_ids"] == [] for activity in plan["activities"])
    assert plan["resource_details"] == {}
    assert all(activity["duration_minutes"] is None for activity in plan["activities"])


def test_cms_lookup_uses_explicit_actor_school_and_preserves_database_errors(monkeypatch):
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", "001")
    calls = []
    def approved(course):
        calls.append(course)
        return [{"resource_id": "same-school"}]
    monkeypatch.setattr(learning, "approved_plan_resources", approved)
    assert learning._load_resources(Actor("2", "student", "Sinh viên", "SV1"), "LAW101") == []
    assert calls == []
    assert learning._load_resources(Actor("1", "student", "Sinh viên", "SV1"), "LAW101") == [{"resource_id": "same-school"}]
    assert calls == ["LAW101"]
    def fail(course):
        raise RuntimeError("database failure")
    monkeypatch.setattr(learning, "approved_plan_resources", fail)
    with pytest.raises(RuntimeError, match="database failure"):
        learning._load_resources(Actor("1", "student", "Sinh viên", "SV1"), "LAW101")


def test_student_projection_omits_private_metadata_added_by_future_schema(context, questions):
    from dss.platform.models import Assessment
    assessment = publish(context, questions)
    with platform_session("1", write=True, actor=context["admin"]) as session:
        row = session.get(Assessment, assessment["id"])
        updated = deepcopy(row.questions)
        updated[0]["private_rubric"] = {"correct_answer": "A", "teacher_notes": "staff-only"}
        row.questions = updated
    dto = learning.get_assessment(context["student"], assessment["id"])
    assert set(dto["questions"][0]) == {"question_id", "topic_id", "text", "options"}


@pytest.fixture
def plan_resource(context, questions, monkeypatch):
    from types import SimpleNamespace
    resource = {
        "resource_id": "cms:lesson-1:doc-1", "status": "APPROVED", "source_kind": "cms_lesson",
        "verified_cms": True, "course_id": "LAW101", "topic_id": "sources",
        "title": "Approved lesson", "lesson_id": "lesson-1", "document_id": "doc-1",
    }
    approved = [resource]
    lesson = learning.cms_lecture_repository.CMSLesson(
        lesson_id="lesson-1", course_id="LAW101", topic_id="sources", lecturer_id="teacher",
        title="Approved lesson", current_document_id="doc-1")
    calls = []
    chunks = [{"document_id": "doc-1", "course_id": "LAW101", "content": "# Approved content\nOfficial text."}]
    def get_chunks(document_id, *, course_id):
        calls.append((document_id, course_id))
        return chunks
    monkeypatch.setattr(learning, "_load_resources", lambda actor, course_id: list(approved))
    monkeypatch.setattr(learning.cms_lecture_repository, "get_lesson", lambda lesson_id: lesson)
    monkeypatch.setattr(learning.vector_store, "get_vector_store",
                        lambda **kwargs: SimpleNamespace(get_document_chunks=get_chunks))
    result = submit(context, publish(context, questions))
    return {"result": result, "approved": approved, "resource": resource, "lesson": lesson,
            "calls": calls, "chunks": chunks}


def test_plan_resource_opens_only_current_approved_content_for_owner_or_assigned_staff(context, plan_resource):
    plan_id, resource_id = plan_resource["result"]["plan"]["id"], plan_resource["resource"]["resource_id"]
    for actor in [context["student"], context["teacher"], context["admin"]]:
        opened = learning.get_plan_resource(actor, plan_id, resource_id)
        assert opened["content"] == "# Approved content\nOfficial text."
        assert opened["kind"] == "cms_lesson"
        assert opened["document_id"] == "doc-1"
    assert plan_resource["calls"] == [("doc-1", "LAW101")] * 3


def test_plan_resource_denies_other_students_foreign_schools_and_unassigned_staff(context, plan_resource):
    plan_id, resource_id = plan_resource["result"]["plan"]["id"], plan_resource["resource"]["resource_id"]
    for actor in [context["other"], Actor("2", "student", "Sinh viên", "SV1"),
                  Actor("1", "outsider", "Giảng viên / CVHT"), Actor("1", "operator", "Platform Admin")]:
        with pytest.raises(PermissionError):
            learning.get_plan_resource(actor, plan_id, resource_id)
    with pytest.raises(PermissionError):
        learning.get_plan_resource(context["student"], plan_id, "not-in-this-plan")
    assert not plan_resource["calls"]


@pytest.mark.parametrize("change", ["revoked", "new-version", "excluded", "unofficial", "wrong-course", "wrong-topic"])
def test_plan_resource_revocation_replacement_or_scope_change_prevents_read(context, plan_resource, change):
    if change == "revoked":
        plan_resource["approved"].clear()
    elif change == "new-version":
        plan_resource["lesson"].current_document_id = "doc-2"
    elif change == "excluded":
        plan_resource["lesson"].excluded_document_ids = ["doc-1"]
    elif change == "unofficial":
        plan_resource["lesson"].official_source = False
    elif change == "wrong-course":
        plan_resource["resource"]["course_id"] = "LAW999"
    else:
        plan_resource["resource"]["topic_id"] = "another-topic"
    with pytest.raises(PermissionError):
        learning.get_plan_resource(context["student"], plan_resource["result"]["plan"]["id"],
                                   plan_resource["resource"]["resource_id"])
    assert not plan_resource["calls"]


def test_plan_resource_does_not_read_another_dedicated_school_store(context, plan_resource, monkeypatch):
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", "2")
    with pytest.raises(PermissionError, match="school"):
        learning.get_plan_resource(context["student"], plan_resource["result"]["plan"]["id"],
                                   plan_resource["resource"]["resource_id"])
    assert not plan_resource["calls"]


def test_plan_resource_read_rechecks_approval_after_content_loading(context, plan_resource, monkeypatch):
    resources = plan_resource["approved"]
    calls = []
    def changing_approval(actor, course_id):
        calls.append(course_id)
        return list(resources) if len(calls) == 1 else []
    monkeypatch.setattr(learning, "_load_resources", changing_approval)
    with pytest.raises(PermissionError, match="changed while opening"):
        learning.get_plan_resource(context["student"], plan_resource["result"]["plan"]["id"],
                                   plan_resource["resource"]["resource_id"])
    assert len(plan_resource["calls"]) == 1


def test_plan_resource_drops_chunks_outside_exact_document_and_course(context, plan_resource):
    plan_resource["chunks"][:] = [
        {"document_id": "doc-foreign", "course_id": "LAW101", "content": "Private document"},
        {"document_id": "doc-1", "course_id": "LAW999", "content": "Private course"},
    ]
    with pytest.raises(LookupError, match="no readable content"):
        learning.get_plan_resource(context["student"], plan_resource["result"]["plan"]["id"],
                                   plan_resource["resource"]["resource_id"])


@pytest.mark.parametrize("url", ["https://example.edu/approved", "http://example.edu/approved"])
def test_external_plan_resource_returns_only_exact_approved_url_without_fetching(context, questions, monkeypatch, url):
    resource = {"resource_id": "approved-external", "course_id": "LAW101", "topic_id": "sources",
                "status": "APPROVED", "title": "Approved link", "url": url}
    monkeypatch.setattr(learning, "_load_resources", lambda actor, course_id: [resource])
    result = submit(context, publish(context, questions))
    opened = learning.get_plan_resource(context["student"], result["plan"]["id"], resource["resource_id"])
    assert opened == {"resource_id": resource["resource_id"], "title": resource["title"], "kind": "external", "url": url}


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///private.txt", "ftp://example.edu/file",
                               "https://user:secret@example.edu/private"])
def test_external_plan_resource_rejects_unsafe_replacement_urls(context, questions, monkeypatch, url):
    resource = {"resource_id": "approved-external", "course_id": "LAW101", "topic_id": "sources",
                "status": "APPROVED", "title": "Approved link", "url": "https://example.edu/approved"}
    monkeypatch.setattr(learning, "_load_resources", lambda actor, course_id: [resource])
    result = submit(context, publish(context, questions))
    resource["url"] = url
    with pytest.raises(PermissionError, match="valid web link"):
        learning.get_plan_resource(context["student"], result["plan"]["id"], resource["resource_id"])
