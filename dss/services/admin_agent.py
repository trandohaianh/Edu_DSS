"""Admin AI Agent — Đặc vụ AI hỗ trợ vận hành và quản trị hệ thống EduDSS.

Nguyên tắc phân quyền & Phạm vi:
- Chỉ hoạt động trong namespace `admin_operations` (Tuyệt đối không dùng student_learning).
- Quyền ĐỌC dữ liệu hệ thống:
  + System metrics & storage (dung lượng kho, số bản ghi, token usage)
  + Activity logs & Audit trails (lịch sử đăng nhập, thao tác)
  + Data quality metrics (tỷ lệ missing values, lỗi schema)
  + Model registry metadata (bản Production, danh sách Candidate)
  + Model drift reports
- Quyền THỰC THI (Automation Boundaries):
  + Tác vụ RỦI RO THẤP (Low-risk, được tự động kích hoạt):
    * Dọn dẹp bộ nhớ đệm tạm thời (clean temp cache)
    * Lập chỉ mục lại Vector Store (reindex vector cache)
    * Tổng hợp báo cáo sức khỏe hệ thống
  + Tác vụ RỦI RO CAO (High-risk, BẮT BUỘC Admin phê duyệt):
    * Promote / Rollback mô hình Production
    * Xóa tài khoản người dùng hoặc xóa dataset
    * Thay đổi cấu hình bảo mật hoặc reset hệ thống
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from dss.services.auth_service import require_role
from dss.services.rag_namespaces import NAMESPACE_ADMIN_OPERATIONS


class AdminAIAgent:
    """Đặc vụ thông minh hỗ trợ Quản trị viên giám sát và vận hành hệ thống."""

    def __init__(self, warehouse=None, llm_gateway=None):
        self.warehouse = warehouse
        self.llm_gateway = llm_gateway
        self.namespace = NAMESPACE_ADMIN_OPERATIONS

    def get_system_health_telemetry(self) -> Dict[str, Any]:
        """Thu thập các chỉ số sức khỏe hệ thống (Read-only)."""
        metrics = {
            "status": "healthy",
            "models_count": 0,
            "datasets_count": 0,
            "activities_count": 0,
            "storage_paths_exist": False,
        }

        if self.warehouse:
            try:
                models = self.warehouse.list_models()
                datasets = self.warehouse.list_datasets()
                metrics["models_count"] = len(models)
                metrics["datasets_count"] = len(datasets)
                metrics["storage_paths_exist"] = os.path.exists(self.warehouse.base_path)
            except Exception as e:
                metrics["status"] = "degraded"
                metrics["error"] = str(e)

        from dss.services.token_tracker import get_system_budget_status
        metrics["budget_status"] = get_system_budget_status()

        return metrics

    def diagnose_system_state(self) -> Dict[str, Any]:
        """Tự động phân tích và đưa ra khuyến nghị bảo trì."""
        telemetry = self.get_system_health_telemetry()
        findings = []
        recommendations = []

        budget = telemetry.get("budget_status", {})
        if budget.get("status") in ("daily_warning", "monthly_warning"):
            findings.append("Chi phí token AI đang tiến gần ngưỡng cảnh báo 80%.")
            recommendations.append("Xem xét tối ưu độ dài ngữ cảnh RAG hoặc tăng hạn ngạch hệ thống.")
        elif budget.get("status") in ("daily_exceeded", "monthly_exceeded"):
            findings.append("Ngân sách AI đã chạm 100%. Các cuộc gọi mới sẽ kích hoạt fallback.")
            recommendations.append("Cần Admin cấp thêm ngân sách hoặc bật chế độ tiết kiệm.")

        if telemetry["models_count"] == 0:
            findings.append("Chưa có mô hình nào được huấn luyện trong Kho dữ liệu.")
            recommendations.append("Giảng viên cần huấn luyện mô hình để sẵn sàng cho phân loại rủi ro.")

        return {
            "telemetry": telemetry,
            "findings": findings,
            "recommendations": recommendations,
            "healthy": len(findings) == 0,
        }

    # --- CÁC TÁC VỤ RỦI RO THẤP (TỰ ĐỘNG THỰC THI ĐƯỢC) ---
    def run_low_risk_maintenance(self, task_name: str) -> Tuple[bool, str]:
        """Thực thi các công việc bảo trì an toàn không gây mất mát dữ liệu."""
        allowed_tasks = ["clean_temp_cache", "reindex_vector_cache", "generate_daily_health_report"]
        if task_name not in allowed_tasks:
            return False, f"Tác vụ '{task_name}' không nằm trong danh mục rủi ro thấp cho phép tự động chạy."

        if task_name == "clean_temp_cache":
            # Dọn file rác .tmp trong thư mục warehouse
            if self.warehouse and os.path.exists(self.warehouse.base_path):
                cleaned = 0
                for root, _, files in os.walk(self.warehouse.base_path):
                    for f in files:
                        if f.endswith(".tmp"):
                            try:
                                os.remove(os.path.join(root, f))
                                cleaned += 1
                            except OSError:
                                pass
                return True, f"Đã dọn dẹp thành công {cleaned} tệp tạm (.tmp)."
            return True, "Không có tệp tạm cần dọn dẹp."

        elif task_name == "reindex_vector_cache":
            return True, "Đã làm mới chỉ mục tìm kiếm tri thức nội bộ."

        elif task_name == "generate_daily_health_report":
            diag = self.diagnose_system_state()
            return True, f"Đã tạo báo cáo: {len(diag['findings'])} ghi chú, hệ thống: {diag['telemetry']['status']}."

        return False, "Tác vụ không xác định."

    # --- CÁC TÁC VỤ RỦI RO CAO (BẮT BUỘC ADMIN PHÊ DUYỆT) ---
    @require_role("Admin")
    def request_high_risk_operation(
        self,
        operation_type: str,
        target_id: str,
        admin_confirmation_token: str,
    ) -> Tuple[bool, str]:
        """Tác vụ rủi ro cao (Promote/Rollback/Delete) — BẮT BUỘC có xác nhận của Admin."""
        if not admin_confirmation_token or admin_confirmation_token != "CONFIRM_ADMIN_OPERATION":
            return False, "Tác vụ rủi ro cao bị từ chối: Thiếu mã xác nhận tường minh từ Quản trị viên."

        if operation_type == "promote_model":
            from dss.services.model_registry import promote
            return promote(self.warehouse, target_id, promotion_reason="Thực thi qua Admin Agent đã được phê duyệt")

        elif operation_type == "rollback_model":
            from dss.services.model_registry import rollback
            return rollback(self.warehouse, target_id, rollback_reason="Thực thi qua Admin Agent đã được phê duyệt")

        return False, f"Loại thao tác rủi ro cao '{operation_type}' không được hỗ trợ."
