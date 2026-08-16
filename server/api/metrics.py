"""指标库 API：检索 + 手动录入/编辑/删除 + 趋势图 + Excel 导出（数据飞轮的可视化入口）。"""

import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from src.utils.metrics_store import (
    query_metrics, export_excel, _all_keys,
    add_metric_manual, update_metric, delete_metric, metric_trend,
)
from server.response import ok

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("")
def list_metrics(
    framework_key: str = Query(None),
    metric: str = Query(None),
    period: str = Query(None),
    year: int = Query(None),
):
    """检索指标库（可按行业 / 指标 / 时间过滤）。"""
    rows = query_metrics(framework_key, metric, period, year)
    return ok({
        "count": len(rows),
        "industries": _all_keys(),
        "metrics": rows,
    })


@router.get("/trend")
def trend(framework_key: str = Query(...), metric: str = Query(...)):
    """单指标趋势：按年份聚合的数值序列，供前端折线图。"""
    series = metric_trend(framework_key, metric)
    return ok({
        "framework_key": framework_key,
        "metric": metric,
        "series": series,
    })


@router.post("")
def create_metric(payload: dict = None):
    """手动录入一条指标（自动归一化 + 年份提取）。"""
    p = payload or {}
    framework_key = (p.get("framework_key") or "").strip()
    metric = (p.get("metric") or "").strip()
    value = (p.get("value") or "").strip()
    if not framework_key or not metric or not value:
        raise HTTPException(400, "framework_key / metric / value 不能为空")
    added = add_metric_manual(
        framework_key, metric, value,
        period=p.get("period", ""),
        source_tier=(p.get("source_tier") or "D").upper(),
        source_title=p.get("source_title", ""),
        source_url=p.get("source_url", ""),
        publisher=p.get("publisher", ""),
        unit=p.get("unit", ""),
        subject=(p.get("subject") or "").strip(),
    )
    if not added:
        raise HTTPException(400, "指标录入失败：数值无法归一化，或与已有条目重复")
    return ok({"added": added})


@router.put("/{metric_id}")
def edit_metric(metric_id: int, payload: dict = None):
    """编辑一条指标（value / period 变化时自动重新归一化）。"""
    if not update_metric(metric_id, payload or {}):
        raise HTTPException(400, "编辑失败：无有效字段，或数值无法归一化")
    return ok({"updated": metric_id})


@router.delete("/{metric_id}")
def remove_metric(metric_id: int):
    """删除一条指标。"""
    if not delete_metric(metric_id):
        raise HTTPException(404, "指标不存在")
    return ok({"deleted": metric_id})


@router.post("/batch_delete")
def batch_delete_metrics(payload: dict = None):
    """批量删除指标（接受 ids 数组）。"""
    ids = (payload or {}).get("ids") or []
    if not ids:
        raise HTTPException(400, "ids 不能为空")
    deleted = 0
    for mid in ids:
        try:
            if delete_metric(int(mid)):
                deleted += 1
        except (ValueError, TypeError):
            continue
    return ok({"deleted": deleted})


@router.get("/export")
def export(framework_key: str = Query(None)):
    """把指标库导出为 Excel（.xlsx）；临时文件在响应后自动清理。"""
    path = export_excel(framework_key)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="指标库.xlsx",
        background=BackgroundTask(os.remove, path),
    )
