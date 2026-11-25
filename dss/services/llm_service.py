"""LLM service — Phase 10 của kế hoạch refactor EduDSS (mục 11 bản yêu cầu).

Bọc lại `MultiAIProvider.generate_personalized_advice` (dss/core/models.py) để
cung cấp chế độ "So sánh AI" (Compare AI) — gọi ĐỒNG THỜI nhiều provider bằng
ThreadPoolExecutor, giới hạn số request chạy cùng lúc bằng
`dss.config.MAX_CONCURRENT_REQUESTS`. Đây là kiến trúc multi-LLM đã CHUẨN BỊ
SẴN nhưng KHÔNG được gọi mặc định — luồng "Tạo Kế hoạch Học tập" bình thường
(dss/tabs/ai_advisor.py) vẫn luôn chỉ gọi đúng 1 provider như trước, không đổi
hành vi. `compare_providers()` chỉ chạy khi người dùng chủ động bấm nút so sánh
(chỉ Giảng viên/Admin, xem `@require_role` ở ai_advisor.py).

Workstream C (2026-09, Issue AIGOV-001): `compare_providers()` gọi
`LLMGateway.check_quota_and_rate_limit()` MỘT LẦN trước khi phân phối N cuộc
gọi song song — trước đây hoàn toàn không kiểm tra hạn ngạch tổ chức/người
dùng cho đường này. Vẫn KHÔNG đi qua toàn bộ `stream_generate()` (bỏ qua
fallback cascade) một cách có chủ đích: mục đích của Compare AI là biết
CHÍNH XÁC provider X có hoạt động hay không, không phải nhận câu trả lời của
provider khác bị gắn nhãn sai thành X — xem docstring của
`check_quota_and_rate_limit` trong llm_gateway.py.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

import dss.config as dss_config


@dataclass
class ProviderRunResult:
    provider_key: str
    provider_label: str
    model_name: str
    text: str = ""
    error: Optional[str] = None
    elapsed_seconds: float = 0.0


def _run_one_provider(
    llm_integration,
    provider_key: str,
    provider_label: str,
    model_name: str,
    call_kwargs: dict,
    student_weaknesses,
    predicted_gpa,
    use_rag: bool,
    embedding_model_name: str,
    use_warehouse_data: bool,
    student_profile,
    runtime_documents,
    role: str,
) -> ProviderRunResult:
    """Gọi 1 provider TỚI KHI XONG (gộp hết chunk stream thành 1 chuỗi) — chạy
    trong 1 thread riêng của ThreadPoolExecutor. Lỗi của provider này KHÔNG làm
    hỏng kết quả của các provider khác (bắt lỗi cục bộ, trả về trong error)."""
    t0 = time.monotonic()
    try:
        try:
            stream = llm_integration.generate_personalized_advice(
                student_weaknesses=student_weaknesses,
                predicted_gpa=predicted_gpa,
                provider=provider_key,
                use_rag=use_rag,
                embedding_model_name=embedding_model_name,
                use_warehouse_data=use_warehouse_data,
                student_profile=student_profile,
                runtime_documents=runtime_documents,
                model_name=model_name,
                role=role,
                **call_kwargs,
            )
        except TypeError:
            # Tương thích ngược với MultiAIProvider cache cũ chưa hỗ trợ runtime_documents
            # (giống rag_service.retrieve_documents — xem Phase 2).
            stream = llm_integration.generate_personalized_advice(
                student_weaknesses=student_weaknesses,
                predicted_gpa=predicted_gpa,
                provider=provider_key,
                use_rag=use_rag,
                embedding_model_name=embedding_model_name,
                use_warehouse_data=use_warehouse_data,
                student_profile=student_profile,
                model_name=model_name,
                **call_kwargs,
            )
        text = "".join(stream)
        elapsed = time.monotonic() - t0
        # Ghi nhận Token & Chi phí cho cuộc gọi so sánh AI
        try:
            from dss.services import token_tracker
            from dss.services.context_budget import approximate_token_count

            in_tok = approximate_token_count(str(student_weaknesses)) + 200
            out_tok = approximate_token_count(text)
            token_tracker.record_usage(
                user_id="compare_ai_user",
                role="Giảng viên / CVHT",
                request_type="compare_ai",
                provider=provider_key,
                model=model_name or "default",
                input_tokens=in_tok,
                output_tokens=out_tok,
            )
        except Exception:
            pass

        if text.strip().startswith(("Lỗi", "⏳", "Provider không khả dụng")):
            return ProviderRunResult(
                provider_key, provider_label, model_name, text="", error=text, elapsed_seconds=elapsed
            )
        return ProviderRunResult(provider_key, provider_label, model_name, text=text, elapsed_seconds=elapsed)
    except Exception as e:
        return ProviderRunResult(
            provider_key,
            provider_label,
            model_name,
            error=f"Lỗi không mong đợi khi gọi {provider_label}: {e}",
            elapsed_seconds=time.monotonic() - t0,
        )


def compare_providers(
    llm_integration,
    provider_specs: list[dict],
    student_weaknesses,
    predicted_gpa,
    student_profile=None,
    runtime_documents=None,
    use_rag: bool = True,
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    use_warehouse_data: bool = True,
    role: str = "Giảng viên / CVHT",
) -> list[ProviderRunResult]:
    """Gọi ĐỒNG THỜI nhiều provider cho CÙNG 1 học sinh/điểm yếu, trả về danh
    sách kết quả (giữ đúng thứ tự `provider_specs`, không phải thứ tự hoàn
    thành) để UI hiển thị so sánh cạnh nhau.

    provider_specs: mỗi phần tử là 1 dict {
        "provider_key": "gemini" | "groq" | "openai" | "huggingface" | "ollama",
        "provider_label": tên hiển thị,
        "model_name": tên model cụ thể,
        "call_kwargs": dict tham số riêng của provider đó (api_key/hf_token/base_url),
    }

    Giới hạn số luồng chạy đồng thời bằng dss.config.MAX_CONCURRENT_REQUESTS —
    nếu so sánh nhiều hơn số đó, các provider dư sẽ đợi tới lượt thay vì bắn hết
    request cùng lúc (giảm rủi ro rate-limit dây chuyền, xem Phase 7).
    """
    if not provider_specs:
        return []

    # Workstream C (Issue AIGOV-001): this deliberately does NOT route
    # through LLMGateway.stream_generate()'s fallback cascade — the whole
    # point of "Compare AI" is to know whether EACH specifically-requested
    # provider works, not to silently receive a different provider's answer
    # mislabeled as the one being compared. It DOES now go through the same
    # quota/rate-limit gate every other AI call path uses (see
    # LLMGateway.check_quota_and_rate_limit), so a Lecturer cannot use
    # Compare AI to bypass the organization's monthly AI quota or the
    # per-user token quota — previously neither was enforced here at all.
    from dss.services.llm_gateway import GatewayError, LLMGateway

    gateway = LLMGateway(llm_integration)
    try:
        gateway.check_quota_and_rate_limit(
            user_id="compare_ai_user",
            role="Giảng viên / CVHT",
            prompt=str(student_weaknesses),
        )
    except GatewayError as exc:
        return [
            ProviderRunResult(
                spec["provider_key"],
                spec.get("provider_label", spec["provider_key"]),
                spec.get("model_name", ""),
                error=str(exc),
            )
            for spec in provider_specs
        ]

    max_workers = min(len(provider_specs), max(1, dss_config.MAX_CONCURRENT_REQUESTS))
    results_by_key: dict[str, ProviderRunResult] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_spec = {
            executor.submit(
                _run_one_provider,
                llm_integration,
                spec["provider_key"],
                spec.get("provider_label", spec["provider_key"]),
                spec.get("model_name", ""),
                spec.get("call_kwargs", {}),
                student_weaknesses,
                predicted_gpa,
                use_rag,
                embedding_model_name,
                use_warehouse_data,
                student_profile,
                runtime_documents,
                role,
            ): spec
            for spec in provider_specs
        }
        for future in as_completed(future_to_spec):
            spec = future_to_spec[future]
            results_by_key[spec["provider_key"]] = future.result()

    # Trả về đúng thứ tự người dùng đã chọn, không phải thứ tự hoàn thành song song.
    return [results_by_key[spec["provider_key"]] for spec in provider_specs]


def resolve_auto_provider(llm_integration) -> Optional[dict]:
    """Tự động chọn 1 provider AI sẵn sàng — dùng cho các nơi Sinh viên gọi AI
    mà KHÔNG được thấy khái niệm "provider"/"API key" (vd. hộp hỏi nhanh trên
    Dashboard). Cùng thứ tự ưu tiên đã dùng trong `ai_advisor.py` (mặc định hệ
    thống do Admin đặt > Ollama local > provider cloud đầu tiên có sẵn key qua
    secrets/env) — tách ra đây để dùng lại được ở nhiều nơi, không phải chỉ tab
    Tư vấn AI. Trả về None nếu không có provider nào sẵn sàng (nơi gọi tự
    chuyển sang thông báo phù hợp, không phải lỗi)."""
    from dss.core.models import AI_MODEL_CATALOG, _check_ollama_running
    from dss.services import admin_ai_config
    from dss.services.llm_gateway import is_known_unhealthy

    label_by_key = {
        "huggingface": "Hugging Face (Local/Cloud)",
        "gemini": "Google Gemini",
        "groq": "Groq (Siêu tốc)",
        "ollama": "Ollama (Local)",
        "openai": "OpenAI (ChatGPT)",
    }
    default_cfg = admin_ai_config.get_default_provider()
    if default_cfg:
        provider_key = default_cfg["provider_key"]
        model_name = default_cfg["model_name"]
        api_key = (
            llm_integration.get_api_key_from_secrets(provider_key)
            if provider_key in ("gemini", "groq", "openai")
            else ""
        )
        # Mục 9 — KHÔNG tự ý chọn mặc định Admin đã đặt nếu lần kiểm tra sức
        # khoẻ gần nhất (trong TTL) đã XÁC NHẬN provider đó không dùng được
        # (vd. BILLING_REQUIRED) — rơi xuống auto-detect thay vì im lặng trả
        # về 1 provider đã biết là hỏng.
        if (provider_key == "ollama" or api_key or provider_key == "huggingface") and not is_known_unhealthy(
            provider_key
        ):
            return {
                "provider_key": provider_key,
                "model_name": model_name,
                "api_key": api_key,
                "label": label_by_key.get(provider_key, provider_key),
            }

    if _check_ollama_running():
        return {
            "provider_key": "ollama",
            "model_name": AI_MODEL_CATALOG["ollama"][0],
            "api_key": "",
            "label": "Ollama (Local)",
        }

    for prov_key, prov_label in [
        ("gemini", "Google Gemini"),
        ("groq", "Groq (Siêu tốc)"),
        ("openai", "OpenAI (ChatGPT)"),
    ]:
        if is_known_unhealthy(prov_key):
            continue  # đã xác nhận không dùng được (vd. hết hạn mức thanh toán) — không chọn lại
        found_key = llm_integration.get_api_key_from_secrets(prov_key)
        if found_key:
            # Gemini: model nhanh nhất đứng đầu danh sách; Groq/OpenAI giữ lựa chọn thứ 2 như cũ.
            _model = AI_MODEL_CATALOG[prov_key][0 if prov_key == "gemini" else 1]
            return {"provider_key": prov_key, "model_name": _model, "api_key": found_key, "label": prov_label}

    return None


_GATEWAY_INSTANCE = None
