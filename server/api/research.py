"""调研任务 API：提交 / 暂停 / 续跑 / 复位 / 结果。

任务执行与前端解耦：POST /run 把任务丢进后台队列（APScheduler 线程池），
立即返回，页面关闭也不影响任务继续跑；进度通过 checkpoint + WebSocket 查询。
"""

from fastapi import APIRouter, HTTPException

from src.ui.helpers import load_checkpoint, load_result
from src.utils.checkpoint import Checkpoint
from server.workers import queue
from server.workers.runner import run_research
from server.response import ok
from server.paths import resolve_project_dir

router = APIRouter(prefix="/api/projects", tags=["research"])


def _dir(project_id: str) -> str:
    return resolve_project_dir(project_id)


def _topic(project_id: str, d: str) -> str:
    ck = load_checkpoint(d) or {}
    return (ck.get("topic") or "").strip()


@router.post("/{project_id}/run")
def run(project_id: str, payload: dict = None):
    """提交调研任务到后台队列（非阻塞）。"""
    d = _dir(project_id)
    topic = ((payload or {}).get("topic") or "").strip() or _topic(project_id, d)
    if not topic:
        raise HTTPException(400, "缺少课题 topic")
    if not queue.submit(project_id, run_research, project_id, topic, False):
        raise HTTPException(409, "该项目已有任务在运行")
    return ok({"project_id": project_id, "topic": topic, "status": "queued"})


@router.post("/{project_id}/pause")
def pause(project_id: str):
    """请求暂停：置 pause_requested，orchestrator 在阶段边界优雅停下。"""
    d = _dir(project_id)
    Checkpoint(d).request_pause()
    return ok({"project_id": project_id, "status": "pause_requested"})


@router.post("/{project_id}/stop")
def stop(project_id: str):
    """终止任务：置 stop_requested + 从队列移除，orchestrator 在阶段边界彻底停止。"""
    d = _dir(project_id)
    Checkpoint(d).request_stop()
    queue.cancel(project_id)
    return ok({"project_id": project_id, "status": "stop_requested"})


@router.post("/{project_id}/resume")
def resume(project_id: str):
    """从断点续跑：清除暂停/终止信号，以 resume=True 重新入队。"""
    d = _dir(project_id)
    topic = _topic(project_id, d)
    ck = Checkpoint(d)
    ck.clear_pause()
    ck.clear_stop()
    if not queue.submit(project_id, run_research, project_id, topic, True):
        raise HTTPException(409, "该项目已有任务在运行")
    return ok({"project_id": project_id, "status": "resumed"})


@router.post("/{project_id}/reset")
def reset(project_id: str, payload: dict = None):
    """从某阶段复位重跑；不指定 stage 则全部重置。"""
    d = _dir(project_id)
    stage = ((payload or {}).get("stage") or "").strip()
    ck = Checkpoint(d)
    ck.clear_stop()
    if stage and stage in ck.STAGES:
        ck.reset_from(stage)
    else:
        state = ck.load()
        state["stages"] = {s: {"status": "pending", "data": None} for s in ck.STAGES}
        state["current_stage"] = ck.STAGES[0]
        state["status"] = "running"
        state["review_stage"] = ""
        ck.save(state)
    return ok({"project_id": project_id, "reset_from": stage or "all"})


@router.get("/{project_id}/result")
def result(project_id: str):
    """报告结果（evidence / conflicts / reasons / warnings / trace / docx）。"""
    d = _dir(project_id)
    return ok({
        "project_id": project_id,
        "result": load_result(d),
        "checkpoint": load_checkpoint(d),
    })
