"""Bài giảng mẫu cho chế độ DEMO — môn CS301 "Học máy ứng dụng trong giáo dục"
(app/demo/cms_lectures/*.md).

Nạp qua ĐÚNG hàm mà nút "Nạp bài giảng" của Giảng viên gọi
(cms_lecture_repository.ingest_lecture_material) — không ghi tắt vào registry.
Chỉ dùng khi chế độ dữ liệu cho phép dữ liệu mẫu (runtime_mode.synthetic_data_allowed);
an toàn khi chạy lại: bài đã có thì bỏ qua, không tạo thêm phiên bản.
"""

from __future__ import annotations

from pathlib import Path

from dss.services import cms_lecture_repository as cms

COURSE_ID = "CS301"
LECTURE_DIR = Path(__file__).resolve().parents[2] / "demo" / "cms_lectures"

# (tệp, lesson_id, topic_id, tiêu đề, độ khó, mục tiêu bài học)
LESSONS = [
    (
        "CS301_L01_hoi_quy_tuyen_tinh.md",
        "CS301-L01",
        "hoi_quy_tuyen_tinh",
        "Bài 1 — Hồi quy tuyến tính: dự đoán điểm học kỳ sau",
        "Foundation",
        "Hiểu mô hình hồi quy tuyến tính, cách học hệ số và đọc kết quả dự đoán điểm.",
    ),
    (
        "CS301_L02_random_forest.md",
        "CS301-L02",
        "random_forest",
        "Bài 2 — Cây quyết định và Random Forest",
        "Standard",
        "Hiểu cây quyết định, quá khớp và cách Random Forest kết hợp nhiều cây.",
    ),
    (
        "CS301_L03_danh_gia_mo_hinh.md",
        "CS301-L03",
        "danh_gia_mo_hinh",
        "Bài 3 — Đánh giá mô hình: kiểm định chéo và các chỉ số",
        "Standard",
        "Chia dữ liệu và kiểm định chéo đúng cách; chọn MAE/RMSE/R², F1-macro; đọc ma trận nhầm lẫn.",
    ),
]


def available() -> bool:
    return all((LECTURE_DIR / f).exists() for f, *_ in LESSONS)


def seed(llm_integration, lecturer_id: str = "giangvien") -> list[tuple[str, bool]]:
    """Nạp các bài còn thiếu. Trả [(lesson_id, đã_nạp_mới)]."""
    out = []
    for file_name, lesson_id, topic_id, title, difficulty, outcome in LESSONS:
        existing = cms.get_lesson(lesson_id)
        if existing and existing.current_document_id:
            out.append((lesson_id, False))
            continue
        cms.ingest_lecture_material(
            file_bytes=(LECTURE_DIR / file_name).read_bytes(),
            file_name=file_name,
            title=title,
            course_id=COURSE_ID,
            lesson_id=lesson_id,
            topic_id=topic_id,
            lecturer_id=lecturer_id,
            llm_integration=llm_integration,
            learning_outcome=outcome,
            difficulty=difficulty,
            content_type="document",
        )
        out.append((lesson_id, True))
    return out
