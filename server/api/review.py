"""三阶段人机协同确认点 API（可编辑）：框架 / 素材 / 终稿。

手动模式（REVIEW_MODE=manual）下，orchestrator 在三个节点停下等待人工确认：
- framework：框架确认（章节增删 / 排序 / 证据门槛调整）
- materials：素材确认（信源增删 / 评级调整 / 标记必采）
- draft：终稿确认（正文编辑 / 打回重写）

每个确认点：GET 读数据 → PUT 保存编辑 → POST confirm 确认通过并续跑。
由于确认点都在下游阶段执行之前，编辑「实时生效」，无需复位下游阶段。
"""

import os

from fastapi import APIRouter, HTTPException

from src.ui.helpers import load_checkpoint, PROJECTS_DIR
from src.utils.checkpoint import Checkpoint
from src.utils.frameworks import _build_value_spec
from src.utils.evidence import EvidenceRecord, records_to_text
from server.workers import queue
from server.workers.runner import run_research
from server.response import ok

router = APIRouter(prefix="/api/projects/{project_id}/review", tags=["review"])


def _dir(project_id: str) -> str:
    d = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.isdir(d):
        raise HTTPException(404, f"项目不存在: {project_id}")
    return d


def _state(project_id: str) -> tuple:
    d = _dir(project_id)
    ck = Checkpoint(d)
    return d, ck, ck.load()


@router.get("")
def get_review(project_id: str):
    """读取当前确认点及其可编辑数据。"""
    d, ck, state = _state(project_id)
    review_stage = state.get("review_stage", "")
    stages = state.get("stages", {})
    resp = {
        "project_id": project_id,
        "review_stage": review_stage,
        "topic": state.get("topic", ""),
    }

    if review_stage == "framework":
        plan = (stages.get("architect") or {}).get("data") or {}
        reqs = plan.get("research_requirements", []) or []
        resp["sections"] = [
            {
                "question_id": r.get("question_id", f"q{i+1}"),
                "title": r.get("section", ""),
                "question": r.get("text", ""),
                "metrics": r.get("metrics", []) or [],
                "min_evidence": r.get("min_evidence", 2),
                "min_tier": r.get("min_tier", "C"),
            }
            for i, r in enumerate(reqs)
        ]
    elif review_stage == "materials":
        verify = (stages.get("verify") or {}).get("data") or {}
        resp["evidence"] = verify.get("evidence", [])
        resp["conflicts"] = verify.get("conflicts", [])
        resp["warnings"] = verify.get("warnings", [])
        resp["coverage"] = verify.get("coverage", {})
    elif review_stage == "draft":
        write = (stages.get("write") or {}).get("data") or {}
        resp["markdown"] = write.get("markdown_report", "")
        verify = (stages.get("verify") or {}).get("data") or {}
        resp["coverage"] = verify.get("coverage", {})
        resp["conflicts"] = verify.get("conflicts", [])
    return ok(resp)


@router.put("/framework")
def save_framework(project_id: str, payload: dict = None):
    """保存框架编辑：章节增删/排序/证据门槛，重建 outline + research_requirements。"""
    d, ck, state = _state(project_id)
    sections = (payload or {}).get("sections") or []
    if not sections:
        raise HTTPException(400, "sections 不能为空")

    outline, requirements = [], []
    for i, s in enumerate(sections, 1):
        title = (s.get("title") or "").strip()
        question = (s.get("question") or "").strip()
        metrics = s.get("metrics") or []
        min_evidence = int(s.get("min_evidence", 2) or 2)
        min_tier = str(s.get("min_tier") or "C").upper()
        outline.append(title)
        requirements.append({
            "question_id": f"q{i}",
            "text": question,
            "required": True,
            "metrics": metrics,
            "min_evidence": min_evidence,
            "min_tier": min_tier,
            "section": title,
            "value_spec": _build_value_spec(metrics),
        })

    arch = (state["stages"].get("architect") or {}).get("data") or {}
    arch["outline"] = outline
    arch["research_requirements"] = requirements
    state["stages"]["architect"]["data"] = arch
    ck.save(state)
    return ok({"project_id": project_id, "saved": len(sections)})


@router.put("/materials")
def save_materials(project_id: str, payload: dict = None):
    """保存素材编辑：信源增删 / 评级调整，重建 evidence + verified_context。"""
    d, ck, state = _state(project_id)
    items = (payload or {}).get("evidence") or []

    kept = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("removed"):
            continue
        kept.append(EvidenceRecord.from_dict(it))

    verify = (state["stages"].get("verify") or {}).get("data") or {}
    verify["evidence"] = [e.to_dict() for e in kept]
    verify["verified_context"] = records_to_text(kept)
    state["stages"]["verify"]["data"] = verify
    ck.save(state)
    return ok({"project_id": project_id, "kept": len(kept)})


@router.put("/draft")
def save_draft(project_id: str, payload: dict = None):
    """保存终稿编辑：正文 markdown。"""
    d, ck, state = _state(project_id)
    markdown = (payload or {}).get("markdown", "")
    write = (state["stages"].get("write") or {}).get("data") or {}
    write["markdown_report"] = markdown
    state["stages"]["write"]["data"] = write
    ck.save(state)
    return ok({"project_id": project_id, "saved": True})


@router.post("/confirm")
def confirm(project_id: str):
    """确认通过：清除确认点，从断点续跑。"""
    d, ck, state = _state(project_id)
    topic = state.get("topic", "")
    if not topic:
        raise HTTPException(400, "项目缺少课题，无法续跑")
    ck.clear_review()
    if not queue.submit(project_id, run_research, project_id, topic, True):
        raise HTTPException(409, "该项目已有任务在运行")
    return ok({"project_id": project_id, "status": "resumed"})
