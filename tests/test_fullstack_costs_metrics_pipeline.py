"""Real provider token usage, pricing, Prometheus metrics, ops pipeline, eval gates."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from dss.services import llm_usage, token_tracker


# ----------------------------------------------------------------------------- pricing
def test_longest_model_name_wins_and_thinking_is_billed_as_output():
    lite = token_tracker.estimate_cost("gemini", "gemini-2.5-flash-lite", 1_000_000, 1_000_000)
    flash = token_tracker.estimate_cost("gemini", "gemini-2.5-flash", 1_000_000, 1_000_000)
    assert lite == pytest.approx(0.10 + 0.40)
    assert flash == pytest.approx(0.30 + 2.50)
    assert token_tracker.estimate_cost("groq", "openai/gpt-oss-20b", 1_000_000, 0) == pytest.approx(0.075)
    assert token_tracker.estimate_cost("demo", "anything", 10**6, 10**6) == 0.0


def test_pricing_override_from_env(monkeypatch):
    monkeypatch.setenv("EDUDSS_LLM_PRICING_JSON", json.dumps({"gemini-flash-lite-latest": {"input": 1, "output": 2}}))
    assert token_tracker.estimate_cost("gemini", "gemini-flash-lite-latest", 10**6, 10**6) == pytest.approx(3.0)
    monkeypatch.setenv("EDUDSS_LLM_PRICING_JSON", "not json")
    assert token_tracker.estimate_cost("gemini", "gemini-flash-lite-latest", 10**6, 0) == pytest.approx(0.25)


# ----------------------------------------------------------------------------- provider usage capture
def test_gemini_usage_metadata_includes_thinking_tokens():
    llm_usage.begin()
    meta = SimpleNamespace(prompt_token_count=1200, candidates_token_count=300, thoughts_token_count=80)
    llm_usage.from_gemini("gemini", "gemini-flash-lite-latest", meta)
    usage = llm_usage.take()
    assert usage == {
        "provider": "gemini",
        "model": "gemini-flash-lite-latest",
        "input_tokens": 1200,
        "thinking_tokens": 80,
        "output_tokens": 380,
    }
    assert llm_usage.take() is None


def test_openai_reasoning_tokens_are_not_double_counted():
    llm_usage.begin()
    usage = SimpleNamespace(
        prompt_tokens=50, completion_tokens=40, completion_tokens_details=SimpleNamespace(reasoning_tokens=10)
    )
    llm_usage.from_openai_compatible("groq", "openai/gpt-oss-20b", usage)
    got = llm_usage.take()
    assert got["output_tokens"] == 40 and got["thinking_tokens"] == 10 and got["input_tokens"] == 50


def test_mock_like_usage_objects_are_ignored():
    from unittest.mock import MagicMock

    llm_usage.begin()
    llm_usage.from_gemini("gemini", "m", MagicMock())
    llm_usage.from_openai_compatible("openai", "m", MagicMock())
    assert llm_usage.take() is None


def test_gateway_records_provider_usage_instead_of_estimate(monkeypatch):
    """End to end through LLMGateway.stream_generate with a fake provider that reports usage."""
    from dss.services import llm_gateway

    class FakeIntegration:
        def call_ai_provider(self, prompt, provider=None, model_name=None, api_key=None, **kw):
            yield "Kế hoạch học tập: ôn chương 1."
            llm_usage.report(provider, "gemini-2.5-flash", 900, 120, 30)

    recorded = []
    monkeypatch.setattr(token_tracker, "record_usage", lambda **kw: recorded.append(kw))
    monkeypatch.setattr(token_tracker, "check_user_quota", lambda *a, **k: (True, ""))
    from dss.services import subscription_service

    monkeypatch.setattr(subscription_service, "consume_ai_request_quota", lambda *a, **k: None)
    gateway = llm_gateway.LLMGateway(llm_integration=FakeIntegration())
    monkeypatch.setattr(
        gateway, "resolve_active_provider_and_model", lambda **kw: ("gemini", "gemini-2.5-flash", "fake-key")
    )
    monkeypatch.setattr(gateway, "_check_rate_limit", lambda: None)
    text = "".join(
        gateway.stream_generate(
            prompt=f"câu hỏi duy nhất {id(recorded)}",
            user_id="u1",
            role="Sinh viên",
            request_type="chat",
            provider="gemini",
        )
    )
    assert "Kế hoạch" in text
    real = [r for r in recorded if r.get("usage_source") == "provider"]
    assert (
        real and real[0]["input_tokens"] == 900 and real[0]["output_tokens"] == 150 and real[0]["thinking_tokens"] == 30
    )


def test_record_usage_stores_source_and_thinking(isolated_token_usage_file=None):
    rec = token_tracker.record_usage(
        user_id="u9",
        role="Sinh viên",
        request_type="chat",
        provider="gemini",
        model="gemini-2.5-flash",
        input_tokens=1000,
        output_tokens=200,
        usage_source="provider",
        thinking_tokens=50,
    )
    assert rec.usage_source == "provider" and rec.thinking_tokens == 50
    assert rec.estimated_cost == pytest.approx(1000 / 1e6 * 0.30 + 200 / 1e6 * 2.50, rel=1e-4)


# ----------------------------------------------------------------------------- metrics
def test_metrics_endpoint_content_and_auth(monkeypatch):
    from dss.core import metrics, metrics_exporter

    metrics.record_login("google", "success")
    metrics.record_page_view("🧪 Huấn luyện — Dự đoán", "Sinh viên")
    metrics.record_ai_usage(
        provider="gemini",
        model="gemini-2.5-flash",
        request_type="chat",
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.001,
        cache_hit=False,
        source="provider",
    )
    body, _ = metrics_exporter.render()
    text = body.decode()
    assert 'edudss_logins_total{method="google",result="success"}' in text
    assert 'page="huan_luyen_du_doan",role="student"' in text
    assert 'edudss_ai_tokens_total{kind="input",model="gemini-2.5-flash",provider="gemini",source="provider"}' in text
    assert "edudss_exporter_up 1.0" in text
    monkeypatch.delenv("EDUDSS_METRICS_TOKEN", raising=False)
    assert metrics_exporter.authorized(None, "127.0.0.1") and not metrics_exporter.authorized(None, "10.0.0.5")
    monkeypatch.setenv("EDUDSS_METRICS_TOKEN", "s3cret")
    assert metrics_exporter.authorized("Bearer s3cret", "10.0.0.5")
    assert not metrics_exporter.authorized("Bearer nope", "127.0.0.1")


def test_unknown_models_and_pages_collapse_to_bounded_labels():
    from dss.core import metrics

    assert metrics._model_label("some-user-typed-model-9000") == "other"
    assert metrics.provider_label("evil-provider") == "other"
    assert metrics.page_slug("📚 Quản lý tri thức (RAG)") == "quan_ly_tri_thuc_rag"


# ----------------------------------------------------------------------------- pipeline
@pytest.fixture
def ops_root(tmp_path, monkeypatch):
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from ops import pipeline

    return tmp_path, pipeline


def test_data_quality_rules():
    from ops.pipeline import check_dataframe

    good = pd.DataFrame({"student_id": ["SV1", "SV2"], "diem_ky_nay": [7.0, 8.5], "ty_le_diem_danh": [0.9, 1.0]})
    assert check_dataframe(good, "g")["severity"] == "ok"
    bad = pd.DataFrame(
        {"student_id": ["SV1", "SV1", "SV3"], "diem_ky_nay": [7.0, 12.0, None], "ty_le_diem_danh": [0.9, 1.4, 0.8]}
    )
    report = check_dataframe(bad, "b")
    assert report["severity"] == "fail"
    assert report["out_of_range"] == {"diem_ky_nay": 1, "ty_le_diem_danh": 1}
    assert "diem_ky_nay" in report["missing_rate"]


def test_psi_detects_shift():
    import numpy as np

    from ops.pipeline import _psi

    rng = np.random.default_rng(0)
    base = rng.normal(7, 1, 2000)
    assert _psi(base, rng.normal(7, 1, 2000)) < 0.05
    assert _psi(base, rng.normal(5, 1, 2000)) > 0.25


def test_backup_restore_drill_and_retention(ops_root):
    root, pipeline = ops_root
    (root / "users.json").write_text('{"a": 1}', encoding="utf-8")
    (root / "datasets").mkdir()
    (root / "datasets" / "d.csv").write_text("x\n1\n", encoding="utf-8")
    (root / "secret.env").write_text("KEY=1", encoding="utf-8")
    result = pipeline.run_job("backup")
    assert result["status"] == "ok", result
    assert result["detail"]["restore_drill"] == "VERIFIED" and result["detail"]["files"] >= 2
    manifest = json.loads((Path(result["detail"]["dir"]) / "manifest.json").read_text(encoding="utf-8"))
    assert not any("secret" in name for name in manifest["files"])
    old = pipeline.backup_root() / "20000101T000000Z"
    old.mkdir(parents=True)
    retention = pipeline.run_job("retention")
    assert "20000101T000000Z" in retention["detail"]["backups_removed"]
    assert pipeline.last_runs()["backup"]["last_success_at"]


def test_kpi_snapshot_and_infra_costs(ops_root):
    root, pipeline = ops_root
    month = pipeline.now().strftime("%Y-%m")
    pipeline.save_infra_cost(month, "Oracle Cloud", "VM A1 (1/3)", 0)
    pipeline.save_infra_cost(month, "DuckDNS", "Tên miền", 0, note="free")
    with pytest.raises(ValueError):
        pipeline.save_infra_cost(month, "", "x", 1)
    snap = pipeline.run_job("kpi_snapshot")
    assert snap["status"] == "ok" and snap["detail"]["infra_month_usd"] == 0.0
    assert "ai_month" in snap["detail"]


# ----------------------------------------------------------------------------- eval gates
def _load_run_evals():
    path = Path(__file__).resolve().parents[1] / "evals" / "run_evals.py"
    spec = importlib.util.spec_from_file_location("run_evals_mod", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_eval_gates_and_regressions():
    ev = _load_run_evals()
    th = {"min": {"ml_reg_r2": 0.9}, "max": {"ml_reg_mae": 0.3}, "must_be_true": ["ml_leakage_guard_ok"]}
    assert ev.gates({"ml_reg_r2": 0.95, "ml_reg_mae": 0.1, "ml_leakage_guard_ok": True}, th) == []
    assert len(ev.gates({"ml_reg_r2": 0.5, "ml_reg_mae": 0.5, "ml_leakage_guard_ok": False}, th)) == 3
    regs, deltas = ev.regressions(
        {"ml_reg_r2": 0.90, "ml_reg_mae": 0.40}, {"ml_reg_r2": 0.99, "ml_reg_mae": 0.06}, 0.03
    )
    assert len(regs) == 2 and deltas["ml_reg_r2"] == pytest.approx(-0.09)


def test_safety_eval_runs_on_golden_sets():
    ev = _load_run_evals()
    out = ev.eval_safety()
    assert out["injection_block_rate"] == 1.0 and out["injection_benign_altered_rate"] == 0.0
    assert out["safety_harmful_recall"] == 1.0 and out["safety_false_flag_rate"] == 0.0
    assert "holdout_injection_block_rate" in out


def test_thresholds_reference_known_metrics():
    ev = _load_run_evals()
    th = json.loads((Path(ev.EVALS) / "thresholds.json").read_text(encoding="utf-8"))
    known = set(ev.HIGHER + ev.LOWER) | {"ml_leakage_guard_ok"}
    assert set(th["min"]) | set(th["max"]) | set(th["must_be_true"]) <= known
