"""项目 API：列表 / 指标 / 详情 / 创建 / 删除。

数据层复用 src/ui/helpers.py 的纯函数（list_projects / load_checkpoint /
load_result / dashboard_metrics），与 Streamlit 端共享同一套 projects/ 产物。
"""

import os
import shutil
from datetime import datetime

from fastapi import APIRouter, HTTPException

from src.ui.helpers import (
    list_projects,
    load_checkpoint,
    load_result,
    dashboard_metrics,
    PROJECTS_DIR,
)
from src.utils import db
from server.workers import queue
from server.response import ok

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _dir(project_id: str) -> str:
    d = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.isdir(d):
        raise HTTPException(404, f"项目不存在: {project_id}")
    return d


@router.get("")
def get_projects():
    return ok({"projects": list_projects(), "metrics": dashboard_metrics()})


@router.post("")
def create_project(payload: dict = None):
    topic = (payload or {}).get("topic", "")
    topic = (topic or "").strip()
    if not topic:
        raise HTTPException(400, "topic 不能为空")
    project_id = f"Project_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(os.path.join(PROJECTS_DIR, project_id), exist_ok=True)
    # 项目元信息入 SQLite（checkpoint 中间状态仍走磁盘 JSON）
    db.project_upsert(project_id, topic=topic, status="running",
                      checkpoint_path=os.path.join(PROJECTS_DIR, project_id, "checkpoint.json"))
    return ok({"project_id": project_id, "topic": topic})


@router.get("/{project_id}")
def get_project(project_id: str):
    d = _dir(project_id)
    return ok({
        "project_id": project_id,
        "checkpoint": load_checkpoint(d),
        "result": load_result(d),
        "running": queue.is_running(project_id),
    })


@router.delete("/{project_id}")
def delete_project(project_id: str):
    d = _dir(project_id)
    queue.cancel(project_id)  # 若在跑，先从队列移除
    shutil.rmtree(d, ignore_errors=True)
    return ok({"deleted": project_id})
