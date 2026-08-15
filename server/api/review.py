"""三阶段人机协同确认点 API（可编辑）：框架 / 素材 / 终稿。

手动模式（REVIEW_MODE=manual）下，orchestrator 在三个节点停下等待人工确认：
- framework：框架确认（章节增删 / 排序 / 证据门槛调整）
- materials：素材确认（信源增删 / 评级调整 / 标记必采）
- draft：终稿确认（正文编辑 / 打回重写）

每个确认点：GET 读数据 → PUT 保存编辑 → POST confirm 确认通过并续跑。
由于确认点都在下游阶段执行之前，编辑「实时生效」，无需复位下游阶段。
"""

from fastapi import APIRouter, HTTPException

from src.ui.helpers import load_checkpoint
from src.utils.checkpoint import Checkpoint
from src.utils.frameworks import _build_value_spec
from src.utils.evidence import EvidenceRecord, records_to_text
from server.workers import queue
from server.workers.runner import run_research
from server.response import ok
from server.paths import resolve_project_dir

router = APIRouter(prefix="/api/projects/{project_id}/review", tags=["review"])


def _dir(project_id: str) -> str:
    return resolve_project_dir(project_id)


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
        resp["warnings"] = verify.get("warnings", [])
        resp["reasons"] = verify.get("reasons", [])
        resp["draft_feedback"] = state.get("draft_feedback", "")
        # 覆盖率报告：join research_requirements（章节/门槛） + coverage（实际证据数）
        plan = (stages.get("architect") or {}).get("data") or {}
        reqs = plan.get("research_requirements", []) or []
        coverage = verify.get("coverage", {}) or {}
        report = []
        for r in reqs:
            qid = r.get("question_id", "")
            covered = coverage.get(qid, 0)
            min_ev = r.get("min_evidence", 1)
            report.append({
                "question_id": qid,
                "section": r.get("section", ""),
                "question": r.get("text", ""),
                "min_evidence": min_ev,
                "min_tier": r.get("min_tier", ""),
                "covered": covered,
                "status": "pass" if covered >= min_ev else "fail",
            })
        total = len(report)
        passed = sum(1 for x in report if x["status"] == "pass")
        resp["coverage_report"] = report
        resp["coverage_summary"] = {
            "total": total,
            "passed": passed,
            "rate": round(passed / total * 100) if total else 0,
        }
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
    """保存终稿编辑：正文 markdown + 可选打回修改意见。"""
    d, ck, state = _state(project_id)
    markdown = (payload or {}).get("markdown", "")
    feedback = ((payload or {}).get("feedback") or "").strip()
    write = (state["stages"].get("write") or {}).get("data") or {}
    write["markdown_report"] = markdown
    state["stages"]["write"]["data"] = write
    if feedback:
        state["draft_feedback"] = feedback
    ck.save(state)
    return ok({"project_id": project_id, "saved": True, "feedback": bool(feedback)})


@router.post("/confirm")
def confirm(project_id: str, payload: dict = None):
    """确认通过（或打回重写）并续跑。

    - rewrite=False：确认通过，继续渲染排版；
    - rewrite=True：打回重写，复位撰写阶段，携带 draft_feedback 重新撰写。
    """
    d, ck, state = _state(project_id)
    topic = state.get("topic", "")
    if not topic:
        raise HTTPException(400, "项目缺少课题，无法续跑")
    rewrite = bool((payload or {}).get("rewrite", False))
    if rewrite:
        # 按确认点决定打回深度：框架打回从架构重跑，素材打回从校验重跑，终稿打回从撰写重跑
        stage = state.get("review_stage", "")
        reset_map = {"framework": "architect", "materials": "verify", "draft": "write"}
        ck.reset_from(reset_map.get(stage, "write"))
    ck.clear_review()
    if not queue.submit(project_id, run_research, project_id, topic, True):
        raise HTTPException(409, "该项目已有任务在运行")
    return ok({"project_id": project_id, "status": "resumed", "rewrite": rewrite})
