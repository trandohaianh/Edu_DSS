"""Ensemble trainer and LLM / multi-provider AI."""
from __future__ import annotations

import json
import os
from datetime import datetime
from threading import Thread

import numpy as np
import pandas as pd
import streamlit as st
from scipy.spatial.distance import cosine
from sklearn.metrics.pairwise import cosine_similarity

from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from dss.core.warehouse import VectorStore
from dss.core.utils import _make_safe_cv_strategy
from dss.core.logging_config import get_logger
from dss.core.observability import observed
from dss.security.prompt_boundary import (
    AI_SYSTEM_POLICY, prompt_within_limit, render_retrieved_context, sanitize_student_text,
)
import dss.config as dss_config

_logger = get_logger(__name__)

from dss.config import *  # noqa: F401,F403 -- shared sklearn/math/shap/etc symbols; see dss/config.py

from dss.config import (
    GEMINI_AVAILABLE,
    GROQ_AVAILABLE,
    OLLAMA_AVAILABLE,
    OPENAI_AVAILABLE,
    genai,
    Groq,
    openai,
    requests,
    xgb,
    lgb,
    XGBOOST_AVAILABLE,
    LIGHTGBM_AVAILABLE,
)


class EnsembleTrainer:
    """Class này chịu trách nhiệm huấn luyện các mô hình ensemble (Stacking) nâng cao."""

    def __init__(self):
        self.models = {}

    @st.cache_data
    def train_ensemble_improved(
            _self,
            df,
            feature_cols,
            target_reg,
            target_clf,
            random_state=42):
        """Hàm chính để huấn luyện các mô hình ensemble cho cả hồi quy và phân loại."""
        if target_reg not in df.columns or target_clf not in df.columns:
            raise KeyError(
                f"Cột mục tiêu '{target_reg}' hoặc '{target_clf}' không tìm thấy.")

        X = df[feature_cols]
        y_reg = df[target_reg]
        y_clf = df[target_clf]

        # Chia dữ liệu cho bài toán hồi quy
        X_train_reg, X_test_reg, y_train_reg, y_test_reg = train_test_split(
            X, y_reg, test_size=0.2, random_state=random_state
        )
        # Chia dữ liệu cho bài toán phân loại (với stratify để giữ nguyên tỉ lệ các lớp)
        clf_counts = pd.Series(y_clf).value_counts(dropna=False)
        stratify_clf = y_clf if (not clf_counts.empty and int(clf_counts.min()) >= 2) else None
        X_train_clf, X_test_clf, y_train_clf, y_test_clf = train_test_split(
            X, y_clf, test_size=0.2, random_state=random_state, stratify=stratify_clf
        )

        # Xác định các cột số và cột phân loại để xử lý riêng
        numeric_features = X.select_dtypes(include=[np.number]).columns.tolist()
        categorical_features = X.select_dtypes(include=['object', 'category']).columns.tolist()
        from dss.core.data_helpers import create_shared_preprocessor  # import trễ: tránh vòng lặp import models<->data_helpers<->trainers
        preprocessor = create_shared_preprocessor(
            numeric_features, categorical_features)

        # --- Xây dựng Pipeline cho Hồi quy (Stacking) ---
        # Các mô hình cơ sở (base models)
        rf_reg = RandomForestRegressor(n_jobs=-1, random_state=random_state)
        gb_reg = GradientBoostingRegressor(random_state=random_state)
        estimators_reg = [("rf", rf_reg), ("gb", gb_reg)]
        # Mô hình Stacking: kết hợp các mô hình cơ sở và dùng một mô hình cuối (final_estimator) để đưa ra dự đoán cuối cùng
        stack_reg = StackingRegressor(
            estimators=estimators_reg,
            final_estimator=Ridge(),
            passthrough=False)
        regression_pipeline = SklearnPipeline(
            steps=[('preprocessor', preprocessor), ('regressor', stack_reg)])

        # Tinh chỉnh tham số tự động bằng GridSearchCV
        param_grid_reg = {
            'regressor__rf__n_estimators': [100, 200, 300],
            'regressor__rf__max_depth': [5, 10, 15],
            'regressor__gb__n_estimators': [50, 100, 200],
            'regressor__final_estimator__alpha': [0.1, 1.0, 10.0]
        }
        cv_reg = _make_safe_cv_strategy(y_train_reg, desired_folds=5, is_classification=False)
        grid_search_reg = GridSearchCV(
            regression_pipeline,
            param_grid=param_grid_reg,
            cv=cv_reg,
            scoring="neg_mean_absolute_error",
            n_jobs=-1,
            verbose=0)
        grid_search_reg.fit(X_train_reg, y_train_reg)
        best_reg = grid_search_reg.best_estimator_

        # --- Xây dựng Pipeline cho Phân loại (Stacking) ---
        rf_clf = RandomForestClassifier(
            n_estimators=200, random_state=random_state)
        gb_clf = RandomForestClassifier(
            n_estimators=200, random_state=random_state)
        estimators_clf = [("rf_c", rf_clf), ("gb_c", gb_clf)]
        stack_clf = StackingClassifier(
            estimators=estimators_clf,
            final_estimator=LogisticRegression(
                max_iter=1000),
            passthrough=False)
        classification_pipeline = SklearnPipeline(
            steps=[('preprocessor', preprocessor), ('classifier', stack_clf)])

        # Tinh chỉnh tham số tự động bằng GridSearchCV
        param_grid_clf = {
            'classifier__final_estimator__C': [0.1, 1.0, 10.0],
            'classifier__rf_c__n_estimators': [100, 200, 300]
        }
        cv_clf = _make_safe_cv_strategy(y_train_clf, desired_folds=5, is_classification=True)
        grid_search_clf = GridSearchCV(
            classification_pipeline,
            param_grid=param_grid_clf,
            cv=cv_clf,
            scoring="f1_macro",
            n_jobs=-1,
            verbose=0)
        grid_search_clf.fit(X_train_clf, y_train_clf)
        best_clf = grid_search_clf.best_estimator_

        # Tạo SHAP explainer để giải thích mô hình (nếu thư viện SHAP có sẵn)
        explainer = None
        if SHAP_AVAILABLE:
            try:
                rf_model = best_reg.named_steps['regressor'].named_estimators_[
                    'rf']
                explainer = shap.TreeExplainer(rf_model)
            except Exception as e:
                st.warning(f"Tạo SHAP explainer thất bại: {e}")

        # Đánh giá mô hình trên tập test
        y_pred_reg = best_reg.predict(X_test_reg)
        y_pred_clf = best_clf.predict(X_test_clf)

        # Tính toán các chỉ số cho mô hình hồi quy
        metrics_reg = {
            "RMSE": float(
                math.sqrt(
                    mean_squared_error(
                        y_test_reg, y_pred_reg))), "MAE": float(
                mean_absolute_error(
                    y_test_reg, y_pred_reg)), "R2": float(
                            r2_score(
                                y_test_reg, y_pred_reg))}
        # Tính toán các chỉ số cho mô hình phân loại
        metrics_clf = {
            "Accuracy": float(
                accuracy_score(
                    y_test_clf,
                    y_pred_clf)),
            "F1_macro": float(
                f1_score(
                    y_test_clf,
                    y_pred_clf,
                    average="macro")),
            "classification_report": classification_report(
                y_test_clf,
                y_pred_clf,
                output_dict=True,
                zero_division=0)}

        # Trả về các mô hình, explainer, features và metrics đã huấn luyện
        return {
            "regressor": best_reg,
            "classifier": best_clf,
            "explainer": explainer,
            "features": feature_cols,
            "metrics_reg": metrics_reg,
            "metrics_clf": metrics_clf,
            "preprocessor": preprocessor}


# Danh sách tên model theo THỨ TỰ ƯU TIÊN cho mỗi provider — NƠI DUY NHẤT cần sửa
# khi một hãng đổi tên/khai tử model (trước đây tên model bị hardcode rải rác ở
# nhiều chỗ trong call_ai_provider + các selectbox UI, mỗi lần provider đổi tên là
# phải dò sửa từng nơi). `call_ai_provider` tự động thử lần lượt các tên trong danh
# sách khi tên đầu bị lỗi "không tìm thấy/khai tử" (xem _is_model_unavailable_error).
def _get_model_list(provider_key: str, default_list: list) -> list:
    """Cho phép người dùng cấu hình tên model mới nhất qua file .env (VD: GEMINI_MODEL=gemini-2.0-flash)
    mà không cần phải sửa code khi các hãng AI nâng cấp đời mô hình mới."""
    env_model = os.environ.get(f"{provider_key.upper()}_MODEL")
    if env_model and env_model.strip():
        m = env_model.strip()
        return [m] + [x for x in default_list if x != m]
    return default_list


# CẬP NHẬT 2026-09: "gemini-1.5-flash"/"gemini-2.0-flash"/"gemini-1.5-pro" và
# "llama-3.3-70b-versatile"/"llama-3.1-8b-instant"/"mixtral-8x7b-32768"/"gemma2-9b-it"
# đã hoàn toàn không còn gọi được (404 NOT_FOUND) — xác nhận qua audit thực tế
# (gọi thật API, không đoán tên) ngày 2026-09-14, xem ghi chú trong
# _GEMINI_THINKING_LEVEL_BY_MODEL bên dưới. Danh sách mới đã được gọi thử THẬT
# và xác nhận trả lời thành công với đúng cặp key hiện có trong .env.
AI_MODEL_CATALOG = {
    # flash-lite đứng ĐẦU (mặc định): đo thật 2026-10-12 cùng 1 câu tư vấn — flash-lite
    # 4.0s, flash 66.5s (63.9s mới ra chữ đầu tiên), chất lượng trả lời tương đương.
    "gemini": _get_model_list("gemini", ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-pro-latest"]),
    "groq": _get_model_list("groq", ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "groq/compound-mini", "qwen/qwen3.6-27b"]),
    "openai": _get_model_list("openai", ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]),
    "huggingface": _get_model_list("huggingface", ["Qwen/Qwen2.5-7B-Instruct", "meta-llama/Llama-3.1-8B-Instruct", "google/gemma-2b-it"]),
    "ollama": _get_model_list("ollama", ["qwen2.5:7b", "llama3.2", "llama3", "mistral"]),
}


# Mục 4 (audit 2026-09-14) — cấu hình TƯỜNG MINH theo TỪNG model đã gọi thử
# thật và biết chắc hỗ trợ mức thinking nào, KHÔNG suy đoán qua substring tên
# model (heuristic cũ `"LOW" if "pro" in model.lower() else "MINIMAL"` đã gây
# lỗi thật: "gemini-flash-latest" không hỗ trợ MINIMAL, chỉ hỗ trợ LOW —
# 400 INVALID_ARGUMENT khi đoán sai). Model KHÔNG có trong bảng này ->
# _resolve_gemini_thinking_level() trả về None -> KHÔNG gửi thinking_config,
# an toàn hơn là đoán bừa.
_GEMINI_THINKING_LEVEL_BY_MODEL = {
    "gemini-flash-latest": "LOW",          # xác nhận qua audit: KHÔNG hỗ trợ MINIMAL
    "gemini-flash-lite-latest": "MINIMAL", # xác nhận qua audit: hỗ trợ cả MINIMAL và LOW
    "gemini-pro-latest": "LOW",            # dòng Pro chỉ hỗ trợ LOW/HIGH, không có MINIMAL
    "gemini-2.5-flash": "MINIMAL",
    "gemini-2.5-pro": "LOW",
    "gemini-2.5-flash-lite": "MINIMAL",
}


def _resolve_gemini_thinking_level(model_name: str):
    """Trả về thinking_level đã XÁC NHẬN phù hợp cho đúng model này, hoặc None
    nếu model không nằm trong danh sách đã kiểm chứng (khi đó lời gọi sẽ KHÔNG
    kèm thinking_config thay vì đoán bừa và có nguy cơ 400 INVALID_ARGUMENT)."""
    return _GEMINI_THINKING_LEVEL_BY_MODEL.get(model_name)


def _is_model_unavailable_error(err_text):
    """True nếu lỗi có vẻ do TÊN MODEL không còn tồn tại/bị khai tử (nên đáng thử
    model kế tiếp trong AI_MODEL_CATALOG), False nếu là lỗi khác (sai API key, hết
    quota, mất mạng...) — thử model khác không giải quyết được các lỗi đó."""
    keywords = [
        "not found", "404", "does not exist", "decommissioned",
        "deprecated", "invalid model", "unknown model", "model_not_found",
    ]
    text = str(err_text).lower()
    return any(k in text for k in keywords)


def _is_timeout_error(err) -> bool:
    """True nếu lỗi là hết thời gian chờ (LLM_TIMEOUT_SECONDS) — model đang treo/
    quá tải; nên chuyển sang model dự phòng kế tiếp thay vì bắt người dùng chờ."""
    text = f"{type(err).__name__} {err}".lower()
    return any(k in text for k in ("timeout", "timed out", "deadline", "deadline_exceeded"))


def _is_billing_required_error(err) -> bool:
    """True nếu lỗi là do TÀI KHOẢN provider hết hạn mức thanh toán/tín dụng
    (vd. OpenAI "insufficient_quota"/"credit_balance_exhausted") — khác HẲN
    rate-limit tạm thời (audit 2026-09-14 xác nhận qua gọi thật: lỗi này cũng
    có mã 429 nhưng KHÔNG tự khỏi sau vài phút, thử lại/backoff vô ích, cần
    nạp thêm tiền/tín dụng vào tài khoản). Phải kiểm tra loại này TRƯỚC
    _is_rate_limit_error vì cùng có mã 429."""
    keywords = [
        "insufficient_quota", "credit_balance_exhausted", "no credits remaining",
        "add credits", "billing", "exceeded your current quota",
    ]
    text = str(err).lower()
    return any(k in text for k in keywords)


def _is_rate_limit_error(err) -> bool:
    """True nếu lỗi là do bị giới hạn tần suất truy cập (HTTP 429 / rate limit /
    quota) từ provider — khác hẳn lỗi tên model (xem _is_model_unavailable_error)
    hay lỗi cấu hình (sai key...). Loại lỗi này nên THỬ LẠI sau một khoảng chờ
    tăng dần (exponential backoff) thay vì đổi model hoặc báo lỗi ngay, vì cùng
    model đó vẫn hoạt động bình thường một khi hết bị giới hạn.

    LOẠI TRỪ lỗi hết hạn mức thanh toán (_is_billing_required_error) — cùng có
    mã 429 nhưng KHÔNG phải tạm thời, retry/backoff không giải quyết được."""
    if _is_billing_required_error(err):
        return False
    keywords = [
        "429", "rate limit", "rate_limit", "too many requests",
        "quota exceeded", "resource_exhausted", "resource exhausted",
    ]
    text = str(err).lower()
    return any(k in text for k in keywords)


def _call_with_rate_limit_retry(fn, *args, max_attempts=4, **kwargs):
    """Gọi fn(*args, **kwargs), tự động thử lại (exponential backoff, tối đa
    max_attempts lần) CHỈ KHI lỗi là rate limit (429) — các lỗi khác (sai API
    key, tên model không tồn tại...) ném ra ngay lần đầu vì chờ rồi thử lại
    không giải quyết được. Dùng cho bước "gửi yêu cầu" của mỗi provider cloud
    (Gemini/Groq/OpenAI) — KHÔNG dùng cho việc lặp qua từng chunk stream, vì
    một khi đã bắt đầu nhận dữ liệu thì không thể "thử lại" mà không lặp nội
    dung đã yield."""
    retryer = Retrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception(_is_rate_limit_error),
        reraise=True,
    )
    return retryer(fn, *args, **kwargs)


# Thời gian chờ tối đa (giây) cho MỖI lần gọi provider AI cloud. Trước đây
# genai.Client/Groq/OpenAI được tạo không có timeout (OpenAI/Groq mặc định 600s,
# Gemini không giới hạn) — 1 model bị treo (đã gặp thật với gemini-flash-latest
# > 90s) làm treo luôn giao diện. Hết thời gian chờ -> thử model dự phòng kế tiếp.
LLM_TIMEOUT_SECONDS = float(os.environ.get("DSS_LLM_TIMEOUT", "60") or 60)

_OLLAMA_DEFAULT_URL = "http://localhost:11434"
# Kết quả kiểm tra Ollama dùng CHUNG cho cả server (không theo từng phiên):
# "đang chạy" giữ 30s, "chưa chạy" giữ 120s. Trên Windows, gọi 1 cổng localhost
# không có dịch vụ tốn ~0.8s (localhost -> thử cả IPv6 + IPv4 = ~1.6s) — kiểm tra
# lặp lại theo từng phiên làm mọi lượt chạy lại của trang Trợ lý AI chậm đi.
_OLLAMA_UP_TTL_SECONDS = 30
_OLLAMA_DOWN_TTL_SECONDS = 120
_OLLAMA_STATUS: dict = {}


def ollama_base_url() -> str:
    """URL server Ollama — đọc OLLAMA_BASE_URL (đã có trong .env.example) hoặc
    OLLAMA_HOST (biến chuẩn của Ollama CLI), mặc định localhost:11434. Chạy app
    trong Docker thì đặt OLLAMA_BASE_URL=http://host.docker.internal:11434.
    Có OLLAMA_API_KEY mà không đặt URL -> dùng Ollama Cloud (https://ollama.com)."""
    url = (os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_HOST") or "").strip()
    if not url:
        url = "https://ollama.com" if os.environ.get("OLLAMA_API_KEY", "").strip() else _OLLAMA_DEFAULT_URL
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    # Ollama mặc định chỉ nghe 127.0.0.1 — "localhost" khiến máy thử IPv6 (::1)
    # trước, mất thêm 1 lượt timeout vô ích mỗi lần kiểm tra/gọi.
    url = url.replace("://localhost", "://127.0.0.1")
    return url.rstrip("/")


def _ollama_headers() -> dict:
    key = os.environ.get("OLLAMA_API_KEY", "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


def list_ollama_models(base_url=None, timeout=2.0) -> list:
    """Tên các model đã `ollama pull` trên server (rỗng nếu server không chạy)."""
    try:
        resp = requests.get(f"{(base_url or ollama_base_url()).rstrip('/')}/api/tags",
                            headers=_ollama_headers(), timeout=timeout)
        if resp.status_code == 200:
            return [m.get("name") for m in resp.json().get("models", []) if m.get("name")]
    except Exception:
        pass
    return []


def resolve_ollama_model(requested=None, base_url=None) -> str:
    """Chọn model Ollama THẬT SỰ đã cài: model được yêu cầu (khớp cả khi thiếu
    tag ':latest') -> model đầu tiên trong AI_MODEL_CATALOG đã cài -> model đầu
    tiên server có. Không có gì để chọn thì trả về model yêu cầu/mặc định để
    server báo lỗi rõ ràng."""
    installed = list_ollama_models(base_url)
    wanted = [m for m in ([requested] if requested else []) + AI_MODEL_CATALOG["ollama"] if m]
    for name in wanted:
        for inst in installed:
            if inst == name or inst == f"{name}:latest" or inst.split(":")[0] == name:
                return inst
    if installed:
        return installed[0]
    return requested or AI_MODEL_CATALOG["ollama"][0]


def _check_ollama_running(base_url=None, timeout=None):
    """Kiểm tra Ollama có THỰC SỰ đang chạy tại base_url hay không (khác với biến
    OLLAMA_AVAILABLE — biến đó chỉ kiểm tra thư viện `requests` có cài được không,
    không hề kiểm tra server Ollama thật). Kết quả lưu dùng chung cho cả server
    theo base_url, CÓ HẠN (xem _OLLAMA_UP/DOWN_TTL_SECONDS) — vừa không kiểm tra
    lại mỗi lượt chạy, vừa nhận ra Ollama mới được bật sau tối đa 2 phút."""
    import time as _time

    base_url = (base_url or ollama_base_url()).rstrip("/")
    if timeout is None:
        # Server local trả lời trong vài ms — không chờ lâu khi Ollama chưa bật.
        timeout = 0.8 if ("localhost" in base_url or "127.0.0.1" in base_url) else 3.0
    cached = _OLLAMA_STATUS.get(base_url)
    if cached:
        ttl = _OLLAMA_UP_TTL_SECONDS if cached[0] else _OLLAMA_DOWN_TTL_SECONDS
        if _time.time() - cached[1] < ttl:
            return cached[0]
    running = False
    try:
        resp = requests.get(f"{base_url}/api/tags", headers=_ollama_headers(), timeout=timeout)
        running = resp.status_code == 200
    except Exception:
        running = False
    _OLLAMA_STATUS[base_url] = (running, _time.time())
    return running


class MultiAIProvider:
    """
    HF / Gemini / Groq / Ollama + RAG (embedding nhẹ mặc định: all-MiniLM-L6-v2).

    Thực tế: HF local mặc định Qwen2.5-1.5B (CPU). Đặt DSS_HF_MODEL nếu cần model lớn + đủ GPU/RAM.
    RAG có thể tắt trong UI nếu máy yếu (tránh OOM).
    """
    
    def __init__(self, data_warehouse=None):
        """Khởi tạo MultiAIProvider.

        embedding_model: Lưu mô hình embedding hiện tại (để tái sử dụng)
        _current_embedding_model: Tên mô hình embedding đang được sử dụng
        knowledge_base: Kho tài liệu học tập để tìm kiếm bằng RAG
        data_warehouse: Kho dữ liệu để lấy dữ liệu lịch sử cho RAG
        vector_store: Vector store để cache embeddings
        """
        self.embedding_model = None  # Mô hình embedding hiện tại (dss_config.SentenceTransformer hoặc tuple tokenizer+model)
        self._current_embedding_model = None  # Tên mô hình embedding đang dùng (để cache)
        self.knowledge_base = self._init_enhanced_knowledge_base()  # Khởi tạo knowledge base với 19 tài liệu học tập (doc_001 đến doc_019)
        self.data_warehouse = data_warehouse  # Kho dữ liệu
        self.vector_store = VectorStore()  # Vector store để cache embeddings
    
    def _init_enhanced_knowledge_base(self):
        """
        Khởi tạo knowledge base mở rộng về tài liệu và môn học.
        
        Knowledge base chứa:
        - documents: Danh sách tài liệu học tập với title, content, tags, subject
        - courses: Danh sách khóa học gợi ý
        
        Mỗi document có:
        - id: Mã định danh duy nhất
        - title: Tiêu đề tài liệu
        - content: Nội dung hướng dẫn học tập
        - tags: Các từ khóa để tìm kiếm
        - subject: Môn học liên quan
        """
        GEN_REF = "Tổng hợp từ kinh nghiệm giảng dạy và nguyên tắc học tập phổ biến — không gắn với một nghiên cứu/tác giả cụ thể."
        return {
            "documents": [  # Danh sách tài liệu học tập
                {
                    "id": "doc_001",
                    "title": "Hướng dẫn học Toán cao cấp",
                    "content": "Toán cao cấp yêu cầu nắm vững kiến thức cơ bản về đại số và giải tích. Nên làm bài tập thường xuyên, tham gia nhóm học tập. Tập trung vào việc hiểu bản chất công thức thay vì học thuộc lòng.",
                    "tags": ["toán", "đại số", "giải tích", "toán cao cấp"],
                    "subject": "toán",
                    "reference": GEN_REF,
                    "status": "DRAFT",
                    "source_verified": False,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_002",
                    "title": "Cải thiện điểm Lập trình",
                    "content": "Lập trình cần thực hành nhiều. Làm các bài tập từ dễ đến khó, đọc code mẫu, tham gia các dự án nhỏ. Học từ lỗi và debug code thường xuyên.",
                    "tags": ["lập trình", "coding", "thực hành", "programming"],
                    "subject": "lập trình",
                    "reference": GEN_REF,
                    "status": "DRAFT",
                    "source_verified": False,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_003",
                    "title": "Kỹ năng quản lý thời gian",
                    "content": "Lập lịch học tập hàng tuần, ưu tiên các môn khó, dành thời gian ôn tập đều đặn mỗi ngày. Sử dụng kỹ thuật Pomodoro để tập trung.",
                    "tags": ["quản lý thời gian", "kỹ năng học tập", "time management"],
                    "subject": "kỹ năng",
                    "reference": "Kỹ thuật Pomodoro — Francesco Cirillo (cuối thập niên 1980s), mô tả trong 'The Pomodoro Technique' (Cirillo, 2006).",
                    # NHÓM F (F-0b CONFIRMED): trước đây gán cứng "status": "APPROVED"
                    # ở đây — KHÔNG có người duyệt hay bản ghi duyệt nào thật, tự nhận
                    # "đã kiểm duyệt CẤP TỔ CHỨC" bằng code. Đã đổi "status" thành
                    # "DRAFT" (trung thực: chưa có quy trình duyệt cấp tổ chức nào
                    # thật sự chạy qua đây) — tài liệu này đã được sao chép vào kho
                    # tri thức thật qua `legacy_knowledge_seed.py` với status=
                    # PENDING_REVIEW, CHỈ trở thành nguồn trích dẫn hợp lệ SAU KHI
                    # Admin duyệt THẬT qua `document_approval_service` (có audit log).
                    # `source_verified` GIỮ NGUYÊN True — đây là khái niệm KHÁC (xem
                    # `source_classification.classify_document`): "nội dung có trích
                    # dẫn nguồn thật/kiểm chứng được" (kỹ thuật Pomodoro của Cirillo
                    # LÀ một nguồn có thật, độc lập với việc hệ thống EduDSS đã duyệt
                    # tài liệu hay chưa) — không đổi để không phá vỡ
                    # test_rag_source_governance.py (đếm 4/19 tài liệu có nguồn thật).
                    "status": "DRAFT",
                    "source_verified": True,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_004",
                    "title": "Phương pháp học hiệu quả",
                    "content": "Sử dụng kỹ thuật Pomodoro, học nhóm, tóm tắt kiến thức bằng sơ đồ tư duy, giải thích lại cho người khác. Áp dụng phương pháp Feynman.",
                    "tags": ["phương pháp học", "kỹ năng", "study methods"],
                    "subject": "kỹ năng",
                    "reference": "Kỹ thuật Pomodoro — Francesco Cirillo (Cirillo, 2006); Kỹ thuật Feynman — đặt theo triết lý học/giảng dạy của nhà vật lý Richard Feynman, phổ biến trong cộng đồng tự học như phương pháp 'học bằng cách dạy lại'.",
                    # NHÓM F (F-0b): "status" đổi APPROVED -> DRAFT (xem giải thích
                    # đầy đủ ở doc_003 phía trên). "source_verified" GIỮ NGUYÊN True
                    # — khái niệm khác (nguồn trích dẫn có thật), không phải "đã được
                    # EduDSS duyệt".
                    "status": "DRAFT",
                    "source_verified": True,
                    "permission_scope": "student_learning",
                },

                {
                    "id": "doc_005",
                    "title": "Cải thiện điểm Vật lý",
                    "content": "Vật lý cần hiểu bản chất hiện tượng, không chỉ học thuộc công thức. Làm nhiều bài tập ứng dụng, xem video minh họa, thực hành thí nghiệm.",
                    "tags": ["vật lý", "khoa học", "physics"],
                    "subject": "vật lý",
                    "reference": GEN_REF,
                    "status": "DRAFT",
                    "source_verified": False,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_006",
                    "title": "Học tốt môn Hóa học",
                    "content": "Hóa học cần nắm vững bảng tuần hoàn, hiểu phản ứng hóa học. Làm nhiều bài tập tính toán, học thuộc công thức quan trọng, thực hành thí nghiệm.",
                    "tags": ["hóa học", "chemistry", "khoa học"],
                    "subject": "hóa học",
                    "reference": GEN_REF,
                    "status": "DRAFT",
                    "source_verified": False,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_007",
                    "title": "Cải thiện kỹ năng đọc hiểu",
                    "content": "Đọc hiểu cần luyện tập thường xuyên. Đọc nhiều loại tài liệu, tóm tắt nội dung, trả lời câu hỏi về bài đọc, học từ vựng mới.",
                    "tags": ["đọc hiểu", "reading", "kỹ năng"],
                    "subject": "ngôn ngữ",
                    "reference": GEN_REF,
                    "status": "DRAFT",
                    "source_verified": False,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_008",
                    "title": "Học tốt môn Lịch sử",
                    "content": "Lịch sử cần tạo dòng thời gian, liên kết các sự kiện, học theo chủ đề. Sử dụng sơ đồ tư duy, đọc thêm tài liệu tham khảo.",
                    "tags": ["lịch sử", "history", "xã hội"],
                    "subject": "lịch sử",
                    "reference": GEN_REF,
                    "status": "DRAFT",
                    "source_verified": False,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_009",
                    "title": "Cải thiện Tiếng Anh / ngoại ngữ",
                    "content": "Học ngoại ngữ hiệu quả cần luyện đều 4 kỹ năng (nghe, nói, đọc, viết) thay vì chỉ học ngữ pháp. Nghe podcast/xem phim có phụ đề 15-20 phút/ngày, ghi chú từ vựng theo chủ đề (không học từ đơn lẻ), luyện nói phản xạ qua ứng dụng hoặc bạn học, làm đề thi thử để quen dạng bài. Ưu tiên input dễ hiểu (i+1) — tài liệu chỉ khó hơn trình độ hiện tại một chút.",
                    "tags": ["tiếng anh", "ngoại ngữ", "english", "ngôn ngữ"],
                    "subject": "tiếng anh",
                    "reference": "Giả thuyết Đầu vào (Input Hypothesis, 'i+1') — Stephen Krashen, 'The Input Hypothesis: Issues and Implications' (1985).",
                    # NHÓM F (F-0b): "status" đổi APPROVED -> DRAFT (xem giải thích
                    # đầy đủ ở doc_003 phía trên). "source_verified" GIỮ NGUYÊN True
                    # — khái niệm khác (nguồn trích dẫn có thật), không phải "đã được
                    # EduDSS duyệt".
                    "status": "DRAFT",
                    "source_verified": True,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_010",
                    "title": "Học tốt môn Sinh học",
                    "content": "Sinh học cần hiểu cơ chế (tại sao) chứ không chỉ thuộc thuật ngữ. Vẽ lại sơ đồ quá trình (vd. quang hợp, hô hấp tế bào, di truyền) bằng tay để nhớ lâu hơn đọc suông. Liên hệ kiến thức với ví dụ thực tế trong cơ thể/tự nhiên. Làm bài tập di truyền học (Mendel, phả hệ) đều đặn vì đây là dạng hay mất điểm nhất.",
                    "tags": ["sinh học", "biology", "khoa học"],
                    "subject": "sinh học",
                    "reference": GEN_REF,
                    "status": "DRAFT",
                    "source_verified": False,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_011",
                    "title": "Kỹ năng làm bài kiểm tra và thi cử",
                    "content": "Trước khi làm bài: đọc lướt toàn bộ đề 2-3 phút để phân bổ thời gian theo điểm số từng câu, làm câu chắc ăn trước để tránh mất điểm oan vì hết giờ. Với trắc nghiệm: loại trừ đáp án sai rõ ràng trước, không bỏ trống. Với tự luận: viết dàn ý nhanh trước khi viết chi tiết để không lạc đề. Dành 5-10 phút cuối để rà lại lỗi sai sót (đọc nhầm đề, tính nhầm dấu).",
                    "tags": ["kỹ năng thi cử", "làm bài kiểm tra", "exam skills", "kỹ năng"],
                    "subject": "kỹ năng",
                    "reference": GEN_REF,
                    "status": "DRAFT",
                    "source_verified": False,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_012",
                    "title": "Quản lý stress và tâm lý học tập",
                    "content": "Áp lực điểm số kéo dài dễ dẫn tới burnout, giảm hiệu suất học ngược lại. Nên chia nhỏ mục tiêu lớn thành các cột mốc ngắn hạn để có cảm giác tiến bộ thường xuyên, ngủ đủ 7-8 tiếng (thiếu ngủ làm giảm khả năng ghi nhớ rõ rệt), dành 10-15 phút/ngày cho vận động nhẹ hoặc hít thở để giảm căng thẳng. Nếu cảm thấy quá tải kéo dài, nên chia sẻ với giảng viên/cố vấn học tập thay vì tự chịu đựng.",
                    "tags": ["stress", "tâm lý", "áp lực học tập", "kỹ năng", "sức khỏe tinh thần"],
                    "subject": "kỹ năng",
                    "reference": GEN_REF,
                    "status": "DRAFT",
                    "source_verified": False,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_013",
                    "title": "Kỹ năng thuyết trình và làm việc nhóm",
                    "content": "Thuyết trình tốt cần cấu trúc rõ (mở đầu nêu vấn đề - thân bài giải quyết - kết luận tóm tắt), luyện nói trước gương hoặc quay video để tự sửa. Khi làm việc nhóm: phân chia đầu việc rõ ràng theo thế mạnh từng người, thống nhất deadline từng phần trước deadline chung, họp ngắn định kỳ để theo dõi tiến độ thay vì dồn việc tới sát hạn.",
                    "tags": ["thuyết trình", "làm việc nhóm", "presentation", "teamwork", "kỹ năng"],
                    "subject": "kỹ năng",
                    "reference": GEN_REF,
                    "status": "DRAFT",
                    "source_verified": False,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_014",
                    "title": "Cải thiện Xác suất thống kê",
                    "content": "Xác suất thống kê hay bị nhầm vì thuật ngữ trừu tượng. Nên học qua ví dụ thực tế (tung xúc xắc, khảo sát mẫu) trước khi học công thức tổng quát, phân biệt rõ các khái niệm hay gây nhầm lẫn (phương sai vs độ lệch chuẩn, xác suất có điều kiện vs xác suất đồng thời). Luyện tập với dữ liệu thật (vd. bảng điểm lớp) để thấy ý nghĩa số liệu thay vì chỉ tính toán máy móc.",
                    "tags": ["xác suất", "thống kê", "statistics", "toán"],
                    "subject": "toán",
                    "reference": GEN_REF,
                    "status": "DRAFT",
                    "source_verified": False,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_015",
                    "title": "Kỹ năng viết luận và báo cáo học thuật",
                    "content": "Viết luận/báo cáo cần luận điểm rõ ràng ngay từ đoạn mở đầu, mỗi đoạn thân bài chỉ nên triển khai một ý chính kèm dẫn chứng cụ thể. Tránh lặp ý, câu quá dài; đọc lại và cắt bớt câu thừa sau khi viết xong bản nháp. Luôn trích dẫn nguồn tham khảo rõ ràng để tránh đạo văn không cố ý.",
                    "tags": ["viết luận", "báo cáo", "writing", "học thuật", "kỹ năng"],
                    "subject": "kỹ năng",
                    "reference": GEN_REF,
                    "status": "DRAFT",
                    "source_verified": False,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_016",
                    "title": "Kỹ năng tự học và nghiên cứu tài liệu",
                    "content": "Tự học hiệu quả cần biết chọn lọc nguồn đáng tin cậy (giáo trình, bài báo khoa học) thay vì chỉ đọc tóm tắt trên mạng. Ghi chú theo phương pháp Cornell hoặc sơ đồ tư duy để dễ ôn lại. Đặt câu hỏi khi đọc ('tại sao', 'nếu khác đi thì sao') thay vì đọc thụ động — đây là cách nhớ sâu hơn học vẹt. Định kỳ ôn lại theo nguyên tắc lặp lại ngắt quãng (spaced repetition) thay vì học dồn trước kỳ thi.",
                    "tags": ["tự học", "nghiên cứu", "self-study", "kỹ năng", "phương pháp học"],
                    "subject": "kỹ năng",
                    "reference": "Phương pháp ghi chú Cornell — Walter Pauk, Đại học Cornell, 'How to Study in College' (1962); Lặp lại ngắt quãng (spaced repetition) — dựa trên nghiên cứu đường cong quên (forgetting curve) của Hermann Ebbinghaus (1885), sau này phát triển thành các hệ thống ôn tập thuật toán (vd. SuperMemo).",
                    # NHÓM F (F-0b): "status" đổi APPROVED -> DRAFT (xem giải thích
                    # đầy đủ ở doc_003 phía trên). "source_verified" GIỮ NGUYÊN True
                    # — khái niệm khác (nguồn trích dẫn có thật), không phải "đã được
                    # EduDSS duyệt".
                    "status": "DRAFT",
                    "source_verified": True,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_017",
                    "title": "Cơ sở dữ liệu và phân tích dữ liệu",
                    "content": "Học cơ sở dữ liệu cần thực hành viết truy vấn SQL thường xuyên thay vì chỉ học lý thuyết chuẩn hóa. Bắt đầu từ SELECT/JOIN cơ bản, sau đó tới subquery và tối ưu truy vấn. Với phân tích dữ liệu: luyện làm sạch dữ liệu thật (dữ liệu thiếu, trùng lặp, sai định dạng) trước khi phân tích, vì đây là bước tốn thời gian nhất trong thực tế nhưng ít được dạy kỹ ở trường.",
                    "tags": ["cơ sở dữ liệu", "sql", "phân tích dữ liệu", "xử lý dữ liệu", "database", "lập trình"],
                    "subject": "lập trình",
                    "reference": GEN_REF,
                    "status": "DRAFT",
                    "source_verified": False,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_018",
                    "title": "Trực quan hóa dữ liệu (Data Visualization)",
                    "content": "Trực quan hóa dữ liệu yếu thường do chọn sai loại biểu đồ cho câu hỏi cần trả lời. Luyện theo từng mục đích cụ thể: so sánh giữa các nhóm dùng biểu đồ cột, xu hướng theo thời gian dùng biểu đồ đường, phân bố một biến dùng histogram/boxplot, quan hệ giữa 2 biến số dùng scatter plot. Thực hành vẽ lại 1 bộ dữ liệu quen thuộc (ví dụ điểm số lớp mình) bằng nhiều loại biểu đồ khác nhau để thấy loại nào truyền tải thông tin rõ nhất, tránh biểu đồ rối mắt (quá nhiều màu/nhãn không cần thiết).",
                    "tags": ["trực quan hóa", "visualization", "biểu đồ", "data visualization", "phân tích dữ liệu"],
                    "subject": "phân tích dữ liệu",
                    "reference": GEN_REF,
                    "status": "DRAFT",
                    "source_verified": False,
                    "permission_scope": "student_learning",
                },
                {
                    "id": "doc_019",
                    "title": "Machine Learning cơ bản",
                    "content": "Machine Learning cơ bản hay bị rối vì học công thức toán trước khi hiểu trực giác. Nên bắt đầu từ việc phân biệt rõ 2 nhóm bài toán chính (hồi quy dự đoán số liên tục, phân loại dự đoán nhãn rời rạc), thực hành với 1-2 mô hình đơn giản trước (Linear/Logistic Regression, Decision Tree) trước khi học mô hình phức tạp. Luôn tự hỏi 3 câu khi đánh giá mô hình: mô hình có học quá khớp dữ liệu train không (overfitting), tập test đã tách riêng khỏi tập train chưa, và metric đánh giá có phù hợp với bài toán không (ví dụ Accuracy dễ gây hiểu lầm với dữ liệu mất cân bằng lớp).",
                    "tags": ["machine learning", "học máy", "mô hình dự đoán", "overfitting", "phân loại", "hồi quy"],
                    "subject": "machine learning",
                    "reference": GEN_REF,
                    "status": "DRAFT",
                    "source_verified": False,
                    "permission_scope": "student_learning",
                }

            ],
            "courses": [
                {
                    "id": "course_001",
                    "name": "Toán cơ bản",
                    "description": "Khóa học bổ trợ toán cơ bản cho sinh viên yếu",
                    "difficulty": "beginner"
                },
                {
                    "id": "course_002",
                    "name": "Lập trình Python",
                    "description": "Khóa học lập trình Python từ cơ bản đến nâng cao",
                    "difficulty": "intermediate"
                },
                {
                    "id": "course_003",
                    "name": "Kỹ năng học tập",
                    "description": "Khóa học về phương pháp và kỹ năng học tập hiệu quả",
                    "difficulty": "beginner"
                },
                {
                    "id": "course_004",
                    "name": "Tiếng Anh giao tiếp học thuật",
                    "description": "Khóa học tiếng Anh tập trung kỹ năng đọc-viết học thuật và giao tiếp cơ bản",
                    "difficulty": "beginner"
                },
                {
                    "id": "course_005",
                    "name": "Xác suất thống kê ứng dụng",
                    "description": "Khóa học xác suất thống kê qua ví dụ thực tế, ít nặng lý thuyết hàn lâm",
                    "difficulty": "intermediate"
                },
                {
                    "id": "course_006",
                    "name": "SQL & Phân tích dữ liệu cơ bản",
                    "description": "Khóa học thực hành truy vấn SQL và làm sạch dữ liệu cho người mới bắt đầu",
                    "difficulty": "beginner"
                }
            ]
        }

    def get_api_key_from_secrets(self, provider_name):
        """
        Lấy API key từ Streamlit secrets hoặc environment variables.
        Ưu tiên secrets (an toàn hơn), sau đó là environment variables.
        
        Parameters:
        -----------
        provider_name : str
            Tên provider: "huggingface", "gemini", "groq", "ollama"
        
        Returns:
        --------
        str : API key nếu tìm thấy, chuỗi rỗng nếu không
        
        Quy trình:
        1. Thử lấy từ Streamlit secrets (ưu tiên - an toàn nhất)
        2. Thử các tên key thay thế (HF_TOKEN, GEMINI_API_KEY, etc.)
        3. Fallback: Lấy từ environment variables
        4. Trả về chuỗi rỗng nếu không tìm thấy
        """
        try:
            # Bước 1: Thử lấy từ Streamlit secrets (cho Hugging Face Spaces)
            # Streamlit secrets là cách an toàn nhất để lưu API keys
            if hasattr(st, 'secrets') and st.secrets is not None:
                secrets_dict = st.secrets.to_dict()  # Chuyển secrets thành dictionary
                key_name = f"{provider_name.upper()}_API_KEY"  # Tạo tên key mặc định
                if key_name in secrets_dict:
                    return secrets_dict[key_name]  # Trả về key nếu tìm thấy
                
                # Bước 2: Thử với các tên key thay thế (vì mỗi provider có thể có nhiều tên)
                alt_names = {
                    "huggingface": ["HF_TOKEN", "HUGGINGFACE_TOKEN", "HF_API_KEY"],  # Các tên key cho Hugging Face
                    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],  # Các tên key cho Gemini
                    "groq": ["GROQ_API_KEY"],  # Tên key cho Groq
                    "ollama": ["OLLAMA_API_KEY"],  # Ollama thường không cần key (chạy local)
                    "openai": ["OPENAI_API_KEY"],  # Tên key cho OpenAI
                }
                if provider_name.lower() in alt_names:  # Kiểm tra provider có trong danh sách không
                    for alt in alt_names[provider_name.lower()]:  # Duyệt qua các tên thay thế
                        if alt in secrets_dict:  # Nếu tìm thấy trong secrets
                            return secrets_dict[alt]  # Trả về key
        except Exception:
            # Nếu có lỗi khi đọc secrets (ví dụ: không có secrets), bỏ qua
            pass
        
        # Bước 3: Fallback - lấy từ environment variables (cho môi trường local)
        env_keys = {
            "huggingface": ["HF_TOKEN", "HUGGINGFACE_TOKEN"],  # Environment variables cho Hugging Face
            "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],  # Environment variables cho Gemini
            "groq": ["GROQ_API_KEY"],  # Environment variables cho Groq
            "ollama": ["OLLAMA_API_KEY"],  # Environment variables cho Ollama
            "openai": ["OPENAI_API_KEY"],  # Environment variables cho OpenAI
        }
        if provider_name.lower() in env_keys:  # Kiểm tra provider có trong danh sách không
            for key in env_keys[provider_name.lower()]:  # Duyệt qua các tên environment variable
                value = os.getenv(key, "")  # Lấy giá trị từ environment variable
                if value:  # Nếu tìm thấy giá trị
                    return value  # Trả về key
        
        return ""  # Trả về chuỗi rỗng nếu không tìm thấy key nào
    
    @st.cache_resource  # Cache resource để không phải tải lại model mỗi lần
    def load_embedding_model(_self, model_name="sentence-transformers/all-MiniLM-L6-v2", hf_token=None):
        """
        Tải mô hình embedding để tìm tài liệu phù hợp (RAG).
        
        Parameters:
        -----------
        model_name : str
            Tên mô hình embedding (ví dụ: "sentence-transformers/all-MiniLM-L6-v2")
        hf_token : str, optional
            Hugging Face token để tải các model private
        
        Returns:
        --------
        tuple : (model, error)
            - model: Mô hình embedding (dss_config.SentenceTransformer hoặc tuple (tokenizer, model))
            - error: Thông báo lỗi nếu có, None nếu thành công
        
        Quy trình:
        1. Kiểm tra thư viện có sẵn không
        2. Ưu tiên dùng sentence-transformers (nhanh và dễ dùng hơn)
        3. Fallback: Dùng transformers trực tiếp nếu sentence-transformers không có
        """
        dss_config._ensure_local_llm_libs()
        from dss.core.release import resolve_embedding_model

        model_name = resolve_embedding_model(model_name)
        # Kiểm tra xem có thư viện cần thiết không
        if not dss_config.SENTENCE_TRANSFORMERS_AVAILABLE and not dss_config.HF_AVAILABLE:
            return None, "Chưa cài đặt sentence-transformers hoặc transformers."
        
        try:
            # Ưu tiên 1: Dùng sentence-transformers (nhanh và dễ dùng hơn)
            if dss_config.SENTENCE_TRANSFORMERS_AVAILABLE and dss_config.SentenceTransformer is not None:
                model = dss_config.SentenceTransformer(model_name, token=hf_token)  # Tải mô hình với token nếu cần
                return model, None  # Trả về model và None (không có lỗi)
            
            # Ưu tiên 2: Dùng transformers trực tiếp (fallback)
            if dss_config.HF_AVAILABLE and dss_config.AutoTokenizer is not None and dss_config.AutoModel is not None:
                tokenizer = dss_config.AutoTokenizer.from_pretrained(model_name, token=hf_token)  # Tải tokenizer
                model = dss_config.AutoModel.from_pretrained(model_name, token=hf_token)  # Tải model
                return (tokenizer, model), None  # Trả về tuple (tokenizer, model) và None
            
            # Nếu không có thư viện nào
            return None, "Thư viện cần thiết chưa được cài đặt"
        except Exception as e:
            # Bắt lỗi và trả về thông báo lỗi
            return None, str(e)
    
    @observed("rag.embedding")
    def get_embedding(self, text, embedding_model_name="sentence-transformers/all-MiniLM-L6-v2", hf_token=None):
        """
        Tạo vector embedding cho văn bản.
        
        Parameters:
        -----------
        text : str
            Văn bản cần chuyển thành vector embedding
        embedding_model_name : str
            Tên mô hình embedding để sử dụng
        hf_token : str, optional
            Hugging Face token nếu cần
        
        Returns:
        --------
        numpy.ndarray hoặc None
            Vector embedding của văn bản, None nếu có lỗi
        
        Quy trình:
        1. Kiểm tra xem model đã được load chưa (cache để tăng tốc)
        2. Nếu chưa hoặc khác model, tải model mới
        3. Xử lý tùy theo loại model (sentence-transformers hoặc transformers)
        4. Trả về vector embedding dạng numpy array
        """
        if not isinstance(text, str) or not text or len(text) > 12000:
            return None
        from dss.core.release import resolve_embedding_model

        embedding_model_name = resolve_embedding_model(embedding_model_name)
        try:
            # Kiểm tra xem model đã được load với đúng tên chưa (cache để tăng tốc)
            if self.embedding_model is None or self._current_embedding_model != embedding_model_name:
                # Nếu chưa load hoặc model khác, tải model mới
                self.embedding_model, err = self.load_embedding_model(embedding_model_name, hf_token)
                if err:  # Nếu có lỗi khi tải model
                    return None  # Trả về None
                self._current_embedding_model = embedding_model_name  # Lưu tên model hiện tại
            
            # Xử lý tùy theo loại model được tải
            if isinstance(self.embedding_model, tuple):
                if not dss_config.TORCH_AVAILABLE:
                    return None
                tokenizer, model = self.embedding_model
                inputs = tokenizer(
                    text, return_tensors="pt", padding=True, truncation=True, max_length=512
                )
                if dss_config.TORCH_AVAILABLE:
                    inputs = {k: v.to(model.device) for k, v in inputs.items()}
                with dss_config.torch.no_grad():
                    outputs = model(**inputs)
                embedding = outputs.last_hidden_state.mean(dim=1).squeeze()
            else:
                # Trường hợp 2: Model là dss_config.SentenceTransformer (dễ dùng hơn)
                embedding = self.embedding_model.encode(text, convert_to_tensor=True)  # Encode text thành vector
            
            # Chuyển embedding về numpy array (từ tensor nếu cần)
            return embedding.cpu().numpy() if hasattr(embedding, 'cpu') else embedding
        except Exception:
            # Nếu có lỗi, trả về None
            return None
    
    def find_relevant_documents_rag(self, query_text, top_k=dss_config.RAG_TOP_K_DEFAULT, embedding_model_name="sentence-transformers/all-MiniLM-L6-v2",
                                     hf_token=None, use_warehouse_data=True, runtime_documents=None,
                                     role="Sinh viên", namespace="student_learning", mode=None):
        """
        Tìm tài liệu phù hợp nhất sử dụng RAG (Retrieval-Augmented Generation).
        Sử dụng embedding để tìm các tài liệu có độ tương đồng cao nhất với điểm yếu của sinh viên.
        TÍCH HỢP: Sử dụng dữ liệu từ kho (warehouse) để học từ lịch sử.
        
        Parameters:
        -----------
        query_text : str
            Câu truy vấn (ví dụ: "cách cải thiện điểm toán")
        top_k : int
            Số lượng tài liệu phù hợp nhất cần trả về
        embedding_model_name : str
            Tên mô hình embedding để sử dụng
        hf_token : str, optional
            Hugging Face token nếu cần
        use_warehouse_data : bool
            Có sử dụng dữ liệu từ kho để học không
        
        Returns:
        --------
        list : Danh sách các tài liệu phù hợp nhất (top_k documents)
        
        Quy trình RAG nâng cấp:
        1. Tạo embedding cho câu truy vấn
        2. Lấy tài liệu từ knowledge base + dữ liệu từ kho (nếu bật)
        3. Sử dụng VectorStore để cache embeddings (tăng tốc)
        4. Tính cosine similarity giữa query và mỗi document
        5. Sắp xếp theo độ tương đồng giảm dần
        6. Trả về top_k tài liệu phù hợp nhất
        # Bước 1: Thu thập toàn bộ tài liệu từ knowledge base và kho dữ liệu
        """
        if not isinstance(query_text, str) or len(query_text) > 2000 or top_k < 1 or top_k > 20:
            return []
        active_mode = mode or os.environ.get("EDUDSS_MODE", "DEMO_SYNTHETIC")
        from dss.core.runtime_mode import is_production as _is_production
        all_documents = []
        
        # 1a. Thêm tài liệu từ knowledge base
        for doc in self.knowledge_base["documents"]:
            # MỤC 11 & 12: Trong REAL_LMS mode, chỉ tài liệu APPROVED và có source_verified mới được truy xuất
            if active_mode == "REAL_LMS" or _is_production():
                if doc.get("status") != "APPROVED" or not doc.get("source_verified"):
                    continue

            all_documents.append({
                'id': doc['id'],
                'title': doc['title'],
                'content': doc['content'],
                'tags': doc.get('tags', []),
                'source': 'knowledge_base',
                'reference': doc.get('reference', ''),
                'status': doc.get('status', 'DRAFT'),
                'source_verified': doc.get('source_verified', False),
                'permission_scope': doc.get('permission_scope', 'student_learning'),
                'text': f"{doc['title']} {doc['content']} {' '.join(doc.get('tags', []))}"
            })


        # 1b. Thêm tài liệu runtime từ dataset đang upload (nếu có)
        for i, doc in enumerate((runtime_documents or [])[:20]):
            title = str(doc.get("title", f"Ngữ cảnh dataset #{i+1}"))
            content = str(doc.get("content", ""))[:4000].strip()
            if not content:
                continue
            tags = doc.get("tags", [])
            if not isinstance(tags, list):
                tags = [str(tags)]
            all_documents.append({
                "id": str(doc.get("id", f"runtime_{i}")),
                "title": title,
                "content": content,
                "tags": tags,
                "source": doc.get("source", "uploaded_dataset"),
                "text": f"{title} {content} {' '.join(tags)}",
            })
            
        # Bước 2: Tạo embedding cho câu truy vấn
        query_embedding = self.get_embedding(query_text, embedding_model_name, hf_token)
        
        # 2b. Thêm dữ liệu từ kho (warehouse) nếu bật VÀ thuộc namespace admin_operations
        # MỤC 13: Cố vấn học tập sinh viên tuyệt đối KHÔNG trộn lịch sử đánh giá mô hình / huấn luyện vào tài liệu học tập
        if use_warehouse_data and self.data_warehouse and namespace == "admin_operations" and role == "Admin":

            # Lấy dữ liệu đánh giá để học từ kết quả
            evaluations = self.data_warehouse.get_evaluation_data_for_rag(limit=10)
            for eval_data in evaluations:
                model_name = eval_data.get('model_name', 'Unknown')
                metrics = eval_data.get('evaluation_results', {})
                
                # Tạo document từ dữ liệu đánh giá
                content = f"Mô hình {model_name} đã được huấn luyện với kết quả: "
                if isinstance(metrics, dict):
                    metric_str = ", ".join([f"{k}: {v:.4f}" if isinstance(v, (int, float)) else f"{k}: {v}" 
                                           for k, v in list(metrics.items())[:5]])
                    content += metric_str
                
                all_documents.append({
                    'id': f"eval_{eval_data.get('evaluation_id', '')}",
                    'title': f"Kết quả đánh giá mô hình {model_name}",
                    'content': content,
                    'tags': ['đánh giá', 'mô hình', model_name.lower()],
                    'source': 'warehouse_evaluation',
                    'text': f"Kết quả đánh giá mô hình {model_name} {content}"
                })
            
            # Lấy lịch sử huấn luyện
            training_history = self.data_warehouse.get_training_history_for_rag(limit=5)
            for train_data in training_history:
                model_name = train_data.get('model_name', 'Unknown')
                metrics = train_data.get('metrics', {})
                
                content = f"Mô hình {model_name} đã được huấn luyện. "
                if isinstance(metrics, dict):
                    metric_str = ", ".join([f"{k}: {v:.4f}" if isinstance(v, (int, float)) else f"{k}: {v}" 
                                           for k, v in list(metrics.items())[:3]])
                    content += f"Metrics: {metric_str}"
                
                all_documents.append({
                    'id': f"train_{train_data.get('training_id', '')}",
                    'title': f"Lịch sử huấn luyện {model_name}",
                    'content': content,
                    'tags': ['huấn luyện', 'lịch sử', model_name.lower()],
                    'source': 'warehouse_training',
                    'text': f"Lịch sử huấn luyện {model_name} {content}"
                })
        
        # Bước 3: Tính toán điểm tương đồng
        similarities = []
        
        if query_embedding is not None:
            # 3a. Dùng Embeddings
            for doc in all_documents:
                doc_id = doc['id']
                doc_text = doc['text']
                # Tài liệu runtime (hồ sơ sinh viên đang tư vấn, dữ liệu upload) có ID cố
                # định theo student_id nhưng NỘI DUNG thay đổi mỗi lần tính lại — không được
                # dùng cache trên đĩa (vĩnh viễn theo doc_id) cho loại này, nếu không lần tư
                # vấn sau sẽ so khớp bằng embedding cũ dù nội dung đã khác.
                is_persistent_doc = doc.get('source') in (
                    'knowledge_base', 'warehouse_evaluation', 'warehouse_training'
                )
                doc_embedding = (
                    self.vector_store.load_embedding(doc_id, embedding_model_name)
                    if is_persistent_doc else None
                )

                if doc_embedding is None:
                    # Nếu chưa có trong cache, tạo embedding mới
                    doc_embedding = self.get_embedding(doc_text, embedding_model_name, hf_token)
                    if doc_embedding is not None and is_persistent_doc:
                        # Lưu vào cache để lần sau không phải tính lại (chỉ áp dụng cho
                        # tài liệu có nội dung ổn định lâu dài)
                        self.vector_store.save_embedding(doc_id, doc_embedding, embedding_model_name)
                        self.vector_store.save_document(doc_id, doc)

                if doc_embedding is not None:
                    similarity = cosine_similarity([query_embedding], [doc_embedding])[0][0]
                    similarities.append((doc, similarity))
        else:
            # 3b. Fallback: Dùng mô hình truy xuất văn bản cơ bản (TF-IDF) nếu không có Torch/Embeddings
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.metrics.pairwise import cosine_similarity as tfidf_cossim
                
                corpus = [doc['text'] for doc in all_documents]
                corpus.append(query_text) # document cuối cùng là câu truy vấn

                vectorizer = TfidfVectorizer().fit_transform(corpus)
                vectors = vectorizer.toarray()
                
                query_vec = vectors[-1:] # vector truy vấn
                doc_vecs = vectors[:-1]  # vector tài liệu
                
                sim_scores = tfidf_cossim(query_vec, doc_vecs)[0]
                # Không lọc cứng theo % ở đây nữa — bước lọc TƯƠNG ĐỐI dùng chung
                # bên dưới (RAG_RELATIVE_THRESHOLD) đã xử lý việc loại tài liệu
                # không liên quan, nhất quán với nhánh embedding.
                for i, doc in enumerate(all_documents):
                    similarities.append((doc, float(sim_scores[i])))
            except Exception:
                # Nếu vẫn lỗi, trở về phương án từ khóa đơn giản nhất
                query_words = set(query_text.lower().split())
                for doc in all_documents:
                    score = sum(1 for w in query_words if len(w) > 3 and w in doc['text'].lower())
                    if score > 0: similarities.append((doc, float(score)))

        # Bước 4: Sắp xếp theo độ tương đồng giảm dần
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Bước 4b: MỤC 14 - NO-EVIDENCE RETRIEVAL
        # LOẠI BỎ hoàn toàn quy tắc ép giữ lại tài liệu đứng đầu (or similarities[:1]).
        # Nếu không có tài liệu hoặc điểm của tài liệu đứng đầu < RAG_LOW_CONFIDENCE_FLOOR,
        # TRẢ VỀ RỖNG [] để LLM không bịa đặt câu trả lời từ tài liệu lạc đề.
        if not similarities:
            return []

        top1_score = similarities[0][1]
        if top1_score < dss_config.RAG_LOW_CONFIDENCE_FLOOR:
            # Sàn tin cậy không đạt -> câu hỏi lạc đề / không có bằng chứng
            return []

        cutoff = top1_score * dss_config.RAG_RELATIVE_THRESHOLD
        similarities = [item for item in similarities if item[1] >= cutoff]

        # Bước 5: Trả về top_k tài liệu phù hợp nhất
        results = []
        for doc, score in similarities[:top_k]:
            doc_out = dict(doc)
            doc_out['relevance_score'] = float(score)
            doc_out['low_confidence'] = False
            results.append(doc_out)
        return results


    # Các cột điểm số trong dataset mẫu là chỉ số tổng hợp (không gắn với 1 môn học cụ
    # thể), nên không thể tìm tài liệu RAG theo môn (Toán/Hóa/Sinh...) từ tên cột thô —
    # ánh xạ sang chủ đề kỹ năng thực sự liên quan để tránh khớp nhầm tài liệu môn học.
    _COLUMN_RAG_TOPIC_HINTS = {
        'diem_giua_ky': 'phương pháp học và ôn tập hiệu quả, kỹ năng làm bài kiểm tra',
        'diem_ky_nay': 'phương pháp học tổng thể, cải thiện kết quả học kỳ',
        'diem_ky_sau': 'phương pháp học tổng thể, cải thiện kết quả học kỳ',
        'diem_du_an': 'kỹ năng làm dự án, làm việc nhóm, quản lý thời gian dự án',
        'so_gio_hoc_tuan': 'quản lý thời gian học tập hàng tuần',
        'ty_le_diem_danh': 'động lực học tập, duy trì thói quen học đều đặn, quản lý stress',
        'gpa_previous': 'phương pháp học tổng thể và duy trì kết quả học tập',
        'final_score': 'phương pháp học tổng thể, cải thiện kết quả học kỳ',
        # Điểm theo chủ đề (TOPIC_SCORE_COLUMNS) — dịch sang đúng từ khóa khớp tag
        # trong Kho tri thức để RAG tìm đúng tài liệu về chủ đề đang yếu.
        'diem_thong_ke': 'xác suất thống kê',
        'diem_xu_ly_du_lieu': 'phân tích dữ liệu, xử lý dữ liệu, làm sạch dữ liệu',
        'diem_truc_quan_hoa': 'trực quan hóa dữ liệu, biểu đồ',
        'diem_machine_learning': 'machine learning, học máy',
        'diem_lap_trinh': 'lập trình, coding, thực hành',
    }

    def _build_rag_query_from_weaknesses(self, student_weaknesses, student_profile=None):
        """Tạo câu truy vấn RAG giàu ngữ cảnh từ danh sách điểm yếu."""
        from dss.core.data_helpers import feature_label

        # A-3: điểm yếu THẬT do ai_advisor.py tạo có dạng
        # "**<Nhãn tiếng Việt>** (SV: x, TB lớp: y)" — NHÃN, không phải tên cột kỹ
        # thuật — nên tra thẳng theo _COLUMN_RAG_TOPIC_HINTS (khóa = tên cột) không
        # bao giờ khớp, là code chết trong luồng thật. Tra thêm theo NHÃN tiếng Việt
        # (feature_label(col)) để khớp đúng định dạng thật; vẫn giữ tra theo tên cột
        # kỹ thuật để tương thích ngược với nơi gọi truyền thẳng tên cột.
        label_hints = {
            feature_label(col).strip().lower(): hint
            for col, hint in self._COLUMN_RAG_TOPIC_HINTS.items()
        }
        cleaned_topics = []
        for weakness in (student_weaknesses or []):
            base = str(weakness).split("(")[0].strip().strip("*").strip().lower()
            # Nếu là tên cột/nhãn điểm số tổng hợp (không phải tên môn học), dịch
            # sang chủ đề kỹ năng liên quan để RAG không khớp nhầm sang tài liệu
            # môn học cụ thể.
            base = self._COLUMN_RAG_TOPIC_HINTS.get(base) or label_hints.get(base) or base
            if base and base not in cleaned_topics:
                cleaned_topics.append(base)

        if not cleaned_topics:
            cleaned_topics = ["quản lý thời gian", "phương pháp học hiệu quả"]

        profile = student_profile or {}
        risk_level = profile.get("risk_level", "trung bình")
        progress_note = profile.get("progress_note", "chưa có dữ liệu tiến bộ rõ ràng")
        return (
            f"Tư vấn kế hoạch học tập cá nhân hóa cho sinh viên có rủi ro {risk_level}. "
            f"Các điểm yếu chính: {', '.join(cleaned_topics[:5])}. "
            f"Tiến bộ gần đây: {progress_note}. "
            "Ưu tiên tài liệu giúp cải thiện GPA và kỹ năng tự học."
        )

    def _estimate_study_weeks(self, predicted_gpa, weakness_count):
        """Thời lượng kế hoạch cố định 4 tuần — đủ ngắn để cụ thể, hành động được ngay,
        thay vì kéo dài 6-8 tuần khiến kế hoạch dễ bị chung chung ở các tuần cuối."""
        return 4

    def _prepare_personalized_advice_prompt(
        self, student_weaknesses, predicted_gpa, relevant_docs, student_profile=None
    ):
        """Trả về prompt + metadata dùng cho cả stream và fallback.

        Bảo mật (Phase 8A): `risk_level`/`progress_note`/từng điểm yếu được
        làm sạch qua `sanitize_student_text` (che định danh, giới hạn độ
        dài) trước khi vào prompt. Tài liệu RAG (`relevant_docs`, nội dung
        có thể đến từ dữ liệu người dùng tải lên / pgvector) được coi là DỮ
        LIỆU KHÔNG ĐÁNG TIN — đưa vào prompt qua `render_retrieved_context`
        (bọc rõ ràng, loại câu lệnh giống prompt-injection) thay vì nối
        chuỗi trực tiếp. `relevant_docs_str` (hiển thị UI fallback cho
        người dùng) vẫn giữ định dạng gạch đầu dòng dễ đọc, tách biệt khỏi
        khối văn bản KHÔNG ĐÁNG TIN thực sự gửi cho AI provider."""
        profile = student_profile or {}
        # K-3: nhãn nguồn số liệu (mô hình Production hay điểm quan sát được) do
        # ai_advisor.py truyền vào qua predict_for_student() — KHÔNG mặc định
        # gọi đây là "dự đoán" khi không chắc số liệu có qua mô hình hay không.
        gpa_label = sanitize_student_text(profile.get("gpa_label", "Điểm dự đoán (GPA)"), max_chars=100)
        risk_level = sanitize_student_text(profile.get("risk_level", "trung bình"), max_chars=100)
        progress_note = sanitize_student_text(profile.get("progress_note", "chưa có dữ liệu tiến bộ rõ ràng"), max_chars=300)
        plan_weeks = int(profile.get("plan_weeks") or self._estimate_study_weeks(predicted_gpa, len(student_weaknesses or [])))

        weaknesses_str = (
            "\n".join([f"- {sanitize_student_text(w, max_chars=200)}" for w in (student_weaknesses or [])[:10]])
            if student_weaknesses
            else "- Không có điểm yếu đặc biệt"
        )
        relevant_docs_str = (
            "\n".join(
                [f"- **{sanitize_student_text(doc.get('title', ''), max_chars=150)}**: "
                 f"{sanitize_student_text(doc.get('content', ''), max_chars=500)}..." for doc in relevant_docs[:5]]
            )
            if relevant_docs
            else "- Không có tài liệu gợi ý"
        )
        low_confidence_note = ""
        if relevant_docs and any(doc.get("low_confidence") for doc in relevant_docs):
            # Điểm tương đồng RAG thấp ngay cả với tài liệu đứng đầu (xem
            # RAG_LOW_CONFIDENCE_FLOOR ở dss/config.py) — không chắc các tài liệu
            # trên thực sự khớp chủ đề, nhắc LLM không trích dẫn như chắc chắn.
            low_confidence_note = (
                "\n\n(Lưu ý: độ liên quan giữa các tài liệu trên với điểm yếu đang tư vấn không cao — "
                "hãy dùng như tham khảo mở rộng, không khẳng định chắc chắn khớp chủ đề.)"
            )
            relevant_docs_str += low_confidence_note
        context_block = render_retrieved_context(relevant_docs or []) + low_confidence_note
        prompt = f"""{AI_SYSTEM_POLICY}

Bạn là một cố vấn học tập gần gũi, tinh tế và thực tế. Mục tiêu là giúp sinh viên thấy rõ hướng đi tiếp theo, theo giọng văn tự nhiên như một người thầy/cố vấn giàu kinh nghiệm.

## THÔNG TIN SINH VIÊN:
- {gpa_label}: {predicted_gpa:.2f}
- Mức độ rủi ro học tập: {risk_level}
- Mức độ tiến bộ gần đây: {progress_note}
- Điểm yếu được phát hiện:
{weaknesses_str}

## TÀI LIỆU GỢI Ý (RAG):
{context_block}

## YÊU CẦU:
Viết một báo cáo phân tích và kế hoạch học tập CHI TIẾT trong {plan_weeks} tuần, gồm các phần:
1. Tóm tắt tình trạng học tập — nêu rõ nguyên nhân khả dĩ đằng sau từng điểm yếu, không chỉ liệt kê lại số liệu.
2. Cảnh báo rủi ro — giải thích vì sao mức độ rủi ro này đáng lo (hoặc không), hậu quả cụ thể nếu không cải thiện.
3. Kế hoạch học tập theo từng tuần (liệt kê rõ Tuần 1...Tuần {plan_weeks}) — mỗi tuần cần có: mục tiêu cụ thể, 2-3 hoạt động/bài tập THỰC TẾ (không chỉ nói chung chung "ôn tập"), và tiêu chí biết đã hoàn thành tuần đó.
4. Đề xuất môn ưu tiên — giải thích lý do ưu tiên môn này trước, kèm ví dụ dạng bài/chủ đề cụ thể cần tập trung.
5. Gợi ý tài liệu cụ thể bám theo điểm yếu — trích dẫn rõ nội dung nào trong TÀI LIỆU GỢI Ý ở trên áp dụng cho điểm yếu nào, và cách áp dụng.
6. KPI theo dõi tiến độ mỗi tuần (ví dụ số giờ học, số bài tập, mini test) — đưa con số cụ thể, không nói chung chung.

Viết tiếng Việt mạch lạc, ấm áp, không dùng giọng mệnh lệnh kiểu "phải/lập tức", hạn chế văn phong máy móc. Ưu tiên tính cụ thể/hành động được ngay hơn là câu chữ hoa mỹ — mỗi gợi ý nên có ví dụ hoặc con số đi kèm."""
        return prompt, weaknesses_str, relevant_docs_str, {
            "plan_weeks": plan_weeks,
            "risk_level": risk_level,
            "progress_note": progress_note,
        }
    
    @observed("ai.provider", metadata=lambda self, prompt, provider="huggingface", model_name=None, **kwargs: {
        "provider": provider, "model": model_name or "default"})
    def call_ai_provider(self, prompt, provider="huggingface", model_name=None, **kwargs):
        """
        Gọi AI provider để tạo phản hồi (Streaming).
        Hỗ trợ: huggingface, gemini, groq, ollama
        """
        if not prompt_within_limit(prompt):
            yield "Yêu cầu AI rỗng hoặc vượt giới hạn độ dài. Vui lòng rút gọn nội dung."
            return
        provider = provider.lower()
        if provider == "huggingface":
            dss_config._ensure_local_llm_libs()

        if provider == "huggingface" and dss_config.HF_AVAILABLE:
            hf_token = kwargs.get("hf_token", self.get_api_key_from_secrets("huggingface"))
            # Mặc định nhẹ cho CPU; đặt DSS_HF_MODEL (env) nếu có GPU/RAM lớn (vd. Llama-8B).
            model_name = model_name or os.environ.get(
                "DSS_HF_MODEL", "Qwen/Qwen2.5-1.5B-Instruct"
            )
            try:
                if not dss_config.TORCH_AVAILABLE:
                    yield "Lỗi Hugging Face: cần cài PyTorch (torch) để chạy model cục bộ."
                    return
                try:
                    from transformers import TextIteratorStreamer
                    from threading import Thread
                except ImportError:
                    yield "Lỗi Hugging Face: thiếu TextIteratorStreamer (transformers quá cũ?)."
                    return
                if not getattr(self, "hf_tokenizer", None) or getattr(
                    self, "_hf_loaded_name", None
                ) != model_name:
                    self.hf_tokenizer = dss_config.AutoTokenizer.from_pretrained(
                        model_name, token=hf_token
                    )
                    load_kw = dict(
                        token=hf_token,
                        low_cpu_mem_usage=True,
                    )
                    if dss_config.torch.cuda.is_available():
                        load_kw["torch_dtype"] = "auto"
                        load_kw["device_map"] = "auto"
                    else:
                        load_kw["torch_dtype"] = dss_config.torch.float32
                        load_kw["device_map"] = None
                    try:
                        self.hf_model = dss_config.AutoModelForCausalLM.from_pretrained(
                            model_name, **load_kw
                        )
                    except Exception as load_err:
                        for attr in ("hf_model", "hf_tokenizer"):
                            if hasattr(self, attr):
                                delattr(self, attr)
                        self._hf_loaded_name = None
                        _logger.warning("Hugging Face model load failed (model=%s): %s", model_name, type(load_err).__name__)
                        yield "Lỗi Hugging Face: không tải được model — thử model nhỏ hơn hoặc dùng Groq/Gemini."
                        return
                    if load_kw.get("device_map") is None:
                        self.hf_model = self.hf_model.to("cpu")
                    self._hf_loaded_name = model_name
                inputs = self.hf_tokenizer(
                    f"{AI_SYSTEM_POLICY}\n\n{prompt}", return_tensors="pt", truncation=True, max_length=2048
                )
                inputs = {
                    k: v.to(self.hf_model.device) for k, v in inputs.items()
                }
                streamer = TextIteratorStreamer(
                    self.hf_tokenizer, skip_prompt=True, skip_special_tokens=True
                )
                gen_kw = dict(
                    **inputs,
                    streamer=streamer,
                    max_new_tokens=min(int(kwargs.get("max_new_tokens", 1000)), 1500),
                    temperature=0.7,
                    do_sample=True,
                    top_p=0.9,
                    pad_token_id=getattr(
                        self.hf_tokenizer, "pad_token_id", None
                    )
                    or getattr(self.hf_tokenizer, "eos_token_id", None),
                )
                thread = Thread(target=self.hf_model.generate, kwargs=gen_kw)
                thread.start()
                for new_text in streamer:
                    yield new_text
            except Exception as e:
                _logger.warning("Hugging Face provider failed: error_type=%s", type(e).__name__)
                yield "Lỗi Hugging Face: không thể hoàn tất yêu cầu."

        elif provider == "gemini" and GEMINI_AVAILABLE:
            api_key = kwargs.get("api_key") or self.get_api_key_from_secrets("gemini")
            if not api_key:
                yield "Lỗi Gemini: chưa tìm thấy API key. Vui lòng nhập key hoặc cấu hình GEMINI_API_KEY/GOOGLE_API_KEY."
                return
            # Thử lần lượt model được truyền vào trước, rồi tới danh sách dự phòng
            # trong AI_MODEL_CATALOG — khi Google đổi tên/khai tử 1 model, hệ thống tự
            # chuyển sang model kế tiếp thay vì phải sửa code (xem _is_model_unavailable_error).
            candidates = ([model_name] if model_name else []) + [
                m for m in AI_MODEL_CATALOG["gemini"] if m != model_name
            ]
            last_err = None
            for candidate_model in candidates:
                any_output = False
                try:
                    client = genai.Client(
                        api_key=api_key,
                        http_options=genai.types.HttpOptions(timeout=int(LLM_TIMEOUT_SECONDS * 1000)),
                    )
                    # Các model Gemini 3.x có bước "suy nghĩ" (thinking) ẩn trước khi trả lời, và
                    # token dùng cho bước này bị trừ CHUNG vào max_output_tokens — tệ hơn, mức suy
                    # nghĩ mặc định tỉ lệ THUẬN với max_output_tokens (cho ngân sách càng lớn, model
                    # càng nghĩ nhiều), nên chỉ tăng max_output_tokens không giải quyết được (đã xác
                    # nhận qua thực tế: tăng 3000 -> 16384 vẫn bị cắt ngang). Cách xử lý đúng là chủ
                    # động khống chế mức suy nghĩ bằng thinking_level — model Pro chỉ hỗ trợ LOW/HIGH,
                    # các model Flash hỗ trợ thêm MINIMAL (ít token suy nghĩ nhất). Mức hỗ trợ
                    # KHÁC NHAU theo từng model cụ thể (không suy đoán được qua tên) — dùng bảng
                    # tường minh _GEMINI_THINKING_LEVEL_BY_MODEL (đã gọi thử thật để xác nhận);
                    # model lạ/chưa xác minh thì KHÔNG gửi thinking_config (an toàn hơn đoán bừa).
                    gen_config_kwargs = {"max_output_tokens": 8192, "system_instruction": AI_SYSTEM_POLICY}
                    thinking_level = _resolve_gemini_thinking_level(candidate_model)
                    if thinking_level:
                        gen_config_kwargs["thinking_config"] = genai.types.ThinkingConfig(thinking_level=thinking_level)
                    response = _call_with_rate_limit_retry(
                        client.models.generate_content_stream,
                        model=candidate_model,
                        contents=prompt,
                        config=genai.types.GenerateContentConfig(**gen_config_kwargs),
                    )
                    usage_metadata = None
                    for chunk in response:
                        # SDK mới (google.genai): .text trả về None gọn gàng khi chunk không có
                        # phần văn bản hợp lệ (vd. chunk chỉ mang metadata) và tự loại phần "suy
                        # nghĩ" ra khỏi .text — không cần try/except như SDK cũ.
                        usage_metadata = getattr(chunk, "usage_metadata", None) or usage_metadata
                        text = chunk.text
                        if text:
                            any_output = True
                            yield text
                    # Số token thật (gồm token suy nghĩ) từ chunk cuối -> chi phí khớp hoá đơn.
                    from dss.services import llm_usage
                    llm_usage.from_gemini("gemini", candidate_model, usage_metadata)
                    return
                except Exception as e:
                    last_err = e
                    if _is_billing_required_error(e):
                        # KHÁC HẲN rate-limit tạm thời — tài khoản hết hạn mức thanh toán/tín
                        # dụng, retry/đổi model không giải quyết được. Chỉ log LOẠI lỗi.
                        _logger.warning("Gemini billing/quota het han muc (model=%s): %s", candidate_model, type(e).__name__)
                        yield ("💳 Hệ thống AI (Gemini) hiện không thể dùng do tài khoản đã hết hạn mức thanh toán/tín dụng. "
                               "Vui lòng liên hệ Admin để nạp thêm hoặc chọn nguồn AI khác.")
                        return
                    if not any_output and _is_rate_limit_error(e):
                        # Đã thử lại (exponential backoff) qua _call_with_rate_limit_retry
                        # nhưng vẫn bị giới hạn tần suất — báo thân thiện, không lộ lỗi thô.
                        # Chỉ log LOẠI lỗi (không log str(e) đầy đủ — một số SDK có thể vô
                        # tình chèn thông tin request vào message lỗi).
                        _logger.warning("Gemini rate-limit sau khi đã retry (model=%s): %s", candidate_model, type(e).__name__)
                        yield ("⏳ Hệ thống AI (Gemini) đang bị giới hạn tần suất truy cập. "
                               "Đã tự động thử lại nhiều lần nhưng chưa thành công — vui lòng thử lại sau ít phút.")
                        return
                    if any_output or not (_is_model_unavailable_error(e) or _is_timeout_error(e)):
                        # Đã lỡ trả ra nội dung (không đổi model giữa chừng) hoặc lỗi không
                        # liên quan tên model (sai key/hết quota...) — thử model khác vô ích.
                        # KHÔNG bao giờ đưa str(e) thô ra người dùng — SDK có thể vô tình chèn
                        # thông tin request/key vào message lỗi. Chi tiết đầy đủ chỉ vào log kỹ thuật.
                        _logger.exception("Lỗi Gemini (model=%s)", candidate_model)
                        yield "⚠️ Hệ thống AI (Gemini) hiện gặp sự cố. Vui lòng thử lại sau hoặc chọn nguồn AI khác."
                        return
            _logger.error("Gemini: hết danh sách model dự phòng (%s). Lỗi cuối: %s", ", ".join(candidates), type(last_err).__name__ if last_err else "—")
            yield f"Lỗi Gemini: không gọi được model nào trong danh sách dự phòng ({', '.join(candidates)}). Vui lòng thử lại sau."

        elif provider == "groq" and GROQ_AVAILABLE:
            api_key = kwargs.get("api_key") or self.get_api_key_from_secrets("groq")
            if not api_key:
                yield "Lỗi Groq: chưa tìm thấy API key. Vui lòng nhập key hoặc cấu hình GROQ_API_KEY."
                return
            candidates = ([model_name] if model_name else []) + [
                m for m in AI_MODEL_CATALOG["groq"] if m != model_name
            ]
            last_err = None
            for candidate_model in candidates:
                any_output = False
                try:
                    client = Groq(api_key=api_key, timeout=LLM_TIMEOUT_SECONDS, max_retries=0)
                    stream = _call_with_rate_limit_retry(
                        client.chat.completions.create,
                        model=candidate_model,
                        messages=[
                            # Dùng tiếng Anh thuần ASCII cho system prompt — chuỗi tiếng Việt có dấu
                            # ở đây từng khiến client Groq/httpx trên Windows crash với
                            # "UnicodeEncodeError: 'ascii' codec can't encode character...". Ngôn ngữ
                            # đầu ra vẫn là tiếng Việt vì đã được yêu cầu rõ trong nội dung prompt chính.
                            {"role": "system", "content": AI_SYSTEM_POLICY},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        # Đã xác nhận qua thực tế: 3000 token bị cắt ngang giữa chừng với báo cáo
                        # nhiều tuần chi tiết — model hỗ trợ tới 65.536 token nên nâng lên 8192.
                        max_tokens=8192,
                        stream=True
                    )
                    stream_usage = None
                    for chunk in stream:
                        # Chunk cuối mang usage (OpenAI: stream_options include_usage, choices rỗng;
                        # Groq: x_groq.usage) — không đọc choices[0] khi danh sách rỗng.
                        stream_usage = (getattr(chunk, "usage", None)
                                        or getattr(getattr(chunk, "x_groq", None), "usage", None) or stream_usage)
                        choices = getattr(chunk, "choices", None) or []
                        if choices and choices[0].delta.content is not None:
                            any_output = True
                            yield choices[0].delta.content
                    from dss.services import llm_usage
                    llm_usage.from_openai_compatible("groq", candidate_model, stream_usage)
                    return
                except Exception as e:
                    last_err = e
                    if _is_billing_required_error(e):
                        _logger.warning("Groq billing/quota het han muc (model=%s): %s", candidate_model, type(e).__name__)
                        yield ("💳 Hệ thống AI (Groq) hiện không thể dùng do tài khoản đã hết hạn mức thanh toán/tín dụng. "
                               "Vui lòng liên hệ Admin để nạp thêm hoặc chọn nguồn AI khác.")
                        return
                    if not any_output and _is_rate_limit_error(e):
                        _logger.warning("Groq rate-limit sau khi đã retry (model=%s): %s", candidate_model, type(e).__name__)
                        yield ("⏳ Hệ thống AI (Groq) đang bị giới hạn tần suất truy cập. "
                               "Đã tự động thử lại nhiều lần nhưng chưa thành công — vui lòng thử lại sau ít phút.")
                        return
                    if any_output or not (_is_model_unavailable_error(e) or _is_timeout_error(e)):
                        _logger.exception("Lỗi Groq (model=%s)", candidate_model)
                        yield "⚠️ Hệ thống AI (Groq) hiện gặp sự cố. Vui lòng thử lại sau hoặc chọn nguồn AI khác."
                        return
            _logger.error("Groq: hết danh sách model dự phòng (%s). Lỗi cuối: %s", ", ".join(candidates), type(last_err).__name__ if last_err else "—")
            yield f"Lỗi Groq: không gọi được model nào trong danh sách dự phòng ({', '.join(candidates)}). Vui lòng thử lại sau."

        elif provider == "openai" and OPENAI_AVAILABLE:
            api_key = kwargs.get("api_key") or self.get_api_key_from_secrets("openai")
            if not api_key:
                yield "Lỗi OpenAI: chưa tìm thấy API key. Vui lòng nhập key hoặc cấu hình OPENAI_API_KEY."
                return
            candidates = ([model_name] if model_name else []) + [
                m for m in AI_MODEL_CATALOG["openai"] if m != model_name
            ]
            last_err = None
            for candidate_model in candidates:
                any_output = False
                try:
                    client = openai.OpenAI(api_key=api_key, timeout=LLM_TIMEOUT_SECONDS, max_retries=0)
                    stream = _call_with_rate_limit_retry(
                        client.chat.completions.create,
                        model=candidate_model,
                        messages=[
                            # Dùng tiếng Anh thuần ASCII cho system prompt, đồng bộ với nhánh Groq —
                            # tránh mọi rủi ro encoding tương tự dù OpenAI chưa ghi nhận lỗi này.
                            {"role": "system", "content": AI_SYSTEM_POLICY},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        # Đã xác nhận qua thực tế với Groq: 3000 token bị cắt ngang giữa chừng với
                        # báo cáo nhiều tuần chi tiết — nâng lên 8192 cho cả OpenAI để tránh lặp lại.
                        max_tokens=8192,
                        stream=True,
                        stream_options={"include_usage": True}
                    )
                    stream_usage = None
                    for chunk in stream:
                        # Chunk cuối mang usage (OpenAI: stream_options include_usage, choices rỗng;
                        # Groq: x_groq.usage) — không đọc choices[0] khi danh sách rỗng.
                        stream_usage = (getattr(chunk, "usage", None)
                                        or getattr(getattr(chunk, "x_groq", None), "usage", None) or stream_usage)
                        choices = getattr(chunk, "choices", None) or []
                        if choices and choices[0].delta.content is not None:
                            any_output = True
                            yield choices[0].delta.content
                    from dss.services import llm_usage
                    llm_usage.from_openai_compatible("openai", candidate_model, stream_usage)
                    return
                except Exception as e:
                    last_err = e
                    if _is_billing_required_error(e):
                        _logger.warning("OpenAI billing/quota het han muc (model=%s): %s", candidate_model, type(e).__name__)
                        yield ("💳 Hệ thống AI (OpenAI) hiện không thể dùng do tài khoản đã hết hạn mức thanh toán/tín dụng. "
                               "Vui lòng liên hệ Admin để nạp thêm hoặc chọn nguồn AI khác.")
                        return
                    if not any_output and _is_rate_limit_error(e):
                        _logger.warning("OpenAI rate-limit sau khi đã retry (model=%s): %s", candidate_model, type(e).__name__)
                        yield ("⏳ Hệ thống AI (OpenAI) đang bị giới hạn tần suất truy cập. "
                               "Đã tự động thử lại nhiều lần nhưng chưa thành công — vui lòng thử lại sau ít phút.")
                        return
                    if any_output or not (_is_model_unavailable_error(e) or _is_timeout_error(e)):
                        _logger.exception("Lỗi OpenAI (model=%s)", candidate_model)
                        yield "⚠️ Hệ thống AI (OpenAI) hiện gặp sự cố. Vui lòng thử lại sau hoặc chọn nguồn AI khác."
                        return
            _logger.error("OpenAI: hết danh sách model dự phòng (%s). Lỗi cuối: %s", ", ".join(candidates), type(last_err).__name__ if last_err else "—")
            yield f"Lỗi OpenAI: không gọi được model nào trong danh sách dự phòng ({', '.join(candidates)}). Vui lòng thử lại sau."

        elif provider == "ollama" and OLLAMA_AVAILABLE:
            # `or` (không chỉ .get mặc định) — 1 số nơi gọi truyền base_url=""
            # tường minh; khi đó dùng URL cấu hình trong .env (ollama_base_url()).
            base_url = (kwargs.get("base_url") or ollama_base_url()).rstrip("/")
            if not _check_ollama_running(base_url):
                yield (f"Lỗi Ollama: không kết nối được tới {base_url}. Hãy cài và mở Ollama "
                       "(https://ollama.com/download) hoặc đặt OLLAMA_BASE_URL trong .env.")
                return
            model_name = resolve_ollama_model(model_name, base_url)
            try:
                response = requests.post(
                    f"{base_url}/api/chat",
                    json={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": AI_SYSTEM_POLICY},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": True,
                        "keep_alive": "30m",  # giữ model trong RAM -> lần hỏi sau không phải nạp lại
                    },
                    headers=_ollama_headers(),
                    stream=True,
                    timeout=(5, 300),  # 5s kết nối; tối đa 300s chờ giữa 2 token (CPU chậm)
                )
                if response.status_code == 200:
                    for line in response.iter_lines():
                        if not line:
                            continue
                        json_resp = json.loads(line)
                        if json_resp.get("error"):
                            yield f"Lỗi Ollama: {str(json_resp['error'])[:200]}"
                            return
                        chunk = (json_resp.get("message") or {}).get("content") or json_resp.get("response")
                        if chunk:
                            yield chunk
                elif response.status_code == 404:
                    yield (f"Lỗi Ollama: chưa có model '{model_name}' trên máy. "
                           f"Chạy lệnh `ollama pull {model_name}` rồi thử lại.")
                elif response.status_code in (401, 403):
                    yield "Lỗi Ollama: OLLAMA_API_KEY không hợp lệ hoặc thiếu quyền."
                else:
                    yield f"Lỗi Ollama: HTTP {response.status_code}"
            except requests.exceptions.ConnectionError:
                yield (f"Lỗi Ollama: không kết nối được tới {base_url}. Hãy cài và mở Ollama "
                       "(https://ollama.com/download) hoặc đặt OLLAMA_BASE_URL trong .env.")
            except Exception as e:
                _logger.warning("Ollama provider failed: error_type=%s", type(e).__name__)
                yield "Lỗi Ollama: không thể hoàn tất yêu cầu."
        else:
            yield "Provider không khả dụng hoặc chưa được cấu hình đúng."
    
    def generate_personalized_advice(self, student_weaknesses, predicted_gpa, provider="huggingface",
                                     use_rag=True, embedding_model_name="sentence-transformers/all-MiniLM-L6-v2",
                                     use_warehouse_data=True, student_profile=None, runtime_documents=None,
                                     role="Sinh viên", prefetched_relevant_docs=None, **kwargs):
        """
        Tạo lời khuyên học tập cá nhân hóa sử dụng RAG và AI provider (Streaming).

        `use_warehouse_data`/`runtime_documents`: GIỮ trong chữ ký để không phá
        các nơi gọi hiện có (ai_advisor.py, llm_service.py truyền cả hai theo
        tên), nhưng KHÔNG còn dùng để chọn tài liệu trích dẫn — theo thiết kế
        NHÓM F, bối cảnh runtime (dataset/hồ sơ sinh viên) không được coi là
        nguồn trích dẫn (xem REPORT.md Mục 8.2 điểm 4). Trên thực tế
        `runtime_documents` do ai_advisor.py truyền vào LUÔN là `[]` (xem
        comment tại nơi gọi: "TUYỆT ĐỐI không chèn hồ sơ sinh viên vào vector
        documents/RAG"), nên không có hành vi nào bị mất khi bỏ dùng ở đây.

        NHÓM F remediation pass (đợt 2, đọc lập review 2026-09): trước đây hàm
        này tự gọi `self.find_relevant_documents_rag` — đường RAG CŨ đọc thẳng
        19 tài liệu viết cứng trong `_init_enhanced_knowledge_base`, hoàn toàn
        KHÔNG qua lọc quản trị (`document_governance.is_document_usable`) khi
        không chạy REAL_LMS mode. Đây chính là đường sinh ra NỘI DUNG THẬT của
        "Kế hoạch học tập" (nút chính, mọi provider) VÀ của "So sánh AI"
        (`_run_compare_ai` -> `llm_service.compare_providers` ->
        `_run_one_provider` -> hàm này) — rộng hơn nhiều so với closure
        `_find_docs_rag_safe` trong ai_advisor.py (closure đó chỉ phục vụ
        khung "Bằng chứng & Nguồn tham khảo"/xem trước, KHÔNG phải nguồn tài
        liệu thật sự được đưa vào prompt). Sửa: gọi `rag_service.retrieve_unified_context`
        — CÙNG một hàm mà `_find_docs_rag_safe` dùng — để nội dung kế hoạch
        thật sự sinh ra và khung "Bằng chứng & Nguồn tham khảo"/`verify_citations`
        luôn xét TRÊN CÙNG một tập tài liệu đã qua duyệt (trước đây có thể lệch
        nhau: plan trích tài liệu A, panel bằng chứng lại kiểm tra tài liệu B).

        H-2 (đọc lập review kiến trúc thương mại, đợt 3): dù đã hợp nhất về
        CÙNG MỘT HÀM truy xuất (`retrieve_unified_context`), gọi hàm đó HAI
        LẦN cho CÙNG một response (1 lần ở đây để build prompt, 1 lần nữa ở
        `ai_advisor.py` sau khi stream xong để build khung "Bằng chứng &
        Nguồn tham khảo"/`verify_citations`) vẫn có rủi ro lý thuyết trả về
        HAI TẬP TÀI LIỆU KHÁC NHAU nếu trạng thái duyệt/kho tri thức thay đổi
        giữa 2 lần gọi (vd. Admin duyệt/từ chối 1 tài liệu ngay trong lúc
        streaming). `prefetched_relevant_docs`: nếu nơi gọi ĐÃ tự truy xuất
        trước (khuyến khích — xem `ai_advisor.py`), truyền list đó vào đây để
        dùng LẠI Y NGUYÊN thay vì truy xuất lần nữa — đảm bảo prompt gửi LLM
        và tài liệu hiển thị/kiểm tra trích dẫn LUÔN là CÙNG MỘT TẬP object,
        không phải 2 lần gọi độc lập có thể lệch nhau. Nếu không truyền
        (vd. đường `_run_compare_ai`/`compare_providers`, chưa refactor để
        pre-fetch), hàm tự truy xuất như cũ.
        """
        relevant_docs = []
        rag_query = ""
        if prefetched_relevant_docs is not None:
            relevant_docs = prefetched_relevant_docs
        elif use_rag and student_weaknesses:
            rag_query = self._build_rag_query_from_weaknesses(student_weaknesses, student_profile=student_profile)
            hf_token = kwargs.get("hf_token", self.get_api_key_from_secrets("huggingface"))
            from dss.services import rag_service as _rag_service
            _unified = _rag_service.retrieve_unified_context(
                self, rag_query, role=role, namespace=_rag_service.NAMESPACE_STUDENT_LEARNING,
                top_k=5, embedding_model_name=embedding_model_name, hf_token=hf_token,
            )
            relevant_docs = _unified.get("chunks", [])

        prompt, weaknesses_str, relevant_docs_str, advice_meta = self._prepare_personalized_advice_prompt(
            student_weaknesses, predicted_gpa, relevant_docs, student_profile=student_profile
        )
        
        response_stream = self.call_ai_provider(prompt, provider=provider, **kwargs)
        
        has_error = False
        first_chunk = True
        generated_chunks = []
        
        err_markers = ("Lỗi", "Provider không khả dụng")
        for chunk in response_stream:
            if first_chunk and chunk and str(chunk).startswith(err_markers):
                has_error = True
                fallback_chunk = f"**[CHẾ ĐỘ GIẢ LẬP AI - DO {provider.upper()} API CHƯA ĐƯỢC CẤU HÌNH HOẶC LỖI]**\n\n*{chunk}*\n\n"
                generated_chunks.append(fallback_chunk)
                yield fallback_chunk
                break
            first_chunk = False
            generated_chunks.append(str(chunk))
            yield chunk

        # Một số provider (đặc biệt Gemini) có thể dừng stream giữa chừng mà KHÔNG ném lỗi
        # và KHÔNG có tín hiệu rõ ràng nào bắt được ở tầng call_ai_provider (vd. bị chặn an
        # toàn nhưng candidate vẫn báo finish_reason STOP, hoặc kết nối bị ngắt êm) — khiến
        # báo cáo trông như "đã xong" trong khi thực ra thiếu hẳn phần thân (kế hoạch tuần,
        # KPI...). Dò bằng heuristic: nội dung quá ngắn so với yêu cầu (báo cáo nhiều tuần)
        # hoặc không kết thúc bằng dấu câu hoàn chỉnh — nếu nghi ngờ, báo rõ cho người dùng
        # thay vì để họ tưởng nhầm là bản đầy đủ.
        if not has_error:
            full_text = "".join(generated_chunks).strip()
            looks_truncated = full_text and (
                len(full_text) < 800
                or not full_text.endswith((".", "!", "?", '"', "”", ")", "*", ":", "-"))
            )
            if looks_truncated:
                warning_chunk = (
                    "\n\n⚠️ *Nội dung phía trên có vẻ ngắn hoặc dừng giữa chừng so với yêu "
                    "cầu (một kế hoạch nhiều tuần đầy đủ) — nhiều khả năng AI đã bị dừng sớm "
                    "(giới hạn phía nhà cung cấp, mạng chập chờn...). Hãy thử tạo lại hoặc "
                    "đổi sang provider khác nếu thấy nội dung thiếu.*"
                )
                generated_chunks.append(warning_chunk)
                yield warning_chunk

        if has_error:
            yield "Chào bạn, tôi là trợ lý ảo hỗ trợ học tập. Vì kết nối tới mô hình AI hiện đang gặp gián đoạn, tôi gửi bạn một số phân tích nhanh dựa trên hệ thống RAG:\n\n"
            yield f"**1. Tóm tắt tình trạng:**\n"
            yield f"- GPA dự đoán hiện tại của bạn: **{predicted_gpa:.2f}**\n"
            yield f"- Bạn cần cải thiện các môn sau:\n{weaknesses_str}\n\n"
            yield f"**2. Tài liệu học tập được RAG đề xuất:**\n{relevant_docs_str}\n\n"
            yield "**3. Lời khuyên chung:**\n- Dành thêm thời gian ôn tập lại kiến thức nền tảng.\n- Tham khảo tài liệu gợi ý bên trên."
            generated_chunks.extend([
                "Chào bạn, tôi là trợ lý ảo hỗ trợ học tập. Vì kết nối tới mô hình AI hiện đang gặp gián đoạn, tôi gửi bạn một số phân tích nhanh dựa trên hệ thống RAG:\n\n",
                f"**1. Tóm tắt tình trạng:**\n- GPA dự đoán hiện tại của bạn: **{predicted_gpa:.2f}**\n- Bạn cần cải thiện các môn sau:\n{weaknesses_str}\n\n",
                f"**2. Tài liệu học tập được RAG đề xuất:**\n{relevant_docs_str}\n\n",
                "**3. Lời khuyên chung:**\n- Dành thêm thời gian ôn tập lại kiến thức nền tảng.\n- Tham khảo tài liệu gợi ý bên trên."
            ])

        if self.data_warehouse is not None:
            try:
                self.data_warehouse.save_ai_consultation(
                    {
                        "student_id": (student_profile or {}).get("student_id", "unknown"),
                        "predicted_gpa": float(predicted_gpa),
                        "weaknesses": student_weaknesses or [],
                        "provider": provider,
                        "model_name": kwargs.get("model_name", ""),
                        "embedding_model": embedding_model_name,
                        "rag_query": rag_query,
                        "top_documents": [doc.get("title", "") for doc in relevant_docs[:5]],
                        "generated_plan": "".join(generated_chunks),
                        "metadata": advice_meta,
                        "created_at": datetime.now().isoformat(),
                    }
                )
            except Exception:
                pass
        return

    def find_relevant_documents(self, query, top_k=3, embedding_model_name="sentence-transformers/all-MiniLM-L6-v2", hf_token=None):
        """Wrapper cho find_relevant_documents_rag."""
        return self.find_relevant_documents_rag(
            query_text=query,
            top_k=top_k,
            embedding_model_name=embedding_model_name,
            hf_token=hf_token,
            use_warehouse_data=True # Default to True for advanced RAG
        )
