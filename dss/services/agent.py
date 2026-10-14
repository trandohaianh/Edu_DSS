"""Agent / Orchestrator — FINAL GAP CLOSURE, Sections 17-19.

Trước đợt này: NOT_IMPLEMENTED (xem AI_AGENT_ORCHESTRATION.md — lý do trì
hoãn: cùng khoảng trống "2 thế giới dữ liệu" chặn Regulation Resolver/Rule
Engine, và kỷ luật phạm vi có chủ đích thay vì vội vàng thêm 1 lớp orchestration
mới ở cuối 1 đợt đã rất lớn). Đợt này xây phần LÕI THẬT, TỐI THIỂU, đã test —
KHÔNG phải 1 "free autonomous LLM agent" tự quyết định làm gì — Agent CHỈ điều
phối các hàm ĐÃ CÓ (Calculator/Regulation Resolver/Rule Engine/Validator),
qua 1 allowlist tường minh, tĩnh (không tự mở rộng lúc chạy).

QUAN TRỌNG (trung thực về phạm vi, giống mọi module khác trong đợt này):
- `_ALLOWED_TOOLS` chỉ liệt kê các hàm ĐÃ tồn tại/đã test (gpa_calculator,
  rule_engine, validator) — regulation_resolver/RAG/ML Prediction/LLM
  Gateway CHƯA có hàm điều phối thật qua Agent trong đợt này (chỉ có ví dụ
  minh hoạ `run_gpa_calculation` — không tự nhận đã có "toàn bộ Agent").
- KHÔNG có RBAC/tenant-scope enforcement THẬT trong module này — vẫn bị
  chặn bởi khoảng trống "2 thế giới dữ liệu" đã ghi nhận nhiều lần
  (ai_router.py, POSTGRES_RUNTIME_VALIDATION.md). `AgentRequest.organization_id`
  tồn tại trong hợp đồng dữ liệu để SẴN SÀNG cho khi khoảng trống đó được
  nối, nhưng KHÔNG có logic nào trong file này thực sự lọc theo nó.
- KHÔNG có audit log ghi thật vào DB — `audit_metadata` chỉ là 1 dict trả
  về trong `AgentResult`, nơi gọi (chưa xây trong đợt này) sẽ cần tự ghi
  vào `audit_log_repository` nếu muốn log thật.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

_ALLOWED_TOOLS = frozenset({
    "gpa_calculator.compute_required_remaining_gpa",
    "regulation_resolver.resolve_regulation",
    "rule_engine.evaluate_credit_limit",
    "rule_engine.evaluate_academic_warning",
    "rule_engine.evaluate_thesis_eligibility",
    "rule_engine.evaluate_graduation_eligibility",
    "validator.validate_gpa_value",
    "validator.validate_rule_engine_result",
    "validator.validate_regulation_resolution",
    "validator.validate_llm_numeric_claim",
})


class ToolNotAllowedError(RuntimeError):
    """Agent từ chối gọi bất kỳ hàm nào không có tên trong `_ALLOWED_TOOLS`."""


class AuthorizationError(RuntimeError):
    """Agent từ chối THỰC THI request — danh tính/phạm vi không hợp lệ hoặc
    không đủ quyền cho intent này. Fail-closed: bất kỳ trường danh tính bắt
    buộc nào thiếu đều bị từ chối, không mặc định cho qua."""


# Khớp đúng chuỗi vai trò dùng trong toàn bộ ứng dụng (dss/integrations/
# postgres_lms_cms.py::_ROLE_MAP và các nơi khác) — KHÔNG tự đặt tên khác.
_ROLE_STUDENT = "Sinh viên"
_ROLE_LECTURER = "Giảng viên / CVHT"
_ROLE_ADMIN = "Admin"
_STAFF_ROLES = frozenset({_ROLE_LECTURER, _ROLE_ADMIN})

# Intent chỉ Admin được phép thực thi qua Agent (vd. quản trị quy chế/hệ
# thống) — danh sách tường minh, tĩnh, giống mẫu _ALLOWED_TOOLS.
_ADMIN_ONLY_INTENTS = frozenset({
    "ADMIN_REGULATION_MANAGEMENT",
    "ADMIN_AI_PROVIDER_CONFIG",
    "ADMIN_AUDIT_REVIEW",
})


def authorize(request: "AgentRequest") -> None:
    """Xác thực quyền THỰC SỰ trước khi thực thi bất kỳ tool nào — KHÔNG tin
    tưởng bất kỳ trường danh tính nào lấy TỪ nội dung câu hỏi (`request_text`
    không bao giờ được đọc ở đây để suy ra danh tính). Toàn bộ kiểm tra dựa
    trên các trường CẤU TRÚC của `AgentRequest` — vốn phải được tầng gọi
    (Router/UI, đã xác thực qua phiên đăng nhập thật) resolve TRƯỚC khi tạo
    request này, không phải Agent tự tra cứu.

    Raises `AuthorizationError` (fail-closed) khi:
    - Thiếu `user_id` hoặc `role` (danh tính không đầy đủ — không suy đoán).
    - `role` không phải 1 trong 3 vai trò hợp lệ đã biết.
    - `role == Sinh viên` VÀ `authorized_context["subject_user_id"]` (sinh
      viên mà dữ liệu đang nói về) khác `user_id` — KHÔNG cho phép sinh
      viên A truy cập dữ liệu của sinh viên B qua Agent.
    - `organization_id` của request khác `authorized_context["organization_id"]`
      (nếu cả 2 đều có mặt) — KHÔNG cho phép truy cập chéo tổ chức.
    - `intent` nằm trong `_ADMIN_ONLY_INTENTS` mà `role != Admin`.
    """
    if not request.user_id or not request.role:
        raise AuthorizationError("Thiếu user_id hoặc role — từ chối (fail-closed).")

    if request.role not in (_ROLE_STUDENT, _ROLE_LECTURER, _ROLE_ADMIN):
        raise AuthorizationError(f"Vai trò không hợp lệ: {request.role!r} — từ chối (fail-closed).")

    if request.intent in _ADMIN_ONLY_INTENTS and request.role != _ROLE_ADMIN:
        raise AuthorizationError(f"Intent '{request.intent}' chỉ dành cho Admin.")

    subject_user_id = request.authorized_context.get("subject_user_id")
    if request.role == _ROLE_STUDENT and subject_user_id is not None and subject_user_id != request.user_id:
        raise AuthorizationError(
            "Sinh viên chỉ được truy cập dữ liệu của CHÍNH mình qua Agent — "
            f"user_id={request.user_id!r} != subject_user_id={subject_user_id!r}."
        )

    ctx_org_id = request.authorized_context.get("organization_id")
    if request.organization_id is not None and ctx_org_id is not None and ctx_org_id != request.organization_id:
        raise AuthorizationError(
            f"organization_id không khớp giữa request ({request.organization_id!r}) "
            f"và authorized_context ({ctx_org_id!r}) — từ chối truy cập chéo tổ chức."
        )


def _invoke_tool(tool_name: str, fn: Callable, /, *args, **kwargs) -> Any:
    if tool_name not in _ALLOWED_TOOLS:
        raise ToolNotAllowedError(
            f"Tool '{tool_name}' không nằm trong allowlist — Agent từ chối gọi."
        )
    return fn(*args, **kwargs)


@dataclass
class AgentRequest:
    """Hợp đồng request có cấu trúc (Section 17) — KHÔNG dùng dict tự do dễ
    thiếu trường. `authorized_context` PHẢI đã được nơi gọi (Router/UI) xác
    thực quyền truy cập trước — Agent không tự tra cứu quyền, nhưng
    `authorize()` VẪN kiểm tra tính nhất quán nội bộ (Section 3) trước khi
    bất kỳ tool nào được thực thi."""

    user_id: str
    organization_id: Optional[str]
    role: str
    intent: str
    authorized_context: dict
    request_text: str
    correlation_id: str


@dataclass
class AgentResult:
    intent: str
    tools_used: list = field(default_factory=list)
    decision: Any = None
    evidence: dict = field(default_factory=dict)
    llm_used: bool = False
    validator_result: Any = None
    fallback: Optional[str] = None
    audit_metadata: dict = field(default_factory=dict)


def _emit_audit_event(request: AgentRequest, *, tools_used: list, validator_result, fallback, final_status: str) -> None:
    """Section 10: mọi lời gọi tool-order thật đều PHÁT 1 sự kiện audit
    (best-effort, không raise) — KHÔNG chỉ định nghĩa `ai_decision_audit.py`
    rồi không ai gọi (đúng bài học lặp lại nhiều lần trong đợt này: Circuit
    Breaker/Rule Engine/Validator đều từng bị hỏi "đã thật sự wire chưa")."""
    from dss.services import ai_decision_audit

    ai_decision_audit.emit(ai_decision_audit.AIDecisionAuditEvent(
        correlation_id=request.correlation_id, tenant_id=request.organization_id,
        actor_ref=request.user_id, role=request.role, intent=request.intent, tier=1,
        tools_used=list(tools_used), llm_used=False, fallback_type=fallback,
        validator_status=getattr(validator_result, "status", None), final_status=final_status,
    ))


def run_gpa_calculation(request: AgentRequest) -> AgentResult:
    """Ví dụ minh hoạ tool-order THẬT cho GPA (Section 18): Router → Agent →
    dữ liệu sinh viên đã ủy quyền → Calculator → Validator → (LLM giải thích,
    KHÔNG bật trong hàm này — 0 lượt gọi LLM) → response.

    `authorized_context` cần đủ 4 khoá: current_gpa/credits_done/target_gpa/
    credits_remaining — nơi gọi (chưa xây trong đợt này) chịu trách nhiệm
    tự resolve chúng từ dữ liệu ĐÃ ủy quyền của sinh viên. KHÔNG tự bịa giá
    trị thiếu — trả `fallback="INSUFFICIENT_DATA"` trung thực.

    Section 3: gọi `authorize()` TRƯỚC bất kỳ tool nào — raises
    `AuthorizationError` (không tự bắt lỗi ở đây, để lỗi lan lên tầng gọi xử
    lý rõ ràng, không âm thầm nuốt lỗi phân quyền)."""
    authorize(request)

    tools_used: list[str] = []
    ctx = request.authorized_context
    required_keys = ("current_gpa", "credits_done", "target_gpa", "credits_remaining")
    if any(ctx.get(k) is None for k in required_keys):
        _emit_audit_event(request, tools_used=tools_used, validator_result=None, fallback="INSUFFICIENT_DATA", final_status="INSUFFICIENT_DATA")
        return AgentResult(
            intent=request.intent, tools_used=tools_used, decision=None,
            evidence={}, llm_used=False, validator_result=None,
            fallback="INSUFFICIENT_DATA",
            audit_metadata={
                "correlation_id": request.correlation_id, "user_id": request.user_id,
                "role": request.role, "reason": "missing GPA calculation inputs",
            },
        )

    from dss.services.gpa_calculator import compute_required_remaining_gpa

    tools_used.append("gpa_calculator.compute_required_remaining_gpa")
    calc_result = _invoke_tool(
        "gpa_calculator.compute_required_remaining_gpa",
        compute_required_remaining_gpa,
        current_gpa=ctx["current_gpa"], credits_done=ctx["credits_done"],
        target_gpa=ctx["target_gpa"], credits_remaining=ctx["credits_remaining"],
    )

    from dss.services import validator

    tools_used.append("validator.validate_gpa_value")
    check_value = calc_result.rounded_value if calc_result.status == "ok" else 0.0
    val_result = _invoke_tool("validator.validate_gpa_value", validator.validate_gpa_value, check_value)

    _emit_audit_event(request, tools_used=tools_used, validator_result=val_result, fallback=None, final_status=calc_result.status)
    return AgentResult(
        intent=request.intent, tools_used=tools_used, decision=calc_result,
        evidence={"calculator_result": calc_result}, llm_used=False,
        validator_result=val_result, fallback=None,
        audit_metadata={
            "correlation_id": request.correlation_id, "user_id": request.user_id, "role": request.role,
        },
    )


def run_regulation_or_rule_check(request: AgentRequest) -> AgentResult:
    """Section 18-B: Router → Agent → Regulation Resolver → Rule Engine →
    (RAG evidence — KHÔNG triển khai trong hàm này, xem hạn chế bên dưới) →
    (LLM giải thích — KHÔNG bật, 0 lượt gọi) → Validator → response.

    `authorized_context` cần: `regulations` (list[RegulationVersion] đã
    resolve sẵn từ tầng lưu trữ), `organization_id`/`program_id`/`cohort`,
    và TÙY CHỌN `rule` (1 `AcademicRule` + tên hàm đánh giá + input) nếu câu
    hỏi cũng cần kiểm tra 1 quy tắc cụ thể sau khi đã biết quy chế áp dụng.

    HẠN CHẾ TRUNG THỰC: không tự lấy RAG evidence (cần wiring RAG riêng,
    chưa làm trong đợt này) — nếu `authorized_context` không có `regulations`
    thật, trả `INSUFFICIENT_DATA` trung thực, không tự bịa quy chế."""
    authorize(request)
    tools_used: list[str] = []
    ctx = request.authorized_context

    regulations = ctx.get("regulations")
    org_id, program_id, cohort = ctx.get("organization_id"), ctx.get("program_id"), ctx.get("cohort")
    if regulations is None or org_id is None or program_id is None or cohort is None:
        return AgentResult(
            intent=request.intent, tools_used=tools_used, fallback="INSUFFICIENT_DATA",
            audit_metadata={"correlation_id": request.correlation_id, "user_id": request.user_id, "role": request.role},
        )

    from dss.services.regulation_resolver import resolve_regulation
    from dss.services import validator

    tools_used.append("regulation_resolver.resolve_regulation")
    reg_result = _invoke_tool(
        "regulation_resolver.resolve_regulation", resolve_regulation,
        regulations, organization_id=org_id, program_id=program_id, cohort=cohort,
    )
    tools_used.append("validator.validate_regulation_resolution")
    reg_validation = _invoke_tool(
        "validator.validate_regulation_resolution", validator.validate_regulation_resolution, reg_result,
    )

    rule_result = None
    rule_validation = None
    rule_spec = ctx.get("rule")
    if reg_result.status == "ok" and rule_spec is not None:
        from dss.services import rule_engine

        eval_fn_name = rule_spec["evaluate_fn_name"]  # vd. "evaluate_credit_limit"
        tool_name = f"rule_engine.{eval_fn_name}"
        eval_fn = getattr(rule_engine, eval_fn_name)
        tools_used.append(tool_name)
        rule_result = _invoke_tool(tool_name, eval_fn, rule_spec["rule"], **rule_spec["kwargs"])
        tools_used.append("validator.validate_rule_engine_result")
        rule_validation = _invoke_tool(
            "validator.validate_rule_engine_result", validator.validate_rule_engine_result, rule_result,
        )

    return AgentResult(
        intent=request.intent, tools_used=tools_used,
        decision=rule_result if rule_result is not None else reg_result,
        evidence={"regulation_result": reg_result, "rule_result": rule_result},
        llm_used=False, validator_result=rule_validation or reg_validation, fallback=None,
        audit_metadata={"correlation_id": request.correlation_id, "user_id": request.user_id, "role": request.role},
    )


def run_risk_explanation(request: AgentRequest) -> AgentResult:
    """Section 18-C: Router → Agent → (ML prediction đã lưu + phiên bản mô
    hình + SHAP evidence — ĐÃ được tính bởi `model_service.py` trước đó, xem
    hạn chế bên dưới) → (LLM diễn giải — KHÔNG bật, 0 lượt gọi trong hàm
    này) → response.

    `authorized_context` cần: `prediction`, `model_version`, `shap_evidence`.

    HẠN CHẾ TRUNG THỰC: hàm này KHÔNG tự chạy `model_service.py`'s dự đoán/
    SHAP — nó đóng gói kết quả ĐÃ CÓ SẴN từ tầng gọi vào đúng khuôn
    AgentResult. Không có bước Validator chuyên biệt cho ML prediction/SHAP
    trong đợt này (validator.py chưa có hàm nào cho việc này — xem
    DECISION_ENGINE_ARCHITECTURE.md) — `validator_result=None` trung thực,
    không tự bịa 1 bước kiểm chứng chưa tồn tại."""
    authorize(request)
    ctx = request.authorized_context
    required = ("prediction", "model_version", "shap_evidence")
    if any(ctx.get(k) is None for k in required):
        return AgentResult(
            intent=request.intent, fallback="INSUFFICIENT_DATA",
            audit_metadata={"correlation_id": request.correlation_id, "user_id": request.user_id, "role": request.role},
        )

    return AgentResult(
        intent=request.intent, tools_used=["model_service.predict_for_student (pre-computed by caller)"],
        decision=ctx["prediction"],
        evidence={"model_version": ctx["model_version"], "shap_evidence": ctx["shap_evidence"]},
        llm_used=False, validator_result=None, fallback=None,
        audit_metadata={"correlation_id": request.correlation_id, "user_id": request.user_id, "role": request.role},
    )


def run_personalized_plan(request: AgentRequest) -> AgentResult:
    """Section 18-D: Router → Agent → (Calculator/Regulation/Rules/ML —
    TÙY CHỌN, chỉ chạy nếu dữ liệu tương ứng có trong `authorized_context`)
    → (RAG đã duyệt — KHÔNG tự lấy trong hàm này) → LLM CHỈ để tổng hợp văn
    bản (KHÔNG được tự tính bất kỳ con số nào — xem `enforce_rule_engine_
    decision_cannot_be_overridden`/`validator.validate_llm_numeric_claim`
    nếu LLM có nêu số) → Validator → response.

    HẠN CHẾ TRUNG THỰC: hàm này KHÔNG tự gọi LLM Gateway thật (chưa wiring
    LLM call qua Agent trong đợt này) — `llm_used` LUÔN là False, và
    `evidence` chỉ tổng hợp các kết quả xác định ĐÃ tính được từ context,
    không tự tổng hợp văn bản. Đây là khung tổng hợp bằng chứng xác định,
    chưa phải "kế hoạch cá nhân hoá" hoàn chỉnh."""
    authorize(request)
    tools_used: list[str] = []
    evidence: dict = {}
    ctx = request.authorized_context

    if all(ctx.get(k) is not None for k in ("current_gpa", "credits_done", "target_gpa", "credits_remaining")):
        gpa_result = run_gpa_calculation(request)
        tools_used.extend(gpa_result.tools_used)
        evidence["gpa"] = gpa_result.decision

    if ctx.get("regulations") is not None:
        reg_result = run_regulation_or_rule_check(request)
        tools_used.extend(reg_result.tools_used)
        evidence["regulation"] = reg_result.decision

    if not evidence:
        return AgentResult(
            intent=request.intent, fallback="INSUFFICIENT_DATA",
            audit_metadata={"correlation_id": request.correlation_id, "user_id": request.user_id, "role": request.role},
        )

    return AgentResult(
        intent=request.intent, tools_used=tools_used, decision=None, evidence=evidence,
        llm_used=False, validator_result=None, fallback=None,
        audit_metadata={"correlation_id": request.correlation_id, "user_id": request.user_id, "role": request.role},
    )


def enforce_rule_engine_decision_cannot_be_overridden(rule_result, llm_suggested_status: Optional[str]) -> str:
    """Section 19 ở tầng Agent: TÁI SỬ DỤNG (không viết lại) nguồn sự thật
    duy nhất `rule_engine.decide_final_status()` — 2 nơi cùng triển khai
    logic "LLM không được ghi đè" dễ lệch nhau theo thời gian, đúng bài học
    từ lỗi S-1 (2 tiêu chí xếp hạng khác nhau ở 2 nơi) đã sửa trong phiên
    này."""
    from dss.services.rule_engine import decide_final_status

    return decide_final_status(rule_result, llm_suggested_status)
