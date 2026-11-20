"""Unit tests for SaaS Subscription & Entitlement Service."""
from dss.services import subscription_service


def test_get_default_subscription():
    sub = subscription_service.get_organization_subscription()
    assert isinstance(sub, dict)
    assert "org_id" in sub
    assert "plan" in sub
    assert "status" in sub
    assert sub["status"] in ("ACTIVE", "EXPIRED", "SUSPENDED")


def test_entitlement_active():
    subscription_service.update_subscription_status("ACTIVE")
    is_allowed, reason = subscription_service.check_entitlement()
    assert is_allowed is True
    assert reason is None


def test_entitlement_expired():
    subscription_service.update_subscription_status("EXPIRED")
    is_allowed, reason = subscription_service.check_entitlement()
    assert is_allowed is False
    assert "hết hạn" in reason.lower()
    # Khôi phục lại trạng thái ACTIVE cho các test khác
    subscription_service.update_subscription_status("ACTIVE")


def test_entitlement_suspended():
    subscription_service.update_subscription_status("SUSPENDED")
    is_allowed, reason = subscription_service.check_entitlement()
    assert is_allowed is False
    assert "tạm ngưng" in reason.lower()
    # Khôi phục lại trạng thái ACTIVE
    subscription_service.update_subscription_status("ACTIVE")


def test_feature_entitlement():
    subscription_service.update_subscription_status("ACTIVE")
    is_allowed, _ = subscription_service.check_entitlement("LMS_SYNC")
    assert is_allowed is True

    is_allowed, reason = subscription_service.check_entitlement("NON_EXISTENT_FEATURE_XYZ")
    assert is_allowed is False
    assert "chưa bao gồm tính năng" in reason
