"""Layered Semantic Cache Test Suite for EduDSS.

Validates:
1. Exact match cache hit (L1 fast lookup).
2. Student learning plan state-hashed caching & invalidation.
3. Course knowledge base invalidation.
"""
from dss.services.semantic_cache import LayeredSemanticCache, CACHE_CLASS_GLOBAL, CACHE_CLASS_STUDENT


def test_exact_cache_hit_and_miss():
    """Verify that exact queries return cached responses with zero latency."""
    cache = LayeredSemanticCache()
    
    key = "plan::student_123::hash_abc"
    content = "Bạn nên làm 5 bài tập về cây nhị phân."
    
    # Miss before store
    assert cache.exact_cache.get(key) is None
    
    cache.exact_cache.set(key, content, CACHE_CLASS_GLOBAL, {"course_id": "CS101"})
    
    # Hit after store
    hit = cache.exact_cache.get(key)
    assert hit == content


def test_student_plan_caching_and_invalidation():
    """Verify student plan caching by state hash and student-specific invalidation."""
    cache = LayeredSemanticCache()
    
    pseudonym = "Student_A1B2C3"
    state_hash_1 = "hash_state_week1"
    state_hash_2 = "hash_state_week2"
    plan_1 = {"week": 1, "target_hours": 6.5}
    plan_2 = {"week": 2, "target_hours": 8.0}
    
    cache.set_student_plan(pseudonym, state_hash_1, plan_1)
    
    # Hit for state 1
    assert cache.get_student_plan(pseudonym, state_hash_1) == plan_1
    # Miss for state 2
    assert cache.get_student_plan(pseudonym, state_hash_2) is None
    
    # Invalidate student
    deleted = cache.invalidate_student(pseudonym)
    assert deleted >= 1
    assert cache.get_student_plan(pseudonym, state_hash_1) is None


def test_course_kb_cache_invalidation():
    """Verify that updating course knowledge base invalidates cached entries for that course."""
    cache = LayeredSemanticCache()
    
    cache.exact_cache.set("q1", "ans1", CACHE_CLASS_GLOBAL, {"course_id": "CS101"})
    cache.exact_cache.set("q2", "ans2", CACHE_CLASS_GLOBAL, {"course_id": "MATH101"})
    
    assert cache.exact_cache.get("q1") == "ans1"
    assert cache.exact_cache.get("q2") == "ans2"
    
    # Invalidate course CS101
    cache.invalidate_course_kb("CS101")
    assert cache.exact_cache.get("q1") is None
    assert cache.exact_cache.get("q2") == "ans2"
