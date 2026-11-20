"""LMS Database & Relational Persistence Layer cho EduDSS LMS.

Mục 25 Yêu cầu:
- Tuyệt đối không dùng CSV/JSON làm kho lưu trữ chính trong chế độ REAL_LMS.
- Cung cấp schema quan hệ chuẩn hóa (Relational Repositories) cho PostgreSQL/SQLite:
  1. students
  2. courses
  3. enrollments
  4. assessments
  5. question_attempts
  6. lms_events
  7. semester_results
  8. student_mastery
  9. learning_plans
  10. diagnostic_assessments
  11. predictions
  12. interventions
  13. model_registry
  14. llm_usage
  15. audit_logs
  16. knowledge_sources
  17. knowledge_chunks
- Hỗ trợ giao dịch (Transactions), xử lý ghi đồng thời (Concurrent writes),
  và DDL Migrations cho hệ thống sản xuất.
"""

from __future__ import annotations

import sqlite3
import threading
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

LMS_POSTGRESQL_DDL_MIGRATIONS = """
-- EduDSS LMS Production Relational Schema Migration (PostgreSQL + pgvector)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. students
CREATE TABLE IF NOT EXISTS students (
    student_id VARCHAR(64) PRIMARY KEY,
    pseudonym VARCHAR(64) UNIQUE NOT NULL,
    cohort VARCHAR(32),
    major VARCHAR(64),
    academic_status VARCHAR(32) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. courses
CREATE TABLE IF NOT EXISTS courses (
    course_id VARCHAR(64) PRIMARY KEY,
    course_code VARCHAR(32) UNIQUE NOT NULL,
    course_name TEXT NOT NULL,
    credits INT NOT NULL DEFAULT 3,
    department VARCHAR(64),
    semester VARCHAR(32)
);

-- 3. enrollments
CREATE TABLE IF NOT EXISTS enrollments (
    enrollment_id VARCHAR(64) PRIMARY KEY,
    student_id VARCHAR(64) REFERENCES students(student_id) ON DELETE CASCADE,
    course_id VARCHAR(64) REFERENCES courses(course_id) ON DELETE CASCADE,
    enrolled_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(32) DEFAULT 'enrolled'
);

-- 4. assessments
CREATE TABLE IF NOT EXISTS assessments (
    assessment_id VARCHAR(64) PRIMARY KEY,
    course_id VARCHAR(64) REFERENCES courses(course_id),
    title TEXT NOT NULL,
    type VARCHAR(32), -- 'quiz', 'assignment', 'midterm', 'final'
    max_score FLOAT DEFAULT 10.0,
    weight FLOAT DEFAULT 1.0,
    due_date TIMESTAMP WITH TIME ZONE
);

-- 5. question_attempts
CREATE TABLE IF NOT EXISTS question_attempts (
    attempt_id VARCHAR(64) PRIMARY KEY,
    student_id VARCHAR(64) REFERENCES students(student_id),
    assessment_id VARCHAR(64) REFERENCES assessments(assessment_id),
    question_id VARCHAR(64),
    is_correct BOOLEAN NOT NULL,
    response_time_seconds FLOAT,
    attempt_count INT DEFAULT 1,
    hints_used INT DEFAULT 0,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. lms_events
CREATE TABLE IF NOT EXISTS lms_events (
    event_id VARCHAR(64) PRIMARY KEY,
    student_id VARCHAR(64) REFERENCES students(student_id),
    event_type VARCHAR(64) NOT NULL, -- 'login', 'material_view', 'video_watch', 'forum_post'
    payload JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. semester_results
CREATE TABLE IF NOT EXISTS semester_results (
    result_id VARCHAR(64) PRIMARY KEY,
    student_id VARCHAR(64) REFERENCES students(student_id),
    course_id VARCHAR(64) REFERENCES courses(course_id),
    semester VARCHAR(32) NOT NULL,
    gpa FLOAT,
    final_grade VARCHAR(8),
    credits_earned INT
);

-- 8. student_mastery
CREATE TABLE IF NOT EXISTS student_mastery (
    mastery_id VARCHAR(64) PRIMARY KEY,
    student_id VARCHAR(64) REFERENCES students(student_id),
    topic VARCHAR(128) NOT NULL,
    mastery_score FLOAT NOT NULL, -- 0.0 to 1.0
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 9. learning_plans
CREATE TABLE IF NOT EXISTS learning_plans (
    plan_id VARCHAR(64) PRIMARY KEY,
    student_id VARCHAR(64) REFERENCES students(student_id),
    version INT NOT NULL DEFAULT 1,
    plan_data JSONB NOT NULL,
    status VARCHAR(32) DEFAULT 'active',
    valid_until TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 10. diagnostic_assessments
CREATE TABLE IF NOT EXISTS diagnostic_assessments (
    diagnostic_id VARCHAR(64) PRIMARY KEY,
    student_id VARCHAR(64) REFERENCES students(student_id),
    topic VARCHAR(128) NOT NULL,
    blueprint JSONB NOT NULL,
    results JSONB,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- 11. predictions
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id VARCHAR(64) PRIMARY KEY,
    student_id VARCHAR(64) REFERENCES students(student_id),
    model_version VARCHAR(64) NOT NULL,
    target_column VARCHAR(64) NOT NULL,
    predicted_value FLOAT,
    predicted_label VARCHAR(32),
    confidence_interval JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 12. interventions
CREATE TABLE IF NOT EXISTS interventions (
    intervention_id VARCHAR(64) PRIMARY KEY,
    student_id VARCHAR(64) REFERENCES students(student_id),
    lecturer_id VARCHAR(64) NOT NULL,
    action_type VARCHAR(64) NOT NULL,
    notes TEXT,
    status VARCHAR(32) DEFAULT 'open',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 13. model_registry
CREATE TABLE IF NOT EXISTS model_registry (
    training_id VARCHAR(64) PRIMARY KEY,
    model_key VARCHAR(128) NOT NULL,
    version INT NOT NULL,
    status VARCHAR(32) NOT NULL, -- 'candidate', 'production', 'archived'
    metrics JSONB NOT NULL,
    model_sha256 VARCHAR(64) NOT NULL,
    promoted_by VARCHAR(64),
    promoted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 14. llm_usage
CREATE TABLE IF NOT EXISTS llm_usage (
    usage_id VARCHAR(64) PRIMARY KEY,
    user_pseudonym VARCHAR(64) NOT NULL,
    role VARCHAR(32) NOT NULL,
    provider VARCHAR(32) NOT NULL,
    model VARCHAR(64) NOT NULL,
    input_tokens INT NOT NULL,
    output_tokens INT NOT NULL,
    estimated_cost FLOAT NOT NULL,
    cache_hit BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 15. audit_logs
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id VARCHAR(64) PRIMARY KEY,
    actor_id VARCHAR(64) NOT NULL,
    action VARCHAR(64) NOT NULL,
    target_entity VARCHAR(64) NOT NULL,
    details JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 16. knowledge_sources
CREATE TABLE IF NOT EXISTS knowledge_sources (
    source_id VARCHAR(64) PRIMARY KEY,
    title TEXT NOT NULL,
    publisher TEXT,
    year INT,
    doi VARCHAR(128),
    url TEXT,
    status VARCHAR(32) DEFAULT 'APPROVED', -- 'DRAFT', 'APPROVED', 'ARCHIVED'
    source_verified BOOLEAN DEFAULT TRUE,
    permission_scope VARCHAR(32) DEFAULT 'student_learning',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 17. knowledge_chunks
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id VARCHAR(128) PRIMARY KEY,
    source_id VARCHAR(64) REFERENCES knowledge_sources(source_id) ON DELETE CASCADE,
    course_id VARCHAR(64),
    content TEXT NOT NULL,
    embedding vector(384),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""


class BaseLMSRepository(ABC):
    """Giao diện trừu tượng cho tầng Persistence chuẩn LMS."""

    @abstractmethod
    def record_student_event(self, student_id: str, event_type: str, payload: Dict[str, Any]) -> str:
        pass

    @abstractmethod
    def save_learning_plan(self, student_id: str, version: int, plan_dict: Dict[str, Any]) -> str:
        pass

    @abstractmethod
    def get_latest_learning_plan(self, student_id: str) -> Optional[Dict[str, Any]]:
        pass


class SQLiteLMSRepository(BaseLMSRepository):
    """Triển khai SQLite hỗ trợ Transaction và ghi đồng thời cho chế độ Local/Test."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    student_id TEXT PRIMARY KEY,
                    pseudonym TEXT UNIQUE NOT NULL,
                    created_at TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS learning_plans (
                    plan_id TEXT PRIMARY KEY,
                    student_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    plan_json TEXT NOT NULL,
                    created_at TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS lms_events (
                    event_id TEXT PRIMARY KEY,
                    student_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT,
                    created_at TEXT
                );
            """)
            conn.commit()

    def initialize_schema(self) -> None:
        """Khởi tạo toàn bộ 17 bảng chuẩn hoá của LMS trong SQLite."""
        table_defs = [
            "CREATE TABLE IF NOT EXISTS lms_users (id TEXT PRIMARY KEY, username TEXT UNIQUE, role TEXT, email TEXT, created_at TEXT)",
            "CREATE TABLE IF NOT EXISTS lms_courses (course_id TEXT PRIMARY KEY, course_code TEXT, course_name TEXT, credits INT, semester TEXT)",
            "CREATE TABLE IF NOT EXISTS lms_enrollments (enrollment_id TEXT PRIMARY KEY, student_id TEXT, course_id TEXT, status TEXT)",
            "CREATE TABLE IF NOT EXISTS lms_quizzes (quiz_id TEXT PRIMARY KEY, course_id TEXT, title TEXT, max_score REAL)",
            "CREATE TABLE IF NOT EXISTS lms_quiz_submissions (submission_id TEXT PRIMARY KEY, quiz_id TEXT, student_id TEXT, score REAL)",
            "CREATE TABLE IF NOT EXISTS lms_assignments (assignment_id TEXT PRIMARY KEY, course_id TEXT, title TEXT, due_date TEXT)",
            "CREATE TABLE IF NOT EXISTS lms_assignment_submissions (submission_id TEXT PRIMARY KEY, assignment_id TEXT, student_id TEXT, grade REAL)",
            "CREATE TABLE IF NOT EXISTS lms_forum_posts (post_id TEXT PRIMARY KEY, course_id TEXT, author_id TEXT, content TEXT)",
            "CREATE TABLE IF NOT EXISTS lms_forum_interactions (id TEXT PRIMARY KEY, post_id TEXT, student_id TEXT, action_type TEXT)",
            "CREATE TABLE IF NOT EXISTS lms_resources (resource_id TEXT PRIMARY KEY, course_id TEXT, title TEXT, resource_type TEXT, url TEXT)",
            "CREATE TABLE IF NOT EXISTS lms_resource_access_logs (log_id TEXT PRIMARY KEY, student_id TEXT, resource_id TEXT, duration_seconds INT, completion_ratio REAL, timestamp TEXT)",
            "CREATE TABLE IF NOT EXISTS lms_video_sessions (session_id TEXT PRIMARY KEY, student_id TEXT, video_id TEXT, watched_seconds INT)",
            "CREATE TABLE IF NOT EXISTS lms_student_competencies (id TEXT PRIMARY KEY, student_id TEXT, competency_code TEXT, mastery_level REAL)",
            "CREATE TABLE IF NOT EXISTS lms_diagnostic_assessments (diag_id TEXT PRIMARY KEY, student_id TEXT, gap_category TEXT, score REAL)",
            "CREATE TABLE IF NOT EXISTS lms_student_learning_profiles (profile_id TEXT PRIMARY KEY, student_id TEXT, profile_json TEXT, updated_at TEXT)",
            "CREATE TABLE IF NOT EXISTS lms_structured_learning_plans (plan_id TEXT PRIMARY KEY, student_id TEXT, version INT, plan_json TEXT, created_at TEXT)",
            "CREATE TABLE IF NOT EXISTS lms_plan_activity_logs (log_id TEXT PRIMARY KEY, plan_id TEXT, activity_id TEXT, status TEXT, completed_at TEXT)",
        ]
        with self._lock, self._get_connection() as conn:
            for sql in table_defs:
                conn.execute(sql)
            conn.commit()

    def transaction(self):
        """Context manager hỗ trợ giao dịch ACID trong SQLite."""
        from contextlib import contextmanager

        @contextmanager
        def _tx():
            conn = self._get_connection()
            try:
                with self._lock:
                    yield conn
                    conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        return _tx()

    def record_resource_access(
        self,
        student_id: str,
        resource_id: str,
        duration_seconds: int = 0,
        completion_ratio: float = 1.0,
    ) -> str:
        """Ghi nhận nhật ký truy cập học liệu an toàn giao dịch."""
        import uuid

        log_id = f"log_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "INSERT INTO lms_resource_access_logs (log_id, student_id, resource_id, duration_seconds, completion_ratio, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (log_id, student_id, resource_id, duration_seconds, completion_ratio, now),
            )
            conn.commit()
        return log_id

    def record_student_event(self, student_id: str, event_type: str, payload: Dict[str, Any]) -> str:
        import json
        import uuid

        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "INSERT INTO lms_events (event_id, student_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (event_id, student_id, event_type, json.dumps(payload), now),
            )
            conn.commit()
        return event_id

    def save_learning_plan(self, student_id: str, version: int, plan_dict: Dict[str, Any]) -> str:
        import json
        import uuid

        plan_id = plan_dict.get("plan_id") or f"plan_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO learning_plans (plan_id, student_id, version, plan_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (plan_id, student_id, version, json.dumps(plan_dict), now),
            )
            conn.commit()
        return plan_id

    def get_latest_learning_plan(self, student_id: str) -> Optional[Dict[str, Any]]:
        import json

        with self._lock, self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT plan_json FROM learning_plans WHERE student_id = ? ORDER BY version DESC LIMIT 1",
                (student_id,),
            )
            row = cur.fetchone()
            if row:
                return json.loads(row["plan_json"])
        return None


# Aliases cho tầng Persistence chuẩn hoá
LMSRepository = SQLiteLMSRepository
LMS_SCHEMA_DDL = LMS_POSTGRESQL_DDL_MIGRATIONS
