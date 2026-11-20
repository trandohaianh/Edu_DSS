"""Platform Admin — University Onboarding (Stage 2).

Practical, additive Streamlit UI over dss/services/university_onboarding.py
— every action here calls that module's real functions (real HTTP test
connection, real DB writes, real activation-gate checks); nothing in this
tab fabricates a result. Requires Postgres (`DATABASE_URL`) to be
configured — university/tenant management is inherently a Postgres-backed
concept in this codebase (see dss/db/models.py::Organization), not
something the local single-tenant JSON warehouse mode has.
"""

from __future__ import annotations

import streamlit as st

from dss.db.repositories import university_repository as repo
from dss.services import university_onboarding as onboarding
from dss.tabs import ui_kit


def university_onboarding_tab():
    ui_kit.page_header(
        "Onboarding Trường Đại học",
        subtitle="Cấp phát một trường đại học mới trên CÙNG MỘT mã nguồn EduDSS — không sao chép code, không viết lại thuật toán.",
        icon="🏛️",
    )

    from dss.db.session import is_database_configured

    if not is_database_configured():
        st.error("Chưa cấu hình PostgreSQL (DATABASE_URL). Quản lý trường đại học yêu cầu PostgreSQL.")
        return

    try:
        orgs = repo.list_organizations()
    except Exception as e:
        ui_kit.report_error("Không thể tải danh sách tổ chức", e)
        return

    st.subheader("Các trường đại học hiện có")
    if orgs:
        st.dataframe(
            [
                {
                    "ID": o["id"],
                    "Mã": o["org_code"],
                    "Tên": o["name"],
                    "Trạng thái vòng đời": o["lifecycle_status"],
                    "Chế độ triển khai": o["deployment_mode"],
                }
                for o in orgs
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("Chưa có trường đại học nào.")

    st.markdown("---")
    st.subheader("Thêm trường đại học mới")

    step = st.session_state.get("_onboarding_step", "provision")
    org_id = st.session_state.get("_onboarding_org_id")

    with st.expander("1️⃣ Thông tin cơ bản", expanded=(step == "provision")):
        col1, col2 = st.columns(2)
        org_code = col1.text_input("Mã tổ chức (org_code)", key="ob_org_code")
        name = col2.text_input("Tên trường", key="ob_name")
        domain = st.text_input("Domain (tuỳ chọn)", key="ob_domain")
        deployment_mode = st.selectbox(
            "Chế độ triển khai",
            onboarding.SIMULATED_EXTERNAL_ORGS and ["MULTI_TENANT_SAAS", "DEDICATED"],
            key="ob_deployment_mode",
        )
        if st.button("Tạo tổ chức (SETUP)", key="ob_provision_btn"):
            if not org_code or not name:
                st.error("Cần nhập mã tổ chức và tên trường.")
            else:
                try:
                    new_id = onboarding.provision_university(org_code, name, domain or None, deployment_mode)
                    st.session_state["_onboarding_org_id"] = new_id
                    st.session_state["_onboarding_step"] = "admin"
                    st.success(f"Đã tạo tổ chức #{new_id} (trạng thái SETUP).")
                    st.rerun()
                except Exception as e:
                    ui_kit.report_error("Lỗi tạo tổ chức", e)

    if not org_id:
        return

    with st.expander("2️⃣ Tạo tài khoản Admin trường", expanded=(step == "admin")):
        admin_username = st.text_input("Tên đăng nhập Admin", key="ob_admin_username")
        admin_password = st.text_input("Mật khẩu", type="password", key="ob_admin_password")
        if st.button("Tạo tài khoản Admin", key="ob_create_admin_btn"):
            try:
                onboarding.create_university_admin(org_id, admin_username, admin_password)
                st.session_state["_onboarding_step"] = "connector"
                st.success("Đã tạo tài khoản Admin. Tổ chức chuyển sang trạng thái CONFIGURING.")
                st.rerun()
            except Exception as e:
                ui_kit.report_error("Lỗi tạo Admin", e)

    with st.expander("3️⃣ Cấu hình kết nối LMS/CMS", expanded=(step == "connector")):
        st.caption(
            "credential_reference phải là TÊN biến môi trường chứa token thật — không dán token trực tiếp vào đây."
        )
        external_org = st.selectbox("Tổ chức bên ngoài (simulator)", ["org-a", "org-b"], key="ob_external_org")
        base_url = st.text_input("Base URL", value="http://localhost:8765", key="ob_base_url")
        credential_reference = st.text_input("Credential reference (tên biến môi trường)", key="ob_cred_ref")
        if st.button("Lưu cấu hình kết nối", key="ob_save_connector_btn"):
            try:
                onboarding.configure_connector(
                    org_id,
                    connector_type="simulated_lms_cms",
                    external_organization_id=external_org,
                    base_url=base_url,
                    credential_reference=credential_reference,
                )
                st.session_state["_onboarding_step"] = "test"
                st.success("Đã lưu cấu hình kết nối.")
                st.rerun()
            except Exception as e:
                ui_kit.report_error("Lỗi cấu hình", e)

    with st.expander("4️⃣ Kiểm tra kết nối", expanded=(step == "test")):
        if st.button("Test Connection (HTTP thật)", key="ob_test_conn_btn"):
            result = onboarding.test_connection(org_id)
            if result["status"] == "SUCCESS":
                st.success(f"✅ {result['detail']}")
            else:
                st.error(f"❌ {result['detail']}")

    with st.expander("5️⃣ Xác thực ánh xạ dữ liệu (Canonical Mapping)", expanded=(step == "test")):
        if st.button("Xác thực Mapping", key="ob_validate_mapping_btn"):
            result = onboarding.validate_mapping(org_id)
            if result["status"] == "VALID":
                st.success("✅ Mapping hợp lệ cho tất cả tài nguyên đã bật.")
            else:
                st.error("❌ Mapping chưa hợp lệ:")
            st.json(result["resource_mappings"])

    with st.expander("6️⃣ Đồng bộ dữ liệu ban đầu", expanded=(step == "test")):
        if st.button("Chạy Initial Sync", key="ob_initial_sync_btn"):
            result = onboarding.run_initial_sync(org_id)
            if result["status"] == "SUCCESS":
                st.success("✅ Đồng bộ ban đầu thành công.")
                st.json(result["results"])
            else:
                st.error(f"❌ {result.get('detail', 'Đồng bộ thất bại')}")

    with st.expander("7️⃣ Kích hoạt trường đại học", expanded=(step == "test")):
        accept_without_sync = st.checkbox(
            "Chấp nhận kích hoạt dù chưa đồng bộ (trường hợp đặc biệt)", key="ob_accept_no_sync"
        )
        if st.button("Kích hoạt (Activate)", key="ob_activate_btn", type="primary"):
            result = onboarding.activate_university(org_id, accept_without_sync=accept_without_sync)
            if result.activated:
                st.success("🎉 Trường đại học đã ACTIVE.")
                st.session_state["_onboarding_step"] = "provision"
                st.session_state.pop("_onboarding_org_id", None)
            else:
                st.error("Chưa thể kích hoạt — cần khắc phục:")
                for reason in result.reasons:
                    st.warning(f"• {reason}")

    st.markdown("---")
    st.subheader("Vô hiệu hoá / Kích hoạt lại")
    disable_org_id = st.number_input("ID tổ chức", min_value=1, step=1, key="ob_disable_org_id")
    col_d1, col_d2 = st.columns(2)
    if col_d1.button("Vô hiệu hoá (giữ nguyên dữ liệu)", key="ob_disable_btn"):
        try:
            repo.disable_organization(int(disable_org_id))
            st.success(f"Đã vô hiệu hoá tổ chức #{int(disable_org_id)} — dữ liệu KHÔNG bị xoá.")
        except Exception as e:
            ui_kit.report_error("Chưa vô hiệu hoá được tổ chức", e)
    if col_d2.button("Kích hoạt lại", key="ob_enable_btn"):
        try:
            repo.enable_organization(int(disable_org_id))
            st.success(f"Đã kích hoạt lại tổ chức #{int(disable_org_id)}.")
        except Exception as e:
            ui_kit.report_error("Chưa kích hoạt lại được tổ chức", e)
