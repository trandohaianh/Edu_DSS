"""Validated learning observations. Missing or invalid measurements remain unknown.

Academic and topic scores use 0..10; accuracy/mastery/retention use 0..1.
Zero is an observation, never a missing-value sentinel. Numeric defaults are
None so downstream advice cannot silently turn absent logs into evidence.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional


def observed_number(
    value: Any, *, minimum: float = 0.0, maximum: Optional[float] = None, integer: bool = False
) -> Optional[float]:
    """Return a finite, in-range observation; reject booleans and coercion errors."""
    if value is None or isinstance(value, bool) or type(value).__name__ == "bool_":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    if integer:
        return int(number) if number.is_integer() else None
    return number


def observed_mapping(value: Any, *, maximum: float) -> Dict[str, float]:
    # CSV imports carry JSON objects as strings; parse only JSON, never eval.
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return {}
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, raw in value.items():
        number = observed_number(raw, maximum=maximum)
        if isinstance(key, str) and key.strip() and number is not None:
            result[key.strip()] = number
    return result


def _text_list(value: Any) -> List[str]:
    return [item.strip() for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


@dataclass
class AcademicEvidence:
    quiz_average: Optional[float] = None
    assignment_average: Optional[float] = None
    exam_score: Optional[float] = None
    topic_scores: Dict[str, float] = field(default_factory=dict)
    prerequisite_mastery: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("quiz_average", "assignment_average", "exam_score"):
            setattr(self, name, observed_number(getattr(self, name), maximum=10.0))
        self.topic_scores = observed_mapping(self.topic_scores, maximum=10.0)
        self.prerequisite_mastery = observed_mapping(self.prerequisite_mastery, maximum=1.0)


@dataclass
class QuestionLevelEvidence:
    accuracy_rate: Optional[float] = None
    average_response_time_seconds: Optional[float] = None
    attempt_count_per_question: Optional[float] = None
    hint_requests_count: Optional[int] = None
    skipped_questions_count: Optional[int] = None
    repeated_error_patterns: List[str] = field(default_factory=list)
    subskill_mastery: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.accuracy_rate = observed_number(self.accuracy_rate, maximum=1.0)
        for name in ("average_response_time_seconds", "attempt_count_per_question"):
            setattr(self, name, observed_number(getattr(self, name)))
        for name in ("hint_requests_count", "skipped_questions_count"):
            setattr(self, name, observed_number(getattr(self, name), integer=True))
        self.repeated_error_patterns = _text_list(self.repeated_error_patterns)
        self.subskill_mastery = observed_mapping(self.subskill_mastery, maximum=1.0)


@dataclass
class BehavioralEvidence:
    active_days_last_month: Optional[int] = None
    login_frequency_per_week: Optional[float] = None
    average_session_duration_minutes: Optional[float] = None
    material_views_count: Optional[int] = None
    video_completion_rate: Optional[float] = None
    practice_frequency_per_week: Optional[float] = None
    submission_lateness_count: Optional[int] = None

    def __post_init__(self) -> None:
        self.active_days_last_month = observed_number(self.active_days_last_month, maximum=31, integer=True)
        self.video_completion_rate = observed_number(self.video_completion_rate, maximum=1.0)
        for name in ("login_frequency_per_week", "average_session_duration_minutes", "practice_frequency_per_week"):
            setattr(self, name, observed_number(getattr(self, name)))
        for name in ("material_views_count", "submission_lateness_count"):
            setattr(self, name, observed_number(getattr(self, name), integer=True))


@dataclass
class LearningTrajectory:
    learning_velocity: Optional[float] = None
    time_to_mastery_hours: Optional[float] = None
    delayed_retention_rate: Optional[float] = None
    repeated_misconceptions: List[str] = field(default_factory=list)
    historical_baseline_score: Optional[float] = None
    score_trend: Optional[str] = None

    def __post_init__(self) -> None:
        self.learning_velocity = observed_number(self.learning_velocity)
        if self.learning_velocity == 0:
            self.learning_velocity = None
        self.time_to_mastery_hours = observed_number(self.time_to_mastery_hours)
        self.delayed_retention_rate = observed_number(self.delayed_retention_rate, maximum=1.0)
        self.historical_baseline_score = observed_number(self.historical_baseline_score, maximum=10.0)
        self.repeated_misconceptions = _text_list(self.repeated_misconceptions)
        if self.score_trend not in ("improving", "stable", "declining"):
            self.score_trend = None


@dataclass
class StudentLearningProfile:
    student_pseudonym: str
    course_id: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    academic: AcademicEvidence = field(default_factory=AcademicEvidence)
    question_level: QuestionLevelEvidence = field(default_factory=QuestionLevelEvidence)
    behavioral: BehavioralEvidence = field(default_factory=BehavioralEvidence)
    trajectory: LearningTrajectory = field(default_factory=LearningTrajectory)
    secondary_class_context: Dict[str, float] = field(default_factory=dict)
    # Canonical metric path -> input field name; never store raw PII or values.
    evidence_sources: Dict[str, str] = field(default_factory=dict)
    invalid_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def build_from_lms_records(
        cls,
        student_id: str,
        course_id: str,
        raw_lms_data: Dict[str, Any],
        class_averages: Optional[Dict[str, float]] = None,
    ) -> StudentLearningProfile:
        from dss.services.privacy_service import privacy_service

        raw = raw_lms_data if isinstance(raw_lms_data, dict) else {}
        sources: Dict[str, str] = {}
        invalid: List[str] = []

        def read(path, *keys, maximum=None, integer=False):
            for key in keys:
                if key not in raw or raw[key] is None:
                    continue
                value = observed_number(raw[key], maximum=maximum, integer=integer)
                if value is None:
                    invalid.append(path)
                else:
                    sources[path] = key
                return value
            return None

        def mapping(path, maximum):
            result = observed_mapping(raw.get(path), maximum=maximum)
            if path in raw:
                original = raw[path]
                if isinstance(original, str):
                    try:
                        original = json.loads(original)
                    except (ValueError, TypeError):
                        original = None
                if not isinstance(original, dict) or len(result) != len(original):
                    invalid.append(path)
                if result:
                    sources[path] = path
            return result

        academic = AcademicEvidence(
            quiz_average=read("academic.quiz_average", "quiz_score", "quiz_average", maximum=10),
            assignment_average=read(
                "academic.assignment_average", "assignment_score", "assignment_average", maximum=10
            ),
            exam_score=read("academic.exam_score", "exam_score", "diem_cuoi_ky", maximum=10),
            topic_scores=mapping("topic_scores", 10),
            prerequisite_mastery=mapping("prerequisite_mastery", 1),
        )
        question = QuestionLevelEvidence(
            accuracy_rate=read("question_level.accuracy_rate", "accuracy_rate", maximum=1),
            average_response_time_seconds=read("question_level.average_response_time_seconds", "avg_response_time"),
            attempt_count_per_question=read("question_level.attempt_count_per_question", "attempt_count"),
            hint_requests_count=read("question_level.hint_requests_count", "hint_count", integer=True),
            skipped_questions_count=read("question_level.skipped_questions_count", "skipped_count", integer=True),
            repeated_error_patterns=_text_list(raw.get("repeated_errors")),
            subskill_mastery=mapping("subskill_mastery", 1),
        )
        behavior = BehavioralEvidence(
            active_days_last_month=read("behavioral.active_days_last_month", "active_days", maximum=31, integer=True),
            login_frequency_per_week=read("behavioral.login_frequency_per_week", "login_freq"),
            average_session_duration_minutes=read("behavioral.average_session_duration_minutes", "session_duration"),
            material_views_count=read("behavioral.material_views_count", "material_views", integer=True),
            video_completion_rate=read("behavioral.video_completion_rate", "video_completion", maximum=1),
            practice_frequency_per_week=read("behavioral.practice_frequency_per_week", "practice_freq"),
            submission_lateness_count=read("behavioral.submission_lateness_count", "lateness_count", integer=True),
        )
        velocity = read("trajectory.learning_velocity", "learning_velocity")
        if velocity == 0:
            invalid.append("trajectory.learning_velocity")
            sources.pop("trajectory.learning_velocity", None)
            velocity = None
        trajectory = LearningTrajectory(
            learning_velocity=velocity,
            time_to_mastery_hours=read("trajectory.time_to_mastery_hours", "time_to_mastery"),
            delayed_retention_rate=read("trajectory.delayed_retention_rate", "retention_rate", maximum=1),
            repeated_misconceptions=_text_list(raw.get("misconceptions")),
            historical_baseline_score=read(
                "trajectory.historical_baseline_score", "gpa_previous", "baseline_score", maximum=10
            ),
            # No invented stable trend or assumed course grading weights.
            score_trend=raw.get("score_trend"),
        )
        return cls(
            student_pseudonym=privacy_service.generate_pseudonym(str(student_id)),
            course_id=str(course_id),
            academic=academic,
            question_level=question,
            behavioral=behavior,
            trajectory=trajectory,
            secondary_class_context=observed_mapping(class_averages, maximum=float("inf")),
            evidence_sources=sources,
            invalid_fields=list(dict.fromkeys(invalid)),
        )
