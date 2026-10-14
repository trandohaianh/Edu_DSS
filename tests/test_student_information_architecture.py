"""Audit 2026-09 — Special Student Role Audit + Student Information Architecture:
Student phải thấy mục tiêu học tập (Nhóm học tập của bạn / Dự đoán kết quả học
tập / Hướng nghiệp / Giải thích bài học), không phải thuật ngữ kỹ thuật ML
(Clustering / Training pipeline / CDSS / CMS). Backend/RBAC (ai_hub.py,
clustering.py "role != Sinh viên" gates) đã đúng từ trước — đây chỉ là các bài
test hồi quy cho lớp trình bày (labels/headers/expanders) vừa sửa, đọc trực
tiếp mã nguồn bằng `inspect.getsource` (không import dss.main vì đó là kịch
bản Streamlit cấp cao nhất, chạy toàn bộ khi import ngoài phiên Streamlit thật).
"""
from __future__ import annotations

import inspect
from pathlib import Path

_MAIN_PY = Path(__file__).resolve().parent.parent / "dss" / "main.py"


def test_main_py_source_role_branches_ml_hub_section_header():
    source = _MAIN_PY.read_text(encoding="utf-8")
    idx_tab = source.find('elif selected_main_tab == "🧪 Huấn luyện — Dự đoán":')
    assert idx_tab != -1
    window = source[idx_tab: idx_tab + 1500]
    assert 'current_role == "Sinh viên"' in window
    assert "Dự đoán kết quả học tập của bạn" in window
    assert "Huấn luyện & Dự đoán" in window


def test_main_py_source_gates_ml_jargon_glossary_and_pipeline_badge_for_student():
    """Badge nhắc 'pipeline CV' và expander từ điển thuật ngữ ML (GridSearchCV,
    overfitting, data leakage...) không được hiển thị vô điều kiện cho mọi vai
    trò — phải nằm sau `if current_role != "Sinh viên":`."""
    source = _MAIN_PY.read_text(encoding="utf-8")
    idx_glossary = source.find("Quy trình thực hiện & từ điển thuật ngữ")
    idx_badge = source.find("tiền xử lý nằm trong pipeline CV")
    idx_guard = source.find('if current_role != "Sinh viên":')
    assert idx_glossary != -1 and idx_badge != -1 and idx_guard != -1
    assert idx_guard < idx_badge < idx_glossary


def test_main_py_source_llm_sub_tabs_use_role_aware_labels_for_student():
    source = _MAIN_PY.read_text(encoding="utf-8")
    idx_map = source.find("_student_llm_tab_labels")
    assert idx_map != -1
    window = source[idx_map: idx_map + 800]
    assert "Kế hoạch học tập" in window
    assert "Hướng nghiệp" in window
    assert "Giải thích bài học" in window
    assert 'current_role == "Sinh viên"' in window


def test_clustering_tab_role_branches_header_and_hides_technical_guide_for_student():
    from dss.tabs import clustering

    source = inspect.getsource(clustering)
    idx_fn = source.find("def clustering_hybrid_tab(")
    assert idx_fn != -1
    window = source[idx_fn: idx_fn + 2500]
    assert 'role == "Sinh viên"' in window
    assert "Nhóm học tập của bạn" in window
    assert "Phân cụm & Gợi ý" in window
    # Expander kỹ thuật (Elbow/Silhouette/K-Means) phải nằm sau gate role != Sinh viên
    idx_guide = window.find("Hướng dẫn chi tiết từng bước")
    idx_guard = window.find('if role != "Sinh viên":')
    assert idx_guide != -1 and idx_guard != -1
    assert idx_guard < idx_guide


def test_clustering_tab_student_kpi_row_has_no_technical_cluster_count_label():
    """Thẻ KPI 'Số cụm (k)' chỉ dành Giảng viên/Admin — Sinh viên xem 'Nhóm học
    tập của bạn' thay vì số liệu kỹ thuật K-Means."""
    from dss.tabs import clustering

    source = inspect.getsource(clustering)
    idx_role_check = source.find('if role == "Sinh viên":')
    # Ranh giới chính xác của nhánh else (không dùng find("else:") chung chung
    # vì có thể khớp nhầm 1 khối if/else lồng bên trong nhánh Sinh viên trước đó).
    idx_else = source.find('else:\n        first_card = ("Dataset"', idx_role_check)
    assert idx_role_check != -1 and idx_else != -1
    student_branch = source[idx_role_check:idx_else]
    non_student_branch = source[idx_else: idx_else + 1200]
    assert "Số cụm (k)" not in student_branch
    assert "Nhóm học tập của bạn" in student_branch
    assert "Số cụm (k)" in non_student_branch


def test_advisory_tab_role_branches_header_without_cdss_acronym_for_student():
    """FINAL PRODUCTION GAP CLOSURE (Phần 21/41, 2026-09-26): trước đây nhánh
    Giảng viên/Admin vẫn ghi đầy đủ '(Career Decision Support System)' —
    test cũ chỉ đặc tả hành vi đó (biết là vấn đề, chưa sửa). Nay ĐÃ bỏ tên
    hệ thống tiếng Anh khỏi CẢ 2 nhánh — cập nhật test để không còn 2
    "sự thật" mâu thuẫn (test cũ khẳng định phải CÓ chuỗi kỹ thuật đó)."""
    from dss.tabs import advisory

    source = inspect.getsource(advisory.student_advisory_tab)
    assert 'role == "Sinh viên"' in source
    assert "Hướng nghiệp của bạn" in source
    assert "Định hướng nghề nghiệp" in source
    assert '"Tư vấn — Định hướng nghề nghiệp (Career Decision Support System)"' not in source, (
        "Tiêu đề kỹ thuật cũ không được dùng làm tham số section_header nữa."
    )
    idx_role_check = source.find('role == "Sinh viên"')
    idx_student_title = source.find("Hướng nghiệp của bạn")
    idx_staff_title = source.find('"Định hướng nghề nghiệp"')
    assert idx_role_check < idx_student_title < idx_staff_title, (
        "Nhánh Sinh viên (if) phải đứng trước nhánh Giảng viên/Admin (else) trong luồng if/else"
    )


def test_learning_explainer_tab_role_branches_header_without_cms_acronym_for_student():
    """FINAL PRODUCTION GAP CLOSURE (Phần 21/41, 2026-09-26): tương tự — bỏ
    '(CMS)' khỏi CẢ tiêu đề Giảng viên/Admin, không chỉ Sinh viên."""
    from dss.tabs import learning_explainer_tab as let

    source = inspect.getsource(let.learning_explainer_tab)
    assert 'role in ("Giảng viên / CVHT", "Admin")' in source
    assert "Giải thích bài học" in source
    assert "Giải thích bài giảng" in source
    assert '"AI Giải thích Bài giảng (CMS)"' not in source, "Tiêu đề kỹ thuật cũ không được dùng làm tham số section_header nữa."
    idx_if = source.find('role in ("Giảng viên / CVHT", "Admin")')
    idx_staff_title = source.find('"Giải thích bài giảng"')
    idx_student_title = source.find('"Giải thích bài học"')
    assert idx_if < idx_staff_title, "Tiêu đề 'Giải thích bài giảng' phải nằm trong nhánh Giảng viên/Admin"
    assert idx_student_title > idx_if


def test_learning_explainer_student_view_has_no_raw_cms_wording_in_visible_messages():
    """`CMS_ONLY`/`CMS_PLUS_SUPPLEMENTARY` là hằng số nội bộ (không hiển thị cho
    người dùng) nên được phép xuất hiện trong mã nguồn — chỉ kiểm tra các chuỗi
    thông báo thực sự hiển thị cho Sinh viên không còn nhắc tới "CMS"."""
    from dss.tabs import learning_explainer_tab as let

    source = inspect.getsource(let._render_student_view)
    assert "Chưa có bài giảng nào trong CMS" not in source
    assert "Chưa đủ nội dung CMS" not in source


def test_learning_explainer_quiz_panel_has_no_raw_cms_wording():
    from dss.tabs import learning_explainer_tab as let

    source = inspect.getsource(let._render_quiz_panel)
    assert "Chưa đủ nội dung CMS" not in source


def test_main_py_sidebar_groups_consultation_history_with_ai_assistant_for_student():
    """Sidebar IA audit: 'Lịch sử tư vấn' là lịch sử các lượt dùng Trợ lý AI —
    phải nằm cùng nhóm với 'Tư vấn — AI (LLM)' (nhóm TRỢ LÝ AI), không phải
    nhóm 'HỌC TẬP & PHÂN TÍCH' (phân tích học tập, không phải lịch sử hội thoại)."""
    source = _MAIN_PY.read_text(encoding="utf-8")
    idx_groups = source.find('SIDEBAR_NAV_GROUPS = {')
    idx_sinh_vien_end = source.find('"Giảng viên / CVHT": [', idx_groups)
    student_block = source[idx_groups:idx_sinh_vien_end]
    idx_ai_group = student_block.find('("TRỢ LÝ AI"')
    idx_study_group = student_block.find('("HỌC TẬP & PHÂN TÍCH"')
    assert idx_ai_group != -1 and idx_study_group != -1
    ai_group_line = student_block[idx_ai_group: student_block.find("]),", idx_ai_group)]
    study_group_line = student_block[idx_study_group: student_block.find("]),", idx_study_group)]
    assert "📝 Lịch sử tư vấn" in ai_group_line
    assert "📝 Lịch sử tư vấn" not in study_group_line


def test_clustering_tab_student_section_has_no_cosine_or_kmeans_jargon():
    """Student Product Acceptance audit (2026-09): mục 'Gợi ý theo nội dung'
    hiển thị cho Sinh viên trước đây ghi thẳng '(bạn học tương tự — cosine)'
    và một cảnh báo lỗi trỏ Sinh viên tới nút 'Chạy Phân cụm K-Means' mà
    Sinh viên không có quyền bấm (nút đó chỉ tồn tại trong khối cấu hình
    dành Giảng viên/Admin, role != Sinh viên)."""
    import inspect
    from dss.tabs import clustering

    source = inspect.getsource(clustering.clustering_hybrid_tab)
    # "cosine" vẫn được phép xuất hiện trong hướng dẫn kỹ thuật CHỈ Giảng
    # viên/Admin (đã gate role != Sinh viên từ trước) — chỉ kiểm tra đúng
    # dòng tiêu đề Sinh viên nhìn thấy đã được đổi, không cấm cả hàm.
    assert "bạn học tương tự — cosine" not in source
    assert "Bạn học có hồ sơ tương tự" in source
    idx_kmeans_warning = source.find("Chạy Phân cụm K-Means")
    if idx_kmeans_warning != -1:
        idx_role_guard = source.rfind('role == "Sinh viên"', 0, idx_kmeans_warning)
        idx_else = source.find("else:", idx_role_guard) if idx_role_guard != -1 else -1
        assert idx_role_guard != -1 and idx_else != -1 and idx_role_guard < idx_else < idx_kmeans_warning, (
            "Cảnh báo 'Chạy Phân cụm K-Means' phải nằm sau gate role != Sinh viên"
        )


def test_clustering_tab_cluster_legend_has_no_english_jargon_parentheticals():
    """'(Cluster Profiles)', '(Grouped Bar Chart)', '(Benchmark)' là các chú
    thích tiếng Anh kỹ thuật không cần thiết, hiển thị cho mọi vai trò kể cả
    Sinh viên."""
    import inspect
    from dss.tabs import clustering

    source = inspect.getsource(clustering.clustering_hybrid_tab)
    assert "(Cluster Profiles)" not in source
    assert "(Grouped Bar Chart)" not in source
    assert "(Benchmark)" not in source


def test_ai_advisor_tab_page_header_role_branches_for_student():
    """Student Product Acceptance audit (2026-09): nhãn điều hướng sub-tab đã
    đổi thành 'Kế hoạch học tập' cho Sinh viên (SIA-NAV-001). Tiêu đề trang
    cho Giảng viên/Admin trước đây vẫn ghi 'Tư vấn — AI (LLM)' kèm '(RAG)'
    trong subtitle — lộ tên công nghệ nội bộ. FINAL PRODUCTION GAP CLOSURE
    (Phần 21/41, 2026-09-26): đã đổi tiêu đề Giảng viên/Admin thành 'Tư vấn'
    (ngắn, không lộ thuật ngữ kỹ thuật) — cập nhật test để phản ánh ĐÚNG
    trạng thái mong muốn (trước đây test này chỉ đặc tả hành vi CŨ đã biết
    là vấn đề, không khẳng định đó là đúng)."""
    import inspect
    from dss.tabs import ai_advisor

    source = inspect.getsource(ai_advisor.ai_advisor_tab)
    assert 'role == "Sinh viên"' in source
    idx_role_check = source.find('role == "Sinh viên"')
    idx_student_title = source.find("Kế hoạch học tập của bạn")
    idx_staff_title = source.find('"Tư vấn"', idx_role_check)
    assert idx_student_title != -1 and idx_staff_title != -1
    assert idx_role_check < idx_student_title < idx_staff_title
    assert '"Tư vấn — AI (LLM)"' not in source, "Tiêu đề kỹ thuật cũ không được dùng làm tham số section_header nữa."


def test_clustering_interpretation_panel_uses_feature_label_not_raw_columns():
    """Lecturer Product Acceptance audit (2026-09): thẻ 'Diễn giải cụm' (Giảng
    viên/Admin) hiển thị thẳng tên cột kỹ thuật ("Mạnh: final_score,
    gpa_previous") thay vì nhãn thân thiện qua feature_label() -- phát hiện
    qua ảnh chụp màn hình thật, không phải chỉ đọc code."""
    import inspect
    from dss.tabs import clustering

    source = inspect.getsource(clustering.clustering_hybrid_tab)
    idx_manh = source.find('f"✅ Mạnh: {')
    idx_yeu = source.find('f"⚠️ Yếu: {')
    assert idx_manh != -1 and idx_yeu != -1
    assert "feature_label(c) for c in strengths_r" in source[idx_manh: idx_manh + 100]
    assert "feature_label(c) for c in weaknesses_r" in source[idx_yeu: idx_yeu + 100]


def test_home_student_dashboard_card_has_no_raw_shap_wording():
    """'SHAP' là thuật ngữ kỹ thuật (Section: tránh EDA/Classification/
    Regression/Clustering/SHAP/RAG/LLM trong trải nghiệm Sinh viên) — thẻ
    'Yếu tố ảnh hưởng' trên Dashboard cá nhân của Sinh viên không được nhắc
    tới tên thuật toán giải thích mô hình."""
    from dss.tabs import home

    source = inspect.getsource(home._render_student_home_dashboard)
    assert "(SHAP)" not in source
    assert "giải thích SHAP" not in source
    assert "hiển thị SHAP" not in source
    assert "Yếu tố ảnh hưởng đến điểm dự báo" in source
