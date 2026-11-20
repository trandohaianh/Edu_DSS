"""Deterministic external LMS/CMS simulator using a real HTTP process.

This service deliberately has no imports from ``dss``.  It represents an external
university system and can run as a separate host process or Docker container.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

TOKENS = {"sim-token-org-a": "org-a", "sim-token-org-b": "org-b"}
WEBHOOK_SECRET = "simulator-webhook-secret"
RESOURCES = (
    "users",
    "students",
    "lecturers",
    "courses",
    "enrollments",
    "assignments",
    "submissions",
    "grades",
    "attendance",
    "activities",
    "content",
)
ID_FIELDS = {
    "users": "user_external_id",
    "students": "student_external_id",
    "lecturers": "lecturer_external_id",
    "courses": "course_external_id",
    "enrollments": "enrollment_external_id",
    "assignments": "assignment_external_id",
    "submissions": "submission_external_id",
    "grades": "grade_external_id",
    "attendance": "attendance_external_id",
    "activities": "activity_external_id",
    "content": "content_external_id",
}


def _ts(minutes: int) -> str:
    return (datetime(2026, 1, 15, 8, 0, tzinfo=UTC) + timedelta(minutes=minutes)).isoformat()


def build_data() -> dict[str, list[dict[str, Any]]]:
    data = {name: [] for name in RESOURCES}
    for oi, org in enumerate(("org-a", "org-b")):
        prefix = "A" if oi == 0 else "B"
        lecturers = [f"lec-{prefix}-01", f"lec-{prefix}-02"]
        students = [f"stu-{prefix}-{n:02d}" for n in range(1, 5)]
        courses = [f"course-{prefix}-DATA", f"course-{prefix}-AI"]
        for i, lid in enumerate(lecturers):
            data["users"].append(
                {
                    "organization_id": org,
                    "user_external_id": f"user-{lid}",
                    "role": "lecturer",
                    "display_name": f"Lecturer {prefix}{i + 1}",
                    "updated_at": _ts(oi * 100 + i),
                }
            )
            data["lecturers"].append(
                {
                    "organization_id": org,
                    "lecturer_external_id": lid,
                    "user_external_id": f"user-{lid}",
                    "department": "Computer Science",
                    "updated_at": _ts(oi * 100 + i),
                }
            )
        for i, sid in enumerate(students):
            data["users"].append(
                {
                    "organization_id": org,
                    "user_external_id": f"user-{sid}",
                    "role": "student",
                    "display_name": f"Student {prefix}{i + 1}",
                    "updated_at": _ts(oi * 100 + 10 + i),
                }
            )
            data["students"].append(
                {
                    "organization_id": org,
                    "student_external_id": sid,
                    "user_external_id": f"user-{sid}",
                    "cohort": "2024",
                    "updated_at": _ts(oi * 100 + 10 + i),
                }
            )
        for i, cid in enumerate(courses):
            data["courses"].append(
                {
                    "organization_id": org,
                    "course_external_id": cid,
                    "lecturer_external_id": lecturers[i],
                    "title": f"{prefix} {'Data Engineering' if i == 0 else 'Applied AI'}",
                    "updated_at": _ts(oi * 100 + 20 + i),
                }
            )
            aid = f"assign-{prefix}-{i + 1:02d}"
            data["assignments"].append(
                {
                    "organization_id": org,
                    "assignment_external_id": aid,
                    "course_external_id": cid,
                    "title": f"Project {i + 1}",
                    "due_at": _ts(oi * 100 + 80 + i),
                    "updated_at": _ts(oi * 100 + 30 + i),
                }
            )
            content_id = f"content-{prefix}-{i + 1:02d}"
            data["content"].append(
                {
                    "organization_id": org,
                    "content_external_id": content_id,
                    "course_external_id": cid,
                    "title": f"Lesson {i + 1}",
                    "body": f"Deterministic lesson for tenant {org} course {cid}.",
                    "version": 1,
                    "updated_at": _ts(oi * 100 + 35 + i),
                }
            )
            for j, sid in enumerate(students):
                eid = f"enroll-{prefix}-{i + 1}-{j + 1}"
                subid = f"submit-{prefix}-{i + 1}-{j + 1}"
                data["enrollments"].append(
                    {
                        "organization_id": org,
                        "enrollment_external_id": eid,
                        "student_external_id": sid,
                        "course_external_id": cid,
                        "status": "active",
                        "updated_at": _ts(oi * 100 + 40 + j),
                    }
                )
                data["submissions"].append(
                    {
                        "organization_id": org,
                        "submission_external_id": subid,
                        "assignment_external_id": aid,
                        "student_external_id": sid,
                        "status": "submitted",
                        "submitted_at": _ts(oi * 100 + 50 + j),
                        "updated_at": _ts(oi * 100 + 50 + j),
                    }
                )
                data["grades"].append(
                    {
                        "organization_id": org,
                        "grade_external_id": f"grade-{prefix}-{i + 1}-{j + 1}",
                        "submission_external_id": subid,
                        "student_external_id": sid,
                        "course_external_id": cid,
                        "score": 72 + i * 5 + j,
                        "updated_at": _ts(oi * 100 + 60 + j),
                    }
                )
                data["attendance"].append(
                    {
                        "organization_id": org,
                        "attendance_external_id": f"att-{prefix}-{i + 1}-{j + 1}",
                        "student_external_id": sid,
                        "course_external_id": cid,
                        "present": j != 3,
                        "occurred_at": _ts(oi * 100 + 65 + j),
                        "updated_at": _ts(oi * 100 + 65 + j),
                    }
                )
                data["activities"].append(
                    {
                        "organization_id": org,
                        "activity_external_id": f"act-{prefix}-{i + 1}-{j + 1}",
                        "student_external_id": sid,
                        "course_external_id": cid,
                        "activity_type": "lesson.viewed",
                        "duration_seconds": 600 + j * 60,
                        "occurred_at": _ts(oi * 100 + 70 + j),
                        "updated_at": _ts(oi * 100 + 70 + j),
                    }
                )
    return data


DATA = build_data()
RATE_ATTEMPTS: dict[str, int] = {}


def build_events(org: str) -> list[dict[str, Any]]:
    prefix = "A" if org == "org-a" else "B"
    return [
        {
            "event_id": f"evt-{prefix}-submission-1",
            "organization_id": org,
            "event_type": "submission.created",
            "occurred_at": _ts(200),
            "data": next(x for x in DATA["submissions"] if x["organization_id"] == org),
        },
        {
            "event_id": f"evt-{prefix}-grade-1",
            "organization_id": org,
            "event_type": "grade.updated",
            "occurred_at": _ts(210),
            "data": next(x for x in DATA["grades"] if x["organization_id"] == org),
        },
        {
            "event_id": f"evt-{prefix}-content-1",
            "organization_id": org,
            "event_type": "content.updated",
            "occurred_at": _ts(220),
            "data": {
                **next(x for x in DATA["content"] if x["organization_id"] == org),
                "version": 2,
                "body": f"Updated deterministic lesson for {org}.",
            },
        },
    ]


class Handler(BaseHTTPRequestHandler):
    server_version = "EduDSS-Simulator/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _json(self, status: int, payload: Any, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _auth(self, query: dict[str, list[str]]) -> str | None:
        raw = self.headers.get("Authorization", "")
        token = raw[7:] if raw.startswith("Bearer ") else ""
        org = TOKENS.get(token)
        if not org:
            self._json(401, {"error": {"code": "unauthorized", "message": "valid bearer token required"}})
            return None
        requested = self.headers.get("X-Organization-ID") or query.get("organization_id", [org])[0]
        if requested != org:
            self._json(
                403, {"error": {"code": "tenant_forbidden", "message": "token cannot access requested organization"}}
            )
            return None
        return org

    def _scenario(self, query: dict[str, list[str]]) -> bool:
        scenario = query.get("scenario", [""])[0]
        if scenario == "500":
            self._json(500, {"error": {"code": "simulated_internal_error"}})
            return True
        if scenario == "timeout":
            time.sleep(float(query.get("delay", ["1.0"])[0]))
            return False
        if scenario == "malformed":
            body = b'{"items": ['
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return True
        if scenario == "429":
            key = self.headers.get("X-Request-ID", "default")
            RATE_ATTEMPTS[key] = RATE_ATTEMPTS.get(key, 0) + 1
            if RATE_ATTEMPTS[key] <= 2:
                self._json(
                    429, {"error": {"code": "rate_limited", "attempt": RATE_ATTEMPTS[key]}}, {"Retry-After": "0.05"}
                )
                return True
        return False

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/health":
            self._json(200, {"status": "ok", "service": "simulated-university-lms-cms"})
            return
        if not parsed.path.startswith("/api/"):
            self._json(404, {"error": {"code": "not_found"}})
            return
        org = self._auth(query)
        if not org or self._scenario(query):
            return
        resource = parsed.path.removeprefix("/api/")
        if resource == "events":
            items = build_events(org)
        elif resource in DATA:
            items = [dict(x) for x in DATA[resource] if x["organization_id"] == org]
        else:
            self._json(404, {"error": {"code": "not_found", "resource": resource}})
            return
        if query.get("scenario", [""])[0] == "invalid_payload":
            items = [{"organization_id": org, "updated_at": _ts(1)}]
        since = query.get("updated_since", [None])[0]
        if since:
            key = "occurred_at" if resource == "events" else "updated_at"
            items = [x for x in items if x.get(key, "") > since]
        if query.get("duplicate", ["0"])[0] == "1" and items:
            items.insert(1, dict(items[0]))
        page = max(1, int(query.get("page", ["1"])[0]))
        page_size = min(100, max(1, int(query.get("page_size", ["3"])[0])))
        start = (page - 1) * page_size
        selected = items[start : start + page_size]
        next_page = page + 1 if start + page_size < len(items) else None
        self._json(
            200,
            {
                "items": selected,
                "page": page,
                "page_size": page_size,
                "next_page": next_page,
                "total": len(items),
                "organization_id": org,
            },
        )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/admin/mutate":
            org = self._auth(query)
            if not org:
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                request_data = json.loads(self.rfile.read(length) or b"{}")
                resource = request_data["resource"]
                external_id = request_data["external_id"]
                changes = request_data["changes"]
                id_field = ID_FIELDS[resource]
                row = next(
                    item for item in DATA[resource] if item["organization_id"] == org and item[id_field] == external_id
                )
                if not isinstance(changes, dict):
                    raise ValueError("changes must be an object")
                row.update(changes)
            except (ValueError, KeyError, StopIteration, json.JSONDecodeError):
                self._json(400, {"error": {"code": "invalid_mutation"}})
                return
            self._json(200, {"status": "updated", "record": row})
            return
        if parsed.path != "/api/webhooks/deliver":
            self._json(404, {"error": {"code": "not_found"}})
            return
        org = self._auth(query)
        if not org:
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request_data = json.loads(self.rfile.read(length) or b"{}")
            callback = request_data["callback_url"]
        except (ValueError, KeyError, json.JSONDecodeError):
            self._json(400, {"error": {"code": "invalid_delivery_request"}})
            return
        events = build_events(org)
        mode = request_data.get("mode", "normal")
        if mode == "duplicate":
            events = [events[0], dict(events[0])]
        elif mode == "out_of_order":
            events = [
                events[1],
                {
                    **events[1],
                    "event_id": events[1]["event_id"] + "-old",
                    "occurred_at": _ts(205),
                    "data": {**events[1]["data"], "score": 1},
                },
            ]
        elif mode == "invalid":
            events = [
                {
                    "event_id": "invalid",
                    "organization_id": org,
                    "event_type": "unknown",
                    "occurred_at": _ts(1),
                    "data": {},
                }
            ]
        elif mode == "wrong_tenant":
            events = [{**events[0], "organization_id": "org-b" if org == "org-a" else "org-a"}]
        delivered = []
        for event in events:
            body = json.dumps(event).encode("utf-8")
            signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
            attempts = 0
            status = 0
            while attempts < 3:
                attempts += 1
                req = urllib.request.Request(
                    callback,
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json", "X-Simulator-Signature": signature},
                )
                try:
                    with urllib.request.urlopen(req, timeout=2) as response:
                        status = response.status
                    break
                except urllib.error.HTTPError as exc:
                    status = exc.code
                    if status not in (429, 500, 502, 503):
                        break
                    time.sleep(0.05 * attempts)
                except OSError:
                    status = 599
                    time.sleep(0.05 * attempts)
            delivered.append({"event_id": event.get("event_id"), "status": status, "attempts": attempts})
        self._json(200, {"deliveries": delivered})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"simulator_listening={args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
