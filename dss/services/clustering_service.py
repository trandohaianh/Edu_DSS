"""Clustering service — hoàn tất Phase 2 của kế hoạch refactor EduDSS.

Tách toàn bộ tính toán THUẦN (không gọi `st.*`) ra khỏi `dss/tabs/clustering.py`:
tiền xử lý, Elbow/Silhouette, K-Means fit/predict, PCA, thống kê điểm mạnh/yếu
theo cụm, kế hoạch can thiệp, gợi ý bạn học tương tự (cosine similarity), và
gợi ý cụm tham chiếu. `clustering.py` giờ chỉ còn UI/orchestration (widget,
biểu đồ, session_state) và gọi xuống đây — Y HỆT thuật toán cũ, không đổi
tham số/kết quả (random_state=42, n_init=10, ngưỡng ±10%... giữ nguyên).
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import KNNImputer
from sklearn.metrics import davies_bouldin_score, silhouette_score
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.pipeline import Pipeline as SklearnPipeline
from sklearn.preprocessing import StandardScaler

from dss.core.data_helpers import feature_label

# C-1: bộ từ khóa dùng để chọn cột mặc định cho phân cụm — bản cũ chỉ có tiếng
# Anh (score/gpa/hours/point/mark/grade) nên trên dữ liệu mẫu tiếng Việt
# (diem_giua_ky, ty_le_diem_danh, so_gio_hoc_tuan, ...) hầu như không khớp gì.
_CLUSTER_FEATURE_KEYWORDS = [
    "score",
    "gpa",
    "hours",
    "point",
    "mark",
    "grade",
    "diem",
    "ty_le",
    "so_gio",
]


def select_default_cluster_features(
    df: pd.DataFrame, max_fallback_features: int = 5, corr_threshold: float = 0.98
) -> list[str]:
    """C-1: chọn cột mặc định cho phân cụm — DÙNG CHUNG cho `clustering.py` (UI)
    và `bootstrap_service._bootstrap_default_clustering` (phân cụm ngầm sau đăng
    nhập), tránh 2 nơi tự lặp lại cùng 1 logic rồi lệch nhau.

    Loại TRIỆT ĐỂ:
    - Cột ID/PCA/cluster (như trước).
    - Bí danh/target của CẢ 2 target mặc định (diem_ky_sau, xep_loai) — bản cũ
      không loại nên `final_score` (bí danh của diem_ky_sau) lọt thẳng vào phân
      cụm mặc định trên dữ liệu mẫu.
    - Cột gần như trùng lặp (|r| > corr_threshold) với 1 cột ĐÃ chọn trước đó
      (vd. gpa_previous = diem_ky_nay / 2.5, tương quan ~0.9999).
    """
    from dss.core.target_utils import get_leaky_target_columns, is_identifier_column

    all_numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    # Loại cột định danh theo TỪ trong tên (is_identifier_column), không theo chuỗi con "id":
    # bản cũ loại nhầm video_views, midterm_score, valid_attempts.
    all_numeric_cols = [
        c
        for c in all_numeric_cols
        if not is_identifier_column(c) and "pca" not in c.lower() and "cluster" not in c.lower()
    ]

    forbidden = {"final_score", "grade", "diem_ky_sau", "xep_loai"}
    for default_target in ("diem_ky_sau", "xep_loai"):
        forbidden.update(str(c).lower() for c in get_leaky_target_columns(default_target))
    safe_cols = [c for c in all_numeric_cols if c.lower() not in forbidden]

    candidate_cols = [c for c in safe_cols if any(k in c.lower() for k in _CLUSTER_FEATURE_KEYWORDS)]
    if not candidate_cols:
        candidate_cols = safe_cols[:max_fallback_features]

    selected: list[str] = []
    for col in candidate_cols:
        is_near_duplicate = False
        for chosen in selected:
            try:
                corr = df[col].corr(df[chosen])
            except Exception:
                corr = 0.0
            if pd.notna(corr) and abs(corr) > corr_threshold:
                is_near_duplicate = True
                break
        if not is_near_duplicate:
            selected.append(col)
    return selected


def preprocess_features(df: pd.DataFrame, selected_cols: list[str]):
    """Điền giá trị thiếu (KNNImputer) + chuẩn hóa (StandardScaler) — Y HỆT
    pipeline cũ trong `clustering_hybrid_tab` (Bước 1). Trả về (preprocessor đã
    fit, X_processed) — preprocessor giữ lại để dùng nhất quán về sau nếu cần."""
    df_cluster = df[selected_cols].copy()
    preprocessor = SklearnPipeline(
        steps=[
            ('imputer', KNNImputer(n_neighbors=3)),
            ('scaler', StandardScaler()),
        ]
    )
    X_processed = preprocessor.fit_transform(df_cluster)
    return preprocessor, X_processed


def _silhouette_score_bounded(X_processed, labels):
    """Use a reproducible estimate above 2,000 rows; exact score for small classes."""
    return silhouette_score(
        X_processed,
        labels,
        metric="euclidean",
        sample_size=2000 if len(X_processed) > 2000 else None,
        random_state=42,
    )


# Silhouette tốt nhất dưới ngưỡng này: dữ liệu không có cấu trúc nhóm rõ ràng (quy ước
# Kaufman & Rousseeuw: < 0.25 là "không có cấu trúc đáng kể").
WEAK_STRUCTURE_SILHOUETTE = 0.25
WEAK_STRUCTURE_WARNING = (
    "Cảnh báo: không có cấu trúc nhóm rõ ràng (Silhouette tốt nhất {sil:.3f} < 0.25). "
    "Các cụm chỉ là cách cắt tuỳ ý một phân bố liên tục — không nên diễn giải như các nhóm "
    "sinh viên tách biệt."
)


def weak_structure_warning(best_silhouette) -> Optional[str]:
    """Chuỗi cảnh báo khi Silhouette tốt nhất < 0.25, ngược lại None."""
    try:
        sil = float(best_silhouette)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(sil) or sil >= WEAK_STRUCTURE_SILHOUETTE:
        return None
    return WEAK_STRUCTURE_WARNING.format(sil=sil)


def _knee_k(k_list, inertia) -> Optional[int]:
    """Điểm khuỷu (Kneedle): chuẩn hoá K và Inertia về [0, 1], chọn K xa dây cung nối điểm
    đầu–cuối nhất. Bản cũ lấy K có độ giảm Inertia TUYỆT ĐỐI lớn nhất — với đường Inertia lồi
    giảm dần thì đó gần như luôn là k_start+1, bất kể dữ liệu. None khi < 3 điểm hoặc đường
    không cong (không có khuỷu)."""
    if len(k_list) < 3:
        return None
    x = np.asarray(k_list, dtype=float)
    y = np.asarray(inertia, dtype=float)
    if not np.all(np.isfinite(y)) or y[0] == y[-1]:
        return None
    x_n = (x - x[0]) / (x[-1] - x[0])
    y_n = (y - y[-1]) / (y[0] - y[-1])
    # Đường lồi giảm: khoảng cách tới dây cung y = 1 - x là (1 - x_n) - y_n.
    dist = (1.0 - x_n) - y_n
    idx = int(np.argmax(dist[1:-1])) + 1
    if dist[idx] <= 1e-9:
        return None
    return int(k_list[idx])


def compute_elbow_silhouette(X_processed, k_start: int, k_end: int, progress_callback=None) -> dict:
    """Quét K từ k_start đến k_end, tính Inertia + Silhouette cho mỗi K, và đề
    xuất K tốt nhất — Y HỆT logic cũ (Bước 2). `progress_callback(fraction)`
    (0..1) tuỳ chọn, chỉ để UI cập nhật thanh tiến trình, không ảnh hưởng kết
    quả tính toán.

    Trả về dict: k_list, inertia, silhouette, suggested_k_elbow,
    suggested_k_sil, recommended_k, reason.
    """
    inertia = []
    sil_scores = []
    k_range = range(k_start, k_end + 1)
    n_samples = len(X_processed)

    for idx, k in enumerate(k_range):
        kmeans_temp = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans_temp.fit_predict(X_processed)
        inertia.append(float(kmeans_temp.inertia_))

        sil_val = float("nan")
        if 1 < k < n_samples:
            try:
                n_lab = len(set(labels))
                if n_lab >= 2 and n_lab < n_samples:
                    sil_val = float(_silhouette_score_bounded(X_processed, labels))
            except Exception:
                sil_val = float("nan")
        sil_scores.append(sil_val)

        if progress_callback is not None:
            progress_callback((idx + 1) / len(k_range))

    k_list = list(k_range)
    suggested_k_elbow = _knee_k(k_list, inertia)

    sil_arr = np.array(sil_scores, dtype=float)
    valid_sil = np.isfinite(sil_arr)
    suggested_k_sil = None
    if valid_sil.any():
        suggested_k_sil = int(k_list[int(np.nanargmax(sil_arr))])

    recommended_k = suggested_k_sil
    reason = ""
    if recommended_k is not None:
        best_sil = float(np.nanmax(sil_arr))
        reason = (
            f"K = {recommended_k} có Silhouette cao nhất trong khoảng đã thử "
            f"({best_sil:.3f}) — thường dễ chọn hơn chỉ nhìn Elbow."
        )
        if suggested_k_elbow is not None and suggested_k_elbow != recommended_k:
            reason += f" Tham khảo Elbow (điểm khuỷu của đường Inertia): K = {suggested_k_elbow}."
    elif suggested_k_elbow is not None:
        recommended_k = suggested_k_elbow
        reason = f"Không tính được Silhouette ổn định; dùng gợi ý Elbow: K = {recommended_k}."
    else:
        reason = "Chưa đủ dữ liệu để tự đề xuất K; vui lòng tăng số mẫu hoặc đổi khoảng K."

    warning = weak_structure_warning(np.nanmax(sil_arr)) if valid_sil.any() else None
    if warning:
        reason = f"{warning} {reason}".strip()

    return {
        "k_list": k_list,
        "inertia": inertia,
        "silhouette": sil_scores,
        "suggested_k_elbow": suggested_k_elbow,
        "suggested_k_sil": suggested_k_sil,
        "recommended_k": recommended_k,
        "reason": reason,
        "weak_structure": warning is not None,
        "warning": warning,
    }


def run_kmeans(X_processed, k: int):
    """K-Means fit/predict — Y HỆT tham số cũ (random_state=42, n_init=10).
    Trả về (model đã fit, mảng nhãn cụm)."""
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    clusters = kmeans.fit_predict(X_processed)
    return kmeans, clusters


def compute_cluster_quality_metrics(X_processed, labels) -> dict:
    """Silhouette (càng cao/gần 1 càng tốt) + Davies-Bouldin (càng thấp/gần 0
    càng tốt) cho đúng kết quả phân cụm HIỆN TẠI (K đã chạy) — bổ sung thêm
    Davies-Bouldin bên cạnh Silhouette đã có, vì 2 chỉ số bù nhau: Silhouette
    đánh giá theo từng điểm dữ liệu, Davies-Bouldin đánh giá theo khoảng cách
    giữa tâm các cụm — dùng cùng lúc cho kết luận "cụm tách rõ" đáng tin hơn.
    Trả về {'silhouette': float|None, 'davies_bouldin': float|None}."""
    n_labels = len(set(labels))
    n_samples = len(X_processed)
    if n_labels < 2 or n_labels >= n_samples:
        return {"silhouette": None, "davies_bouldin": None}
    try:
        sil = float(_silhouette_score_bounded(X_processed, labels))
    except Exception:
        sil = None
    try:
        db = float(davies_bouldin_score(X_processed, labels))
    except Exception:
        db = None
    return {
        "silhouette": sil,
        "davies_bouldin": db,
        "silhouette_sample_size": min(n_samples, 2000) if sil is not None else 0,
        "weak_structure": weak_structure_warning(sil) is not None,
        "warning": weak_structure_warning(sil),
    }


def compute_pca(X_processed):
    """PCA giảm chiều còn tối đa 2 thành phần (hoặc 1 nếu không đủ mẫu/đặc
    trưng) — Y HỆT logic cũ (Bước 4, Phần 1). Trả về dict: n_components, X_pca,
    variance_explained, total_variance (%). Trả về None nếu không đủ dữ liệu."""
    n_samples, n_features = X_processed.shape
    n_components = int(min(2, n_features, n_samples))
    if n_components < 1:
        return None
    pca = PCA(n_components=n_components)
    X_pca = pca.fit_transform(X_processed)
    variance_explained = pca.explained_variance_ratio_
    total_variance = float(np.sum(variance_explained) * 100)
    return {
        "n_components": n_components,
        "X_pca": X_pca,
        "variance_explained": variance_explained,
        "total_variance": total_variance,
    }


def compute_cluster_means(df_results: pd.DataFrame, selected_cols: list[str]) -> pd.DataFrame:
    """Bảng trung bình từng feature theo cụm + số lượng SV mỗi cụm — Y HỆT logic
    cũ (Bước 4, Phần 2 'chân dung cụm')."""
    cluster_mean_df = df_results.groupby('cluster')[selected_cols].mean().round(2)
    cluster_counts = df_results['cluster'].value_counts().sort_index()
    cluster_mean_df.insert(0, 'Số lượng SV', cluster_counts)
    return cluster_mean_df


def compute_strengths_weaknesses(
    group_avg: pd.Series,
    overall_avg: pd.Series,
    *,
    overall_std: Optional[pd.Series] = None,
    z_strong: float = 0.5,
    z_weak: float = -0.5,
    upper_ratio: float = 1.1,
    lower_ratio: float = 0.9,
):
    """Điểm mạnh/yếu của 1 cụm so với toàn khoá cho từng đặc trưng.

    C-3 (POST_72H_MASTER_PRODUCTION_CLOSURE): khi `overall_std` được truyền
    vào (độ lệch chuẩn CỦA TỪNG CỘT tính trên TOÀN BỘ sinh viên, không phải
    trên các trung bình cụm), dùng z-score = (group_avg − overall_avg) /
    overall_std thay cho tỷ lệ cố định ±10% — z-score xét ĐỘ PHÂN TÁN thật
    của từng đặc trưng, nên một cột dao động mạnh (vd. giờ tự học 2-35)
    không còn bị gắn "mạnh"/"yếu" dễ dàng như một cột ít dao động (vd. tỷ lệ
    điểm danh 0.6-1.0) chỉ vì cùng vượt ngưỡng ±10% tương đối.

    Ngưỡng z > +0.5 / z < −0.5 ("nửa độ lệch chuẩn") là quy ước thống kê phổ
    biến cho "khác biệt tương đối đáng chú ý trong 1 nhóm nhỏ" — không phải
    một phép kiểm định ý nghĩa thống kê chặt chẽ (cỡ mẫu 1 cụm thường nhỏ),
    và KHÔNG ngụ ý quan hệ nhân quả (đặc trưng này không "gây ra" cụm này).

    Khi `overall_std` không được cung cấp (tương thích ngược với lời gọi cũ
    chưa cập nhật), fallback về logic ratio ±10% cũ, giữ nguyên hành vi lịch
    sử — không phá vỡ caller nào chưa được cập nhật."""
    if overall_std is not None:
        safe_std = overall_std.replace(0, np.nan)
        z_scores = ((group_avg - overall_avg) / safe_std).fillna(0.0)
        strengths = z_scores[z_scores > z_strong].index.tolist()
        weaknesses = z_scores[z_scores < z_weak].index.tolist()
        if not strengths and not weaknesses and len(z_scores) > 0:
            z_sorted = z_scores.sort_values(ascending=False)
            top_col, bot_col = z_sorted.index[0], z_sorted.index[-1]
            if z_sorted.iloc[0] >= 0:
                strengths = [top_col]
            if z_sorted.iloc[-1] <= 0 or (len(z_sorted) > 1 and not weaknesses):
                weaknesses = [bot_col]
        return strengths, weaknesses

    # --- Fallback ratio-based cũ (KHÔNG có overall_std truyền vào) ---
    strengths = group_avg[group_avg > overall_avg * upper_ratio].index.tolist()
    weaknesses = group_avg[group_avg < overall_avg * lower_ratio].index.tolist()

    # Nếu không có đặc trưng nào vượt ngưỡng tuyệt đối ±10%, tìm thế mạnh tương đối và trọng tâm bứt phá
    if not strengths and not weaknesses and len(group_avg) > 0:
        diff_rel = (group_avg - overall_avg) / overall_avg.replace(0, np.nan)
        diff_sorted = diff_rel.sort_values(ascending=False)
        top_col = diff_sorted.index[0]
        bot_col = diff_sorted.index[-1]
        if diff_sorted.iloc[0] >= 0:
            strengths = [top_col]
        if diff_sorted.iloc[-1] <= 0 or (len(diff_sorted) > 1 and not weaknesses):
            weaknesses = [bot_col]
    return strengths, weaknesses


def compute_diff_pct(group_avg: pd.Series, overall_avg: pd.Series) -> pd.Series:
    """% chênh lệch so với trung bình chung, tránh chia cho 0 — Y HỆT logic cũ."""
    diff_pct = (group_avg - overall_avg) / overall_avg.replace(0, np.nan) * 100
    return diff_pct.fillna(0).round(1)


# Phân loại "họ" đặc trưng theo mẫu tên cột — quyết định KIỂU hành động gợi ý
# (ôn tập chủ đề / tăng giờ tự học / cải thiện điểm danh / rà soát theo môn cụ
# thể...), để 2 cột khác nhau không bao giờ nhận đúng 1 câu văn như trước đây.
_FEATURE_FAMILY_PATTERNS = [
    (("ty_le_diem_danh", "attendance"), "attendance"),
    (("so_gio_hoc", "study_hours"), "study_time"),
    (("gpa_previous", "gpa"), "gpa"),
    (("diem_ky_sau", "final_score", "diem_tong"), "final_score"),
]


def _feature_family(feat: str) -> str:
    feat_lower = feat.lower()
    for patterns, family in _FEATURE_FAMILY_PATTERNS:
        if any(p in feat_lower for p in patterns):
            return family
    return "topic_score"  # điểm theo môn/chủ đề cụ thể hoặc đặc trưng khác


def _build_intervention_text(feat: str, feat_lbl: str, gap_pct: float, priority: str) -> str:
    """Sinh HÀNH ĐỘNG GỢI Ý gắn với ĐÚNG đặc trưng (feat_lbl) và mức chênh lệch
    thật (gap_pct) — không dùng chung 1 câu cho mọi feature. Luôn nêu rõ: vấn
    đề (tên đặc trưng + % chênh lệch), hành động cụ thể, và mốc thời gian."""
    family = _feature_family(feat)
    gap_abs = abs(gap_pct)

    if priority == "Cao":
        timeframe = "trong tuần này"
        if family == "attendance":
            action = f"Đặt mục tiêu tham dự tối thiểu 90% số buổi học {timeframe} — hiện {feat_lbl.lower()} đang thấp hơn nhóm {gap_abs:.0f}%."
        elif family == "study_time":
            action = f"Tăng thêm 2–3 giờ tự học {timeframe}, ưu tiên các môn có điểm dưới trung bình ({feat_lbl.lower()} đang thấp hơn nhóm {gap_abs:.0f}%)."
        elif family == "gpa":
            action = f"So sánh các môn có mức giảm lớn nhất so với kỳ trước và ưu tiên ôn lại môn giảm nhiều nhất ({feat_lbl} thấp hơn nhóm {gap_abs:.0f}%)."
        elif family == "final_score":
            action = f"Ưu tiên ôn lại các chủ đề có điểm dưới trung bình và hoàn thành thêm 2 bài luyện tập bổ sung {timeframe} ({feat_lbl} thấp hơn nhóm {gap_abs:.0f}%)."
        else:
            action = f"Dành thời gian ôn tập riêng cho {feat_lbl} {timeframe} và làm thêm bài luyện tập — hiện thấp hơn nhóm {gap_abs:.0f}%, mức chênh lệch đáng chú ý nhất trong các chỉ số đang theo dõi."
    elif priority == "Trung bình":
        timeframe = "trong 1–2 tuần tới"
        if family == "attendance":
            action = f"Theo dõi và cải thiện dần {feat_lbl.lower()} {timeframe}, tránh vắng thêm buổi nào — hiện thấp hơn nhóm {gap_abs:.0f}%."
        elif family == "study_time":
            action = f"Tăng nhẹ thời lượng tự học {timeframe} cho các chủ đề còn yếu ({feat_lbl.lower()} thấp hơn nhóm {gap_abs:.0f}%)."
        elif family == "gpa":
            action = f"Rà soát lại các môn có điểm giảm so với kỳ trước, ôn tập bổ sung {timeframe}."
        elif family == "final_score":
            action = f"Làm thêm bài luyện theo chủ đề để củng cố kiến thức, đánh giá lại {timeframe}."
        else:
            action = f"Làm thêm bài luyện tập cho {feat_lbl} {timeframe} để cải thiện dần độ chắc kiến thức — hiện thấp hơn nhóm {gap_abs:.0f}%."
    elif priority == "Duy trì thế mạnh":
        action = f"{feat_lbl} đang cao hơn nhóm {gap_abs:.0f}% — phù hợp để thử thêm bài nâng cao hoặc chia sẻ kinh nghiệm với bạn cùng nhóm."
    else:
        action = f"{feat_lbl} hiện gần với mức trung bình nhóm (chênh lệch {gap_pct:+.0f}%) — tiếp tục theo dõi thêm 1–2 tuần trước khi cần điều chỉnh."
    return action


def compute_intervention_plan(diff_pct_series: pd.Series, selected_cols: list[str]) -> pd.DataFrame:
    """Bảng can thiệp ưu tiên theo % chênh lệch — ngưỡng phân loại mức ưu tiên
    giữ nguyên (<=-20% Cao, <=-10% Trung bình, >=+10% Duy trì thế mạnh, còn lại
    Theo dõi), nhưng NỘI DUNG hành động gợi ý giờ gắn với đúng đặc trưng cụ thể
    (tên hiển thị tiếng Việt + % chênh lệch thật) thay vì 1 câu chung chung lặp
    lại cho mọi đặc trưng."""
    rows = []
    for feat in selected_cols:
        gap_pct = float(diff_pct_series.get(feat, 0.0))
        feat_lbl = feature_label(feat)
        if gap_pct <= -20:
            priority = "Cao"
        elif gap_pct <= -10:
            priority = "Trung bình"
        elif gap_pct >= 10:
            priority = "Duy trì thế mạnh"
        else:
            priority = "Theo dõi"
        action = _build_intervention_text(feat, feat_lbl, gap_pct, priority)
        rows.append(
            {
                "Chỉ số": feat_lbl,
                "Chênh lệch so với nhóm (%)": round(gap_pct, 1),
                "Mức ưu tiên": priority,
                "Hành động gợi ý": action,
            }
        )
    return pd.DataFrame(rows).sort_values(by="Chênh lệch so với nhóm (%)", ascending=True)


def find_similar_students(X_processed, cluster_positions, student_position: int, top_k: int = 5):
    """Top-k bạn học tương tự trong CÙNG 1 cụm theo cosine similarity trên
    ma trận đặc trưng đã chuẩn hóa — Y HỆT logic cũ (Bước 4, Phần 'Gợi ý cá
    nhân'). `cluster_positions`: mảng vị trí hàng (trong df_results/X_processed
    gốc) thuộc cụm đang xem. `student_position`: vị trí hàng của sinh viên đang
    xem trong CÙNG hệ quy chiếu đó (không phải cluster_positions).

    Trả về list[(global_position, similarity_score)] đã sắp theo độ tương đồng
    giảm dần, KHÔNG gồm chính sinh viên đó — rỗng nếu sinh viên không thuộc cụm
    hoặc cụm có < 2 sinh viên."""
    cluster_pos = np.asarray(cluster_positions)
    cset = set(cluster_pos.tolist())
    if student_position not in cset or len(cluster_pos) < 2:
        return []

    rel_idx = int(np.where(cluster_pos == student_position)[0][0])
    X_cluster = X_processed[cluster_pos]
    sims = cosine_similarity(X_cluster[rel_idx : rel_idx + 1], X_cluster).flatten()
    sims_rel = [(i, s) for i, s in enumerate(sims) if i != rel_idx]
    sims_rel.sort(key=lambda x: x[1], reverse=True)

    top = sims_rel[:top_k]
    return [(int(cluster_pos[rel_i]), float(score)) for rel_i, score in top]


def find_reference_cluster(cluster_means_all: pd.DataFrame, current_cluster_id, weakness_cols: list[str]):
    """Cụm khác có trung bình CAO NHẤT trên đúng các đặc trưng đang là điểm yếu
    của cụm hiện tại — Y HỆT logic cũ (Bước 4, Phần 'Gợi ý cụm tham chiếu').
    Trả về cluster_id phù hợp nhất, hoặc None nếu không có điểm yếu/không tìm
    được cụm tham chiếu."""
    if not weakness_cols:
        return None
    ref_scores = {}
    for cid, row in cluster_means_all.iterrows():
        if cid == current_cluster_id:
            continue
        ref_scores[cid] = row[weakness_cols].mean()
    if not ref_scores:
        return None
    return max(ref_scores.items(), key=lambda kv: kv[1])[0]
