"""Centralized Display Mapper for EduDSS.

Chuyển đổi toàn bộ tên cột kỹ thuật (snake_case), mã enum chẩn đoán, trạng thái duyệt
quiz, trạng thái thuê bao, và các thuật ngữ ML thành nhãn tiếng Việt học thuật chuẩn mực.
Tuyệt đối KHÔNG hiển thị raw identifiers trên giao diện người dùng.
"""
from __future__ import annotations
from typing import Optional, Dict, Any

# 1. Cột dữ liệu & đặc trưng học tập
RAW_COLUMN_TO_VIETNAMESE: Dict[str, str] = {
    "student_id": "Mã sinh viên",
    "ma_sinh_vien": "Mã sinh viên",
    "ho_ten": "Họ và tên",
    "full_name": "Họ và tên",
    "lop": "Lớp sinh hoạt",
    "class_name": "Lớp sinh hoạt",
    "khoa": "Khoa / Ngành",
    "final_score": "Điểm tổng kết",
    "diem_tong_ket": "Điểm tổng kết",
    "diem_ky_nay": "Điểm học kỳ hiện tại",
    "diem_ky_sau": "Điểm kỳ sau (dự đoán)",
    "gpa_previous": "GPA kỳ trước",
    "gpa_tich_luy": "GPA tích lũy",
    "gpa": "Điểm trung bình (GPA)",
    "diem_giua_ky": "Điểm giữa kỳ",
    "diem_chuyen_can": "Điểm chuyên cần",
    "diem_du_an": "Điểm đồ án / dự án",
    "ty_le_diem_danh": "Tỷ lệ điểm danh (%)",
    "attendance_rate": "Tỷ lệ điểm danh (%)",
    "so_gio_hoc_tuan": "Số giờ tự học / tuần",
    "study_hours_weekly": "Số giờ tự học / tuần",
    "so_lan_dang_nhap": "Số lượt tương tác LMS",
    "lms_logins": "Số lượt tương tác LMS",
    "ty_le_hoan_thanh_bai_tap": "Tỷ lệ hoàn thành bài tập (%)",
    "assignment_completion_rate": "Tỷ lệ hoàn thành bài tập (%)",
    "ngay_hoat_dong_gan_nhat": "Số ngày từ lần học gần nhất",
    "days_since_last_activity": "Số ngày từ lần học gần nhất",
    "xep_loai": "Xếp loại học lực",
    "grade": "Xếp loại học lực",
    "muc_do_nguy_co": "Mức độ nguy cơ học tập",
    "risk_level": "Mức độ nguy cơ học tập",
    # Điểm chủ đề / kỹ năng
    "diem_thong_ke": "Thống kê & Xác suất",
    "diem_xu_ly_du_lieu": "Kỹ thuật tiền xử lý dữ liệu",
    "diem_truc_quan_hoa": "Trực quan hóa dữ liệu",
    "diem_machine_learning": "Machine Learning căn bản",
    "diem_lap_trinh": "Lập trình Python & Cấu trúc dữ liệu",
    "diem_co_so_du_lieu": "Cơ sở dữ liệu & SQL",
    "diem_toan_roi_rac": "Toán rời rạc & Đại số",
}

# 2. Danh mục chẩn đoán học tập (Diagnosis categories)
DIAGNOSIS_CATEGORY_TO_VIETNAMESE: Dict[str, str] = {
    "MASTERY_ON_TRACK": "Tiến độ học tập ổn định",
    "KNOWLEDGE_GAP": "Thiếu hụt kiến thức chuyên môn",
    "PREREQUISITE_GAP": "Chưa vững kiến thức nền tảng",
    "LOW_PRACTICE": "Thời lượng luyện tập chưa đạt yêu cầu",
    "LOW_RETENTION": "Khả năng ghi nhớ dài hạn cần củng cố",
    "SLOW_RESPONSE": "Tốc độ xử lý bài tập còn chậm",
    "CARELESS_FAST_RESPONSE": "Làm bài vội, thiếu kiểm tra lại",
    "LOW_ENGAGEMENT": "Mức độ tương tác học tập thấp",
    "INCONSISTENT_STUDY": "Nhịp độ học tập chưa đều đặn",
    "INSUFFICIENT_DATA": "Chưa đủ dữ liệu để đưa ra kết luận",
}

# 3. Trạng thái quy trình duyệt Quiz (Quiz Approval Workflow)
QUIZ_STATUS_TO_VIETNAMESE: Dict[str, str] = {
    "DRAFT": "Bản nháp",
    "PENDING_LECTURER_APPROVAL": "Chờ giảng viên duyệt",
    "APPROVED": "Đã phê duyệt",
    "REJECTED": "Đã từ chối",
}

# 4. Nguồn gốc dữ liệu học tập (Data Context Source)
DATA_SOURCE_TO_VIETNAMESE: Dict[str, str] = {
    "REAL": "Dữ liệu LMS chính thức",
    "UPLOADED": "Dữ liệu giảng viên tải lên",
    "DEMO": "Dữ liệu mô phỏng thử nghiệm",
    "EMPTY": "Chưa có dữ liệu học tập",
}

# 5. Trạng thái thuê bao SaaS (Subscription status)
SUBSCRIPTION_STATUS_TO_VIETNAMESE: Dict[str, str] = {
    "ACTIVE": "Đang hoạt động",
    "TRIAL": "Giai đoạn triển khai (Pilot)",
    "EXPIRED": "Hết hạn thuê bao",
    "SUSPENDED": "Tạm ngưng dịch vụ",
}

# 6. Gói dịch vụ SaaS (Subscription plans)
SUBSCRIPTION_PLAN_TO_VIETNAMESE: Dict[str, str] = {
    "STARTER": "Gói Khoa / Bộ môn cơ bản",
    "PROFESSIONAL": "Gói Trường / Viện chuyên nghiệp",
    "ENTERPRISE": "Gói Đại học thông minh toàn diện",
}

# 7. Thuật ngữ & Chỉ số Machine Learning kèm giải thích
ML_METRIC_LABELS: Dict[str, Dict[str, str]] = {
    "accuracy": {
        "label": "Độ chính xác tổng thể (Accuracy)",
        "desc": "Tỷ lệ dự đoán đúng trên tổng số sinh viên đánh giá.",
    },
    "precision": {
        "label": "Độ chuẩn xác (Precision)",
        "desc": "Khả năng cảnh báo nguy cơ chính xác, hạn chế báo động nhầm.",
    },
    "recall": {
        "label": "Độ bao phủ (Recall)",
        "desc": "Tỷ lệ phát hiện đầy đủ sinh viên thực sự có nguy cơ trượt/cảnh báo.",
    },
    "f1": {
        "label": "Điểm F1-Score cân bằng",
        "desc": "Trung bình điều hòa giữa Precision và Recall, phản ánh mô hình cân bằng.",
    },
    "mae": {
        "label": "Sai số tuyệt đối trung bình (MAE)",
        "desc": "Độ lệch trung bình giữa điểm dự đoán và điểm thực tế (tính theo thang 10).",
    },
    "rmse": {
        "label": "Căn sai số bình phương trung bình (RMSE)",
        "desc": "Độ lệch có phạt nặng sai số lớn, càng thấp mô hình dự báo điểm càng chuẩn.",
    },
    "r2": {
        "label": "Hệ số xác định (R²)",
        "desc": "Tỷ lệ biến thiên của điểm số được mô hình giải thích (càng gần 1.0 càng tốt).",
    },
    "silhouette": {
        "label": "Chỉ số tách cụm Silhouette",
        "desc": "Độ chặt chẽ và tách biệt giữa các nhóm sinh viên (-1 đến +1, càng gần 1 càng rõ nhóm).",
    },
    "davies_bouldin": {
        "label": "Chỉ số Davies-Bouldin",
        "desc": "Mức độ tương đồng giữa các cụm (càng thấp thể hiện phân cụm càng chất lượng).",
    },
}

# 8. Namespace tri thức RAG sang ngôn ngữ học thuật
RAG_NAMESPACE_TO_VIETNAMESE: Dict[str, str] = {
    "dss_rag_general": "Quy chế đào tạo & Sổ tay sinh viên",
    "dss_rag_lecture": "Học liệu & Bài giảng số của Giảng viên",
    "dss_rag_career": "Từ điển kỹ năng & Chuẩn đầu ra nghề nghiệp",
}


def map_field_label(field_name: str) -> str:
    """Chuyển đổi tên trường dữ liệu snake_case sang tiếng Việt học thuật."""
    if not field_name:
        return ""
    key = str(field_name).strip()
    if key in RAW_COLUMN_TO_VIETNAMESE:
        return RAW_COLUMN_TO_VIETNAMESE[key]
    # Tra cứu hoa thường
    lower_key = key.lower()
    if lower_key in RAW_COLUMN_TO_VIETNAMESE:
        return RAW_COLUMN_TO_VIETNAMESE[lower_key]
    # Fallback tự động làm đẹp tên không có trong từ điển
    return key.replace("_", " ").strip().title()


def map_diagnosis_category(cat_name: Optional[str]) -> str:
    """Chuyển đổi enum danh mục chẩn đoán sang tiếng Việt."""
    if not cat_name:
        return "Tiến độ bình thường"
    key = str(cat_name).strip()
    return DIAGNOSIS_CATEGORY_TO_VIETNAMESE.get(key, "Nhận định chung")


def map_quiz_status(status: Optional[str]) -> str:
    """Chuyển đổi trạng thái duyệt quiz sang tiếng Việt."""
    if not status:
        return "Bản nháp"
    key = str(status).strip().upper()
    return QUIZ_STATUS_TO_VIETNAMESE.get(key, "Chờ duyệt")


def map_data_source(source: Optional[str]) -> str:
    """Chuyển đổi mã nguồn dữ liệu sang tiếng Việt."""
    if not source:
        return "Chưa xác định"
    key = str(source).strip().upper()
    return DATA_SOURCE_TO_VIETNAMESE.get(key, "Dữ liệu học tập")


def map_subscription_status(status: Optional[str]) -> str:
    """Chuyển đổi trạng thái thuê bao sang tiếng Việt."""
    if not status:
        return "Chưa kích hoạt"
    key = str(status).strip().upper()
    return SUBSCRIPTION_STATUS_TO_VIETNAMESE.get(key, "Hoạt động")


def map_ml_metric(metric_key: str) -> Dict[str, str]:
    """Trả về label và mô tả tiếng Việt cho chỉ số ML."""
    lower_key = str(metric_key).lower().strip()
    return ML_METRIC_LABELS.get(lower_key, {
        "label": metric_key.upper(),
        "desc": f"Chỉ số đánh giá mô hình {metric_key.upper()}",
    })


def map_rag_namespace(namespace: str) -> str:
    """Chuyển đổi namespace RAG kỹ thuật sang tên học liệu thân thiện."""
    return RAG_NAMESPACE_TO_VIETNAMESE.get(str(namespace).strip(), "Tài liệu học tập tích hợp")


def clean_display_dataframe(df, max_cols: Optional[int] = None):
    """Hàm tiện ích đổi tên toàn bộ columns của một DataFrame sang tiếng Việt

    để hiển thị trên st.dataframe / st.table mà không sửa DataFrame gốc trong logic.
    """
    if df is None or not hasattr(df, "columns"):
        return df
    display_df = df.copy()
    rename_dict = {col: map_field_label(str(col)) for col in display_df.columns}
    display_df.rename(columns=rename_dict, inplace=True)
    if max_cols and len(display_df.columns) > max_cols:
        display_df = display_df.iloc[:, :max_cols]
    return display_df
