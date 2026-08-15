"""指标库 API：检索 + Excel 导出（数据飞轮的可视化入口）。"""

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from src.utils.metrics_store import query_metrics, export_excel, _all_keys
from server.response import ok

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("")
def list_metrics(
    framework_key: str = Query(None),
    metric: str = Query(None),
    period: str = Query(None),
):
    """检索指标库（可按行业 / 指标 / 时间过滤）。"""
    rows = query_metrics(framework_key, metric, period)
    return ok({
        "count": len(rows),
        "industries": _all_keys(),
        "metrics": rows,
    })


@router.get("/export")
def export(framework_key: str = Query(None)):
    """把指标库导出为 Excel（.xlsx）。"""
    path = export_excel(framework_key)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="指标库.xlsx",
    )
