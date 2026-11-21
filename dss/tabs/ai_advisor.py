"""AI advisor tab — LLM study plans."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st

import dss.config as dss_config
from dss.config import (
    GEMINI_AVAILABLE,
    GROQ_AVAILABLE,
    OLLAMA_AVAILABLE,
    OPENAI_AVAILABLE,
    px,
)
from dss.core.data_helpers import (
    TOPIC_SCORE_COLUMNS,
    feature_label,
    is_weakness,
    topic_color,
)
from dss.core.data_helpers import (
    is_production_environment as _is_production_environment,
)
from dss.core.logging_config import get_logger
from dss.core.models import AI_MODEL_CATALOG, _check_ollama_running, ollama_base_url
from dss.services import (
    admin_ai_config,
    ai_router,
    citation_service,
    context_budget,
    llm_service,
    privacy_service,
    prompt_security,
    rag_service,
    token_tracker,
)
from dss.services import diagnosis_engine as diagnosis_engine_module
from dss.services.auth_service import require_role
from dss.services.diagnosis_engine import DiagnosisEngine
from dss.services.learning_plan import StudentLearningPlan, learning_plan_generator
from dss.services.learning_profile import StudentLearningProfile

# Lớp bảo vệ tập trung (đã có sẵn dịch vụ ở dss/services/, trước đây chưa được
# nối vào luồng tư vấn thật — chỉ ai_advisor.py gọi thẳng MultiAIProvider):
# Gateway (quota/retry/token-cost), khử PII, chống prompt injection, xác minh
# trích dẫn. Xem docs/DEAD_CODE_AUDIT.md và báo cáo refactor Phase 6 để biết lý do.
from dss.services.llm_gateway import LLMGateway as _LLMGateway
from dss.services.model_service import (
    compute_lecturer_dashboard_overview,
    compute_progress_note,
    predict_for_student,
)
from dss.services.rag_namespaces import NAMESPACE_STUDENT_LEARNING

# Phase 2 refactor: logic thuần (không UI) chuyển sang services/report_service.py
# — giữ alias tên cũ để không phải sửa các lời gọi bên dưới trong cùng phase.
from dss.services.report_service import build_demo_study_plan as _build_demo_study_plan
from dss.tabs import ui_kit

_logger = get_logger(__name__)


_SUGGESTED_QUESTIONS_LECTURER = [
    "Những sinh viên nào đang có nguy cơ cao?",
    "Yếu tố nào ảnh hưởng nhiều nhất đến kết quả học tập?",
    "Tôi nên can thiệp như thế nào?",
    "Gợi ý kế hoạch hỗ trợ nhóm sinh viên này.",
]
_SUGGESTED_QUESTIONS_STUDENT = [
    "Tại sao GPA dự báo của tôi giảm?",
    "Tôi nên cải thiện môn nào trước?",
    "Lập kế hoạch học tập cho tôi.",
    "Điểm yếu lớn nhất của tôi là gì?",
]


def _week_plan_from_structured_plan(plan: StudentLearningPlan, weeks: int = 4) -> list:
    """Audit 2026-09-15 (Issue FUNC-PLAN-001): chuyển `StudentLearningPlan` THẬT
    (learning_plan_generator.generate_plan — có chẩn đoán/liều lượng/bằng chứng
    tính từ đúng hồ sơ sinh viên) thành đúng hình dạng `week_plan` mà checklist/
    lưu/xuất file đã dùng từ trước (`[{"week","topic","action","done"}]`) — để
    KHÔNG phải viết lại toàn bộ luồng chat/RAG/Gateway đang chạy tốt, chỉ thay
    NGUỒN dữ liệu cấu trúc từ heuristic demo sang bản có căn cứ/truy vết được.
    KHÔNG bịa dữ liệu: nếu plan không có priority_topics/activities, dùng đúng
    danh sách weaknesses/mặc định trung lập đã có sẵn trong plan đó."""
    topics = plan.priority_topics or plan.weaknesses or ["Ôn tập tổng hợp theo chẩn đoán hiện tại"]
    result = []
    for i in range(1, weeks + 1):
        topic = topics[(i - 1) % len(topics)]
        if plan.activities:
            act = plan.activities[(i - 1) % len(plan.activities)]
            schedule = (
                f"{act.frequency_per_week} lần/tuần, {act.duration_minutes} phút/lần"
                if act.frequency_per_week is not None and act.duration_minutes is not None
                else "Thời lượng và lịch học cần được xác nhận thêm"
            )
            action = f"{act.method} ({schedule}). Lý do: {act.reason}. Kỳ vọng: {act.expected_outcome}"
        else:
            action = f"Ôn tập chủ đề: {topic}"
        result.append({"week": i, "topic": topic, "action": action, "done": False})
    return result


def _render_weekly_reminder_checklist(week_plan, current_student_id):
    """Checklist nhắc nhở học tập theo tuần — luôn dựng từ `week_plan` tính CỤC BỘ
    (không phụ thuộc kết quả LLM), nên hoạt động 100% offline. Trạng thái tích chỉ
    lưu trong session hiện tại (chưa gắn tài khoản lâu dài) — đủ dùng cho phạm vi
    đồ án, không phải giới hạn kỹ thuật nghiêm trọng vì mỗi phiên làm việc của
    Sinh viên thường liền mạch."""
    if not week_plan:
        return
    st.markdown("#### Nhắc nhở học tập theo tuần")
    st.caption("Tự đánh dấu khi hoàn thành — giúp bạn không bỏ sót việc cần làm mỗi tuần.")
    sid = current_student_id or "guest"
    today_week_idx = int(datetime.now().strftime("%U")) % max(len(week_plan), 1)
    for idx, wp in enumerate(week_plan):
        done_key = f"reminder_done_{sid}_{wp['week']}"
        is_current = idx == today_week_idx
        label = f"{'👉 ' if is_current else ''}Tuần {wp['week']}" + (f" — {wp['topic']}" if wp.get('topic') else "")
        st.checkbox(label, key=done_key, value=st.session_state.get(done_key, False))


# ---------------------------------------------------------------------------
# RBAC 3 cấp cho tab Tư vấn AI (mục 2/3 bản yêu cầu refactor):
#   - Sinh viên : chỉ dùng AI Learning Assistant, 1 provider mặc định tự động,
#                 KHÔNG thấy cấu hình kỹ thuật/provider/API key/Compare AI.
#   - Giảng viên: dùng AI Teaching Assistant + Compare AI, chọn được provider
#                 trong số đã sẵn sàng, nhưng KHÔNG xem/sửa API key/secrets.
#   - Admin     : toàn quyền — quản lý provider, API key/secrets, test kết nối,
#                 đặt provider/model mặc định hệ thống, và Compare AI.
# Mỗi hàm nhạy cảm bên dưới đều được bọc `@require_role(...)` — kiểm tra
# `st.session_state["_auth_role"]` của CHÍNH phiên đang chạy, độc lập với biến
# `role` được truyền qua tham số — nên đây là chặn quyền ở TẦNG HÀM, không chỉ
# ẩn nút trên UI (dù lỡ 1 nhánh UI nào đó gọi nhầm, hàm vẫn tự chặn).
# ---------------------------------------------------------------------------
def _list_ready_cloud_providers(llm_integration, available_map):
    """Danh sách (provider_key, label) các provider ĐÃ SẴN SÀNG dùng ngay (đã
    cấu hình API key qua secrets/env, hoặc chạy local) — dùng chung cho cả bộ
    chọn provider của Giảng viên lẫn danh sách ứng viên Compare AI. KHÔNG bao
    giờ trả về hay hiển thị giá trị key thật, chỉ trả về provider_key/label."""
    candidates = []
    for _prov_key, _prov_label in [
        ("gemini", "Google Gemini"),
        ("groq", "Groq (Siêu tốc)"),
        ("openai", "OpenAI (ChatGPT)"),
    ]:
        if available_map.get(_prov_label, False) and llm_integration.get_api_key_from_secrets(_prov_key):
            candidates.append((_prov_key, _prov_label))
    if _check_ollama_running():
        candidates.append(("ollama", "Ollama (Local)"))
    # Chỉ coi là "sẵn sàng" khi quản trị viên bật rõ (dss_config.local_hf_enabled) — chỉ
    # cài transformers thôi không đủ, tránh tự tải mô hình ~15 GB khi chưa có khoá API.
    if dss_config.HF_AVAILABLE and dss_config.local_hf_enabled():
        candidates.append(("huggingface", "Hugging Face (Local/Cloud)"))
    return candidates


@require_role("Admin")
def _render_admin_provider_config(llm_integration, all_labels, available_map):
    """Cấu hình provider ĐẦY ĐỦ — chỉ Admin: chọn bất kỳ provider nào (kể cả
    chưa sẵn sàng, để nhập key mới), xem/nhập API key, và đặt làm mặc định hệ
    thống. Bị chặn ở tầng hàm (@require_role) — không chỉ do UI không hiện nút."""
    st.markdown("#### Cấu hình nguồn AI (Admin)")

    llm_type = st.radio("Chọn nền tảng AI:", all_labels, horizontal=True, key="llm_type")
    if not available_map.get(llm_type, False):
        st.warning(
            f"Provider **{llm_type}** hiện chưa sẵn sàng trên máy này. Bạn có thể chuyển sang provider có trạng thái **Sẵn sàng** hoặc dùng Demo mode."
        )

    provider_map = {
        "Hugging Face (Local/Cloud)": "huggingface",
        "Google Gemini": "gemini",
        "Groq (Siêu tốc)": "groq",
        "Ollama (Local)": "ollama",
        "OpenAI (ChatGPT)": "openai",
    }
    selected_provider = provider_map.get(llm_type, "huggingface")

    model_name_input = ""
    api_key_input = ""
    hf_token_input = ""
    embedding_model_name = "sentence-transformers/all-MiniLM-L6-v2"
    use_embedding = st.checkbox("Sử dụng tài liệu học tập (RAG)", value=True, key="use_embedding")

    st.markdown("##### Thông số kết nối")
    col_param1, col_param2 = st.columns(2)

    with col_param1:
        if selected_provider == "huggingface":
            model_name_input = st.selectbox(
                "Mô hình Hugging Face:", AI_MODEL_CATALOG["huggingface"], key="hf_model_sel"
            )
            api_key_input = st.text_input(
                "Hugging Face Token (Tùy chọn/Cho model Private):", type="password", key="hf_token_input"
            )
            hf_token_input = api_key_input
        elif selected_provider == "gemini":
            gem_options = AI_MODEL_CATALOG["gemini"] + ["Tùy chỉnh (Nhập model khác)..."]
            gem_sel = st.selectbox(
                "Mô hình Gemini:",
                gem_options,
                key="gemini_model_sel",
                help="Nếu model đã chọn bị hãng khai tử/đổi tên, hệ thống tự thử các model khác trong danh sách này khi gọi API.",
            )
            if gem_sel == "Tùy chỉnh (Nhập model khác)...":
                model_name_input = st.text_input(
                    "Nhập tên model Gemini:", value="gemini-2.0-flash", key="gemini_custom_input"
                )
            else:
                model_name_input = gem_sel
            api_key_input = st.text_input(
                "Gemini API Key (để trống nếu đã đặt trong secrets/env):", type="password", key="gemini_key_input"
            )
        elif selected_provider == "groq":
            groq_options = AI_MODEL_CATALOG["groq"] + ["Tùy chỉnh (Nhập model khác)..."]
            groq_sel = st.selectbox(
                "Mô hình Groq:",
                groq_options,
                key="groq_model_sel",
                help="Nếu model đã chọn bị hãng khai tử/đổi tên, hệ thống tự thử các model khác trong danh sách này khi gọi API.",
            )
            if groq_sel == "Tùy chỉnh (Nhập model khác)...":
                model_name_input = st.text_input(
                    "Nhập tên model Groq:", value="llama-3.3-70b-versatile", key="groq_custom_input"
                )
            else:
                model_name_input = groq_sel
            api_key_input = st.text_input("Groq API Key:", type="password", key="groq_key_input")
        elif selected_provider == "ollama":
            model_name_input = st.text_input(
                "Tên mô hình Ollama (VD: qwen2.5:7b, llama3.2):",
                value=AI_MODEL_CATALOG["ollama"][0],
                key="ollama_model_input",
            )
            api_key_input = st.text_input("Ollama Base URL:", value=ollama_base_url(), key="ollama_url_input")
            if _check_ollama_running(api_key_input or ollama_base_url()):
                st.caption("✅ Đã phát hiện Ollama đang chạy tại địa chỉ này.")
            else:
                st.caption("⚠️ Chưa phát hiện Ollama chạy tại địa chỉ này — kiểm tra lại đã khởi động Ollama chưa.")
        elif selected_provider == "openai":
            openai_options = AI_MODEL_CATALOG["openai"] + ["Tùy chỉnh (Nhập model khác)..."]
            openai_sel = st.selectbox(
                "Mô hình OpenAI:",
                openai_options,
                key="openai_model_sel",
                help="Nếu model đã chọn bị hãng khai tử/đổi tên, hệ thống tự thử các model khác trong danh sách này khi gọi API.",
            )
            if openai_sel == "Tùy chỉnh (Nhập model khác)...":
                model_name_input = st.text_input(
                    "Nhập tên model OpenAI:", value="gpt-4o-mini", key="openai_custom_input"
                )
            else:
                model_name_input = openai_sel
            api_key_input = st.text_input(
                "OpenAI API Key (để trống nếu đã đặt trong secrets/env):", type="password", key="openai_key_input"
            )

    with col_param2:
        if use_embedding:
            embedding_model_name = st.selectbox(
                "Mô hình Tìm kiếm (Embedding):",
                ["sentence-transformers/all-MiniLM-L6-v2", "BAAI/bge-base-en-v1.5"],
                key="embed_model_sel",
            )
            use_warehouse_data = st.checkbox("Sử dụng lịch sử từ Kho dữ liệu", value=True, key="use_wh_data")
        else:
            use_warehouse_data = False
            st.info(
                "💡 Bật tính năng 'Sử dụng tài liệu học tập (RAG)' để AI đưa ra lời khuyên chính xác dựa trên tài liệu."
            )

    _current_default = admin_ai_config.get_default_provider()
    _is_current_default = (
        bool(_current_default)
        and _current_default["provider_key"] == selected_provider
        and _current_default["model_name"] == model_name_input
    )
    col_def1, col_def2 = st.columns([1, 1])
    with col_def1:
        if _is_current_default:
            st.caption(f"⭐ Đây đang là mặc định hệ thống (`{selected_provider}` / `{model_name_input}`).")
        elif st.button("⭐ Đặt làm mặc định hệ thống", key="set_default_provider_btn"):
            admin_ai_config.set_default_provider(selected_provider, model_name_input)
            st.success(f"✅ Đã đặt `{selected_provider}` / `{model_name_input}` làm mặc định cho Giảng viên/Sinh viên.")
            st.rerun()
    with col_def2:
        if _current_default and st.button("↩️ Xoá mặc định (quay lại tự động)", key="clear_default_provider_btn"):
            admin_ai_config.clear_default_provider()
            st.success("✅ Đã xoá mặc định hệ thống — quay lại tự động dò provider.")
            st.rerun()

    return {
        "llm_type": llm_type,
        "selected_provider": selected_provider,
        "model_name_input": model_name_input,
        "api_key_input": api_key_input,
        "hf_token_input": hf_token_input,
        "embedding_model_name": embedding_model_name,
        "use_embedding": use_embedding,
        "use_warehouse_data": use_warehouse_data,
    }


@require_role("Giảng viên / CVHT", "Admin")
def _render_teacher_provider_picker(llm_integration, available_map):
    """Bộ chọn provider RÚT GỌN cho Giảng viên — chỉ chọn trong số provider ĐÃ
    SẴN SÀNG (đã có key qua secrets/env, hoặc chạy local), KHÔNG có ô nhập API
    key nào (không xem/sửa được secrets). Ưu tiên mặc định hệ thống do Admin đặt
    (`admin_ai_config`) nếu provider đó vẫn sẵn sàng."""
    st.markdown("#### Chọn nguồn AI")
    ready = _list_ready_cloud_providers(llm_integration, available_map)
    label_map = {
        "huggingface": "Hugging Face (Local/Cloud)",
        "gemini": "Google Gemini",
        "groq": "Groq (Siêu tốc)",
        "ollama": "Ollama (Local)",
        "openai": "OpenAI (ChatGPT)",
    }

    if not ready:
        st.warning(
            "Hiện chưa có provider AI nào sẵn sàng (Admin chưa cấu hình API key/secrets). Hệ thống sẽ dùng **Demo mode**."
        )
        return {
            "llm_type": "none",
            "selected_provider": "none",
            "model_name_input": "",
            "api_key_input": "",
            "hf_token_input": "",
            "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
            "use_embedding": True,
            "use_warehouse_data": True,
        }

    default_cfg = admin_ai_config.get_default_provider()
    default_idx = 0
    if default_cfg:
        for i, (key, _lbl) in enumerate(ready):
            if key == default_cfg["provider_key"]:
                default_idx = i
                break

    labels = [lbl for _, lbl in ready]
    picked_label = st.selectbox(
        "Nền tảng AI (đã cấu hình sẵn bởi Admin):", labels, index=default_idx, key="teacher_provider_pick"
    )
    picked_key = dict((lbl, key) for key, lbl in ready)[picked_label]

    model_options = AI_MODEL_CATALOG[picked_key]
    model_default_idx = 0
    if default_cfg and default_cfg["provider_key"] == picked_key and default_cfg["model_name"] in model_options:
        model_default_idx = model_options.index(default_cfg["model_name"])
    model_name_input = (
        st.selectbox("Model:", model_options, index=model_default_idx, key="teacher_model_pick")
        if picked_key != "ollama"
        else model_options[0]
    )

    use_embedding = st.checkbox("Sử dụng tài liệu học tập (RAG)", value=True, key="use_embedding")
    if use_embedding:
        embedding_model_name = st.selectbox(
            "Mô hình Tìm kiếm (Embedding):",
            ["sentence-transformers/all-MiniLM-L6-v2", "BAAI/bge-base-en-v1.5"],
            key="embed_model_sel",
        )
    else:
        embedding_model_name = "sentence-transformers/all-MiniLM-L6-v2"
    # "Lịch sử từ Kho dữ liệu" (kết quả huấn luyện/đánh giá mô hình) là nội dung
    # thuộc namespace admin_operations (xem dss/services/rag_namespaces.py) —
    # Giảng viên chỉ được cấp student_learning + lecturer_support, KHÔNG được
    # đọc dữ liệu vận hành hệ thống, nên không có tuỳ chọn bật ở đây nữa.
    use_warehouse_data = False

    return {
        "llm_type": label_map[picked_key],
        "selected_provider": picked_key,
        "model_name_input": model_name_input,
        # KHÔNG có ô nhập key — luôn rỗng, tự resolve từ secrets ở nơi gọi.
        "api_key_input": "",
        "hf_token_input": "",
        "embedding_model_name": embedding_model_name,
        "use_embedding": use_embedding,
        "use_warehouse_data": use_warehouse_data,
    }


@require_role("Admin")
def _run_connection_test(
    llm_integration, selected_provider, model_name_input, resolved_api_key, api_key_input, llm_type
):
    """Kiểm tra kết nối provider — CHỈ Admin (chặn ở tầng hàm), vì hành động này
    cần dùng API key thật để gọi thử, và chỉ Admin mới được thấy/nhập key."""
    with st.spinner("Đang kiểm tra kết nối..."):
        test_prompt = "Say 'OK' if you receive this message."
        if selected_provider in ("gemini", "groq", "openai"):
            kwargs = {"api_key": resolved_api_key}
        elif selected_provider == "huggingface":
            kwargs = {"hf_token": api_key_input}
        else:
            kwargs = {"base_url": api_key_input}
        stream = llm_integration.call_ai_provider(
            test_prompt, provider=selected_provider, model_name=model_name_input, **kwargs
        )
        test_res = "".join(stream)
        err_prefix = ("Lỗi", "Provider không khả dụng")
        if test_res.strip() and not test_res.strip().startswith(err_prefix):
            st.success(f"✅ Kết nối {llm_type} thành công!")
        else:
            st.error(f"❌ Kết nối thất bại: {test_res or '(rỗng)'}")


@require_role("Giảng viên / CVHT", "Admin")
def _run_compare_ai(
    llm_integration,
    specs,
    weaknesses_llm,
    predicted_gpa_llm,
    student_profile,
    runtime_rag_documents,
    role="Giảng viên / CVHT",
):
    """Chạy So sánh AI đồng thời nhiều provider — CHỈ Giảng viên/Admin (chặn ở
    tầng hàm), Sinh viên không có khái niệm "so sánh provider".

    NHÓM F remediation pass (đợt 2): `role` được chuyển xuống
    `llm_service.compare_providers` -> `generate_personalized_advice` để RAG
    trích dẫn qua `retrieve_unified_context` lọc namespace đúng theo vai trò
    thật (trước đây "So sánh AI" đi qua đường RAG cũ, không lọc quản trị)."""
    with st.spinner(
        f"Đang gọi đồng thời {len(specs)} provider (tối đa {dss_config.MAX_CONCURRENT_REQUESTS} luồng cùng lúc)..."
    ):
        compare_results = llm_service.compare_providers(
            llm_integration,
            specs,
            student_weaknesses=weaknesses_llm,
            predicted_gpa=predicted_gpa_llm,
            student_profile=student_profile,
            runtime_documents=runtime_rag_documents,
            use_rag=True,
            use_warehouse_data=True,
            role=role,
        )
    tabs_cmp = st.tabs([f"{r.provider_label} ({r.elapsed_seconds:.1f}s)" for r in compare_results])
    for tab, res in zip(tabs_cmp, compare_results):
        with tab:
            st.caption(f"Model: `{res.model_name}`")
            if res.error:
                st.error(res.error)
            else:
                st.markdown(res.text)


def ai_advisor_tab(df, llm_integration, role=None, current_student_id=None, wh=None):
    """AI advisor tab using LLM."""
    from dss.services import engine_gateway

    if engine_gateway.enabled():
        from dss.tabs.engine_advisor import engine_advisor_tab

        return engine_advisor_tab(llm_integration=llm_integration)

    ui_kit.render_synthetic_data_banner(df)  # E-1: cảnh báo rõ khi đang xem dữ liệu mô phỏng
    # Student Product Acceptance audit (2026-09): nhãn điều hướng (sub-tab
    # radio ở main.py) đã đổi thành "Kế hoạch học tập" cho Sinh viên từ trước,
    # nhưng tiêu đề THẬT của trang (section_header ở đây) từng ghi tên công
    # nghệ nội bộ đầy đủ, không khớp nhãn điều hướng mà người dùng vừa bấm
    # vào — đã sửa ở nhánh else bên dưới (FINAL PRODUCTION GAP CLOSURE Phần 21/41).
    if role == "Sinh viên":
        ui_kit.section_header(
            "Kế hoạch học tập của bạn",
            subtitle="Kế hoạch học tập cá nhân hóa, dựa trên dự đoán và tài liệu tham khảo đã được kiểm chứng.",
        )
    else:
        # FINAL PRODUCTION GAP CLOSURE (Phần 21/41): bỏ "(LLM)"/"(RAG)" khỏi
        # tiêu đề/mô tả — tên công nghệ nội bộ, không cần thiết cho người
        # dùng (Giảng viên/Admin vẫn hiểu "Tư vấn" là tính năng AI mà không
        # cần thấy thuật ngữ kỹ thuật ngay tiêu đề trang).
        ui_kit.section_header(
            "Tư vấn",
            subtitle="Kế hoạch học tập cá nhân hóa, dựa trên dự đoán và tài liệu tham khảo.",
        )

    # PERF-001: KHÔNG import thật torch/transformers/sentence-transformers (~9-20s) chỉ để
    # hiển thị danh sách provider — dss_config.HF_AVAILABLE (find_spec, gần như miễn phí) đã
    # đủ để biết gói CÓ CÀI hay không cho mục đích liệt kê lựa chọn ở đây. Import thật chỉ
    # thực sự cần khi người dùng BẤM dùng provider Hugging Face (Local), lúc đó
    # call_ai_provider()/load_embedding_model() đã tự gọi _ensure_local_llm_libs().

    # Structured plans/history do not depend on provider readiness or a GPA column.
    from dss.tabs.learning_plan_workspace import course_id_from_record, render_learning_plan_workspace

    render_learning_plan_workspace(df)
    if df is None or df.empty:
        return
    if role == "Sinh viên":
        # History remains readable without a usable prediction dataset.
        from dss.services.auth_service import current_user

        identity = current_user() or {}
        id_column = next((c for c in ("student_id", "id", "Student ID", "ID") if c in df.columns), None)
        own_id = identity.get("student_id")
        if not id_column or not own_id or not (df[id_column].astype(str) == str(own_id)).any():
            return
        prediction_columns = [
            c
            for c in df.select_dtypes(include=[np.number]).columns
            if "id" not in str(c).lower() and "pca" not in str(c).lower() and "cluster" not in str(c).lower()
        ]
        if not prediction_columns:
            return

    available_map = {
        "Hugging Face (Local/Cloud)": dss_config.HF_AVAILABLE,
        "Google Gemini": GEMINI_AVAILABLE,
        "Groq (Siêu tốc)": GROQ_AVAILABLE,
        "Ollama (Local)": OLLAMA_AVAILABLE,
        "OpenAI (ChatGPT)": OPENAI_AVAILABLE,
    }
    enabled_labels = [k for k, ok in available_map.items() if ok]
    all_labels = list(available_map.keys())

    # RBAC 3 cấp (allowlist, không phải denylist "!= Sinh viên" — an toàn hơn nếu
    # có role lạ nào đó xuất hiện, mặc định KHÔNG được coi là staff).
    is_admin = role == "Admin"
    is_staff = role in ("Giảng viên / CVHT", "Admin")

    if is_staff:
        # Bảng trạng thái kỹ thuật (tên các provider AI, cài đặt hay chưa) chỉ có
        # ý nghĩa với người quản trị/Giảng viên đang cấu hình hệ thống — với Sinh
        # viên đây toàn thuật ngữ khó hiểu (Hugging Face/Gemini/Groq/Ollama...)
        # không giúp ích gì cho việc dùng tính năng, nên ẩn hẳn.
        if not enabled_labels:
            st.warning("Hiện chưa có provider AI khả dụng. Bạn vẫn có thể dùng **Demo mode** (không cần API) bên dưới.")

        with st.expander("Trạng thái hệ thống AI/RAG", expanded=False):
            # SINGLE SOURCE OF TRUTH (UI/RAG consistency pass): trước đây bảng này tự
            # suy ra "Sẵn sàng" chỉ từ *_AVAILABLE (nghĩa thật: "có cấu hình/cài đặt
            # thư viện hay không"), khác hẳn "Cấu hình AI" (trang test provider) —
            # nơi DUY NHẤT thực sự gọi 1 request thật để biết provider có hoạt động
            # hay không (`llm_gateway.check_provider_health`). Hai bảng vì vậy có thể
            # mâu thuẫn nhau (vd. OpenAI hết hạn mức thanh toán vẫn hiện "Sẵn sàng" ở
            # đây trong khi trang test báo BILLING_REQUIRED). Sửa: đọc lại ĐÚNG kết
            # quả đã cache từ lần bấm "Kiểm tra kết nối" ở trang Cấu hình AI (cùng 1
            # session_state key `_admin_ai_health_{pkey}`) thay vì tự suy đoán riêng —
            # nếu Admin chưa từng bấm kiểm tra, hiện thật "Chưa kiểm tra", KHÔNG bịa
            # "Sẵn sàng" chỉ vì có key.
            from dss.services import llm_gateway as _llm_gateway_status

            def _cached_health_label(pkey: str, configured: bool) -> str:
                cached = st.session_state.get(f"_admin_ai_health_{pkey}")
                if cached:
                    category = cached.get("category", _llm_gateway_status.HEALTH_UNKNOWN_ERROR)
                    return _llm_gateway_status.PROVIDER_HEALTH_FRIENDLY_LABEL.get(category, category)
                return "Chưa kiểm tra" if configured else "Chưa cấu hình"

            st.caption(
                "Trạng thái dưới đây dùng chung kết quả với trang **Cấu hình AI** "
                "(nhấn \"Kiểm tra kết nối\" ở đó để làm mới) — không tự suy đoán riêng."
            )
            cst2, cst3, cst4, cst5 = st.columns(4)
            cst2.metric("Gemini", _cached_health_label("gemini", GEMINI_AVAILABLE))
            cst3.metric("Groq", _cached_health_label("groq", GROQ_AVAILABLE))
            # Ollama không đi qua check_provider_health cache (kiểm tra local-process,
            # không phải API key) — giữ nguyên kiểm tra "đang chạy" trực tiếp, đây là
            # tín hiệu thật, không phải suy đoán từ cấu hình.
            cst4.metric("Ollama", "Đang chạy" if (OLLAMA_AVAILABLE and _check_ollama_running()) else "Chưa chạy")
            cst5.metric("OpenAI", _cached_health_label("openai", OPENAI_AVAILABLE))

            st.markdown("<div style='height:0.4rem;'></div>", unsafe_allow_html=True)
            st.caption(
                "**Mô hình nhúng (Embedding)** — vai trò khác hẳn LLM: dùng để chuyển "
                "nội dung tài liệu/câu hỏi thành vector phục vụ tìm kiếm ngữ nghĩa (RAG), "
                "không sinh câu trả lời. Sẵn sàng/chưa sẵn sàng của mục này KHÔNG đồng "
                "nghĩa với việc LLM có hoạt động hay không."
            )
            st.metric("Hugging Face (thư viện embedding)", "Sẵn sàng" if dss_config.HF_AVAILABLE else "Chưa cài")

    # --- Chọn sinh viên ---
    st.markdown("##### Chọn sinh viên")

    # Tìm cột ID sinh viên
    student_id_col = None
    for col in ['student_id', 'id', 'student_name', 'name', 'Student ID', 'ID']:
        if col in df.columns:
            student_id_col = col
            break

    if student_id_col is None:
        st.warning("⚠️ Không tìm thấy cột ID sinh viên. Hệ thống sẽ sử dụng hàng đầu tiên.")
        student_id_llm = "Student_1"
    elif role == "Sinh viên":
        # Sinh viên không được chọn tư vấn cho bạn học khác — luôn cố định
        # về đúng mã số của chính mình, không hiện selectbox.
        student_id_llm = current_student_id
        st.info(f"👤 Đang tư vấn cho: **{student_id_llm}**")
    else:
        student_id_llm = st.selectbox(
            "Chọn Sinh viên để tư vấn:", df[student_id_col].unique(), key="llm_student_select"
        )

    if not student_id_llm:
        return

    # --- Phân tích điểm yếu & hồ sơ rủi ro (tính toán thuần, KHÔNG render ở đây —
    # phần hiển thị được gộp thành 2 cột NGỮ CẢNH/RỦI RO bên dưới sau khi mọi giá
    # trị cần thiết đã sẵn sàng, để khớp bố cục mockup: trái = phân tích, phải =
    # thẻ rủi ro/yếu tố chính). Logic tính toán giữ nguyên 100% so với bản gốc.

    # *** FIX LỖI LOGIC: Lấy đúng dữ liệu sinh viên ***
    try:  # Lấy dòng dữ liệu của sinh viên đã chọn
        if student_id_col:
            student_data_llm_row = df[df[student_id_col] == student_id_llm].iloc[0]
        else:
            student_data_llm_row = df.iloc[0]
        # Filter student_data_llm_row to only include relevant numeric and
        # categorical features for the prompt
        relevant_cols = [
            col
            for col in df.columns
            if 'id' not in col.lower() and 'pca' not in col.lower() and 'cluster' not in col.lower()
        ]
    except (IndexError, KeyError):
        st.error("Không tìm thấy dữ liệu cho sinh viên đã chọn.")
        return

    student_data_llm_filtered = student_data_llm_row[relevant_cols].to_dict()

    # Xác định điểm GPA/Score (để truyền cho LLM) — dò các tên cột điểm phổ biến
    # (giống logic ở tab Dashboard) thay vì chỉ 2 tên cố định, để hoạt động được
    # với dữ liệu tùy ý người dùng tải lên, không chỉ dữ liệu mẫu tiếng Việt.
    gpa_col_llm = None
    for _cand in ['diem_ky_sau', 'diem_ky_nay', 'final_score', 'gpa_previous', 'gpa', 'score', 'total_score']:
        if _cand in df.columns and pd.api.types.is_numeric_dtype(df[_cand]):
            gpa_col_llm = _cand
            break
    if gpa_col_llm is None:
        _numeric_gpa_candidates = [
            c
            for c in df.select_dtypes(include=[np.number]).columns
            if 'id' not in c.lower() and 'pca' not in c.lower() and 'cluster' not in c.lower()
        ]
        if not _numeric_gpa_candidates:
            st.error("Không tìm thấy cột số nào trong dữ liệu để làm căn cứ tư vấn. Vui lòng kiểm tra lại dữ liệu.")
            return
        gpa_col_llm = st.selectbox(
            "Không tự nhận diện được cột điểm/GPA — chọn cột đại diện cho kết quả học tập:",
            _numeric_gpa_candidates,
            key="llm_gpa_col_manual",
        )
    # K-3: "Điểm dự đoán" PHẢI đến từ mô hình Production (nếu có) — KHÔNG đọc
    # thẳng cột dữ liệu (có thể chính là target thật, vd. diem_ky_sau) rồi gọi
    # đó là "dự đoán". predict_for_student() tự tra Model Registry, chỉ trả
    # source="model" khi thật sự đã chạy qua pipeline.predict().
    _prediction_info = predict_for_student(
        wh, st.session_state.get("current_dataset_id"), gpa_col_llm, student_data_llm_row
    )
    predicted_gpa_llm = _prediction_info["value"]
    predicted_gpa_source = _prediction_info["source"]
    if predicted_gpa_llm is None:
        st.info(
            "Chưa có điểm hiện tại hay mô hình dự báo cho sinh viên này, nên chưa thể đánh giá mức rủi ro "
            "hay tư vấn dựa trên điểm. Hãy nhập điểm (hoặc huấn luyện mô hình dự báo) rồi quay lại."
        )
        return
    predicted_gpa_model_name = _prediction_info.get("model_name")
    predicted_gpa_model_version = _prediction_info.get("version")
    if predicted_gpa_source == "model":
        predicted_gpa_label = f"Dự đoán ({predicted_gpa_model_name} v{predicted_gpa_model_version})"
    else:
        predicted_gpa_label = "Điểm hiện tại (chưa có dự báo)"

    # === HỒ SƠ HỌC TẬP VÀ CHẨN ĐOÁN ĐA CHIỀU (Section 5, 6, 7) ===
    # Loại bỏ việc chỉ dựa vào student_score < 0.9 * class_average làm căn cứ cá nhân hoá duy nhất.
    numeric_features = df.select_dtypes(include=[np.number]).columns.tolist()
    actionable_numeric_features = [
        col
        for col in numeric_features
        if 'id' not in col.lower() and 'pca' not in col.lower() and 'cluster' not in col.lower() and col != gpa_col_llm
    ]
    avg_scores_llm = df[actionable_numeric_features].mean()

    lms_raw_dict = (
        student_data_llm_row.to_dict() if hasattr(student_data_llm_row, "to_dict") else dict(student_data_llm_row)
    )
    learning_prof = StudentLearningProfile.build_from_lms_records(
        student_id=str(student_id_llm),
        course_id=course_id_from_record(lms_raw_dict),
        raw_lms_data=lms_raw_dict,
        class_averages=avg_scores_llm.to_dict() if hasattr(avg_scores_llm, "to_dict") else dict(avg_scores_llm),
    )
    structured_diagnoses = DiagnosisEngine().diagnose_student(learning_prof)

    weaknesses_llm = []
    _weakness_gaps = []  # (col, gap) song song với weaknesses_llm — dùng để sắp xếp độ ưu tiên

    # 1. Bổ sung chẩn đoán suy luận có cấu trúc (Knowledge Gap, Low Practice, v.v.) —
    # CHỈ đưa vào danh sách "điểm yếu" các chẩn đoán THỰC SỰ là vấn đề; chẩn đoán
    # "tiến độ ổn định" (MASTERY_ON_TRACK) không phải điểm yếu, đưa vào đây sẽ hiện
    # nhầm dưới panel "Phân tích điểm yếu". Nhãn hiển thị luôn qua category_label()
    # — tuyệt đối không để lộ enum kỹ thuật (vd. "MASTERY_ON_TRACK") ra UI/prompt AI.
    for diag in structured_diagnoses:
        top_hyp = diag.hypotheses[0] if diag.hypotheses else None
        cat = top_hyp.category if top_hyp else None
        if cat in (
            diagnosis_engine_module.CATEGORY_MASTERY_ON_TRACK,
            diagnosis_engine_module.CATEGORY_INSUFFICIENT_DATA,
        ):
            continue
        cat_label = diagnosis_engine_module.category_label(cat)
        weaknesses_llm.append(f"**{cat_label}** — {diag.issue}: *{'; '.join(diag.evidence)}*")
        _weakness_gaps.append(-2.0)  # ưu tiên cao nhất

    # 2. Bổ sung các chỉ số học thuật tụt hậu so với ngưỡng đạt hoặc trung bình lớp
    # A-4: is_weakness() chỉ áp dụng cho cột đã khai báo chiều tốt/xấu
    # (WEAKNESS_DETECTION_DIRECTIONS) — loại trừ bí danh/target và cột mà giá
    # trị THẤP mới là TỐT (vd. ngay_hoat_dong_gan_nhat), tránh gắn nhầm "điểm
    # yếu" cho sinh viên đang thực sự tốt hơn trung bình lớp ở chỉ số đó.
    for col in actionable_numeric_features:
        col_val = float(student_data_llm_row[col])
        avg_val = float(avg_scores_llm[col])
        gap = col_val - avg_val
        if is_weakness(col, col_val, avg_val):
            weaknesses_llm.append(f"**{feature_label(col)}** (SV: **{col_val:.2f}**, TB lớp: **{avg_val:.2f}**)")
            _weakness_gaps.append(gap)

    # Sắp xếp điểm yếu theo mức độ nghiêm trọng (lệch âm nhiều nhất trước)
    if _weakness_gaps:
        weaknesses_llm = [w for _, w in sorted(zip(_weakness_gaps, weaknesses_llm), key=lambda p: p[0])]

    # --- Dữ liệu chẩn đoán lỗ hổng kiến thức THEO CHỦ ĐỀ (nếu dữ liệu có) ---
    _topic_cols_present = [c for c in TOPIC_SCORE_COLUMNS if c in df.columns and c in student_data_llm_row.index]
    _topic_labels, _topic_scores, _topic_colors, _weak_topic_labels = [], [], [], []
    _topic_class_avg, _topic_gap, _topic_status = [], [], []
    if _topic_cols_present:
        _topic_labels = [TOPIC_SCORE_COLUMNS[c] for c in _topic_cols_present]
        _topic_scores = [float(student_data_llm_row[c]) for c in _topic_cols_present]
        # Mỗi môn/chủ đề 1 màu CỐ ĐỊNH theo TÊN (topic_color) — không còn mã màu theo
        # ngưỡng đạt/chưa đạt (đỏ/xanh), giúp phân biệt trực quan giữa các môn trên
        # MỌI biểu đồ của hệ thống, không phụ thuộc thứ tự cột trong dataset.
        _topic_colors = [topic_color(lbl) for lbl in _topic_labels]
        _weak_topic_labels = [lbl for lbl, s in zip(_topic_labels, _topic_scores) if s < 5.0]
        _topic_class_avg = [float(df[c].mean()) for c in _topic_cols_present]
        _topic_gap = [s - a for s, a in zip(_topic_scores, _topic_class_avg)]
        _topic_status = [
            "Cần theo dõi"
            if s < 5.0
            else ("Tốt hơn TB lớp" if g > 0 else "Ngang TB lớp" if abs(g) < 0.05 else "Dưới TB lớp")
            for s, g in zip(_topic_scores, _topic_gap)
        ]

    # Tạo hồ sơ sinh viên phục vụ prompt cá nhân hóa sâu hơn
    # Dùng CHUNG định nghĩa rủi ro tương đối với Trang chủ Sinh viên
    # (model_service.classify_relative_risk) để 2 trang không bao giờ lệch nhau.
    from dss.services.model_service import classify_relative_risk

    risk_level = classify_relative_risk(predicted_gpa_llm, df[gpa_col_llm]) or "trung bình"

    # K-4: so sánh CÙNG THANG điểm — compute_progress_note tự ưu tiên diem_ky_nay
    # (đã thang 10) và chỉ quy đổi gpa_previous (thang 4) khi cần, tránh so lệch
    # thang khiến gần như mọi sinh viên đều hiện "đang cải thiện" giả tạo.
    _progress_delta, progress_note = compute_progress_note(predicted_gpa_llm, student_data_llm_row)

    student_profile = {
        "student_id": str(student_id_llm),
        "risk_level": risk_level,
        "progress_note": progress_note,
        "plan_weeks": 4,
        "learning_profile": learning_prof.to_dict(),
        "diagnoses": [d.to_dict() for d in structured_diagnoses],
        # K-3: ghi rõ nguồn số liệu vào prompt (mô hình Production hay điểm quan
        # sát được) — không để LLM/prompt ngầm định đây luôn là "dự đoán".
        "gpa_label": predicted_gpa_label,
    }

    # === Hàng ngữ cảnh: TRÁI = phân tích điểm yếu, PHẢI = thẻ rủi ro/yếu tố chính
    # (bố cục theo mockup: khu vực chính chứa phân tích/prompt, panel bên phải
    # chứa ngữ cảnh rủi ro + yếu tố chính — dữ liệu 100% lấy từ tính toán ở trên).
    _risk_badge_kind = {"cao": "danger", "trung bình": "warning", "thấp": "success"}.get(risk_level, "neutral")
    col_ctx_main, col_ctx_side = st.columns([2, 1], gap="medium")
    with col_ctx_main:
        with st.container(border=True):
            st.markdown("##### Phân tích điểm yếu")
            if weaknesses_llm:
                weakness_md = "<br>".join([f"- {w}" for w in weaknesses_llm[:8]])
                st.markdown(f"**Điểm yếu phát hiện ({len(weaknesses_llm)}):**")
                st.markdown(weakness_md, unsafe_allow_html=True)
            else:
                st.caption("Không phát hiện điểm yếu nổi bật (dưới ngưỡng 10% so với trung bình lớp).")
            if _topic_cols_present:
                st.markdown("---")
                st.markdown("**📊 Điểm theo từng chủ đề**")
                fig_topic = px.bar(
                    x=_topic_labels,
                    y=_topic_scores,
                    labels={"x": "Chủ đề", "y": "Điểm (thang 10)"},
                    text=[f"{s:.1f}" for s in _topic_scores],
                    custom_data=[_topic_class_avg, _topic_gap, _topic_status],
                )
                fig_topic.update_traces(
                    marker_color=_topic_colors,
                    textposition="outside",
                    hovertemplate=(
                        "<b>%{x}</b><br>"
                        "Điểm: %{y:.2f}<br>"
                        "TB lớp: %{customdata[0]:.2f}<br>"
                        "Chênh lệch: %{customdata[1]:+.2f}<br>"
                        "Trạng thái: %{customdata[2]}"
                        "<extra></extra>"
                    ),
                )
                fig_topic.add_hline(y=5.0, line_dash="dash", line_color="#94a3b8")
                fig_topic.update_layout(yaxis_range=[0, 10], showlegend=False, margin=dict(t=10, b=10))
                st.plotly_chart(fig_topic, width="stretch", key="topic_diagnosis_chart")
                if _weak_topic_labels:
                    st.caption(f"⚠️ Chủ đề cần cải thiện: **{', '.join(_weak_topic_labels)}** (điểm dưới 5.0/10).")
                else:
                    st.caption("✅ Không có chủ đề nào dưới ngưỡng đạt (5.0/10).")
    with col_ctx_side:
        with st.container(border=True):
            st.markdown("##### Hồ sơ rủi ro")
            st.caption(f"Sinh viên: **{student_id_llm}**")
            ui_kit.render_badge(f"Mức rủi ro: {risk_level.upper()}", kind=_risk_badge_kind)
            st.caption(ui_kit.RELATIVE_RISK_DISCLAIMER)
            st.metric(predicted_gpa_label, f"{float(predicted_gpa_llm):.2f}")
            st.caption(progress_note)
            if weaknesses_llm:
                st.markdown("**Yếu tố chính cần cải thiện:**")
                for w in weaknesses_llm[:4]:
                    st.caption(f"• {w.split('(')[0].strip()}")

    st.markdown("---")

    # NHÓM F: Tư vấn AI giờ trích dẫn qua rag_service.retrieve_unified_context —
    # đọc TRỰC TIẾP kho tri thức thật (tài liệu Admin/Giảng viên tải lên qua tab
    # "Quản lý tri thức", đã qua duyệt) — KHÔNG còn đọc
    # `MultiAIProvider._init_enhanced_knowledge_base` (19 tài liệu viết cứng, xem
    # F-0a/F-0b) cho mục đích trích dẫn. Giữ nguyên chữ ký cũ (trả về list) để
    # không phải sửa 5 nơi đang gọi `_find_docs_rag_safe(...)` bên dưới; thông
    # báo trung thực khi không có tài liệu hợp lệ được lưu vào session_state để
    # khối "Bằng chứng & Nguồn tham khảo" hiển thị đúng lý do (xem bên dưới).
    def _find_docs_rag_safe(query_text, top_k=5):
        result = rag_service.retrieve_unified_context(
            llm_integration,
            query_text,
            role=role,
            namespace=NAMESPACE_STUDENT_LEARNING,
            top_k=top_k,
            embedding_model_name=embedding_model_name,
            hf_token=hf_token_input if hf_token_input else None,
        )
        st.session_state["_last_rag_retrieval_status"] = result.get("status")
        st.session_state["_last_rag_retrieval_message"] = result.get("message")
        return result.get("chunks", [])

    # --- BƯỚC 3: CẤU HÌNH VÀ CHẠY LLM ---
    st.markdown("##### Tạo kế hoạch học tập (AI)")
    personal_goal = st.text_area(
        "🎯 Mục tiêu cá nhân (tuỳ chọn):",
        value="",
        placeholder="Ví dụ: tăng GPA lên 3.0 trong 2 tháng, cải thiện Toán và Lập trình...",
        key="llm_personal_goal",
    )
    if personal_goal.strip():
        student_profile["progress_note"] = (
            f"{student_profile['progress_note']}; mục tiêu cá nhân: {personal_goal.strip()}"
        )

    if role == "Sinh viên":
        # Sinh viên không cần biết "provider AI"/"API key" là gì — hệ thống tự
        # dùng nền tảng đã được Admin cấu hình mặc định (admin_ai_config), hoặc
        # tự dò qua secrets/env nếu Admin chưa đặt gì. Nếu chưa cấu hình gì cả,
        # nút "Tạo Kế hoạch Học tập" bên dưới tự động chuyển sang Demo mode
        # (không cần Internet/API) — không báo lỗi, không chặn tính năng.
        llm_type = "none"
        selected_provider = "none"
        model_name_input = ""
        api_key_input = ""
        hf_token_input = ""
        resolved_api_key = ""
        embedding_model_name = "sentence-transformers/all-MiniLM-L6-v2"
        use_embedding = True
        # Sinh viên chỉ được cấp namespace student_learning (dss/services/rag_namespaces.py)
        # — dữ liệu huấn luyện/đánh giá mô hình (admin_operations) không bao giờ lộ ra đây.
        use_warehouse_data = False

        _label_by_key = {
            "huggingface": "Hugging Face (Local/Cloud)",
            "gemini": "Google Gemini",
            "groq": "Groq (Siêu tốc)",
            "ollama": "Ollama (Local)",
            "openai": "OpenAI (ChatGPT)",
        }
        _default_cfg = admin_ai_config.get_default_provider()
        _ready_now = dict(_list_ready_cloud_providers(llm_integration, available_map))
        if _default_cfg and _default_cfg["provider_key"] in _ready_now:
            # Admin đã đặt mặc định VÀ provider đó vẫn sẵn sàng ngay bây giờ.
            selected_provider = _default_cfg["provider_key"]
            llm_type = _label_by_key[selected_provider]
            model_name_input = _default_cfg["model_name"]
            if selected_provider in ("gemini", "groq", "openai"):
                api_key_input = resolved_api_key = llm_integration.get_api_key_from_secrets(selected_provider)
        elif _check_ollama_running():
            # Ưu tiên Ollama (chạy LOCAL trên máy) TRƯỚC cloud nếu máy đã cài sẵn —
            # không cần API key, không phụ thuộc Internet hay việc hãng nào đó đổi
            # tên model ("package về máy" đúng nghĩa).
            selected_provider, llm_type, model_name_input = "ollama", "Ollama (Local)", AI_MODEL_CATALOG["ollama"][0]
        else:
            for _prov_key, _prov_label, _prov_model in [
                ("gemini", "Google Gemini", AI_MODEL_CATALOG["gemini"][0]),
                ("groq", "Groq (Siêu tốc)", AI_MODEL_CATALOG["groq"][1]),
                ("openai", "OpenAI (ChatGPT)", AI_MODEL_CATALOG["openai"][1]),
            ]:
                _found_key = llm_integration.get_api_key_from_secrets(_prov_key)
                if _found_key:
                    selected_provider, llm_type, model_name_input = _prov_key, _prov_label, _prov_model
                    api_key_input = resolved_api_key = _found_key
                    break
    elif role == "Admin":
        # Cấu hình kỹ thuật (API key, provider mặc định hệ thống...) tách hẳn vào
        # 1 expander riêng, đóng mặc định — tách biệt trực quan khỏi luồng tư vấn
        # chính, đúng yêu cầu mockup "admin config visually separated". Hàm bên
        # trong vẫn tự chặn `@require_role("Admin")` độc lập với việc UI có ẩn/hiện.
        with st.expander("Cấu hình hệ thống AI (Admin)", expanded=False):
            _cfg = _render_admin_provider_config(llm_integration, all_labels, available_map)
        llm_type = _cfg["llm_type"]
        selected_provider = _cfg["selected_provider"]
        model_name_input = _cfg["model_name_input"]
        api_key_input = _cfg["api_key_input"]
        hf_token_input = _cfg["hf_token_input"]
        embedding_model_name = _cfg["embedding_model_name"]
        use_embedding = _cfg["use_embedding"]
        use_warehouse_data = _cfg["use_warehouse_data"]
    elif role == "Giảng viên / CVHT":
        with st.expander("Chọn nguồn AI", expanded=False):
            _cfg = _render_teacher_provider_picker(llm_integration, available_map)
        llm_type = _cfg["llm_type"]
        selected_provider = _cfg["selected_provider"]
        model_name_input = _cfg["model_name_input"]
        api_key_input = _cfg["api_key_input"]
        hf_token_input = _cfg["hf_token_input"]
        embedding_model_name = _cfg["embedding_model_name"]
        use_embedding = _cfg["use_embedding"]
        use_warehouse_data = _cfg["use_warehouse_data"]
    else:
        # Role lạ không nằm trong 3 vai trò đã biết — mặc định KHÔNG cấp quyền kỹ
        # thuật gì (an toàn theo hướng deny-by-default), rơi về hành vi như Sinh
        # viên (tự dò/Demo mode) thay vì lộ ra cấu hình provider/API key.
        llm_type = "none"
        selected_provider = "none"
        model_name_input = ""
        api_key_input = ""
        hf_token_input = ""
        embedding_model_name = "sentence-transformers/all-MiniLM-L6-v2"
        use_embedding = True
        use_warehouse_data = False

    # Ngữ cảnh học tập của sinh viên được truyền qua student_profile có cấu trúc (Section 5, 23, 24).
    # TUYỆT ĐỐI không chèn hồ sơ sinh viên vào vector documents/RAG để tránh rò rỉ PII và ô nhiễm tri thức sư phạm.
    runtime_rag_documents = []

    # --- Nút kiểm tra kết nối (call_ai_provider trả về generator — cần gộp chunk) ---
    # CHỈ ADMIN — hành động này cần dùng API key thật (resolved_api_key), và chỉ
    # Admin mới được thấy/nhập key (Giảng viên dùng provider có sẵn nhưng không
    # xem được key thật). `_run_connection_test` tự chặn lại ở tầng hàm nữa
    # (@require_role("Admin")) — không chỉ dựa vào `if is_admin` ở đây.
    resolved_api_key = api_key_input
    if selected_provider in ("gemini", "groq", "openai") and not resolved_api_key:
        # Tự động lấy key từ secrets/env nếu không có key nhập tay (Admin) hoặc
        # không có key nào được truyền sẵn (Giảng viên/Sinh viên).
        resolved_api_key = llm_integration.get_api_key_from_secrets(selected_provider)

    # =========================================================================
    # KHUNG TRÒ CHUYỆN AI (chat thật, đa lượt) — TRUNG TÂM của trang, theo đúng
    # yêu cầu mockup ("Hỏi AI về lớp học"/"Trợ lý học tập AI" là 1 cuộc hội
    # thoại, không phải chỉ 1 form "Tạo kế hoạch" một lượt). KHÔNG viết logic
    # LLM/RAG mới — tái dùng ĐÚNG `llm_integration.call_ai_provider` (đã có
    # retry rate-limit 429 tích hợp sẵn ở core/models.py), `rag_service` qua
    # closure `_find_docs_rag_safe`, và `_build_demo_study_plan` làm phương án
    # dự phòng khi chưa có provider nào sẵn sàng (y hệt logic Demo mode đã có).
    st.markdown("---")
    _chat_key = f"ai_chat_history_{role}_{student_id_llm}"
    if _chat_key not in st.session_state:
        st.session_state[_chat_key] = []

    # 3 cột: bối cảnh (trái) / hội thoại (giữa) / bằng chứng-nguồn RAG (phải) —
    # đúng bố cục "AI Copilot" theo yêu cầu thiết kế (không phải 1 form 2 cột).
    # Khung chat là khu vực CHÍNH của trang (không phải 1 trong 3 khối ngang hàng) —
    # tăng tỉ lệ cột rõ rệt (~55% bề ngang) so với 2 cột phụ trái/phải.
    col_chat_context, col_chat_thread, col_chat_evidence = st.columns([0.85, 2.3, 0.85], gap="medium")

    with col_chat_context:
        with st.container(border=True):
            st.markdown("##### Bối cảnh")
            st.caption(f"Đang trao đổi về: **{student_id_llm}**")
            _chat_badge_kind = {"cao": "danger", "trung bình": "warning", "thấp": "success"}.get(risk_level, "neutral")
            ui_kit.render_badge(f"Rủi ro: {risk_level.upper()}", kind=_chat_badge_kind)
            st.caption(ui_kit.RELATIVE_RISK_DISCLAIMER)
            st.metric(predicted_gpa_label, f"{float(predicted_gpa_llm):.2f}")
            if weaknesses_llm:
                st.caption("Yếu tố cần chú ý: " + ", ".join(w.split("(")[0].strip() for w in weaknesses_llm[:3]))

            # Bối cảnh CẢ LỚP cho Giảng viên/Admin — tái dùng ĐÚNG hàm đã có ở
            # Dashboard giảng viên (compute_lecturer_dashboard_overview), không
            # viết phép tính rủi ro lớp học mới. Bỏ qua im lặng nếu chưa có
            # Production hồi quy cho dataset này (không phải lỗi).
            _class_ctx_line = None
            if is_staff and wh is not None:
                try:
                    _class_overview = compute_lecturer_dashboard_overview(
                        df, wh, st.session_state.get("current_dataset_id"), gpa_col_llm
                    )
                    if _class_overview.get("status") == "ok":
                        _rc = _class_overview["risk_counts"]
                        _class_ctx_line = (
                            f"Toàn lớp ({len(df)} SV): {_rc['cao']} rủi ro cao, {_rc['trung bình']} trung bình, "
                            f"{_rc['thấp']} thấp. Điểm dự đoán trung bình lớp: {_class_overview['avg_predicted']:.2f}."
                        )
                        st.caption(f"📊 {_class_ctx_line}")
                except Exception:
                    _class_ctx_line = None

            st.markdown("---")
            st.markdown("**💡 Câu hỏi gợi ý**")
            _sugg_list = _SUGGESTED_QUESTIONS_STUDENT if role == "Sinh viên" else _SUGGESTED_QUESTIONS_LECTURER
            _pending_question = None
            for _qi, _sugg_q in enumerate(_sugg_list):
                if st.button(_sugg_q, key=f"sugg_q_{_qi}", width="stretch"):
                    _pending_question = _sugg_q

    with col_chat_thread:
        with st.container(border=True):
            _chat_hdr_col1, _chat_hdr_col2 = st.columns([3, 1])
            with _chat_hdr_col1:
                st.markdown("##### Trò chuyện với AI")
            with _chat_hdr_col2:
                if st.session_state.get(f"_chat_demo_confirmed_{_chat_key}"):
                    ui_kit.render_badge("Chế độ mô phỏng", kind="neutral")
            _chat_history = st.session_state[_chat_key]
            _chat_box = st.container(height=560)
            with _chat_box:
                if not _chat_history:
                    st.caption(
                        "Chưa có tin nhắn nào — hãy bấm 1 câu hỏi gợi ý bên trái hoặc nhập câu hỏi của bạn bên dưới."
                    )
                for _msg in _chat_history:
                    with st.chat_message(_msg["role"]):
                        if _msg.get("hallucinated"):
                            st.caption("⚠️ Một số nguồn trong câu trả lời này chưa được xác minh khớp tài liệu.")
                        st.markdown(_msg["content"])
                        if _msg.get("sources"):
                            with st.expander("Nguồn tham khảo", expanded=False):
                                for _src in _msg["sources"]:
                                    st.caption(f"• {_src}")

            _chat_demo_confirmed_key = f"_chat_demo_confirmed_{_chat_key}"
            _chat_pending_q_key = f"_chat_pending_question_{_chat_key}"

            # Nếu đang chờ xác nhận Demo (câu hỏi trước đó chưa có provider thật) —
            # hiện 2 nút xác nhận NGAY TRÊN ô nhập, không tự động rơi vào Demo im lặng.
            # Production Demo Policy (audit 2026-09): trong REAL_LMS, KHÔNG được đề
            # nghị Demo — chỉ thông báo trung thực AI chưa khả dụng.
            if st.session_state.get(_chat_pending_q_key) and _is_production_environment():
                st.warning("🔒 Trợ lý AI hiện chưa khả dụng. Vui lòng thử lại sau.")
                if st.button("Quay lại", key="chat_cancel_unavailable", width="stretch"):
                    st.session_state.pop(_chat_pending_q_key, None)
                    st.rerun()
            elif st.session_state.get(_chat_pending_q_key):
                _cc1, _cc2 = st.columns(2)
                with _cc1:
                    _chat_go_demo = st.button(
                        "Tiếp tục với chế độ mô phỏng", key="chat_confirm_demo", type="primary", width="stretch"
                    )
                with _cc2:
                    _chat_cancel_demo = st.button("Quay lại", key="chat_cancel_demo", width="stretch")
                if _chat_cancel_demo:
                    st.session_state.pop(_chat_pending_q_key, None)
                    st.rerun()
                if _chat_go_demo:
                    st.session_state[_chat_demo_confirmed_key] = True

            _typed_question = st.chat_input("Nhập câu hỏi của bạn...", key="ai_chat_input")
            _question = st.session_state.get(_chat_pending_q_key) or _pending_question or _typed_question

            if _question:
                _is_replaying_pending = _question == st.session_state.get(_chat_pending_q_key) and st.session_state.get(
                    _chat_demo_confirmed_key
                )
                if not _is_replaying_pending:
                    _chat_history.append({"role": "user", "content": _question})

                # OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE (Phần 4-6, 9-12):
                # Router THUẦN (không gọi LLM để phân loại) chặn TRƯỚC khi
                # tốn 1 lượt RAG retrieval + LLM Gateway cho 3 route đã thật
                # sự wire hành vi runtime trong đợt này (đúng nguyên tắc
                # "LLM IS NOT THE DECISION ENGINE" — xem docs/ai/AI_ROUTING_MATRIX.md
                # cho các route khác mới chỉ phân loại, chưa có code đứng sau):
                #   - GPA_CALCULATION: Calculator trả lời NGAY, LLM không được
                #     tự tính con số này.
                #   - REGULATION_LOOKUP: chặn LLM tự đoán quy chế — trả lời
                #     trung thực (hiện chưa có ánh xạ organization_id/
                #     program_id/cohort cho sinh viên trong dataset mô phỏng
                #     nên không tra cứu đầy đủ được, xem ai_router.py).
                #   - ACADEMIC_RULE_CHECK: chặn LLM tự quyết định ALLOW/DENY
                #     điều kiện học vụ — Rule Engine (rule_engine.py) là nơi
                #     duy nhất được quyết định, nhưng cùng lý do với
                #     REGULATION_LOOKUP (thiếu organization_id/program_id/
                #     cohort + số tín chỉ đã hoàn thành), trả lời trung thực
                #     thay vì tự bịa input.
                #   - DIRECT_DATA_LOOKUP (Phần 15, FINAL GAP CLOSURE): đọc
                #     THẲNG dữ liệu CỦA CHÍNH sinh viên đang hỏi
                #     (student_data_llm_filtered, đã resolve từ
                #     current_student_id ở trên — KHÔNG BAO GIỜ dữ liệu của
                #     sinh viên khác) — route DUY NHẤT được phân loại đúng từ
                #     trước nhưng CHƯA có hành vi thật (docs/ai/AI_ROUTING_MATRIX.md,
                #     mục "Gaps") — nay đã đóng.
                _route_decision = ai_router.classify(_question)
                # Section 5 (FINAL REMAINING-GAPS CLOSURE): truyền danh tính
                # THẬT (đã resolve từ current_student_id ở trên qua pseudonym
                # — KHÔNG BAO GIỜ mã số sinh viên thật) để build_gpa_
                # calculation_reply() định tuyến qua agent.run_gpa_calculation()
                # với authorize() thật, không chỉ unit-test/class riêng lẻ.
                _gpa_reply = (
                    ai_router.build_gpa_calculation_reply(
                        _question,
                        user_id=privacy_service.generate_pseudonym(str(student_id_llm)),
                        role=role or "Sinh viên",
                    )
                    if _route_decision.intent == ai_router.INTENT_GPA_CALCULATION
                    else None
                )
                _regulation_reply = (
                    ai_router.build_regulation_lookup_reply(_question)
                    if _route_decision.intent == ai_router.INTENT_REGULATION_LOOKUP
                    else None
                )
                _rule_check_reply = (
                    ai_router.build_academic_rule_check_reply(_question)
                    if _route_decision.intent == ai_router.INTENT_ACADEMIC_RULE_CHECK
                    else None
                )
                _direct_lookup_reply = (
                    ai_router.build_direct_data_lookup_reply(_question, student_row=student_data_llm_filtered)
                    if _route_decision.intent == ai_router.INTENT_DIRECT_DATA_LOOKUP
                    else None
                )
                _router_short_circuit_reply = (
                    _gpa_reply or _regulation_reply or _rule_check_reply or _direct_lookup_reply
                )
                if _router_short_circuit_reply is not None:
                    st.session_state.pop(_chat_pending_q_key, None)
                    _chat_history.append(
                        {
                            "role": "assistant",
                            "content": _router_short_circuit_reply,
                            "sources": [],
                            "hallucinated": False,
                            "route": _route_decision.intent,
                        }
                    )
                    st.rerun()

                _rag_query = (
                    llm_integration._build_rag_query_from_weaknesses(weaknesses_llm, student_profile=student_profile)
                    + " "
                    + _question
                )
                _chat_docs = _find_docs_rag_safe(query_text=_rag_query, top_k=4)
                # E-4: ghi rõ loại nguồn (tài liệu mẫu nội bộ chưa kiểm duyệt vs.
                # đã kiểm duyệt/tải lên) thay vì chỉ hiện tên tài liệu trần trụi.
                _chat_sources = [rag_service.format_document_citation(d) for d in _chat_docs] if _chat_docs else []

                # Section 24 (FINAL GAP CLOSURE): Knowledge Fallback
                # PREVENT-BEFORE. Trước đợt này hệ thống CHỈ có VERIFY-AFTER
                # (citation_service.verify_citations() kiểm tra SAU khi LLM đã
                # trả lời — vẫn để LLM "thử trả lời" trước rồi mới gắn cờ
                # hallucinated). Với route RAG_QA cụ thể (câu hỏi rõ ràng về
                # nội dung 1 tài liệu — KHÔNG áp dụng cho ADVISOR_CHAT chung
                # chung, vốn được phép trả lời từ khả năng hội thoại tổng
                # quát), nếu retrieval trả về RỖNG thì KHÔNG được hỏi LLM —
                # chặn TRƯỚC, không phải phát hiện SAU.
                if _route_decision.intent == ai_router.INTENT_RAG_QA and not _chat_docs:
                    st.session_state.pop(_chat_pending_q_key, None)
                    _chat_history.append(
                        {
                            "role": "assistant",
                            "content": (
                                "Em chưa tìm thấy tài liệu đã được duyệt phù hợp với câu hỏi này. "
                                "Để tránh đưa ra thông tin không có căn cứ, hệ thống KHÔNG để AI tự "
                                "suy đoán trong trường hợp này.\n\nVui lòng thử diễn đạt lại câu hỏi cụ "
                                "thể hơn, hoặc liên hệ giảng viên/Phòng Đào tạo."
                            ),
                            "sources": [],
                            "hallucinated": False,
                            "route": _route_decision.intent,
                        }
                    )
                    st.rerun()

                # Tự động chọn provider RIÊNG cho chat (KHÔNG dùng thẳng `selected_provider`
                # của panel cấu hình phía trên) — panel đó cho Admin/Giảng viên có thể đang
                # chọn "Hugging Face (Local)", tải model vài GB về máy khi gọi lần đầu, từng
                # làm SẬP HẲN tiến trình Streamlit (segmentation fault khi load checkpoint)
                # lúc kiểm thử thật. `resolve_auto_provider` (đã dùng cho hộp hỏi nhanh ở
                # Student Dashboard) ưu tiên mặc định Admin -> Ollama (local, nhẹ) -> cloud
                # đã có key — KHÔNG BAO GIỜ tự ý chọn Hugging Face local, an toàn hơn cho 1
                # tính năng hỏi-nhanh-nhiều-lượt như chat này.
                _chat_auto = llm_service.resolve_auto_provider(llm_integration)

                if not _chat_auto and not st.session_state.get(_chat_demo_confirmed_key):
                    # KHÔNG tự động rơi vào Demo trong im lặng — giữ nguyên câu hỏi và hỏi
                    # xác nhận (2 nút render ngay phía trên ô nhập); trả lời ngay khi xác nhận.
                    st.session_state[_chat_pending_q_key] = _question
                    st.rerun()

                _chat_has_hallucination = False
                if _chat_auto:
                    # FINAL REMAINING-GAPS CLOSURE (Section 7): lịch sử hội
                    # thoại là VĂN BẢN TỰ DO do chính sinh viên gõ — sinh viên
                    # có thể tự gõ tên/email/SĐT/MSSV thật bất kỳ lúc nào.
                    # Trước đây nối thẳng m["content"] KHÔNG qua khử PII nào —
                    # lỗ hổng thật đã tìm thấy khi audit (PRIVACY_PROVIDER_
                    # PAYLOAD_AUDIT.md). Dùng sanitize_conversation_turn_for_
                    # provider() (mạnh hơn sanitize_pii_from_text() — thêm cả
                    # MSSV + tên tự giới thiệu) cho MỖI lượt trước khi ghép.
                    _history_snippet = "\n".join(
                        f"{'Người dùng' if m['role'] == 'user' else 'Trợ lý'}: "
                        f"{privacy_service.sanitize_conversation_turn_for_provider(m['content'])}"
                        for m in _chat_history[-6:-1]
                    )
                    # Khử PII trước khi đưa vào ngữ cảnh gửi LLM (dss/services/privacy_service.py)
                    # — bối cảnh chỉ chứa định danh giả danh + mức rủi ro/GPA nhóm + điểm yếu,
                    # không có tên/email/SĐT/mã số sinh viên thật.
                    _anon_context, _privacy_audit = privacy_service.build_anonymized_student_context(
                        student_id_llm,
                        predicted_gpa_llm,
                        weaknesses_llm,
                        student_profile,
                    )
                    _chat_context_extra = []
                    if _class_ctx_line:
                        _chat_context_extra.append(_class_ctx_line)
                    if _history_snippet:
                        _chat_context_extra.append(f"Lịch sử hội thoại gần đây:\n{_history_snippet}")
                    _full_student_context = _anon_context + (
                        "\n" + "\n".join(_chat_context_extra) if _chat_context_extra else ""
                    )
                    _chat_system_instructions = (
                        f"Bạn là trợ lý học tập AI cho {'Giảng viên đang xem hồ sơ sinh viên' if is_staff else 'sinh viên'} này. "
                        "Trả lời ngắn gọn, cụ thể, bằng tiếng Việt, dựa trên bối cảnh học tập bên dưới."
                    )
                    # Ranh giới XML tách rõ chỉ thị hệ thống / bối cảnh / tài liệu RAG (không tin
                    # cậy) / câu hỏi người dùng — chống chèn lệnh gián tiếp từ nội dung tài liệu
                    # (dss/services/prompt_security.py), thay vì nối chuỗi f-string trực tiếp như cũ.
                    _chat_prompt = prompt_security.build_secure_rag_prompt(
                        system_instructions=_chat_system_instructions,
                        student_context=_full_student_context,
                        retrieved_chunks=_chat_docs,
                        user_query=_question,
                    )

                    _chat_kwargs = {"model_name": _chat_auto["model_name"]}
                    if _chat_auto["provider_key"] in ("gemini", "groq", "openai"):
                        _chat_kwargs["api_key"] = _chat_auto["api_key"]
                    elif _chat_auto["provider_key"] == "ollama":
                        _chat_kwargs["base_url"] = ollama_base_url()

                    try:
                        with st.spinner("Đang trả lời..."):
                            _stream = _LLMGateway(llm_integration).stream_generate(
                                prompt=_chat_prompt,
                                user_id=privacy_service.generate_pseudonym(str(student_id_llm)),
                                role=role or "Sinh viên",
                                request_type="advisor_chat",
                                provider=_chat_auto["provider_key"],
                                model=_chat_auto.get("model_name") or "default",
                                **_chat_kwargs,
                            )
                            _answer = "".join(_stream)
                    except Exception:
                        _logger.exception(
                            "Lỗi khi lấy phản hồi chat AI qua Gateway (provider=%s)", _chat_auto["provider_key"]
                        )
                        _answer = "⚠️ Không thể lấy phản hồi từ AI lúc này. Vui lòng thử lại sau."

                    # Xác minh trích dẫn: cảnh báo nếu AI nêu nguồn không khớp tài liệu đã nạp.
                    _chat_citation_check = citation_service.verify_citations(_answer, _chat_docs)
                    _chat_has_hallucination = bool(_chat_citation_check.get("hallucinated_citations"))
                    if _chat_has_hallucination:
                        _answer += (
                            "\n\n*(⚠️ Một số nguồn được nhắc tới có thể không khớp tài liệu đã nạp "
                            "— vui lòng đối chiếu lại phần \"Bằng chứng & Nguồn tham khảo\".)*"
                        )
                else:
                    # Chế độ mô phỏng — người dùng ĐÃ xác nhận (xem khối 2 nút phía trên ô
                    # nhập). TÁI DÙNG đúng hàm sinh kế hoạch demo đã có, không viết logic trả
                    # lời mới. Badge "Chế độ mô phỏng" ở tiêu đề khung chat đã báo rõ trạng
                    # thái — không lặp lại lời giải thích dài ở MỖI tin nhắn.
                    _demo_plan, _ = _build_demo_study_plan(
                        student_id_llm,
                        float(predicted_gpa_llm) if isinstance(predicted_gpa_llm, (int, float, np.floating)) else 0.0,
                        weaknesses_llm,
                        student_profile,
                        retrieved_docs=_chat_docs,
                        personal_goal=personal_goal,
                    )
                    _answer = _demo_plan

                st.session_state.pop(_chat_pending_q_key, None)
                # NHÓM F mục 5: gắn cờ rõ ràng khi câu trả lời có trích dẫn không
                # khớp tài liệu đã nạp — KHÔNG coi đây là 1 lượt tư vấn "sạch"
                # (is_grounded=False), dù vẫn hiển thị cho người dùng kèm cảnh báo
                # ở trên (không xóa câu trả lời, chỉ không đánh dấu là đáng tin).
                _chat_history.append(
                    {
                        "role": "assistant",
                        "content": _answer,
                        "sources": _chat_sources,
                        "hallucinated": _chat_has_hallucination,
                    }
                )
                st.rerun()

            if st.session_state[_chat_key] and st.button("🗑️ Xoá cuộc trò chuyện", key="ai_chat_clear"):
                st.session_state[_chat_key] = []
                st.rerun()

    with col_chat_evidence:
        with st.container(border=True):
            st.markdown("##### Bằng chứng & Nguồn tham khảo")
            _last_sourced_msg = next(
                (m for m in reversed(st.session_state[_chat_key]) if m.get("role") == "assistant" and m.get("sources")),
                None,
            )
            if _last_sourced_msg:
                st.caption("Tài liệu RAG dùng cho câu trả lời gần nhất:")
                for _src in _last_sourced_msg["sources"]:
                    st.markdown(
                        f"<div style='padding:0.5rem 0.7rem;border:1px solid var(--border);border-radius:8px;"
                        f"margin-bottom:0.5rem;font-size:var(--fs-support);color:var(--text-primary);background:var(--bg-secondary);'>"
                        f"📄 {_src}</div>",
                        unsafe_allow_html=True,
                    )
            elif st.session_state.get("_last_rag_retrieval_status") in (
                "NO_RELEVANT_EVIDENCE",
                "PERMISSION_DENIED",
                "ERROR",
            ):
                # NHÓM F: khi kho tri thức KHÔNG có tài liệu đã duyệt phù hợp,
                # nói rõ "chưa có" thay vì im lặng hoặc để LLM tự bịa nội dung.
                st.warning(
                    "📭 "
                    + (
                        st.session_state.get("_last_rag_retrieval_message")
                        or "Chưa có tài liệu chính thức được duyệt cho câu hỏi này."
                    )
                )
                st.caption(
                    "Phần phân tích dựa trên dữ liệu (dự đoán, chẩn đoán) ở cột bên trái vẫn không bị ảnh hưởng."
                )
            else:
                ui_kit.empty_state(
                    "Chưa có bằng chứng nào",
                    icon="📄",
                    hint="Nguồn tài liệu RAG sẽ hiện ở đây sau khi bạn đặt câu hỏi.",
                )

    # --- Công cụ kỹ thuật (Kiểm tra kết nối / So sánh AI / Xem trước RAG / Demo)
    # gộp vào 1 khối tách biệt trực quan khỏi luồng tư vấn chính — CHỈ Giảng
    # viên/Admin thấy (Sinh viên không cần biết "provider"/"RAG"/"token" là gì).
    # RBAC vẫn chặn ở tầng hàm bên trong (`@require_role`) độc lập với khối UI này.
    if is_staff:
        with st.expander("Công cụ kỹ thuật (RAG · So sánh AI · Kiểm tra kết nối)", expanded=False):
            if is_admin:
                _can_test = selected_provider in ("huggingface", "ollama") or (
                    selected_provider in ("gemini", "groq", "openai") and bool(resolved_api_key)
                )
                if _can_test and available_map.get(llm_type, False):
                    if st.button(f"🧪 Kiểm tra {llm_type} API Key", key="btn_test_llm_conn"):
                        _run_connection_test(
                            llm_integration,
                            selected_provider,
                            model_name_input,
                            resolved_api_key,
                            api_key_input,
                            llm_type,
                        )

            # --- Chế độ "So sánh AI" (Compare AI) — Phase 10 refactor ---
            # Kiến trúc multi-LLM đã sẵn (dss/services/llm_service.py, ThreadPoolExecutor
            # giới hạn bởi MAX_CONCURRENT_REQUESTS) nhưng CHỦ ĐỘNG không gọi ở luồng tạo kế
            # hoạch bình thường phía dưới — chỉ chạy khi bấm đúng nút này. `_run_compare_ai`
            # tự chặn lại ở tầng hàm (@require_role) nếu không phải Giảng viên/Admin.
            st.markdown("**🆚 So sánh nhiều AI cùng lúc** (tùy chọn, không bắt buộc)")
            st.caption(
                "Gọi đồng thời nhiều provider cho CÙNG 1 sinh viên để đối chiếu chất lượng câu trả lời — "
                "không thay thế luồng tạo kế hoạch chính bên dưới, chỉ dùng khi cần đánh giá/thử nghiệm."
            )
            _compare_candidates = _list_ready_cloud_providers(llm_integration, available_map)

            if len(_compare_candidates) < 2:
                st.info(
                    "Cần ít nhất 2 provider sẵn sàng (đã cấu hình API key hoặc chạy local) để so sánh — "
                    "hiện chỉ có " + (", ".join(lbl for _, lbl in _compare_candidates) or "0 provider") + "."
                )
            else:
                _compare_labels = st.multiselect(
                    "Chọn các provider muốn so sánh:",
                    [lbl for _, lbl in _compare_candidates],
                    default=[lbl for _, lbl in _compare_candidates[:2]],
                    key="compare_ai_providers_pick",
                )
                if st.button("🆚 Chạy so sánh", key="run_compare_ai") and len(_compare_labels) >= 2:
                    _label_to_key = {lbl: key for key, lbl in _compare_candidates}
                    _specs = []
                    for _lbl in _compare_labels:
                        _key = _label_to_key[_lbl]
                        _kwargs = {}
                        if _key in ("gemini", "groq", "openai"):
                            _kwargs["api_key"] = llm_integration.get_api_key_from_secrets(_key)
                        elif _key == "ollama":
                            _kwargs["base_url"] = ollama_base_url()
                        _specs.append(
                            {
                                "provider_key": _key,
                                "provider_label": _lbl,
                                "model_name": AI_MODEL_CATALOG[_key][0],
                                "call_kwargs": _kwargs,
                            }
                        )
                    _run_compare_ai(
                        llm_integration,
                        _specs,
                        weaknesses_llm,
                        predicted_gpa_llm,
                        student_profile,
                        runtime_rag_documents,
                        role=role or "Giảng viên / CVHT",
                    )

            st.markdown("---")
            # Nút "Xem trước tài liệu RAG" (thuật ngữ kỹ thuật) và nút Demo riêng chỉ
            # dành cho Giảng viên/Admin thao tác/debug — nút "Tạo Kế hoạch Học tập" duy
            # nhất bên dưới đã TỰ ĐỘNG chuyển sang Demo mode khi cần, nên Sinh viên chỉ
            # cần đúng 1 nút, không phải phân biệt "AI thật" hay "Demo".
            col_quick1, col_quick2 = st.columns([1, 1])
            with col_quick1:
                if st.button("🔎 Xem trước tài liệu RAG (Top 5)", key="preview_rag_docs_btn"):
                    query_text = llm_integration._build_rag_query_from_weaknesses(
                        weaknesses_llm, student_profile=student_profile
                    )
                    docs_preview = _find_docs_rag_safe(query_text=query_text, top_k=5)
                    if docs_preview:
                        st.success(f"Tìm thấy {len(docs_preview)} tài liệu phù hợp.")
                        _rag_source_labels = {
                            "knowledge_base": "📚 Kho tài liệu học tập",
                            "uploaded_dataset": "👤 Hồ sơ sinh viên (từ dữ liệu đang tải)",
                        }
                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        "Tiêu đề": d.get("title", ""),
                                        "Nguồn": _rag_source_labels.get(
                                            d.get("source", "knowledge_base"), d.get("source", "knowledge_base")
                                        ),
                                        "Nguồn tham khảo": d.get("reference", "") or "—",
                                        "Nội dung tóm tắt": str(d.get("content", ""))[:140] + "...",
                                    }
                                    for d in docs_preview
                                ]
                            ),
                            width="stretch",
                            hide_index=True,
                        )
                        st.caption(
                            "💡 \"Hồ sơ sinh viên\" là dữ liệu điểm số của chính sinh viên này (không phải tài liệu tĩnh) — "
                            "được đưa vào để AI bám sát hồ sơ thực tế thay vì chỉ dùng kiến thức chung. Cột \"Nguồn tham khảo\" "
                            "cho biết tài liệu trong Kho tri thức dựa trên phương pháp/nghiên cứu cụ thể nào (nếu có), hay chỉ "
                            "là kinh nghiệm giảng dạy tổng hợp."
                        )
                    else:
                        st.info("Chưa tìm được tài liệu phù hợp.")
            with col_quick2:
                # Production Demo Policy (audit 2026-09): nút Demo này KHÔNG được
                # tồn tại trong REAL_LMS — chỉ là công cụ demo/dev nội bộ.
                if not _is_production_environment() and st.button(
                    "⚡ Tạo kế hoạch nhanh (Demo - không cần API)", key="run_llm_demo"
                ):
                    query_text = llm_integration._build_rag_query_from_weaknesses(
                        weaknesses_llm, student_profile=student_profile
                    )
                    docs_preview = _find_docs_rag_safe(query_text=query_text, top_k=5)
                    plan_demo, week_plan_demo = _build_demo_study_plan(
                        student_id_llm,
                        float(predicted_gpa_llm) if isinstance(predicted_gpa_llm, (int, float, np.floating)) else 0.0,
                        weaknesses_llm,
                        student_profile,
                        retrieved_docs=docs_preview,
                        personal_goal=personal_goal,
                    )
                    st.markdown(plan_demo)
                    _render_weekly_reminder_checklist(week_plan_demo, current_student_id)

    st.markdown("---")
    _run_llm_btn_label = "🚀 Tạo Kế hoạch Học tập" if role == "Sinh viên" else "🚀 Tạo Kế hoạch Học tập bằng AI"
    _demo_confirm_key = f"_ai_demo_confirm_pending_{student_id_llm}"
    _demo_active_key = f"_ai_demo_mode_active_{student_id_llm}"

    _provider_actually_ready = available_map.get(llm_type, False) and not (
        selected_provider in ["gemini", "groq", "openai"] and not resolved_api_key
    )
    _run_clicked = st.button(_run_llm_btn_label, type="primary", key="run_llm")

    if _run_clicked:
        if _provider_actually_ready:
            st.session_state.pop(_demo_confirm_key, None)
            st.session_state[_demo_active_key] = False
        else:
            # KHÔNG tự động chuyển sang Demo trong im lặng — phải hỏi người dùng
            # trước (yêu cầu bắt buộc). Không tạo/hiển thị bất kỳ nội dung nào ở
            # lượt bấm này; chỉ bật cờ chờ xác nhận, xử lý ở khối bên dưới.
            st.session_state[_demo_confirm_key] = True

    if st.session_state.get(_demo_confirm_key) and _is_production_environment():
        # Production Demo Policy (audit 2026-09): KHÔNG đề nghị chế độ mô phỏng
        # trong REAL_LMS — chỉ thông báo trạng thái trung thực, không phương án Demo.
        st.warning("🔒 Trợ lý AI hiện chưa khả dụng. Vui lòng thử lại sau hoặc liên hệ quản trị viên.")
        if st.button("Đã hiểu", key="ack_ai_unavailable"):
            st.session_state.pop(_demo_confirm_key, None)
            st.rerun()
        _run_clicked = False
    elif st.session_state.get(_demo_confirm_key):
        st.info(
            "**AI trực tuyến hiện chưa sẵn sàng.**\n\n"
            "Bạn có muốn tiếp tục với chế độ tư vấn mô phỏng không?\n\n"
            "Chế độ mô phỏng sẽ sử dụng dữ liệu và mẫu tư vấn có sẵn trong hệ thống, "
            "không gọi mô hình AI bên ngoài."
        )
        _col_demo_yes, _col_demo_no = st.columns(2)
        with _col_demo_yes:
            _go_demo = st.button(
                "Tiếp tục với chế độ mô phỏng", key="confirm_demo_mode", type="primary", width="stretch"
            )
        with _col_demo_no:
            _cancel_demo = st.button("Quay lại", key="cancel_demo_mode", width="stretch")
        if _cancel_demo:
            st.session_state.pop(_demo_confirm_key, None)
            st.rerun()
        if _go_demo:
            st.session_state.pop(_demo_confirm_key, None)
            st.session_state[_demo_active_key] = True
            _run_clicked = True
        else:
            _run_clicked = False

    if _run_clicked and (_provider_actually_ready or st.session_state.get(_demo_active_key)):
        with st.spinner("🤖 Đang phân tích dữ liệu và tạo kế hoạch (có thể mất vài phút)..."):
            try:
                if not _provider_actually_ready:
                    ui_kit.render_badge("Chế độ mô phỏng", kind="neutral")
                    query_text = llm_integration._build_rag_query_from_weaknesses(
                        weaknesses_llm, student_profile=student_profile
                    )
                    docs_preview = _find_docs_rag_safe(query_text=query_text, top_k=5)
                    plan_demo, week_plan_demo = _build_demo_study_plan(
                        student_id_llm,
                        float(predicted_gpa_llm) if isinstance(predicted_gpa_llm, (int, float, np.floating)) else 0.0,
                        weaknesses_llm,
                        student_profile,
                        retrieved_docs=docs_preview,
                        personal_goal=personal_goal,
                    )
                    st.markdown("### Kế hoạch học tập (Chế độ mô phỏng)")
                    st.markdown(plan_demo)
                    _render_weekly_reminder_checklist(week_plan_demo, current_student_id)
                    return

                # H-2 (đọc lập review kiến trúc thương mại, đợt 3): truy xuất RAG
                # ĐÚNG MỘT LẦN cho cả response này — trước đây prompt gửi LLM và
                # khung "Bằng chứng & Nguồn tham khảo"/verify_citations sau đó gọi
                # retrieve_unified_context RIÊNG (2 lần độc lập cho cùng 1 response),
                # có rủi ro lý thuyết trả về 2 tập tài liệu khác nhau nếu trạng thái
                # duyệt thay đổi giữa 2 lần gọi. Truy xuất 1 lần ở đây, truyền
                # NGUYÊN VẸN object list đó (`prefetched_relevant_docs`) xuống
                # generate_personalized_advice VÀ dùng LẠI cho khung bằng chứng bên
                # dưới — đảm bảo prompt LLM, sources hiển thị UI và citation
                # verification LUÔN xét trên CÙNG MỘT tập tài liệu, không phải 2
                # lần gọi có thể lệch nhau.
                _plan_relevant_docs = None
                if use_embedding and weaknesses_llm:
                    _plan_query_text = llm_integration._build_rag_query_from_weaknesses(
                        weaknesses_llm, student_profile=student_profile
                    )
                    _plan_relevant_docs = _find_docs_rag_safe(query_text=_plan_query_text, top_k=5)

                if selected_provider == "huggingface":
                    # Model local (transformers) — giữ đường gọi trực tiếp: quy ước tham số
                    # (hf_token) khác với api_key đã chuẩn hoá của Gateway, và đây là provider
                    # miễn phí/local nên không cần quota/chi phí qua Gateway.
                    try:
                        plan_stream = llm_integration.generate_personalized_advice(
                            student_weaknesses=weaknesses_llm,
                            predicted_gpa=predicted_gpa_llm,
                            provider=selected_provider,
                            model_name=model_name_input,
                            hf_token=api_key_input,
                            use_rag=use_embedding,
                            embedding_model_name=embedding_model_name,
                            use_warehouse_data=use_warehouse_data,
                            student_profile=student_profile,
                            runtime_documents=runtime_rag_documents,
                            role=role or "Sinh viên",
                            prefetched_relevant_docs=_plan_relevant_docs,
                        )
                    except TypeError:
                        plan_stream = llm_integration.generate_personalized_advice(
                            student_weaknesses=weaknesses_llm,
                            predicted_gpa=predicted_gpa_llm,
                            provider=selected_provider,
                            model_name=model_name_input,
                            hf_token=api_key_input,
                            use_rag=use_embedding,
                            embedding_model_name=embedding_model_name,
                            use_warehouse_data=use_warehouse_data,
                            student_profile=student_profile,
                        )
                    # Nhánh này không qua LLMGateway → tự bọc bộ lọc lời khuyên có hại.
                    from dss.services.output_guard import guard_stream

                    plan_stream = guard_stream(plan_stream, role=role or "Sinh viên", request_type="advisor_plan")
                else:
                    # Gemini/Groq/OpenAI/Ollama — đi qua LLM Gateway tập trung (Section S):
                    # kiểm tra hạn ngạch/token, retry+backoff, giới hạn đồng thời, tự ghi
                    # nhận token/chi phí (token_tracker) dưới định danh giả danh — không lưu
                    # mã sinh viên thật vào log sử dụng AI (Section T/U).
                    gateway_kwargs = {}
                    if selected_provider == "ollama":
                        gateway_kwargs["base_url"] = api_key_input
                    _quota_estimate_text = " ".join(weaknesses_llm) + " " + str(student_profile)
                    plan_stream = _LLMGateway(llm_integration).stream_generate(
                        prompt=_quota_estimate_text,
                        user_id=privacy_service.generate_pseudonym(str(student_id_llm)),
                        role=role or "Sinh viên",
                        request_type="advisor_plan",
                        provider=selected_provider,
                        model=model_name_input,
                        student_weaknesses=weaknesses_llm,
                        predicted_gpa=predicted_gpa_llm,
                        use_rag=use_embedding,
                        embedding_model_name=embedding_model_name,
                        use_warehouse_data=use_warehouse_data,
                        student_profile=student_profile,
                        runtime_documents=runtime_rag_documents,
                        prefetched_relevant_docs=_plan_relevant_docs,
                        **gateway_kwargs,
                    )

                st.markdown("---")
                st.markdown("### Báo cáo Phân tích & Kế hoạch Học tập")
                with st.container(border=True):
                    # st.write_stream sẽ streaming realtime và trả về toàn bộ text
                    plan_placeholder = st.empty()
                    with plan_placeholder.container():
                        plan = st.write_stream(plan_stream)
                    # AI đôi khi dùng <br> để xuống dòng trong 1 ô bảng Markdown (cách duy nhất
                    # hợp lệ, vì bảng không cho phép xuống dòng thật bên trong ô) — st.write_stream
                    # không diễn giải HTML nên hiển thị nguyên văn "<br>" thay vì xuống dòng thật.
                    # Sau khi stream xong, nếu phát hiện có <br>, render lại đúng 1 lần cuối có
                    # cho phép HTML để bảng hiển thị đúng.
                    if plan and "<br" in plan.lower():
                        with plan_placeholder.container():
                            st.markdown(plan, unsafe_allow_html=True)

                # H-2: dùng LẠI đúng tập tài liệu đã truy xuất 1 lần ở trên
                # (`_plan_relevant_docs`) — KHÔNG gọi lại retrieve_unified_context
                # lần thứ 2, để tránh lệch tập tài liệu giữa nội dung AI vừa sinh
                # và khung "Bằng chứng & Nguồn tham khảo"/citation verification
                # bên dưới. Nếu không có (`use_embedding=False`/không có điểm yếu),
                # giữ nguyên hành vi cũ: rỗng.
                _docs_for_checklist = _plan_relevant_docs or []

                # Xác minh trích dẫn: đối chiếu nguồn AI nêu ra với tài liệu RAG thực sự
                # đã nạp — cảnh báo nếu phát hiện trích dẫn bịa đặt (Section AC test #9).
                _plan_citation_check = citation_service.verify_citations(plan or "", _docs_for_checklist)
                if _plan_citation_check.get("hallucinated_citations"):
                    st.warning(
                        "⚠️ AI có thể đã trích dẫn một số nguồn không khớp với tài liệu đã nạp — "
                        "vui lòng đối chiếu lại trước khi áp dụng kế hoạch này."
                    )

                # Audit 2026-09-15 (Issue FUNC-PLAN-001): kế hoạch tuần có cấu trúc giờ
                # dùng learning_plan_generator.generate_plan() THẬT (chẩn đoán + liều
                # lượng tính từ đúng learning_prof của sinh viên này) thay vì gọi lại
                # _build_demo_study_plan() — hàm đó giờ CHỈ còn dùng cho đúng 2 nhánh
                # đã tự nhận là "Demo" ở trên (người dùng bấm nút Demo tường minh, hoặc
                # đã xác nhận qua hộp thoại "AI chưa sẵn sàng"). Văn bản tư vấn tự do
                # (`plan`, ở trên) vẫn do LLM thật sinh ra qua Gateway — không đổi.
                try:
                    _structured_plan = learning_plan_generator.generate_plan(learning_prof)
                    week_plan_ai = _week_plan_from_structured_plan(_structured_plan, weeks=4)
                except Exception:
                    _logger.exception("Không thể tạo kế hoạch có cấu trúc từ learning_plan_generator")
                    _structured_plan = None
                    week_plan_ai = []
                _render_weekly_reminder_checklist(week_plan_ai, current_student_id)

                if _structured_plan is not None:
                    with st.expander("🔍 Tại sao hệ thống đề xuất kế hoạch này? (Bằng chứng & chẩn đoán)"):
                        if _structured_plan.evidence_used:
                            st.markdown("**Bằng chứng dùng để tính liều lượng học tập:**")
                            for _ev in _structured_plan.evidence_used:
                                st.caption(f"• {_ev}")
                        if _structured_plan.diagnoses:
                            st.markdown("**Chẩn đoán:**")
                            for _dg in _structured_plan.diagnoses:
                                st.caption(f"• {_dg.get('issue', '—')}")
                        # Không hiển thị "_structured_plan.confidence" dưới dạng phần trăm:
                        # đây là hằng số chính sách cố định (0.85 cho MỌI sinh viên), không
                        # phải giá trị đo lường/hiệu chuẩn từ dữ liệu — hiển thị như tỷ lệ %
                        # sẽ khiến người dùng hiểu nhầm là một chỉ số được tính riêng cho họ.
                        st.caption(f"Đánh giá lại vào: {_structured_plan.next_review_at[:10]}")

                # --- LƯU & XUẤT KẾ HOẠCH ---
                st.markdown("---")
                col_save_plan, col_export_excel, col_export_pdf = st.columns(3)

                with col_save_plan:
                    if hasattr(llm_integration, 'data_warehouse') and llm_integration.data_warehouse:
                        # Auto-save: kế hoạch vừa tạo xong được lưu ngay, không cần bấm nút.
                        try:
                            plan_df = pd.DataFrame(
                                [
                                    {
                                        'student_id': student_id_llm,
                                        'created_at': datetime.now().isoformat(),
                                        'plan_content': plan,
                                        'predicted_gpa': predicted_gpa_llm,
                                        'ai_provider': selected_provider,
                                        'ai_model': model_name_input,
                                    }
                                ]
                            )

                            dataset_id, meta = llm_integration.data_warehouse.save_dataset(
                                plan_df,
                                dataset_name=f"study_plan_{student_id_llm}_{datetime.now().strftime('%Y%m%d%H%M')}",
                                description=f"Kế hoạch AI từ {llm_type}",
                                data_type="advisor",
                            )
                            st.success(f"✅ Đã tự động lưu kế hoạch vào kho! ID: `{dataset_id}`")
                        except Exception as e:
                            ui_kit.report_error("❌ Lỗi khi tự động lưu", e)

                with col_export_excel:
                    buffer_plan = BytesIO()
                    with pd.ExcelWriter(buffer_plan, engine='xlsxwriter') as writer:
                        plan_df_export = pd.DataFrame(
                            [
                                {
                                    'Student ID': student_id_llm,
                                    'Predicted GPA': predicted_gpa_llm,
                                    'Created At': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    'AI Provider': f"{selected_provider} ({model_name_input})",
                                    'Study Plan': plan,
                                }
                            ]
                        )
                        plan_df_export.to_excel(writer, index=False, sheet_name='Study Plan')

                    st.download_button(
                        label="📥 Xuất Excel (.xlsx)",
                        data=buffer_plan.getvalue(),
                        file_name=f"study_plan_{student_id_llm}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.ms-excel",
                        key="export_plan_excel",
                        use_container_width=True,
                    )

                with col_export_pdf:
                    try:
                        from dss.services.pdf_certificate_service import generate_career_passport_pdf

                        _pdf_plan_bytes = generate_career_passport_pdf(
                            student_id=str(student_id_llm),
                            target_role="Lộ trình can thiệp học tập AI",
                            career_fit_score=float(predicted_gpa_llm * 10) if predicted_gpa_llm else 80.0,
                            career_readiness_score=75.0,
                            gap_size="Trung bình"
                            if risk_level == "trung bình"
                            else ("Nhỏ" if risk_level == "thấp" else "Lớn"),
                            four_week_plan=week_plan_ai if 'week_plan_ai' in locals() else None,
                        )
                        st.download_button(
                            label="📜 Xuất Chứng Nhận PDF",
                            data=_pdf_plan_bytes,
                            file_name=f"AI_Plan_Certificate_{student_id_llm}_{datetime.now().strftime('%Y%m%d')}.pdf",
                            mime="application/pdf",
                            key="export_plan_pdf",
                            use_container_width=True,
                        )
                    except Exception:
                        pass
            except Exception:
                _logger.exception("Tạo kế hoạch học tập thất bại (mã EDSS-PLAN-001).")
                ui_kit.error_state(
                    "Chưa tạo được kế hoạch học tập",
                    "Đã xảy ra lỗi khi tạo kế hoạch. Dữ liệu của bạn không bị thay đổi.",
                    support_hint="Vui lòng thử lại. Nếu lỗi lặp lại, liên hệ Quản trị viên và cung cấp mã EDSS-PLAN-001.",
                )


def _mask_key(raw_key: str) -> str:
    """Che gần hết ký tự của API key thật — CHỈ hiện 4 ký tự cuối để nhận diện
    (vd. đổi key có bị dùng nhầm không), không bao giờ hiện đủ key gốc."""
    if not raw_key:
        return "—"
    if len(raw_key) <= 4:
        return "•" * len(raw_key)
    return "•" * 10 + raw_key[-4:]


@require_role("Admin")
def ai_configuration_tab(llm_integration):
    """Cấu hình AI — trang riêng CHỈ Admin (đúng yêu cầu "role duy nhất được
    xem cấu hình provider kỹ thuật"). Đây là view THEO DÕI/đặt provider mặc
    định hệ thống (tái dùng nguyên `admin_ai_config.get/set/clear_default_
    provider` đã có, chặn RBAC ở tầng hàm từ trước) — không lặp lại form nhập
    key nhiều bước đã có trong tab Tư vấn AI (dành cho việc chọn provider CHO
    1 phiên chat cụ thể, mục đích khác với trang cấu hình hệ thống này).

    KHÔNG BAO GIỜ hiển thị API key thật dù đã có trong secrets/env — chỉ báo
    trạng thái Sẵn sàng/Chưa cấu hình + 4 ký tự cuối để đối chiếu.
    """
    ui_kit.page_header(
        "Cấu hình AI",
        subtitle="Nguồn AI dùng để diễn giải và cá nhân hoá câu trả lời. Khoá API không bao giờ được hiển thị.",
    )
    ui_kit.alert_box(
        "EduDSS vẫn hoạt động khi không có nguồn AI trực tuyến: tính toán điểm, quy tắc học vụ, dự đoán và tra cứu "
        "tài liệu không phụ thuộc vào nhà cung cấp AI. AI chỉ dùng để diễn giải và cá nhân hoá — không ra quyết định học vụ.",
        kind="info",
        title="Chế độ hoạt động khi thiếu AI",
    )

    _providers = [
        ("gemini", "Google Gemini"),
        ("groq", "Groq"),
        ("openai", "OpenAI"),
        ("ollama", "Ollama (máy chủ cục bộ)"),
    ]
    _default_cfg = admin_ai_config.get_default_provider()

    col_head, col_btn = st.columns([3, 1.3], vertical_alignment="bottom")
    with col_head:
        ui_kit.subsection_header(
            "Trạng thái provider",
            subtitle="\"Cấu hình\" chỉ đọc biến môi trường/secrets (không gửi request). \"Kiểm tra kết nối\" gửi 1 request "
            "tối thiểu tới từng provider — bấm thủ công để không tốn hạn mức mỗi lần tải trang.",
        )
    with col_btn:
        if st.button("Kiểm tra kết nối tất cả provider", key="ai_config_test_all", type="primary", width="stretch"):
            from dss.services import llm_gateway as _llm_gateway

            with st.spinner("Đang gọi thử từng provider..."):
                for _pkey, _ in _providers:
                    st.session_state[f"_admin_ai_health_{_pkey}"] = _llm_gateway.check_provider_health(_pkey).to_dict()
                    st.session_state[f"_admin_ai_health_{_pkey}_at"] = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
            st.rerun()

    _cols = st.columns(len(_providers), gap="small")
    for _col, (_pkey, _plabel) in zip(_cols, _providers):
        with _col:
            with st.container(border=True):
                ui_kit.card_title(_plabel)
                if _pkey == "ollama":
                    _config_html = ui_kit.badge_html("Không dùng khoá API", "neutral")
                else:
                    _configured = bool(llm_integration.get_api_key_from_secrets(_pkey))
                    _config_html = (
                        ui_kit.status_html("ready", "Đã có khoá")
                        if _configured
                        else ui_kit.status_html("not_configured")
                    )

                _health = st.session_state.get(f"_admin_ai_health_{_pkey}")
                _tested_at = st.session_state.get(f"_admin_ai_health_{_pkey}_at")
                if _health is None:
                    _conn_html = ui_kit.status_html("not_checked")
                elif _health["category"] == "NOT_CONFIGURED":
                    _conn_html = ui_kit.status_html("not_configured")
                else:
                    _is_ready = _health["category"] == "READY"
                    _conn_html = ui_kit.badge_html(
                        "Kết nối được" if _is_ready else "Không khả dụng",
                        "success"
                        if _is_ready
                        else ("warning" if _health["category"] == "BILLING_REQUIRED" else "danger"),
                    )
                st.markdown(
                    f"<div class='dss-kv'><span class='dss-kv-key'>Cấu hình</span><span class='dss-kv-value'>{_config_html}</span></div>"
                    f"<div class='dss-kv'><span class='dss-kv-key'>Kết nối</span><span class='dss-kv-value'>{_conn_html}</span></div>",
                    unsafe_allow_html=True,
                )
                if _health is not None:
                    st.caption(f"Model: {_health.get('model') or '—'}")
                    # Giữ dạng "Nhãn (CATEGORY)" — mã phân loại đọc được bằng máy (E2E so khớp).
                    st.caption(f"Kết quả: {_health['friendly_label']} ({_health['category']})")
                    if _tested_at:
                        st.caption(f"Kiểm tra lúc {_tested_at}")
                else:
                    st.caption("Chưa kiểm tra trong phiên này.")
                if _default_cfg and _default_cfg.get("provider_key") == _pkey:
                    ui_kit.render_badge(f"Mặc định hệ thống · {_default_cfg.get('model_name')}", "info")

    st.markdown("<div class='dss-spacer-24'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        ui_kit.card_title("Provider mặc định của hệ thống")
        st.caption(
            "Áp dụng cho mọi phiên Trợ lý AI khi người dùng không tự chọn provider. Chọn model cụ thể ở trang "
            "Trợ lý AI (mục \"Đặt làm mặc định hệ thống\"); trang này để xem và xoá mặc định."
        )
        if _default_cfg:
            st.markdown(
                f"<div class='dss-kv'><span class='dss-kv-key'>Mặc định hiện tại</span>"
                f"<span class='dss-kv-value'>{_default_cfg['provider_key']} / {_default_cfg['model_name']}</span></div>",
                unsafe_allow_html=True,
            )
            with st.container(key="danger_ai_config_clear"):
                if st.button("Xoá mặc định", key="ai_config_clear_default"):
                    admin_ai_config.clear_default_provider()
                    st.session_state.show_success_message = (
                        "Đã xoá provider mặc định — hệ thống quay lại tự dò provider."
                    )
                    st.rerun()
        else:
            st.caption("Chưa đặt mặc định — hệ thống tự dò theo thứ tự Ollama → Gemini → Groq → OpenAI.")
