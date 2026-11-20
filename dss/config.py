"""Imports, flags, plotly patches, exceptions."""
from __future__ import annotations

# --- PHẦN 1: IMPORT CÁC THƯ VIỆN CẦN THIẾT ---
# Phần này import tất cả các thư viện cần thiết cho ứng dụng.
# - Các thư viện chuẩn Python: hashlib, json, math, os, warnings, datetime, io
# - Các thư viện dữ liệu/ML: numpy, pandas, scikit-learn, joblib
# - Streamlit: giao diện web tương tác
import json  # đọc/ghi cấu trúc JSON (metadata, lịch sử)
import math  # các hàm toán học cơ bản (sqrt, floor, ...)
import os  # thao tác file system (tạo folder, path join)
import warnings  # để bật/tắt cảnh báo khi cần
from datetime import datetime  # thời gian hiện tại, lưu metadata
from io import BytesIO  # dùng để xây buffer khi tải file (Excel)
from pathlib import Path

# --- Nạp app/.env (ĐIỂM DUY NHẤT trong toàn bộ codebase gọi load_dotenv) ---
# Đây là module cấu hình trung tâm, được import trước tiên bởi mọi service đọc
# API key (llm_gateway.py, core/models.py) — nạp ở đây đảm bảo os.getenv()/
# os.environ.get() ở các nơi đó luôn thấy được giá trị từ .env, mà không cần
# rải load_dotenv() ra nhiều file.
#
# CHỈ định đường dẫn TƯỜNG MINH tới app/.env (Path(__file__).parent.parent —
# config.py nằm ở app/dss/config.py nên parent.parent = app/) — KHÔNG dùng
# load_dotenv() không tham số, vì nó sẽ dò tìm .env theo thư mục làm việc hiện
# tại (cwd) và có thể vô tình nạp nhầm D:\KLTN\code\.env (chỉ có OPENAI_API_KEY,
# thiếu GEMINI_API_KEY/GROQ_API_KEY) tuỳ vào nơi lệnh `streamlit run` được gọi.
#
# override=False (mặc định của load_dotenv) đảm bảo đúng thứ tự ưu tiên: biến
# môi trường THẬT đã được OS/hệ thống triển khai export từ trước KHÔNG bao giờ
# bị .env ghi đè — .env chỉ điền vào chỗ còn trống, đúng cho môi trường dev cục bộ.
try:
    from dotenv import load_dotenv as _load_dotenv

    _ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
    if _ENV_PATH.exists():
        _load_dotenv(dotenv_path=_ENV_PATH, override=False)
except ImportError:
    pass  # python-dotenv chưa cài — biến môi trường thật (OS/deployment) vẫn hoạt động bình thường

try:
    import joblib  # lưu/restore các pipeline/mô hình scikit-learn
    JOBLIB_AVAILABLE = True
except Exception:
    joblib = None
    JOBLIB_AVAILABLE = False
    # joblib không có sẵn trong môi trường hiện tại; nhiều tính năng lưu/load mô hình sẽ không hoạt động
import numpy as np  # xử lý số học mảng, random, toán học
import pandas as pd  # DataFrame manipulation, đọc/ghi CSV/Excel
import streamlit as st  # framework UI cho ứng dụng

# Giảm log cảnh báo nhiễu gây lag khi rerun nhiều lần.
warnings.filterwarnings(
    "ignore",
    message="X does not have valid feature names, but LGBMRegressor was fitted with feature names",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    message="invalid value encountered in divide",
    category=RuntimeWarning,
)
try:
    from scipy.stats import ConstantInputWarning as _ScipyConstantInputWarning

    warnings.filterwarnings("ignore", category=_ScipyConstantInputWarning)
except Exception:
    pass


# Visualize libraries
import plotly.express as px
import matplotlib.pyplot as plt

# Chuẩn hóa hiển thị giá trị trên biểu đồ để dễ đọc nhanh.
_px_bar_original = px.bar
_px_line_original = px.line


def _px_bar_with_labels(*args, **kwargs):
    kwargs.setdefault("text_auto", True)
    fig = _px_bar_original(*args, **kwargs)
    try:
        fig.update_traces(
            selector=dict(type="bar"),
            textposition="outside",
            cliponaxis=False,
        )
    except Exception:
        pass
    return fig


def _px_line_with_labels(*args, **kwargs):
    fig = _px_line_original(*args, **kwargs)
    try:
        max_points_for_labels = 20
        for trace in fig.data:
            y_vals = getattr(trace, "y", None)
            if y_vals is not None and len(y_vals) <= max_points_for_labels:
                trace.mode = "lines+markers+text"
                trace.text = [f"{float(v):.4f}" for v in y_vals]
                trace.textposition = "top center"
    except Exception:
        pass
    return fig


px.bar = _px_bar_with_labels
px.line = _px_line_with_labels

# ML libraries
from sklearn.preprocessing import StandardScaler, MinMaxScaler, LabelEncoder, OneHotEncoder, RobustScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    RandomForestClassifier,
    RandomForestRegressor,
    StackingRegressor,
)
from sklearn.linear_model import LogisticRegression, LinearRegression, Ridge, Lasso
from sklearn.svm import SVC, SVR
from sklearn.model_selection import train_test_split, GridSearchCV, cross_val_score, StratifiedKFold, KFold
from sklearn.metrics import (
    confusion_matrix,
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    mean_squared_error,
    mean_absolute_error,
    r2_score,
    )
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.impute import SimpleImputer, KNNImputer
from sklearn.pipeline import Pipeline, Pipeline as SklearnPipeline
from sklearn.feature_selection import SelectKBest, mutual_info_classif, RFE

# Imbalanced-Learn for SMOTE
try:
    from imblearn.pipeline import Pipeline as ImbPipeline
    from imblearn.over_sampling import SMOTE, BorderlineSMOTE, ADASYN
    IMB_LEARN_AVAILABLE = True
except ImportError:
    ImbPipeline = None
    SMOTE = BorderlineSMOTE = ADASYN = None
    IMB_LEARN_AVAILABLE = False
    
from scipy.spatial.distance import cosine

# SHAP for Model Explainability (optional — tránh crash khi chưa cài)
try:
    import shap  # type: ignore
except ImportError:
    shap = None
try:
    from streamlit_shap import st_shap
except ImportError:
    st_shap = None

# Optional third-party dependencies ------------------------------------------------
# Một số thư viện là tùy chọn (không bắt buộc) nhưng bổ sung tính năng:
# - xgboost, lightgbm: mô hình gradient boosting nhanh/hiệu quả
# - shap: giải thích mô hình tree-based
# - sentence-transformers / transformers / torch: embedding và LLM local
# - openai: gọi API OpenAI nếu cần (chat/completion)
# - xlsxwriter, openpyxl: ghi Excel nâng cao
try:
    import xgboost as xgb  # XGBoost (nếu cài)
    XGBOOST_AVAILABLE = True
except ImportError:
    xgb = None
    XGBOOST_AVAILABLE = False

try:
    import lightgbm as lgb  # LightGBM (nếu cài)
    LIGHTGBM_AVAILABLE = True
except ImportError:
    lgb = None
    LIGHTGBM_AVAILABLE = False

SHAP_AVAILABLE = shap is not None


def _safe_n_splits(n_samples, desired_folds=5, min_folds=2):
    """Trả về số folds an toàn, tránh n_splits > n_samples."""
    n_samples = int(n_samples)
    desired_folds = int(desired_folds)
    if n_samples < min_folds:
        raise ValueError(
            f"Không đủ dữ liệu để cross-validation: cần >= {min_folds} mẫu, hiện có {n_samples}."
        )
    return max(min_folds, min(desired_folds, n_samples))


def _make_safe_cv_strategy(y, desired_folds=5, is_classification=False, random_state=42):
    """
    Tạo chiến lược CV an toàn theo dữ liệu thực tế.
    - Classification: ưu tiên StratifiedKFold; tự fallback sang KFold nếu class quá hiếm.
    - Regression: dùng KFold với n_splits <= số mẫu.
    """
    n_samples = len(y)
    n_splits = _safe_n_splits(n_samples, desired_folds=desired_folds, min_folds=2)
    if is_classification:
        class_counts = pd.Series(y).value_counts(dropna=False)
        min_class_samples = int(class_counts.min()) if not class_counts.empty else 0
        if min_class_samples >= 2:
            n_splits = max(2, min(n_splits, min_class_samples))
            return StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
        return KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    return KFold(n_splits=n_splits, shuffle=True, random_state=random_state)


def _normalize_labels_for_metrics(y_true, y_pred):
    """
    Chuẩn hóa nhãn cho các metric phân loại để tránh lỗi
    `Mix of label input types (string and number)`.
    """
    y_true_arr = np.asarray(list(y_true), dtype=object)
    y_pred_arr = np.asarray(list(y_pred), dtype=object)
    y_true_safe = np.array([str(v) for v in y_true_arr], dtype=str)
    y_pred_safe = np.array([str(v) for v in y_pred_arr], dtype=str)
    labels = np.unique(np.concatenate([y_true_safe, y_pred_safe]))
    return y_true_safe, y_pred_safe, labels


def _ensure_label_mapping(labels_obj):
    """Chuẩn hóa nhãn về dict {mã nội bộ (int) -> tên nhãn gốc} để tra bằng `.get(code, ...)`.

    `labels_obj` (session_state.hub_labels) thường là mảng class_labels do trainer trả về,
    trong đó VỊ TRÍ (index) mới là mã nội bộ mà pipeline.predict() dùng — không phải giá trị
    phần tử. Vì vậy phải enumerate() để lấy đúng cặp (mã số -> tên gốc), không được lấy chính
    giá trị làm khóa (sẽ không bao giờ khớp với mã số nguyên do predict() trả về).
    """
    if isinstance(labels_obj, dict):
        return labels_obj
    if labels_obj is None:
        return {}
    if isinstance(labels_obj, np.ndarray):
        return {i: str(v) for i, v in enumerate(labels_obj.tolist())}
    if isinstance(labels_obj, (list, tuple, set, pd.Index)):
        return {i: str(v) for i, v in enumerate(labels_obj)}
    return {}


def _render_low_performance_guidance_cls(model_name, accuracy, train_accuracy):
    """Hiển thị gợi ý xử lý khi mô hình phân loại quá kém."""
    st.error(
        f"❌ `{model_name}` có hiệu năng quá thấp (Test Accuracy: {accuracy:.2%}, "
        f"Train Accuracy: {train_accuracy:.2%}). Tạm loại khỏi danh sách mô hình dùng tiếp."
    )
    st.markdown(
        """
**Gợi ý sửa nhanh để cải thiện:**
- Kiểm tra lại cột `target` (không bị sai kiểu, không lẫn mã định danh).
- Gộp/bỏ các lớp quá hiếm (class chỉ vài mẫu) hoặc thu thêm dữ liệu cho lớp đó.
- Bật cân bằng lớp (`SMOTE/BorderlineSMOTE`) khi dữ liệu lệch lớp mạnh.
- Tăng chất lượng feature: bỏ cột nhiễu, thêm feature liên quan nghiệp vụ.
- Với dữ liệu nhỏ, ưu tiên model đơn giản (`Logistic Regression`, `Random Forest`) trước.
"""
    )


def _explain_best_params(best_params):
    """Sinh mô tả ngắn cho các tham số tối ưu để hiển thị khi train."""
    if not best_params:
        return []
    explanations = []
    for full_key, value in best_params.items():
        param_name = str(full_key).split("__")[-1]
        if param_name == "n_estimators":
            explanations.append(
                f"- `{full_key} = {value}`: số cây của mô hình; tăng số cây thường ổn định hơn nhưng sẽ chạy chậm hơn."
            )
        elif param_name == "max_depth":
            explanations.append(
                f"- `{full_key} = {value}`: độ sâu tối đa của cây; sâu hơn học chi tiết hơn nhưng có thể tăng overfitting."
            )
        elif param_name == "min_samples_split":
            explanations.append(
                f"- `{full_key} = {value}`: số mẫu tối thiểu để tách node; giá trị lớn hơn giúp mô hình bớt chia quá nhỏ."
            )
        elif param_name == "min_samples_leaf":
            explanations.append(
                f"- `{full_key} = {value}`: số mẫu tối thiểu tại node lá; tăng giá trị này giúp dự đoán mượt và ít nhiễu hơn."
            )
        elif param_name == "learning_rate":
            explanations.append(
                f"- `{full_key} = {value}`: tốc độ học mỗi vòng boosting; nhỏ hơn thường ổn định hơn nhưng cần nhiều vòng hơn."
            )
        elif param_name == "C":
            explanations.append(
                f"- `{full_key} = {value}`: mức regularization của Logistic Regression. "
                "Regularization là cơ chế 'phạt' mô hình quá phức tạp để giảm overfitting. "
                "Trong Logistic Regression, `C` là nghịch đảo của độ phạt: `C` nhỏ -> phạt mạnh hơn (mô hình đơn giản hơn), "
                "`C` lớn -> phạt yếu hơn (mô hình linh hoạt hơn)."
            )
        elif param_name == "solver":
            explanations.append(
                f"- `{full_key} = {value}`: thuật toán tối ưu dùng để fit Logistic Regression."
            )
        else:
            explanations.append(
                f"- `{full_key} = {value}`: tham số tối ưu được chọn tự động bởi GridSearchCV."
            )
    return explanations

try:
    from huggingface_hub import login as hf_login
    HUGGINGFACE_HUB_AVAILABLE = True
except ImportError:
    hf_login = None
    HUGGINGFACE_HUB_AVAILABLE = False

# torch / transformers / sentence-transformers rất nặng để import (nhiều giây, có máy tới
# hàng chục giây) nhưng chỉ thực sự cần khi người dùng dùng model Hugging Face cục bộ
# (embedding RAG hoặc sinh văn bản local) — đa số người dùng chỉ gọi API ngoài (Gemini/Groq/
# OpenAI) nên không cần trả giá này lúc khởi động app. Import thật được hoãn tới lần đầu
# tiên _ensure_local_llm_libs() được gọi (xem các hàm load_local_llm/load_embedding_model/
# call_ai_provider), thay vì chạy ngay khi nạp file — giúp app hiện giao diện nhanh hơn nhiều
# cho các use-case không đụng tới Hugging Face local.
import importlib.util as _importlib_util

SentenceTransformer = None
SENTENCE_TRANSFORMERS_AVAILABLE = _importlib_util.find_spec("sentence_transformers") is not None

torch = None
TORCH_AVAILABLE = _importlib_util.find_spec("torch") is not None

AutoTokenizer = AutoModelForCausalLM = AutoModel = None
HF_AVAILABLE = _importlib_util.find_spec("transformers") is not None

_local_llm_libs_loaded = False

# PERF-001 — instrumentation dev/test-only: bật bằng biến môi trường
# EDUDSS_PERF_DEBUG=1, KHÔNG hiển thị trong UI, chỉ ghi ra stderr của tiến
# trình server (log dev) để đo thời gian thật của từng giai đoạn khởi động
# nặng (import torch/transformers, khởi tạo SentenceTransformer, v.v.).
import os as _os
import time as _time

PERF_DEBUG = _os.environ.get("EDUDSS_PERF_DEBUG") == "1"


def perf_mark(label: str, t_start: float | None = None) -> float:
    """Ghi 1 mốc thời gian (dev/test only). Trả về time.time() hiện tại để
    gọi tiếp cho mốc kế tiếp. Không làm gì (chi phí ~0) khi PERF_DEBUG=False."""
    now = _time.time()
    if PERF_DEBUG:
        elapsed = f" (+{now - t_start:.2f}s)" if t_start is not None else ""
        print(f"[PERF] {now:.3f} {label}{elapsed}", flush=True)
    return now


def _ensure_local_llm_libs():
    """Import thật torch/transformers/sentence-transformers (chỉ chạy 1 lần, kết quả được
    cache lại) và cập nhật lại chính xác các cờ *_AVAILABLE (find_spec ở trên chỉ biết là có
    cài đặt hay không, không biết import có thực sự thành công hay không — vd. xung đột phiên
    bản huggingface-hub vẫn có thể khiến import transformers lỗi dù đã cài)."""
    global torch, SentenceTransformer, AutoTokenizer, AutoModelForCausalLM, AutoModel
    global TORCH_AVAILABLE, HF_AVAILABLE, SENTENCE_TRANSFORMERS_AVAILABLE, _local_llm_libs_loaded
    if _local_llm_libs_loaded:
        return
    _local_llm_libs_loaded = True
    _t0 = perf_mark("_ensure_local_llm_libs: start (first call this process)")
    try:
        import torch as _torch
        torch = _torch
        TORCH_AVAILABLE = True
    except (ImportError, OSError):
        TORCH_AVAILABLE = False
    _t1 = perf_mark("_ensure_local_llm_libs: torch imported", _t0)
    try:
        from transformers import AutoTokenizer as _AT, AutoModelForCausalLM as _AMCL, AutoModel as _AM
        AutoTokenizer, AutoModelForCausalLM, AutoModel = _AT, _AMCL, _AM
        HF_AVAILABLE = True
    except (ImportError, OSError):
        HF_AVAILABLE = False
    _t2 = perf_mark("_ensure_local_llm_libs: transformers imported", _t1)
    try:
        from sentence_transformers import SentenceTransformer as _ST
        SentenceTransformer = _ST
        SENTENCE_TRANSFORMERS_AVAILABLE = True
    except (ImportError, OSError):
        # OSError: vd. WinError 4551 — Windows Application Control chặn torch\lib\*.dll
        SENTENCE_TRANSFORMERS_AVAILABLE = False
    perf_mark("_ensure_local_llm_libs: sentence_transformers imported (done)", _t2)
    perf_mark("_ensure_local_llm_libs: TOTAL", _t0)

try:
    import openai  # type: ignore  # API OpenAI (nếu dùng)
    OPENAI_AVAILABLE = True
except ImportError:
    openai = None
    OPENAI_AVAILABLE = False

# AI Providers: Gemini, Groq, Ollama
try:
    import google.genai as genai  # type: ignore  # Google Gemini API (SDK mới — google.generativeai đã bị Google khai tử)
    GEMINI_AVAILABLE = True
except ImportError:
    genai = None
    GEMINI_AVAILABLE = False

try:
    from groq import Groq  # type: ignore  # Groq API
    GROQ_AVAILABLE = True
except ImportError:
    Groq = None
    GROQ_AVAILABLE = False

try:
    import requests  # type: ignore  # For Ollama API calls
    OLLAMA_AVAILABLE = True
except ImportError:
    requests = None
    OLLAMA_AVAILABLE = False

try:
    import xlsxwriter  # type: ignore  # optional excel writer
    XLSXWRITER_AVAILABLE = True
except ImportError:
    XLSXWRITER_AVAILABLE = False

try:
    import openpyxl  # type: ignore  # optional excel reader/writer
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

# For custom exceptions
# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================
class ConfigError(Exception):
    """
    Exception tùy chỉnh cho các lỗi cấu hình.
    Được sử dụng khi có vấn đề với cấu hình hệ thống hoặc tham số không hợp lệ.
    """
    pass


def setup_page() -> None:
    """Streamlit page config — call once from main."""
    import streamlit as st

    st.set_page_config(
        page_title="EduDSS",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="auto",
    )


# --- Theme (C1.3 design system) ------------------------------------------------
# Toàn bộ màu nằm trong dss/styles/main.css dưới dạng token CSS. Python chỉ phát
# 1 marker (`.dss-theme-<mode>`) để main.css chọn bộ token tương ứng qua
# `:root:has(...)` — không còn khối CSS tối song song trong Python.
THEME_MODES = ("light", "dark", "system")
THEME_LABELS = {"light": "Sáng", "dark": "Tối", "system": "Hệ thống"}
DEFAULT_THEME = "system"

# Plotly vẽ bằng SVG với màu cụ thể (không đọc được biến CSS) — đây là nơi DUY
# NHẤT giữ bản sao màu token cho biểu đồ. "system" dùng màu trung tính đọc được
# trên cả nền sáng lẫn nền tối vì phía server không biết giao diện của hệ điều hành.
CHART_TOKENS = {
    "light": {"text": "#5F6368", "title": "#202124", "grid": "#E3E5E8", "line": "#C4C8CD"},
    "dark": {"text": "#CBD5E1", "title": "#F8FAFC", "grid": "#273449", "line": "#3B4A63"},
    "system": {"text": "#8A94A6", "title": "#8A94A6", "grid": "rgba(138,148,166,0.25)", "line": "rgba(138,148,166,0.45)"},
}


def current_theme() -> str:
    import streamlit as st

    mode = st.session_state.get("dss_theme", DEFAULT_THEME)
    if mode == "auto":  # giá trị cũ trước C1.3
        mode = "system"
    return mode if mode in THEME_MODES else DEFAULT_THEME


def inject_styles() -> None:
    """Nạp main.css + marker chế độ giao diện đang chọn (sáng / tối / theo hệ thống)."""
    import streamlit as st
    from pathlib import Path

    css_path = Path(__file__).resolve().parent / "styles" / "main.css"
    if css_path.is_file():
        css = css_path.read_text(encoding="utf-8")
        st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)

    mode = current_theme()
    st.markdown(
        f"<div class='dss-marker dss-theme-{mode}' data-theme='{mode}'></div>",
        unsafe_allow_html=True,
    )


CHART_FONT_FAMILY = "Be Vietnam Pro, Segoe UI, Arial, sans-serif"


def style_figure(fig):
    """Áp token giao diện hiện tại lên 1 figure Plotly: nền trong suốt (nền thẻ
    chứa nó quyết định màu), chữ/lưới theo token — biểu đồ không còn là ô trắng
    trên trang tối."""
    tokens = CHART_TOKENS[current_theme()]
    try:
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            # Cùng phông với toàn app (Be Vietnam Pro — .streamlit/config.toml).
            font=dict(family=CHART_FONT_FAMILY, size=13, color=tokens["text"]),
            legend=dict(font=dict(color=tokens["text"]), bgcolor="rgba(0,0,0,0)"),
            hoverlabel=dict(font=dict(family=CHART_FONT_FAMILY)),
        )
        if getattr(fig.layout.title, "text", None):
            fig.update_layout(title_font=dict(color=tokens["title"], size=16))
        fig.update_xaxes(gridcolor=tokens["grid"], linecolor=tokens["line"], zerolinecolor=tokens["line"],
                         tickfont=dict(color=tokens["text"]), title_font=dict(color=tokens["text"]))
        fig.update_yaxes(gridcolor=tokens["grid"], linecolor=tokens["line"], zerolinecolor=tokens["line"],
                         tickfont=dict(color=tokens["text"]), title_font=dict(color=tokens["text"]))
    except Exception:
        pass
    return fig


def _install_themed_plotly_chart() -> None:
    """Bọc st.plotly_chart 1 lần duy nhất: mọi biểu đồ trong app đi qua
    style_figure() — không phải sửa từng nơi gọi."""
    import streamlit as st

    if getattr(st.plotly_chart, "_dss_themed", False):
        return
    _original = st.plotly_chart

    def _themed_plotly_chart(figure_or_data, *args, **kwargs):
        if hasattr(figure_or_data, "update_layout"):
            style_figure(figure_or_data)
        return _original(figure_or_data, *args, **kwargs)

    _themed_plotly_chart._dss_themed = True
    st.plotly_chart = _themed_plotly_chart


# --- Display text filter (C1.3 portfolio polish) ----------------------------
# Decorative emoji at the START of user-facing text (alerts, captions, button /
# expander / tab labels, Markdown headings) made professional screens look like
# a demo. Instead of editing ~170 call sites (some option labels are also used
# in program logic), the filter removes ONLY a leading run of emoji/pictographs
# at display time. Option VALUES of selectbox/radio/multiselect are never
# touched, so widget values and logic are unchanged.
import re as _re

_LEADING_DECOR_RE = _re.compile(
    r"^(\s*(?:\*\*|#{1,6}\s+)?)"
    r"(?:\s*(?:[0-9#*]\uFE0F?\u20E3|[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2190-\u21FF\u2300-\u23FF]"
    r"[\uFE0F\u200D\U0001F3FB-\U0001F3FF]*))+\s*"
)


def strip_leading_decoration(text):
    """Remove a leading run of decorative emoji (keeps Markdown bold/heading markers)."""
    if not isinstance(text, str):
        return text
    return _LEADING_DECOR_RE.sub(lambda m: m.group(1), text, count=1)


_TEXT_FIRST_ARG = ("success", "info", "warning", "error", "caption", "subheader", "header", "title", "toast",
                   "button", "download_button", "form_submit_button", "checkbox", "toggle", "expander",
                   "popover", "metric", "markdown")


def _wrap_first_text_arg(fn, name):
    if getattr(fn, "_dss_decor_filtered", False):
        return fn

    def wrapper(*args, **kwargs):
        if args:
            first = args[0]
            if name == "markdown" and isinstance(first, str) and first.lstrip().startswith("<"):
                return fn(*args, **kwargs)
            args = (strip_leading_decoration(first),) + tuple(args[1:])
        elif "label" in kwargs:
            kwargs["label"] = strip_leading_decoration(kwargs["label"])
        elif "body" in kwargs:
            kwargs["body"] = strip_leading_decoration(kwargs["body"])
        return fn(*args, **kwargs)

    wrapper._dss_decor_filtered = True
    wrapper.__name__ = getattr(fn, "__name__", name)
    wrapper.__doc__ = getattr(fn, "__doc__", None)
    return wrapper


def _wrap_tabs(fn):
    if getattr(fn, "_dss_decor_filtered", False):
        return fn

    def wrapper(tabs, *args, **kwargs):
        return fn([strip_leading_decoration(t) for t in tabs], *args, **kwargs)

    wrapper._dss_decor_filtered = True
    return wrapper


def install_display_text_filter() -> None:
    """Idempotent: wraps module-level `st.*` calls and DeltaGenerator methods
    (columns/containers/sidebar) once per process."""
    import streamlit as st
    from streamlit.delta_generator import DeltaGenerator

    for name in _TEXT_FIRST_ARG:
        if hasattr(DeltaGenerator, name):
            setattr(DeltaGenerator, name, _wrap_first_text_arg(getattr(DeltaGenerator, name), name))
        if hasattr(st, name):
            setattr(st, name, _wrap_first_text_arg(getattr(st, name), name))
    if hasattr(DeltaGenerator, "tabs"):
        DeltaGenerator.tabs = _wrap_tabs(DeltaGenerator.tabs)
    if hasattr(st, "tabs"):
        st.tabs = _wrap_tabs(st.tabs)


def apply_plotly_patches() -> None:
    """Apply bar/line label helpers to plotly express."""
    import plotly.express as px

    _install_themed_plotly_chart()

    # main.py gọi hàm này ở MỖI lượt rerun — không bọc lại lần nữa (trước đây
    # chuỗi wrapper px.bar/px.line dài thêm 1 tầng sau mỗi lượt rerun).
    if getattr(px.bar, "_dss_labelled", False):
        return

    _px_bar_original = px.bar
    _px_line_original = px.line

    def _px_bar_with_labels(*args, **kwargs):
        kwargs.setdefault("text_auto", True)
        fig = _px_bar_original(*args, **kwargs)
        try:
            fig.update_traces(
                selector=dict(type="bar"),
                textposition="outside",
                cliponaxis=False,
            )
        except Exception:
            pass
        return fig

    def _px_line_with_labels(*args, **kwargs):
        fig = _px_line_original(*args, **kwargs)
        try:
            max_points_for_labels = 20
            for trace in fig.data:
                y_vals = getattr(trace, "y", None)
                if y_vals is not None and len(y_vals) <= max_points_for_labels:
                    trace.mode = "lines+markers+text"
                    trace.text = [f"{float(v):.4f}" for v in y_vals]
                    trace.textposition = "top center"
        except Exception:
            pass
        return fig

    _px_bar_with_labels._dss_labelled = True
    px.bar = _px_bar_with_labels
    px.line = _px_line_with_labels


# --- RAG (Retrieval-Augmented Generation) — Phase 6 refactor ---
# Lấy từ đo thực nghiệm (không phải đoán tay): với model embedding đang dùng
# (all-MiniLM-L6-v2), câu truy vấn HOÀN TOÀN không liên quan (thời tiết, ẩm
# thực...) vẫn đạt cosine similarity ~0.52-0.57 với tài liệu bất kỳ trong kho —
# trong khi câu truy vấn ĐÚNG chủ đề ("machine learning") có thể chỉ đạt 0.43
# với đúng tài liệu liên quan. Hai khoảng này CHỒNG LẤN nhau — không tồn tại 1
# ngưỡng tuyệt đối nào tách sạch "liên quan" khỏi "nhiễu" cho model này. Vì vậy
# dùng lọc TƯƠNG ĐỐI theo điểm cao nhất của CHÍNH truy vấn đó (RAG_RELATIVE_
# THRESHOLD), không so với 1 số cố định — xem `MultiAIProvider.find_relevant_
# documents_rag` (dss/core/models.py) để biết cách áp dụng.
RAG_TOP_K_DEFAULT = 5
# Giữ lại tài liệu có điểm >= 85% điểm của tài liệu đứng đầu trong CÙNG 1 lượt
# truy vấn — luôn giữ tài liệu đứng đầu (không bao giờ trả về rỗng).
RAG_RELATIVE_THRESHOLD = 0.85
# Nếu tài liệu đứng đầu cũng dưới mức này (dựa trên ngưỡng nhiễu đo được ở
# trên), toàn bộ kết quả được đánh dấu low_confidence=True — vẫn trả về (không
# giấu), để nơi gọi (vd. prompt LLM) tự quyết định có nên trích dẫn "chắc chắn"
# hay chỉ nêu như tham khảo mở rộng.
RAG_LOW_CONFIDENCE_FLOOR = 0.55

# --- Multi-LLM "So sánh AI" (Compare AI) — Phase 10 refactor, mục 11 bản yêu cầu ---
# CHỈ dùng khi người dùng chủ động bấm nút "So sánh AI" (dss/services/llm_service.py)
# — KHÔNG BAO GIỜ được gọi mặc định ở luồng tạo kế hoạch học tập thông thường (vẫn
# luôn chỉ gọi 1 provider như trước). Giới hạn số request cloud API chạy đồng thời
# để tránh 1 lượt so sánh tự bắn quá nhiều request cùng lúc gây rate-limit dây
# chuyền (xem Phase 7 — _call_with_rate_limit_retry) hoặc quá tải máy khi có
# Hugging Face local trong danh sách so sánh.
MAX_CONCURRENT_REQUESTS = 3

# --- Cấu hình LMS-Scale RAG & Ingestion (~20.000 sinh viên) ---
DEFAULT_CHUNK_SIZE = 400
DEFAULT_CHUNK_OVERLAP = 80
RAG_STRICT_NO_EVIDENCE = True
