"""Session cleanup and cached app singletons."""
from __future__ import annotations

import streamlit as st

from dss.core.models import MultiAIProvider
from dss.core.trainers import ClassificationTrainer, RegressionTrainer
from dss.core.warehouse import DataWarehouse


def clear_all_session_state_for_new_data():
    """Xoa session state khi tai du lieu moi."""
    keys_to_clear = [k for k in st.session_state.keys() if k.startswith(
        'clf_') or k.startswith('reg_') or k.startswith('cluster_') or k.startswith('llm_')]
    for k in keys_to_clear:
        st.session_state.pop(k, None)
    # Dataset đổi -> mã số sinh viên đã "đăng nhập" có thể không còn tồn tại
    # trong dữ liệu mới -> bắt đăng nhập lại (xem _is_valid_student_login).
    st.session_state.pop('current_student_id', None)


@st.cache_resource(show_spinner=False)
def init_trainers_and_warehouse():
    """Singleton dùng chung cho cả session (Phase 8 refactor): trước đây hàm này
    không cache, nên bị gọi lại — và ClassificationTrainer/RegressionTrainer/
    DataWarehouse bị tạo lại — trên MỌI lần Streamlit rerun (tức mỗi lần người
    dùng bấm nút/đổi widget), gây tốn I/O (DataWarehouse.__init__ tạo 9 thư mục
    mỗi lần) và dựng lại các estimator sklearn không cần thiết."""
    clf_trainer = ClassificationTrainer()
    reg_trainer = RegressionTrainer()
    warehouse = DataWarehouse()
    llm_integration = MultiAIProvider(data_warehouse=warehouse) # Use MultiAIProvider with Warehouse
    return clf_trainer, reg_trainer, llm_integration, warehouse
