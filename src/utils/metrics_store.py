"""行业指标知识库：数据飞轮（存储后端为 SQLite）。

每次报告生成后，把通过校验的核心指标沉淀到 SQLite 指标库，新建同行业报告时
用历史指标交叉验证，冲突优先提示历史高等级信源数值。支持按行业 / 指标 / 时间
检索，并可导出 Excel。

存储：SQLite 表 metrics（见 src/utils/db.py），旧 JSON 数据自动迁移。
"""

import os
from datetime import datetime

from .normalizer import normalize_value, normalize_period
from .investment_checks import classify_metric, metric_label
from . import db

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA_DIR = os.path.join(_ROOT, "data")

_TIER_RANK = {"A": 6, "B": 5, "C": 4, "D": 3, "E": 2, "F": 1, "": 0}


def _field(e, name, default=""):
    """兼容 EvidenceRecord（dataclass）与 dict 两种形态的字段读取。"""
    if isinstance(e, dict):
        return e.get(name, default)
    return getattr(e, name, default)


def extract_metrics(evidence, framework_key: str = "") -> list:
    """从证据列表提取核心指标条目（指标名 + 归一化数值 + 时间 + 来源 + 等级）。"""
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
    return db.metrics_list(framework_key)


def save_metrics(framework_key: str, entries: list, report_id: str = "") -> int:
    """把指标条目追加到行业指标库（SQLite，去重）。返回新增条数。"""
    return db.metrics_insert(framework_key, entries, report_id)


def _all_keys() -> list:
    return db.metrics_framework_keys()


def add_metric_manual(framework_key: str, metric: str, value: str, period: str = "",
                      source_tier: str = "D", source_title: str = "", source_url: str = "",
                      publisher: str = "", unit: str = "") -> int:
    """手动录入一条指标（自动归一化 + 年份提取），返回新增条数（0=未入库）。

    framework_key 为 generic 或空时拒绝入库（同自动沉淀策略）。
    """
    if not framework_key or framework_key == "generic":
        return 0
    nv = normalize_value(value)
    if nv is None:
        return 0
    p = normalize_period(period)
    entry = {
        "metric": metric,
        "metric_label": metric_label(metric),
        "value": value,
        "value_norm": nv.value,
        "unit": unit or nv.unit,
        "period": period,
        "year": p.year if p else None,
        "source_title": source_title,
        "source_url": source_url,
        "source_tier": source_tier or "D",
        "publisher": publisher,
    }
    return db.metrics_insert(framework_key, [entry], report_id="manual")


_EDITABLE_FIELDS = {
    "framework_key", "metric", "value", "unit", "period", "year",
    "source_title", "source_url", "source_tier", "publisher",
}


def update_metric(metric_id: int, fields: dict) -> bool:
    """编辑一条指标；若 value / period 变化则重新归一化。"""
    fields = dict(fields or {})
    # 去除非可编辑字段，只保留白名单
    editable = {k: v for k, v in fields.items() if k in _EDITABLE_FIELDS}
    if not editable:
        return False
    if "value" in editable:
        nv = normalize_value(str(editable["value"]))
        if nv is None:
            return False
        editable["value_norm"] = nv.value
        if not editable.get("unit"):
            editable["unit"] = nv.unit
    if "period" in editable and "year" not in editable:
        p = normalize_period(str(editable["period"]))
        editable["year"] = p.year if p else None
    if "metric" in editable and "metric_label" not in editable:
        editable["metric_label"] = metric_label(editable["metric"])
    return db.metrics_update(metric_id, editable)


def delete_metric(metric_id: int) -> bool:
    """删除一条指标。"""
    return db.metrics_delete(metric_id)


def metric_trend(framework_key: str, metric: str) -> list:
    """单指标趋势：按年份聚合（同年取信源等级最高者），返回升序序列。

    返回 [{"year", "value", "value_norm", "source_tier"}]
    """
    rows = db.metrics_list(framework_key, metric)
    by_year = {}
    for r in rows:
        y = r.get("year")
        if y is None:
            continue
        cur_rank = _TIER_RANK.get(r.get("source_tier", ""), 0)
        old = by_year.get(y)
        if old is None or cur_rank > _TIER_RANK.get(old.get("source_tier", ""), 0):
            by_year[y] = r
    return [
        {
            "year": y,
            "value": r.get("value"),
            "value_norm": r.get("value_norm"),
            "unit": r.get("unit"),
            "source_tier": r.get("source_tier"),
        }
        for y, r in sorted(by_year.items())
    ]


def query_metrics(framework_key: str = None, metric: str = None, period: str = None, year: int = None) -> list:
    """检索指标库（可按行业 / 指标 / 时间过滤）。"""
    rows = db.metrics_list(framework_key, metric, period, year)
    for r in rows:
        r.setdefault("framework_key", framework_key or "")
    return rows


def cross_validate(framework_key: str, evidence: list, threshold: float = 0.2) -> list:
    """用历史指标库交叉验证当前证据，返回冲突提示列表。"""
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

    out_path = out_path or os.path.join(_DATA_DIR, "metrics_export.xlsx")
    dirname = os.path.dirname(out_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    wb.save(out_path)
    return out_path
