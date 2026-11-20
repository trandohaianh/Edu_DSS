"""Transactional class assessments, measured results and immutable plan versions."""

from __future__ import annotations

import os
import uuid
from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy import func, select

from dss.platform.context import Actor
from dss.platform.models import Assessment, Attempt, ClassEnrollment, ClassPlan
from dss.platform.store import audit, platform_session
from dss.services import cms_lecture_repository, vector_store
from dss.services.classroom_service import require_class_access, require_school_writes
from dss.services.learning_plan import learning_plan_generator
from dss.services.learning_plan_resources import approved_plan_resources
from dss.services.learning_profile import (
    AcademicEvidence,
    QuestionLevelEvidence,
    StudentLearningProfile,
    observed_number,
)
from dss.services.privacy_service import generate_pseudonym
from dss.services.rag_namespaces import NAMESPACE_STUDENT_LEARNING

STUDENT = "Sinh viên"


def _text(value, field, maximum=128):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum or "\x00" in value:
        raise ValueError(f"{field} must be nonempty and at most {maximum} characters.")
    return value.strip()


def _limit(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
        raise ValueError("max_attempts must be an integer from 1 to 100.")
    return value


def _questions(questions):
    """Teachers approve complete MCQ snapshots; arbitrary input keys never reach learners."""
    if not isinstance(questions, list) or not 1 <= len(questions) <= 100:
        raise ValueError("An assessment needs 1 to 100 approved questions.")
    result, seen = [], set()
    for item in questions:
        if not isinstance(item, dict):
            raise ValueError("Each question must be an object.")
        qid = _text(item.get("question_id"), "question_id")
        if qid in seen:
            raise ValueError("question_id must be unique within an assessment.")
        seen.add(qid)
        options = item.get("options")
        if not isinstance(options, list) or not 2 <= len(options) <= 8:
            raise ValueError("Each question needs 2 to 8 options.")
        options = [_text(option, "option", 4000) for option in options]
        if len(set(options)) != len(options):
            raise ValueError("Question options must be distinct.")
        answer = item.get("correct_answer_index")
        if isinstance(answer, bool) or not isinstance(answer, int) or not 0 <= answer < len(options):
            raise ValueError("correct_answer_index must identify an option.")
        explanation = item.get("explanation", "")
        if not isinstance(explanation, str) or len(explanation) > 10000 or "\x00" in explanation:
            raise ValueError("explanation must be text of at most 10000 characters.")
        result.append(
            {
                "question_id": qid,
                "topic_id": _text(item.get("topic_id"), "topic_id"),
                "text": _text(item.get("text"), "question text", 10000),
                "options": options,
                "correct_answer_index": answer,
                "explanation": explanation,
            }
        )
    return result


def _iso(value):
    if value is None:
        return None
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value).isoformat()


def _assessment_dict(row, actor):
    questions = deepcopy(row.questions)
    if actor.role == STUDENT:
        questions = [
            {key: value for key, value in item.items() if key in {"question_id", "topic_id", "text", "options"}}
            for item in questions
        ]
    return {
        "id": row.id,
        "class_id": row.class_id,
        "family_id": row.family_id,
        "version": row.version,
        "title": row.title,
        "status": row.status,
        "max_attempts": row.max_attempts,
        "created_at": _iso(row.created_at),
        "published_at": _iso(row.published_at),
        "question_count": len(questions),
        "questions": questions,
    }


def _assessment(session, actor, assessment_id, *, staff=False):
    row = session.get(Assessment, str(assessment_id))
    if row is None or row.school_id != actor.school_id:
        raise PermissionError("Assessment access is unavailable.")
    classroom = require_class_access(session, actor, row.class_id, staff=staff)
    if actor.role == STUDENT and row.status == "draft":
        raise PermissionError("Assessment access is unavailable.")
    return row, classroom


def _writable(session, actor, classroom):
    require_school_writes(session, actor)
    if classroom.status != "active":
        raise PermissionError("This class is closed for new learning operations.")


def _student(actor):
    if actor.role != STUDENT or not actor.student_id:
        raise PermissionError("An enrolled student is required.")


def create_assessment(actor: Actor, class_id: str, title: str, questions: list, max_attempts: int = 3):
    title, questions, maximum = _text(title, "title", 255), _questions(questions), _limit(max_attempts)
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        classroom = require_class_access(session, actor, class_id, staff=True)
        _writable(session, actor, classroom)
        row = Assessment(
            school_id=actor.school_id, class_id=classroom.id, title=title, questions=questions, max_attempts=maximum
        )
        session.add(row)
        session.flush()
        audit(session, actor, "assessment.created", row.id, school_id=actor.school_id)
        return _assessment_dict(row, actor)


def update_assessment_draft(
    actor: Actor, assessment_id: str, questions: list, *, title: str | None = None, max_attempts: int | None = None
):
    questions = _questions(questions)
    if title is not None:
        title = _text(title, "title", 255)
    if max_attempts is not None:
        max_attempts = _limit(max_attempts)
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        row, classroom = _assessment(session, actor, assessment_id, staff=True)
        _writable(session, actor, classroom)
        if row.status != "draft":
            raise ValueError("Published questions are immutable; create a new version.")
        row.questions = questions
        if title is not None:
            row.title = title
        if max_attempts is not None:
            row.max_attempts = max_attempts
        audit(session, actor, "assessment.draft_updated", row.id, school_id=actor.school_id)
        return _assessment_dict(row, actor)


def publish_assessment(actor: Actor, assessment_id: str):
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        row, classroom = _assessment(session, actor, assessment_id, staff=True)
        _writable(session, actor, classroom)
        if row.status == "published":
            return _assessment_dict(row, actor)
        if row.status != "draft":
            raise ValueError("A closed assessment cannot be republished; create a new version.")
        _questions(row.questions)
        earlier = session.scalars(
            select(Assessment).where(
                Assessment.school_id == actor.school_id,
                Assessment.class_id == row.class_id,
                Assessment.family_id == row.family_id,
                Assessment.status == "published",
            )
        ).all()
        for old in earlier:
            old.status = "closed"
        row.status, row.published_at = "published", datetime.now(UTC)
        audit(session, actor, "assessment.published", row.id, school_id=actor.school_id)
        return _assessment_dict(row, actor)


def close_assessment(actor: Actor, assessment_id: str):
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        row, classroom = _assessment(session, actor, assessment_id, staff=True)
        _writable(session, actor, classroom)
        if row.status == "draft":
            raise ValueError("Only a published assessment can be closed.")
        if row.status != "closed":
            row.status = "closed"
            audit(session, actor, "assessment.closed", row.id, school_id=actor.school_id)
        return _assessment_dict(row, actor)


def revise_assessment(actor: Actor, assessment_id: str, questions: list):
    questions = _questions(questions)
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        row, classroom = _assessment(session, actor, assessment_id, staff=True)
        _writable(session, actor, classroom)
        if row.status == "draft":
            raise ValueError("Update the existing draft before publishing it.")
        family = select(Assessment).where(
            Assessment.school_id == actor.school_id,
            Assessment.class_id == row.class_id,
            Assessment.family_id == row.family_id,
        )
        draft = session.scalar(family.where(Assessment.status == "draft"))
        if draft is not None:
            if draft.questions != questions:
                raise ValueError("This assessment already has a draft; update that draft.")
            return _assessment_dict(draft, actor)
        version = (
            session.scalar(
                select(func.max(Assessment.version)).where(
                    Assessment.school_id == actor.school_id,
                    Assessment.class_id == row.class_id,
                    Assessment.family_id == row.family_id,
                )
            )
            + 1
        )
        revised = Assessment(
            school_id=actor.school_id,
            class_id=row.class_id,
            family_id=row.family_id,
            version=version,
            title=row.title,
            questions=questions,
            max_attempts=row.max_attempts,
        )
        session.add(revised)
        session.flush()
        audit(
            session,
            actor,
            "assessment.revised",
            revised.id,
            school_id=actor.school_id,
            details={"previous_assessment_id": row.id},
        )
        return _assessment_dict(revised, actor)


def list_assessments(actor: Actor, class_id: str):
    with platform_session(actor.school_id, actor=actor) as session:
        require_class_access(session, actor, class_id)
        query = select(Assessment).where(Assessment.school_id == actor.school_id, Assessment.class_id == class_id)
        if actor.role == STUDENT:
            query = query.where(Assessment.status.in_(["published", "closed"]))
        return [
            _assessment_dict(row, actor)
            for row in session.scalars(query.order_by(Assessment.created_at.desc(), Assessment.version.desc())).all()
        ]


def get_assessment(actor: Actor, assessment_id: str):
    with platform_session(actor.school_id, actor=actor) as session:
        row, _ = _assessment(session, actor, assessment_id)
        return _assessment_dict(row, actor)


def _answers(questions, answers, response_times):
    if not isinstance(answers, list) or len(answers) != len(questions):
        raise ValueError("Provide one answer for every question.")
    for question, answer in zip(questions, answers):
        if isinstance(answer, bool) or not isinstance(answer, int) or not 0 <= answer < len(question["options"]):
            raise ValueError("Each answer must be a valid option index.")
    if response_times is not None:
        if not isinstance(response_times, list) or len(response_times) != len(questions):
            raise ValueError("response_times must match the question count.")
        values = [observed_number(value, maximum=86400) for value in response_times]
        if any(value is None for value in values):
            raise ValueError("response_times must contain finite, nonnegative seconds.")
        response_times = values
    return list(answers), response_times


def _attempt_dict(row):
    return {
        "id": row.id,
        "class_id": row.class_id,
        "assessment_id": row.assessment_id,
        "student_code": row.student_code,
        "score": row.score,
        "correct_count": row.correct_count,
        "total_count": row.total_count,
        "topic_scores": deepcopy(row.topic_scores),
        "submitted_at": _iso(row.submitted_at),
        "answers": list(row.answers),
        "response_times": deepcopy(row.response_times),
    }


def _plan_dict(row):
    return {
        "id": row.id,
        "class_id": row.class_id,
        "student_code": row.student_code,
        "attempt_id": row.attempt_id,
        "version": row.version,
        "created_at": _iso(row.created_at),
        "plan": deepcopy(row.plan),
        "completion": deepcopy(row.completion),
    }


def _prior_submission(session, actor, assessment, answers, times, key):
    attempt = session.scalar(
        select(Attempt).where(
            Attempt.school_id == actor.school_id,
            Attempt.class_id == assessment.class_id,
            Attempt.student_code == actor.student_id,
            Attempt.submission_key == key,
        )
    )
    if attempt is None:
        return None
    if attempt.assessment_id != assessment.id or attempt.answers != answers or attempt.response_times != times:
        raise ValueError("This submission_key already identifies a different response.")
    plan = session.scalar(
        select(ClassPlan).where(
            ClassPlan.school_id == actor.school_id,
            ClassPlan.attempt_id == attempt.id,
        )
    )
    if plan is None:
        raise RuntimeError("The saved attempt has no matching learning plan.")
    return {"attempt": _attempt_dict(attempt), "plan": _plan_dict(plan)}


def _load_resources(actor, course_id):
    # The legacy CMS is server-dedicated. Never resolve it under another Actor's school.
    server_school = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip() or "demo"
    if server_school.isdecimal():
        server_school = str(int(server_school))
    return approved_plan_resources(course_id) if server_school == actor.school_id else []


def _build_plan(actor, classroom, assessment, attempt, version, resources):
    sources = {
        "academic.quiz_average": f"attempt:{attempt.id}:score",
        "academic.topic_scores": f"attempt:{attempt.id}:topic_scores",
        "question_level.accuracy_rate": f"attempt:{attempt.id}:correct_count/total_count",
    }
    mean_time = None
    if attempt.response_times is not None:
        mean_time = sum(attempt.response_times) / attempt.total_count
        sources["question_level.average_response_time_seconds"] = f"attempt:{attempt.id}:client_reported_timing"
    profile = StudentLearningProfile(
        student_pseudonym=generate_pseudonym(
            actor.student_id, organization_id=(int(actor.school_id) if actor.school_id != "demo" else 0)
        ),
        course_id=classroom.course_id,
        academic=AcademicEvidence(quiz_average=attempt.score, topic_scores=attempt.topic_scores),
        question_level=QuestionLevelEvidence(
            accuracy_rate=attempt.correct_count / attempt.total_count, average_response_time_seconds=mean_time
        ),
        evidence_sources=sources,
    )
    payload = learning_plan_generator.generate_plan(profile, version=version, approved_resources=resources).to_dict()
    # The legacy generator also reads a global demo catalogue. Classroom plans
    # expose only resources approved by this school's CMS.
    allowed = {
        resource["resource_id"] for resource in resources if isinstance(resource, dict) and resource.get("resource_id")
    }
    for activity in payload["activities"]:
        activity["approved_resource_ids"] = [rid for rid in activity["approved_resource_ids"] if rid in allowed]
        if not activity["approved_resource_ids"]:
            activity.update(
                method="Đề nghị giảng viên chọn học liệu và bài đánh giá phù hợp với chủ đề.",
                duration_minutes=None,
                frequency_per_week=None,
            )
    payload["resource_details"] = {
        rid: item for rid, item in payload.get("resource_details", {}).items() if rid in allowed
    }
    payload.update(
        plan_id=str(uuid.uuid4()),
        class_id=classroom.id,
        source_attempt_id=attempt.id,
        source_assessment={
            "id": assessment.id,
            "family_id": assessment.family_id,
            "version": assessment.version,
            "title": assessment.title,
        },
        evidence_sources=sources,
    )
    return payload


def submit_attempt(actor: Actor, assessment_id: str, answers: list, submission_key: str, response_times=None):
    _student(actor)
    key = _text(submission_key, "submission_key")
    # Read school-scoped CMS resources before taking the school write lock.
    with platform_session(actor.school_id, actor=actor) as session:
        assessment, classroom = _assessment(session, actor, assessment_id)
        answers, times = _answers(assessment.questions, answers, response_times)
        saved = _prior_submission(session, actor, assessment, answers, times, key)
        if saved is not None:
            return saved
        if assessment.status != "published":
            raise ValueError("Only published assessments accept new attempts.")
        if classroom.status != "active":
            raise PermissionError("This class is closed for new learning operations.")
        snapshot = deepcopy(assessment.questions)
        course_id = classroom.course_id
    resources = _load_resources(actor, course_id)
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        assessment, classroom = _assessment(session, actor, assessment_id)
        saved = _prior_submission(session, actor, assessment, answers, times, key)
        if saved is not None:
            return saved
        _writable(session, actor, classroom)
        if assessment.status != "published" or assessment.questions != snapshot or classroom.course_id != course_id:
            raise ValueError("The assessment changed; reload it before submitting.")
        count = session.scalar(
            select(func.count(Attempt.id)).where(
                Attempt.school_id == actor.school_id,
                Attempt.class_id == classroom.id,
                Attempt.assessment_id == assessment.id,
                Attempt.student_code == actor.student_id,
            )
        )
        if count >= assessment.max_attempts:
            raise ValueError("The maximum number of attempts has been reached.")
        correct, topics = 0, defaultdict(lambda: [0, 0])
        for question, answer in zip(assessment.questions, answers):
            hit = int(answer == question["correct_answer_index"])
            correct += hit
            topics[question["topic_id"]][0] += hit
            topics[question["topic_id"]][1] += 1
        total = len(answers)
        attempt = Attempt(
            school_id=actor.school_id,
            class_id=classroom.id,
            assessment_id=assessment.id,
            student_code=actor.student_id,
            submission_key=key,
            answers=answers,
            response_times=times,
            score=round(correct / total * 10, 4),
            correct_count=correct,
            total_count=total,
            topic_scores={topic: round(hit / size * 10, 4) for topic, (hit, size) in topics.items()},
        )
        session.add(attempt)
        session.flush()
        version = (
            session.scalar(
                select(func.max(ClassPlan.version)).where(
                    ClassPlan.school_id == actor.school_id,
                    ClassPlan.class_id == classroom.id,
                    ClassPlan.student_code == actor.student_id,
                )
            )
            or 0
        ) + 1
        payload = _build_plan(actor, classroom, assessment, attempt, version, resources)
        plan = ClassPlan(
            id=payload["plan_id"],
            school_id=actor.school_id,
            class_id=classroom.id,
            student_code=actor.student_id,
            attempt_id=attempt.id,
            version=version,
            plan=payload,
            completion={},
        )
        session.add(plan)
        session.flush()
        audit(
            session,
            actor,
            "attempt.submitted",
            attempt.id,
            school_id=actor.school_id,
            details={"class_id": classroom.id, "assessment_id": assessment.id, "plan_id": plan.id},
        )
        return {"attempt": _attempt_dict(attempt), "plan": _plan_dict(plan)}


def list_my_attempts(actor: Actor, class_id: str):
    _student(actor)
    with platform_session(actor.school_id, actor=actor) as session:
        require_class_access(session, actor, class_id)
        return [
            _attempt_dict(row)
            for row in session.scalars(
                select(Attempt)
                .where(
                    Attempt.school_id == actor.school_id,
                    Attempt.class_id == class_id,
                    Attempt.student_code == actor.student_id,
                )
                .order_by(Attempt.submitted_at.desc(), Attempt.id.desc())
            ).all()
        ]


def list_my_plans(actor: Actor, class_id: str):
    _student(actor)
    with platform_session(actor.school_id, actor=actor) as session:
        require_class_access(session, actor, class_id)
        return [
            _plan_dict(row)
            for row in session.scalars(
                select(ClassPlan)
                .where(
                    ClassPlan.school_id == actor.school_id,
                    ClassPlan.class_id == class_id,
                    ClassPlan.student_code == actor.student_id,
                )
                .order_by(ClassPlan.version.desc())
            ).all()
        ]


def get_my_plan(actor: Actor, class_id: str):
    plans = list_my_plans(actor, class_id)
    return plans[0] if plans else None


def set_plan_activity_completed(actor: Actor, plan_id: str, index: int, completed: bool):
    _student(actor)
    if isinstance(index, bool) or not isinstance(index, int) or index < 0 or not isinstance(completed, bool):
        raise ValueError("Provide a nonnegative activity index and a boolean completion.")
    with platform_session(actor.school_id, write=True, actor=actor) as session:
        row = session.get(ClassPlan, str(plan_id))
        if row is None or row.school_id != actor.school_id or row.student_code != actor.student_id:
            raise PermissionError("Learning plan access is unavailable.")
        require_class_access(session, actor, row.class_id)
        if index >= len(row.plan.get("activities", [])):
            raise ValueError("Activity index is outside this plan.")
        completion = dict(row.completion)
        if completion.get(str(index)) != completed:
            completion[str(index)] = completed
            row.completion = completion
            audit(
                session,
                actor,
                "plan.activity_completed",
                row.id,
                school_id=actor.school_id,
                details={"activity_index": index, "completed": completed},
            )
        return _plan_dict(row)


def get_class_progress(actor: Actor, class_id: str):
    with platform_session(actor.school_id, actor=actor) as session:
        require_class_access(session, actor, class_id, staff=True)
        roster = session.scalars(
            select(ClassEnrollment.student_code)
            .where(
                ClassEnrollment.school_id == actor.school_id,
                ClassEnrollment.class_id == class_id,
                ClassEnrollment.active.is_(True),
            )
            .order_by(ClassEnrollment.student_code)
        ).all()
        attempts = session.scalars(
            select(Attempt)
            .where(
                Attempt.school_id == actor.school_id,
                Attempt.class_id == class_id,
            )
            .order_by(Attempt.submitted_at.desc(), Attempt.id.desc())
        ).all()
        plans = session.scalars(
            select(ClassPlan)
            .where(
                ClassPlan.school_id == actor.school_id,
                ClassPlan.class_id == class_id,
            )
            .order_by(ClassPlan.version.desc())
        ).all()
        counts, latest, latest_plan = defaultdict(int), {}, {}
        topic_observations = defaultdict(dict)
        for attempt in attempts:
            counts[attempt.student_code] += 1
            latest.setdefault(attempt.student_code, attempt)
            # A new test may cover only some topics. Preserve each other topic's
            # latest actual observation, with its original assessment/date.
            for topic, score in attempt.topic_scores.items():
                topic_observations[attempt.student_code].setdefault(
                    topic,
                    {
                        "score": score,
                        "attempt_id": attempt.id,
                        "assessment_id": attempt.assessment_id,
                        "submitted_at": _iso(attempt.submitted_at),
                    },
                )
        for plan in plans:
            latest_plan.setdefault(plan.student_code, plan)
        students, topic_values = [], defaultdict(list)
        for code in roster:
            attempt, plan = latest.get(code), latest_plan.get(code)
            observations = deepcopy(topic_observations[code])
            scores = {topic: observation["score"] for topic, observation in observations.items()}
            for topic, score in scores.items():
                topic_values[topic].append(score)
            activities = plan.plan.get("activities", []) if plan else []
            students.append(
                {
                    "student_code": code,
                    "attempt_count": counts[code],
                    "latest_score": attempt.score if attempt else None,
                    "topic_scores": scores,
                    "topic_observations": observations,
                    "latest_submitted_at": _iso(attempt.submitted_at) if attempt else None,
                    "plan_version": plan.version if plan else None,
                    "completed_activities": sum(plan.completion.get(str(i)) is True for i in range(len(activities)))
                    if plan
                    else 0,
                    "total_activities": len(activities),
                    "needs_review": any(score < 6 for score in scores.values()),
                }
            )
        return {
            "class_id": class_id,
            "student_count": len(roster),
            "assessed_students": sum(code in latest for code in roster),
            "attempt_count": sum(counts[code] for code in roster),
            "students": students,
            "topic_summary": {
                topic: {"average_score": round(sum(values) / len(values), 4), "observed_students": len(values)}
                for topic, values in sorted(topic_values.items())
            },
        }


def get_plan_resource(actor: Actor, plan_id: str, resource_id: str):
    """Open only a plan's still-approved, current resource, without AI or URL fetching."""
    resource_id = _text(resource_id, "resource_id", 512)
    with platform_session(actor.school_id, actor=actor) as session:
        row = session.get(ClassPlan, str(plan_id))
        if row is None or row.school_id != actor.school_id:
            raise PermissionError("Learning resource access is unavailable.")
        require_class_access(session, actor, row.class_id, staff=actor.role != STUDENT)
        if actor.role == STUDENT and row.student_code != actor.student_id:
            raise PermissionError("Learning resource access is unavailable.")
        plan = deepcopy(row.plan)
        if not any(resource_id in activity.get("approved_resource_ids", []) for activity in plan.get("activities", [])):
            raise PermissionError("This resource does not belong to the selected plan.")
        course_id = plan["course_id"]
        saved_detail = plan.get("resource_details", {}).get(resource_id, {})
    # The approved loader is tenant-scoped; a foreign Actor must never reach
    # legacy dedicated-school CMS metadata, even if they know a resource ID.
    server_school = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip() or "demo"
    if server_school.isdecimal():
        server_school = str(int(server_school))
    if server_school != actor.school_id:
        raise PermissionError("This school's resource store is unavailable.")
    key = lambda value: " ".join(str(value or "").strip().casefold().split())
    topics = {key(topic) for topic in plan.get("priority_topics", [])}
    candidates = [
        item
        for item in _load_resources(actor, course_id)
        if isinstance(item, dict)
        and item.get("resource_id") == resource_id
        and item.get("status") == "APPROVED"
        and key(item.get("course_id") or item.get("course")) == key(course_id)
        and key(item.get("topic_id") or item.get("topic")) in topics
    ]
    if len(candidates) != 1:
        raise PermissionError("This resource is no longer approved for the selected plan.")
    resource = candidates[0]
    title = str(resource.get("title") or resource_id)
    if resource.get("source_kind") != "cms_lesson":
        url = resource.get("url")
        try:
            parsed = urlparse(url) if isinstance(url, str) else None
            safe = (
                parsed is not None
                and parsed.scheme in {"http", "https"}
                and parsed.hostname
                and parsed.username is None
                and parsed.password is None
            )
        except ValueError:
            safe = False
        if not safe:
            raise PermissionError("The approved resource has no valid web link.")
        return {"resource_id": resource_id, "title": title, "kind": "external", "url": url}
    lesson_id, document_id = resource.get("lesson_id"), resource.get("document_id")
    if (
        resource.get("verified_cms") is not True
        or not isinstance(lesson_id, str)
        or not isinstance(document_id, str)
        or saved_detail.get("lesson_id") != lesson_id
        or saved_detail.get("document_id") != document_id
    ):
        raise PermissionError("The approved lesson version no longer matches this plan.")
    lesson = cms_lecture_repository.get_lesson(lesson_id)
    if (
        lesson is None
        or not lesson.official_source
        or lesson.course_id != course_id
        or key(lesson.topic_id) != key(resource.get("topic_id"))
        or lesson.current_document_id != document_id
        or document_id in lesson.excluded_document_ids
    ):
        raise PermissionError("The lesson is no longer available in the approved version.")
    store = vector_store.get_vector_store(namespace=NAMESPACE_STUDENT_LEARNING)
    chunks = store.get_document_chunks(document_id, course_id=course_id)
    content = "\n\n".join(
        chunk["content"]
        for chunk in chunks
        if isinstance(chunk, dict)
        and isinstance(chunk.get("content"), str)
        and chunk.get("document_id") == document_id
        and chunk.get("course_id") == course_id
    )
    if not content.strip():
        raise LookupError("The approved lesson has no readable content.")
    # Recheck governance after the read so replacement/revocation during loading
    # cannot turn an old snapshot into an eligible resource.
    refreshed = _load_resources(actor, course_id)
    if not any(item == resource for item in refreshed):
        raise PermissionError("This resource changed while opening it; reload the plan.")
    return {
        "resource_id": resource_id,
        "title": title,
        "kind": "cms_lesson",
        "lesson_id": lesson_id,
        "document_id": document_id,
        "content": content,
    }
