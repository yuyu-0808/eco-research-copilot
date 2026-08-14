"""确定性校验器：框架合规性 + 证据匹配度双重校验。

不依赖模型自评——用纯代码核对：
1. 每个必答问题（章节）是否匹配了足够数量的有效证据（丢弃 D 级后计数）；
2. 核心指标是否有满足最低信源等级（S/A/B）的证据支撑；
3. 同一章节内的数值矛盾自动标红（保留人工判断入口）。

校验结果只由代码给出，模型输出无法改写结论。
"""

from .evidence import EvidenceRecord, TIER_LABEL
from .source_grade import source_grade
from .normalizer import normalize_value

_TIER_RANK = {"S": 4, "A": 3, "B": 2, "D": 1, "": 0}


def _tier_ok(tier: str, min_tier: str) -> bool:
    if not min_tier:
        return True
    return _TIER_RANK.get(tier, 0) >= _TIER_RANK.get(min_tier, 0)


def _check_value_spec(evidence: list, spec: dict) -> list:
    """检查证据数值是否越界（契约规定的合理区间）。

    只校验「比例型」数值（百分比/成数/分数），避免误伤「3000 亿元」这类非比例数值。
    返回越界问题列表（空 = 全部合规）。
    """
    if not spec:
        return []
    ratio_range = spec.get("ratio_range")
    issues = []
    for e in evidence:
        if not e.value:
            continue
        nv = normalize_value(e.value)
        if nv is None or not nv.is_ratio:
            continue  # 非比例型数值不校验区间
        pct = nv.value * 100
        if ratio_range and not (ratio_range[0] <= pct <= ratio_range[1]):
            issues.append(
                f"「{e.claim}」数值 {e.value}（{pct:.1f}%）超出合理区间 "
                f"{ratio_range[0]}~{ratio_range[1]}"
            )
    return issues


def validate(plan_data: dict, evidence: list) -> dict:
    """对证据列表做确定性校验。

    返回：
        is_pass:   是否全部必答问题都达标
        reasons:   未达标原因列表（空 = 通过）
        coverage:  每个 question_id 的有效证据条数
        conflicts: 检测到的数值矛盾（同 section 同 claim 不同 value）
    """
    requirements = plan_data.get("research_requirements", []) or []
    evidence = [e for e in (evidence or []) if isinstance(e, EvidenceRecord)]

    coverage = {}
    reasons = []
    tier_gaps = []

    for req in requirements:
        qid = req.get("question_id", "")
        section = req.get("section", "")
        min_ev = int(req.get("min_evidence", 1) or 1)
        min_tier = req.get("min_tier") or ""

        # 归属该问题的有效证据（丢弃 D 级）
        matched = [
            e for e in evidence
            if (e.question_id == qid or (section and e.section == section))
            and e.source_tier != "D"
        ]
        coverage[qid] = len(matched)

        if len(matched) < min_ev:
            reasons.append(f"「{req.get('text', section or qid)}」证据不足：{len(matched)}/{min_ev} 条")
            continue

        # 核心指标信源等级门槛
        if min_tier:
            high_tier = [e for e in matched if _tier_ok(e.source_tier, min_tier)]
            if not high_tier:
                tier_gaps.append(
                    f"「{req.get('text', section or qid)}」缺少 {min_tier} 级（{TIER_LABEL.get(min_tier, '')}）信源支撑"
                )

        # 数值口径契约校验（越界拦截：比例型指标超出合理区间）
        spec = req.get("value_spec")
        if spec:
            spec_issues = _check_value_spec(matched, spec)
            if spec_issues:
                reasons.append(
                    f"「{req.get('text', section or qid)}」{len(spec_issues)} 项数值越界："
                    + spec_issues[0] + (" 等" if len(spec_issues) > 1 else "")
                )

    # 数值矛盾检测：同 section 同 claim 出现不同 value → 标红
    conflicts = _detect_conflicts(evidence)

    is_pass = (not reasons) and (not tier_gaps)
    reasons.extend(tier_gaps)

    return {
        "is_pass": is_pass,
        "reasons": reasons,
        "coverage": coverage,
        "conflicts": conflicts,
    }


def _detect_conflicts(evidence: list) -> list:
    """同 section + 同 claim 归一化后 value 不一致，判定为矛盾。"""
    groups = {}
    for e in evidence:
        if not e.value or not e.claim:
            continue
        key = (e.section, e.claim.strip())
        groups.setdefault(key, []).append(e)

    conflicts = []
    for (section, claim), items in groups.items():
        # 归一化后比对：语义相等（如"30%"vs"0.3"、"3万辆"vs"30000辆"）不算矛盾
        normalized = {}
        for e in items:
            nv = normalize_value(e.value)
            if nv is not None:
                normalized.setdefault(nv.key(), e.value)
        if len(normalized) > 1:
            conflicts.append({
                "section": section,
                "claim": claim,
                "values": sorted({e.value for e in items}),
                "normalized": sorted(
                    f"{k[0]}{(' ' + k[1]) if k[1] else ''}" for k in normalized.keys()
                ),
                "sources": [
                    {"title": e.source_title, "url": e.source_url, "tier": e.source_tier}
                    for e in items
                ],
            })
    return conflicts


def infer_publisher(url: str) -> str:
    """从域名推断发布机构（粗粒度，供证据展示用）。"""
    if not url:
        return ""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc or url
        host = host.lower().replace("www.", "")
        return host.split(".")[0]
    except Exception:
        return ""
