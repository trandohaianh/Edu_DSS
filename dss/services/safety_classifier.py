"""Bộ phân loại an toàn học được (lớp thứ hai sau bộ lọc từ khoá).

Vì sao cần: bộ lọc từ khoá bắt đúng cụm đã liệt kê, nhưng trên tập giữ riêng chỉ bắt 12,5% lời
khuyên có hại và 50% câu chèn lệnh. Mô hình ở đây là TF-IDF n-gram ký tự (bền với biến thể chính tả,
thiếu dấu, từ ghép) + Logistic Regression, huấn luyện trên ``dss/resources/safety_train_v1.json``.
Tập này sinh theo mẫu, chứa cả câu CẤM ĐOÁN ("không được chép bài") để mô hình học ngữ cảnh phủ định,
và được kiểm tra không trùng câu nào với tập đánh giá.

- Chạy offline, không cần GPU hay mạng; huấn luyện < 1 giây, lần đầu dùng thì cache trong tiến trình.
- Ngưỡng chọn bằng cross-validation TRÊN TẬP TRAIN: ngưỡng thấp nhất giữ tỉ lệ báo nhầm ≤ 5%.
- Đây vẫn là mô hình nhỏ học từ dữ liệu tự viết. Khách hàng cần độ phủ cao hơn có thể bật thêm lớp
  LLM-judge (``EDUDSS_SAFETY_LLM_JUDGE=1``) hoặc thay bằng mô hình đa ngôn ngữ đã tinh chỉnh.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

TRAIN_PATH = Path(__file__).resolve().parents[1] / "resources" / "safety_train_v1.json"
MAX_FALSE_POSITIVE_RATE = 0.05
_lock = threading.Lock()
_models: dict[str, _Model] = {}


@dataclass
class _Model:
    pipeline: object
    threshold: float
    positive: str

    def score(self, text: str) -> float:
        proba = self.pipeline.predict_proba([text])[0]
        return float(proba[list(self.pipeline.classes_).index(self.positive)])


def _build(task: str) -> _Model:
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import FeatureUnion, make_pipeline

    data = json.loads(TRAIN_PATH.read_text(encoding="utf-8"))[task]
    positive = "harmful" if task == "advice" else "attack"
    texts = [c["text"] for c in data]
    labels = np.array([c["label"] for c in data])

    def make():
        features = FeatureUnion(
            [
                (
                    "char",
                    TfidfVectorizer(
                        analyzer="char_wb", ngram_range=(2, 5), lowercase=True, sublinear_tf=True, min_df=1
                    ),
                ),
                (
                    "word",
                    TfidfVectorizer(
                        analyzer="word",
                        ngram_range=(1, 2),
                        lowercase=True,
                        sublinear_tf=True,
                        token_pattern=r"(?u)\b\w+\b",
                    ),
                ),
            ]
        )
        return make_pipeline(features, LogisticRegression(C=8.0, max_iter=2000, class_weight="balanced"))

    pipe = make()
    oof = cross_val_predict(
        make(), texts, labels, cv=StratifiedKFold(5, shuffle=True, random_state=0), method="predict_proba"
    )
    pipe.fit(texts, labels)
    p_pos = oof[:, list(pipe.classes_).index(positive)]
    neg_scores = np.sort(p_pos[labels != positive])
    # ngưỡng = phân vị (1 - FPR tối đa) của điểm mẫu âm, không thấp hơn 0,5 để tránh báo nhầm dày đặc
    q = neg_scores[min(len(neg_scores) - 1, int(np.ceil((1 - MAX_FALSE_POSITIVE_RATE) * len(neg_scores))))]
    return _Model(pipe, float(max(0.5, q + 1e-6)), positive)


def _model(task: str) -> _Model:
    with _lock:
        if task not in _models:
            _models[task] = _build(task)
        return _models[task]


def harmful_advice_score(text: str) -> tuple[bool, float]:
    """(có hại?, xác suất) cho một lời khuyên do AI sinh ra."""
    if not text or not text.strip():
        return False, 0.0
    m = _model("advice")
    s = m.score(text)
    return s >= m.threshold, s


def injection_score(text: str) -> tuple[bool, float]:
    """(có dấu hiệu chèn lệnh?, xác suất) cho văn bản không tin cậy (tài liệu RAG, tin nhắn)."""
    if not text or not text.strip():
        return False, 0.0
    m = _model("injection")
    s = m.score(text)
    return s >= m.threshold, s


def thresholds() -> dict:
    return {task: round(_model(task).threshold, 4) for task in ("advice", "injection")}
