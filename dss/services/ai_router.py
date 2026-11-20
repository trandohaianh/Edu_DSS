"""AI Intent/Complexity Router — OVERNIGHT AUTONOMOUS PRODUCTION CLOSURE
Phần 4-6.

34Q matrix xác nhận Q2/Q6 (Tier 1/2/3 routing) NOT_IMPLEMENTED trước đợt
này — mọi câu hỏi, kể cả câu tính toán đơn giản, đều đi thẳng LLM đầy đủ.

Module này là "production-quality minimum" — PHÂN LOẠI THUẦN, không gọi
LLM để phân loại (đúng yêu cầu: "Prefer deterministic intent patterns...
LLM fallback chỉ khi thực sự cần" — chưa có bằng chứng cần thiết nên KHÔNG
thêm phụ thuộc LLM/SLM nào cho việc phân loại). Dựa trên mẫu câu/từ khóa
tiếng Việt + ngữ cảnh đã có sẵn (request_type nơi gọi truyền vào).

QUAN TRỌNG (trung thực về phạm vi): phiên này thực sự "wire" 2 route thay
đổi hành vi thật:
- GPA_CALCULATION (gọi `gpa_calculator` thay vì để LLM tự tính, xem
  `dss/tabs/ai_advisor.py::ai_advisor_tab`).
- REGULATION_LOOKUP (chặn LLM tự đoán quy chế — xem
  `build_regulation_lookup_reply()` bên dưới. PHÁT HIỆN QUAN TRỌNG khi wire:
  codebase hiện có 2 THẾ GIỚI DỮ LIỆU tách biệt — (a) dataset mô phỏng sinh
  viên dùng cho AI Advisor/`current_student_id` KHÔNG có khái niệm
  organization_id/program_id/cohort nào, và (b) hệ multi-tenant Postgres
  thật (`tenant_service.py`, University Onboarding) CÓ organization_id
  nhưng chưa hề được nối với luồng chat sinh viên. Vì vậy
  `regulation_resolver.resolve_regulation()` (đã có, thuần, test đầy đủ từ
  đợt trước) KHÔNG THỂ được gọi với organization_id/program_id/cohort thật
  trong đợt này — gọi với giá trị bịa ra sẽ VI PHẠM nguyên tắc chống fabricate.
  Thay vào đó, hành vi thật được wire là: CHẶN LLM tự trả lời câu hỏi quy
  chế và trả lời trung thực rằng cần liên hệ Phòng Đào tạo — đây vẫn là một
  thay đổi hành vi runtime THẬT (trước đó câu hỏi này rơi thẳng xuống LLM
  Gateway, có nguy cơ LLM tự đoán quy chế).)

- ACADEMIC_RULE_CHECK (Phần 12 — chặn LLM tự quyết định ALLOW/DENY điều
  kiện học vụ. `rule_engine.py` đã có đầy đủ (credit limit/academic
  warning/thesis eligibility/graduation eligibility, ALLOW/DENY/WARNING/
  INSUFFICIENT_DATA, có `decide_final_status()` đảm bảo LLM không bao giờ
  ghi đè quyết định của Rule Engine — xem test_rule_engine.py), nhưng CÙNG
  LÝ DO với REGULATION_LOOKUP: không có organization_id/program_id/cohort
  VÀ không có dữ liệu tín chỉ đã hoàn thành cho sinh viên trong dataset mô
  phỏng, nên KHÔNG THỂ gọi `rule_engine.evaluate_*()` với input thật. Hành
  vi thật được wire là CHẶN LLM tự trả lời ALLOW/DENY và trả lời trung thực
  yêu cầu liên hệ Phòng Đào tạo/Cố vấn học tập.)

Xem `docs/ai/AI_ROUTING_MATRIX.md` để biết chi tiết route nào đã ảnh hưởng runtime,
route nào mới chỉ là nhãn phân loại.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

INTENT_DIRECT_DATA_LOOKUP = "DIRECT_DATA_LOOKUP"
INTENT_GPA_CALCULATION = "GPA_CALCULATION"
INTENT_ACADEMIC_RULE_CHECK = "ACADEMIC_RULE_CHECK"
INTENT_REGULATION_LOOKUP = "REGULATION_LOOKUP"
INTENT_RAG_QA = "RAG_QA"
INTENT_ML_PREDICTION = "ML_PREDICTION"
INTENT_LEARNING_EXPLANATION = "LEARNING_EXPLANATION"
INTENT_ADVISOR_CHAT = "ADVISOR_CHAT"
INTENT_ADVISOR_PLAN = "ADVISOR_PLAN"
INTENT_COMPLEX_REASONING = "COMPLEX_REASONING"
INTENT_UNKNOWN = "UNKNOWN"

TIER_1 = 1  # Cache/DB/Calculator/Rule Engine — không cần LLM
TIER_2 = 2  # RAG/lightweight — có thể không cần LLM lớn (SLM nếu có bằng chứng cần)
TIER_3 = 3  # LLM Gateway đầy đủ

# Route nào đã THỰC SỰ thay đổi hành vi runtime (đọc từ code, không phải
# tuyên bố suông) — dùng trong test + report để không tự nhận "đã wire" nếu
# chưa có code thật đứng sau route đó.
_BEHAVIOR_CHANGING_ROUTES = frozenset(
    {
        INTENT_GPA_CALCULATION,
        INTENT_REGULATION_LOOKUP,
        INTENT_ACADEMIC_RULE_CHECK,
        INTENT_DIRECT_DATA_LOOKUP,
    }
)


@dataclass
class RouteDecision:
    intent: str
    tier: int
    capability: str
    requires_llm: bool
    requires_rag: bool
    requires_rules: bool
    requires_calculator: bool
    reason: str
    wired_to_real_behavior: bool = field(init=False)

    def __post_init__(self):
        self.wired_to_real_behavior = self.intent in _BEHAVIOR_CHANGING_ROUTES


# --- Mẫu nhận diện GPA_CALCULATION -----------------------------------------
# "3.05 lên 3.20 cần bao nhiêu" / "GPA 3.05 ... muốn lên 3.20 ... cần bao nhiêu"
# Cần bắt được ÍT NHẤT 2 số thập phân (điểm hiện tại + điểm mục tiêu) VÀ 1 từ
# khóa ý định tính toán ("cần bao nhiêu", "cần đạt", "lên bao nhiêu").
# {1,3} (không phải {1,2}) vì số tín chỉ điển hình có thể tới 3 chữ số (vd.
# chương trình cử nhân ~120-150 tín chỉ) — GPA (0-10/0-4) vẫn khớp đúng vì
# phần thập phân xét riêng ({1,2} chữ số sau dấu chấm/phẩy).
_NUMBER_RE = re.compile(r"\b(\d{1,3}(?:[.,]\d{1,2})?)\b")
_GPA_CALC_INTENT_PHRASES = (
    "cần bao nhiêu",
    "cần đạt",
    "lên bao nhiêu",
    "cần đạt bao nhiêu",
    "muốn lên",
    "muốn đạt",
    "để đạt",
)

_REGULATION_LOOKUP_PHRASES = (
    "quy chế nào",
    "quy định nào",
    "áp dụng cho em",
    "áp dụng cho tôi",
    "quy chế đang áp dụng",
    "quy chế hiện hành",
)

_ACADEMIC_RULE_CHECK_PHRASES = (
    "có được đăng ký",
    "có đủ điều kiện",
    "đủ điều kiện làm khóa luận",
    "đủ điều kiện tốt nghiệp",
    "được phép đăng ký",
    "điều kiện đăng ký môn",
)

_DIRECT_DATA_LOOKUP_PHRASES = (
    "điểm hiện tại của em",
    "điểm hiện tại của tôi",
    "gpa của em là bao nhiêu",
    "gpa của tôi là bao nhiêu",
    "điểm của em là bao nhiêu",
    "điểm danh của em",
)

_LEARNING_EXPLANATION_PHRASES = (
    "tại sao em có nguy cơ",
    "tại sao hệ thống đánh giá",
    "giải thích vì sao",
    "vì sao em",
    "giải thích lại",
    "em không hiểu kết quả",
    # Thêm sau khi trace ví dụ mẫu "Tại sao em bị đánh giá có nguy cơ?" (thể bị
    # động, không khớp "tại sao hệ thống đánh giá"/"tại sao em có nguy cơ" —
    # rơi nhầm về ADVISOR_CHAT chung thay vì LEARNING_EXPLANATION, dù vẫn an
    # toàn vì ADVISOR_CHAT vẫn dùng LLM+RAG+citation, chỉ là kém chính xác hơn).
    "bị đánh giá có nguy cơ",
    "em bị đánh giá",
)

_ADVISOR_PLAN_PHRASES = (
    "lập kế hoạch",
    "kế hoạch học kỳ",
    "kế hoạch học tập",
)

_RAG_QA_PHRASES = (
    "tóm tắt tài liệu",
    "tài liệu này nói gì",
    "nội dung bài giảng",
)


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(p in text for p in phrases)


def try_extract_gpa_calculation_inputs(question: str) -> Optional[dict]:
    """Trích số liệu để gọi `gpa_calculator.compute_required_remaining_gpa()`
    từ câu hỏi tự do — KHÔNG suy đoán bừa.

    Hỗ trợ 2 trường hợp:
    - Đủ 4 số theo thứ tự (current_gpa, credits_done, target_gpa,
      credits_remaining) nếu người dùng tự nêu đủ (câu hỏi có kèm số tín
      chỉ) — hiếm nhưng hỗ trợ đầy đủ nếu có.
    - CHỈ 2 số (current_gpa, target_gpa, đúng mẫu ví dụ chuẩn "GPA 3.05,
      muốn lên 3.20") — trả về với `credits_done`/`credits_remaining` là
      `None`, nơi gọi PHẢI tự hỏi lại thay vì bịa số tín chỉ (hệ thống hiện
      KHÔNG có trường "tín chỉ" nào trong dữ liệu sinh viên mô phỏng —
      `dss/core/data_helpers.py::generate_data()` không sinh cột nào như
      vậy — nên không có nguồn thật để tự điền)."""
    numbers = _NUMBER_RE.findall(question)
    if len(numbers) < 2:
        return None

    def _to_float(s: str) -> float:
        return float(s.replace(",", "."))

    if len(numbers) >= 4:
        return {
            "current_gpa": _to_float(numbers[0]),
            "credits_done": _to_float(numbers[1]),
            "target_gpa": _to_float(numbers[2]),
            "credits_remaining": _to_float(numbers[3]),
        }
    return {
        "current_gpa": _to_float(numbers[0]),
        "target_gpa": _to_float(numbers[1]),
        "credits_done": None,
        "credits_remaining": None,
    }


def build_gpa_calculation_reply(
    question: str,
    *,
    user_id: str = "unknown_caller",
    role: str = "Sinh viên",
    correlation_id: Optional[str] = None,
) -> Optional[str]:
    """Trả lời QUYẾT ĐỊNH CHO câu hỏi GPA_CALCULATION — dùng
    `gpa_calculator.compute_required_remaining_gpa()` làm nguồn số DUY
    NHẤT, KHÔNG để LLM tự tính. Trả `None` nếu câu hỏi không đủ 2 số (nơi
    gọi nên rơi về đường LLM thông thường thay vì gọi hàm này).

    FINAL REMAINING-GAPS CLOSURE (Section 5): khi đủ 4 số (đã có tín chỉ),
    con số THẬT SỰ được tính qua `agent.run_gpa_calculation()` (Router →
    Agent → Calculator → Validator, đúng Section 18-A) thay vì gọi thẳng
    `compute_required_remaining_gpa()` — Agent tự chạy `authorize()` trước.
    `user_id`/`role` mặc định an toàn cho lời gọi cũ chưa cập nhật (không có
    `subject_user_id` trong context nên không kích hoạt kiểm tra chéo sinh
    viên — không phá vỡ tương thích ngược)."""
    extracted = try_extract_gpa_calculation_inputs(question)
    if extracted is None:
        return None

    if extracted["credits_done"] is None or extracted["credits_remaining"] is None:
        # KHÔNG bịa số tín chỉ — hệ thống hiện không có dữ liệu "tín chỉ" nào
        # trong hồ sơ sinh viên (generate_data() không sinh cột này) để tự
        # điền. Hỏi lại thay vì đoán (đúng nguyên tắc chống bịa dữ liệu).
        return (
            f"Mình hiểu bạn có điểm trung bình hiện tại **{extracted['current_gpa']:.2f}** và muốn đạt "
            f"**{extracted['target_gpa']:.2f}**. Để tính chính xác điểm trung bình cần đạt ở phần còn lại, "
            f"mình cần biết thêm: bạn đã học bao nhiêu tín chỉ, và còn bao nhiêu tín chỉ nữa? "
            f"(Hệ thống hiện chưa có sẵn dữ liệu tín chỉ trong hồ sơ của bạn để tự tính — vui lòng cho mình "
            f"biết 2 con số đó, ví dụ: \"đã học 80 tín chỉ, còn 40 tín chỉ\".)"
        )

    import uuid

    from dss.services import agent as agent_module

    agent_request = agent_module.AgentRequest(
        user_id=user_id,
        organization_id=None,
        role=role,
        intent=INTENT_GPA_CALCULATION,
        authorized_context={
            "current_gpa": extracted["current_gpa"],
            "credits_done": extracted["credits_done"],
            "target_gpa": extracted["target_gpa"],
            "credits_remaining": extracted["credits_remaining"],
        },
        request_text=question,
        correlation_id=correlation_id or uuid.uuid4().hex[:8],
    )
    agent_result = agent_module.run_gpa_calculation(agent_request)
    result = agent_result.decision

    if result.status == "INVALID_INPUT":
        return (
            "Mình chưa hiểu đúng các con số trong câu hỏi (thang điểm hoặc số tín chỉ không hợp lệ). "
            "Bạn có thể nêu rõ lại: điểm trung bình hiện tại, số tín chỉ đã học, điểm mục tiêu, và số tín chỉ còn lại không?"
        )
    if result.status == "INFEASIBLE":
        return (
            f"Với {extracted['credits_remaining']:.0f} tín chỉ còn lại, mục tiêu **{extracted['target_gpa']:.2f}** "
            f"KHÔNG khả thi — {result.messages[0]}"
        )

    # Phần 13: Validator (đã chạy BÊN TRONG agent.run_gpa_calculation()) xác
    # nhận con số Calculator tính ra nằm trong thang điểm hợp lệ TRƯỚC KHI
    # hiển thị — chặn số liệu vô lý lọt ra ngoài như kết quả đáng tin.
    from dss.services import validator

    gpa_check = agent_result.validator_result
    if gpa_check.status != validator.STATUS_PASS:
        return validator.decide_safe_fallback_message(gpa_check)

    return (
        f"Bạn cần đạt trung bình **{result.rounded_value:.2f}** cho **{extracted['credits_remaining']:.0f} tín chỉ còn lại** "
        f"để đạt mục tiêu {extracted['target_gpa']:.2f} (tính trên toàn bộ chương trình).\n\n"
        f"*(Kết quả tính bằng công thức xác định — không phải AI ước lượng.)*"
    )


_REGULATION_NO_MAPPING_REPLY = (
    "Em cần liên hệ **Phòng Đào tạo** hoặc quản trị viên hệ thống để được "
    "xác nhận CHÍNH XÁC quy chế đang áp dụng cho chương trình/khóa của em.\n\n"
    "Lý do: hệ thống không cho phép AI tự suy đoán quy chế học vụ (có thể sai "
    "phiên bản, ảnh hưởng quyền lợi học tập), và tài khoản của em hiện chưa "
    "được ánh xạ tới đúng Trường/Chương trình/Khóa để tra cứu tự động.\n\n"
    "*(Đây là câu trả lời cố định để chặn AI tự đoán — không phải AI tạo ra.)*"
)


_DIRECT_LOOKUP_ATTENDANCE_COLS = ("ty_le_diem_danh", "attendance_rate", "attendance")
# CỐ Ý KHÔNG gồm diem_ky_sau — đó là target/nhãn thật của dữ liệu mô phỏng
# (xem K-3, model_service.py::predict_for_student), câu hỏi "điểm HIỆN TẠI"
# hỏi về hiện trạng, không phải kết quả kỳ sau — dùng cột đó ở đây sẽ lộ y
# hệt lỗi K-3 (rò rỉ target làm dữ liệu "hiện tại").
_DIRECT_LOOKUP_SCORE_COLS = ("diem_ky_nay", "final_score", "gpa_previous", "gpa", "score", "total_score")


def build_direct_data_lookup_reply(question: str, *, student_row: Optional[dict]) -> Optional[str]:
    """Trả lời QUYẾT ĐỊNH CHO câu hỏi DIRECT_DATA_LOOKUP (Phần 15,
    POST_72H_MASTER_PRODUCTION_CLOSURE) — đọc THẲNG dữ liệu hiện có của
    CHÍNH sinh viên đang hỏi, KHÔNG cần LLM, KHÔNG dùng cột target/tương lai
    (xem `_DIRECT_LOOKUP_SCORE_COLS` — không có diem_ky_sau).

    AN TOÀN CROSS-STUDENT: hàm này CHỈ đọc `student_row` — dict đã được nơi
    gọi (`ai_advisor.py`) resolve từ CHÍNH phiên đăng nhập hiện tại
    (`current_student_id`) TRƯỚC khi gọi hàm này. Không có tham số student_id
    nào trong hàm này lấy từ nội dung câu hỏi — nên KHÔNG CÓ ĐƯỜNG nào để nội
    dung câu hỏi (dù có ai đó cố tình gõ ID của sinh viên khác vào) khiến hàm
    này trả về dữ liệu của SINH VIÊN KHÁC. Trả `None` nếu không nhận diện
    được cột dữ liệu phù hợp hoặc `student_row` không có (nơi gọi nên rơi về
    đường LLM thông thường hoặc báo lỗi thay vì bịa)."""
    if not student_row:
        return None
    text = (question or "").strip().lower()
    if not text:
        return None

    if "điểm danh" in text:
        for cand in _DIRECT_LOOKUP_ATTENDANCE_COLS:
            value = student_row.get(cand)
            if value is not None:
                pct = float(value) * 100 if float(value) <= 1.0 else float(value)
                return (
                    f"Tỷ lệ điểm danh hiện tại của em: **{pct:.1f}%**.\n\n"
                    f"*(Dữ liệu trực tiếp từ hồ sơ của em — không qua AI suy luận.)*"
                )
        return None

    for cand in _DIRECT_LOOKUP_SCORE_COLS:
        value = student_row.get(cand)
        if value is not None:
            return (
                f"Điểm hiện tại của em: **{float(value):.2f}**.\n\n"
                f"*(Dữ liệu trực tiếp từ hồ sơ của em — không qua AI suy luận.)*"
            )
    return None


def build_regulation_lookup_reply(
    question: str,
    *,
    organization_id: Optional[str] = None,
    program_id: Optional[str] = None,
    cohort: Optional[str] = None,
) -> str:
    """Trả lời QUYẾT ĐỊNH CHO câu hỏi REGULATION_LOOKUP — `resolve_regulation()`
    (dss/services/regulation_resolver.py) là NƠI DUY NHẤT được quyết định
    phiên bản quy chế, LLM KHÔNG được tự chọn.

    `organization_id`/`program_id`/`cohort` là optional vì nơi gọi hiện tại
    (`dss/tabs/ai_advisor.py`, luồng chat dựa trên dataset mô phỏng) KHÔNG có
    3 giá trị này cho sinh viên — codebase có 2 thế giới dữ liệu chưa nối
    (xem docstring đầu module). KHÔNG được tự bịa giá trị để vẫn "trông như"
    tra cứu được — khi thiếu, trả lời trung thực rằng chưa tra cứu được thay
    vì gọi resolve_regulation() với tham số giả.

    Khi 3 giá trị có thật (vd. sau khi 2 thế giới dữ liệu được nối ở đợt
    sau), hàm gọi resolve_regulation() thật với dữ liệu từ regulation_store
    (JSON store cục bộ, không cần Postgres — an toàn khi 72h simulation
    đang chạy)."""
    if organization_id is None or program_id is None or cohort is None:
        return _REGULATION_NO_MAPPING_REPLY

    from dss.services import regulation_store
    from dss.services.regulation_resolver import resolve_regulation

    candidates = regulation_store.list_regulations(organization_id=organization_id)
    result = resolve_regulation(
        candidates,
        organization_id=organization_id,
        program_id=program_id,
        cohort=cohort,
    )

    # Phần 13: Validator xác nhận kết quả Regulation Resolver tự nhất quán
    # (vd. status="ok" phải có kèm object quy chế thật) TRƯỚC KHI hiển thị.
    from dss.services import validator

    consistency_check = validator.validate_regulation_resolution(result)
    if consistency_check.status != validator.STATUS_PASS:
        return validator.decide_safe_fallback_message(consistency_check)

    if result.status == "ok":
        reg = result.regulation
        return (
            f"Quy chế đang áp dụng: **{reg.regulation_id}** (version {reg.version}, "
            f"hiệu lực từ {reg.effective_from}).\n\n"
            f"*(Kết quả từ Regulation Resolver — không phải AI tự chọn.)*"
        )
    return (
        f"Không xác định được quy chế đang áp dụng: {result.message}\n\n"
        f"Vui lòng liên hệ Phòng Đào tạo để được xác nhận chính xác."
    )


_RULE_CHECK_NO_MAPPING_REPLY = (
    "Em cần liên hệ **Cố vấn học tập** hoặc **Phòng Đào tạo** để được xác "
    "nhận CHÍNH XÁC em có đủ điều kiện hay không.\n\n"
    "Lý do: hệ thống không cho phép AI tự quyết định ALLOW/DENY cho các "
    "điều kiện học vụ (đăng ký môn/giới hạn tín chỉ/khóa luận/tốt nghiệp) — "
    "quyết định này PHẢI do Rule Engine dựa trên dữ liệu chính thức (tín "
    "chỉ đã hoàn thành, GPA, quy chế áp dụng), và tài khoản của em hiện "
    "chưa được ánh xạ đủ dữ liệu đó để đánh giá tự động.\n\n"
    "*(Đây là câu trả lời cố định để chặn AI tự đoán — không phải AI tạo ra.)*"
)


def build_academic_rule_check_reply(question: str, *, rule_evaluation_result=None) -> str:
    """Trả lời QUYẾT ĐỊNH CHO câu hỏi ACADEMIC_RULE_CHECK — `rule_engine.py`
    (Phần 12) là NƠI DUY NHẤT được quyết định ALLOW/DENY/WARNING, LLM KHÔNG
    được tự quyết định hay ghi đè (xem `rule_engine.decide_final_status()`).

    `rule_evaluation_result` là optional (kiểu `rule_engine.RuleEvaluationResult`)
    vì nơi gọi hiện tại (`dss/tabs/ai_advisor.py`) KHÔNG có đủ dữ liệu thật
    (organization_id/program_id/cohort + số tín chỉ đã hoàn thành) để tự
    evaluate — cùng khoảng trống kiến trúc với `build_regulation_lookup_reply()`
    (2 thế giới dữ liệu chưa nối, xem docstring đầu module). KHÔNG được tự
    bịa input để vẫn "trông như" đánh giá được — khi thiếu, trả lời trung
    thực thay vì gọi rule_engine với tham số giả."""
    if rule_evaluation_result is None:
        return _RULE_CHECK_NO_MAPPING_REPLY

    # Phần 13: Validator xác nhận kết quả Rule Engine tự nhất quán (status
    # hợp lệ, DENY/WARNING phải kèm lý do cụ thể) TRƯỚC KHI hiển thị.
    from dss.services import validator

    consistency_check = validator.validate_rule_engine_result(rule_evaluation_result)
    if consistency_check.status != validator.STATUS_PASS:
        return validator.decide_safe_fallback_message(consistency_check)

    from dss.services.rule_engine import STATUS_ALLOW, STATUS_DENY, STATUS_WARNING

    if rule_evaluation_result.status == STATUS_ALLOW:
        return (
            f"✅ Đủ điều kiện. {rule_evaluation_result.reason}\n\n"
            f"*(Kết quả từ Rule Engine — không phải AI tự quyết định.)*"
        )
    if rule_evaluation_result.status == STATUS_DENY:
        return (
            f"❌ Không đủ điều kiện. {rule_evaluation_result.reason}\n\n"
            f"*(Kết quả từ Rule Engine — không phải AI tự quyết định.)*"
        )
    if rule_evaluation_result.status == STATUS_WARNING:
        return (
            f"⚠️ Cảnh báo. {rule_evaluation_result.reason}\n\n*(Kết quả từ Rule Engine — không phải AI tự quyết định.)*"
        )
    return (
        f"Chưa đủ dữ liệu để đánh giá: {rule_evaluation_result.reason}\n\n"
        f"Vui lòng liên hệ Cố vấn học tập/Phòng Đào tạo để được xác nhận chính xác."
    )


def classify(question: str, *, request_type: Optional[str] = None) -> RouteDecision:
    """Phân loại 1 câu hỏi người dùng THUẦN bằng mẫu câu tiếng Việt xác định
    — KHÔNG gọi LLM. `request_type` (nếu nơi gọi đã biết, vd. "advisor_plan"
    từ nút "Tạo Kế hoạch Học tập") được ưu tiên khi câu hỏi không đủ rõ,
    tránh đoán sai khi đã có ngữ cảnh chắc chắn hơn từ chính UI gọi tới."""
    text = (question or "").strip().lower()

    if not text:
        return RouteDecision(
            intent=INTENT_UNKNOWN,
            tier=TIER_3,
            capability="fallback",
            requires_llm=True,
            requires_rag=False,
            requires_rules=False,
            requires_calculator=False,
            reason="Câu hỏi rỗng — không phân loại được, để LLM xử lý an toàn.",
        )

    numbers = _NUMBER_RE.findall(text)
    has_calc_intent_phrase = _contains_any(text, _GPA_CALC_INTENT_PHRASES)
    if len(numbers) >= 2 and has_calc_intent_phrase and ("gpa" in text or "điểm" in text or "lên" in text):
        return RouteDecision(
            intent=INTENT_GPA_CALCULATION,
            tier=TIER_1,
            capability="gpa_calculator",
            requires_llm=False,
            requires_rag=False,
            requires_rules=False,
            requires_calculator=True,
            reason=f"Phát hiện >= 2 số ({numbers[:2]}) + cụm từ ý định tính toán GPA — chuyển Calculator, không cần LLM tính.",
        )

    if _contains_any(text, _ACADEMIC_RULE_CHECK_PHRASES):
        return RouteDecision(
            intent=INTENT_ACADEMIC_RULE_CHECK,
            tier=TIER_1,
            capability="rule_engine",
            requires_llm=False,
            requires_rag=False,
            requires_rules=True,
            requires_calculator=False,
            reason="Câu hỏi về điều kiện/quy tắc học vụ xác định — cần Rule Engine + Regulation Resolver, không phải LLM tự suy đoán.",
        )

    if _contains_any(text, _REGULATION_LOOKUP_PHRASES):
        return RouteDecision(
            intent=INTENT_REGULATION_LOOKUP,
            tier=TIER_1,
            capability="regulation_resolver",
            requires_llm=False,
            requires_rag=False,
            requires_rules=False,
            requires_calculator=False,
            reason="Câu hỏi về quy chế đang áp dụng — cần Regulation Resolver chọn đúng phiên bản, LLM không được tự chọn.",
        )

    if _contains_any(text, _DIRECT_DATA_LOOKUP_PHRASES):
        return RouteDecision(
            intent=INTENT_DIRECT_DATA_LOOKUP,
            tier=TIER_1,
            capability="student_data",
            requires_llm=False,
            requires_rag=False,
            requires_rules=False,
            requires_calculator=False,
            reason="Tra cứu số liệu trực tiếp đã có sẵn (điểm/điểm danh hiện tại) — không cần LLM.",
        )

    if _contains_any(text, _LEARNING_EXPLANATION_PHRASES):
        return RouteDecision(
            intent=INTENT_LEARNING_EXPLANATION,
            tier=TIER_3,
            capability="diagnosis_engine+llm",
            requires_llm=True,
            requires_rag=False,
            requires_rules=False,
            requires_calculator=False,
            reason="Giải thích chẩn đoán/dự đoán — cần LLM diễn giải kết quả ML/chẩn đoán đã có, không tự bịa nguyên nhân.",
        )

    if _contains_any(text, _RAG_QA_PHRASES):
        return RouteDecision(
            intent=INTENT_RAG_QA,
            tier=TIER_2,
            capability="rag",
            requires_llm=True,
            requires_rag=True,
            requires_rules=False,
            requires_calculator=False,
            reason="Câu hỏi về nội dung tài liệu cụ thể — cần RAG lấy bằng chứng trước khi LLM trả lời.",
        )

    if request_type == "advisor_plan" or _contains_any(text, _ADVISOR_PLAN_PHRASES):
        return RouteDecision(
            intent=INTENT_ADVISOR_PLAN,
            tier=TIER_3,
            capability="advisor_plan",
            requires_llm=True,
            requires_rag=True,
            requires_rules=False,
            requires_calculator=False,
            reason="Yêu cầu lập kế hoạch học tập cá nhân hóa — cần LLM tổng hợp từ RAG + dự đoán ML.",
        )

    # Mặc định an toàn: KHÔNG đoán bừa là câu hỏi đơn giản — rơi về
    # ADVISOR_CHAT (LLM xử lý, đường hiện có, đã có RAG + citation
    # verification) thay vì UNKNOWN mù mờ, để không có route nào "im lặng"
    # không xử lý được.
    return RouteDecision(
        intent=INTENT_ADVISOR_CHAT,
        tier=TIER_3,
        capability="advisor_chat",
        requires_llm=True,
        requires_rag=True,
        requires_rules=False,
        requires_calculator=False,
        reason="Không khớp mẫu nào cụ thể — dùng đường hội thoại AI đầy đủ (đã có RAG + citation verification) làm mặc định an toàn.",
    )
