"""pgvector exact-search scale benchmark (audit evidence, no app data).

Measures the SAME query shape PgVectorStore.search uses — tenant filter,
cosine `<=>` ORDER BY, LIMIT = overfetch (50) — on random unit 384-dim vectors
at increasing corpus sizes, exact scan vs HNSW. Random vectors are a
worst-case-ish proxy for latency only; they say nothing about retrieval quality.

Usage: python tools/pgvector_scale_benchmark.py "postgresql://user:pw@host:port/db"
"""

from __future__ import annotations

import statistics
import sys
import time

import numpy as np
import psycopg2

DIM = 384
SIZES = [10_000, 50_000, 100_000, 250_000]
QUERIES = 30
LIMIT = 50


def vec_literal(v):
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def timed_queries(cur, rng, org_id=1):
    lat = []
    for _ in range(QUERIES):
        q = rng.standard_normal(DIM).astype(np.float32)
        q /= np.linalg.norm(q)
        t0 = time.perf_counter()
        cur.execute(
            "SELECT id FROM bench_chunks WHERE organization_id = %s ORDER BY embedding <=> %s::vector LIMIT %s",
            (org_id, vec_literal(q), LIMIT),
        )
        cur.fetchall()
        lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()
    return {"p50": statistics.median(lat), "p95": lat[int(0.95 * (len(lat) - 1))], "max": lat[-1]}


def main(url):
    rng = np.random.default_rng(42)
    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cur.execute("DROP TABLE IF EXISTS bench_chunks")
    cur.execute(
        f"CREATE TABLE bench_chunks (id bigserial PRIMARY KEY, organization_id int NOT NULL, embedding vector({DIM}))"
    )
    cur.execute("CREATE INDEX ON bench_chunks (organization_id)")
    loaded = 0
    print(f"{'rows(org=1)':>12} {'mode':>6} {'p50 ms':>8} {'p95 ms':>8} {'max ms':>8}")
    for size in SIZES:
        while loaded < size:
            batch = min(5000, size - loaded)
            vecs = rng.standard_normal((batch, DIM)).astype(np.float32)
            vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
            args = ",".join(cur.mogrify("(%s,%s::vector)", (1, vec_literal(v))).decode() for v in vecs)
            cur.execute("INSERT INTO bench_chunks (organization_id, embedding) VALUES " + args)
            loaded += batch
        cur.execute("ANALYZE bench_chunks")
        r = timed_queries(cur, rng)
        print(f"{size:>12,} {'exact':>6} {r['p50']:>8.1f} {r['p95']:>8.1f} {r['max']:>8.1f}", flush=True)
    t0 = time.perf_counter()
    cur.execute("SET maintenance_work_mem = '512MB'")
    cur.execute("CREATE INDEX bench_hnsw ON bench_chunks USING hnsw (embedding vector_cosine_ops)")
    build = time.perf_counter() - t0
    cur.execute("SET hnsw.ef_search = 100")
    r = timed_queries(cur, rng)
    print(
        f"{SIZES[-1]:>12,} {'hnsw':>6} {r['p50']:>8.1f} {r['p95']:>8.1f} {r['max']:>8.1f}   (build {build:.0f}s, ef_search=100)"
    )
    cur.execute("DROP TABLE bench_chunks")


if __name__ == "__main__":
    main(sys.argv[1])
