import io
import json
import logging

from dss.core import health_diagnostics, observability


def _capture(monkeypatch):
    stream = io.StringIO()
    logger = logging.Logger("dss.test.observability", level=logging.INFO)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(observability.StructuredFormatter())
    logger.addHandler(handler)
    monkeypatch.setattr("dss.core.logging_config.get_logger", lambda name: logger)
    return stream


def test_correlation_id_scopes_and_structured_log(monkeypatch):
    stream = _capture(monkeypatch)
    first = observability.new_correlation_id()
    assert len(first) == 32
    with observability.correlation_scope() as nested:
        with observability.observe("test.operation"):
            assert observability.current_correlation_id() == nested
    assert observability.current_correlation_id() == first
    event = json.loads(stream.getvalue().splitlines()[-1])
    assert event["correlation_id"] == nested
    assert event["duration_ms"] >= 0
    assert event["outcome"] == "success"


def test_ai_failure_counted_without_secret_in_log(monkeypatch):
    stream = _capture(monkeypatch)

    @observability.observed("ai.provider", metadata=lambda: {"provider": "groq", "model": "safe-model"})
    def failing():
        raise RuntimeError("api_key=sk-abcdefghijklmnop")

    try:
        failing()
    except RuntimeError:
        pass
    event = json.loads(stream.getvalue().splitlines()[-1])
    assert event["outcome"] == "error"
    assert event["provider"] == "groq"
    assert "sk-abcdefghijklmnop" not in stream.getvalue()
    assert observability.metrics_snapshot()["counters"]["ai.provider:error"] >= 1


def test_rag_metrics_omit_retrieved_text(monkeypatch):
    from dss.services.rag_service import retrieve_documents

    stream = _capture(monkeypatch)

    class FakeProvider:
        def find_relevant_documents_rag(self, **kwargs):
            return [{"content": "PRIVATE DOCUMENT CONTENT", "title": "private"}]

    assert len(retrieve_documents(FakeProvider(), "private question", top_k=3)) == 1
    event = json.loads(stream.getvalue().splitlines()[-1])
    assert event["operation"] == "rag.retrieve"
    assert event["top_k"] == 3
    assert event["result_count"] == 1
    assert "PRIVATE DOCUMENT CONTENT" not in stream.getvalue()


def test_vector_backend_label_without_document_content(monkeypatch, tmp_path):
    from dss.services.vector_store import LocalVectorStore

    stream = _capture(monkeypatch)
    store = LocalVectorStore(base_dir=str(tmp_path))
    assert store.search([0.1, 0.2]) == []
    event = json.loads(stream.getvalue().splitlines()[-1])
    assert event["operation"] == "rag.vector_search"
    assert event["backend"] == "local"


def test_ml_metrics_omit_feature_rows(monkeypatch):
    stream = _capture(monkeypatch)

    class FakeModel:
        def predict(self, rows):
            return [1] * len(rows)

    assert observability.predict_with_metrics(FakeModel(), [{"private": "SECRET STUDENT FEATURE"}]) == [1]
    event = json.loads(stream.getvalue().splitlines()[-1])
    assert event["operation"] == "ml.predict"
    assert event["batch_size"] == 1
    assert "SECRET STUDENT FEATURE" not in stream.getvalue()


def test_health_and_readiness_are_distinct(monkeypatch):
    assert health_diagnostics.liveness()["status"] == "alive"
    monkeypatch.setattr(health_diagnostics, "postgres_diagnostic", lambda: {"status": "unavailable", "required": True})
    monkeypatch.setattr(
        health_diagnostics, "pgvector_diagnostic", lambda: {"status": "not_required", "required": False}
    )
    monkeypatch.setattr(
        health_diagnostics, "model_artifact_diagnostic", lambda: {"status": "not_available", "required": False}
    )
    result = health_diagnostics.readiness()
    assert result["status"] == "not_ready"
    assert result["checks"]["postgresql"]["status"] == "unavailable"


def test_postgres_probe_failure_is_safe(monkeypatch):
    from dss.db import session

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:private-password@invalid/edudss")
    monkeypatch.setattr(session, "get_engine", lambda: (_ for _ in ()).throw(RuntimeError("private-password")))
    result = health_diagnostics.postgres_diagnostic()
    assert result == {"status": "unavailable", "required": True}
    assert "private-password" not in str(result)


def test_existing_redaction_still_applies_to_structured_logs():
    record = logging.LogRecord(
        "dss.test", logging.INFO, __file__, 1, "Authorization: Bearer sk-abcdefghijklmnop student SV123", (), None
    )
    output = observability.StructuredFormatter().format(record)
    assert "sk-abcdefghijklmnop" not in output
    assert "SV123" not in output
    assert json.loads(output)["message"]
