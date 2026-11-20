"""Model Registry — Phase 4 của kế hoạch refactor EduDSS (mục 6 bản yêu cầu).

Bọc lại các hàm registry đã cài trong `core/warehouse.py` (Warehouse là nơi lưu
trữ thật — file .joblib + metadata JSON) thành 1 điểm gọi tường minh cho UI, để
UI (vd. `warehouse_tab.py`) không phải biết chi tiết cách Warehouse tổ chức
file. Nguyên tắc "1 nguồn sự thật duy nhất" (single source of truth): mỗi cặp
(dataset_id, target_col) chỉ có ĐÚNG 1 bản Production tại 1 thời điểm — version
khác vẫn được giữ lại đầy đủ để xem lịch sử hoặc rollback, không bị xoá.
"""
from __future__ import annotations

import os

import streamlit as st

from dss.core.logging_config import get_logger
from dss.db.repositories import audit_log_repository
from dss.services.auth_service import require_role

_logger = get_logger(__name__)


def _resolve_organization_id_best_effort() -> int | None:
    """Issue MODELREG-002 (found during final-candidate-v2 verification):
    `_set_production_with_audit` wrote audit_log_repository.record() calls
    with organization_id=None. The audit_logs table's RLS policy is
    `organization_id = current_setting('app.organization_id')` for BOTH
    qual and WITH CHECK — under SQL's NULL semantics, `NULL = NULL` is
    NULL, never TRUE, so a non-superuser app-role connection (how the
    real deployed app always connects — see dss/db/session.py) can NEVER
    satisfy that WITH CHECK with organization_id=None. The insert was
    silently rejected and swallowed by record()'s own broad
    `except Exception` (by design, so a broken audit write never blocks
    an actual promotion) — meaning every model promotion/rollback audit
    entry was silently dropped in any RLS-enforced deployment. This
    resolver mirrors dss/core/warehouse.py::_current_organization_id()'s
    env var but never raises — falling back to None preserves the
    pre-fix (no-op) behavior for deployments that don't set
    EDUDSS_ORGANIZATION_ID (e.g. the existing non-Postgres test suite)."""
    raw = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _actor() -> str:
    """Người đang thực hiện thao tác, để ghi vào nhật ký kiểm toán.

    Khoá phiên do auth_service đặt là `_auth_username` (xem auth_service.current_user).
    Trước đây hàm promote/rollback đọc nhầm khoá `_auth_user` — khoá đó không tồn tại ở
    bất kỳ đâu khác trong mã nguồn, nên `.get()` luôn trượt và nhật ký ghi đúng một chuỗi
    "admin" cho mọi lần duyệt, bất kể ai bấm. Dùng chung một khoá với tenant_service và
    user_management_service để nhật ký nêu đúng tên người chịu trách nhiệm.
    """
    return str(st.session_state.get("_auth_username") or "admin")


def get_production(wh, dataset_id, target_col):
    """Trả (pipeline, metadata) của bản Production hiện tại, hoặc (None, None)."""
    return wh.get_production_model(dataset_id, target_col)


@st.cache_resource(show_spinner=False)
def _load_artifact_cached(_wh, warehouse_scope: str, training_id: str):
    """Tải pipeline .joblib — cache CHỈ là tối ưu tốc độ (tránh joblib.load lặp
    lại mỗi lần Streamlit rerun), KHÔNG phải nguồn sự thật.

    PERF (2026-09): `show_spinner=False`, không phải chuỗi thông báo — một
    chuỗi khiến `st.cache_resource` tạo phần tử UI (`st.empty()`) cho spinner.
    Phần tử Streamlit ĐẦU TIÊN được tạo trong 1 tiến trình chưa có
    ScriptRunContext thật (đúng tình huống pytest, và bất kỳ ngữ cảnh nền/
    worker nào chạy ngoài `streamlit run`) khiến Streamlit dò TOÀN BỘ call
    stack (`inspect.stack()`) để quyết định có in cảnh báo "chạy bằng
    streamlit run" hay không — trên Windows, việc này gọi `nt._getfinalpathname`
    hàng nghìn lần và tốn 1-2 giây (đo bằng cProfile, xem
    reports/production_readiness/PERF_20K_REMEDIATION.md). Chi phí này chỉ trả
    1 lần cho MỖI TIẾN TRÌNH (Streamlit dùng cờ module-level
    `_use_warning_has_been_displayed`), nên vô hại trong 1 phiên Streamlit
    thật chạy lâu dài, nhưng lại chiếm phần lớn ngân sách 5 giây của benchmark
    20k sinh viên khi bài kiểm thử đó là phần tử Streamlit đầu tiên được tạo.
    Tắt spinner (không tạo phần tử UI) loại bỏ hoàn toàn chi phí này mà KHÔNG
    đổi ngữ nghĩa cache/model — chỉ mất dòng chữ "Đang tải..." hiển thị khi
    cache miss thật trong UI (tải từ đĩa cục bộ thường dưới 1 giây, không đáng
    để đánh đổi lấy độ trễ dò stack này).

    Cache key = (warehouse_scope, training_id), KHÔNG PHẢI (dataset_id, target_col).
    Đây là điểm mấu chốt: `training_id` đổi ngay khi Admin Promote/Rollback (con
    trỏ Production trỏ sang bản ghi khác) — nên lần gọi kế tiếp tự nhiên tính ra
    cache key khác, luôn tải đúng bản mới, không có cách nào "dính" lại bản cũ do
    cache stale. `_wh` bắt đầu bằng `_` nên Streamlit KHÔNG hash nó (instance
    warehouse không hashable ổn định); `warehouse_scope` (đường dẫn thư mục
    models) mới là phần được hash, đảm bảo 2 Warehouse trỏ 2 thư mục khác nhau
    (vd. 2 test riêng biệt) không bao giờ chia sẻ nhầm cache.
    """
    return _wh.load_model_training(training_id)


def clear_production_cache():
    """Xoá toàn bộ cache artifact đã tải — dùng trong test teardown/setup để mỗi
    test bắt đầu từ trạng thái sạch, không bị rò rỉ cache giữa các test."""
    _load_artifact_cached.clear()


def resolve_production(wh, dataset_id, target_col):
    """SOURCE OF TRUTH DUY NHẤT cho việc dự đoán: luôn hỏi Model Registry (không
    phải session_state) xem bản Production hiện tại của (dataset_id, target_col)
    là gì, rồi tải đúng artifact đó (có cache theo training_id để nhanh).

    Không bao giờ âm thầm rơi về 1 model khác (vd. model đang có sẵn trong
    session, hay model đầu tiên tìm thấy) khi chưa có Production — trả về
    status="empty" để UI tự hiển thị trạng thái rõ ràng, đúng yêu cầu "controlled
    empty/error state, không đoán bừa".

    Trả về dict:
        {"status": "ok", "pipeline": ..., "metadata": {...}, "message": "..."}
        {"status": "empty", "pipeline": None, "metadata": None, "message": "..."}
        {"status": "error", "pipeline": None, "metadata": None, "message": "..."}
    """
    if not dataset_id or not target_col:
        return {
            "status": "empty",
            "pipeline": None,
            "metadata": None,
            "message": "Chưa xác định được dataset/target để tra Model Registry.",
        }

    training_id = wh.get_production_training_id(dataset_id, target_col)
    if not training_id:
        return {
            "status": "empty",
            "pipeline": None,
            "metadata": None,
            "message": (
                f"Chưa có mô hình Production cho target '{target_col}' của dataset này. "
                "Giảng viên cần huấn luyện trước (mô hình tốt nhất sẽ được lưu ở trạng thái Candidate), "
                "sau đó Admin cần Promote version đó lên Production trong Kho dữ liệu."
            ),
        }

    pipeline, metadata, msg = _load_artifact_cached(wh, wh.models_path, training_id)
    if pipeline is None:
        return {"status": "error", "pipeline": None, "metadata": None, "message": msg}
    return {"status": "ok", "pipeline": pipeline, "metadata": metadata, "message": msg}


def list_versions(wh, dataset_id, target_col):
    """Lịch sử version (mới nhất trước) cho (dataset_id, target_col)."""
    return wh.list_model_versions(dataset_id, target_col)


def get_provenance(training_id, organization_id=None):
    """Workstream C (§9): the MODEL -> VERSION -> DATASET -> FEATURE SCHEMA
    -> METRICS -> ARTIFACT -> DRIFT HISTORY chain for one training_id, read
    from Postgres. Returns None if ML_PROVENANCE Postgres mirroring isn't
    enabled, Postgres isn't configured, or nothing was recorded for this
    training_id (e.g. it predates Workstream C, or was trained while the
    flag was off) — never raises, since this is a read-only governance view
    layered on top of the real registry above, not a dependency of it."""
    from dss.core.persistence_config import is_postgres_enabled

    if not is_postgres_enabled("ML_PROVENANCE"):
        return None
    try:
        import os

        from dss.db.repositories import ml_provenance_repository as repo

        org_id = organization_id or int(os.environ["EDUDSS_ORGANIZATION_ID"])
        return repo.get_model_provenance(org_id, training_id)
    except Exception:
        return None


def evaluate_drift(
    training_id,
    baseline_df,
    current_df,
    *,
    y_true_baseline=None,
    y_pred_baseline=None,
    y_true_current=None,
    y_pred_current=None,
    task_type="classification",
    organization_id=None,
    evaluated_by=None,
):
    """Workstream C (§6-§10): runs data-drift (always) and performance-drift
    (only if ground truth is passed for both windows) evaluation, computes a
    retraining recommendation, and — if ML_PROVENANCE Postgres mirroring is
    enabled and a recorded model_version exists for `training_id` — persists
    the result to `drift_evaluations`. Always returns the computed result
    dict even when persistence is unavailable/disabled, so the caller (e.g.
    an Admin-facing drift-review UI) always gets a real, honest answer."""
    from dss.services import ml_provenance

    _logger.info("drift evaluation started: training_id=%s", training_id)
    data_drift = ml_provenance.evaluate_data_drift(baseline_df, current_df)
    performance_drift = ml_provenance.evaluate_performance_drift(
        task_type, y_true_baseline, y_pred_baseline, y_true_current, y_pred_current,
    )
    action = ml_provenance.recommend_action(data_drift["overall_status"], performance_drift["overall_status"])

    result = {"data_drift": data_drift, "performance_drift": performance_drift, "recommended_action": action}
    _logger.info(
        "drift evaluation completed: training_id=%s data_drift=%s performance_drift=%s recommended_action=%s",
        training_id, data_drift["overall_status"], performance_drift["overall_status"], action,
    )
    if action == "RETRAIN_RECOMMENDED":
        _logger.warning("retraining recommended: training_id=%s", training_id)
    elif data_drift["overall_status"] == "DRIFT_DETECTED" or performance_drift["overall_status"] == "DRIFT_DETECTED":
        _logger.warning("drift detected: training_id=%s", training_id)

    from dss.core.persistence_config import is_postgres_enabled

    if is_postgres_enabled("ML_PROVENANCE"):
        try:
            import os

            from dss.db.repositories import ml_provenance_repository as repo

            org_id = organization_id or int(os.environ["EDUDSS_ORGANIZATION_ID"])
            mv = repo.get_model_provenance(org_id, training_id)
            if mv:
                model_version_id = mv["model_version"]["id"]
                for kind, payload in (("data_drift", data_drift), ("performance_drift", performance_drift)):
                    repo.record_drift_evaluation(
                        organization_id=org_id, model_version_id=model_version_id, evaluation_type=kind,
                        overall_status=payload["overall_status"], recommended_action=action,
                        details=payload, thresholds_used=payload.get("thresholds", {}), evaluated_by=evaluated_by,
                    )
        except Exception:
            pass  # Best-effort persistence only — result above is always returned regardless.

    return result


@require_role("Admin")
def promote(wh, training_id, promoted_by=None, promotion_reason=None):
    """Đặt 1 version đã lưu làm Production — CHỈ Quản trị viên (Admin).

    Vòng đời thật (audit 2026-09-15, Issue MODELREG-001 — khớp đúng với
    warehouse.py::save_model_training/set_production_model, không còn là mô
    tả rời rạc với code): TRAINED -> status="candidate" (is_production=False,
    không tự động lên Production dù là bản tốt nhất — should_promote luôn
    False trừ khi auto_promote=True được truyền rõ, hiện KHÔNG nơi nào trong
    app truyền auto_promote=True) -> [Admin xem, gọi promote() ở đây]
    -> status="production" (is_production=True) -> khi có bản khác được
    promote, bản cũ tự chuyển status="archived" (is_production=False).
    UI đọc field `status` này qua warehouse_tab._model_lifecycle_badge_text().
    """
    if promoted_by is None:
        promoted_by = _actor()
    if promotion_reason is None:
        promotion_reason = "Admin manual promotion via Model Registry"
    return _set_production_with_audit(wh, training_id, promoted_by, promotion_reason, action="model.promoted")


@require_role("Admin")
def rollback(wh, training_id, promoted_by=None, promotion_reason=None):
    """Quay lại 1 version cũ hơn làm Production — CHỈ Quản trị viên (Admin)."""
    if promoted_by is None:
        promoted_by = _actor()
    if promotion_reason is None:
        promotion_reason = "Admin manual rollback via Model Registry"
    return _set_production_with_audit(wh, training_id, promoted_by, promotion_reason, action="model.rolled_back")


def _set_production_with_audit(wh, training_id, promoted_by, promotion_reason, action):
    """PERF/Phase-1: wraps warehouse.set_production_model() with a real audit-log
    write (dss/db/repositories/audit_log_repository.py) — the security audit
    trail Phase 0 found did not exist for this exact action. Best-effort: audit
    logging never blocks or fails the actual promote/rollback (it degrades to a
    no-op when no PostgreSQL is configured, which is the default for this phase
    and for the existing test suite)."""
    before_meta = wh.get_model_metadata_only(training_id)
    model_key = None
    prev_training_id = None
    if before_meta:
        model_key = before_meta.get("model_key") or f"{before_meta.get('dataset_id')}::{before_meta.get('target_col')}"
        prev_training_id = wh.get_production_training_id(before_meta.get("dataset_id"), before_meta.get("target_col"))

    ok, msg = wh.set_production_model(training_id, promoted_by=promoted_by, promotion_reason=promotion_reason)

    if ok:
        audit_log_repository.record(
            action=action,
            target_type="model_version",
            target_id=training_id,
            actor_username=str(promoted_by),
            organization_id=_resolve_organization_id_best_effort(),
            before={"model_key": model_key, "production_training_id": prev_training_id},
            after={"model_key": model_key, "production_training_id": training_id, "reason": promotion_reason},
        )
    return ok, msg


def run_on_demand_drift_check(training_id: str, wh) -> dict:
    """D-1 (POST_72H_MASTER_PRODUCTION_CLOSURE, Câu 85): kiểm tra drift THEO
    YÊU CẦU (on-demand) — trước đợt này, `evaluate_drift()` (định nghĩa phía
    trên trong file này) đã được cài đặt và test đầy đủ nhưng KHÔNG có nơi
    nào trong UI gọi tới (xác nhận qua grep `dss/tabs/*.py` — 0 kết quả) —
    hệ thống KHÔNG được phép tự nhận "có giám sát drift" khi không ai gọi
    hàm này bao giờ. Đây là bước tối thiểu trung thực: 1 nút Admin bấm để
    kiểm tra, không phải lịch tự động (ứng dụng Streamlit này không có hạ
    tầng scheduler nền để chạy định kỳ).

    HẠN CHẾ TRUNG THỰC (PHẢI hiểu trước khi đọc kết quả): môi trường demo
    này không có luồng dữ liệu SẢN XUẤT THẬT chảy vào sau khi mô hình được
    Promote. "baseline" và "current" ở đây là train-split và test-split GỐC
    đã lưu lúc huấn luyện (`warehouse.save_training_data()`) — đây là kiểm
    tra SANITY (train/test có lệch phân bố bất thường không), KHÔNG PHẢI
    giám sát drift sản xuất thật. Khi hệ thống có dữ liệu vận hành thật, cửa
    sổ "current" PHẢI được thay bằng dữ liệu mới thu thập sau triển khai,
    không phải test split cũ — trường `window_note` dưới đây nói rõ điều
    này mỗi lần gọi, không chỉ trong docstring."""
    import pandas as pd

    model = wh.get_model_metadata_only(training_id)
    if model is None:
        return {"status": "ERROR", "message": f"Không tìm thấy mô hình training_id={training_id}."}

    train_id = model.get("train_data_id")
    test_id = model.get("test_data_id")
    if not train_id or not test_id:
        return {
            "status": "INSUFFICIENT_DATA",
            "message": "Mô hình này không có dữ liệu train/test đã lưu để so sánh drift.",
        }

    train_path = os.path.join(wh.training_data_path, f"{train_id}_train.csv")
    test_path = os.path.join(wh.training_data_path, f"{test_id}_test.csv")
    if not os.path.exists(train_path) or not os.path.exists(test_path):
        return {
            "status": "INSUFFICIENT_DATA",
            "message": "Dữ liệu train/test gốc của mô hình này không còn trên đĩa (có thể đã bị dọn dẹp).",
        }

    baseline_df = pd.read_csv(train_path).drop(columns=["target"], errors="ignore")
    current_df = pd.read_csv(test_path).drop(columns=["target"], errors="ignore")
    task_type = "classification" if model.get("class_labels") else "regression"

    result = evaluate_drift(
        training_id=training_id,
        baseline_df=baseline_df,
        current_df=current_df,
        task_type=task_type,
        organization_id=_resolve_organization_id_best_effort(),
    )
    from datetime import datetime as _dt

    result["checked_at"] = _dt.now().isoformat()
    result["model_version"] = model.get("version")
    result["dataset_id"] = model.get("dataset_id")
    result["window_note"] = (
        "So sánh train-split (baseline) vs. test-split (current) GỐC của mô hình lúc huấn "
        "luyện — KHÔNG PHẢI dữ liệu vận hành thật thu thập sau triển khai (môi trường demo "
        "hiện chưa có luồng dữ liệu sản xuất mới). Đây là kiểm tra sanity, không phải giám "
        "sát drift sản xuất thật."
    )
    return result
