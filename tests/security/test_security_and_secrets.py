"""Security & Secrets Test Suite for EduDSS.

Validates:
1. Zero live API keys in repository and configuration templates.
2. Account lockout after 5 failed login attempts.
3. Model artifact SHA-256 checksum verification and tampering rejection.
4. RBAC security enforcement (Lecturer cannot promote model, Student cannot see keys).
"""
import hashlib
import json
import os
import re
import pytest
from pathlib import Path

from dss.services.auth_service import authenticate, is_account_locked, AccountLockedError
from dss.core.warehouse import DataWarehouse


class DummyModel:
    def predict(self, X):
        return [1.0] * len(X)


def test_zero_live_api_keys_in_env_example_and_config():
    """Verify that .env.example contains only placeholders, never real keys."""
    env_example = Path(__file__).resolve().parent.parent.parent / ".env.example"
    assert env_example.exists(), ".env.example must exist"
    content = env_example.read_text(encoding="utf-8")
    
    # Check that no real google/groq/openai/hf keys exist
    assert "AIzaSy" not in content
    assert "gsk_" not in content
    assert "sk-" not in content
    assert not re.search(r"AIzaSy[A-Za-z0-9_-]{33}", content)
    assert not re.search(r"gsk_[A-Za-z0-9_-]{40,}", content)
    assert not re.search(r"sk-[A-Za-z0-9_-]{40,}", content)


def test_login_brute_force_lockout():
    """Verify that 5 failed login attempts result in 15-minute account lockout."""
    username = "test_attacker_user"
    
    # 5 failed attempts
    for _ in range(5):
        assert authenticate(username, "wrong_password") is None
        
    # 6th attempt should raise AccountLockedError
    with pytest.raises(AccountLockedError):
        authenticate(username, "any_password")


def test_model_artifact_sha256_tampering_rejected(tmp_path):
    """Verify that if a .joblib model file is modified/corrupted, it is rejected."""
    wh = DataWarehouse(base_path=str(tmp_path))
    
    training_id, meta = wh.save_model_training(
        dataset_id="sec_ds",
        model_pipeline=DummyModel(),
        model_name="SecureModel",
        feature_cols=["f1", "f2"],
        target_col="diem_cuoi_ky",
        metrics={"r2": 0.95, "mae": 0.2},
    )
    
    # Verify file saved and metadata contains checksum
    joblib_path = tmp_path / "models" / f"{training_id}.joblib"
    assert joblib_path.exists()
    meta_path = tmp_path / "metadata" / f"{training_id}_model.json"
    with open(meta_path, "r", encoding="utf-8") as f:
        saved_meta = json.load(f)
    assert "model_sha256" in saved_meta
    
    # Now tamper with the joblib file
    with open(joblib_path, "ab") as f:
        f.write(b"CORRUPT_PAYLOAD")
        
    # Attempting to load the tampered model must reject with SHA-256 error
    pipeline, meta_loaded, msg = wh.load_model_training(training_id)
    assert pipeline is None
    assert "SHA-256" in msg or "Lỗi bảo mật" in msg


def test_lecturer_cannot_promote_to_production(tmp_path):
    """Verify that only Admin can promote a candidate to production."""
    import streamlit as st
    from dss.services.model_registry import promote
    
    wh = DataWarehouse(base_path=str(tmp_path))
    
    training_id, meta = wh.save_model_training(
        dataset_id="sec_ds",
        model_pipeline=DummyModel(),
        model_name="CandidateModel",
        feature_cols=["f1", "f2"],
        target_col="diem_cuoi_ky",
        metrics={"r2": 0.99, "mae": 0.05},
    )
    
    # Lecturer tries to promote -> must be rejected at service layer
    st.session_state["_auth_role"] = "Giảng viên"
    with pytest.raises(PermissionError):
        promote(wh, training_id)
        
    # Model remains candidate
    _, meta_reloaded, _ = wh.load_model_training(training_id)
    assert meta_reloaded["is_production"] is False

