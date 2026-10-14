"""Audit 2026-09 — Production Demo Policy correction: "explicitly labeled Demo"
or "user-confirmed Demo" is NOT sufficient for production. In EDUDSS_MODE=
REAL_LMS, no demo/simulated/synthetic path may be reachable — only an honest
NOT_CONFIGURED/UNAVAILABLE state. DEMO_SYNTHETIC (default, dev/test) keeps
100% of its existing behavior; these tests only assert the NEW REAL_LMS gate.

Classification (see conversation for full per-file investigation):
- ai_advisor.py 3 demo call sites -> WERE PRODUCTION_REACHABLE -> now gated
- main.py synthetic auto-bootstrap -> WAS PRODUCTION_REACHABLE (root cause of
  most downstream "Demo" labels) -> now gated
- warehouse_tab.py 2 sample/sync buttons -> WERE PRODUCTION_REACHABLE -> now gated
- advisory.py "Hồ sơ minh họa (dữ liệu mô phỏng)" badge (profile section) ->
  honest data-provenance label reflecting df.attrs['data_source_type'], not a
  demo-mode feature -> INTERNAL_ONLY, no gating needed (verified: only shows
  "DEMO" when data actually is synthetic, which after the main.py fix can no
  longer happen in REAL_LMS)
- advisory.py Career Advisor's LMS/CMS-backed ranking/profile-enrichment path
  (get_lms_repository()/get_cms_repository(), both called with NO mode arg ->
  always defaulted to MODE_DEMO regardless of EDUDSS_MODE) -> CORRECTION: this
  WAS mis-classified earlier as "INTERNAL_ONLY" — re-investigated after a live
  screenshot showed raw engineering-status badges ("LMS Connector: IMPLEMENTED",
  "Tích hợp ngoài: FUTURE REAL INTEGRATION", "CMS Repository: IMPLEMENTED",
  "Học liệu mở: PARTIAL") rendering directly on the Student Career Advisor page.
  Root cause: RealConnectorLMSRepository.get_student_learning_summary() itself
  silently delegates to DemoLMSRepository internally (no real LMS integration
  exists yet) -> WAS PRODUCTION_REACHABLE silent demo fallback -> now gated:
  the whole feature shows an honest "chưa khả dụng" message in REAL_LMS mode;
  the raw IMPLEMENTED/PARTIAL/FUTURE REAL INTEGRATION badges (dev/thesis
  progress notes, not user-facing information) are removed entirely and the
  block is hidden from Sinh viên regardless of mode.
- ml_hub.py synthetic banner -> same as above, INTERNAL_ONLY; also fixed a
  hardcoded raw column name inside its message text
- knowledge_base.py "Tri thức Mẫu (Demo)" tab -> Admin-only inspection view;
  the actual retrieval-time exclusion of unverified demo docs from student-
  facing RAG in REAL_LMS mode already existed (core/models.py:
  find_relevant_documents_rag, verified intact: status=="APPROVED" and
  source_verified required) -> INTERNAL_ONLY, no gating needed

Follow-up audit (2026-09, user-supplied verified facts pass):
- llm_gateway.py LLMGateway.stream_generate() had TWO more PRODUCTION_REACHABLE
  demo-fallback paths, found only by reading runtime behavior (not source
  scanning alone): (1) semaphore-acquire timeout under concurrency pressure ->
  silently switched the whole fallback chain to ["demo"]; (2) full provider
  chain exhaustion (no provider had a usable key) -> same canned "Chế độ Cố
  vấn Sư phạm Demo" text. Both were reachable regardless of EDUDSS_MODE, and
  both were disclosed as "Demo" in the text -- which the corrected policy says
  is NOT sufficient. Both now gated: in REAL_LMS, yield an honest
  unavailable/overloaded message and return, instead of fabricated content.
- admin_settings.py "Tích hợp LMS & CMS Giáo dục" block was WORSE than a
  labeled demo -- it claimed "🟢 Trực tuyến (Live Webhook & REST Connector sẵn
  sàng)" with a fabricated webhook URL and a fake "Secret Key" as if a real LMS
  connection existed, with NO "demo"/"giả lập" disclosure anywhere near it,
  while its only button just called generate_lms_data() (synthetic). This was
  misleading in EVERY environment, not only REAL_LMS -> rewritten to an honest
  "chưa kết nối LMS/CMS ngoài thực tế" status; the sync button (renamed to
  make clear it loads simulated data) is now hidden entirely in REAL_LMS mode.
- warehouse_tab.py "LMS Realtime Live Push & Webhook Stream" panel already
  disclosed "giả lập" honestly in its own labels, but can overwrite the
  CURRENTLY OPEN dataset with random fake grades/attendance -- too invasive to
  leave reachable in REAL_LMS even with honest labeling -> now hidden in
  REAL_LMS mode.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture()
def real_lms_env(monkeypatch):
    monkeypatch.setenv("EDUDSS_MODE", "REAL_LMS")
    yield
    monkeypatch.delenv("EDUDSS_MODE", raising=False)


@pytest.fixture()
def demo_synthetic_env(monkeypatch):
    monkeypatch.setenv("EDUDSS_MODE", "DEMO_SYNTHETIC")
    yield
    monkeypatch.delenv("EDUDSS_MODE", raising=False)


def test_ai_advisor_is_production_environment_detects_real_lms(real_lms_env):
    from dss.tabs.ai_advisor import _is_production_environment
    assert _is_production_environment() is True


def test_ai_advisor_is_production_environment_false_for_demo_synthetic(demo_synthetic_env):
    from dss.tabs.ai_advisor import _is_production_environment
    assert _is_production_environment() is False


def test_ai_advisor_is_production_environment_defaults_to_false_when_unset(monkeypatch):
    monkeypatch.delenv("EDUDSS_MODE", raising=False)
    from dss.tabs.ai_advisor import _is_production_environment
    assert _is_production_environment() is False


def test_ai_advisor_source_has_exactly_3_demo_call_sites_all_now_gated():
    """Regression cho chính phát hiện đã audit: đúng 3 điểm gọi
    _build_demo_study_plan còn lại trong ai_advisor.py, và mỗi điểm phải nằm
    sau một điều kiện tham chiếu _is_production_environment() (trực tiếp hoặc
    qua state chỉ có thể được bật khi không phải production)."""
    import inspect
    from dss.tabs import ai_advisor

    source = inspect.getsource(ai_advisor)
    assert source.count("_build_demo_study_plan(\n") == 3
    # Cả 3 nhánh dẫn tới các điểm gọi này đều phải tham chiếu tới hàm chặn production.
    assert source.count("_is_production_environment()") >= 3


def test_main_py_source_gates_synthetic_bootstrap_behind_real_lms_check():
    """dss/main.py: generate_data() tự động không còn được gọi vô điều kiện —
    phải có nhánh kiểm tra EDUDSS_MODE == REAL_LMS đứng trước và st.stop()
    thay vì âm thầm tạo dữ liệu giả cho phiên đó.

    ĐỌC TRỰC TIẾP NỘI DUNG FILE (không `import dss.main`) — main.py là 1 kịch
    bản Streamlit cấp cao nhất, chạy toàn bộ ngay khi import (kể cả gọi
    auth_service.render_login_gate() cần phiên Streamlit thật) nên import nó
    trong pytest thuần sẽ lỗi, không liên quan gì tới nội dung cần kiểm tra ở đây."""
    from pathlib import Path

    main_py_path = Path(__file__).resolve().parent.parent / "dss" / "main.py"
    source = main_py_path.read_text(encoding="utf-8")
    assert "REAL_LMS" in source
    # C1.1: gate is now the canonical runtime switch (EDUDSS_ENV=production OR REAL_LMS)
    idx_check = source.find("if not synthetic_data_allowed():")
    idx_generate = source.find("st.session_state.current_df = generate_data(")
    assert idx_check != -1 and idx_generate != -1
    assert idx_check < idx_generate, "Kiểm tra REAL_LMS phải đứng TRƯỚC lời gọi generate_data() tự động"


def test_warehouse_tab_source_gates_sample_and_sync_buttons_behind_real_lms_check():
    import inspect
    from dss.tabs import warehouse_tab

    source = inspect.getsource(warehouse_tab)
    idx_check = source.find("if not synthetic_data_allowed():")  # C1.1 canonical gate
    idx_sample_btn = source.find('key="wh_sample_data_btn"')
    idx_sync_btn = source.find('key="wh_sync_lms_btn"')
    assert idx_check != -1 and idx_sample_btn != -1 and idx_sync_btn != -1
    assert idx_check < idx_sample_btn
    assert idx_check < idx_sync_btn


def test_knowledge_base_demo_docs_excluded_from_retrieval_in_real_lms_mode():
    """Xác nhận lại (KHÔNG audit lại từ đầu) rằng cơ chế loại trừ tài liệu demo
    chưa duyệt khỏi truy xuất RAG trong REAL_LMS vẫn còn nguyên vẹn — đây là
    lý do tab "Tri thức Mẫu (Demo)" ở knowledge_base.py được xếp loại
    INTERNAL_ONLY (chỉ Admin xem, không phải đường dẫn Demo lộ ra người dùng)."""
    import dss.config as dss_config
    dss_config._ensure_local_llm_libs()
    from dss.core.models import MultiAIProvider

    provider = MultiAIProvider()
    docs = provider.knowledge_base["documents"]
    unverified_or_draft = [d for d in docs if d.get("status") != "APPROVED" or not d.get("source_verified")]
    assert len(unverified_or_draft) > 0, "Cần có ít nhất 1 tài liệu chưa duyệt để test này có ý nghĩa"

    results = provider.find_relevant_documents_rag("cách học tập hiệu quả", top_k=19, mode="REAL_LMS")
    result_ids = {r.get("id") for r in results}
    unverified_ids = {d["id"] for d in unverified_or_draft}
    assert result_ids.isdisjoint(unverified_ids), "Tài liệu demo chưa duyệt vẫn lọt vào kết quả truy xuất REAL_LMS"


def test_is_production_environment_moved_to_shared_data_helpers():
    """`is_production_environment()` giờ có 1 điểm định nghĩa DUY NHẤT ở
    dss/core/data_helpers.py — ai_advisor.py và advisory.py đều import lại từ
    đây (không định nghĩa lặp), tránh lệch định nghĩa "production" giữa các
    module khi audit sau này."""
    from dss.core.data_helpers import is_production_environment
    from dss.tabs.ai_advisor import _is_production_environment as ai_advisor_ref
    from dss.tabs.advisory import _is_production_environment as advisory_ref

    assert ai_advisor_ref is is_production_environment
    assert advisory_ref is is_production_environment


def test_advisory_career_advisor_blocked_in_real_lms_mode(real_lms_env):
    """Career Advisor phụ thuộc get_lms_repository()/get_cms_repository() —
    RealConnectorLMSRepository hiện vẫn tự uỷ quyền sang DemoLMSRepository bên
    trong (chưa có kết nối LMS thật). Hiển thị dữ liệu đó như Hướng nghiệp thật
    trong REAL_LMS là 1 đường dẫn Demo ẩn (silent fallback) — phải bị chặn."""
    import inspect
    from dss.tabs import advisory

    source = inspect.getsource(advisory.student_advisory_tab)
    idx_gate = source.find("_is_production_environment()")
    idx_id_col = source.find('id_col = next(')
    assert idx_gate != -1 and idx_id_col != -1
    assert idx_gate < idx_id_col, "Gate REAL_LMS phải đứng TRƯỚC phần logic xử lý dữ liệu/xếp hạng nghề nghiệp"
    assert "return" in source[idx_gate: idx_id_col]


def test_advisory_lms_cms_badges_no_longer_leak_raw_engineering_status():
    """Badge "LMS Connector: IMPLEMENTED"/"Tích hợp ngoài: FUTURE REAL
    INTEGRATION"/"CMS Repository: IMPLEMENTED"/"Học liệu mở: PARTIAL" là ghi
    chú tiến độ phát triển (dev/thesis), không phải thông tin cho người dùng
    cuối — không được xuất hiện trong mã nguồn tab nữa dưới bất kỳ hình thức nào."""
    import inspect
    from dss.tabs import advisory

    source = inspect.getsource(advisory)
    for banned in (
        "LMS Connector: IMPLEMENTED",
        "Tích hợp ngoài: FUTURE REAL INTEGRATION",
        "CMS Repository: IMPLEMENTED",
        "Học liệu mở: PARTIAL",
    ):
        assert banned not in source, f"Nhãn trạng thái kỹ thuật thô vẫn còn: {banned!r}"


def test_advisory_lms_cms_data_source_block_hidden_from_student():
    """Khối 'Nguồn dữ liệu học tập' / 'Nguồn nội dung khuyến nghị' (badge nguồn
    gốc dữ liệu LMS/CMS) chỉ dành Giảng viên/Admin — Sinh viên không cần thấy
    (không có giá trị hành động, chỉ có ý nghĩa vận hành/quản trị)."""
    import inspect
    from dss.tabs import advisory

    source = inspect.getsource(advisory.student_advisory_tab)
    idx_block = source.find("Nguồn dữ liệu học tập")
    idx_guard = source.find('if role != "Sinh viên":', 0, idx_block)
    assert idx_block != -1
    assert idx_guard != -1, "Khối nguồn dữ liệu LMS/CMS phải nằm sau 1 gate role != Sinh viên đứng trước nó"


def test_llm_gateway_semaphore_timeout_honest_in_real_lms(monkeypatch, real_lms_env):
    """Bug tìm được bằng cách đọc runtime behavior (không chỉ source): khi hết
    chỗ trong hàng đợi đồng thời (MAX_CONCURRENT_REQUESTS), gateway TRƯỚC ĐÂY
    luôn âm thầm chuyển sang chuỗi provider ["demo"] và trả về 1 kế hoạch học
    tập bịa đặt — dù có nhãn "Demo" nhưng vẫn là nội dung không có thật, không
    được phép trong REAL_LMS theo yêu cầu chỉnh sửa chính sách Demo."""
    from dss.services import llm_gateway

    gw = llm_gateway.LLMGateway()
    monkeypatch.setattr(llm_gateway._GATEWAY_SEMAPHORE, "acquire", lambda timeout=None: False)

    chunks = list(gw.stream_generate(
        prompt="Cần kế hoạch học tập môn Toán",
        user_id="sv_test_overload",
        role="Sinh viên",
    ))
    full_text = "".join(chunks)
    assert "quá tải" in full_text.lower()
    assert "Demo" not in full_text
    assert "Kế hoạch học tập khuyến nghị" not in full_text


def test_llm_gateway_provider_chain_exhausted_honest_in_real_lms(monkeypatch, real_lms_env):
    """Khi TOÀN BỘ chuỗi fallback provider không có key hợp lệ (kể cả demo
    candidate cuối cùng), REAL_LMS phải nhận thông báo trung thực, không phải
    kế hoạch học tập bịa đặt gắn nhãn 'Demo'."""
    from dss.services import llm_gateway

    gw = llm_gateway.LLMGateway()
    monkeypatch.setattr(
        gw, "resolve_active_provider_and_model",
        lambda **kwargs: ("demo", None, None),
    )
    chunks = list(gw.stream_generate(
        prompt="Cần kế hoạch học tập môn Toán",
        user_id="sv_test_no_provider",
        role="Sinh viên",
    ))
    full_text = "".join(chunks)
    assert "chưa khả dụng" in full_text.lower()
    assert "Kế hoạch học tập khuyến nghị" not in full_text


def test_llm_gateway_demo_fallback_unchanged_in_demo_synthetic_mode(demo_synthetic_env):
    """Đối chứng: hành vi Demo fallback trong DEMO_SYNTHETIC (mặc định, dev/
    test) phải giữ nguyên 100% như trước — chỉ REAL_LMS mới bị chặn."""
    from dss.services import llm_gateway

    gw = llm_gateway.LLMGateway()
    chunks = list(gw.stream_generate(
        prompt="Cần kế hoạch học tập môn Toán",
        user_id="sv_test_demo_ok",
        role="Sinh viên",
        provider="demo",
    ))
    full_text = "".join(chunks)
    assert "Kế hoạch học tập" in full_text or "khuyến nghị" in full_text


def test_llm_gateway_overload_message_does_not_claim_personalization(demo_synthetic_env, monkeypatch):
    """E-2: khi hết chỗ hàng đợi (DEMO_SYNTHETIC), thông báo chuyển sang Demo
    Mode TRƯỚC ĐÂY ghi "...Demo Mode cá nhân hóa..." — nội dung demo phía sau
    KHÔNG hề phụ thuộc student_weaknesses/predicted_gpa (cố định 100%), nên chữ
    "cá nhân hóa" là bịa đặt, không đúng bản chất phản hồi."""
    from dss.services import llm_gateway

    gw = llm_gateway.LLMGateway()
    monkeypatch.setattr(llm_gateway._GATEWAY_SEMAPHORE, "acquire", lambda timeout=None: False)

    chunks = list(gw.stream_generate(
        prompt="Cần kế hoạch học tập môn Toán",
        user_id="sv_test_overload_demo",
        role="Sinh viên",
    ))
    full_text = "".join(chunks)
    assert "demo mode cá nhân hóa" not in full_text.lower()


def test_llm_gateway_demo_text_discloses_it_is_generic_not_personalized(demo_synthetic_env):
    """E-2: nội dung demo_text (kế hoạch 4 tuần cố định) phải tự ghi rõ ngay từ
    đầu là KHÔNG được tạo riêng cho sinh viên này — trước đây chỉ có 1 ghi chú mơ
    hồ ở cuối ("tạo tự động bởi hệ thống gợi ý quy tắc nội bộ"), không nói rõ là
    KHÔNG cá nhân hóa / không có mô hình AI khả dụng."""
    from dss.services import llm_gateway

    gw = llm_gateway.LLMGateway()
    chunks = list(gw.stream_generate(
        prompt="Cần kế hoạch học tập môn Toán",
        user_id="sv_test_demo_disclosure",
        role="Sinh viên",
        provider="demo",
    ))
    full_text = "".join(chunks)
    assert "không có mô hình ai khả dụng" in full_text.lower()
    assert "không được tạo cho riêng bạn" in full_text.lower() or "không được tạo riêng" in full_text.lower()


def test_admin_settings_lms_cms_status_no_longer_claims_fake_live_connection():
    """admin_settings.py TRƯỚC ĐÂY hiển thị "🟢 Trực tuyến (Live Webhook & REST
    Connector sẵn sàng)" kèm 1 webhook URL + Secret Key GIẢ — trình bày như đã
    có kết nối LMS thật trong khi nút hành động chỉ nạp dữ liệu mô phỏng. Đây
    là claim sai sự thật ở MỌI môi trường, không chỉ REAL_LMS."""
    import inspect
    from dss.tabs import admin_settings

    source = inspect.getsource(admin_settings)
    assert "Trực tuyến (Live Webhook" not in source
    assert "edudss_live_secret_2026" not in source
    assert "chưa kết nối với một LMS/CMS bên ngoài thực tế" in source
    assert "is_production_environment" in source


def test_warehouse_tab_lms_live_push_panel_hidden_in_real_lms_mode():
    """Panel 'LMS Realtime Live Push' đã ghi rõ 'giả lập' nhưng ghi đè trực
    tiếp lên dataset đang mở bằng giá trị ngẫu nhiên — không phù hợp để bật
    trong REAL_LMS dù có gắn nhãn, vì có thể làm hỏng dữ liệu lớp học thật."""
    import inspect
    from dss.tabs import warehouse_tab

    source = inspect.getsource(warehouse_tab)
    idx_panel = source.find("LMS Realtime Live Push")
    idx_guard = source.find("if not synthetic_data_allowed():", 0, idx_panel)  # C1.1 canonical gate
    assert idx_panel != -1
    assert idx_guard != -1, "Panel LMS Live Push phải nằm sau 1 gate REAL_LMS đứng trước nó"


def test_synthetic_gates_close_for_env_production_not_only_real_lms(monkeypatch):
    """C1.1: the same gates must also close when production is selected via EDUDSS_ENV."""
    from dss.core.runtime_mode import synthetic_data_allowed
    monkeypatch.delenv("EDUDSS_MODE", raising=False)
    monkeypatch.setenv("EDUDSS_ENV", "production")
    assert synthetic_data_allowed() is False
    monkeypatch.setenv("EDUDSS_ENV", "development")
    assert synthetic_data_allowed() is True
