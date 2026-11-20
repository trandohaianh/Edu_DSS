"""Connector Moodle Web Services chạy với máy chủ Moodle giả lập (tests/fixtures/fake_moodle.py)."""
import pytest

from dss.services.moodle_connector import MoodleClient, MoodleError, MoodleLMSRepository, _flatten, to_ten
from tests.fixtures.fake_moodle import TOKEN, FakeMoodle


@pytest.fixture()
def moodle():
    with FakeMoodle() as fm:
        yield fm


def client(fm, token=TOKEN):
    return MoodleClient(fm.url, token, allow_insecure=True, retries=2, timeout_s=5)


def test_requires_https_except_local_test_server():
    with pytest.raises(ValueError):
        MoodleClient("http://lms.truong.edu.vn", "t")
    with pytest.raises(ValueError):
        MoodleClient("http://lms.truong.edu.vn", "t", allow_insecure=True)   # chỉ localhost
    with pytest.raises(ValueError):
        MoodleClient("https://lms.truong.edu.vn", "")


def test_check_connection_reports_missing_functions():
    with FakeMoodle(functions=["core_webservice_get_site_info", "core_user_get_users_by_field"]) as fm:
        status = client(fm).check_connection()
    assert status["ok"] is False and status["site"] == "LMS Trường Thử nghiệm"
    assert "gradereport_user_get_grade_items" in status["missing_functions"]


def test_bad_token_raises_without_retry(moodle):
    with pytest.raises(MoodleError) as err:
        client(moodle, "wrong").site_info()
    assert err.value.errorcode == "invalidtoken"
    assert moodle.httpd.calls == 1


def test_token_never_in_url(moodle):
    client(moodle).site_info()
    assert all(TOKEN not in q for q in moodle.httpd.seen_query_strings)


def test_retries_transient_5xx(moodle):
    moodle.httpd.fail_next = 2
    assert client(moodle).check_connection()["ok"] is True
    assert moodle.httpd.calls == 3


def test_summary_maps_grades_progress_and_subjects(moodle):
    s = MoodleLMSRepository(client(moodle)).get_student_learning_summary("SV001")
    assert s.course_grades == {"Cấu trúc dữ liệu": 8.75, "Xác suất thống kê": 3.8}
    assert s.strong_subjects == ["Cấu trúc dữ liệu"] and s.weak_subjects == ["Xác suất thống kê"]
    assert s.gpa == round((8.75 + 3.8) / 2, 2)
    assert s.average_progress == round((60.0 + 100.0) / 2, 1)          # 3/5 hoạt động và 3/3
    scores = {r.title: r.score for r in s.assessment_history}
    assert scores["Quiz 1"] == 9.0 and scores["Bài tập lớn"] == 8.5     # 18/20, 85/100 -> thang 10
    types = {r.title: r.assessment_type for r in s.assessment_history}
    assert types["Kiểm tra giữa kỳ"] == "midterm" and types["Thi cuối kỳ"] == "final"


def test_falls_back_to_username_when_idnumber_empty(moodle):
    s = MoodleLMSRepository(client(moodle)).get_student_learning_summary("sv002")
    assert s.course_grades == {"Cấu trúc dữ liệu": 4.0}
    assert [r.title for r in s.assessment_history] == ["Quiz 1"]        # bài chưa chấm (graderaw null) bị bỏ


def test_unknown_student(moodle):
    with pytest.raises(LookupError):
        MoodleLMSRepository(client(moodle)).get_student_learning_summary("SV999")


def test_roster_only_students(moodle):
    rows = MoodleLMSRepository(client(moodle)).course_roster_grades(101)
    assert {r["student_id"] for r in rows} == {"SV001", "sv002"}         # giảng viên bị loại
    assert {r["student_id"]: r["course_total"] for r in rows} == {"SV001": 8.75, "sv002": 4.0}


def test_read_only(moodle):
    with pytest.raises(PermissionError):
        MoodleLMSRepository(client(moodle)).record_learning_action("SV001", "CTDL", "x", 5)


def test_helpers():
    assert _flatten({"field": "idnumber", "values": ["A", "B"], "criteria": [{"key": "k", "value": 1}]}) == {
        "field": "idnumber", "values[0]": "A", "values[1]": "B", "criteria[0][key]": "k", "criteria[0][value]": 1}
    assert to_ten(15, 0, 20) == 7.5 and to_ten(None, 0, 10) is None and to_ten(5, 10, 10) is None
