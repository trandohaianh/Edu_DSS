"""C1.1 — PostgreSQL is never exposed on all interfaces; production has one public
entry point (the TLS reverse proxy) with security headers."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

APP = Path(__file__).resolve().parents[1]
PROD = APP / "deploy" / "production"


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_dev_compose_binds_every_published_port_to_loopback_by_default():
    compose = _load(APP / "docker-compose.yml")
    for name, svc in compose["services"].items():
        for port in svc.get("ports", []):
            host_part = str(port).rsplit(":", 1)[0]
            assert host_part.startswith("${EDUDSS_BIND_ADDR:-127.0.0.1}") or host_part.startswith(
                "${DB_BIND_ADDR:-127.0.0.1}"
            ), f"{name} publishes {port} on all interfaces by default"


def test_production_database_and_app_publish_no_ports():
    compose = _load(PROD / "docker-compose.prod.yml")
    services = compose["services"]
    for name in ("postgres", "app", "migrate"):
        assert not services[name].get("ports"), f"{name} must not publish a host port in production"
    assert services["postgres"]["networks"] == ["backend"]
    assert compose["networks"]["backend"]["internal"] is True
    assert sorted(str(p) for p in services["proxy"]["ports"]) == ["443:443", "80:80"]


def test_production_app_runs_in_production_mode_with_required_secrets():
    env = _load(PROD / "docker-compose.prod.yml")["services"]["app"]["environment"]
    assert env["EDUDSS_ENV"] == "production"
    assert ":?" in env["EDUDSS_PSEUDONYM_KEY"]  # deployment refuses to start without the key
    assert "${DB_APP_USER}" in env["DATABASE_URL"]  # app connects as the non-superuser (RLS applies)


def test_caddyfile_terminates_tls_and_sets_security_headers():
    caddy = (PROD / "Caddyfile").read_text(encoding="utf-8")
    # Bước 9: nhiều bản app — Caddy tìm qua DNS (`dynamic a app 8501`), không còn một upstream cố định.
    assert "{$EDUDSS_DOMAIN}" in caddy and "dynamic a app 8501" in caddy
    for header in (
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Content-Security-Policy",
        "Permissions-Policy",
    ):
        assert header in caddy
    assert re.search(r"connect-src[^\"]*wss:", caddy)  # Streamlit WebSocket allowed
    assert "-Server" in caddy


def test_production_env_template_holds_no_secret_values():
    for line in (PROD / "production.env.example").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if any(t in key for t in ("PASSWORD", "KEY", "TOKEN", "SECRET")) and not key.endswith("_VERSION"):
                assert value.strip() == "", f"{key} must be blank in the template"


def test_filled_production_env_is_git_ignored():
    rules = (APP / ".gitignore").read_text(encoding="utf-8")
    assert "deploy/**/*.env" in rules
