"""Nạp 3 bài giảng mẫu (app/demo/cms_lectures/*.md) vào CMS để demo tính năng
"Giải thích bài giảng" — dòng lệnh tương đương nút "Nạp bài giảng mẫu" trong
tab Trợ lý AI > Giải thích bài giảng của Giảng viên (dss/services/demo_lectures.py).

    cd app
    python tools/seed_demo_lectures.py            # nạp vào kho dữ liệu đang dùng
    python tools/seed_demo_lectures.py --ask      # nạp + hỏi thử AI 1 câu
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dss.config  # noqa: E402,F401  (nạp app/.env)
from dss.core.models import MultiAIProvider  # noqa: E402
from dss.services import cms_lecture_repository as cms  # noqa: E402
from dss.services import demo_lectures  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask", action="store_true", help="hỏi thử AI 1 câu sau khi nạp")
    args = ap.parse_args()
    logging.disable(logging.WARNING)
    llm = MultiAIProvider()
    for lesson_id, new in demo_lectures.seed(llm):
        print(("+ đã nạp " if new else "= đã có, bỏ qua ") + lesson_id)
    if args.ask:
        from dss.services import learning_explainer as le

        lesson = cms.get_lesson("CS301-L03")
        r = le.generate_explanation(
            llm,
            "Vì sao không nên chỉ dùng Accuracy khi lớp Yếu rất ít sinh viên?",
            demo_lectures.COURSE_ID,
            lesson.lesson_id,
            lesson.topic_id,
            "Standard",
            socratic_mode=False,
            mode=le.CMS_ONLY,
            user_id="demo",
        )
        print(
            "\n--- AI trả lời (có nội dung CMS: %s) ---\n%s\n--- nguồn: %s"
            % (r.has_cms_content, r.answer, sorted({c.label for c in r.citations}))
        )


if __name__ == "__main__":
    main()
