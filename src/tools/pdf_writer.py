"""PDF 导出器：用 reportlab 把 Markdown 报告渲染成券商研报风格的 PDF。

纯 Python 实现，无外部系统依赖；中文字体用 Windows 系统自带的黑体 / 宋体。
Markdown 解析只覆盖报告正文常见元素：标题（# / ## / ###）、段落、无序列表、
表格、图表占位符（[[CHART:n]] / [[TABLE:n]]）、行内粗体 / 斜体 / 代码。
"""

import os
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONT_DIR = "C:/Windows/Fonts"
_HEAD_FONT = "SimHei"   # 黑体（标题）
_BODY_FONT = "SimSun"   # 宋体（正文）

_BRAND = colors.HexColor("#3A49C4")
_MUTED = colors.HexColor("#747C92")
_DANGER = colors.HexColor("#C84052")
_LINE = colors.HexColor("#D7DCE8")


def _register_fonts():
    try:
        if "SimHei" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("SimHei", os.path.join(_FONT_DIR, "simhei.ttf")))
        if "SimSun" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("SimSun", os.path.join(_FONT_DIR, "simsun.ttc"), subfontIndex=0))
    except Exception:
        # 字体注册失败时退回 reportlab 默认字体（中文会乱码，但保证不崩溃）
        pass


def _inline(text: str) -> str:
    """行内 markdown → reportlab Paragraph 支持的 HTML 子集。"""
    t = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', t)
    return t


def _styles():
    _register_fonts()
    return {
        "h1": ParagraphStyle("h1", fontName=_HEAD_FONT, fontSize=18, leading=26,
                              textColor=_BRAND, spaceBefore=14, spaceAfter=8),
        "h2": ParagraphStyle("h2", fontName=_HEAD_FONT, fontSize=14, leading=20,
                              textColor=colors.HexColor("#1F2430"), spaceBefore=12, spaceAfter=6),
        "h3": ParagraphStyle("h3", fontName=_HEAD_FONT, fontSize=12, leading=18,
                              textColor=colors.HexColor("#3A4153"), spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("body", fontName=_BODY_FONT, fontSize=10.5, leading=17,
                               textColor=colors.HexColor("#2A2F3D"), alignment=TA_LEFT, spaceAfter=6),
        "cover": ParagraphStyle("cover", fontName=_HEAD_FONT, fontSize=24, leading=34,
                                textColor=colors.HexColor("#1F2430"), alignment=TA_CENTER, spaceAfter=14),
        "cover_sub": ParagraphStyle("cover_sub", fontName=_BODY_FONT, fontSize=12, leading=18,
                                    textColor=_MUTED, alignment=TA_CENTER, spaceAfter=4),
        "abstract": ParagraphStyle("abstract", fontName=_BODY_FONT, fontSize=10.5, leading=17,
                                   textColor=colors.HexColor("#4A5060"), spaceAfter=6),
        "ref": ParagraphStyle("ref", fontName=_BODY_FONT, fontSize=9.5, leading=15,
                              textColor=colors.HexColor("#3A4153"), spaceAfter=3),
    }


def _parse_table_block(lines):
    """解析 markdown 表格块，返回 (table_data, 剩余行)。"""
    if not lines or not lines[0].strip().startswith("|"):
        return None, lines
    block = []
    i = 0
    while i < len(lines) and lines[i].strip().startswith("|"):
        block.append(lines[i].strip())
        i += 1
    rows = []
    for line in block:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    if len(rows) >= 2 and all(re.match(r"^:?-{2,}:?$", c) for c in rows[1]):
        # 跳过对齐分隔行
        rows.pop(1)
    return rows, lines[i:]


def _add_table(story, rows):
    st = _styles()
    if not rows:
        return
    ncol = max(len(r) for r in rows)
    norm = [r + [""] * (ncol - len(r)) for r in rows]
    data = [[_inline(c) for c in row] for row in norm]
    tbl = Table(data, colWidths=[(A4[0] - 4.4 * cm) / ncol] * ncol)
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), _HEAD_FONT),
        ("FONTNAME", (0, 1), (-1, -1), _BODY_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#2A2F3D")),
        ("BACKGROUND", (0, 0), (-1, 0), _BRAND),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6FB")]),
        ("GRID", (0, 0), (-1, -1), 0.5, _LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 10))


def _placeholder(text: str) -> str:
    """图表占位符 → 文本标注。"""
    def _chart(m):
        return f'<font color="#3A49C4">【图 {m.group(1)}】</font>'
    def _table(m):
        return f'<font color="#3A49C4">【表 {m.group(1)}】</font>'
    t = re.sub(r"\[\[CHART:(\d+)\]\]", _chart, text)
    t = re.sub(r"\[\[TABLE:(\d+)\]\]", _table, t)
    return t


def generate_pdf(ai_data: dict, out_path: str) -> str:
    """把报告数据渲染成 PDF，返回文件路径。"""
    _register_fonts()
    st = _styles()
    title = ai_data.get("report_title", "行业研究报告")
    publish_date = ai_data.get("publish_date", "")
    core = (ai_data.get("core_insights", "") or "").strip()
    md = ai_data.get("markdown_report", "") or ""
    references = ai_data.get("references", []) or []
    disclaimer = (ai_data.get("disclaimer") or "").strip()

    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2.4 * cm, bottomMargin=2.2 * cm,
        title=title, author="Eco-Research Copilot",
    )
    story = []

    # 封面
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph(title, st["cover"]))
    story.append(Spacer(1, 0.6 * cm))
    story.append(HRFlowable(width="32%", thickness=1.2, color=_BRAND, hAlign="CENTER"))
    story.append(Spacer(1, 0.6 * cm))
    if publish_date:
        story.append(Paragraph(f"发布日期：{publish_date}", st["cover_sub"]))
    story.append(Paragraph("研究引擎：Eco-Research Copilot", st["cover_sub"]))
    story.append(Spacer(1, 3 * cm))
    if disclaimer:
        story.append(Paragraph(_inline(f"免责声明：{disclaimer}"), st["cover_sub"]))
    story.append(Spacer(1, 0.6 * cm))

    # 摘要
    if core:
        story.append(Paragraph("摘要", st["h1"]))
        story.append(Paragraph(_inline(core), st["abstract"]))
        story.append(Spacer(1, 0.4 * cm))

    # 正文（逐行解析）
    lines = md.split("\n")
    i = 0
    para = []
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        # 表格块
        if stripped.startswith("|") and "|" in stripped[1:]:
            if para:
                story.append(Paragraph(_placeholder(_inline("<br/>".join(para))), st["body"]))
                para = []
            rows, remaining = _parse_table_block(lines[i:])
            if rows:
                _add_table(story, rows)
            i += len(lines[i:]) - len(remaining)
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            if para:
                story.append(Paragraph(_placeholder(_inline("<br/>".join(para))), st["body"]))
                para = []
            level = len(m.group(1))
            style = st["h1"] if level == 1 else st["h2"] if level == 2 else st["h3"]
            story.append(Paragraph(_placeholder(_inline(m.group(2))), style))
            i += 1
            continue

        # 无序列表
        m = re.match(r"^[-*]\s+(.*)$", stripped)
        if m:
            if para:
                story.append(Paragraph(_placeholder(_inline("<br/>".join(para))), st["body"]))
                para = []
            story.append(Paragraph(_placeholder(_inline("• " + m.group(1))), st["body"]))
            i += 1
            continue

        # 空行：段落结束
        if not stripped:
            if para:
                story.append(Paragraph(_placeholder(_inline("<br/>".join(para))), st["body"]))
                para = []
            i += 1
            continue

        # 普通段落
        para.append(stripped)
        i += 1

    if para:
        story.append(Paragraph(_placeholder(_inline("<br/>".join(para))), st["body"]))

    # 参考文献
    if references:
        story.append(Paragraph("参考文献", st["h1"]))
        for idx, r in enumerate(references, 1):
            title_r = r.get("title", "") if isinstance(r, dict) else str(r)
            url = r.get("url", "") if isinstance(r, dict) else ""
            line = f"[{idx}] {title_r}"
            if url:
                line += f'　<font color="#3A49C4">{url}</font>'
            story.append(Paragraph(_inline(line), st["ref"]))

    doc.build(story)
    return out_path
