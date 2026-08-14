"""行研图表确定性选择器。

与「让 LLM 自由选图表类型」相反，这里用确定性规则根据图表语义特征
（标题 / 图例 / 类别标签）推荐图表类型，用于纠正 LLM 的自由选择。

体现「确定性优先」：图表类型由数据语义决定，不赌模型发挥。
"""

import re

# 语义关键词 → 推荐图表类型（按优先级匹配）
_TYPE_RULES = [
    # 趋势 → 折线
    (("趋势", "走势", "增速", "增长", "演变", "变化", "逐年", "季度", "同比"), "line"),
    # 整体构成 → 饼图（"份额"不在此组，份额通常是对比，走柱状）
    (("占比", "结构", "构成", "比例"), "pie"),
    # 对比 / 排行 / 产业链 / 政策 → 柱状
    (("份额", "对比", "排行", "排名", "龙头", "厂商", "竞争", "格局", "企业",
      "产业链", "价值", "成本", "环节", "政策", "时间线", "里程碑"), "bar"),
]


def suggest_chart_type(chart: dict):
    """根据图表语义特征推荐图表类型。

    返回推荐类型（line/bar/pie/area）；返回 None 表示无法判断，保持原样。
    """
    if not isinstance(chart, dict):
        return None
    title = str(chart.get("title") or "") + " " + str(chart.get("label") or "")
    labels = chart.get("labels", []) or []

    # 1. 语义关键词匹配
    for keywords, typ in _TYPE_RULES:
        if any(k in title for k in keywords):
            # 占比结构但类别 > 5 → 饼图难读，改柱状
            if typ == "pie" and len(labels) > 5:
                return "bar"
            return typ

    # 2. 类别标签含时间特征 → 折线
    if _looks_temporal(labels):
        return "line"

    return None


def _looks_temporal(labels) -> bool:
    """判断类别标签是否像时间序列（年份 / 季度 / 月份）。"""
    return any(re.search(r"(19|20)\d{2}|Q[1-4]|季度|\d{1,2}月", str(l)) for l in labels)


def apply_chart_rules(charts: list) -> list:
    """对图表列表应用确定性规则：纠正 LLM 选的类型，返回修正后的列表。

    只做「纠偏」：规则能明确判断时才改，否则保持 LLM 原样。
    """
    if not charts:
        return charts
    for c in charts:
        if not isinstance(c, dict):
            continue
        suggested = suggest_chart_type(c)
        if suggested and suggested != c.get("type"):
            c["type"] = suggested
    return charts
