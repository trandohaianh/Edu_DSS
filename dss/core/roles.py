"""Phân quyền theo vai trò (Giảng viên / Sinh viên / Admin).

Không dùng đăng nhập mật khẩu — hệ thống hiện tại chỉ chạy 1 phiên dùng chung,
nên chỉ cần một bộ chọn vai trò đơn giản để lọc giao diện. Được thiết kế sẵn
để sau này nhúng vào LMS: LMS chỉ cần mở link kèm `?role=teacher` (hoặc
student/admin) là hệ thống tự nhận đúng vai trò, không cần sửa code.
"""
import re
import streamlit as st

ROLES = ["Giảng viên / CVHT", "Sinh viên", "Admin"]
HOME_TAB_LABEL = "🏡 Trang chủ"

_LEADING_ICON_RE = re.compile(r"^\S+\s+")


TAB_SHORT_LABELS = {
    HOME_TAB_LABEL: "Trang chủ",
    "📊 Dashboard": "Dashboard",
    "🔍 Khám phá — Xử lý dữ liệu": "Khám phá dữ liệu",
    "🧪 Huấn luyện — Dự đoán": "Huấn luyện & dự đoán",
    "🔬 Phân cụm — Gợi ý": "Phân cụm & gợi ý",
    "🤖 Tư vấn — AI (LLM)": "Trợ lý AI",
    "📦 Kho dữ liệu": "Kho dữ liệu",
    "🗄️ Model Registry": "Mô hình ML",
    "📚 Quản lý tri thức (RAG)": "Tài liệu & quy chế",
    "📄 Duyệt tài liệu": "Duyệt tài liệu",
    "⚙️ Cấu hình AI": "Cấu hình AI",
    "📈 Báo cáo hệ thống": "Báo cáo & giám sát",
    "📝 Lịch sử tư vấn": "Lịch sử tư vấn",
    "🔧 Cài đặt": "Cài đặt",
    "👥 Người dùng": "Người dùng",
    "🔗 Tích hợp LMS/CMS": "Tích hợp LMS/CMS",
}

# C1.3: cùng 1 trang có thể mang tên khác theo vai trò — Sinh viên thấy MỤC TIÊU
# của mình, không phải thuật ngữ kỹ thuật; Admin không có tab "Dashboard" nên
# Trang chủ của Admin gọi là "Tổng quan". Chỉ đổi NHÃN hiển thị — khoá tab
# (TAB_ACCESS) giữ nguyên nên RBAC không đổi.
ROLE_TAB_LABELS = {
    "Sinh viên": {
        "🧪 Huấn luyện — Dự đoán": "Dự đoán kết quả",
        "🔬 Phân cụm — Gợi ý": "Nhóm học tập & gợi ý",
    },
    "Admin": {
        HOME_TAB_LABEL: "Tổng quan",
    },
}


def nav_label(tab_label: str, role: str | None = None) -> str:
    """Nhãn điều hướng theo vai trò (không emoji)."""
    role_labels = ROLE_TAB_LABELS.get(role or "", {})
    if tab_label in role_labels:
        return role_labels[tab_label]
    return display_label(tab_label)


TAB_ICONS = {
    HOME_TAB_LABEL: "🏠",
    "📊 Dashboard": "📊",
    "🔍 Khám phá — Xử lý dữ liệu": "🔍",
    "🧪 Huấn luyện — Dự đoán": "🧪",
    "🔬 Phân cụm — Gợi ý": "🔬",
    "🤖 Tư vấn — AI (LLM)": "🤖",
    "📦 Kho dữ liệu": "📦",
    "🗄️ Model Registry": "🗄️",
    "📚 Quản lý tri thức (RAG)": "📚",
    "📄 Duyệt tài liệu": "📄",
    "⚙️ Cấu hình AI": "⚙️",
    "📈 Báo cáo hệ thống": "📈",
    "📝 Lịch sử tư vấn": "📝",
    "🔧 Cài đặt": "🔧",
    "👥 Người dùng": "👥",
    "🔗 Tích hợp LMS/CMS": "🔗",
}


def display_label(tab_label: str) -> str:
    """Rút gọn nhãn tab chuẩn 1 dòng theo phong cách CodingLab, loại bỏ hoàn toàn
    từ ngữ rườm rà. Giá trị GỐC vẫn giữ nguyên làm khoá trong TAB_ACCESS/session-state
    để không ảnh hưởng tới logic nghiệp vụ toàn hệ thống."""
    if tab_label in TAB_SHORT_LABELS:
        return TAB_SHORT_LABELS[tab_label]
    return _LEADING_ICON_RE.sub("", tab_label, count=1)


def tab_icon(tab_label: str) -> str:
    """Lấy icon emoji/ký hiệu của tab."""
    return TAB_ICONS.get(tab_label, "📌")

ROLE_INFO = {
    "Giảng viên / CVHT": {
        "icon": "👩‍🏫",
        "color": "#2563eb",
        "tagline": "Theo dõi cả lớp, phát hiện rủi ro sớm",
        "desc": "Huấn luyện & so sánh mô hình dự đoán, phân cụm sinh viên, xem giải thích SHAP và quản lý toàn bộ dữ liệu/mô hình trong Kho dữ liệu.",
        "features": [
            "Dashboard tổng quan cả lớp",
            "Huấn luyện & so sánh nhiều mô hình ML",
            "Phân cụm sinh viên theo năng lực/hành vi",
            "Quản lý dataset & mô hình trong Kho dữ liệu",
        ],
    },
    "Sinh viên": {
        "icon": "🎓",
        "color": "#0d9488",
        "tagline": "Biết mình đang ở đâu, cần cải thiện gì",
        "desc": "Xem dự đoán kết quả học tập của chính mình, hiểu vì sao (SHAP), nhận gợi ý cải thiện theo cụm và kế hoạch học tập 4 tuần từ AI.",
        "features": [
            "Dự đoán điểm / mức rủi ro của riêng mình",
            "Xem mình thuộc nhóm nào trong lớp & vì sao",
            "Tư vấn AI cá nhân hóa — kế hoạch 4 tuần",
            "Định hướng nghề nghiệp theo sở thích & năng lực",
        ],
    },
    "Admin": {
        "icon": "🛠️",
        "color": "#7c3aed",
        "tagline": "Quản trị dữ liệu, vận hành hệ thống",
        "desc": "Tải, kiểm tra và quản lý toàn bộ dataset, mô hình đã huấn luyện và lịch sử hoạt động của hệ thống.",
        "features": [
            "Tải & khám phá dữ liệu thô",
            "Quản lý dataset trong Kho dữ liệu",
            "Quản lý mô hình đã huấn luyện",
            "Xem lịch sử hoạt động hệ thống",
        ],
    },
}

ROLE_ALIASES = {
    "teacher": "Giảng viên / CVHT",
    "instructor": "Giảng viên / CVHT",
    "lecturer": "Giảng viên / CVHT",
    "giảng viên": "Giảng viên / CVHT",
    "gv": "Giảng viên / CVHT",
    "student": "Sinh viên",
    "learner": "Sinh viên",
    "sinh viên": "Sinh viên",
    "sv": "Sinh viên",
    "admin": "Admin",
    "administrator": "Admin",
}

ALL_TABS = [
    HOME_TAB_LABEL,
    "📊 Dashboard",
    "🔍 Khám phá — Xử lý dữ liệu",
    "🧪 Huấn luyện — Dự đoán",
    "🔬 Phân cụm — Gợi ý",
    "🤖 Tư vấn — AI (LLM)",
    "📦 Kho dữ liệu",
    "🗄️ Model Registry",
    "📚 Quản lý tri thức (RAG)",
    "📄 Duyệt tài liệu",
    "⚙️ Cấu hình AI",
    "📈 Báo cáo hệ thống",
    "📝 Lịch sử tư vấn",
    "🔧 Cài đặt",
    "👥 Người dùng",
    "🔗 Tích hợp LMS/CMS",
    "🏛️ Onboarding Trường Đại học",
]

# Vai trò nào được thấy tab nào ở thanh điều hướng chính.
TAB_ACCESS = {
    HOME_TAB_LABEL: set(ROLES),
    # Đổi tên từ "🏠 Trang chính — Dashboard" -> "📊 Dashboard" (yêu cầu thiết
    # kế: Trang chủ và Dashboard phải là 2 route/trải nghiệm TÁCH BIỆT rõ
    # ràng, không dùng chung tên gây hiểu lầm "cùng 1 khái niệm"). Không đổi
    # tập quyền (vẫn chỉ Giảng viên).
    "📊 Dashboard": {"Giảng viên / CVHT"},
    "🔍 Khám phá — Xử lý dữ liệu": {"Giảng viên / CVHT", "Admin"},
    "🧪 Huấn luyện — Dự đoán": {"Giảng viên / CVHT", "Sinh viên"},
    "🔬 Phân cụm — Gợi ý": {"Giảng viên / CVHT", "Sinh viên"},
    # Phase 10 refactor: Trước đây CHỈ Sinh viên vào được tab này, nhưng phần lớn
    # code trong ai_advisor.py (cấu hình provider/API key, nút test kết nối, và
    # tính năng "So sánh AI") viết cho Giảng viên/Admin (`role != "Sinh viên"`)
    # — với TAB_ACCESS cũ, các phần đó là dead code không ai bấm tới được. Mở
    # thêm 2 vai trò này để code hiện có thực sự dùng được; Sinh viên vẫn thấy
    # đúng trải nghiệm đơn giản cũ (mọi phần kỹ thuật vẫn ẩn qua role != "Sinh viên").
    "🤖 Tư vấn — AI (LLM)": {"Sinh viên", "Giảng viên / CVHT", "Admin"},
    "📦 Kho dữ liệu": {"Giảng viên / CVHT", "Admin"},
    # UI redesign (mockup Admin "Báo cáo hệ thống"): CHỈ Admin — dựng hoàn toàn từ
    # dữ liệu thật đã có sẵn (list_datasets/list_models/get_history), không thêm
    # quyền hay logic nghiệp vụ mới. Xem dss/tabs/admin_reports.py.
    "📈 Báo cáo hệ thống": {"Admin"},
    # UI redesign (mockup Sinh viên "Lịch sử tư vấn"): CHỈ Sinh viên — dựng từ
    # warehouse.get_history()/save_ai_consultation() đã được gọi thật trong
    # models.py. Xem dss/tabs/consultation_history.py.
    "📝 Lịch sử tư vấn": {"Sinh viên"},
    # Phase C (rebuild UI/UX): 4 trang Admin mới, mỗi trang dựng từ dữ liệu/
    # service THẬT đã có sẵn (model_registry/knowledge_base/admin_ai_config/
    # auth_service) — không thêm logic nghiệp vụ mới, chỉ thêm điểm điều
    # hướng theo đúng cơ chế TAB_ACCESS hiện có. CHỈ Admin (đúng yêu cầu
    # "role duy nhất được xem cấu hình provider kỹ thuật" cho AI Configuration,
    # và các trang quản trị khác vốn đã Admin-only trong kiến trúc hiện tại).
    "🗄️ Model Registry": {"Admin"},
    "📚 Quản lý tri thức (RAG)": {"Admin"},
    # FINAL REMEDIATION PASS Mục 3 (2026-09): trước đây backend
    # (document_approval_service) đã hỗ trợ vai trò Giảng viên duyệt tài
    # liệu môn mình phụ trách, nhưng KHÔNG có lối vào UI nào cho vai trò này
    # (tab "Quản lý tri thức (RAG)" ở trên chỉ Admin thấy). Trang này hẹp,
    # chỉ gọi document_approval_service (không tự viết lại RBAC) — xem
    # dss/tabs/knowledge_base.py::lecturer_document_approval_tab.
    "📄 Duyệt tài liệu": {"Giảng viên / CVHT"},
    "⚙️ Cấu hình AI": {"Admin"},
    "🔧 Cài đặt": {"Admin"},
    # C1.3: tách 2 khối vốn nằm chung trong trang "Cài đặt" thành 2 trang Admin
    # riêng (Người dùng / Tích hợp LMS-CMS) — cùng dữ liệu/service thật, không
    # thêm quyền hay chức năng nghiệp vụ mới. CHỈ Admin.
    "👥 Người dùng": {"Admin"},
    "🔗 Tích hợp LMS/CMS": {"Admin"},
    # Stage 2 (University Onboarding): a NEW, cross-tenant role, deliberately
    # NOT added to ROLES (that list drives the per-tenant login role concept;
    # Platform Admin operates ACROSS tenants, logs in by real username/
    # password like any other user — see auth_service.py — just with a role
    # value that exists only in the `roles` DB table, not in this UI-only
    # constant). Because this tab is the ONLY one explicitly granted to
    # "Platform Admin", and filter_tabs_for_role() defaults an
    # unlisted-role lookup to set(ROLES) (which excludes Platform Admin by
    # construction), a Platform Admin session sees exactly this one tab and
    # nothing else — no other TAB_ACCESS entry needed changing.
    "🏛️ Onboarding Trường Đại học": {"Platform Admin"},
}


def filter_tabs_for_role(all_tabs, role):
    return [t for t in all_tabs if role in TAB_ACCESS.get(t, set(ROLES))]
