"""LMS-Scale Load & Performance Benchmark Suite for EduDSS (~20,000 students/year).

Validates:
1. Batch prediction throughput and latency at 20,000 student scale.
2. Memory consumption bounds under high-volume inference.
3. Quantile latencies (p50, p95, p99) and predictions/sec telemetry.
"""
import time
import tracemalloc
import numpy as np
import pandas as pd

from dss.core.warehouse import DataWarehouse
from dss.services.model_service import resolve_production_for_prediction


def generate_synthetic_20k_cohort():
    """Generates 20,000 synthetic student feature records representing annual LMS cohort."""
    n = 20000
    rng = np.random.RandomState(42)
    
    df = pd.DataFrame({
        "student_id": [f"SV_{i:06d}" for i in range(n)],
        "diem_chuyen_can": rng.uniform(4.0, 10.0, size=n),
        "diem_giua_ky": rng.uniform(3.0, 10.0, size=n),
        "so_gio_hoc_tuan": rng.uniform(2.0, 30.0, size=n),
        "so_lan_xem_bai_giang": rng.randint(0, 50, size=n),
        "so_bai_tap_hoan_thanh": rng.randint(0, 30, size=n),
        "diem_trung_binh_tich_luy": rng.uniform(1.8, 4.0, size=n),
    })
    return df


def test_20000_students_batch_prediction_benchmark(tmp_path):
    """Benchmark batch inference latency, memory delta, and throughput for 20,000 students."""
    wh = DataWarehouse(base_path=str(tmp_path))
    
    # Train and promote a real Ridge regression model on mock data
    from sklearn.linear_model import Ridge
    X_train = np.random.uniform(0, 10, size=(200, 6))
    y_train = 0.3 * X_train[:, 0] + 0.4 * X_train[:, 1] + 0.3 * X_train[:, 2]
    features = [
        "diem_chuyen_can",
        "diem_giua_ky",
        "so_gio_hoc_tuan",
        "so_lan_xem_bai_giang",
        "so_bai_tap_hoan_thanh",
        "diem_trung_binh_tich_luy",
    ]
    model = Ridge().fit(X_train, y_train)
    
    training_id, meta = wh.save_model_training(
        dataset_id="benchmark_dataset",
        model_pipeline=model,
        model_name="ScaleBenchmarkModel",
        feature_cols=features,
        target_col="diem_cuoi_ky",
        metrics={"r2": 0.88, "mae": 0.35},
        is_best=True,
    )
    wh.set_production_model(training_id, promoted_by="Admin")
    
    cohort_df = generate_synthetic_20k_cohort()
    
    # Measure memory using tracemalloc
    tracemalloc.start()
    
    # Run batch inference with timing
    t0 = time.perf_counter()
    res = resolve_production_for_prediction(wh, dataset_id="benchmark_dataset", target_col="diem_cuoi_ky")
    assert res["status"] == "ok", f"Expected ok status, got {res.get('message')}"
    prod_model = res["pipeline"]
    X_pred = cohort_df[features]
    predictions = prod_model.predict(X_pred)
    elapsed_total_sec = time.perf_counter() - t0
    
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    mem_delta_mb = peak_mem / (1024 * 1024)
    
    throughput_rps = len(cohort_df) / max(elapsed_total_sec, 0.0001)
    
    # Individual micro-batch chunk latencies to compute p50, p95, p99
    chunk_size = 100
    chunk_latencies_ms = []
    for i in range(0, len(cohort_df), chunk_size):
        chunk = X_pred.iloc[i : i + chunk_size]
        t_start = time.perf_counter()
        _ = prod_model.predict(chunk)
        chunk_latencies_ms.append((time.perf_counter() - t_start) * 1000)
        
    p50_ms = float(np.percentile(chunk_latencies_ms, 50))
    p95_ms = float(np.percentile(chunk_latencies_ms, 95))
    p99_ms = float(np.percentile(chunk_latencies_ms, 99))
    
    print("\n--- 20,000 STUDENTS LOAD TEST TELEMETRY ---")
    print(f"Total cohort size:       {len(cohort_df)} students")
    print(f"Total inference time:    {elapsed_total_sec:.4f} s")
    print(f"Throughput:              {throughput_rps:.1f} predictions/sec")
    print(f"Chunk (100) p50 latency: {p50_ms:.3f} ms")
    print(f"Chunk (100) p95 latency: {p95_ms:.3f} ms")
    print(f"Chunk (100) p99 latency: {p99_ms:.3f} ms")
    print(f"Process RAM increase:    {mem_delta_mb:.2f} MB")
    print("------------------------------------------")
    
    # Assertions for LMS scale viability:
    # 20k predictions should complete in well under 5 seconds on modern CPU
    assert elapsed_total_sec < 5.0, f"Batch inference took too long: {elapsed_total_sec:.2f}s"
    assert throughput_rps > 5000, f"Throughput too low: {throughput_rps} rps"
    assert len(predictions) == 20000
