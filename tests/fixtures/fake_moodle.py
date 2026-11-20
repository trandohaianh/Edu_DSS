"""Máy chủ Moodle giả lập (Moodle 4.x Web Services REST, JSON) cho test connector.

Hình dạng JSON theo tài liệu API của Moodle (core_webservice_get_site_info,
core_user_get_users_by_field, core_enrol_get_users_courses, core_enrol_get_enrolled_users,
gradereport_user_get_grade_items, core_completion_get_activities_completion_status) và lỗi
``webservice_access_exception`` khi token sai hoặc hàm chưa được thêm vào external service.
"""
from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

TOKEN = "test-token-0123456789abcdef"
USERS = [
    {"id": 11, "username": "sv001", "idnumber": "SV001", "firstname": "An", "lastname": "Nguyễn", "fullname": "Nguyễn An"},
    {"id": 12, "username": "sv002", "idnumber": "", "firstname": "Bình", "lastname": "Trần", "fullname": "Trần Bình"},
    {"id": 90, "username": "gv01", "idnumber": "GV01", "firstname": "Hoa", "lastname": "Lê", "fullname": "Lê Hoa"},
]
COURSES = {
    101: {"id": 101, "shortname": "CTDL", "fullname": "Cấu trúc dữ liệu", "startdate": 1725148800, "enddate": 4102444800, "completed": False, "progress": 60},
    102: {"id": 102, "shortname": "XSTK", "fullname": "Xác suất thống kê", "startdate": 1725148800, "enddate": 1735603200, "completed": True, "progress": 100},
}
ENROL = {11: [101, 102], 12: [101], 90: [101, 102]}


def _item(iid, name, itype, module, raw, gmax=10.0, gmin=0.0, ts=1727740800):
    return {"id": iid, "itemname": name, "itemtype": itype, "itemmodule": module, "graderaw": raw,
            "grademin": gmin, "grademax": gmax, "gradedatesubmitted": ts, "gradedategraded": ts, "weightraw": 0.5}


GRADES = {
    (101, 11): [_item(1, "Quiz 1", "mod", "quiz", 18, gmax=20), _item(2, "Bài tập lớn", "mod", "assign", 85, gmax=100, ts=1730419200),
                _item(3, None, "course", None, 87.5, gmax=100)],
    (102, 11): [_item(4, "Kiểm tra giữa kỳ", "mod", "quiz", 3.5), _item(5, "Thi cuối kỳ", "mod", "assign", 4.0, ts=1733011200),
                _item(6, None, "course", None, 3.8)],
    (101, 12): [_item(1, "Quiz 1", "mod", "quiz", 8, gmax=20), _item(2, "Bài tập lớn", "mod", "assign", None, gmax=100),
                _item(3, None, "course", None, 40, gmax=100)],
}
COMPLETION = {(101, 11): [1, 1, 0, 2, 0], (102, 11): [1, 1, 1], (101, 12): [0, 0, 1, 0, 0]}
FUNCTIONS = ["core_webservice_get_site_info", "core_user_get_users_by_field", "core_enrol_get_users_courses",
             "core_enrol_get_enrolled_users", "gradereport_user_get_grade_items",
             "core_completion_get_activities_completion_status", "core_course_get_courses_by_field"]


def _arr(form, name):
    out, pat = [], re.compile(rf"^{re.escape(name)}\[(\d+)\]$")
    for k, v in form.items():
        m = pat.match(k)
        if m:
            out.append((int(m.group(1)), v))
    return [v for _, v in sorted(out)]


class _Handler(BaseHTTPRequestHandler):
    server_version = "FakeMoodle/4.4"

    def log_message(self, *args):
        pass

    def _send(self, body, status=200):
        raw = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):  # noqa: N802
        srv = self.server
        srv.calls += 1
        if srv.fail_next > 0:
            srv.fail_next -= 1
            return self._send({"error": "maintenance"}, 503)
        length = int(self.headers.get("Content-Length") or 0)
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
        srv.seen_query_strings.append(self.path)
        if self.path != "/webservice/rest/server.php":
            return self._send({"error": "not found"}, 404)
        if form.get("wstoken") != TOKEN:
            return self._send({"exception": "moodle_exception", "errorcode": "invalidtoken", "message": "Invalid token - token not found"})
        fn = form.get("wsfunction")
        if fn not in srv.functions:
            return self._send({"exception": "webservice_access_exception", "errorcode": "accessexception",
                               "message": "Access control exception"})
        uid = int(form["userid"]) if form.get("userid") else None
        cid = int(form["courseid"]) if form.get("courseid") else None
        if fn == "core_webservice_get_site_info":
            return self._send({"sitename": "LMS Trường Thử nghiệm", "username": "edudss_ws", "release": "4.4.3 (Build: 20240916)",
                               "version": "2024042203", "functions": [{"name": f, "version": "2024042203"} for f in srv.functions]})
        if fn == "core_user_get_users_by_field":
            field, values = form["field"], _arr(form, "values")
            return self._send([u for u in USERS if u.get(field) and u[field] in values])
        if fn == "core_enrol_get_users_courses":
            return self._send([COURSES[c] for c in ENROL.get(uid, [])])
        if fn == "core_enrol_get_enrolled_users":
            out = []
            for u in USERS:
                if cid in ENROL.get(u["id"], []):
                    role = "editingteacher" if u["username"].startswith("gv") else "student"
                    out.append({**u, "roles": [{"roleid": 3 if role != "student" else 5, "shortname": role}]})
            return self._send(out)
        if fn == "gradereport_user_get_grade_items":
            ugs = [{"courseid": c, "userid": u, "userfullname": next(x["fullname"] for x in USERS if x["id"] == u), "gradeitems": items}
                   for (c, u), items in GRADES.items() if c == cid and (uid is None or u == uid)]
            return self._send({"usergrades": ugs, "warnings": []})
        if fn == "core_course_get_courses_by_field":
            wanted = [int(form["value"])] if form.get("value") else list(COURSES)
            return self._send({"courses": [COURSES[c] for c in wanted if c in COURSES], "warnings": []})
        if fn == "core_completion_get_activities_completion_status":
            states = COMPLETION.get((cid, uid), [])
            return self._send({"statuses": [{"cmid": 1000 + i, "modname": "quiz", "state": s, "tracking": 1} for i, s in enumerate(states)],
                               "warnings": []})
        return self._send({"exception": "invalid_parameter_exception", "errorcode": "invalidparameter", "message": "?"})


class FakeMoodle:
    def __init__(self, functions=None):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.calls, self.httpd.fail_next, self.httpd.seen_query_strings = 0, 0, []
        self.httpd.functions = list(functions or FUNCTIONS)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
