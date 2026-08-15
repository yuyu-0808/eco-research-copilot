"""投研专属证据校验规则。

在通用校验（证据数 + 信源等级 + 矛盾检测 + 口径契约）之上，新增四类
投研场景专属规则，命中「数据要准、要符合行业常识」的核心诉求：

1. 财务勾稽校验：净利 ≈ 营收 × 净利率、毛利 = 营收 - 营业成本、毛利率 = 毛利 / 营收；
2. 行业区间校验：分行业分指标的常识区间（毛利率 / 净利率 / 增速 / 渗透率等）越界预警；
3. 时间序列校验：同一指标相邻年份数值跳变超阈值且无说明，标记待核实；
4. 多源偏差校验：同一指标多信源数值偏差超阈值，标红并列出全部来源供用户采信。

这四类规则输出「预警 / 待核实」级别的问题，不替代硬性拦截（证据不足仍由
validator 判失败），而是作为第二道「投研逻辑」关卡，供用户决策采信。
"""

from typing import List, Optional

from .normalizer import normalize_value, normalize_period

# ----------------------------------------------------------------------
# 指标分类器：把「事实主张」文本映射到规范指标类型
# ----------------------------------------------------------------------
# 顺序敏感：越具体、越该优先的放前面（如「净利率」须先于「净利润」匹配，
# 「毛利率」须先于「毛利」匹配，避免把利润率误判成利润额）。
_METRICS = [
    ("gross_margin", "毛利率", ["毛利率"]),
    ("net_margin", "净利率", ["净利率", "净利润率", "利润率"]),
    ("net_profit", "净利润", ["归母净利润", "归母净利", "净利润", "净利"]),
    ("gross_profit", "毛利", ["毛利润", "毛利"]),
    ("operating_cost", "营业成本", ["营业总成本", "营业成本"]),
    ("revenue", "营业收入", ["营业总收入", "营业收入", "营收", "销售收入"]),
    ("market_size", "市场规模", ["市场规模", "行业规模", "市场空间", "行业空间", "产值"]),
    ("penetration", "渗透率", ["渗透率"]),
    ("market_share", "市场份额", ["市占率", "市场份额", "占有率", "集中度", "cr5", "cr10", "cr3"]),
    ("growth_rate", "增速", ["同比增速", "同比增长", "复合增速", "增速", "增长率", "yoy", "cagr"]),
    ("shipments", "出货量", ["出货量", "销量"]),
    ("capacity", "产能", ["产能", "产量", "装机容量", "装机量"]),
    ("price", "价格", ["均价", "单价", "售价", "价格"]),
]

_METRIC_LABEL = {key: label for key, label, _ in _METRICS}


def classify_metric(text: str) -> Optional[str]:
    """把事实主张文本归类为规范指标类型；无法归类返回 None。"""
    t = (text or "").lower()
    for key, _label, keywords in _METRICS:
        if any(k in t for k in keywords):
            return key
    return None


def metric_label(metric: str) -> str:
    return _METRIC_LABEL.get(metric, metric or "未知指标")


# ----------------------------------------------------------------------
# 行业常识区间（比例型指标，单位 %）
# ----------------------------------------------------------------------
# 与 validator 的 value_spec（0-100% 物理区间，硬拦截）不同：这里给出的是
# 「行业常识区间」，越界只预警、不拦截——用于抓「毛利率 250%」「渗透率 120%」
# 这类明显违背行业常识的数值。
DEFAULT_METRIC_RANGES = {
    "gross_margin": (-20, 100),
    "net_margin": (-100, 100),
    "growth_rate": (-100, 300),
    "penetration": (0, 100),
    "market_share": (0, 100),
}

# 分行业覆盖（键 = framework key），可配置、可扩展；未覆盖的指标回落到默认区间。
INDUSTRY_METRIC_RANGES = {
    "new_energy": {
        "growth_rate": (-100, 200),
    },
    "tmt": {
        "growth_rate": (-100, 150),
    },
    "consumer": {
        "growth_rate": (-50, 100),
    },
}

# 默认多源偏差阈值（相对偏差），越界标红
DEFAULT_DEVIATION_THRESHOLD = 0.20
# 默认时间序列跳变阈值（同比），越界标记待核实
DEFAULT_JUMP_THRESHOLD = 0.50
# 财务勾稽默认容差（相对偏差）
DEFAULT_RECON_TOLERANCE = 0.20

# 时间序列「有说明」关键词：命中则不判异常（数据跳变有合理解释）
_EXPLAIN_WORDS = [
    "大幅", "暴增", "激增", "骤降", "翻倍", "腰斩", "疫情", "补贴", "退坡",
    "政策", "基数", "低基数", "高基数", "并购", "并表", "复产", "涨价",
    "原材料", "产能释放", "一次性", "重组", "剥离", "计提", "减值", "周期",
]


def _has_explanation(record) -> bool:
    """判断跳变证据是否自带解释（claim / excerpt 命中说明词）。"""
    text = f"{getattr(record, 'claim', '')} {getattr(record, 'excerpt', '')}"
    return any(w in text for w in _EXPLAIN_WORDS)


# ----------------------------------------------------------------------
# 内部工具
# ----------------------------------------------------------------------

def _group_by_scope(evidence: list) -> dict:
    """按 (section, 年份) 分组，用于财务勾稽的同口径比对。"""
    groups = {}
    for e in evidence:
        if not getattr(e, "claim", "") or not getattr(e, "value", ""):
            continue
        p = normalize_period(getattr(e, "period", ""))
        year = p.year if p else 0
        groups.setdefault((getattr(e, "section", ""), year), []).append(e)
    return groups


def _metric_map(items: list) -> dict:
    """把一组证据映射为 metric -> 代表性证据（取信源等级最高者）。"""
    out = {}
    for e in items:
        metric = classify_metric(getattr(e, "claim", ""))
        if not metric or not getattr(e, "value", ""):
            continue
        if metric not in out:
            out[metric] = e
            continue
        # 信源等级更高者优先（tier_rank 越大越可信）
        cur_rank = getattr(e, "tier_rank", 0) or 0
        old_rank = getattr(out[metric], "tier_rank", 0) or 0
        if cur_rank > old_rank:
            out[metric] = e
    return out


def _metric_value(record) -> Optional[float]:
    """取证据数值的归一化浮点值（比例型返回 0-1 小数，金额型返回基准值）。"""
    nv = normalize_value(getattr(record, "value", ""))
    return nv.value if nv else None


def _deviation(a: float, b: float) -> float:
    """相对偏差：|a-b| / max(|a|, 1e-9)。"""
    return abs(a - b) / max(abs(a), 1e-9)


def _issue(rule: str, level: str, message: str, detail: dict = None) -> dict:
    return {
        "rule": rule,
        "level": level,
        "message": message,
        "detail": detail or {},
    }


# ----------------------------------------------------------------------
# 规则 1：财务勾稽校验
# ----------------------------------------------------------------------

def check_financial_reconciliation(evidence: list, tolerance: float = DEFAULT_RECON_TOLERANCE) -> list:
    """校验基础财务勾稽关系，返回不成立的勾稽问题列表。

    同 (section, 年份) 口径内做交叉验证：
    - 净利 ≈ 营收 × 净利率
    - 毛利 = 营收 - 营业成本
    - 毛利率 = 毛利 / 营收
    """
    issues = []
    for (section, year), items in _group_by_scope(evidence).items():
        m = _metric_map(items)
        revenue = _metric_value(m["revenue"]) if "revenue" in m else None
        net_margin = _metric_value(m["net_margin"]) if "net_margin" in m else None
        net_profit = _metric_value(m["net_profit"]) if "net_profit" in m else None
        gross_profit = _metric_value(m["gross_profit"]) if "gross_profit" in m else None
        operating_cost = _metric_value(m["operating_cost"]) if "operating_cost" in m else None
        gross_margin = _metric_value(m["gross_margin"]) if "gross_margin" in m else None

        scope = f"{section} {year}年" if year else (section or "全篇")

        # 净利 ≈ 营收 × 净利率
        if revenue is not None and net_margin is not None and net_profit is not None and revenue != 0:
            expected = revenue * net_margin
            if _deviation(net_profit, expected) > tolerance:
                issues.append(_issue(
                    "financial_reconciliation", "warning",
                    f"「净利 ≈ 营收 × 净利率」不成立：{scope}营收 {revenue:g} × 净利率 {net_margin*100:.1f}% ≈ {expected:g}，但净利润记录为 {net_profit:g}，偏差 {_deviation(net_profit, expected)*100:.0f}%",
                    {"section": section, "year": year, "expected": expected, "actual": net_profit},
                ))

        # 毛利 = 营收 - 营业成本
        if revenue is not None and operating_cost is not None and gross_profit is not None:
            expected_gross = revenue - operating_cost
            if expected_gross > 0 and _deviation(gross_profit, expected_gross) > tolerance:
                issues.append(_issue(
                    "financial_reconciliation", "warning",
                    f"「毛利 = 营收 - 营业成本」不成立：{scope}营收 {revenue:g} - 营业成本 {operating_cost:g} = {expected_gross:g}，但毛利记录为 {gross_profit:g}，偏差 {_deviation(gross_profit, expected_gross)*100:.0f}%",
                    {"section": section, "year": year, "expected": expected_gross, "actual": gross_profit},
                ))

        # 毛利率 = 毛利 / 营收
        if revenue is not None and gross_profit is not None and gross_margin is not None and revenue != 0:
            expected_margin = gross_profit / revenue
            if _deviation(gross_margin, expected_margin) > tolerance:
                issues.append(_issue(
                    "financial_reconciliation", "warning",
                    f"「毛利率 = 毛利 / 营收」不成立：{scope}毛利 {gross_profit:g} / 营收 {revenue:g} = {expected_margin*100:.1f}%，但毛利率记录为 {gross_margin*100:.1f}%，偏差 {_deviation(gross_margin, expected_margin)*100:.0f}%",
                    {"section": section, "year": year, "expected": expected_margin, "actual": gross_margin},
                ))

    return issues


# ----------------------------------------------------------------------
# 规则 2：行业区间校验
# ----------------------------------------------------------------------

def check_industry_range(evidence: list, framework_key: str = "") -> list:
    """校验数值是否落在「行业常识区间」内，越界仅预警、不拦截。"""
    issues = []
    overrides = INDUSTRY_METRIC_RANGES.get(framework_key, {})
    for e in evidence:
        metric = classify_metric(getattr(e, "claim", ""))
        if not metric or not getattr(e, "value", ""):
            continue
        nv = normalize_value(getattr(e, "value", ""))
        if nv is None or not nv.is_ratio:
            continue  # 只对比例型指标做常识区间校验
        pct = nv.value * 100
        rng = overrides.get(metric) or DEFAULT_METRIC_RANGES.get(metric)
        if rng and not (rng[0] <= pct <= rng[1]):
            issues.append(_issue(
                "industry_range", "warning",
                f"「{metric_label(metric)}」数值 {pct:.1f}% 超出行业常识区间 {rng[0]}~{rng[1]}%（{getattr(e, 'claim', '')[:40]}）",
                {"metric": metric, "value": pct, "range": rng},
            ))
    return issues


# ----------------------------------------------------------------------
# 规则 3：时间序列校验
# ----------------------------------------------------------------------

def check_time_series(evidence: list, threshold: float = DEFAULT_JUMP_THRESHOLD) -> list:
    """同一指标相邻年份跳变超阈值且无说明 → 标记待核实。"""
    groups = {}
    for e in evidence:
        metric = classify_metric(getattr(e, "claim", ""))
        if not metric or not getattr(e, "value", ""):
            continue
        nv = normalize_value(getattr(e, "value", ""))
        if nv is None or nv.is_ratio:
            continue  # 比例型（增速/渗透率等）本身是跨期值，不做跨年跳变比对
        p = normalize_period(getattr(e, "period", ""))
        if p is None:
            continue
        groups.setdefault((getattr(e, "section", ""), metric), []).append((p.year, nv.value, e))

    issues = []
    for (section, metric), items in groups.items():
        items.sort(key=lambda x: x[0])
        # 同年多值取平均，避免重复计数
        merged = {}
        for year, val, e in items:
            merged.setdefault(year, []).append((val, e))
        series = [(y, sum(v for v, _ in vs) / len(vs), vs[0][1]) for y, vs in sorted(merged.items())]

        for (y1, v1, _), (y2, v2, e2) in zip(series, series[1:]):
            if y2 <= y1 or v1 == 0:
                continue
            change = (v2 - v1) / abs(v1)
            if abs(change) > threshold and not _has_explanation(e2):
                issues.append(_issue(
                    "time_series", "verify",
                    f"「{metric_label(metric)}」{y1}年 {v1:g} → {y2}年 {v2:g}，跳变 {change*100:+.0f}%，无说明，待核实",
                    {"section": section, "metric": metric, "from": {"year": y1, "value": v1}, "to": {"year": y2, "value": v2}},
                ))
    return issues


# ----------------------------------------------------------------------
# 规则 4：多源偏差校验
# ----------------------------------------------------------------------

def check_multi_source_deviation(evidence: list, threshold: float = DEFAULT_DEVIATION_THRESHOLD) -> list:
    """同一指标（同 section + 同年）多信源数值偏差超阈值 → 标红并列出全部来源。"""
    groups = {}
    for e in evidence:
        metric = classify_metric(getattr(e, "claim", ""))
        if not metric or not getattr(e, "value", ""):
            continue
        nv = normalize_value(getattr(e, "value", ""))
        if nv is None:
            continue
        p = normalize_period(getattr(e, "period", ""))
        year = p.year if p else 0
        # 比例型用百分比口径、金额型用归一化基准值口径
        base = nv.value * 100 if nv.is_ratio else nv.value
        groups.setdefault((getattr(e, "section", ""), metric, year), []).append((base, e))

    issues = []
    for (section, metric, year), items in groups.items():
        # 去重：同源同值只保留一条，避免同一信源反复出现被误判为「多源」
        dedup = {}
        for base, e in items:
            key = (e.source_url or e.source_title or "", round(base, 4))
            dedup.setdefault(key, (base, e))
        vals = list(dedup.values())
        if len(vals) < 2:
            continue
        lo = min(vals, key=lambda x: x[0])
        hi = max(vals, key=lambda x: x[0])
        if lo[0] == 0:
            continue
        dev = (hi[0] - lo[0]) / abs(lo[0])
        if dev > threshold:
            scope = f"{section} {year}年" if year else (section or "全篇")
            sources = [
                {"title": e.source_title, "url": e.source_url, "tier": e.source_tier, "value": e.value}
                for _, e in sorted(vals, key=lambda x: x[0])
            ]
            issues.append(_issue(
                "multi_source_deviation", "warning",
                f"「{metric_label(metric)}」{scope}多源数值偏差 {dev*100:.0f}%（{lo[0]:g} ~ {hi[0]:g}），已列出全部来源供确认采信",
                {"section": section, "metric": metric, "year": year, "min": lo[0], "max": hi[0], "sources": sources},
            ))
    return issues


# ----------------------------------------------------------------------
# 汇总入口
# ----------------------------------------------------------------------

def run_investment_checks(evidence: list, framework_key: str = "") -> dict:
    """运行全部投研专属校验，返回分规则结果 + 扁平化的 warnings 列表。"""
    evidence = [e for e in (evidence or []) if getattr(e, "claim", "") and getattr(e, "value", "")]
    financial = check_financial_reconciliation(evidence)
    industry = check_industry_range(evidence, framework_key)
    timeseries = check_time_series(evidence)
    multisource = check_multi_source_deviation(evidence)

    warnings = financial + industry + timeseries + multisource
    return {
        "financial_reconciliation": financial,
        "industry_range": industry,
        "time_series": timeseries,
        "multi_source_deviation": multisource,
        "warnings": warnings,
    }
