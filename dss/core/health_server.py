"""Operator HTTP endpoints, separate from the Streamlit UI (C1.2).

    GET /livez    200 while the process is up AND Streamlit answers its own health probe.
                  Never checks external dependencies (a DB outage must not restart the app).
    GET /readyz   200 only when the service can safely take traffic (readiness(): DB,
                  pgvector when required, schema at the code's Alembic head, production
                  configuration, pseudonymization key). 503 otherwise. Optional AI
                  providers never affect it.
    GET /version  release identity + runtime state (dss.core.release.version_document()).
    GET /metrics  Prometheus text format (dss/core/metrics_exporter.py). Bearer
                  EDUDSS_METRICS_TOKEN; without a token only loopback clients are served.
                  The reverse proxy publishes ONLY this path of the health port.

Why a separate process: Streamlit executes the app script only when a browser session
connects, so the app itself cannot answer readiness before the first user. This server
starts with the container (see Dockerfile CMD) on EDUDSS_HEALTH_PORT (default 8081).
Responses contain statuses, versions and revision ids only — no secrets, URLs or paths.
Readiness results are cached briefly so probes cannot hammer the database.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_CACHE_SECONDS = float(os.environ.get("EDUDSS_READINESS_CACHE_SECONDS", "5"))
_cache_lock = threading.Lock()
_cache: dict = {}


def _cached(key: str, producer):
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _CACHE_SECONDS:
            return hit[1]
    value = producer()
    with _cache_lock:
        _cache[key] = (now, value)
    return value


def streamlit_alive() -> bool:
    port = os.environ.get("STREAMLIT_PORT", "8501")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def livez() -> tuple[int, dict]:
    ui = streamlit_alive()
    return (200 if ui else 503), {"status": "alive" if ui else "ui_unavailable"}


def readyz() -> tuple[int, dict]:
    def compute():
        from dss.core.health_diagnostics import readiness
        from dss.core.runtime_mode import current_env

        result = readiness()
        if not streamlit_alive():
            result["status"] = "not_ready"
            result["checks"]["ui"] = {"status": "unavailable", "required": True}
        result["environment"] = current_env()
        return result

    result = _cached("readyz", compute)
    return (200 if result["status"] == "ready" else 503), result


def version() -> tuple[int, dict]:
    from dss.core.release import version_document

    return 200, _cached("version", version_document)


ROUTES = {
    "/livez": livez,
    "/readyz": readyz,
    "/version": version,
    # aliases commonly used by load balancers / the reverse proxy prefix
    "/healthz": livez,
}


class Handler(BaseHTTPRequestHandler):
    server_version = "edudss-health"
    sys_version = ""

    def do_GET(self):  # noqa: N802
        if self.path.split("?", 1)[0].rstrip("/") == "/metrics":
            self._metrics()
            return
        route = ROUTES.get(self.path.split("?", 1)[0].rstrip("/") or "/")
        if route is None:
            self._send(404, {"status": "not_found"})
            return
        try:
            code, body = route()
        except Exception:
            code, body = 503, {"status": "error"}
        self._send(code, body)

    def _metrics(self) -> None:
        try:
            from dss.core import metrics_exporter

            client_ip = self.client_address[0] if self.client_address else ""
            if not metrics_exporter.authorized(self.headers.get("Authorization"), client_ip):
                self._send(401, {"status": "unauthorized"})
                return
            payload, content_type = metrics_exporter.render()
        except Exception:
            self._send(503, {"status": "metrics_unavailable"})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send(self, code: int, body: dict) -> None:
        payload = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):  # probes every few seconds: keep logs quiet
        return


def serve(port: int | None = None, host: str = "0.0.0.0") -> ThreadingHTTPServer:
    port = int(port or os.environ.get("EDUDSS_HEALTH_PORT", "8081"))
    return ThreadingHTTPServer((host, port), Handler)


def probe(endpoint: str) -> int:
    """`python -m dss.core.health_server probe readyz` — for compose healthchecks and
    deploy scripts running inside the container (the health port is never published)."""
    port = os.environ.get("EDUDSS_HEALTH_PORT", "8081")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/{endpoint.strip('/')}", timeout=10) as resp:
            print(resp.read().decode("utf-8"))
            return 0
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", "replace"))
    except Exception as exc:
        print(json.dumps({"status": "unreachable", "error": type(exc).__name__}))
    return 1


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["probe"] and len(argv) == 2:
        return probe(argv[1])
    from dss.security.log_redaction import install_log_redaction

    install_log_redaction()
    server = serve()
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
