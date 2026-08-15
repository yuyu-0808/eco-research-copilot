"""统计接口：Token 消耗 / 任务成功率 / 平均耗时等看板数据。"""

from fastapi import APIRouter

from src.utils import db
from server.response import ok

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def get_stats():
    return ok(db.stats_summary())
