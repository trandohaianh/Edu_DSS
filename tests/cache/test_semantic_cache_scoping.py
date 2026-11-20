"""POST-72H MASTER PRODUCTION CLOSURE — Section 15/16: Semantic Cache
security audit. `SemanticCache.lookup()`/`.store()` (embedding-based,
distinct from `ExactCache` which was the subject of the P0 fix earlier this
session) are NEVER called anywhere in dss/ production code today (confirmed
via grep across dss/ — zero matches) — so there is currently no production
cross-user/cross-tenant exposure through this specific class. It IS,
however, a real module with real safety claims in its own docstrings
("TUYỆT ĐỐI không áp dụng semantic cache dùng chung cho STUDENT cache
class") that had NO test verifying them before this file. These tests close
that gap so the claim is enforced, not just asserted in a comment — and so
that if/when this class is ever wired into a real path, its safety
properties are already guarded by regression tests."""

from __future__ import annotations

from dss.services.semantic_cache import (
    CACHE_CLASS_COURSE,
    CACHE_CLASS_GLOBAL,
    CACHE_CLASS_STUDENT,
    SemanticCache,
)


def test_lookup_never_returns_a_hit_for_student_class_even_with_identical_embedding():
    """STUDENT-class content must NEVER be served via similarity match — even
    a perfect (identical) embedding match must miss, because similarity is
    not authorization: 2 different students could have near-identical
    embeddings for genuinely different personal questions."""
    cache = SemanticCache(similarity_threshold=0.5)
    embedding = [1.0, 0.0, 0.0]
    cache.store(
        key="k1",
        content="CÂU TRẢ LỜI CÁ NHÂN CỦA SINH VIÊN A",
        query_embedding=embedding,
        cache_class=CACHE_CLASS_STUDENT,
        dimensions={"student_pseudonym": "A"},
    )
    result = cache.lookup(query_embedding=embedding, cache_class=CACHE_CLASS_STUDENT)
    assert result is None, (
        "SemanticCache KHÔNG được trả về bất kỳ kết quả nào cho CACHE_CLASS_STUDENT, "
        "kể cả khi embedding truy vấn giống hệt embedding đã lưu — similarity không phải "
        "là authorization."
    )


def test_store_is_a_silent_noop_for_student_class():
    """`store()` for STUDENT-class content must not even persist internally —
    otherwise a future code change to `lookup()` could accidentally start
    serving it."""
    cache = SemanticCache()
    cache.store(
        key="k1",
        content="riêng tư",
        query_embedding=[1.0, 0.0],
        cache_class=CACHE_CLASS_STUDENT,
        dimensions={},
    )
    assert cache._entries == [], "STUDENT-class store() phải là no-op thật sự, không lưu entry nào."


def test_lookup_does_not_cross_course_boundaries():
    """A GLOBAL/COURSE-class semantic hit scoped to course A must never be
    served for a query scoped to course B, even with a near-identical
    embedding — course_id is a hard filter, not a similarity dimension."""
    cache = SemanticCache(similarity_threshold=0.5)
    embedding = [1.0, 0.0, 0.0]
    cache.store(
        key="k1",
        content="Nội dung môn CS101",
        query_embedding=embedding,
        cache_class=CACHE_CLASS_COURSE,
        dimensions={"course_id": "CS101"},
    )
    result = cache.lookup(query_embedding=embedding, cache_class=CACHE_CLASS_COURSE, course_id="MATH101")
    assert result is None, (
        "Semantic hit của môn CS101 KHÔNG được phục vụ cho truy vấn của môn MATH101 dù embedding giống hệt."
    )


def test_lookup_same_course_still_hits_above_threshold():
    """Sanity check: the course filter above isn't just blocking everything —
    a genuine same-course, above-threshold match must still hit."""
    cache = SemanticCache(similarity_threshold=0.5)
    embedding = [1.0, 0.0, 0.0]
    cache.store(
        key="k1",
        content="Nội dung môn CS101",
        query_embedding=embedding,
        cache_class=CACHE_CLASS_COURSE,
        dimensions={"course_id": "CS101"},
    )
    result = cache.lookup(query_embedding=embedding, cache_class=CACHE_CLASS_COURSE, course_id="CS101")
    assert result is not None
    content, score = result
    assert content == "Nội dung môn CS101"


def test_global_class_lookup_ignores_course_filter_by_design():
    """GLOBAL-class content (e.g. generic regulation FAQ, not course-specific)
    is intentionally not course-scoped — documenting this as INTENTIONAL, not
    an oversight, since GLOBAL entries never carry a course_id dimension."""
    cache = SemanticCache(similarity_threshold=0.5)
    embedding = [1.0, 0.0, 0.0]
    cache.store(
        key="k1",
        content="Câu trả lời chung",
        query_embedding=embedding,
        cache_class=CACHE_CLASS_GLOBAL,
        dimensions={},
    )
    result = cache.lookup(query_embedding=embedding, cache_class=CACHE_CLASS_GLOBAL)
    assert result is not None
