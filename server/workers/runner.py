"""执行器：在后台线程里跑 orchestrator.run()，并把结果落盘为 result.json。

只做一件事：实例化 ResearchOrchestrator 并运行。核心逻辑（状态机 / 断点续跑 /
暂停信号 / 代码校验）全部复用 src/orchestrator.py，零改动。
"""

import os

from src.orchestrator import ResearchOrchestrator
from src.utils.checkpoint import Checkpoint, PauseRequested
from src.ui.helpers import save_result
from src.utils.metrics_store import extract_metrics, save_metrics
from src.utils import db

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECTS_DIR = os.path.join(ROOT_DIR, "projects")


def run_research(project_id: str, topic: str, resume: bool = False) -> None:
    """后台执行一次调研任务。

    - 正常完成：orchestrator 内部已把各阶段产物写入 checkpoint，这里再补一份
      result.json 供历史回看（复用 helpers.save_result）。
    - 暂停 / 失败：orchestrator 会抛 PauseRequested / Exception，checkpoint 里
      已记录 paused / failed 状态，供续跑与状态查询。
    """
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    os.makedirs(project_dir, exist_ok=True)

    orchestrator = ResearchOrchestrator(project_name=project_id, resume=resume)
    try:
        result = orchestrator.run(topic)
        _persist_result(project_dir, project_id, topic, orchestrator)
    except PauseRequested:
        # 已暂停：checkpoint 记录 paused 状态，等 resume 续跑，不落 result
        return
    except Exception:
        # 失败：checkpoint 记录 failed 状态，向上抛给调度器（线程结束）
        raise


def _persist_result(project_dir: str, project_id: str, topic: str, orchestrator) -> None:
    """把完整调研结果组装成 result.json 落盘，供历史回看。"""
    ckpt = Checkpoint(project_dir)
    state = ckpt.load()
    stages = state.get("stages", {})
    plan_data = (stages.get("architect") or {}).get("data") or {}
    structure = (stages.get("structure") or {}).get("data") or {}
    write_data = (stages.get("write") or {}).get("data") or {}
    verify_data = (stages.get("verify") or {}).get("data") or {}
    docx_path = ((stages.get("render") or {}).get("data") or {}).get("docx_path", "")

    final_result = {
        "plan_data": plan_data,
        "ai_data": {
            "report_title": structure.get("report_title", ""),
            "publish_date": structure.get("publish_date", ""),
            "core_insights": structure.get("core_insights", ""),
            "markdown_report": write_data.get("markdown_report", ""),
            "charts": structure.get("charts", []),
            "tables": structure.get("tables", []),
            "references": structure.get("references", []),
        },
        "docx_path": docx_path,
        "evidence": verify_data.get("evidence", []),
        "conflicts": verify_data.get("conflicts", []),
        "reasons": verify_data.get("reasons", []),
        "coverage": verify_data.get("coverage", {}),
        "warnings": verify_data.get("warnings", []),
        "checks": verify_data.get("checks", {}),
        "trace": state.get("trace", {}),
    }
    save_result(project_dir, project_id, topic, final_result)

    # 项目元信息入 SQLite（状态 completed + 图表数等）
    try:
        db.project_upsert(
            project_id, topic=topic, status="completed",
            has_result=True, has_docx=bool(docx_path),
            n_charts=len(structure.get("charts", [])),
            n_tables=len(structure.get("tables", [])),
        )
    except Exception:
        pass

    # 数据飞轮：把通过校验的核心指标沉淀到行业指标库（失败不阻断）
    try:
        framework_key = plan_data.get("framework_key", "")
        entries = extract_metrics(verify_data.get("evidence", []), framework_key)
        added = save_metrics(framework_key, entries, report_id=project_id)
        if added:
            orchestrator.logger.log_event(
                "指标库", "SUCCESS", f"沉淀 {added} 条核心指标到「{framework_key}」指标库"
            )
    except Exception as e:
        orchestrator.logger.log_event("指标库", "WARNING", f"指标沉淀失败（不影响报告）: {e}")
