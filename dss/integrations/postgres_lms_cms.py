"""Durable integration glue from the simulated LMS/CMS transport to Workstream B."""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import secrets
import threading
from dataclasses import dataclass
from typing import Any

from dss.core.observability import observed
from dss.db.repositories import domain_persistence_repository as domain_repo
from dss.db.repositories.user_repository import UserRepository
from dss.services.chunking_service import DocumentChunk
from dss.services.cms_rag_lifecycle import upsert_and_reindex
from dss.services.vector_store import BaseVectorStore, PgVectorStore
from dss.integrations.lms_cms_connector import (
    EVENT_TYPES, ID_FIELDS, IntegrationError, LMSCMSConnector, validate_record,
)

_SYNC_LOCKS: dict[int, threading.Lock] = {}
_SYNC_LOCKS_GUARD = threading.Lock()
_ROLE_MAP = {"student": "Sinh viên", "lecturer": "Giảng viên / CVHT", "admin": "Admin"}


def deterministic_embedding(text: str) -> list[float]:
    """Stable local 384-dimensional embedding for deterministic integration tests."""
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    values = [((seed[i % len(seed)] / 255.0) * 2.0) - 1.0 for i in range(384)]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def _sync_lock(organization_id: int) -> threading.Lock:
    with _SYNC_LOCKS_GUARD:
        return _SYNC_LOCKS.setdefault(organization_id, threading.Lock())


@dataclass
class PostgresIntegrationBoundary:
    organization_id: int
    external_organization_id: str
    vector_store: BaseVectorStore

    @classmethod
    def create(cls, organization_id: int, external_organization_id: str, database_url: str):
        return cls(organization_id, external_organization_id, PgVectorStore(database_url, organization_id=organization_id))

    def _tenant_record(self, record: dict[str, Any]) -> dict[str, Any]:
        if str(record.get("organization_id")) != self.external_organization_id:
            raise IntegrationError("tenant_mismatch", "record organization does not match persistence boundary")
        return {**record, "organization_id": self.organization_id}

    @observed("integration.record.upsert", metadata=lambda self, resource, internal_id, record: {"backend": "postgresql"})
    def upsert(self, resource: str, internal_id: str, record: dict[str, Any]) -> bool:
        if resource == "users":
            repo = UserRepository(self.organization_id)
            username = str(record["user_external_id"])
            existing = repo.get_user_by_username(username)
            role = _ROLE_MAP.get(str(record.get("role", "student")).lower(), "Sinh viên")
            student_id = username.removeprefix("user-") if role == "Sinh viên" else None
            if existing is None:
                repo.create_user(username, secrets.token_urlsafe(32), role, student_id=student_id, auto_provisioned=True)
                return True
            changed = existing.get("role") != role or existing.get("student_id") != student_id
            if existing.get("role") != role:
                repo.change_role(username, role)
            if student_id and existing.get("student_id") != student_id:
                repo.update_user(username, student_id=student_id)
            return changed
        if resource == "content":
            previous = domain_repo.get_cms_content(self.organization_id, str(record["content_external_id"]))
            body = str(record.get("body", ""))
            version = int(record.get("version", 1))
            document_id = f"{record['content_external_id']}:v{version}"
            chunk = DocumentChunk(
                # rag_chunks.chunk_id is globally unique in the accepted schema;
                # prefix it with the internal tenant key so identical external CMS
                # IDs in different organizations cannot collide before RLS applies.
                chunk_id=f"org-{self.organization_id}:{document_id}#c1", document_id=document_id,
                course_id=str(record.get("course_external_id") or "GEN_COURSE"),
                content=body, token_count=max(1, len(body.split())),
                embedding=deterministic_embedding(body),
                metadata={"content_external_id": record["content_external_id"], "version": version, "source": "simulated_cms"},
            )
            upsert_and_reindex(self.organization_id, self._tenant_record(record), [chunk], self.vector_store)
            return previous is None or previous.get("version") != version or previous.get("checksum_sha256") != hashlib.sha256(body.encode()).hexdigest()
        result = domain_repo.upsert_external(self.organization_id, resource, self._tenant_record(record))
        return bool(result["created"])

    def on_content_updated(self, record: dict[str, Any]) -> None:
        self.upsert("content", "", record)


class PersistentSyncService:
    def __init__(self, connector: LMSCMSConnector, boundary: PostgresIntegrationBoundary, source: str = "simulated-lms-cms"):
        self.connector = connector
        self.boundary = boundary
        self.source = source

    @observed("integration.sync.resource", metadata=lambda self, resource, **kwargs: {"backend": "postgresql"})
    def sync_resource(self, resource: str, *, incremental: bool = False, page_size: int = 100, scenario: str | None = None) -> dict[str, Any]:
        with _sync_lock(self.boundary.organization_id):
            state = domain_repo.get_sync_state(self.boundary.organization_id, self.source, resource) if incremental else None
            cursor = state.get("cursor") if state else None
            try:
                records = self.connector.fetch(resource, updated_since=cursor, page_size=page_size, scenario=scenario)
                changed = 0
                for record in records:
                    external_id = str(record[ID_FIELDS[resource]])
                    internal_id = self.connector.mapper.resolve(self.connector.organization_id, resource, external_id)
                    changed += int(self.boundary.upsert(resource, internal_id, record))
                next_cursor = max((str(row["updated_at"]) for row in records), default=cursor)
                domain_repo.set_sync_state(self.boundary.organization_id, self.source, resource, cursor=next_cursor, status="success")
                return {"resource": resource, "fetched": len(records), "changed": changed, "cursor": next_cursor}
            except Exception as exc:
                domain_repo.set_sync_state(self.boundary.organization_id, self.source, resource, cursor=cursor, status="failed", error_code=type(exc).__name__)
                raise

    @observed("integration.sync.all", metadata=lambda self, **kwargs: {"backend": "postgresql"})
    def sync_all(self, *, incremental: bool = False, page_size: int = 100) -> dict[str, dict[str, Any]]:
        return {resource: self.sync_resource(resource, incremental=incremental, page_size=page_size) for resource in ID_FIELDS}


class DurableWebhookProcessor:
    def __init__(self, organization_id: int, external_organization_id: str, secret: str, boundary: PostgresIntegrationBoundary, source: str = "simulated-lms-cms"):
        self.organization_id = organization_id
        self.external_organization_id = external_organization_id
        self.secret = secret
        self.boundary = boundary
        self.source = source

    @observed("integration.webhook.process", metadata=lambda self, body, signature: {"backend": "postgresql"})
    def process(self, body: bytes, signature: str) -> tuple[int, dict[str, Any]]:
        expected = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature or ""):
            return 401, {"status": "invalid_signature"}
        try:
            event = json.loads(body)
        except json.JSONDecodeError:
            return 400, {"status": "invalid_event"}
        if not isinstance(event, dict) or event.get("event_type") not in EVENT_TYPES or not all(event.get(key) for key in ("event_id", "organization_id", "occurred_at")) or not isinstance(event.get("data"), dict):
            return 400, {"status": "invalid_event"}
        if str(event["organization_id"]) != self.external_organization_id:
            return 403, {"status": "wrong_tenant"}
        resource = EVENT_TYPES[event["event_type"]]
        data = dict(event["data"])
        data.setdefault("updated_at", event["occurred_at"])
        try:
            validate_record(resource, data, self.external_organization_id)
            decision = domain_repo.receive_event(self.organization_id, self.source, {
                "organization_id": self.organization_id, "event_id": event["event_id"],
                "event_type": event["event_type"], "external_entity_id": data[ID_FIELDS[resource]],
                "source_timestamp": event["occurred_at"], "payload": data,
            })
            if decision["status"] in {"duplicate", "out_of_order"}:
                return 200, {"status": decision["status"]}
            external_id = str(data[ID_FIELDS[resource]])
            internal_id = hashlib.sha256(f"{self.external_organization_id}:{resource}:{external_id}".encode()).hexdigest()
            self.boundary.upsert(resource, internal_id, data)
            domain_repo.mark_event(self.organization_id, event["event_id"], status="processed")
            return 200, {"status": "processed"}
        except (IntegrationError, KeyError, ValueError):
            return 400, {"status": "invalid_event"}
