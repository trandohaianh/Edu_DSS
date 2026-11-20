"""Ollama: URL cấu hình qua .env, tự chọn model đã cài, /api/chat streaming,
báo lỗi nhanh và rõ ràng khi server chưa chạy / chưa pull model."""

from __future__ import annotations

import json

import pytest

from dss.core import models


class _Resp:
    def __init__(self, status=200, payload=None, lines=None):
        self.status_code = status
        self._payload = payload or {}
        self._lines = lines or []

    def json(self):
        return self._payload

    def iter_lines(self):
        return iter(self._lines)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("OLLAMA_BASE_URL", "OLLAMA_HOST", "OLLAMA_API_KEY", "OLLAMA_MODEL"):
        monkeypatch.delenv(k, raising=False)
    models._OLLAMA_STATUS.clear()
    yield
    models._OLLAMA_STATUS.clear()


def test_base_url_from_env(monkeypatch):
    assert models.ollama_base_url() == "http://127.0.0.1:11434"
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:11500")
    assert models.ollama_base_url() == "http://127.0.0.1:11500"
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/")
    assert models.ollama_base_url() == "http://host.docker.internal:11434"


def test_api_key_without_url_uses_ollama_cloud(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "k")
    assert models.ollama_base_url() == "https://ollama.com"
    assert models._ollama_headers() == {"Authorization": "Bearer k"}


def test_resolve_model_prefers_installed(monkeypatch):
    monkeypatch.setattr(models, "list_ollama_models", lambda *a, **k: ["llama3.2:latest", "mistral:7b"])
    assert models.resolve_ollama_model("llama3.2") == "llama3.2:latest"
    assert models.resolve_ollama_model("khong-co") == "llama3.2:latest"  # model catalog đầu tiên đã cài
    monkeypatch.setattr(models, "list_ollama_models", lambda *a, **k: [])
    assert models.resolve_ollama_model("x") == "x"


def test_chat_streams_content(monkeypatch):
    sent = {}
    monkeypatch.setattr(models, "_check_ollama_running", lambda *a, **k: True)
    monkeypatch.setattr(models, "list_ollama_models", lambda *a, **k: ["qwen2.5:7b"])

    def _post(url, json=None, **kw):
        sent["url"], sent["body"] = url, json
        lines = [b'{"message": {"content": "Xin "}}', b"", b'{"message": {"content": "chao"}, "done": true}']
        return _Resp(lines=lines)

    monkeypatch.setattr(models.requests, "post", _post)
    out = "".join(
        models.MultiAIProvider.call_ai_provider(object.__new__(models.MultiAIProvider), "hi", provider="ollama")
    )
    assert out == "Xin chao"
    assert sent["url"].endswith("/api/chat") and sent["body"]["model"] == "qwen2.5:7b"
    assert sent["body"]["messages"][0]["role"] == "system"


def test_missing_model_gives_pull_hint(monkeypatch):
    monkeypatch.setattr(models, "_check_ollama_running", lambda *a, **k: True)
    monkeypatch.setattr(models, "list_ollama_models", lambda *a, **k: [])
    monkeypatch.setattr(models.requests, "post", lambda *a, **k: _Resp(status=404))
    out = "".join(
        models.MultiAIProvider.call_ai_provider(object.__new__(models.MultiAIProvider), "hi", provider="ollama")
    )
    assert "ollama pull" in out


def test_server_down_fails_fast_without_posting(monkeypatch):
    monkeypatch.setattr(models, "_check_ollama_running", lambda *a, **k: False)

    def _post(*a, **k):
        raise AssertionError("không được gọi /api/chat khi server không chạy")

    monkeypatch.setattr(models.requests, "post", _post)
    out = "".join(
        models.MultiAIProvider.call_ai_provider(object.__new__(models.MultiAIProvider), "hi", provider="ollama")
    )
    assert "không kết nối được" in out


def test_status_is_cached_server_wide_and_down_result_kept_longer(monkeypatch):
    calls = []

    def _get(url, **kw):
        calls.append(url)
        raise models.requests.exceptions.ConnectionError("down")

    monkeypatch.setattr(models.requests, "get", _get)
    assert models._check_ollama_running("http://127.0.0.1:11434") is False
    assert models._check_ollama_running("http://127.0.0.1:11434") is False
    assert len(calls) == 1  # lần 2 dùng kết quả đã lưu, không gọi mạng lại
    assert models._OLLAMA_DOWN_TTL_SECONDS > models._OLLAMA_UP_TTL_SECONDS
