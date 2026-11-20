# Kế hoạch Redesign toàn diện: Hệ thống Hỗ trợ Ra Quyết định Nghề nghiệp (Career Decision Support System - EduDSS)

Tài liệu thiết kế kỹ thuật và kế hoạch thực thi chuyển đổi chức năng **"AI Tư vấn hướng nghiệp"** từ mô hình cũ đơn giản (*Sở thích + Điểm số → Nghề phù hợp*) thành **Career Decision Support System (CDSS)** toàn diện, minh bạch, có thể truy vết và cá nhân hoá theo đúng 31 tiêu chuẩn nghiệp vụ được yêu cầu.

---

## 1. Mục tiêu & 9 Câu hỏi Cốt lõi của Hệ thống Mới

Hệ thống được thiết kế để trả lời trọn vẹn 9 câu hỏi then chốt của sinh viên:
1. **Tôi phù hợp nghề nào?** → Xếp hạng Top 3–5 nghề theo Career Fit (0–100%).
2. **Vì sao tôi phù hợp?** → Bóc tách minh chứng cụ thể từ 4 nguồn dữ liệu: Môn học/Điểm số, Dự án/Hoạt động, Kỹ năng tự nhận & đã xác thực, Sở thích & Phong cách làm việc.
3. **Tôi đang sẵn sàng đến mức nào?** → Chỉ số Career Readiness (0–100%) tách biệt hoàn toàn với Career Fit.
4. **Tôi còn thiếu kỹ năng gì?** → Bảng Gap Analysis chia 3 nhóm: *Đã có (✓)*, *Cần củng cố (△)*, *Chưa có (✕)* với 4 mức ưu tiên (*Critical, High, Medium, Nice-to-have*), bao gồm cả kỹ năng chuyên môn lẫn sản phẩm thực tế (portfolio/dự án/phỏng vấn).
5. **Nghề nào phù hợp với năng lực nhưng không phù hợp với điều kiện cá nhân?** → Bộ lọc phát hiện xung đột năng lực cao (Fit ≥ 70%) nhưng vướng ràng buộc (Constraint < 60% do ca kíp, làm tại chỗ, hoặc tiếng Anh).
6. **Nếu muốn theo nghề đó thì phải học gì?** → Từng hành động cụ thể gắn với tài nguyên học tập uy tín, nỗ lực ước tính và kết quả đầu ra đo lường được.
7. **Tôi cần làm gì trong 1 tháng / 3 tháng / 6 tháng?** → Lộ trình cá nhân hoá theo đúng 3 cột mốc: 30 ngày (1 tháng), 90 ngày (3 tháng), 180 ngày (6 tháng).
8. **Tôi có thể chuyển từ nghề A sang nghề B như thế nào?** → Module Career Transition: Kỹ năng dùng chung (Shared Skills), Kỹ năng còn thiếu (Missing Skills), Độ khả thi chuyển dịch, và Lộ trình chuyển đổi.
9. **Nếu mục tiêu hoặc điều kiện thay đổi thì khuyến nghị thay đổi ra sao?** → Module What-if Analysis: Giả lập nâng kỹ năng, thay đổi ràng buộc làm việc, điều chỉnh khung thời gian, tự động tính lại điểm và giải thích biến thiên (Δ Fit, Δ Readiness).

---

## 2. Kiến trúc Pipeline Mới

```
Student Profile (Học thuật + GPA + Điểm chuyên đề)
   ├── Academic Competency (Map Subject -> Domain)
   ├── Skill Profile (Kỹ năng + Evidence + Confidence + Source)
   ├── Experience Profile (Dự án, Luận văn, Thực tập, Chứng chỉ, Portfolio)
   ├── Interest Profile (Mini-assessment 7 chiều theo thang 1–5)
   ├── Work-style Profile (7 trục phong cách làm việc)
   ├── Career Constraints (Địa điểm, Ca kíp, Remote, Tiếng Anh, Giờ học/tuần)
   └── Career Goal (Mục tiêu vị trí, Thời gian 1–24 tháng)
         │
         ▼
Career Knowledge Base (12 vai trò chuẩn hoá, Required/Preferred weights, Resources)
         │
         ├──► Career Fit Scoring (Skill 30% + Academic 20% + Interest 20% + Exp 10% + WorkStyle 10% + Constraint 10%)
         ├──► Career Readiness Scoring (Required Skills 35% + Project 20% + Exp 15% + Portfolio 10% + English 10% + Interview 10%)
         ├──► Gap Analysis (Đã có / Cần củng cố / Chưa có; Phân cấp Critical -> Nice-to-have)
         ├──► Career Ranking (Top 3–5 nghề + Đánh giá Độ tin cậy High/Med/Low)
         ├──► Career Roadmap (Milestones: 1 tháng / 3 tháng / 6 tháng cá nhân hoá theo Gap)
         ├──► What-if Simulator (Giả lập thay đổi Skill/Constraint/Goal & tính lại Delta)
         ├──► Career Transition & Alternative Paths (Primary / Secondary / Long-term)
         ├──► Feedback Loop (Đánh dấu hoàn thành task, cập nhật skill -> Recompute)
         └──► Grounded AI Career Advisor (Prompt an toàn, chống bịa đặt, có Offline Fallback)
```

---

## 3. Chi tiết Thay đổi Kỹ thuật

### Component 1: `dss/services/career_profile.py`
- **Academic Profile**:
  - Bổ sung tính toán `gpa` từ dữ liệu thực tế (`final_score`, `gpa_previous`, hoặc trung bình các môn).
  - Mở rộng từ điển `SUBJECT_TO_COMPETENCY_DOMAIN` hỗ trợ cả tiếng Việt và tiếng Anh:
    - *Statistics / diem_thong_ke* → `Data Analysis / Quantitative Skills`
    - *Database / diem_xu_ly_du_lieu / diem_csdl* → `SQL / Data Engineering`
    - *Machine Learning / diem_machine_learning* → `AI / Data Science`
    - *Web Programming / diem_lap_trinh / diem_web* → `Software / Web Development`
    - *Software Analysis / diem_ptpm* → `Business Analysis`
    - *Data Visualization / diem_truc_quan_hoa* → `Data Visualization / BI`
  - Tự động phát hiện `strengths` (domain ≥ 7.0) và `weaknesses` (domain < 5.5).
- **Skill Profile**:
  - Đầy đủ danh mục 4 nhóm: Technical (10 skills), Business (4 skills), Soft (5 skills), Language (English).
  - Cấu trúc `SkillItem`: `skill_name`, `category`, `skill_level` (None, Basic, Intermediate, Advanced), `evidence` (List[str]), `confidence` (low, medium, high), `source` (self_assessment, academic_score, project, experience, certificate).
  - Quy tắc bằng chứng: Không tự nhận kỹ năng nếu không có evidence; Điểm học thuật cao chỉ cấp mức gián tiếp (Basic, medium confidence); Dự án/kinh nghiệm thực tế nâng lên high confidence.
- **Experience Profile**:
  - Hỗ trợ 7 loại hình: `internship`, `employment`, `project`, `thesis`, `certification`, `extracurricular`, `portfolio`.
  - Tự động suy ra bằng chứng kỹ năng khi thêm kinh nghiệm (vd: Dự án ML → Python + ML + Data Processing; Thực tập → Teamwork + Process + Excel/Tools).
  - Hỗ trợ ghi nhận trạng thái Portfolio và Luyện tập phỏng vấn (Interview prep).
- **Interest Profile**:
  - Mini-assessment 7 trục theo đúng đặc tả:
    1. *data*: Làm việc với dữ liệu
    2. *system_building*: Xây dựng hệ thống
    3. *business_problem*: Giải quyết bài toán kinh doanh
    4. *client_communication*: Giao tiếp với khách hàng
    5. *ai_research*: Nghiên cứu AI
    6. *ui_ux_design*: Thiết kế giao diện
    7. *system_operations*: Vận hành hệ thống
- **Work-Style Profile**:
  - 7 trục đánh giá (1–5): Độc lập vs Nhóm, Technical vs Business, Phân tích vs Giao tiếp, Ổn định vs Thay đổi, Văn phòng vs Hiện trường, Giờ hành chính vs Ca kíp, Chuyên gia vs Quản lý.
- **Career Constraints**:
  - `desired_location`, `willingness_to_relocate`, `preferred_hours` (office_hours/shift_ok), `shift_acceptance`, `expected_salary_band`, `english_level`, `learning_hours_per_week`, `preferred_industry`, `remote_preference` (remote/on_site/flexible).
- **Career Goal**:
  - `goal_type` (Internship, Fresher job, Junior role, Career switching, Long-term career), `target_role_id`, `target_timeframe_months` (1 đến 24 tháng).

### Component 2: `dss/services/career_knowledge_base.py`
- Cập nhật chuẩn hoá 12 vai trò:
  1. **Data Analyst**
  2. **Data Engineer**
  3. **Data Scientist**
  4. **Machine Learning Engineer**
  5. **Business Analyst**
  6. **Backend Developer**
  7. **Frontend Developer**
  8. **QA / Tester**
  9. **DevOps / Cloud Engineer**
  10. **Database Administrator**
  11. **AI Engineer**
  12. **System Analyst**
- Mỗi vai trò có:
  - `required_skills` (trọng số 0.1–1.0)
  - `preferred_skills` (trọng số 0.1–1.0)
  - `academic_domains` (trọng số 0.1–1.0)
  - `interest_axes` (trọng số theo 7 trục mới)
  - `work_style` (kỳ vọng 1–5 theo 7 trục)
  - `typical_tasks` (nhiệm vụ điển hình)
  - `minimum_english` (Beginner/Intermediate/Advanced/Fluent)
  - `preferred_hours` (office_hours/shift_ok)
  - `remote_friendly` (remote/on_site/flexible)
  - `adjacent_roles` (vai trò liền kề)
  - `learning_resources` (tài nguyên uy tín có URL thực tế & gắn skill mục tiêu)
  - `alternative_path_notes` (giải thích lý do chọn làm bước đệm hoặc mục tiêu dài hạn)

### Component 3: `dss/services/career_scoring.py`
- **Career Fit Score (0–100%)**:
  - Trọng số tập trung có thể cấu hình:
    ```python
    CAREER_FIT_WEIGHTS = {
        "skill": 0.30,
        "academic": 0.20,
        "interest": 0.20,
        "experience": 0.10,
        "work_style": 0.10,
        "constraint": 0.10,
    }
    ```
  - `Skill Match`: Công thức phân biệt bắt buộc vs nên có:
    $$\text{SkillMatch} = 0.8 \times \frac{\sum w_i \cdot l_i}{\sum w_i} (\text{required}) + 0.2 \times \frac{\sum w_j \cdot l_j}{\sum w_j} (\text{preferred})$$
  - `Constraint Match`: Phạt điểm khi có xung đột (yêu cầu làm ca trong khi chỉ muốn giờ hành chính: -0.35; yêu cầu on-site khi chỉ muốn remote: -0.25; thiếu chuẩn tiếng Anh: -0.1 đến -0.25; không sẵn sàng chuyển chỗ ở khi khác tỉnh/thành: -0.2).
  - Phân tích xung đột Năng lực vs Ràng buộc: Hàm `detect_constraint_conflicts(profile, role, fit_result)` tìm các nghề có điểm năng lực cao (Academic + Skill ≥ 70%) nhưng điểm ràng buộc thấp (< 60%), trả lời trực diện Câu hỏi 5.
- **Career Readiness Score (0–100%)**:
  - Trọng số tập trung có thể cấu hình:
    ```python
    CAREER_READINESS_WEIGHTS = {
        "required_skill_coverage": 0.35,
        "project_evidence": 0.20,
        "experience": 0.15,
        "portfolio": 0.10,
        "english": 0.10,
        "interview_prep": 0.10,
    }
    ```
  - Bóc tách đầy đủ bằng chứng cho từng thành phần.
- **Độ tin cậy khuyến nghị (Confidence)**:
  - *High*: Hồ sơ có đủ dữ liệu học thuật, kỹ năng có bằng chứng, kinh nghiệm, sở thích, ràng buộc.
  - *Medium*: Hồ sơ có học thuật và kỹ năng nhưng chưa có dự án/ràng buộc.
  - *Low*: Hồ sơ mới chỉ có điểm số hoặc sở thích đơn lẻ → Hiển thị cảnh báo khuyến nghị người dùng bổ sung dữ liệu.

### Component 4: `dss/services/career_gap_analysis.py`
- Phân nhóm 3 trạng thái:
  - `ĐÃ CÓ (✓)`: Kỹ năng đạt mức Intermediate trở lên.
  - `CẦN CỦNG CỐ (△)`: Kỹ năng ở mức Basic hoặc mới có bằng chứng gián tiếp từ môn học.
  - `CHƯA CÓ (✕)`: Chưa có dữ liệu hoặc mức None.
- Xếp hạng ưu tiên:
  - `Critical`: Kỹ năng bắt buộc (required) có trọng số cao (≥ 0.8) mà sinh viên chưa có.
  - `High`: Kỹ năng bắt buộc trọng số trung bình (≥ 0.5) hoặc kỹ năng nên có quan trọng.
  - `Medium`: Kỹ năng bắt buộc mức độ nền tảng hoặc kỹ năng nên có thông thường.
  - `Nice-to-have`: Kỹ năng phụ trợ hoặc kỹ năng đã đạt chuẩn.
- Bổ sung khoảng cách về tạo tác nghề nghiệp (Practical Artifact Gaps):
  - Kiểm tra xem sinh viên đã có Portfolio liên quan, Dự án mẫu (capstone/dashboard), và Chuẩn bị phỏng vấn kỹ thuật chưa.

### Component 5: `dss/services/career_roadmap.py`
- Lộ trình thích ứng cá nhân hoá theo Gap thực tế của từng sinh viên:
  - **1 THÁNG (30 NGÀY)**: Xử lý kỹ năng `Critical` & `High`, bài tập mini-project giải quyết vấn đề cốt lõi.
  - **3 THÁNG (90 NGÀY)**: Kỹ năng `Medium`, xây dựng dự án hoàn chỉnh / dashboard / pipeline đầu-cuối.
  - **6 THÁNG (180 NGÀY)**: Hoàn thiện Portfolio, chuẩn bị CV, luyện tập phỏng vấn kỹ thuật (SQL/Coding/Case interview), ứng tuyển vị trí Fresher/Junior.
- Mỗi nhiệm vụ (Roadmap Task) chuẩn hoá đủ 7 trường:
  - `action`: Hành động cụ thể.
  - `reason`: Lý do vì sao cần học (dẫn chứng từ yêu cầu vai trò và hiện trạng).
  - `resource`: Tên tài liệu/khoá học.
  - `resource_url`: Đường dẫn học tập thực tế.
  - `estimated_effort`: Nỗ lực ước tính (giờ/tuần).
  - `target_result`: Kết quả đầu ra kiểm chứng được.
  - `priority`: Mức độ ưu tiên.
- **Career Alternative Path**:
  - `Primary Path` (Nghề chính).
  - `Secondary Path` (Nghề có thể nộp đồng thời, giải thích rõ kỹ năng tương đồng).
  - `Long-term Path` (Nghề phát triển dài hạn, lộ trình tích luỹ kinh nghiệm).
- **Career Transition Plan**:
  - Phân tích từ Nghề A sang Nghề B: Kỹ năng dùng chung (Shared Skills), Kỹ năng còn thiếu (Missing Skills), Độ tương đồng %, và Lộ trình chuyển đổi từng bước.

### Component 6: `dss/services/career_whatif.py`
- Xây dựng công cụ What-if phân tích quyết định:
  - *Kịch bản 1 (Skill Upgrade)*: "Nếu tôi học thêm hoặc nâng kỹ năng X lên mức Y thì Career Fit và Readiness thay đổi thế nào?"
  - *Kịch bản 2 (Constraint Adjustment)*: "Nếu tôi chấp nhận làm ca, hoặc nếu tôi chuyển sang làm việc tại văn phòng/remote thì những nghề nào được mở ra?"
  - *Kịch bản 3 (Timeframe Priority)*: "Nếu tôi muốn có việc trong vòng 3 tháng thay vì 6 tháng, thứ tự ưu tiên nghề nghiệp thay đổi ra sao?"
  - *Kịch bản 4 (Constraint Filtering)*: "Nếu tôi kiên quyết không làm ca đêm / không thể chuyển nơi ở, những nghề nào sẽ bị loại trừ?"
- Tự động tính toán Delta (trước vs sau) và sinh giải thích nguyên nhân rõ ràng, minh bạch.

### Component 7: `dss/services/career_ai_advisor.py` (Mới)
- **Context Builder**:
  - Tổng hợp hồ sơ chuẩn hoá: Danh tính mã hoá, Điểm học thuật & thế mạnh/điểm yếu, Kỹ năng & bằng chứng, Kinh nghiệm, Sở thích 7 chiều, Ràng buộc, Mục tiêu, Top nghề với Fit/Readiness %, Gap chi tiết, Lộ trình 30/90/180 ngày.
- **Strict Anti-Hallucination Guardrails**:
  - Nghiêm cấm bịa đặt kỹ năng chưa có trong hồ sơ.
  - Nếu thiếu dữ liệu, bắt buộc trả lời: *"Hiện chưa có đủ dữ liệu để đánh giá kỹ năng... Vui lòng bổ sung tại mục Hồ sơ nghề nghiệp."*
- **Grounded Offline Deterministic Fallback**:
  - Khi LLM offline hoặc chưa cấu hình API key, hệ thống kích hoạt bộ giải đáp quy tắc thông minh (Rule-based Decision Engine) dựa trực tiếp trên các phép toán đã tính để trả lời chính xác 5 câu hỏi thường gặp:
    1. *Vì sao tôi hợp nghề A hơn nghề B?* → So sánh từng cặp chỉ số, thế mạnh môn học và khoảng cách kỹ năng.
    2. *Điểm yếu lớn nhất của tôi là gì?* → Trích xuất các Gap có mức `Critical` và `High`.
    3. *Tôi nên học kỹ năng nào trước?* → Phân tích ưu tiên theo Gap Priority và thời gian đầu tư.
    4. *Tôi có đủ khả năng apply Fresher chưa?* → Đánh giá dựa trên điểm Readiness và các tạo tác thực tế.
    5. *Nếu chỉ có 2 tháng thì nên học gì?* → Trích xuất các task 30 ngày và 60 ngày quan trọng nhất.

### Component 8: UI Redesign `dss/tabs/advisory.py`
Trang Tư vấn nghề nghiệp được tổ chức lại thành 7 Tabs nghiệp vụ chuyên sâu:
- **Tab 1: 1️⃣ Hồ sơ nghề nghiệp**
  - Huy hiệu minh bạch: `Hồ sơ minh họa (dữ liệu mô phỏng)` khi ở chế độ DEMO hoặc `Dữ liệu học tập thực tế` khi ở chế độ REAL.
  - Thẻ điểm học thuật: GPA tổng quan, điểm từng chuyên đề, thẻ điểm mạnh / điểm cần cải thiện.
  - Bảng tự đánh giá kỹ năng: 4 nhóm (Technical, Business, Soft, Language), thanh trượt chọn mức độ, hiển thị nhãn bằng chứng và nguồn (`academic_score`, `project`, `self_assessment`).
  - Form thêm kinh nghiệm & tạo tác: Hỗ trợ đính kèm portfolio, chứng chỉ, tự động link bằng chứng kỹ năng.
  - Mini-assessment sở thích: 7 thang trượt trực quan (1–5).
  - Trục phong cách làm việc: 7 thang trượt song song đối chiếu.
  - Thiết lập ràng buộc cá nhân & mục tiêu (có đầy đủ vị trí, chuyển chỗ ở, ca kíp, mức lương, remote, thời gian).
- **Tab 2: 2️⃣ Nghề phù hợp & Khuyến nghị**
  - Thẻ độ tin cậy khuyến nghị (Confidence Badge: High / Medium / Low) kèm giải thích.
  - Top 3–5 nghề: Hiển thị song song `Career Fit`, `Career Readiness`, `Khoảng cách kỹ năng`.
  - Khối giải thích "Vì sao nghề này phù hợp?": Bóc tách rõ *Điểm mạnh*, *Minh chứng cụ thể* (môn học, dự án, kỹ năng), và *Thách thức / Điểm chưa phù hợp*.
  - Khối cảnh báo đặc biệt (Trả lời Câu hỏi 5): *Nghề phù hợp năng lực nhưng vướng ràng buộc cá nhân* (vd: Kỹ thuật tốt nhưng yêu cầu làm ca/on-site).
- **Tab 3: 3️⃣ So sánh nghề nghiệp**
  - Cho phép chọn tối đa 3 nghề để so sánh dạng ma trận đối đầu.
  - So sánh chi tiết: Fit, Readiness, Khoảng cách, Kỹ năng yêu cầu, Phong cách làm việc, Mức độ sẵn sàng.
- **Tab 4: 4️⃣ Khoảng cách kỹ năng (Gap Analysis)**
  - Chọn nghề mục tiêu để soi chi tiết.
  - 3 cột trạng thái: `ĐÃ CÓ (✓)`, `CẦN CỦNG CỐ (△)`, `CHƯA CÓ (✕)`.
  - Huy hiệu ưu tiên rõ ràng: `Critical` (đỏ), `High` (cam), `Medium` (xanh dương), `Nice-to-have` (xanh lá).
  - Đánh giá khoảng cách tạo tác nghề nghiệp (Portfolio, Dự án thực hành, Phỏng vấn).
- **Tab 5: 5️⃣ Lộ trình phát triển & Chuyển nghề**
  - Lộ trình 3 mốc thời gian: `30 ngày (1 tháng)`, `90 ngày (3 tháng)`, `180 ngày (6 tháng)`.
  - Từng thẻ công việc hiển thị rõ: Hành động, Lý do, Tài nguyên học có link, Nỗ lực ước tính, Kết quả mong đợi, Mức độ ưu tiên.
  - Con đường thay thế (Alternative Paths): Phân tích Nghề hiện tại → Nghề dự phòng nộp kèm → Mục tiêu dài hạn kèm giải thích lý do.
  - Chuyển đổi nghề nghiệp (Career Transition Explorer): Chọn Nghề A → Nghề B, xem Kỹ năng chung, Kỹ năng thiếu, và Lộ trình chuyển đổi.
- **Tab 6: 6️⃣ Giả lập What-if & Cập nhật tiến độ**
  - Bộ giả lập What-if:
    - Thử nghiệm nâng cấp kỹ năng (vd: Nâng SQL từ Basic lên Intermediate/Advanced) → Xem ngay Fit và Readiness tăng bao nhiêu %.
    - Thử nghiệm đổi ràng buộc (vd: Bật "Chấp nhận làm ca", "Ưu tiên remote") → Xem khuyến nghị thay đổi thế nào.
    - Lọc nghề theo thời gian đạt mục tiêu (1 tháng / 3 tháng / 6 tháng).
  - Vòng lặp phản hồi (Feedback Loop): Cho phép sinh viên đánh dấu "Đã hoàn thành" nhiệm vụ hoặc tự cập nhật chứng chỉ mới → Tự động tính toán lại Readiness và cập nhật Lộ trình ngay lập tức.
- **Tab 7: 7️⃣ AI Career Advisor**
  - Chat tương tác với AI Cố vấn nghề nghiệp.
  - Các nút câu hỏi nhanh gắn liền với 5 câu hỏi trọng tâm.
  - Tích hợp hệ thống LLM Gateway đã có sẵn (bảo mật dữ liệu, kiểm soát token, chống prompt injection).
  - Tự động chuyển sang Grounded Deterministic Advisor khi LLM ngoại tuyến để không làm gián đoạn trải nghiệm người dùng.

---

## 4. Kế hoạch Kiểm thử & Xác minh (Verification Plan)

### Automated Tests (`tests/test_career_advisor.py`)
Mở rộng bộ test hồi quy hiện có lên tối thiểu 22 test cases bao phủ toàn diện:
1. `test_career_knowledge_base_has_all_12_roles`: Kiểm tra đủ 12 vai trò với đầy đủ metadata.
2. `test_subject_to_domain_mapping_supports_vn_and_en`: Xác minh map đúng cả tên tiếng Việt (`diem_thong_ke`...) lẫn tiếng Anh (`Statistics`...).
3. `test_gpa_computation_and_strengths_weaknesses`: Xác minh tính GPA và phân loại mạnh/yếu chuẩn xác.
4. `test_no_skill_claimed_without_evidence`: Không tự nhận có kỹ năng nếu không có evidence.
5. `test_academic_gives_basic_experience_gives_high_confidence`: Phân cấp độ tin cậy minh chứng chuẩn xác.
6. `test_career_fit_and_readiness_weights_sum_to_one`: Tổng trọng số chuẩn hoá = 1.0.
7. `test_required_vs_preferred_skill_penalty`: Thiếu required skill phạt điểm nặng hơn preferred.
8. `test_fit_and_readiness_independence`: Điểm Fit và Readiness phân tách độc lập (vd: Fit 84%, Readiness 46%).
9. `test_constraint_penalty_application`: Phạt điểm khi có xung đột ca kíp, remote, tiếng Anh.
10. `test_detect_capability_vs_constraint_conflicts`: Phát hiện đúng nghề hợp năng lực nhưng vướng ràng buộc (Câu hỏi 5).
11. `test_gap_analysis_priority_hierarchy`: Gap phân loại đúng Critical/High/Medium/Nice-to-have.
12. `test_gap_analysis_includes_practical_artifacts`: Phát hiện thiếu Portfolio, Capstone, Interview prep.
13. `test_roadmap_has_30_90_180_days_buckets`: Lộ trình đủ 3 mốc: 1 tháng, 3 tháng, 6 tháng.
14. `test_roadmap_tasks_contain_all_required_fields`: Task đủ 7 trường thông tin bắt buộc.
15. `test_roadmap_is_personalized_to_user_gaps`: Sinh viên khác nhau có roadmap khác nhau.
16. `test_career_transition_shared_and_missing_skills`: Phân tích chuẩn chuyển nghề từ A sang B.
17. `test_alternative_paths_contain_explanations`: Đề xuất con đường thay thế có giải thích rõ ràng.
18. `test_whatif_skill_upgrade_computes_delta`: Nâng skill tính lại đúng Delta Fit & Readiness và không làm hỏng hồ sơ gốc.
19. `test_whatif_constraint_adjustment_filters_or_reranks`: Đổi ràng buộc phản ánh đúng thay đổi xếp hạng.
20. `test_feedback_loop_updates_readiness_and_roadmap`: Cập nhật hoàn thành task làm tăng điểm Readiness.
21. `test_confidence_calculation_logic`: Độ tin cậy High/Med/Low phản ánh đúng mức độ hoàn thiện hồ sơ.
22. `test_grounded_offline_advisor_answers`: Fallback engine trả lời chuẩn xác 5 câu hỏi mà không cần LLM ngoài.

### Manual Verification
- Chạy toàn bộ test suite bằng `python -m pytest tests/test_career_advisor.py -v`.
- Kiểm tra toàn bộ luồng hiển thị 7 tabs của UI.
- Xác nhận các công thức và giải thích truy vết được về dữ liệu đầu vào.
