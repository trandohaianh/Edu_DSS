"""Real-HTTP connector for the separate simulated university LMS/CMS.

Persistence is intentionally behind ``IntegrationBoundary``. Workstream B can supply a
PostgreSQL implementation without changing transport, validation, mapping or webhook code.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol

import requests

from dss.core.observability import observed

logger = logging.getLogger(__name__)
RESOURCES = ("users", "students", "lecturers", "courses", "enrollments", "assignments", "submissions", "grades", "attendance", "activities", "content")
ID_FIELDS = {"users":"user_external_id","students":"student_external_id","lecturers":"lecturer_external_id","courses":"course_external_id","enrollments":"enrollment_external_id","assignments":"assignment_external_id","submissions":"submission_external_id","grades":"grade_external_id","attendance":"attendance_external_id","activities":"activity_external_id","content":"content_external_id"}
EVENT_TYPES = {"submission.created": "submissions", "grade.updated": "grades", "content.updated": "content"}


class IntegrationError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int | None = None, retryable: bool = False):
        super().__init__(message); self.code = code; self.status = status; self.retryable = retryable


class IntegrationBoundary(Protocol):
    def upsert(self, resource: str, internal_id: str, record: dict[str, Any]) -> bool: ...
    def on_content_updated(self, record: dict[str, Any]) -> None: ...


@dataclass
class InMemoryIntegrationBoundary:
    """Test/demo boundary, not a competing persistence architecture."""
    records: dict[str, dict[str, dict[str, Any]]] = field(default_factory=lambda: {r: {} for r in RESOURCES})
    audit: list[dict[str, Any]] = field(default_factory=list)
    rag_invalidations: list[str] = field(default_factory=list)

    def upsert(self, resource: str, internal_id: str, record: dict[str, Any]) -> bool:
        previous = self.records[resource].get(internal_id); changed = previous != record
        self.records[resource][internal_id] = dict(record)
        self.audit.append({"operation": "upsert", "resource": resource, "internal_id": internal_id, "changed": changed})
        return changed

    def on_content_updated(self, record: dict[str, Any]) -> None:
        content_id = record["content_external_id"]
        self.rag_invalidations.append(content_id)
        self.audit.append({"operation": "rag.invalidate_and_reindex.requested", "content_external_id": content_id})


@dataclass
class ExternalIdMapper:
    mappings: dict[tuple[str, str, str], str] = field(default_factory=dict)

    def resolve(self, organization_id: str, resource: str, external_id: str) -> str:
        key = (organization_id, resource, external_id)
        if key not in self.mappings:
            self.mappings[key] = str(uuid.uuid5(uuid.NAMESPACE_URL, ":".join(key)))
        return self.mappings[key]


def validate_record(resource: str, record: Any, organization_id: str) -> dict[str, Any]:
    if resource not in ID_FIELDS or not isinstance(record, dict):
        raise IntegrationError("invalid_payload", "resource record must be an object")
    required = {"organization_id", ID_FIELDS[resource], "updated_at"}
    missing = sorted(required - set(record))
    if missing: raise IntegrationError("invalid_payload", f"missing required fields: {','.join(missing)}")
    if record["organization_id"] != organization_id: raise IntegrationError("tenant_mismatch", "record organization does not match connector")
    try: datetime.fromisoformat(str(record["updated_at"]).replace("Z", "+00:00"))
    except ValueError as exc: raise IntegrationError("invalid_payload", "updated_at must be ISO-8601") from exc
    return record


class LMSCMSConnector:
    def __init__(self, base_url: str, token: str, organization_id: str, *, timeout: float = 2.0, max_attempts: int = 3, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/"); self.token = token; self.organization_id = organization_id; self.timeout = timeout; self.max_attempts = max_attempts; self.session = session or requests.Session(); self.mapper = ExternalIdMapper()

    def health(self) -> dict[str, Any]:
        try: response = self.session.get(f"{self.base_url}/health", timeout=self.timeout); response.raise_for_status(); return response.json()
        except (requests.RequestException, ValueError) as exc: raise IntegrationError("health_failed", "simulator health check failed", retryable=True) from exc

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}", "X-Organization-ID": self.organization_id, "X-Request-ID": str(uuid.uuid4())}
        last: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(f"{self.base_url}{path}", headers=headers, params=params, timeout=self.timeout)
                if response.status_code in (429, 500, 502, 503, 504) and attempt < self.max_attempts:
                    delay = float(response.headers.get("Retry-After", 0.05 * (2 ** (attempt-1)))); time.sleep(min(delay, 0.5)); continue
                if response.status_code >= 400:
                    codes = {401:"unauthorized",403:"tenant_forbidden",404:"not_found",429:"rate_limited",500:"server_error"}
                    raise IntegrationError(codes.get(response.status_code,"http_error"), f"simulator returned HTTP {response.status_code}", status=response.status_code, retryable=response.status_code in (429,500,502,503,504))
                try: payload = response.json()
                except ValueError as exc: raise IntegrationError("malformed_json", "simulator returned malformed JSON") from exc
                if not isinstance(payload, dict): raise IntegrationError("invalid_payload", "response must be an object")
                return payload
            except (requests.Timeout, requests.ConnectionError) as exc:
                last = exc
                if attempt < self.max_attempts: time.sleep(min(0.05 * (2 ** (attempt-1)), 0.5)); continue
                raise IntegrationError("timeout", "simulator request timed out", retryable=True) from exc
        raise IntegrationError("transport_error", "simulator request failed", retryable=True) from last

    @observed("lms.sync.page", metadata=lambda self, resource, **kwargs: {"resource": resource})
    def fetch(self, resource: str, *, updated_since: str | None = None, page_size: int = 100, scenario: str | None = None, duplicate: bool = False) -> list[dict[str, Any]]:
        if resource not in RESOURCES: raise ValueError(f"unknown resource: {resource}")
        page = 1; result: list[dict[str, Any]] = []; seen: set[str] = set(); id_field = ID_FIELDS[resource]
        while page:
            params: dict[str, Any] = {"page": page, "page_size": page_size}
            if updated_since: params["updated_since"] = updated_since
            if scenario: params["scenario"] = scenario
            if duplicate: params["duplicate"] = "1"
            payload = self._get(f"/api/{resource}", params)
            if payload.get("organization_id") != self.organization_id or not isinstance(payload.get("items"), list): raise IntegrationError("invalid_payload", "invalid paginated response envelope")
            for raw in payload["items"]:
                record = validate_record(resource, raw, self.organization_id); external_id = str(record[id_field])
                if external_id not in seen: seen.add(external_id); result.append(record)
            page = payload.get("next_page")
            if page is not None and not isinstance(page, int): raise IntegrationError("invalid_payload", "next_page must be integer or null")
        return result

    @observed("lms.sync.all")
    def sync(self, boundary: IntegrationBoundary, *, updated_since: str | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for resource in RESOURCES:
            records = self.fetch(resource, updated_since=updated_since)
            changed = 0
            for record in records:
                external_id = str(record[ID_FIELDS[resource]]); internal_id = self.mapper.resolve(self.organization_id, resource, external_id)
                changed += int(boundary.upsert(resource, internal_id, record))
            counts[resource] = changed
        return counts


class WebhookProcessor:
    def __init__(self, organization_id: str, secret: str, boundary: IntegrationBoundary, mapper: ExternalIdMapper | None = None):
        self.organization_id = organization_id; self.secret = secret; self.boundary = boundary; self.mapper = mapper or ExternalIdMapper(); self.seen_events: set[str] = set(); self.latest_by_entity: dict[tuple[str,str], str] = {}

    def process(self, body: bytes, signature: str) -> tuple[int, dict[str, Any]]:
        expected = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature or ""): return 401, {"status":"invalid_signature"}
        try: event = json.loads(body)
        except json.JSONDecodeError: return 400, {"status":"invalid_event"}
        if not isinstance(event, dict) or event.get("event_type") not in EVENT_TYPES or not all(event.get(k) for k in ("event_id","organization_id","occurred_at")) or not isinstance(event.get("data"), dict): return 400, {"status":"invalid_event"}
        if event["organization_id"] != self.organization_id: return 403, {"status":"wrong_tenant"}
        if event["event_id"] in self.seen_events: return 200, {"status":"duplicate"}
        resource = EVENT_TYPES[event["event_type"]]; data = dict(event["data"]); data.setdefault("updated_at", event["occurred_at"])
        try: validate_record(resource, data, self.organization_id)
        except IntegrationError: return 400, {"status":"invalid_event"}
        external_id = str(data[ID_FIELDS[resource]]); entity = (resource, external_id); latest = self.latest_by_entity.get(entity)
        self.seen_events.add(event["event_id"])
        if latest and event["occurred_at"] < latest: return 200, {"status":"out_of_order_ignored"}
        self.latest_by_entity[entity] = event["occurred_at"]
        internal_id = self.mapper.resolve(self.organization_id, resource, external_id); self.boundary.upsert(resource, internal_id, data)
        if event["event_type"] == "content.updated": self.boundary.on_content_updated(data)
        return 200, {"status":"processed"}


class WebhookReceiver:
    def __init__(self, processor: WebhookProcessor, host: str = "127.0.0.1", port: int = 0, transient_failures: int = 0, advertised_host: str | None = None):
        self.processor = processor; self.transient_failures = transient_failures
        self.advertised_host = advertised_host or "127.0.0.1"
        outer = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None: return
            def do_POST(self) -> None:
                if self.path != "/webhooks/lms-cms": self.send_error(404); return
                if outer.transient_failures > 0:
                    outer.transient_failures -= 1; payload=b'{"status":"retry"}'; self.send_response(429); self.send_header("Retry-After","0.05")
                else:
                    body=self.rfile.read(int(self.headers.get("Content-Length","0"))); status,result=outer.processor.process(body,self.headers.get("X-Simulator-Signature","")); payload=json.dumps(result).encode(); self.send_response(status)
                self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(payload))); self.end_headers(); self.wfile.write(payload)
        self.server = ThreadingHTTPServer((host, port), Handler); self.thread: threading.Thread | None = None

    @property
    def url(self) -> str: return f"http://{self.advertised_host}:{self.server.server_port}/webhooks/lms-cms"
    def start(self) -> None: self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
    def stop(self) -> None: self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2) if self.thread else None
