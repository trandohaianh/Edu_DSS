"""S-2: metadata feature_cols lưu vào Kho phải khớp cột PIPELINE THẬT SỰ dùng
(st.session_state.hub_feats, do run_training() ghi SAU khi lọc rò rỉ dữ liệu),
KHÔNG PHẢI danh sách chọn thô trên UI (selected_features) — có thể còn chứa cột
đã bị loại (vd. final_score khi target=diem_ky_sau)."""

from __future__ import annotations

import inspect

import streamlit as st

from dss.services.model_service import resolve_saved_feature_cols
from dss.tabs import ml_hub


def test_resolve_saved_feature_cols_prefers_hub_feats_over_raw_selection():
    st.session_state["hub_feats"] = ["diem_ky_nay", "diem_giua_ky"]
    selected_features = ["diem_ky_nay", "diem_giua_ky", "final_score"]  # final_score bị lọc rò rỉ
    assert resolve_saved_feature_cols(selected_features) == ["diem_ky_nay", "diem_giua_ky"]


def test_resolve_saved_feature_cols_falls_back_when_hub_feats_missing():
    assert "hub_feats" not in st.session_state
    selected_features = ["diem_ky_nay", "diem_giua_ky"]
    assert resolve_saved_feature_cols(selected_features) == selected_features


def test_ml_hub_autosave_uses_resolve_saved_feature_cols_not_raw_selection():
    # Autosave Candidate đã chuyển từ ml_hub.py sang model_service.save_session_candidates.
    from dss.services import model_service

    for source in (inspect.getsource(ml_hub), inspect.getsource(model_service.save_session_candidates)):
        assert "feature_cols=selected_features," not in source, (
            "Vẫn lưu metadata feature_cols bằng danh sách chọn thô trên UI "
            "thay vì cột pipeline thật sự dùng (resolve_saved_feature_cols)."
        )
    assert "resolve_saved_feature_cols(" in inspect.getsource(model_service.save_session_candidates)
