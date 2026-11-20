"""Report service — Phase 2 của kế hoạch refactor EduDSS.

`build_demo_study_plan` là logic THUẦN (không gọi `st.*` nào) tạo lộ trình học
tập cá nhân hóa khi chưa cấu hình LLM thật (chế độ Demo/offline) — trước đây
định nghĩa lẫn trong `dss/tabs/ai_advisor.py`. Đây đúng vai trò "Report
Service" trong kiến trúc mục tiêu (mục 18 bản yêu cầu refactor): tổng hợp kết
quả ML + RAG thành nội dung trình bày, KHÔNG tự vẽ UI.
"""

from __future__ import annotations


def build_demo_study_plan(student_id, predicted_gpa, weaknesses, profile, retrieved_docs=None, personal_goal=""):
    """Tạo kế hoạch demo khi chưa cấu hình AI provider.

    Trả về (plan_text, week_plan): `week_plan` là danh sách cấu trúc
    [{"week", "topic", "action", "done"}] — mỗi tuần nhắm ĐÚNG 1 điểm yếu theo thứ
    tự ưu tiên (weaknesses đã được ai_advisor_tab sắp xếp từ nặng nhất), kèm hành
    động cụ thể lấy từ tài liệu RAG khớp chủ đề đó nếu tìm được (nếu không, dùng
    mẫu câu chung làm phương án dự phòng). `week_plan` dùng để dựng checklist nhắc
    nhở (`_render_weekly_reminder_checklist` trong tabs/ai_advisor.py) độc lập
    với `plan_text`.
    """
    # TOPIC_SCORE_COLUMNS import cục bộ (không phải top-level) để tránh vòng phụ
    # thuộc services -> core lúc module này được import bởi core/ ở nơi khác.
    from dss.core.data_helpers import TOPIC_SCORE_COLUMNS

    weeks = int((profile or {}).get("plan_weeks", 4))
    risk_level = (profile or {}).get("risk_level", "trung bình")
    progress_note = (profile or {}).get("progress_note", "chưa có dữ liệu tiến bộ rõ ràng")
    weak_text = ", ".join(weaknesses[:5]) if weaknesses else "chưa có điểm yếu rõ ràng"
    docs = retrieved_docs or []
    doc_lines = "\n".join([f"- {d.get('title', 'Tài liệu')}" for d in docs[:5]]) if docs else "- Chưa có tài liệu gợi ý"
    goal_line = f"- Điều bạn đang hướng tới: {personal_goal}\n" if personal_goal else ""

    fallback_templates = [
        "xây lại nền tảng: 2 buổi ôn lý thuyết trọng tâm + 1 buổi bài tập cơ bản, ghi lại các lỗ hổng kiến thức.",
        "chuẩn hóa dạng bài: luyện theo từng dạng thường sai, mỗi buổi đều có phần tự chữa lỗi và rút kinh nghiệm.",
        "tăng cường thực hành: 1 buổi đề thời gian thực + 1 buổi chữa đề chi tiết + 1 buổi tổng hợp ghi chú cá nhân.",
        "củng cố bền vững: mô phỏng kiểm tra ngắn cuối tuần, đo KPI và điều chỉnh lịch học tuần sau.",
    ]

    def _weakness_label(w):
        col = str(w).split(" (")[0].strip()
        return TOPIC_SCORE_COLUMNS.get(col, col.replace('_', ' ').strip().capitalize())

    def _find_matching_doc(label):
        label_words = [w for w in label.lower().replace('_', ' ').split() if len(w) > 2]
        for d in docs:
            haystack = ' '.join(str(t).lower() for t in d.get('tags', [])) + ' ' + str(d.get('title', '')).lower()
            if any(w in haystack for w in label_words):
                return d
        return None

    # Xây danh sách cấu trúc theo tuần — "tối ưu hoá" đơn giản: tuần đầu luôn nhắm
    # điểm yếu nghiêm trọng nhất (weaknesses đã sắp theo mức độ lệch), xoay vòng nếu
    # số điểm yếu ít hơn số tuần.
    week_plan = []
    for i in range(1, weeks + 1):
        if weaknesses:
            label = _weakness_label(weaknesses[(i - 1) % len(weaknesses)])
            matched_doc = _find_matching_doc(label)
        else:
            label, matched_doc = None, None

        if matched_doc:
            action = (
                f"Chủ đề **{label}** — theo hướng dẫn \"{matched_doc.get('title')}\": {matched_doc.get('content', '')}"
            )
        elif label:
            action = f"Chủ đề **{label}**: {fallback_templates[(i - 1) % len(fallback_templates)]}"
        else:
            action = fallback_templates[(i - 1) % len(fallback_templates)]

        week_plan.append({"week": i, "topic": label, "action": action, "done": False})

    week_lines = [f"- **Tuần {wp['week']}**: {wp['action']}" for wp in week_plan]
    week_plan_text = "\n".join(week_lines)

    # Tính liều lượng can thiệp thực chứng (Dosage Calculation - Section 9)
    # Không áp đặt con số cố định bịa đặt cho mọi sinh viên.
    num_weaknesses = len(weaknesses)
    l_prof = (profile or {}).get("learning_profile")
    has_velocity = False
    if l_prof and isinstance(l_prof, dict):
        from dss.services.learning_profile import observed_number

        trajectory = l_prof.get("trajectory") or {}
        vel = observed_number(trajectory.get("learning_velocity")) if isinstance(trajectory, dict) else None
        has_velocity = vel is not None and vel > 0
        vel = vel if has_velocity else 1.0
        base_h = max(2.5, min(10.0, (num_weaknesses * 1.5 + 2.0) / max(vel, 0.5)))
        target_exercises = int(max(8, min(30, (num_weaknesses * 4 + 6) / max(vel, 0.7))))
    else:
        base_h = max(2.5, min(10.0, num_weaknesses * 1.2 + 2.5))
        target_exercises = int(max(8, min(30, num_weaknesses * 3 + 8)))

    dosage_text = (
        f"- Thời lượng theo chính sách mô phỏng: khoảng **{base_h:.1f} giờ/tuần**\n"
        f"- Khối lượng theo chính sách mô phỏng: khoảng **{target_exercises} bài/tuần**"
    )
    if isinstance(l_prof, dict) and not has_velocity:
        dosage_text = "- Chưa đủ dữ liệu quan sát để đề xuất thời lượng và khối lượng bài tập."
    else:
        dosage_text += "\n- Các con số là gợi ý mô phỏng, chưa được kiểm chứng hiệu quả."

    plan_text = f"""
### 🧭 Kế hoạch học tập (Chế độ demo)
- Sinh viên: `{student_id}`
- GPA dự đoán: **{predicted_gpa:.2f}**
- Mức rủi ro: **{risk_level}**
- Tiến độ gần đây: {progress_note}
{goal_line}
#### 1) Điểm cần ưu tiên
- {weak_text}

#### 2) Kế hoạch {weeks} tuần (đã ưu tiên đúng lỗ hổng nặng nhất trước)
{week_plan_text}

#### 3) Liều lượng can thiệp đề xuất mỗi tuần (Cá nhân hóa theo mức thiếu hụt)
{dosage_text}
- Tiêu chí đạt: Giảm thiểu lỗi lặp lại và hoàn thành các câu hỏi kiểm chứng theo tuần

#### 4) Tài liệu đề xuất (RAG/demo)
{doc_lines}

> Đây là chế độ mô phỏng không cần API. Khi cấu hình provider đầy đủ, kế hoạch sẽ chi tiết và cá nhân hóa sâu hơn.
"""
    return plan_text, week_plan
