"""Trang "Quản lý tri thức (RAG)" — CHỈ Admin (xem `dss/core/roles.py: TAB_ACCESS`).

Hỗ trợ quản trị tri thức cấp trường (LMS-scale):
- Phân tách tri thức theo Namespace: student_learning, lecturer_support, admin_operations
- Xem tài liệu Demo gốc (19 tài liệu) và tài liệu nạp sản xuất
- Nạp tài liệu mới thật (Production Ingestion): PDF, DOCX, PPTX, TXT/Markdown, LMS JSON
- Đường ống phân đoạn ngữ nghĩa (Semantic Chunking) và lưu trữ vào Vector Store
"""

import pandas as pd
import streamlit as st

from dss.config import *  # noqa: F403
from dss.security.upload_security import UploadValidationError, read_upload_within_size_limit, safe_document_name
from dss.services import (
    auth_service,
    cms_lecture_repository,
    document_approval_service,
    document_ingestion,
    knowledge_base_admin,
    rag_namespaces,
    vector_store,
)
from dss.services import document_governance as gov
from dss.services import (
    source_classification as srcclass,
)
from dss.tabs import ui_kit

_KB_DOCUMENT_EXTENSIONS = {".txt", ".md", ".docx", ".pptx", ".pdf", ".json"}

_KB_DELETE_RESULT_KEY = "_kb_delete_result"


@st.dialog("Xóa tài liệu?")
def _confirm_delete_document_dialog(document_id: str, title: str, namespace: str) -> None:
    """Hộp thoại xác nhận xóa (KB-CRUD-001) — không xóa ngay từ 1 cú click lỡ tay."""
    st.write(f"Xóa tài liệu **\"{title}\"**?")
    st.caption(
        "Tài liệu và dữ liệu truy xuất liên quan sẽ bị xóa khỏi Knowledge Base. Thao tác này không thể hoàn tác."
    )
    col_cancel, col_confirm = st.columns(2)
    with col_cancel:
        if st.button("Hủy", key=f"kb_delete_cancel_{document_id}", width="stretch"):
            st.rerun()
    with col_confirm:
        if st.button("Xóa tài liệu", key=f"kb_delete_confirm_{document_id}", type="primary", width="stretch"):
            result = knowledge_base_admin.delete_document_safely(document_id, namespace=namespace)
            st.session_state[_KB_DELETE_RESULT_KEY] = result
            st.rerun()


def knowledge_base_tab(llm_integration):
    # FINAL PRODUCTION GAP CLOSURE (Phần 21/41): bỏ "(RAG & Knowledge Base)" —
    # thuật ngữ kỹ thuật không cần thiết ở tiêu đề trang.
    ui_kit.section_header(
        "Tài liệu",
        subtitle="Quản lý các không gian tri thức phân quyền cho sinh viên, giảng viên và quản trị hệ thống.",
    )

    # ---------------------------------------------------------------------
    # TỔNG QUAN PHÂN LOẠI NGUỒN (Mục B16) — Admin phải thấy NGAY, không phải
    # đào sâu vào từng tab, có bao nhiêu tài liệu thuộc mỗi nhóm nguồn. Không
    # gộp thành 1 tổng duy nhất dễ gây hiểu lầm "toàn bộ đều đáng tin như
    # nhau" — tách rõ course material / supplementary / demo.
    # ---------------------------------------------------------------------
    try:
        _demo_documents = (llm_integration.knowledge_base or {}).get("documents", [])
    except Exception:
        _demo_documents = []
    try:
        _lessons = cms_lecture_repository.list_lessons()
    except Exception:
        _lessons = []

    _n_course_material = len(_lessons)
    _n_supplementary = sum(
        1 for d in _demo_documents if srcclass.classify_document(d) == srcclass.SUPPLEMENTARY_REFERENCE
    )
    _n_demo = sum(1 for d in _demo_documents if srcclass.classify_document(d) == srcclass.DEMO)
    ui_kit.kpi_row(
        [
            (
                f"🎓 {srcclass.SOURCE_LABEL_VI[srcclass.COURSE_MATERIAL]}",
                _n_course_material,
                "Do Giảng viên tải lên qua CMS",
                "success",
            ),
            (
                f"📖 {srcclass.SOURCE_LABEL_VI[srcclass.SUPPLEMENTARY_REFERENCE]}",
                _n_supplementary,
                "Có tác giả/nghiên cứu thật, không gắn môn học cụ thể",
                "warning",
            ),
            (
                f"🧪 {srcclass.SOURCE_LABEL_VI[srcclass.DEMO]}",
                _n_demo,
                "Chỉ phục vụ minh họa/kiểm thử — không phải bằng chứng học thuật",
                None,
            ),
        ]
    )
    st.caption(
        "Learning Explainer (AI giải thích bài học cho Sinh viên) CHỈ truy xuất từ "
        f"**{srcclass.SOURCE_LABEL_VI[srcclass.COURSE_MATERIAL]}** đúng môn/bài đang học — "
        "không bao giờ dùng Dữ liệu demo để trả lời câu hỏi về bài giảng."
    )
    st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)

    tab_course, tab_demo, tab_namespaces, tab_upload = st.tabs(
        [
            "🎓 Tài liệu môn học (CMS)",
            "📖 Nguồn tham khảo & Demo",
            "🗂️ Không Gian Tri Thức (Namespaces)",
            "📤 Nạp Tài Liệu Mới (Ingestion Pipeline)",
        ]
    )

    # =========================================================================
    # TAB MỚI: TÀI LIỆU MÔN HỌC (CMS) — Mục B4/B17: Admin cần thấy tổng quan
    # tài liệu THẬT do Giảng viên tải lên, tách biệt hoàn toàn khỏi 19 tài
    # liệu demo. CHỈ XEM — quản lý/chỉnh sửa chi tiết vẫn ở đúng chỗ hiện có
    # (trang "AI Giải thích Bài giảng" của Giảng viên), tránh 2 nơi cùng có
    # hành động dễ gây nhầm "sửa ở đâu mới đúng" (đúng nguyên tắc đã áp dụng
    # cho Model Registry).
    # =========================================================================
    with tab_course:
        st.caption(
            "Đây là nội dung môn học DO GIẢNG VIÊN CUNG CẤP thật (không phải kết nối CMS "
            "ngoài) — nguồn chính cho AI Giải thích Bài giảng. Quản lý chi tiết (nạp bài "
            "mới, chính sách AI theo bài học...) nằm ở trang \"AI Giải thích Bài giảng\" "
            "của Giảng viên."
        )
        if not _lessons:
            ui_kit.empty_state(
                "Chưa có tài liệu môn học nào được Giảng viên tải lên.",
                hint="Giảng viên nạp bài giảng ở trang \"AI Giải thích Bài giảng\" > \"Nạp & Quản lý\".",
            )
        else:
            _course_rows = [
                {
                    "Môn học": l.course_id,
                    "Bài giảng": l.title,
                    "Giảng viên": l.lecturer_id,
                    "Loại": srcclass.SOURCE_LABEL_VI[srcclass.COURSE_MATERIAL],
                    "Nguồn chính thức": "Có" if l.official_source else "Chưa đánh dấu",
                    "Số phiên bản": len(l.versions),
                    "AI đang bật": "Có" if l.ai_enabled else "Không",
                }
                for l in _lessons
            ]
            st.dataframe(pd.DataFrame(_course_rows), width="stretch", hide_index=True)

    # =========================================================================
    # TAB: NGUỒN THAM KHẢO & DEMO (trước đây "Tri thức Mẫu (Demo Knowledge)")
    # Mục B6: không trình bày GEN_REF như một trích dẫn học thuật thật; Mục
    # B15: phân loại nguồn hiển thị rõ ràng, không mập mờ.
    # =========================================================================
    with tab_demo:
        if not _demo_documents:
            ui_kit.empty_state("Không đọc được kho tài liệu RAG.", hint="Kiểm tra lại khởi tạo AIIntegration.")
        else:
            subjects = sorted({d.get("subject", "—") for d in _demo_documents})
            ui_kit.kpi_row(
                [
                    ("Tổng số tài liệu", len(_demo_documents)),
                    ("Chủ đề kiến thức", len(subjects)),
                    ("Mô hình nhúng mặc định", "all-MiniLM-L6-v2"),
                ]
            )
            st.caption(
                "Dùng để chuyển nội dung tài liệu thành vector phục vụ tìm kiếm ngữ nghĩa — không phải mô hình sinh câu trả lời."
            )
            st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)

            _rows = []
            for d in _demo_documents:
                _cat = srcclass.classify_document(d)
                _rows.append(
                    {
                        "ID": d.get("id", "—"),
                        "Tiêu đề": d.get("title", "—"),
                        "Chủ đề": d.get("subject", "—"),
                        "Phân loại nguồn": srcclass.SOURCE_LABEL_VI[_cat],
                        "Từ khoá": ", ".join(d.get("tags", []) or []),
                    }
                )
            _df_docs = pd.DataFrame(_rows)
            st.dataframe(_df_docs, width="stretch", hide_index=True, height=min(70 + 36 * len(_rows), 460))

            with st.expander("🔍 Xem nội dung chi tiết + nguồn từng tài liệu", expanded=False):
                for d in _demo_documents:
                    _cat = srcclass.classify_document(d)
                    st.markdown(f"**{d.get('title', '—')}** (`{d.get('id', '—')}`)")
                    ui_kit.render_badge(srcclass.SOURCE_LABEL_VI[_cat], kind=srcclass.classification_badge_kind(_cat))
                    st.caption(d.get("content", ""))
                    if _cat == srcclass.DEMO:
                        # Mục B6 — KHÔNG trình bày GEN_REF như 1 trích dẫn học thuật thật.
                        st.caption("Nguồn: Dữ liệu demo nội bộ · Mục đích: Minh họa chức năng truy xuất RAG.")
                    else:
                        st.caption(f"Nguồn tham khảo: {d.get('reference', '—')}")
                    st.markdown("---")

    # =========================================================================
    # TAB 2: KHÔNG GIAN TRI THỨC (NAMESPACES)
    # =========================================================================
    with tab_namespaces:
        selected_ns = st.selectbox(
            "Chọn Không gian Tri thức (Namespace):",
            [
                rag_namespaces.NAMESPACE_STUDENT_LEARNING,
                rag_namespaces.NAMESPACE_LECTURER_SUPPORT,
                rag_namespaces.NAMESPACE_ADMIN_OPERATIONS,
            ],
            format_func=lambda x: {
                rag_namespaces.NAMESPACE_STUDENT_LEARNING: "🧑‍🎓 student_learning (Học tập & Bài giảng SV)",
                rag_namespaces.NAMESPACE_LECTURER_SUPPORT: "👨‍🏫 lecturer_support (Nghiệp vụ Sư phạm & Lớp học)",
                rag_namespaces.NAMESPACE_ADMIN_OPERATIONS: "⚙️ admin_operations (Vận hành & Kỹ thuật Hệ thống)",
            }.get(x, x),
        )

        # Hiển thị kết quả của thao tác xóa gần nhất (nếu có) — TRUNG THỰC theo
        # đúng status trả về, không bao giờ hiển thị thành công giả (A3).
        pending_result = st.session_state.pop(_KB_DELETE_RESULT_KEY, None)
        if pending_result:
            _status = pending_result.get("status")
            _msg = pending_result.get("message", "")
            if _status == knowledge_base_admin.STATUS_SUCCESS:
                st.success(f"✅ {_msg}")
            elif (
                _status == knowledge_base_admin.STATUS_NOT_FOUND
                or _status == knowledge_base_admin.STATUS_UNSUPPORTED
                or _status == knowledge_base_admin.STATUS_BLOCKED_REFERENCED
            ):
                st.warning(f"⚠️ {_msg}")
            else:  # error hoặc bất kỳ trạng thái không mong đợi nào khác
                st.error(f"❌ {_msg}")

        vstore = vector_store.get_vector_store(namespace=selected_ns)
        docs_in_ns = vstore.list_documents()

        # =====================================================================
        # FINAL REMEDIATION PASS Mục 4 (2026-09): nạp có kiểm soát 19 tài liệu
        # mẫu nội bộ (legacy_knowledge_seed) vào KHO THẬT — CHỈ khi Admin chủ
        # động bấm, KHÔNG tự động chạy ở bất kỳ đâu khác (audit code xác nhận
        # `seed_legacy_knowledge_base_documents` không có điểm gọi nào khác
        # trong dss/). Luôn nạp ở trạng thái PENDING_REVIEW (idempotent, không
        # tạo bản trùng) — bấm nút này KHÔNG duyệt bất kỳ tài liệu nào, chỉ đưa
        # chúng vào hàng đợi "Chờ duyệt" bên dưới để Admin tự xem xét từng tài
        # liệu một, đúng quy trình như tài liệu do người dùng thật tải lên.
        if selected_ns == rag_namespaces.NAMESPACE_STUDENT_LEARNING:
            with st.expander("🌱 Nạp tài liệu mẫu nội bộ (19 tài liệu cũ) — cần duyệt lại", expanded=False):
                st.caption(
                    "Chỉ dùng cho môi trường demo/thử nghiệm. Tài liệu được nạp ở trạng thái "
                    "**Chờ duyệt** — KHÔNG tự động duyệt, KHÔNG thể được Tư vấn AI trích dẫn "
                    "cho tới khi bạn tự xem xét và duyệt từng tài liệu ở hàng đợi bên dưới."
                )
                if st.button("Nạp tài liệu mẫu (Chờ duyệt)", key="kb_seed_legacy_docs"):
                    from dss.services import legacy_knowledge_seed

                    try:
                        n = legacy_knowledge_seed.seed_legacy_knowledge_base_documents(llm_integration)
                        st.success(
                            f"Đã nạp {n} tài liệu mới vào hàng đợi Chờ duyệt (tài liệu đã nạp trước đó được giữ nguyên, không nạp trùng)."
                        )
                        st.rerun()
                    except Exception:
                        st.error("Lỗi khi nạp tài liệu mẫu. Vui lòng thử lại hoặc liên hệ quản trị viên.")

        # =====================================================================
        # NHÓM F: HÀNG ĐỢI "CHỜ DUYỆT" — tài liệu tải lên qua tab "Nạp Tài Liệu
        # Mới" LUÔN bắt đầu ở PENDING_REVIEW (document_governance) và KHÔNG
        # BAO GIỜ dùng được cho trích dẫn (rag_service.retrieve_unified_context)
        # cho tới khi được duyệt Ở ĐÂY. FINAL REMEDIATION PASS Mục 3: Giảng
        # viên giờ có trang riêng "📄 Duyệt tài liệu" (hẹp hơn, chỉ tài liệu
        # môn mình phụ trách) — xem `lecturer_document_approval_tab` bên dưới;
        # trang này (Admin-only, TAB_ACCESS) vẫn là nơi duy nhất duyệt được
        # `quy_che` và mọi namespace/loại tài liệu khác.
        pending_docs = [d for d in docs_in_ns if d.get("status") == gov.STATUS_PENDING_REVIEW]
        if pending_docs:
            with st.container(border=True):
                st.markdown(f"##### 🕓 Chờ duyệt ({len(pending_docs)} tài liệu)")
                _actor = auth_service.current_user() or {}
                for d in pending_docs:
                    with st.expander(f"📄 {d.get('title', d.get('document_id'))} — `{d.get('document_id')}`"):
                        st.caption(
                            f"Loại: `{d.get('doc_type') or '—'}` · Môn: `{d.get('course_id') or '—'}` · "
                            f"Người tải lên: `{d.get('uploaded_by') or '—'}` · "
                            f"Nguồn/Đơn vị: {d.get('issuer') or '—'} · Căn cứ: {d.get('official_ref') or '—'}"
                        )
                        _note_key = f"kb_review_note_{d['document_id']}"
                        review_note = st.text_input("Ghi chú duyệt (bắt buộc nếu Từ chối):", key=_note_key)
                        col_approve, col_reject = st.columns(2)
                        with col_approve:
                            if st.button("✅ Duyệt", key=f"kb_approve_{d['document_id']}", width="stretch"):
                                ok, msg = document_approval_service.approve_document(
                                    document_id=d["document_id"],
                                    namespace=selected_ns,
                                    actor_username=_actor.get("username") or "unknown",
                                    actor_role=_actor.get("role") or "Admin",
                                    review_note=review_note or None,
                                )
                                (st.success if ok else st.error)(msg)
                                if ok:
                                    st.rerun()
                        with col_reject:
                            if st.button("❌ Từ chối", key=f"kb_reject_{d['document_id']}", width="stretch"):
                                ok, msg = document_approval_service.reject_document(
                                    document_id=d["document_id"],
                                    namespace=selected_ns,
                                    actor_username=_actor.get("username") or "unknown",
                                    actor_role=_actor.get("role") or "Admin",
                                    review_note=review_note,
                                )
                                (st.success if ok else st.error)(msg)
                                if ok:
                                    st.rerun()

        st.markdown(f"##### Danh sách tài liệu trong `{selected_ns}` ({len(docs_in_ns)} tài liệu)")
        if not docs_in_ns:
            st.info(f"Không gian `{selected_ns}` hiện chưa có tài liệu nạp ngoài. Vui lòng nạp thêm ở tab bên cạnh.")
        else:
            df_ns = pd.DataFrame(docs_in_ns)
            st.dataframe(df_ns, width="stretch", hide_index=True)

            # Hành động xóa gọn nhẹ (compact) thay vì 1 nút to trên mỗi dòng bảng,
            # để nhất quán với phong cách thiết kế hiện có của trang này.
            st.markdown("###### 🗑️ Xóa tài liệu")
            doc_labels = {
                f"{d.get('title', d.get('document_id'))} (`{d.get('document_id')}`)": d.get("document_id")
                for d in docs_in_ns
            }
            del_col1, del_col2 = st.columns([3, 1])
            with del_col1:
                picked_label = st.selectbox(
                    "Chọn tài liệu cần xóa:",
                    list(doc_labels.keys()),
                    key=f"kb_delete_pick_{selected_ns}",
                )
            with del_col2:
                if st.button("Xóa tài liệu", key=f"kb_delete_open_{selected_ns}", width="stretch"):
                    picked_id = doc_labels[picked_label]
                    _confirm_delete_document_dialog(picked_id, picked_label.split(" (`")[0], selected_ns)

    # =========================================================================
    # TAB 3: NẠP TÀI LIỆU MỚI (PRODUCTION INGESTION PIPELINE)
    # =========================================================================
    with tab_upload:
        st.markdown("##### 📥 Đường ống nạp tài liệu sản xuất (LMS Document Ingestion)")
        st.caption("Hỗ trợ tự động trích xuất nội dung, phân đoạn ngữ nghĩa (Semantic Chunking) và nhúng vector.")

        col_up1, col_up2 = st.columns(2)
        with col_up1:
            target_scope = st.selectbox(
                "Phạm vi phân quyền (Permission Scope):",
                rag_namespaces.ALL_NAMESPACES,
                index=0,
                format_func=lambda x: {
                    rag_namespaces.NAMESPACE_STUDENT_LEARNING: "student_learning (Sinh viên được xem)",
                    rag_namespaces.NAMESPACE_LECTURER_SUPPORT: "lecturer_support (Chỉ Giảng viên & Admin)",
                    rag_namespaces.NAMESPACE_ADMIN_OPERATIONS: "admin_operations (Chỉ Admin)",
                }.get(x, x),
            )
            doc_title = st.text_input("Tiêu đề tài liệu:", placeholder="vd: Đề cương chi tiết Giải tích 1")
            course_id = st.text_input("Mã học phần / Khóa học:", value="CS101")

        with col_up2:
            semester = st.text_input("Học kỳ:", value="2026.1")
            chunk_size = st.slider("Kích thước phân đoạn (Chunk Size - ký tự):", 200, 1000, 400, step=50)
            chunk_overlap = st.slider("Độ chồng lặp (Overlap - ký tự):", 20, 200, 80, step=10)

        uploaded_file = st.file_uploader(
            "Chọn tệp tài liệu để tải lên:",
            type=["txt", "md", "docx", "pptx", "pdf", "json"],
            help="Hỗ trợ TXT, Markdown, Word (.docx), PowerPoint (.pptx), PDF và LMS Content (.json)",
        )

        if st.button("🚀 Bắt đầu Nạp & Phân Đoạn Tài Liệu", type="primary", disabled=not uploaded_file):
            if not doc_title:
                st.warning("Vui lòng nhập tiêu đề tài liệu.")
            else:
                _spinner_msg = ui_kit.cold_start_aware_message(
                    llm_integration, "Đang trích xuất nội dung, phân đoạn ngữ nghĩa và tính toán vector..."
                )
                with st.spinner(_spinner_msg):
                    try:
                        safe_name, _ = safe_document_name(
                            getattr(uploaded_file, "name", None), allowed_extensions=_KB_DOCUMENT_EXTENSIONS
                        )
                        file_bytes = read_upload_within_size_limit(uploaded_file)
                        ingested = document_ingestion.ingest_document(
                            file_bytes=file_bytes,
                            file_name=safe_name,
                            title=doc_title,
                            course_id=course_id,
                            semester=semester,
                            permission_scope=target_scope,
                            chunk_size=chunk_size,
                            chunk_overlap=chunk_overlap,
                        )

                        # Tạo embedding cho từng chunk bằng model embedding của hệ thống
                        for c in ingested.chunks:
                            if llm_integration and hasattr(llm_integration, "get_embedding"):
                                c.embedding = llm_integration.get_embedding(c.content)

                        # Lưu vào Vector Store
                        target_vstore = vector_store.get_vector_store(namespace=target_scope)
                        saved_count = target_vstore.add_chunks(ingested.chunks)

                        st.success(
                            f"✅ Nạp tài liệu thành công! ID: `{ingested.document_id}` | "
                            f"Tổng số phân đoạn (chunks): {len(ingested.chunks)} | "
                            f"Đã lưu vào không gian: `{target_scope}` ({saved_count} chunks)."
                        )
                    except UploadValidationError as exc:
                        st.error(str(exc))
                    except Exception:
                        st.error("Lỗi khi nạp tài liệu. Vui lòng thử lại hoặc liên hệ quản trị viên.")


def lecturer_document_approval_tab() -> None:
    """ "📄 Duyệt tài liệu" — hàng đợi duyệt tài liệu HẸP dành riêng cho Giảng
    viên/CVHT (xem `dss/core/roles.py: TAB_ACCESS`).

    FINAL REMEDIATION PASS (Mục 3, đọc lập review 2026-09): backend duyệt
    tài liệu (`document_approval_service`) đã hỗ trợ vai trò Giảng viên từ
    đợt NHÓM F (chỉ duyệt được giao_trinh/bai_giang/de_cuong của MÔN MÌNH
    phụ trách trong CMS — xem `_lecturer_owns_course`), nhưng trước đợt này
    KHÔNG có lối vào UI nào cho Giảng viên: toàn bộ tab "Quản lý tri thức"
    chỉ Admin thấy được (TAB_ACCESS). Trang này CỐ TÌNH hẹp và tối giản để
    an toàn khi thêm mới:
    - CHỈ 2 namespace liên quan tới giảng dạy (student_learning,
      lecturer_support) — KHÔNG cho thấy admin_operations.
    - CHỈ gọi `document_approval_service` (không tự viết lại logic RBAC/
      trạng thái ở đây) — và service ĐÃ tự kiểm tra lại quyền một cách độc
      lập trong `approve_document`/`reject_document`, nên dù bộ lọc hiển thị
      ở đây có sai, backend vẫn từ chối hành động không được phép.
    - KHÔNG có nút xóa/nạp tài liệu mới/duyệt tài liệu ngoài phạm vi môn học
      (những chức năng đó vẫn CHỈ Admin làm được qua "Quản lý tri thức")."""
    ui_kit.section_header(
        "Duyệt tài liệu môn học",
        subtitle="Duyệt/từ chối tài liệu (đề cương, bài giảng, giáo trình) của các môn bạn phụ trách trước khi Tư vấn AI được phép trích dẫn.",
        icon="📄",
    )
    actor = auth_service.current_user() or {}
    actor_username = actor.get("username") or ""
    actor_role = actor.get("role") or "Giảng viên / CVHT"

    if not actor_username:
        st.warning("Không xác định được người dùng hiện tại — vui lòng đăng nhập lại.")
        return

    namespaces = [rag_namespaces.NAMESPACE_STUDENT_LEARNING, rag_namespaces.NAMESPACE_LECTURER_SUPPORT]
    total_pending = 0
    for ns in namespaces:
        pending_docs = document_approval_service.list_pending_documents_for_approver(
            ns,
            actor_username=actor_username,
            actor_role=actor_role,
        )
        total_pending += len(pending_docs)
        if not pending_docs:
            continue
        st.markdown(f"##### `{ns}` — {len(pending_docs)} tài liệu chờ duyệt")
        for d in pending_docs:
            with st.expander(f"📄 {d.get('title', d.get('document_id'))} — `{d.get('document_id')}`"):
                st.caption(
                    f"Loại: `{d.get('doc_type') or '—'}` · Môn: `{d.get('course_id') or '—'}` · "
                    f"Người tải lên: `{d.get('uploaded_by') or '—'}` · "
                    f"Nguồn/Đơn vị: {d.get('issuer') or '—'} · Căn cứ: {d.get('official_ref') or '—'}"
                )
                note_key = f"lecturer_kb_review_note_{d['document_id']}"
                review_note = st.text_input("Ghi chú duyệt (bắt buộc nếu Từ chối):", key=note_key)
                col_approve, col_reject = st.columns(2)
                with col_approve:
                    if st.button("✅ Duyệt", key=f"lecturer_kb_approve_{d['document_id']}", width="stretch"):
                        ok, msg = document_approval_service.approve_document(
                            document_id=d["document_id"],
                            namespace=ns,
                            actor_username=actor_username,
                            actor_role=actor_role,
                            review_note=review_note or None,
                        )
                        (st.success if ok else st.error)(msg)
                        if ok:
                            st.rerun()
                with col_reject:
                    if st.button("❌ Từ chối", key=f"lecturer_kb_reject_{d['document_id']}", width="stretch"):
                        ok, msg = document_approval_service.reject_document(
                            document_id=d["document_id"],
                            namespace=ns,
                            actor_username=actor_username,
                            actor_role=actor_role,
                            review_note=review_note,
                        )
                        (st.success if ok else st.error)(msg)
                        if ok:
                            st.rerun()

    if total_pending == 0:
        st.info("Không có tài liệu nào đang chờ bạn duyệt.")
