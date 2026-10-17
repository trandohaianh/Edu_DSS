"""Thí nghiệm phân định: SMOTE so với class_weight khi lớp thiểu số rất ít mẫu.

Lý do có tệp này: mã trước đây mặc định dùng SMOTE để cân bằng lớp mà chưa bao giờ
đo xem nó có hơn class_weight hay không. Với lớp thiểu số chỉ còn vài mẫu, SMOTE
nội suy giữa các mẫu thật nên mọi điểm sinh ra nằm trên bao lồi của một nhúm điểm —
ở cỡ 2 mẫu thì đúng một đoạn thẳng. Nó làm mô hình tự tin hơn mà không thêm thông tin.

Thiết kế: CÙNG fold, CÙNG seed, chỉ đổi cách cân bằng. Quét cỡ lớp thiểu số để tìm
ngưỡng mà kết luận đổi chiều, thay vì chỉ đo ở một cỡ rồi suy rộng.

Chỉ số chính là PR-AUC (average precision) của lớp thiểu số: nó lấy trung bình trên
toàn dải ngưỡng nên không nhảy theo từng mẫu như F1 tại một ngưỡng cố định.

Chạy:  python3 -I tools/exp_balance_compare.py
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline as SkPipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

CSV = "dữ liệu/sample_student_data_1000.csv"
TARGET = "pass_fail"
# Đặc trưng dự báo hợp lệ: KHÔNG lấy final_score / exam_score / A1..A3 / GPA / grade
# vì chúng suy ra trực tiếp từ mục tiêu.
FEATURES = [
    "prior_gpa", "attendance", "assignment_rate", "practice_score",
    "study_hours_per_day", "lms_time_spent", "lms_clicks",
    "sleep_hours", "mental_health_rating", "social_media_hours",
]
MINORITY_SIZES = [2, 5, 10, 25, 50, 100, 160]
SEEDS = [0, 1, 2, 3, 4]
N_SPLITS = 5


def build(arm: str, k_neighbors: int, seed: int):
    """Ba nhánh so sánh, khác nhau ĐÚNG ở cách cân bằng lớp."""
    rf = RandomForestClassifier(n_estimators=80, random_state=seed)
    if arm == "class_weight":
        rf = RandomForestClassifier(n_estimators=80, random_state=seed, class_weight="balanced")
        return SkPipeline([("sc", StandardScaler()), ("clf", rf)])
    if arm == "smote":
        # cùng quy tắc k_neighbors như trong dss/core/trainers.py
        return ImbPipeline([
            ("sc", StandardScaler()),
            ("smote", SMOTE(random_state=42, k_neighbors=k_neighbors)),
            ("clf", rf),
        ])
    return SkPipeline([("sc", StandardScaler()), ("clf", rf)])


def run_one(X, y, arm: str, seed: int):
    """Trả về (PR-AUC lớp thiểu số, macro-F1) trung bình trên các fold."""
    cv = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=seed)
    ap, f1 = [], []
    for tr, te in cv.split(X, y):
        n_min_train = int(pd.Series(y[tr]).value_counts().min())
        k = max(1, min(5, n_min_train - 1))
        if arm == "smote" and n_min_train < 2:
            return None, None  # SMOTE không chạy nổi ở cỡ này — đúng điều cần ghi nhận
        model = build(arm, k, seed)
        model.fit(X[tr], y[tr])
        proba = model.predict_proba(X[te])[:, 1]
        ap.append(average_precision_score(y[te], proba))
        f1.append(f1_score(y[te], model.predict(X[te]), average="macro"))
    return float(np.mean(ap)), float(np.mean(f1))


def main() -> None:
    df = pd.read_csv(CSV).dropna(subset=FEATURES + [TARGET])
    maj = df[df[TARGET] == 1]
    min_all = df[df[TARGET] == 0]
    print(f"Dữ liệu gốc: {len(maj)} lớp đa số · {len(min_all)} lớp thiểu số")
    print(f"Đặc trưng ({len(FEATURES)}): {', '.join(FEATURES)}\n")

    header = f"{'n thiểu số':>11} | {'không cân bằng':>15} | {'SMOTE':>15} | {'class_weight':>15} | thắng"
    print(header); print("-" * len(header))

    rows = []
    for n_min in MINORITY_SIZES:
        res = {}
        for arm in ("none", "smote", "class_weight"):
            scores = []
            for seed in SEEDS:
                sub = pd.concat([maj, min_all.sample(n=n_min, random_state=seed)])
                X = sub[FEATURES].to_numpy(float)
                y = sub[TARGET].to_numpy(int)
                ap, _ = run_one(X, y, arm, seed)
                if ap is not None:
                    scores.append(ap)
            res[arm] = (float(np.mean(scores)), float(np.std(scores))) if scores else None

        def fmt(v):
            return "không chạy được" if v is None else f"{v[0]:.4f} ±{v[1]:.3f}"

        usable = {k: v for k, v in res.items() if v is not None and k != "none"}
        win = max(usable, key=lambda k: usable[k][0]) if usable else "—"
        gap = ""
        if len(usable) == 2:
            a, b = usable["smote"][0], usable["class_weight"][0]
            gap = f"  (chênh {abs(a-b):+.4f})"
        print(f"{n_min:>11} | {fmt(res['none']):>15} | {fmt(res['smote']):>15} | "
              f"{fmt(res['class_weight']):>15} | {win}{gap}")
        rows.append((n_min, res, win))

    print("\nChỉ số: PR-AUC (average precision) của lớp thiểu số, trung bình "
          f"{N_SPLITS} fold × {len(SEEDS)} seed. ± là độ lệch chuẩn giữa các seed.")

    wins_cw = [n for n, _, w in rows if w == "class_weight"]
    wins_sm = [n for n, _, w in rows if w == "smote"]
    print(f"\nclass_weight thắng ở cỡ: {wins_cw or 'không có'}")
    print(f"SMOTE        thắng ở cỡ: {wins_sm or 'không có'}")


if __name__ == "__main__":
    main()
