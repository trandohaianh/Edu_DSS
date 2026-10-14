# Student Navigation Inventory — Live, from current `dss/main.py` SIDEBAR_NAV_GROUPS["Sinh viên"]

Built directly from `dss/main.py:184-192` (not assumed) — 5 sidebar destinations, one with 2
prediction sub-tabs and one with 3 AI sub-tabs:

1. **🏡 Trang chủ** (Home) — group TỔNG QUAN
2. **🧪 Huấn luyện — Dự đoán** (rendered as "Dự đoán ML" in sidebar) — group HỌC TẬP & PHÂN TÍCH
   - Sub-tab: 👤 Dự đoán — Nhập tay (manual input form)
   - Sub-tab: 📁 Dự đoán — Từ file (misleading name — see FUNC-ML-002 below; no file uploader,
     shows prediction for the student's existing dataset row)
   - (Sinh viên does NOT get "🏋️ Huấn luyện mô hình" — confirmed at code level: `main.py` sets
     `tab_train_ml = None` for this role, and the entire training block is unreachable)
3. **🔬 Phân cụm — Gợi ý** (rendered as "Phân cụm" in sidebar) — group HỌC TẬP & PHÂN TÍCH
4. **🤖 Tư vấn — AI (LLM)** (rendered as "Trợ lý AI" in sidebar) — group TRỢ LÝ AI
   - Sub-tab: Kế hoạch học tập
   - Sub-tab: Hướng nghiệp
   - Sub-tab: Giải thích bài học
5. **📝 Lịch sử tư vấn** (rendered as "Lịch sử" in sidebar) — group TRỢ LÝ AI

This inventory is the walk order for the live acceptance pass below.
