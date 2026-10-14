"""SaaS Subscription & Entitlement Service for EduDSS.

Quản lý thông tin gói thuê bao tổ chức (Trường Đại học/Viện đào tạo), kiểm tra trạng thái
hiệu lực (ACTIVE, EXPIRED, SUSPENDED) và chặn truy cập (Entitlement Gate) khi hết hạn.
Không hỗ trợ dùng thử miễn phí theo chính sách thương mại SaaS của Section 36 & 37.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from dss.core.display_mapper import (
    SUBSCRIPTION_STATUS_TO_VIETNAMESE,
    SUBSCRIPTION_PLAN_TO_VIETNAMESE,
)
from dss.core.data_root import get_data_root
from dss.core.logging_config import get_logger
from dss.core.persistence_config import is_postgres_enabled

_logger = get_logger(__name__)
_SUB_LOCK = threading.Lock()


def _sub_path() -> Path:
    """PERF-002: tính lại mỗi lần gọi, không cache mức module (xem dss/core/data_root.py)."""
    return get_data_root() / "subscription.json"

DEFAULT_ORGANIZATION_SUBSCRIPTION: Dict[str, Any] = {
    "org_id": "org_univ_01",
    "org_name": "Trường Đại học Khoa học Tự nhiên - ĐHQG",
    "domain": "hcmus.edu.vn",
    "plan": "ENTERPRISE",
    "status": "ACTIVE",  # ACTIVE | EXPIRED | SUSPENDED
    "admin_contact": "admin@edudss.edu.vn",
    "created_at": "2025-01-01T00:00:00Z",
    "activated_at": "2025-01-01T00:00:00Z",
    "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
    "max_students": 5000,
    "max_courses": 150,
    "features_enabled": [
        "LMS_SYNC",
        "CMS_LECTURE_RAG",
        "ML_TRAINING",
        "STUDENT_DIAGNOSIS",
        "CAREER_ADVISOR",
        "QUIZ_APPROVAL_QUEUE",
        "ADVANCED_SHAP",
    ],
}


def _current_organization_id() -> int:
    raw = os.environ.get("EDUDSS_ORGANIZATION_ID", "").strip()
    if not raw:
        raise RuntimeError(
            "EDUDSS_ORGANIZATION_ID is required when EDUDSS_SUBSCRIPTION_STORE=postgres."
        )
    return int(raw)


def get_organization_subscription() -> Dict[str, Any]:
    """Lấy thông tin thuê bao tổ chức hiện tại.

    Phase 1B: khi EDUDSS_SUBSCRIPTION_STORE=postgres, PostgreSQL là nguồn sự
    thật DUY NHẤT — không đọc/ghi đúp vào subscription.json cục bộ."""
    if is_postgres_enabled("SUBSCRIPTION"):
        from dss.db.repositories import subscription_repository
        return subscription_repository.get_or_create_subscription(
            _current_organization_id(), defaults=DEFAULT_ORGANIZATION_SUBSCRIPTION
        )

    sub_path = _sub_path()
    if not sub_path.exists():
        with _SUB_LOCK:
            _save_subscription(DEFAULT_ORGANIZATION_SUBSCRIPTION)
        return dict(DEFAULT_ORGANIZATION_SUBSCRIPTION)
    try:
        with open(sub_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else dict(DEFAULT_ORGANIZATION_SUBSCRIPTION)
    except Exception as e:
        _logger.error(f"Lỗi khi đọc subscription.json: {e}")
        return dict(DEFAULT_ORGANIZATION_SUBSCRIPTION)


def _save_subscription(data: Dict[str, Any]) -> bool:
    """Lưu thông tin thuê bao tổ chức an toàn nguyên tử."""
    try:
        sub_path = _sub_path()
        sub_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = sub_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, sub_path)
        return True
    except Exception as e:
        _logger.error(f"Lỗi khi lưu subscription.json: {e}")
        return False


def update_subscription_status(
    status: str,
    plan: Optional[str] = None,
    expires_at: Optional[str] = None,
    max_students: Optional[int] = None,
) -> bool:
    """Cập nhật trạng thái thuê bao tổ chức (dành riêng cho Quản trị viên)."""
    valid_statuses = ("ACTIVE", "EXPIRED", "SUSPENDED")
    if status not in valid_statuses:
        raise ValueError(f"Trạng thái không hợp lệ: {status}. Hợp lệ: {valid_statuses}")

    if is_postgres_enabled("SUBSCRIPTION"):
        from dss.db.repositories import subscription_repository
        org_id = _current_organization_id()
        subscription_repository.get_or_create_subscription(org_id, defaults=DEFAULT_ORGANIZATION_SUBSCRIPTION)
        subscription_repository.update_status(org_id, status=status, plan=plan, max_students=max_students)
        return True

    with _SUB_LOCK:
        sub = get_organization_subscription()
        sub["status"] = status
        if plan:
            sub["plan"] = plan
        if expires_at:
            sub["expires_at"] = expires_at
        if max_students is not None:
            sub["max_students"] = max_students
        sub["updated_at"] = datetime.now(timezone.utc).isoformat()
        return _save_subscription(sub)


def check_entitlement(feature_key: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """Kiểm tra quyền truy cập hệ thống ở tầng Backend (Entitlement Gate).

    Trả về (is_allowed, error_message).
    """
    sub = get_organization_subscription()
    status = sub.get("status", "ACTIVE").upper()

    # 1. Kiểm tra trạng thái thuê bao
    if status == "EXPIRED":
        return False, "Thời hạn thuê bao dịch vụ EduDSS của Tổ chức đã hết hạn. Vui lòng liên hệ Quản trị viên trường để gia hạn hợp đồng."
    if status == "SUSPENDED":
        return False, "Tài khoản dịch vụ EduDSS của Tổ chức hiện đang tạm ngưng do bảo trì hợp đồng hoặc vi phạm chính sách."

    # 2. Kiểm tra ngày hết hạn
    expires_str = sub.get("expires_at")
    if expires_str:
        try:
            exp_date = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp_date:
                # Tự động cập nhật thành EXPIRED
                update_subscription_status("EXPIRED")
                return False, "Hợp đồng dịch vụ EduDSS đã kết thúc vào ngày " + exp_date.strftime("%d/%m/%Y") + "."
        except Exception:
            pass

    # 3. Kiểm tra tính năng cụ thể nếu được yêu cầu
    if feature_key:
        enabled_features = sub.get("features_enabled", [])
        if feature_key not in enabled_features:
            return False, f"Gói dịch vụ hiện tại ({sub.get('plan')}) chưa bao gồm tính năng '{feature_key}'."

    return True, None


def consume_ai_request_quota() -> int | None:
    """Atomically account one tenant AI request when subscription PostgreSQL mode is active."""
    if not is_postgres_enabled("SUBSCRIPTION"):
        return None
    from dss.db.repositories.quota_repository import consume, subscription_limit
    organization_id=_current_organization_id()
    return consume(organization_id,"AI_REQUESTS_MONTH",subscription_limit(organization_id,"max_ai_requests_month"),1)


def render_subscription_gate(current_role: str) -> bool:
    """Kiểm tra và render màn hình khóa truy cập nếu tổ chức chưa kích hoạt hoặc hết hạn.

    Trả về True nếu hợp lệ để tiếp tục; False nếu đã hiển thị màn hình khóa và chặn luồng.
    """
    is_allowed, reason = check_entitlement()
    if is_allowed:
        return True

    # Quản trị viên vẫn được quyền vào tab Cài đặt để quản lý thuê bao, nhưng các vai trò khác bị chặn hoàn toàn
    st.markdown(
        f"""
        <div style='max-width:700px;margin:3rem auto;padding:2.5rem;background:var(--surface);
                    border:1px solid var(--danger);border-radius:16px;box-shadow:0 10px 25px rgba(239,68,68,0.1);text-align:center;'>
            <div style='font-size:3.5rem;margin-bottom:1rem;'>🔒</div>
            <div style='font-size:var(--fs-section-title);font-weight:800;color:var(--danger);margin-bottom:0.8rem;'>
                Dịch Vụ Đang Tạm Khóa
            </div>
            <p style='color:var(--text-secondary);font-size:var(--fs-body);line-height:1.6;margin-bottom:1.5rem;'>
                {reason}
            </p>
            <div style='background:var(--danger-soft);border:1px dashed var(--danger);border-radius:8px;padding:1rem;font-size:var(--fs-support);color:var(--danger);margin-bottom:1.5rem;'>
                Mã tổ chức: <b>{get_organization_subscription().get('org_id')}</b> · Đại diện: <b>{get_organization_subscription().get('org_name')}</b>
            </div>
            <p style='color:var(--text-muted);font-size:var(--fs-caption);'>
                Hệ thống EduDSS không áp dụng chính sách dùng thử hoặc tài khoản demo không xác thực trên phiên bản SaaS thương mại.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return False
