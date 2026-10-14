"""Sample data generation and loading."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import streamlit as st

from dss.config import (
    IMB_LEARN_AVAILABLE, SMOTE, BorderlineSMOTE, ADASYN, ImbPipeline,
    ColumnTransformer, RobustScaler, MinMaxScaler, StandardScaler,
    Pipeline, KNNImputer, SimpleImputer, OneHotEncoder,
)
from dss.core.trainers import DataPreprocessor
from dss.security.upload_security import UploadValidationError, parse_tabular_upload
from dss.core.target_utils import (
    score_to_xep_loai,
    CANONICAL_TARGET_REGRESSION,
    CANONICAL_TARGET_CLASSIFICATION,
    LEGACY_ALIAS_REGRESSION,
    LEGACY_ALIAS_CLASSIFICATION,
)

try:
    # imbalanced-learn (tùy chọn) cho SMOTE/Borderline/ADASYN — dùng tên riêng
    # IMBLEARN_AVAILABLE/SVMSMOTE (khác IMB_LEARN_AVAILABLE ở dss.config) vì 5.py gốc
    # cũng có 2 khối try/except import imblearn độc lập ở 2 vị trí khác nhau.
    from imblearn.over_sampling import SVMSMOTE  # type: ignore
    IMBLEARN_AVAILABLE = True
except Exception:
    SVMSMOTE = None
    IMBLEARN_AVAILABLE = False


# Điểm theo CHỦ ĐỀ/KỸ NĂNG (khác với điểm tổng theo bài kiểm tra ở trên) — cho phép
# chẩn đoán "sinh viên yếu ở đâu" cụ thể thay vì chỉ biết điểm tổng. Dùng chung bởi
# generate_data(), biểu đồ chẩn đoán trong ai_advisor_tab, và _build_demo_study_plan
# (map tên cột -> nhãn tiếng Việt hiển thị cho người dùng).
TOPIC_SCORE_COLUMNS = {
    "diem_thong_ke": "Thống kê",
    "diem_xu_ly_du_lieu": "Xử lý dữ liệu",
    "diem_truc_quan_hoa": "Trực quan hóa dữ liệu",
    "diem_machine_learning": "Machine Learning cơ bản",
    "diem_lap_trinh": "Lập trình Python",
}

# Nhãn hiển thị tiếng Việt cho MỌI cột dữ liệu thô có thể xuất hiện trực tiếp
# trên UI (bảng, biểu đồ, prompt AI) — nguồn TRUNG TÂM DUY NHẤT, không hard-code
# rải rác ở từng tab. Bao gồm cả TOPIC_SCORE_COLUMNS để chỉ có 1 chỗ tra cứu.
# feature_label() bên dưới là điểm gọi duy nhất nên dùng, KHÔNG đọc dict này
# trực tiếp (đảm bảo luôn có fallback an toàn cho cột lạ/chưa khai báo).
FEATURE_LABELS = {
    "diem_ky_nay": "Điểm kỳ này",
    "diem_ky_sau": "Điểm kỳ sau (dự đoán)",
    "final_score": "Điểm tổng kết",
    "gpa_previous": "GPA kỳ trước",
    "grade": "Xếp loại",
    "xep_loai": "Xếp loại",
    "ngay_hoat_dong_gan_nhat": "Số ngày từ lần hoạt động gần nhất",
    "so_lan_dang_nhap": "Số lần đăng nhập",
    "ty_le_hoan_thanh_bai_tap": "Tỷ lệ hoàn thành bài tập",
    "ty_le_diem_danh": "Tỷ lệ điểm danh",
    "so_gio_hoc_tuan": "Số giờ học mỗi tuần",
    "diem_giua_ky": "Điểm giữa kỳ",
    "diem_du_an": "Điểm dự án",
    **TOPIC_SCORE_COLUMNS,
}

# A-4: danh sách cột ĐƯỢC PHÉP dùng làm căn cứ phát hiện "điểm yếu" (ai_advisor.py)
# kèm chiều tốt/xấu — luật cũ áp "col_val < avg_val*0.9" cho MỌI cột số, kể cả
# cột mà giá trị THẤP mới là TỐT (vd. ngay_hoat_dong_gan_nhat: số ngày từ lần
# hoạt động gần nhất — càng THẤP càng tốt, luật cũ sẽ gắn nhầm "điểm yếu" cho
# SINH VIÊN TÍCH CỰC hơn trung bình lớp) và cho cả bí danh/target (final_score
# — chính là diem_ky_sau dưới tên khác). Cột không có trong danh sách này KHÔNG
# được dùng làm căn cứ điểm yếu, dù vẫn là cột số hợp lệ cho mục đích khác.
WEAKNESS_DETECTION_DIRECTIONS = {
    "diem_ky_nay": "higher_is_better",
    "diem_giua_ky": "higher_is_better",
    "diem_du_an": "higher_is_better",
    "ty_le_diem_danh": "higher_is_better",
    "so_gio_hoc_tuan": "higher_is_better",
    "gpa_previous": "higher_is_better",
    "so_lan_dang_nhap": "higher_is_better",
    "ty_le_hoan_thanh_bai_tap": "higher_is_better",
    "ngay_hoat_dong_gan_nhat": "lower_is_better",
    **{col: "higher_is_better" for col in TOPIC_SCORE_COLUMNS},
}


def is_weakness(col: str, col_val: float, avg_val: float, margin: float = 0.10) -> bool:
    """A-4: phát hiện "điểm yếu" ĐÚNG CHIỀU tốt/xấu của từng cột, CHỈ áp dụng
    cho cột đã khai báo trong WEAKNESS_DETECTION_DIRECTIONS (loại trừ hoàn
    toàn bí danh/target và cột chưa rõ ngữ nghĩa). `margin` mặc định 0.10
    (lệch 10% so với trung bình lớp) — giữ nguyên ngưỡng cũ."""
    direction = WEAKNESS_DETECTION_DIRECTIONS.get(col)
    if direction is None or avg_val == 0:
        return False
    if direction == "higher_is_better":
        return col_val < avg_val * (1 - margin)
    return col_val > avg_val * (1 + margin)


def is_production_environment() -> bool:
    """Audit 2026-09 (Production Demo Policy correction): trong môi trường
    REAL_LMS, KHÔNG được phép có bất kỳ đường dẫn Demo/mô phỏng nào lộ ra cho
    người dùng cuối — kể cả khi người dùng đã "xác nhận" muốn dùng Demo. Khi
    hàm này trả về True, mọi nhánh Demo ở các tab dùng chung hàm này (ai_advisor,
    advisory...) phải bị chặn và thay bằng thông báo trung thực (chưa cấu
    hình/chưa khả dụng). Dùng chung 1 điểm gọi duy nhất để không lệch định
    nghĩa "production" giữa các module."""
    # C1.1: ủy quyền cho hợp đồng môi trường DUY NHẤT (dss/core/runtime_mode.py):
    # EDUDSS_ENV=production (hoặc giá trị lạ → coi là production) HOẶC EDUDSS_MODE=REAL_LMS.
    from dss.core.runtime_mode import is_production
    return is_production()


def feature_label(column_name: str) -> str:
    """Nhãn tiếng Việt thân thiện cho 1 cột dữ liệu thô — ĐIỂM GỌI DUY NHẤT nên
    dùng ở UI (bảng/biểu đồ/prompt) thay vì hiển thị thẳng tên cột kỹ thuật
    (snake_case). Cột chưa khai báo trong FEATURE_LABELS vẫn được làm đẹp tối
    thiểu (bỏ gạch dưới, viết hoa chữ đầu) thay vì hiển thị nguyên dạng."""
    if column_name in FEATURE_LABELS:
        return FEATURE_LABELS[column_name]
    return str(column_name).replace("_", " ").strip().capitalize()


# Bảng màu cố định (deterministic) theo TÊN môn/chủ đề — cùng 1 môn luôn ra
# cùng 1 màu ở MỌI biểu đồ trong hệ thống, không phụ thuộc thứ tự/index trong
# danh sách (danh sách môn có thể đổi khi dataset đổi). Palette pastel/chuyên
# nghiệp, đủ tương phản để đọc số trên nền màu.
COURSE_COLOR_MAP = {
    "Thống kê": "#2563EB",              # xanh dương
    "Xử lý dữ liệu": "#F59E0B",         # cam
    "Trực quan hóa dữ liệu": "#16A34A", # xanh lá
    "Machine Learning cơ bản": "#7C3AED",  # tím
    "Lập trình Python": "#DB2777",      # hồng/đỏ
}
_COURSE_COLOR_FALLBACK_PALETTE = [
    "#0D9488", "#EA580C", "#4338CA", "#B45309", "#0891B2",
    "#65A30D", "#C026D3", "#334155", "#DC2626", "#0EA5E9",
]


def topic_color(topic_name: str) -> str:
    """Màu cố định cho 1 môn/chủ đề theo TÊN (không theo index) — môn đã biết
    tra COURSE_COLOR_MAP; môn lạ (dataset mới) tự sinh màu ổn định bằng hash
    tên môn trên palette dự phòng, để cùng 1 tên môn luôn ra cùng 1 màu giữa
    các lần chạy/biểu đồ khác nhau."""
    if topic_name in COURSE_COLOR_MAP:
        return COURSE_COLOR_MAP[topic_name]
    # hash() built-in bị Python random hoá theo phiên chạy (PYTHONHASHSEED) —
    # dùng md5 (ổn định tuyệt đối giữa các lần chạy/tiến trình khác nhau) để
    # cùng 1 tên môn LUÔN ra cùng 1 màu, kể cả sau khi khởi động lại server.
    import hashlib
    digest = hashlib.md5(str(topic_name).encode("utf-8")).hexdigest()
    idx = int(digest, 16) % len(_COURSE_COLOR_FALLBACK_PALETTE)
    return _COURSE_COLOR_FALLBACK_PALETTE[idx]


def generate_data(n_students=1000, n_samples=None, random_state: int | None = 42):
    """Tạo dữ liệu sinh viên MÔ PHỎNG (SYNTHETIC / DEMO DATA ONLY).

    CẢNH BÁO KIẾN TRÚC / PHƯƠNG PHÁP LUẬN:
    - Đây là dữ liệu giả lập phục vụ demo giao diện, kiểm thử chức năng, integration test,
      và khởi tạo ứng dụng (bootstrap) khi chưa có file người dùng tải lên.
    - Công thức tính 'diem_ky_sau' ở dưới là giả định mô phỏng, KHÔNG PHẢI công thức chính thức
      để tính kết quả học kỳ tiếp theo và KHÔNG ĐƯỢC coi là bằng chứng rằng mô hình có khả năng
      dự đoán dữ liệu sinh viên thực với độ chính xác cao.
    - Metadata bắt buộc: data_source_type = "synthetic". Các chỉ số metric tính từ dữ liệu này
      phải được ghi rõ là simulation/demo metrics.
    - Tham số random_state (mặc định 42) đảm bảo tính tái lập (reproducibility) khi chạy thử nghiệm.
    """
    if n_samples is not None:
        n_students = n_samples

    rng = np.random.RandomState(random_state) if random_state is not None else np.random

    # Tạo điểm kỳ này (từ 0-10)
    diem_ky_nay = rng.normal(7.0, 1.5, n_students).clip(0, 10)

    data = {
        'student_id': [f'SV{i:03d}' for i in range(1, n_students + 1)],
        'diem_ky_nay': diem_ky_nay,  # Điểm kỳ này (feature chính, đã biết tại thời điểm t)
        'ty_le_diem_danh': rng.uniform(0.6, 1.0, n_students),  # Tỷ lệ điểm danh
        'so_gio_hoc_tuan': rng.normal(15, 5, n_students).clip(2, 35),  # Số giờ học/tuần
        'diem_giua_ky': rng.normal(6.5, 1.5, n_students).clip(0, 10),  # Điểm giữa kỳ
        'diem_du_an': rng.normal(7.0, 1.0, n_students).clip(0, 10),  # Điểm dự án
    }

    # Điểm theo từng chủ đề
    for _topic_col in TOPIC_SCORE_COLUMNS:
        data[_topic_col] = np.clip(
            0.55 * diem_ky_nay + 0.45 * rng.normal(6.5, 2.0, n_students),
            0, 10,
        )

    df = pd.DataFrame(data)

    # TẠO SYNTHETIC TARGET CHO DEMO (Chỉ dùng cho simulation/demo mode)
    df['diem_ky_sau'] = (
        0.60 * df['diem_ky_nay'] +
        0.15 * df['diem_giua_ky'] +
        0.10 * df['diem_du_an'] +
        0.10 * (df['ty_le_diem_danh'] * 10) +
        0.05 * (df['so_gio_hoc_tuan'] / 3.5)
    ) + rng.normal(0, 0.08, n_students)

    df['diem_ky_sau'] = df['diem_ky_sau'].clip(0, 10)

    for idx in range(len(df)):
        diem_nay = df.loc[idx, 'diem_ky_nay']
        diem_sau = df.loc[idx, 'diem_ky_sau']
        if abs(diem_sau - diem_nay) > 1.5:
            if diem_sau > diem_nay:
                df.loc[idx, 'diem_ky_sau'] = min(diem_nay + 1.5, 10)
            else:
                df.loc[idx, 'diem_ky_sau'] = max(diem_nay - 1.5, 0)

    df = df.round(2)

    # Tạo 'xep_loai' chuẩn hóa bằng hàm tập trung score_to_xep_loai
    df['xep_loai'] = score_to_xep_loai(df['diem_ky_sau']).astype(str)

    # Legacy aliases (chỉ giữ để tương thích ngược hiển thị khi cần; khi train sẽ được canonicalize)
    df['final_score'] = df['diem_ky_sau']
    df['grade'] = df['xep_loai']
    df['gpa_previous'] = (df['diem_ky_nay'] / 2.5).round(2)

    # Gắn cờ metadata nhận diện chế độ dữ liệu mô phỏng
    df.attrs["data_source_type"] = "synthetic"

    return df


def is_synthetic_data(df) -> bool:
    """E-1: true khi dữ liệu đang dùng là dữ liệu MÔ PHỎNG (generate_data()),
    không phải dữ liệu LMS/CMS thật đã tải lên — đọc từ df.attrs['data_source_type']
    do generate_data() gắn sẵn. Mặc định True khi thiếu attrs hoàn toàn (an toàn
    hơn: thà cảnh báo nhầm còn hơn để lọt dữ liệu giả hiển thị như dữ liệu thật)."""
    return getattr(df, "attrs", {}).get("data_source_type", "synthetic") == "synthetic"


def generate_lms_data(n_students=60, course_name="Nhập môn Khoa học dữ liệu", term="HK1 2025-2026"):
    """Dữ liệu GIẢ LẬP mô phỏng đồng bộ từ LMS (DEMO ONLY)."""
    df = generate_data(n_students)
    df['so_lan_dang_nhap'] = np.random.poisson(18, n_students).clip(1, 60)
    df['ty_le_hoan_thanh_bai_tap'] = np.random.uniform(0.4, 1.0, n_students).round(2)
    df['ngay_hoat_dong_gan_nhat'] = np.random.randint(0, 14, n_students)
    df.attrs["data_source_type"] = "synthetic"
    return df, course_name, term


@st.cache_data(show_spinner=False)
def load_data(uploaded_file):
    """
    Tải dữ liệu từ file (CSV hoặc Excel) được upload bởi người dùng.
    Dữ liệu người dùng tải lên là REAL DATA MODE — target phải được quan sát thực tế trong file,
    tuyệt đối không tự tính toán bằng công thức mô phỏng.

    Args:
        uploaded_file: File object từ st.file_uploader (CSV hoặc Excel)

    Returns:
        pd.DataFrame: DataFrame chứa dữ liệu đã được load, hoặc None nếu có lỗi
    """
    if uploaded_file is None:
        return None
    from pathlib import Path
    if isinstance(uploaded_file, (str, Path)):
        # Đường dẫn cục bộ do code nội bộ truyền vào (không phải file người dùng
        # tải lên qua trình duyệt) — không đi qua parse_tabular_upload (validate
        # kích thước/kiểu MIME của 1 UploadedFile), vẫn dùng pandas trực tiếp.
        try:
            file_name_lower = str(uploaded_file).lower()
            if file_name_lower.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            elif file_name_lower.endswith('.xls') or file_name_lower.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
            else:
                return None
            if df is not None:
                df.attrs["data_source_type"] = "real"
            return df
        except Exception as e:
            st.error(f"Lỗi khi tải dữ liệu: {e}")
            return None
    # File thực sự do người dùng tải lên qua trình duyệt (st.file_uploader) —
    # dữ liệu KHÔNG ĐÁNG TIN, phải qua parse_tabular_upload (allowlist đuôi
    # file/MIME, giới hạn dung lượng/số dòng/cột, chống path traversal qua tên
    # file, kiểm tra định dạng CSV/XLSX/XLS thực sự hợp lệ trước khi parse).
    try:
        df = parse_tabular_upload(uploaded_file).frame
        df.attrs["data_source_type"] = "real"
        return df
    except UploadValidationError as exc:
        st.error(str(exc))
        return None


def create_shared_preprocessor(numeric_features, categorical_features, scaler_type="StandardScaler"):
    """Tạo một ColumnTransformer CHUNG cho cả 2 loại mô hình (để đảm bảo tính nhất quán)."""
    if ColumnTransformer is None:
        raise ImportError(
            "ColumnTransformer không khả dụng. Vui lòng cập nhật scikit-learn >= 0.20 để sử dụng tính năng này.")
    
    transformers = []
    
    # Chọn Scaler dựa trên tham số
    if scaler_type == "RobustScaler":
        scaler = RobustScaler()
    elif scaler_type == "MinMaxScaler":
        scaler = MinMaxScaler()
    else:
        scaler = StandardScaler()
        
    if numeric_features:
        numeric_transformer = Pipeline(steps=[
            ('imputer', KNNImputer(n_neighbors=5)),
            ('scaler', scaler)
        ])
        transformers.append(('num', numeric_transformer, numeric_features))
    if categorical_features:
        categorical_transformer = Pipeline(
            steps=[
                ('imputer', SimpleImputer(
                    strategy='most_frequent')), ('onehot', OneHotEncoder(
                        handle_unknown='ignore', sparse_output=False))])
        transformers.append(
            ('cat', categorical_transformer, categorical_features))

    return ColumnTransformer(
        transformers=transformers,
        remainder='passthrough')


def balance_dataset(X, y, method="smote", random_state=42):
    """
    Cân bằng tập dữ liệu phân loại (chỉ dùng cho classification).
    method: "smote", "borderline", "svm", "adasyn" hoặc "none"
    Trả về: X_res, y_res (pandas DataFrame/Series)
    Ghi chú:
    - Yêu cầu imblearn cài đặt để dùng SMOTE biến thể. Nếu không, hàm trả về bản gốc và cảnh báo.
    """
    if method is None or method == "none":
        return X, y

    if not IMBLEARN_AVAILABLE:
        # imblearn không cài -> fallback
        try:
            import warnings as _w
            _w.warn("imblearn không có — bỏ qua bước cân bằng lớp. Cài đặt imbalanced-learn để bật SMOTE.")
        except ImportError:
            pass
        return X, y
        
    sampler = None
    method = (method or "smote").lower()
    if method == "smote":
        sampler = SMOTE(random_state=random_state)
    elif method == "borderline":
        sampler = BorderlineSMOTE(random_state=random_state)
    elif method == "svm":
        sampler = SVMSMOTE(random_state=random_state)
    elif method == "adasyn":
        sampler = ADASYN(random_state=random_state)
    else:
        return X, y
    try:
        X_res, y_res = sampler.fit_resample(X, y)
        # Return as same type (pandas) if input was DataFrame/Series
        if isinstance(X, pd.DataFrame):
            X_res = pd.DataFrame(X_res, columns=X.columns)
        if isinstance(y, (pd.Series, pd.Index)):
            y_res = pd.Series(y_res, name=getattr(y, "name", None))
        return X_res, y_res
    except Exception as e:
        # Nếu lỗi, trả về bản gốc và log
        try:
            import streamlit as _st
            _st.warning(f"⚠️ Cân bằng dữ liệu thất bại ({method}): {e}. Bỏ qua cân bằng.")
        except ImportError:
            pass
        return X, y
