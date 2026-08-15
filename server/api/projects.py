"""项目 API：列表 / 指标 / 详情 / 创建 / 删除。

数据层复用 src/ui/helpers.py 的纯函数（list_projects / load_checkpoint /
load_result / dashboard_metrics），与 Streamlit 端共享同一套 projects/ 产物。
"""

import os
import shutil
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException

from src.ui.helpers import (
    list_projects,
    load_checkpoint,
    load_result,
    dashboard_metrics,
    PROJECTS_DIR,
)
from src.utils import db
from src.utils.checkpoint import Checkpoint
from server.workers import queue
from server.workers.runner import run_research
from server.response import ok
from server.paths import resolve_project_dir

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _dir(project_id: str) -> str:
    return resolve_project_dir(project_id)


def _new_project_id() -> str:
    """生成不冲突的项目 ID（时间戳 + 撞车时加序号后缀）。"""
    base = datetime.now().strftime('%Y%m%d_%H%M%S')
    new_id = f"Project_{base}"
    i = 1
    while os.path.exists(os.path.join(PROJECTS_DIR, new_id)):
        new_id = f"Project_{base}_{i}"
        i += 1
    return new_id


@router.get("")
def get_projects(include_archived: bool = False):
    all_projects = list_projects()
    projects = [p for p in all_projects if not p.get("archived")] if not include_archived else all_projects
    return ok({"projects": projects, "metrics": dashboard_metrics(all_projects)})


@router.post("")
def create_project(payload: dict = None):
    topic = (payload or {}).get("topic", "")
    topic = (topic or "").strip()
    if not topic:
        raise HTTPException(400, "topic 不能为空")
    framework_key = ((payload or {}).get("framework_key") or "").strip()
    project_id = _new_project_id()
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    os.makedirs(project_dir, exist_ok=True)
    # 用户显式选择的框架 key 写入 checkpoint（空 = 自动匹配）
    if framework_key:
        ck = Checkpoint(project_dir)
        state = ck.empty_state()
        state["framework_key"] = framework_key
        ck.save(state)
    # 项目元信息入 SQLite（checkpoint 中间状态仍走磁盘 JSON）
    db.project_upsert(project_id, topic=topic, status="running",
                      checkpoint_path=os.path.join(project_dir, "checkpoint.json"))
    return ok({"project_id": project_id, "topic": topic, "framework_key": framework_key})


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
    ck = Checkpoint(d)
    state = ck.load()
    # 任务仍在运行或暂停：后台线程可能还在写 checkpoint，直接删目录会被 save() 的
    # os.makedirs 复活（僵尸项目）。先请求停止并拒绝删除，待任务彻底停止后再删。
    if queue.is_running(project_id) or state.get("status") in ("running", "paused"):
        ck.request_stop()
        queue.cancel(project_id)
        raise HTTPException(409, "任务仍在运行，已请求停止，请稍后再删除")
    shutil.rmtree(d, ignore_errors=True)
    db.project_delete(project_id)
    return ok({"deleted": project_id})


@router.post("/cleanup")
def cleanup_projects(payload: dict = None):
    """清理 N 天前创建且已结束（非运行/暂停中）的项目，释放磁盘与 SQLite。"""
    days = int((payload or {}).get("days", 30) or 30)
    cutoff = datetime.now() - timedelta(days=days)
    deleted = 0
    for p in list_projects():
        pid = p.get("id", "")
        status = p.get("status", "")
        # 跳过仍在运行 / 暂停中的项目
        if queue.is_running(pid) or status in ("running", "paused"):
            continue
        # 解析创建时间（目录名 Project_YYYYMMDD_HHMMSS）
        try:
            created = datetime.strptime(p.get("created_at", ""), "%Y%m%d_%H%M%S")
        except ValueError:
            continue
        if created >= cutoff:
            continue
        d = p.get("dir", "")
        if d:
            shutil.rmtree(d, ignore_errors=True)
        db.project_delete(pid)
        deleted += 1
    return ok({"deleted": deleted})


@router.post("/{project_id}/rename")
def rename_project(project_id: str, payload: dict = None):
    """重命名项目（更新标题，目录 ID 不变）。"""
    d = _dir(project_id)
    topic = ((payload or {}).get("topic") or "").strip()
    if not topic:
        raise HTTPException(400, "topic 不能为空")
    # 1. checkpoint 标题
    ck = Checkpoint(d)
    state = ck.load()
    state["topic"] = topic
    ck.save(state)
    # 2. result.json 标题
    result = load_result(d)
    if result:
        result["topic"] = topic
        import json
        with open(os.path.join(d, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    # 3. SQLite 元信息
    db.project_update_topic(project_id, topic)
    return ok({"project_id": project_id, "topic": topic})


@router.post("/{project_id}/duplicate")
def duplicate_project(project_id: str):
    """复制项目：把项目目录整体复制为一个新项目。"""
    d = _dir(project_id)
    new_id = _new_project_id()
    new_dir = os.path.join(PROJECTS_DIR, new_id)
    shutil.copytree(d, new_dir)
    # 复制后重置运行状态，避免误判为「正在运行」
    ck = Checkpoint(new_dir)
    state = ck.load()
    state["status"] = "paused"
    state["pause_requested"] = False
    ck.save(state)
    db.project_upsert(new_id, topic=state.get("topic", ""), status="paused",
                      checkpoint_path=os.path.join(new_dir, "checkpoint.json"))
    return ok({"project_id": new_id, "source": project_id})


@router.post("/{project_id}/archive")
def archive_project(project_id: str):
    """归档项目（从默认列表隐藏，可取消归档）。"""
    d = _dir(project_id)
    Checkpoint(d).set_archived(True)
    db.project_archive(project_id, True)
    return ok({"project_id": project_id, "archived": True})


@router.post("/{project_id}/unarchive")
def unarchive_project(project_id: str):
    """取消归档。"""
    d = _dir(project_id)
    Checkpoint(d).set_archived(False)
    db.project_archive(project_id, False)
    return ok({"project_id": project_id, "archived": False})


@router.post("/{project_id}/retry")
def retry_project(project_id: str):
    """一键重试：从断点续跑失败的项目。"""
    d = _dir(project_id)
    state = load_checkpoint(d) or {}
    topic = state.get("topic", "")
    if not topic:
        raise HTTPException(400, "项目缺少课题，无法重试")
    ck = Checkpoint(d)
    ck.clear_pause()
    if not queue.submit(project_id, run_research, project_id, topic, True):
        raise HTTPException(409, "该项目已有任务在运行")
    return ok({"project_id": project_id, "status": "resumed"})
