"""LMS Persistence & Transactional Integrity Test Suite for EduDSS.

Validates:
1. Complete relational schema migration for 17 LMS entities.
2. ACID transactional consistency (rollback on error).
3. Concurrent student interaction log insertions.
4. SSO token integration validation.
"""
import pytest
import sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from dss.core.lms_repository import LMSRepository, LMS_SCHEMA_DDL
from dss.services.auth_service import verify_lms_sso_token


def test_lms_schema_creation(tmp_path):
    """Verify that all 17 LMS entities tables and indexes are created successfully."""
    db_path = tmp_path / "lms_test.db"
    repo = LMSRepository(db_path=str(db_path))
    repo.initialize_schema()
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()
    
    expected_tables = {
        "lms_users",
        "lms_courses",
        "lms_enrollments",
        "lms_quizzes",
        "lms_quiz_submissions",
        "lms_assignments",
        "lms_assignment_submissions",
        "lms_forum_posts",
        "lms_forum_interactions",
        "lms_resources",
        "lms_resource_access_logs",
        "lms_video_sessions",
        "lms_student_competencies",
        "lms_diagnostic_assessments",
        "lms_student_learning_profiles",
        "lms_structured_learning_plans",
        "lms_plan_activity_logs",
    }
    
    assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"


def test_transaction_rollback_on_error(tmp_path):
    """Verify that multi-statement operations roll back on error without partial commit."""
    db_path = tmp_path / "lms_tx_test.db"
    repo = LMSRepository(db_path=str(db_path))
    repo.initialize_schema()
    
    # Inserting user then failing on bad SQL should rollback both
    with pytest.raises(Exception):
        with repo.transaction() as conn:
            conn.execute(
                "INSERT INTO lms_users (id, username, role, email) VALUES (?, ?, ?, ?)",
                ("U101", "student_101", "Student", "s101@school.edu"),
            )
            # Intentionally invalid statement to trigger rollback
            conn.execute("INSERT INTO non_existent_table VALUES (1, 2, 3)")
            
    # Verify user was NOT committed
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM lms_users WHERE id='U101'")
        assert cursor.fetchone()[0] == 0


def test_concurrent_log_insertions(tmp_path):
    """Verify that multiple concurrent threads can write access logs safely."""
    db_path = tmp_path / "lms_concurrent.db"
    repo = LMSRepository(db_path=str(db_path))
    repo.initialize_schema()
    
    def worker(worker_id):
        repo.record_resource_access(
            student_id=f"SV_{worker_id}",
            resource_id="RES_01",
            duration_seconds=120,
            completion_ratio=1.0,
        )
        
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(worker, range(40)))
        
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM lms_resource_access_logs")
        count = cursor.fetchone()[0]
        assert count == 40


def test_lms_sso_token_verification():
    """Verify that verify_lms_sso_token properly validates tokens."""
    # Invalid token
    assert verify_lms_sso_token("") is None
    assert verify_lms_sso_token("short") is None
    
    # Valid mock token
    valid_token = "lms_bearer_sv001_session"
    user = verify_lms_sso_token(valid_token)
    assert user is not None
    assert user["role"] == "Sinh viên"
    assert user["username"] == "sv001"
