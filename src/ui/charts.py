"""图表与表格渲染层：把 ai_data 的图表/表格转成 Vega-Lite spec / HTML，并切分报告正文。

Vega-Lite 由 Streamlit 内置渲染（st.vega_lite_chart），无需额外依赖。
"""
import re

BRAND = "#4A54D6"
PALETTE = ["#4A54D6", "#22A06B", "#E09A2B", "#D6455A", "#5B8DEF", "#7C5BE0", "#3FB6C9", "#C778C9"]
FONT = "Plus Jakarta Sans, PingFang SC, Microsoft YaHei, sans-serif"

_PLACEHOLDER = re.compile(r"\[\[(CHART|TABLE):(\d+)\]\]")


def _rows(labels, data):
    rows = []
    for i, v in enumerate(data):
        lab = labels[i] if i < len(labels) else str(i + 1)
        rows.append({"label": str(lab), "value": v})
    return rows


def chart_to_spec(chart):
    """把 ai_data 里的图表 dict 转成 Vega-Lite spec（line/bar/pie/area）。"""
    if not isinstance(chart, dict):
        return None
    ctype = (chart.get("type") or "line").lower()
    if ctype not in ("line", "bar", "pie", "area"):
        ctype = "line"
    labels = chart.get("labels", []) or []
    data = chart.get("data", []) or []
    if not data:
        return None

    rows = _rows(labels, data)
    base = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "width": "container",
        "height": 260,
        "data": {"values": rows},
        "config": {
            "font": FONT,
            "axis": {
                "labelColor": "#747C92",
                "titleColor": "#747C92",
                "gridColor": "#ECEFF6",
                "tickColor": "#ECEFF6",
                "labelFontSize": 12,
                "domainColor": "#D7DCE8",
            },
            "view": {"stroke": "transparent"},
        },
    }

    if ctype == "pie":
        return {
            **base,
            "mark": {"type": "arc", "innerRadius": 48, "outerRadius": 100},
            "encoding": {
                "theta": {"field": "value", "type": "quantitative"},
                "color": {
                    "field": "label",
                    "type": "nominal",
                    "scale": {"range": PALETTE},
                    "legend": {"title": None, "orient": "right", "labelFontSize": 12},
                },
                "tooltip": [
                    {"field": "label", "type": "nominal"},
                    {"field": "value", "type": "quantitative"},
                ],
            },
        }

    if ctype == "bar":
        mark = {"type": "bar", "color": BRAND, "cornerRadiusEnd": 6}
    elif ctype == "area":
        mark = {"type": "area", "color": BRAND, "opacity": 0.25, "line": {"color": BRAND, "strokeWidth": 2.5}, "interpolate": "monotone"}
    else:
        mark = {"type": "line", "color": BRAND, "strokeWidth": 2.5, "point": True, "interpolate": "monotone"}

    return {
        **base,
        "mark": mark,
        "encoding": {
            "x": {"field": "label", "type": "nominal", "axis": {"labelAngle": 0, "title": None}},
            "y": {"field": "value", "type": "quantitative", "axis": {"title": None}},
            "tooltip": [
                {"field": "label", "type": "nominal"},
                {"field": "value", "type": "quantitative"},
            ],
        },
    }


def table_to_html(table):
    """把 ai_data 里的表格 dict 转成带样式的 HTML 表格。"""
    if not isinstance(table, dict):
        return ""
    headers = table.get("headers", []) or []
    rows = table.get("rows", []) or []
    if not headers and not rows:
        return ""

    parts = ['<table class="report-table">']
    if headers:
        parts.append(
            "<thead><tr>"
            + "".join(f"<th>{html_escape_here(h)}</th>" for h in headers)
            + "</tr></thead>"
        )
    parts.append("<tbody>")
    for r in rows:
        parts.append(
            "<tr>" + "".join(f"<td>{html_escape_here(c)}</td>" for c in r) + "</tr>"
        )
    parts.append("</tbody></table>")
    return "".join(parts)


def html_escape_here(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def split_report(md):
    """把报告 markdown 正文按 [[CHART:n]] / [[TABLE:n]] 占位符切成 (kind, text, index) 序列。

    kind: "text" / "CHART" / "TABLE"
    """
    if not md:
        return [("text", "", None)]
    parts = []
    pos = 0
    for m in _PLACEHOLDER.finditer(md):
        if m.start() > pos:
            parts.append(("text", md[pos:m.start()], None))
        parts.append((m.group(1), "", int(m.group(2))))
        pos = m.end()
    if pos < len(md):
        parts.append(("text", md[pos:], None))
    return parts


def extract_headings(md):
    """提取二级标题列表，用于报告目录导航。"""
    if not md:
        return []
    return re.findall(r"^##\s+(.+)$", md, re.M)
