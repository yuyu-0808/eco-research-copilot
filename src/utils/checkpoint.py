"""Checkpoint 状态管理器：流水线断点续跑与暂停信号的核心。

负责读写项目目录下的 checkpoint.json，记录每个阶段的完成状态与中间产物，
并通过文件实现跨线程（后台执行线程 <-> Streamlit 前端线程）的信号传递：
- 阶段完成状态（pending / done）
- 中间产物数据（plan_data / verified_context / ai_data / docx_path）
- 暂停请求（pause_requested）
"""

import json
import os
import tempfile


class PauseRequested(Exception):
    """协作式暂停信号：在阶段边界抛出，由调用方捕获后优雅退出。"""


class Checkpoint:
    # 流水线六个阶段（顺序固定）：课题架构 / 信源检索 / 事实稽核 / 结构化提炼 / 内容撰写 / 渲染排版
    STAGES = ("architect", "research", "verify", "structure", "write", "render")

    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.path = os.path.join(project_dir, "checkpoint.json")

    def exists(self) -> bool:
        return os.path.exists(self.path)

    def empty_state(self, topic: str = "") -> dict:
        """构造一份全新的 checkpoint 初始状态。"""
        return {
            "version": 1,
            "topic": topic,
            "status": "running",   # running | paused | completed | failed
            "pause_requested": False,
            "current_stage": "plan",
            "stages": {s: {"status": "pending", "data": None} for s in self.STAGES},
        }

    def load(self) -> dict:
        """读取 checkpoint；不存在或损坏时返回空状态。"""
        if not os.path.exists(self.path):
            return self.empty_state()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError):
            return self.empty_state()
        # 容错：补齐缺失字段，避免旧版本/半写文件导致 KeyError
        state.setdefault("version", 1)
        state.setdefault("topic", "")
        state.setdefault("status", "running")
        state.setdefault("pause_requested", False)
        state.setdefault("current_stage", "plan")
        stages = state.setdefault("stages", {})
        for s in self.STAGES:
            stages.setdefault(s, {"status": "pending", "data": None})
        return state

    def save(self, state: dict) -> None:
        """原子写入：先写临时文件再 rename，避免半写损坏 checkpoint。"""
        os.makedirs(self.project_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.project_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    # ---- 阶段状态 ----
    def stage_done(self, name: str, state: dict = None) -> bool:
        state = state or self.load()
        return state["stages"].get(name, {}).get("status") == "done"

    def stage_data(self, name: str, state: dict = None):
        state = state or self.load()
        return state["stages"].get(name, {}).get("data")

    def mark_done(self, name: str, data) -> None:
        """标记某阶段完成并保存中间产物，推进 current_stage。"""
        state = self.load()
        state["stages"][name] = {"status": "done", "data": data}
        state["current_stage"] = self._next_stage(name)
        self.save(state)

    def _next_stage(self, name: str) -> str:
        idx = list(self.STAGES).index(name)
        if idx + 1 < len(self.STAGES):
            return self.STAGES[idx + 1]
        return name

    def reset_from(self, name: str) -> None:
        """把指定阶段及其之后的所有阶段重置为 pending。

        用于中间产物被人工修改后，触发下游阶段重跑。例如编辑 verified_context
        （属于 collect 阶段产物）后调用 reset_from("analyze")，续跑时会重新执行分析+排版。
        """
        state = self.load()
        idx = list(self.STAGES).index(name)
        for s in self.STAGES[idx:]:
            state["stages"][s] = {"status": "pending", "data": None}
        state["current_stage"] = name
        self.save(state)

    # ---- 暂停信号（跨线程，用文件传递） ----
    def request_pause(self) -> None:
        state = self.load()
        state["pause_requested"] = True
        self.save(state)

    def clear_pause(self) -> None:
        state = self.load()
        state["pause_requested"] = False
        state["status"] = "running"
        self.save(state)

    def pause_requested(self) -> bool:
        return self.load().get("pause_requested", False)

    def check_pause(self) -> None:
        """阶段边界调用：若收到暂停请求，置状态为 paused 并抛出 PauseRequested。"""
        if self.pause_requested():
            self.set_status("paused")
            raise PauseRequested()

    def set_status(self, status: str) -> None:
        state = self.load()
        state["status"] = status
        self.save(state)
