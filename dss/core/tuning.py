"""Dò tham số (GridSearchCV) nhanh mà không đánh đổi độ chính xác.

Đo thực tế trên 20.000 sinh viên (8 nhân CPU, Random Forest):
- Lưới đầy đủ (24 tổ hợp phân loại / 12 hồi quy) và lưới gọn (8 / 4) chọn ra
  CÙNG bộ tham số tốt nhất, cùng điểm test — nhưng lưới gọn nhanh hơn ~2.5 lần.
- CV=3 cho cùng điểm với CV=5 khi dữ liệu lớn (mỗi fold vẫn > 5.000 mẫu), nhanh
  hơn thêm ~30%.
- Huấn luyện lại với tham số đã biết: ~1 giây thay vì ~1 phút.
- KHÔNG dùng: max_samples<1, dò trên mẫu con, Halving — F1-macro giảm rõ.

Vì vậy:
- Dữ liệu nhỏ (< LARGE_DATA_ROWS dòng train): lưới đầy đủ + số fold người dùng chọn
  (ở đây lưới quyết định độ chính xác nhiều hơn, và chạy vẫn nhanh).
- Dữ liệu lớn: lưới gọn + tối đa LARGE_DATA_CV_FOLDS fold.
- Ghi nhớ tham số tốt nhất theo (mô hình, cấu hình pipeline, lưới, scoring, số
  fold, DẤU VÂN TAY dữ liệu train) — dữ liệu đổi dù 1 ô là dò lại.
"""
from __future__ import annotations

import hashlib
import os
from collections import OrderedDict

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.model_selection import GridSearchCV

from dss.core.logging_config import get_logger

_logger = get_logger(__name__)

LARGE_DATA_ROWS = int(os.environ.get("DSS_LARGE_DATA_ROWS", "10000") or 10000)
LARGE_DATA_CV_FOLDS = 3
_CACHE_MAX = 128
_BEST_PARAMS_CACHE: "OrderedDict[str, dict]" = OrderedDict()


def is_large(n_train: int) -> bool:
    return int(n_train) >= LARGE_DATA_ROWS


def effective_cv_folds(n_train: int, requested: int) -> int:
    """Số fold thật sự dùng: giữ nguyên lựa chọn người dùng với dữ liệu nhỏ,
    tối đa LARGE_DATA_CV_FOLDS với dữ liệu lớn."""
    requested = int(requested)
    return min(requested, LARGE_DATA_CV_FOLDS) if is_large(n_train) else requested


def select_grid(full: dict, compact: dict, n_train: int) -> dict:
    return compact if is_large(n_train) else full


def _fingerprint(X, y) -> str:
    h = hashlib.sha1()
    X_df = X if isinstance(X, pd.DataFrame) else pd.DataFrame(np.asarray(X))
    h.update(str(list(X_df.columns)).encode())
    h.update(pd.util.hash_pandas_object(X_df, index=False).values.tobytes())
    h.update(pd.util.hash_pandas_object(pd.Series(np.asarray(y).ravel()).astype(str), index=False).values.tobytes())
    return h.hexdigest()


def _cv_signature(cv) -> str:
    if hasattr(cv, "get_n_splits"):
        return f"{type(cv).__name__}:{cv.get_n_splits()}:{getattr(cv, 'random_state', None)}"
    # Danh sách split tĩnh (dữ liệu rất mất cân bằng) — mã hoá theo nội dung.
    return "static:" + hashlib.sha1(repr([(list(a), list(b)) for a, b in cv]).encode()).hexdigest()


def _pipeline_signature(pipeline, param_grid) -> str:
    """Cấu hình pipeline (tiền xử lý, cân bằng lớp, chọn đặc trưng, tham số cố định
    của mô hình) — bỏ các tham số đang dò và n_jobs (không ảnh hưởng kết quả)."""
    items = []
    for k, v in sorted(pipeline.get_params(deep=True).items()):
        if k in param_grid or k.endswith("n_jobs") or k in ("memory", "verbose", "steps"):
            continue
        items.append((k, type(v).__name__ if hasattr(v, "get_params") else repr(v)))
    return repr(items)


def _cache_key(name, pipeline, param_grid, scoring, cv, X, y) -> str:
    parts = [name, _pipeline_signature(pipeline, param_grid), repr(sorted(param_grid.items())),
             str(scoring), _cv_signature(cv), _fingerprint(X, y)]
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def clear_cache() -> None:
    _BEST_PARAMS_CACHE.clear()


def tuned_fit(name, pipeline, param_grid, X, y, cv, scoring, sign=1.0):
    """GridSearchCV có ghi nhớ. Trả (pipeline_đã_fit, cv_mean, cv_std, best_params).

    `sign=-1` cho scoring dạng neg_* (vd. neg_mean_absolute_error) để cv_mean là
    số dương dễ đọc — giống cách trainer đang báo cáo."""
    # clone: pipeline của trainer dùng CHUNG đối tượng mô hình giữa các lần train —
    # không được sửa tham số trên đối tượng dùng chung đó.
    pipeline = clone(pipeline)
    key = _cache_key(name, pipeline, param_grid, scoring, cv, X, y)
    # Bản fit cuối (refit / dùng lại tham số) chạy ở tiến trình chính — bật đa nhân
    # cho mô hình hỗ trợ n_jobs (Random Forest mặc định chỉ dùng 1 nhân). Trong
    # các worker của GridSearchCV, joblib tự giới hạn song song lồng nhau.
    if "model__n_jobs" in pipeline.get_params():
        pipeline.set_params(model__n_jobs=-1)
    hit = _BEST_PARAMS_CACHE.get(key)
    if hit is not None:
        _BEST_PARAMS_CACHE.move_to_end(key)
        pipeline.set_params(**hit["best_params"])
        pipeline.fit(X, y)
        _logger.info("%s: dùng lại tham số tốt nhất đã dò (bỏ qua GridSearchCV): %s", name, hit["best_params"])
        return pipeline, hit["cv_mean"], hit["cv_std"], dict(hit["best_params"])

    gs = GridSearchCV(pipeline, param_grid, cv=cv, scoring=scoring, n_jobs=-1, verbose=0, refit=True)
    gs.fit(X, y)
    cv_mean = float(sign * gs.cv_results_["mean_test_score"][gs.best_index_])
    cv_std = float(gs.cv_results_["std_test_score"][gs.best_index_])
    _BEST_PARAMS_CACHE[key] = {"best_params": dict(gs.best_params_), "cv_mean": cv_mean, "cv_std": cv_std}
    while len(_BEST_PARAMS_CACHE) > _CACHE_MAX:
        _BEST_PARAMS_CACHE.popitem(last=False)
    _logger.info("%s: Best params (%s, %d tổ hợp): %s", name, scoring, len(gs.cv_results_["params"]), gs.best_params_)
    return gs.best_estimator_, cv_mean, cv_std, dict(gs.best_params_)
