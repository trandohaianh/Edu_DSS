"""PDF Certificate and Career Passport Generator Service — EduDSS.

Tạo báo cáo / bằng chứng nhận định hướng nghề nghiệp và lộ trình học tập AI
theo tiêu chuẩn mẫu chứng chỉ / Career Passport sang trọng:
- Viền kép hình học phong cách văn bằng (Double ornate certificate frame)
- Con dấu xác thực số EduDSS (Digital verification seal)
- Bảng định danh sinh viên & Mã kiểm chứng truy xuất
- Chỉ số Career Fit, Career Readiness & Bóc tách năng lực thực tế
- Kế hoạch can thiệp 4 tuần & Liều lượng học tập (Dosage)
- Khối chữ ký xác nhận của Cố vấn học tập & Hệ thống AI
"""
from __future__ import annotations

import io
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _ensure_fonts() -> tuple[str, str, str]:
    """Đăng ký font hỗ trợ tiếng Việt đầy đủ.

    Ưu tiên Arial từ Windows fonts, nếu không có sẽ dùng Helvetica mặc định.
    """
    regular_font = "Helvetica"
    bold_font = "Helvetica-Bold"
    italic_font = "Helvetica-Oblique"

    font_candidates = [
        ("Arial", "arial.ttf", "Arial-Bold", "arialbd.ttf", "Arial-Italic", "ariali.ttf"),
        ("SegoeUI", "segoeui.ttf", "SegoeUI-Bold", "segoeuib.ttf", "SegoeUI-Italic", "segoeuii.ttf"),
        ("Times", "times.ttf", "timesbd.ttf", "timesbd.ttf", "timesi.ttf", "timesi.ttf"),
    ]

    system_font_dirs = [
        "C:/Windows/Fonts",
        "C:/WINNT/Fonts",
        "/usr/share/fonts/truetype",
        "/usr/share/fonts/dejavu",
    ]

    for reg_name, reg_file, bld_name, bld_file, itl_name, itl_file in font_candidates:
        for fdir in system_font_dirs:
            reg_path = os.path.join(fdir, reg_file)
            bld_path = os.path.join(fdir, bld_file)
            itl_path = os.path.join(fdir, itl_file)
            if os.path.exists(reg_path) and os.path.exists(bld_path):
                try:
                    pdfmetrics.registerFont(TTFont(reg_name, reg_path))
                    pdfmetrics.registerFont(TTFont(bld_name, bld_path))
                    if os.path.exists(itl_path):
                        pdfmetrics.registerFont(TTFont(itl_name, itl_path))
                    return reg_name, bld_name, itl_name if os.path.exists(itl_path) else reg_name
                except Exception:
                    continue

    return regular_font, bold_font, italic_font


def _draw_certificate_frame(canvas, doc):
    """Vẽ viền đôi sang trọng và con dấu xác thực lên trang PDF."""
    canvas.saveState()
    width, height = doc.pagesize

    # 1. Viền kép phong cách chứng chỉ
    # Viền ngoài: Màu vàng đồng / Sapphire
    canvas.setStrokeColor(colors.HexColor("#1E3A8A"))
    canvas.setLineWidth(3.0)
    canvas.rect(20, 20, width - 40, height - 40)

    # Viền trong: Màu vàng kim hoàn
    canvas.setStrokeColor(colors.HexColor("#D97706"))
    canvas.setLineWidth(1.0)
    canvas.rect(26, 26, width - 52, height - 52)

    # 2. Họa tiết góc (Corner Ornaments)
    canvas.setStrokeColor(colors.HexColor("#B45309"))
    canvas.setFillColor(colors.HexColor("#D97706"))
    canvas.setLineWidth(1.5)
    for cx, cy in [
        (30, height - 30),
        (width - 30, height - 30),
        (30, 30),
        (width - 30, 30),
    ]:
        canvas.circle(cx, cy, 3, stroke=1, fill=1)

    # 3. Watermark mờ chính giữa
    canvas.setFont("Helvetica-Bold", 42)
    canvas.setFillColor(colors.HexColor("#F8FAFC"))
    canvas.saveState()
    canvas.translate(width / 2.0, height / 2.0)
    canvas.rotate(35)
    canvas.drawCentredString(0, 0, "EDUDSS OFFICIAL VERIFIED")
    canvas.restoreState()

    # 4. Con dấu điện tử EduDSS (Digital Verification Stamp) ở góc dưới phải
    stamp_x = width - 110
    stamp_y = 55
    canvas.setStrokeColor(colors.HexColor("#D97706"))
    canvas.setLineWidth(1.5)
    canvas.circle(stamp_x, stamp_y, 24, stroke=1, fill=0)
    canvas.setStrokeColor(colors.HexColor("#1E3A8A"))
    canvas.setLineWidth(0.8)
    canvas.circle(stamp_x, stamp_y, 20, stroke=1, fill=0)

    canvas.setFont("Helvetica-Bold", 5)
    canvas.setFillColor(colors.HexColor("#1E3A8A"))
    canvas.drawCentredString(stamp_x, stamp_y + 8, "★ EDUDSS ★")
    canvas.drawCentredString(stamp_x, stamp_y, "VERIFIED")
    canvas.drawCentredString(stamp_x, stamp_y - 8, "ACADEMIC")

    canvas.restoreState()


def generate_career_passport_pdf(
    student_id: str,
    target_role: str = "Chuyên viên Phân tích Dữ liệu / Data Analyst",
    career_fit_score: float = 85.0,
    career_readiness_score: float = 78.5,
    gap_size: str = "Nhỏ",
    student_name: Optional[str] = None,
    major: str = "Công nghệ Thông tin / Khoa học Dữ liệu",
    key_strengths: Optional[List[str]] = None,
    key_gaps: Optional[List[str]] = None,
    four_week_plan: Optional[List[Dict[str, Any]]] = None,
    dosage_hours: float = 6.5,
    dosage_exercises: int = 15,
    certificate_id: Optional[str] = None,
) -> bytes:
    """Tạo file PDF Bằng chứng nhận định hướng nghề nghiệp và lộ trình học tập."""
    reg_font, bold_font, italic_font = _ensure_fonts()

    cert_uuid = certificate_id or f"EDSS-{datetime.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
    issue_date = datetime.now().strftime("%d/%m/%Y")
    display_name = student_name or f"Sinh viên {student_id}"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=38,
        rightMargin=38,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    # Style definitions
    header_org = ParagraphStyle(
        "HeaderOrg",
        fontName=bold_font,
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#1E3A8A"),
        alignment=1,  # Center
    )
    header_sub = ParagraphStyle(
        "HeaderSub",
        fontName=reg_font,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#64748B"),
        alignment=1,
    )
    title_style = ParagraphStyle(
        "CertTitle",
        fontName=bold_font,
        fontSize=16,
        leading=21,
        textColor=colors.HexColor("#0F172A"),
        alignment=1,
    )
    title_sub_style = ParagraphStyle(
        "CertTitleSub",
        fontName=bold_font,
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#D97706"),
        alignment=1,
    )
    section_head = ParagraphStyle(
        "SectionHead",
        fontName=bold_font,
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=6,
        spaceAfter=3,
    )
    normal_text = ParagraphStyle(
        "NormalText",
        fontName=reg_font,
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1E293B"),
    )
    bold_text = ParagraphStyle(
        "BoldText",
        fontName=bold_font,
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#0F172A"),
    )
    caption_text = ParagraphStyle(
        "CaptionText",
        fontName=italic_font,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#64748B"),
    )

    elements = []

    # 1. Header Organization
    elements.append(Paragraph("HỆ THỐNG HỖ TRỢ RA QUYẾT ĐỊNH GIÁO DỤC — EDUDSS", header_org))
    elements.append(Paragraph("ACADEMIC DECISION SUPPORT SYSTEM · AI CAREER PASSPORT", header_sub))
    elements.append(Spacer(1, 8))

    # 2. Title Block
    elements.append(Paragraph("CHỨNG NHẬN ĐỊNH HƯỚNG NGHỀ NGHIỆP & LỘ TRÌNH HỌC TẬP AI", title_style))
    elements.append(Paragraph("AI CAREER PASSPORT & INTERVENTION CERTIFICATE", title_sub_style))
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="95%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=8))

    # 3. Student Identity Block
    id_data = [
        [
            Paragraph(f"<b>Mã sinh viên:</b> {student_id}", normal_text),
            Paragraph(f"<b>Họ và tên:</b> {display_name}", normal_text),
        ],
        [
            Paragraph(f"<b>Ngành / Khóa học:</b> {major}", normal_text),
            Paragraph(f"<b>Mã chứng nhận:</b> <code>{cert_uuid}</code>", normal_text),
        ],
        [
            Paragraph(f"<b>Ngày ban hành:</b> {issue_date}", normal_text),
            Paragraph(f"<b>Cơ chế đánh giá:</b> Heuristic & ML closed-loop (LMS)", normal_text),
        ],
    ]
    t_id = Table(id_data, colWidths=[260, 258])
    t_id.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#E2E8F0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#F1F5F9")),
            ("PADDING", (0, 0), (-1, -1), 4.5),
        ])
    )
    elements.append(t_id)
    elements.append(Spacer(1, 8))

    # 4. Career Target & Scores Block
    elements.append(Paragraph("I. ĐỊNH HƯỚNG NGHỀ NGHIỆP HÀNG ĐẦU (TOP TARGET ROLE)", section_head))

    score_data = [
        [
            Paragraph("<b>Vị trí nghề nghiệp đề xuất</b>", normal_text),
            Paragraph("<b>Career Fit</b>", normal_text),
            Paragraph("<b>Career Readiness</b>", normal_text),
            Paragraph("<b>Khoảng cách kỹ năng</b>", normal_text),
        ],
        [
            Paragraph(f"<b>{target_role}</b>", bold_text),
            Paragraph(f"<font color='#2563EB'><b>{career_fit_score:.1f}%</b></font>", bold_text),
            Paragraph(f"<font color='#0D9488'><b>{career_readiness_score:.1f}%</b></font>", bold_text),
            Paragraph(f"<b>{gap_size}</b>", normal_text),
        ],
    ]
    t_score = Table(score_data, colWidths=[230, 95, 95, 98])
    t_score.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFF6FF")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#BFDBFE")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DBEAFE")),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("PADDING", (0, 0), (-1, -1), 5),
        ])
    )
    elements.append(t_score)
    elements.append(Spacer(1, 6))

    # 5. Strengths & Evidences
    strengths_list = key_strengths or [
        "Năng lực lập trình và phân tích thuật toán vững chắc",
        "Tỷ lệ điểm danh và hoàn thành bài lab đạt trên 90%",
        "Tiến độ học tập và tư duy toán xác suất thống kê ổn định",
    ]
    str_lines = "".join(f"• {s}<br/>" for s in strengths_list[:3])
    elements.append(Paragraph(f"<b>Điểm mạnh & Bằng chứng thực tế từ LMS:</b><br/>{str_lines}", normal_text))
    elements.append(Spacer(1, 7))

    # 6. AI 4-Week Intervention Plan & Dosage
    elements.append(Paragraph("II. LỘ TRÌNH HỌC TẬP 4 TUẦN & LIỀU LƯỢNG CAN THIỆP AI", section_head))
    elements.append(
        Paragraph(
            f"<b>Liều lượng đề xuất:</b> Khoảng <b>{dosage_hours:.1f} giờ tự học tập trung/tuần</b> · "
            f"Tối thiểu <b>{dosage_exercises} bài tập củng cố/tuần</b>.",
            bold_text,
        )
    )
    elements.append(Spacer(1, 4))

    plan_rows = [
        [
            Paragraph("<b>Tuần</b>", normal_text),
            Paragraph("<b>Trọng tâm can thiệp & Chủ đề</b>", normal_text),
            Paragraph("<b>Nội dung hành động chi tiết</b>", normal_text),
        ]
    ]

    default_plans = [
        {"week": 1, "topic": "Lỗ hổng kiến thức nền tảng", "action": "Ôn tập lại các khái niệm cơ sở, hoàn thành các bài quiz chẩn đoán có điểm dưới trung bình."},
        {"week": 2, "topic": "Củng cố kỹ năng thực hành lab", "action": "Giải quyết các bài tập cấu trúc dữ liệu và xử lý mảng, code lại các thuật toán trọng yếu."},
        {"week": 3, "topic": "Nâng cao năng lực chuyên sâu", "action": "Thực hiện đồ án nhỏ theo nhóm, rèn luyện kỹ năng viết mã sạch và tối ưu thời gian chạy."},
        {"week": 4, "topic": "Kiểm chứng & Tổng duyệt", "action": "Làm bài thi thử nghiệm tổng hợp, đánh giá mức cải thiện GPA và sẵn sàng ứng tuyển."},
    ]
    active_plan = four_week_plan or default_plans

    for wp in active_plan[:4]:
        w_num = wp.get("week", 1)
        w_topic = wp.get("topic") or "Nội dung trọng tâm"
        w_act = wp.get("action") or "Thực hiện theo hướng dẫn bài giảng"
        plan_rows.append([
            Paragraph(f"<b>Tuần {w_num}</b>", bold_text),
            Paragraph(f"<b>{w_topic}</b>", normal_text),
            Paragraph(w_act[:120] + ("..." if len(w_act) > 120 else ""), normal_text),
        ])

    t_plan = Table(plan_rows, colWidths=[55, 160, 303])
    t_plan.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#CBD5E1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("PADDING", (0, 0), (-1, -1), 4),
        ])
    )
    elements.append(t_plan)
    elements.append(Spacer(1, 10))

    # 7. Signature & Verification Block
    sig_data = [
        [
            Paragraph("<b>CỐ VẤN HỌC TẬP (CVHT)</b><br/><i>(Ký và ghi rõ họ tên)</i>", normal_text),
            Paragraph("<b>TRỢ LÝ HỌC TẬP AI EDUDSS</b><br/><i>(Xác thực thuật toán & LMS)</i>", normal_text),
        ],
        [
            Paragraph("<br/><br/><b>TS. Nguyễn Văn A</b><br/><i>Khoa Công nghệ Thông tin</i>", normal_text),
            Paragraph(f"<br/><br/><b>EduDSS Algorithm Engine v2.4</b><br/><i>ID: {cert_uuid}</i>", normal_text),
        ],
    ]
    t_sig = Table(sig_data, colWidths=[259, 259])
    t_sig.setStyle(
        TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("PADDING", (0, 0), (-1, -1), 4),
        ])
    )
    elements.append(KeepTogether(t_sig))

    elements.append(Spacer(1, 8))
    elements.append(
        Paragraph(
            "<i>Văn bằng được sinh tự động từ Hệ thống EduDSS kết nối LMS/CMS. Xác thực bằng mã truy xuất điện tử tại cổng thông tin sinh viên.</i>",
            caption_text,
        )
    )

    doc.build(elements, onFirstPage=_draw_certificate_frame)
    return buffer.getvalue()
