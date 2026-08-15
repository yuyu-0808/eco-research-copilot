"""行业指标知识库：数据飞轮。

每次报告生成后，把通过校验的核心指标沉淀到对应行业的指标库（JSON 文件），
新建同行业报告时用历史指标交叉验证，冲突优先提示历史高等级信源数值。
指标库支持按行业 / 指标 / 时间检索，并可导出 Excel。

存储：data/metrics_library/{framework_key}.json（每行业一个文件，透明可检视）。
"""

import json
import os
from datetime import datetime

from .normalizer import normalize_value, normalize_period
from .investment_checks import classify_metric, metric_label

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
METRICS_DIR = os.path.join(_ROOT, "data", "metrics_library")

_TIER_RANK = {"A": 6, "B": 5, "C": 4, "D": 3, "E": 2, "F": 1, "": 0}


def _path(framework_key: str) -> str:
    return os.path.join(METRICS_DIR, f"{framework_key}.json")


def _field(e, name, default=""):
    """兼容 EvidenceRecord（dataclass）与 dict 两种形态的字段读取。"""
    if isinstance(e, dict):
        return e.get(name, default)
    return getattr(e, name, default)


def extract_metrics(evidence, framework_key: str = "") -> list:
    """从证据列表提取核心指标条目（指标名 + 归一化数值 + 时间 + 来源 + 等级）。

    只提取「有指标归类 + 可归一化数值」的证据；比例型与非比例型均记录。
    """
    entries = []
    for e in evidence or []:
        claim = _field(e, "claim", "")
        value = _field(e, "value", "")
        metric = classify_metric(claim)
        if not metric or not value:
            continue
        nv = normalize_value(value)
        if nv is None:
            continue
        period = _field(e, "period", "")
        p = normalize_period(period)
        entries.append({
            "metric": metric,
            "metric_label": metric_label(metric),
            "value": value,
            "value_norm": nv.value,
            "unit": _field(e, "unit", "") or nv.unit,
            "period": period,
            "year": p.year if p else None,
            "source_title": _field(e, "source_title", ""),
            "source_url": _field(e, "source_url", ""),
            "source_tier": _field(e, "source_tier", "D"),
            "publisher": _field(e, "publisher", ""),
        })
    return entries


def load_metrics(framework_key: str) -> list:
    """读取某行业的全部历史指标。"""
    path = _path(framework_key)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_metrics(framework_key: str, entries: list, report_id: str = "") -> int:
    """把指标条目追加到行业指标库（按 指标+年份+归一化值 去重）。

    通用框架（generic）不沉淀（无行业口径）。返回新增条数。
    """
    if not framework_key or framework_key == "generic" or not entries:
        return 0
    existing = load_metrics(framework_key)
    seen = {
        (m.get("metric"), m.get("year"), round(m.get("value_norm", 0) or 0, 4))
        for m in existing
    }
    added = 0
    for en in entries:
        key = (en.get("metric"), en.get("year"), round(en.get("value_norm", 0) or 0, 4))
        if key in seen:
            continue
        seen.add(key)
        en["report_id"] = report_id
        en["saved_at"] = datetime.now().isoformat(timespec="seconds")
        existing.append(en)
        added += 1
    if added:
        os.makedirs(METRICS_DIR, exist_ok=True)
        with open(_path(framework_key), "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    return added


def _all_keys() -> list:
    if not os.path.isdir(METRICS_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(METRICS_DIR) if f.endswith(".json"))


def query_metrics(framework_key: str = None, metric: str = None, period: str = None) -> list:
    """检索指标库（可按行业 / 指标 / 时间过滤）。"""
    keys = [framework_key] if framework_key else _all_keys()
    result = []
    for k in keys:
        for m in load_metrics(k):
            if metric and m.get("metric") != metric:
                continue
            if period and period not in (m.get("period") or ""):
                continue
            row = dict(m)
            row["framework_key"] = k
            result.append(row)
    return result


def cross_validate(framework_key: str, evidence: list, threshold: float = 0.2) -> list:
    """用历史指标库交叉验证当前证据，返回冲突提示列表。

    同指标同年份：历史最高等级信源值 vs 当前值，相对偏差超阈值 → 冲突，
    优先提示历史高等级信源数值。
    """
    historical = load_metrics(framework_key)
    if not historical:
        return []
    new_entries = extract_metrics(evidence, framework_key)
    issues = []
    for new in new_entries:
        cand = [
            h for h in historical
            if h.get("metric") == new["metric"] and h.get("year") == new.get("year")
        ]
        if not cand:
            continue
        best = max(cand, key=lambda h: _TIER_RANK.get(h.get("source_tier", ""), 0))
        base = best.get("value_norm")
        cur = new.get("value_norm")
        if base is None or cur is None or base == 0:
            continue
        dev = abs(cur - base) / abs(base)
        if dev > threshold:
            src = best.get("source_title") or best.get("publisher") or "历史记录"
            issues.append({
                "rule": "historical_cross",
                "level": "verify",
                "message": (
                    f"「{new['metric_label']}」{new.get('year')}年 当前值 {new['value']} 与历史值 "
                    f"{best.get('value')}（{best.get('source_tier')}级·{src}）偏差 {dev * 100:.0f}%，待核实"
                ),
                "detail": {"metric": new["metric"], "historical": best, "current": new},
            })
    return issues


def export_excel(framework_key: str = None, out_path: str = None) -> str:
    """把指标库导出为 Excel（.xlsx），返回文件路径。"""
    from openpyxl import Workbook

    rows = query_metrics(framework_key)
    wb = Workbook()
    ws = wb.active
    ws.title = "指标库"
    headers = ["行业", "指标", "指标名", "数值", "归一化值", "单位", "时间", "年份",
               "信源等级", "发布机构", "来源标题", "来源链接", "沉淀时间"]
    ws.append(headers)
    for r in rows:
        ws.append([
            r.get("framework_key", ""),
            r.get("metric", ""),
            r.get("metric_label", ""),
            r.get("value", ""),
            r.get("value_norm", ""),
            r.get("unit", ""),
            r.get("period", ""),
            r.get("year", ""),
            r.get("source_tier", ""),
            r.get("publisher", ""),
            r.get("source_title", ""),
            r.get("source_url", ""),
            r.get("saved_at", ""),
        ])

    out_path = out_path or os.path.join(METRICS_DIR, "metrics_export.xlsx")
    dirname = os.path.dirname(out_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    wb.save(out_path)
    return out_path
