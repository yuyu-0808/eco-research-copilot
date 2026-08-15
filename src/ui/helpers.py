"""UI 数据层：项目历史扫描、结果持久化、仪表盘指标、日志解析。

所有函数均为纯函数/只读，不依赖 Streamlit，方便单独测试。
"""
import json
import os
from datetime import datetime

from src.utils.checkpoint import Checkpoint

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECTS_DIR = os.path.join(ROOT_DIR, "projects")

# 智能体 -> 流水线阶段索引（用于前端可视化，6 步流水线）
STAGE_MAP = {
    "课题架构师": 0,
    "信源研究员": 1,
    "事实稽核官": 2,
    "结构提炼": 3,
    "内容撰写师": 4,
    "逻辑稽核": 4,
    "交付渲染官": 5,
}
STAGE_NAMES = ["架构", "检索", "稽核", "提炼", "撰写", "渲染"]


def html_escape(s):
    """转义 HTML 特殊字符，防止注入/排版错乱。"""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def fmt_duration(sec):
    """秒 -> 人类可读耗时（如 3m 24s）。"""
    sec = int(round(sec))
    if sec < 60:
        return f"{sec}s"
    m, s = divmod(sec, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def _relative_time(ts: str) -> str:
    """把 Project 目录名的时间戳（YYYYMMDD_HHMMSS）转成相对时间（"刚刚"/"12 分钟前"/"3 小时前"/"昨天"/"2026-08-13"）。"""
    if not ts or len(ts) < 8:
        return ts or "—"
    try:
        dt = datetime.strptime(ts[:15] if len(ts) >= 15 else ts[:8] + "_000000", "%Y%m%d_%H%M%S" if "_" in ts[:15] else "%Y%m%d")
    except ValueError:
        return ts
    delta = datetime.now() - dt
    s = int(delta.total_seconds())
    if s < 60:
        return "刚刚"
    m = s // 60
    if m < 60:
        return f"{m} 分钟前"
    h = m // 60
    if h < 24:
        return f"{h} 小时前"
    d = delta.days
    if d == 1:
        return "昨天"
    if d < 7:
        return f"{d} 天前"
    if d < 30:
        return f"{d // 7} 周前"
    return dt.strftime("%Y-%m-%d")


def read_log(project_dir):
    """读取某个项目目录下的 run_log.jsonl，返回事件列表（容错解析）。"""
    path = os.path.join(project_dir, "run_log.jsonl")
    entries = []
    if not os.path.exists(path):
        return entries
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return entries
    return entries


def extract_topic(entries):
    """从日志里提取调研课题。"""
    for e in entries:
        if e.get("action") == "START" and "开始执行调研流水线" in e.get("details", ""):
            return e["details"].split("开始执行调研流水线:", 1)[-1].strip()
    return ""


def load_result(project_dir):
    """加载项目保存的 result.json（完整调研结果）。"""
    path = os.path.join(project_dir, "result.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def load_checkpoint(project_dir):
    """加载项目 checkpoint.json；不存在则返回 None。"""
    ck = Checkpoint(project_dir)
    if not ck.exists():
        return None
    return ck.load()


def save_result(project_dir, project_id, topic, final_result):
    """把一次完整调研结果持久化为 result.json，供历史回看。"""
    os.makedirs(project_dir, exist_ok=True)
    payload = {
        "project_id": project_id,
        "topic": topic,
        "created_at": datetime.now().isoformat(),
        "plan_data": final_result.get("plan_data", {}) if isinstance(final_result, dict) else {},
        "ai_data": final_result.get("ai_data", {}) if isinstance(final_result, dict) else {},
        "docx_path": final_result.get("docx_path", "") if isinstance(final_result, dict) else "",
        "evidence": final_result.get("evidence", []) if isinstance(final_result, dict) else [],
        "conflicts": final_result.get("conflicts", []) if isinstance(final_result, dict) else [],
        "reasons": final_result.get("reasons", []) if isinstance(final_result, dict) else [],
        "coverage": final_result.get("coverage", {}) if isinstance(final_result, dict) else {},
        "warnings": final_result.get("warnings", []) if isinstance(final_result, dict) else [],
        "checks": final_result.get("checks", {}) if isinstance(final_result, dict) else {},
        "trace": final_result.get("trace", {}) if isinstance(final_result, dict) else {},
    }
    path = os.path.join(project_dir, "result.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def list_projects():
    """扫描 projects 目录，返回按时间倒序的项目列表。"""
    projects = []
    if not os.path.isdir(PROJECTS_DIR):
        return projects
    for name in os.listdir(PROJECTS_DIR):
        d = os.path.join(PROJECTS_DIR, name)
        if not os.path.isdir(d):
            continue
        entries = read_log(d)
        result = load_result(d)
        docx = os.path.join(d, "05_final_report.docx")

        topic = (result or {}).get("topic") or extract_topic(entries) or name

        duration = 0.0
        if entries:
            try:
                t0 = datetime.fromisoformat(entries[0]["timestamp"])
                t1 = datetime.fromisoformat(entries[-1]["timestamp"])
                duration = (t1 - t0).total_seconds()
            except (ValueError, KeyError, IndexError):
                duration = 0.0

        ai_data = (result or {}).get("ai_data", {}) or {}
        n_charts = len(ai_data.get("charts", []))
        n_tables = len(ai_data.get("tables", []))
        passed_qa = any("数据质量达标" in (e.get("details") or "") for e in entries)

        completed = bool(result) or os.path.exists(docx)

        # 断点续跑识别：有 checkpoint 且存在已完成阶段、但整体未完成 → 可续跑
        ck_state = load_checkpoint(d)
        ck_status = None
        resumable = False
        if ck_state:
            ck_status = ck_state.get("status")
            if not completed and any(
                (ck_state.get("stages", {}).get(s) or {}).get("status") == "done"
                for s in Checkpoint.STAGES
            ):
                resumable = True

        # 状态精确化：completed > checkpoint 运行态（running/paused/failed/stopped）> partial
        if completed:
            status = "completed"
        elif ck_status:
            status = ck_status
        else:
            status = "partial"
        # 完成时间：优先 result.json 的 created_at，兜底 docx 文件修改时间
        completed_at = ""
        if result:
            completed_at = (result or {}).get("created_at", "")
        if not completed_at and os.path.exists(docx):
            try:
                completed_at = datetime.fromtimestamp(os.path.getmtime(docx)).isoformat()
            except OSError:
                pass

        projects.append({
            "id": name,
            "topic": topic,
            "created_at": name[len("Project_"):] if name.startswith("Project_") else name,
            "has_docx": os.path.exists(docx),
            "has_result": result is not None,
            "status": status,
            "duration": duration,
            "n_charts": n_charts,
            "n_tables": n_tables,
            "n_events": len(entries),
            "relative_time": _relative_time(name[len("Project_"):] if name.startswith("Project_") else ""),
            "completed_at": completed_at,
            "passed_qa": passed_qa,
            "dir": d,
            "resumable": resumable,
            "checkpoint_status": ck_status,
            "error": (ck_state or {}).get("error", ""),
            "archived": bool((ck_state or {}).get("archived", False)),
        })
    projects.sort(key=lambda p: p["id"], reverse=True)
    return projects


def dashboard_metrics(projects=None):
    """计算工作台仪表盘指标。图表/表格累计只统计有完整 result.json 的项目，避免历史老项目显示 0 张。

    可传入已计算的 list_projects() 结果复用，避免重复扫描磁盘。
    """
    if projects is None:
        projects = list_projects()
    total = len(projects)
    completed = sum(1 for p in projects if p["status"] == "completed")
    charts = sum(p["n_charts"] for p in projects if p["has_result"])
    tables = sum(p["n_tables"] for p in projects if p["has_result"])

    qa_total = sum(1 for p in projects if p["n_events"] > 0)
    qa_pass = sum(1 for p in projects if p["passed_qa"])
    qa_rate = round(qa_pass / qa_total * 100) if qa_total else 0

    durations = [p["duration"] for p in projects if p["duration"] > 0]
    avg_sec = sum(durations) / len(durations) if durations else 0.0

    return {
        "total": total,
        "completed": completed,
        "charts": charts,
        "tables": tables,
        "qa_rate": qa_rate,
        "qa_total": qa_total,
        "avg_sec": avg_sec,
    }


def derive_stages(entries):
    """根据日志事件推导 6 个流水线阶段的实时状态：pending/active/done/error。"""
    states = ["pending"] * 6
    for e in entries:
        agent = e.get("agent", "")
        action = e.get("action", "")
        if agent not in STAGE_MAP:
            continue
        i = STAGE_MAP[agent]
        if action in ("SUCCESS",):
            states[i] = "done"
        elif action in ("FAILED", "ERROR"):
            states[i] = "error"
        elif states[i] != "done" and states[i] != "error" and action in ("START", "ACTION", "WARNING", "INFO"):
            states[i] = "active"

    # 全局熔断：Orchestrator 报错时，把仍处于 active 的阶段标为 error
    for e in entries:
        if e.get("action") in ("FAILED", "ERROR") and e.get("agent") == "Orchestrator":
            for i in range(6):
                if states[i] == "active":
                    states[i] = "error"
    return states
