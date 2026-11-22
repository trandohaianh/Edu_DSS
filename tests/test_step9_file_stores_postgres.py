"""Bước 9 (22/11/2026): các kho tệp chuyển sang PostgreSQL (docs/architecture/STEP9_FILE_STORES_TO_POSTGRES.md).

Chạy trên PostgreSQL thật đã migrate tới head; bỏ qua (không giả lập) khi không có DATABASE_URL.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from dss.db.session import is_database_configured

pytestmark = pytest.mark.skipif(not is_database_configured(), reason="cần PostgreSQL thật (DATABASE_URL)")

TID_S9 = f"train_s9_{uuid.uuid4().hex[:8]}"
ALL_STORES = ("PREDICTIONS", "CONSULTATIONS", "ACTIVITY", "AI_TOKEN_USAGE", "SUBSCRIPTION", "ADMIN_AI_CONFIG")


@pytest.fixture()
def org_id(monkeypatch, tmp_path):
    from dss.db.models import Organization
    from dss.db.session import session_scope

    with session_scope() as session:
        org = Organization(org_code=f"S9_{uuid.uuid4().hex[:8]}", name="Bước 9")
        session.add(org)
        session.flush()
        oid = org.id
    monkeypatch.setenv("EDUDSS_ORGANIZATION_ID", str(oid))
    monkeypatch.setenv("EDUDSS_DATA_ROOT", str(tmp_path / "root"))
    return oid


def _enable(monkeypatch, *features):
    for f in features:
        monkeypatch.setenv(f"EDUDSS_{f}_STORE", "postgres")


@pytest.fixture()
def actor(monkeypatch):
    who = {"username": "gv.tuvan", "role": "Giảng viên / CVHT"}
    monkeypatch.setattr("dss.core.warehouse._current_actor", lambda: dict(who))
    return who


def _warehouse(tmp_path):
    from dss.core.warehouse import DataWarehouse

    return DataWarehouse(base_path=str(tmp_path / "wh"))


# ---------------------------------------------------------------- đợt A: thuê bao
def test_subscription_on_postgres_gets_an_expiry_and_expires(org_id, monkeypatch):
    from dss.services import subscription_service

    _enable(monkeypatch, "SUBSCRIPTION")
    sub = subscription_service.get_organization_subscription()
    assert date.fromisoformat(sub["expires_at"]) > date.today() + timedelta(days=360)  # trước: None, không bao giờ hết hạn
    assert sub["max_ai_requests_month"] is None  # mặc định không thêm hạn mức lượt gọi (trần chi phí vẫn áp dụng)
    assert subscription_service.check_entitlement() == (True, None)

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert subscription_service.update_subscription_status("ACTIVE", expires_at=yesterday)
    allowed, reason = subscription_service.check_entitlement()
    assert allowed is False and "kết thúc" in reason
    assert subscription_service.get_organization_subscription()["status"] == "EXPIRED"


def test_expiry_on_the_last_day_is_still_valid():
    from dss.services.subscription_service import _parse_expiry

    end = _parse_expiry(date.today().isoformat())
    assert end.tzinfo is not None and end > datetime.now(UTC)


# ---------------------------------------------------------------- đợt C: dự đoán + tư vấn
def test_prediction_history_reads_back_from_postgres_in_the_file_shape(org_id, monkeypatch, tmp_path, actor):
    _enable(monkeypatch, "PREDICTIONS", "ACTIVITY")
    wh = _warehouse(tmp_path)
    pid = wh.save_prediction(
        {
            "training_id": TID_S9,
            "value": 2.75,
            "inputs": {"student_id": "SV9001", "attendance": 80},
            "metadata": {"model_name": "XGBoost", "confidence": 0.81, "probabilities": [0.2, 0.8]},
        }
    )
    assert not (tmp_path / "wh" / "history" / "prediction_history.json").exists()  # không ghi đúp ra tệp
    [rec] = wh.get_history("prediction")
    assert rec["prediction_id"] == pid and rec["training_id"] == TID_S9
    assert rec["prediction"] == 2.75
    assert rec["input_data"]["student_id"] == "SV9001"
    assert rec["metadata"]["model_name"] == "XGBoost" and rec["metadata"]["probabilities"] == [0.2, 0.8]


def test_consultation_keeps_who_advised_and_all_fields(org_id, monkeypatch, tmp_path, actor):
    _enable(monkeypatch, "CONSULTATIONS", "ACTIVITY")
    wh = _warehouse(tmp_path)
    wh.save_ai_consultation(
        {
            "student_id": "SV9002",
            "provider": "openai",
            "model_name": "gpt-x",
            "predicted_gpa": 2.1,
            "weaknesses": ["Toán rời rạc"],
            "rag_query": "Làm sao cải thiện?",
            "top_documents": [{"title": "Quy chế"}],
            "generated_plan": "Kế hoạch 4 tuần",
            "embedding_model": "bge-m3",
        }
    )
    [rec] = wh.get_history("advisor")
    assert rec["student_id"] == "SV9002"
    assert rec["performed_by"] == "gv.tuvan" and rec["performed_by_role"] == actor["role"]  # AC-GV-10
    assert rec["predicted_gpa"] == 2.1 and rec["weaknesses"] == ["Toán rời rạc"]
    assert rec["top_documents"] == [{"title": "Quy chế"}] and rec["embedding_model"] == "bge-m3"
    assert rec["generated_plan"] == "Kế hoạch 4 tuần" and rec["rag_query"] == "Làm sao cải thiện?"


def test_lecturer_consultation_report_works_on_postgres(org_id, monkeypatch, tmp_path, actor):
    from dss.services import lecturer_reports

    _enable(monkeypatch, "CONSULTATIONS", "ACTIVITY")
    wh = _warehouse(tmp_path)
    wh.save_ai_consultation({"student_id": "SV9003", "provider": "groq", "generated_plan": "A"})
    monkeypatch.setattr("dss.core.warehouse._current_actor", lambda: {"username": "gv.khac", "role": "Giảng viên / CVHT"})
    wh.save_ai_consultation({"student_id": "SV9003", "provider": "groq", "generated_plan": "B"})
    rows = wh.get_history("advisor", limit=100)
    assert {r["performed_by"] for r in rows} == {"gv.tuvan", "gv.khac"}
    # Trang "Lịch sử tư vấn" (AC-GV-10): lọc "chỉ phiên do tôi tư vấn", theo mã SV và theo ngày, rồi xuất bảng.
    mine = lecturer_reports.filter_consultations(rows, student_id="sv9003", performed_by="gv.tuvan",
                                                 date_from=date.today(), date_to=date.today())
    assert [r["generated_plan"] for r in mine] == ["A"]
    frame = lecturer_reports.consultations_frame(rows)
    assert set(frame["Người tư vấn"]) == {"gv.tuvan", "gv.khac"}


# ---------------------------------------------------------------- xoá dữ liệu phủ các kho mới
def test_student_erasure_reaches_predictions_consultations_and_activity(org_id, monkeypatch, tmp_path):
    from dss.db import models
    from dss.db.session import tenant_session_scope
    from dss.services import data_lifecycle

    _enable(monkeypatch, "PREDICTIONS", "CONSULTATIONS", "ACTIVITY")
    with tenant_session_scope(org_id) as session:
        role = session.query(models.Role).filter_by(name="Sinh viên").one_or_none() or models.Role(name="Sinh viên")
        session.add(role)
        session.flush()
        session.add(
            models.User(
                organization_id=org_id, username="sv9010", password_hash="x", password_salt="y",
                role_id=role.id, student_id="SV9010", is_active=True, auto_provisioned=False,
            )
        )
    monkeypatch.setattr("dss.core.warehouse._current_actor", lambda: {"username": "sv9010", "role": "Sinh viên"})
    wh = _warehouse(tmp_path)
    wh.save_prediction({"training_id": f"train_e_{uuid.uuid4().hex[:8]}", "value": 3.0, "inputs": {"student_id": "SV9010"}})
    wh.save_ai_consultation({"student_id": "SV9010", "provider": "openai", "generated_plan": "riêng tư"})
    wh.log_activity("Tư vấn", "SV9010 hỏi về học bổng")

    # trước bước 9: sinh viên chưa có trong `students` -> bản ghi mất mã SV và không xoá được
    with tenant_session_scope(org_id) as session:
        student = session.query(models.Student).filter_by(organization_id=org_id, student_code="SV9010").one()
        user = session.query(models.User).filter_by(organization_id=org_id, username="sv9010").one()
        student.user_id = user.id

    report = data_lifecycle.erase_student_data(org_id, "SV9010", requested_by="admin")
    assert report.deleted["consultations"] == 1 and report.deleted["predictions"] == 1
    assert report.redacted["activity_logs"] >= 2  # hoạt động tự ghi khi lưu dự đoán + tư vấn + lượt ở trên
    assert wh.get_history("advisor") == [] and wh.get_history("prediction") == []


# ---------------------------------------------------------------- đợt B: token AI
def test_token_ledger_on_postgres_keeps_all_fields_and_budget_reads_only_this_month(org_id, monkeypatch):
    from dss.db.models import AiTokenUsage
    from dss.db.session import tenant_session_scope
    from dss.services import token_tracker
    from dss.services.privacy_service import generate_pseudonym

    _enable(monkeypatch, "AI_TOKEN_USAGE")
    pseudo = generate_pseudonym("SV9020")
    token_tracker.record_usage(pseudo, "Sinh viên", "advisor_plan", "openai", "gpt-4o-mini", 1000, 500,
                               cache_hit=False, usage_source="provider", thinking_tokens=120)
    token_tracker.record_usage(pseudo, "Sinh viên", "advisor_plan", "openai", "gpt-4o-mini", 10, 5, cache_hit=True)
    with tenant_session_scope(org_id) as session:  # một bản ghi tháng trước: không được tính vào trần tháng này
        session.add(AiTokenUsage(
            organization_id=org_id, usage_id=f"old_{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(UTC).replace(day=1) - timedelta(days=3), user_id=pseudo, role="Sinh viên",
            request_type="advisor_plan", provider="openai", model="gpt-4o-mini", input_tokens=1, output_tokens=1,
            total_tokens=2, estimated_cost=99.0,
        ))

    rows = token_tracker._load_all_records()
    assert {(r["cache_hit"], r["usage_source"], r["thinking_tokens"]) for r in rows} >= {
        (False, "provider", 120), (True, "estimated", 0)
    }
    status = token_tracker.get_system_budget_status()
    assert status["monthly_cost"] < 1.0  # bản ghi 99 USD của tháng trước không bị tính
    assert token_tracker.get_user_daily_token_usage(pseudo) == 1515

    # bộ xoá dữ liệu tìm sổ token theo đúng bí danh mà các trang AI ghi (generate_pseudonym(mã SV))
    assert generate_pseudonym("SV9020", organization_id=org_id) == pseudo


# ---------------------------------------------------------------- lệnh chuyển dữ liệu cũ
def test_migrate_file_stores_is_dry_run_by_default_and_idempotent(org_id, monkeypatch, tmp_path):
    from dss.core.warehouse import DataWarehouse
    from ops import migrate_file_stores

    root = tmp_path / "root"
    # dữ liệu cũ ở chế độ lưu tệp
    wh = DataWarehouse()
    wh.save_prediction({"training_id": f"train_old_{uuid.uuid4().hex[:8]}", "value": 1.5, "inputs": {"student_id": "SV9030"},
                        "metadata": {"model_name": "RF"}})
    wh.save_ai_consultation({"student_id": "SV9030", "provider": "groq", "generated_plan": "cũ",
                             "performed_by": "gv.cu", "performed_by_role": "Giảng viên / CVHT"})
    (root / "ai_token_usage.json").write_text(json.dumps([{
        "usage_id": f"use_old_{uuid.uuid4().hex[:8]}", "timestamp": datetime.now(UTC).isoformat(), "user_id": "p_x", "role": "Sinh viên",
        "request_type": "advisor_plan", "provider": "openai", "model": "m", "input_tokens": 1, "output_tokens": 1,
        "total_tokens": 2, "estimated_cost": 0.0, "cache_hit": True, "usage_source": "estimated", "thinking_tokens": 0,
    }]), encoding="utf-8")
    expires = (datetime.now(UTC) + timedelta(days=200)).isoformat()
    (root / "subscription.json").write_text(
        json.dumps({"plan": "PRO", "status": "ACTIVE", "max_students": 1200, "expires_at": expires,
                    "features_enabled": ["LMS_SYNC"]}), encoding="utf-8"
    )
    (root / "ai_default_provider.json").write_text(
        json.dumps({"provider_key": "gemini", "model_name": "gemini-flash"}), encoding="utf-8"
    )

    _enable(monkeypatch, *ALL_STORES)
    dry = migrate_file_stores.migrate(execute=False)
    assert dry["predictions"] == {"status": "dry_run", "local_records": 1}
    assert dry["consultations"]["local_records"] == 1 and dry["ai_token_usage"]["local_records"] == 1
    assert wh.get_history("prediction") == []  # dry-run không ghi

    first = migrate_file_stores.migrate(execute=True)
    assert first["predictions"]["imported"] == 1 and first["consultations"]["imported"] == 1
    assert first["ai_token_usage"]["imported"] == 1 and first["admin_ai_config"]["imported"] == 1
    assert first["subscription"]["imported"] == 1
    again = migrate_file_stores.migrate(execute=True)
    assert again["predictions"]["imported"] == 0 and again["consultations"]["imported"] == 0
    assert again["ai_token_usage"]["imported"] == 0 and "imported" not in again["admin_ai_config"]

    [adv] = wh.get_history("advisor")
    assert adv["performed_by"] == "gv.cu" and adv["student_id"] == "SV9030"
    [pred] = wh.get_history("prediction")
    assert pred["metadata"]["model_name"] == "RF"
    assert (root / "ai_token_usage.json").exists()  # không xoá tệp cũ

    from dss.services import admin_ai_config, subscription_service

    sub = subscription_service.get_organization_subscription()
    assert sub["plan"] == "PRO" and sub["max_students"] == 1200 and sub["expires_at"] == expires[:10]
    assert admin_ai_config.get_default_provider() == {"provider_key": "gemini", "model_name": "gemini-flash"}


def test_production_compose_enables_the_migrated_stores():
    from pathlib import Path

    compose = (Path(__file__).resolve().parent.parent / "deploy" / "production" / "docker-compose.prod.yml").read_text(
        encoding="utf-8"
    )
    for feature in ALL_STORES + ("ACADEMIC", "ML_PROVENANCE"):
        assert f"EDUDSS_{feature}_STORE: postgres" in compose, feature
