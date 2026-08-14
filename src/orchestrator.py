from src.utils.logger import AgentLogger
from src.utils.config import Config
from src.utils.checkpoint import Checkpoint, PauseRequested
from src.agents.architect import ArchitectAgent
from src.agents.researcher import ResearcherAgent
from src.agents.auditor import AuditorAgent
from src.agents.writer import WriterAgent
from src.agents.renderer import RendererAgent


class ResearchOrchestrator:
    def __init__(self, project_name: str, resume: bool = False):
        self.project_name = project_name
        self.logger = AgentLogger(project_name)
        self.project_dir = self.logger.project_dir
        self.ckpt = Checkpoint(self.project_dir)
        self.resume = resume

        # 初始化 5 类专业角色（课题架构师 / 信源研究员 / 事实稽核官 / 内容撰写师 / 交付渲染官）
        self.architect = ArchitectAgent(self.logger)
        self.researcher = ResearcherAgent(self.logger)
        self.auditor = AuditorAgent(self.logger)
        self.writer = WriterAgent(self.logger)
        self.renderer = RendererAgent(self.logger)

    # ------------------------------------------------------------------
    # 主入口：6 步流水线 + 两个内循环
    # ------------------------------------------------------------------
    def run(self, user_topic: str) -> dict:
        self.logger.log_event("Orchestrator", "START", f"开始执行调研流水线: {user_topic}")

        # 初始化 checkpoint：全新运行重置阶段；续跑保留已完成的阶段
        state = self.ckpt.load()
        state["topic"] = user_topic
        state["status"] = "running"
        state["pause_requested"] = False
        if not self.resume:
            state["stages"] = {s: {"status": "pending", "data": None} for s in self.ckpt.STAGES}
            state["current_stage"] = "architect"
        self.ckpt.save(state)

        try:
            import time
            trace = {}

            t0 = time.time()
            plan_data = self._stage_architect(user_topic)
            trace["architect"] = {
                "elapsed": round(time.time() - t0, 2),
                "outline": len(plan_data.get("outline", [])),
                "requirements": len(plan_data.get("research_requirements", [])),
            }

            t0 = time.time()
            verified_context = self._stage_research_verify(plan_data)
            vd = self.ckpt.stage_data("verify") or {}
            trace["research_verify"] = {
                "elapsed": round(time.time() - t0, 2),
                "rounds": vd.get("round", 1),
                "evidence": len(vd.get("evidence", [])),
                "conflicts": len(vd.get("conflicts", [])),
                "is_pass": vd.get("is_pass", False),
            }

            t0 = time.time()
            structure = self._stage_structure(plan_data, verified_context)
            trace["structure"] = {
                "elapsed": round(time.time() - t0, 2),
                "charts": len(structure.get("charts", [])),
                "tables": len(structure.get("tables", [])),
            }

            t0 = time.time()
            markdown_report = self._stage_write_audit(plan_data, structure, verified_context)
            trace["write_audit"] = {
                "elapsed": round(time.time() - t0, 2),
                "chars": len(markdown_report or ""),
            }

            t0 = time.time()
            docx_path = self._stage_render(structure, markdown_report)
            trace["render"] = {
                "elapsed": round(time.time() - t0, 2),
                "docx": bool(docx_path),
            }

            # 结构化链路追踪落盘
            state = self.ckpt.load()
            state["trace"] = trace
            self.ckpt.save(state)

            self.ckpt.set_status("completed")
            self.logger.log_event("Orchestrator", "SUCCESS", "🎉 全链路自动调研圆满完成！")

            return {
                "plan_data": plan_data,
                "ai_data": {
                    "report_title": structure.get("report_title", ""),
                    "publish_date": structure.get("publish_date", ""),
                    "core_insights": structure.get("core_insights", ""),
                    "markdown_report": markdown_report,
                    "charts": structure.get("charts", []),
                    "tables": structure.get("tables", []),
                    "references": structure.get("references", []),
                },
                "docx_path": docx_path,
            }

        except PauseRequested:
            self.logger.log_event("Orchestrator", "PAUSED", "⏸️ 收到暂停请求，进度已保存，可随时继续。")
            raise

        except Exception as e:
            self.ckpt.set_status("failed")
            self.logger.log_event("Orchestrator", "ERROR", f"🚨 流水线异常中断: {e}")
            raise e

    # ------------------------------------------------------------------
    # 人工确认检查点（三阶段人机协同：框架 → 素材 → 终稿）
    # ------------------------------------------------------------------
    def _maybe_review(self, stage_name: str) -> None:
        """人工确认模式下，在指定节点停下等待确认；全自动模式直接跳过。"""
        if Config.REVIEW_MODE != "manual":
            return
        self.ckpt.set_review(stage_name)
        self.logger.log_event("Orchestrator", "INFO", f"⏸️ 已到达人工确认点「{stage_name}」，等待确认后继续。")
        raise PauseRequested()

    # ------------------------------------------------------------------
    # 阶段 1：课题架构
    # ------------------------------------------------------------------
    def _stage_architect(self, user_topic: str) -> dict:
        state = self.ckpt.load()
        if self.resume and self.ckpt.stage_done("architect", state):
            data = self.ckpt.stage_data("architect", state)
            self.logger.log_event("Orchestrator", "INFO", "♻️ 断点续跑：阶段「架构」已完成，跳过。")
            return data
        self.ckpt.check_pause()
        plan_data = self.architect.generate_plan(user_topic)
        self.ckpt.mark_done("architect", plan_data)
        self._maybe_review("framework")
        return plan_data

    # ------------------------------------------------------------------
    # 阶段 2 & 3：信源检索与事实稽核的内循环（评级驱动）
    # ------------------------------------------------------------------
    def _stage_research_verify(self, plan_data: dict) -> str:
        state = self.ckpt.load()
        if self.resume and self.ckpt.stage_done("verify", state):
            data = self.ckpt.stage_data("verify", state) or {}
            self.logger.log_event("Orchestrator", "INFO", "♻️ 断点续跑：阶段「检索+稽核」已完成，跳过。")
            return data.get("verified_context", "")

        max_rounds = Config.MAX_COLLECT_ROUNDS
        current_round = 1
        verified_context = ""
        feedback = None
        is_pass = False
        collect_result = {}
        evidence_list = []
        conflicts_list = []
        reasons_list = []
        coverage_map = {}

        while current_round <= max_rounds:
            self.ckpt.check_pause()  # 每轮边界也支持暂停
            self.logger.log_event("Orchestrator", "INFO", f"=== 开启第 {current_round}/{max_rounds} 轮信源稽核循环 ===")

            collect_result = self.researcher.collect_data(plan_data, feedback)
            verify_result = self.auditor.verify_data(plan_data, collect_result)
            is_pass = verify_result.get("is_pass", False)

            if is_pass:
                verified_context = verify_result.get("verified_context", "")
                evidence_list = verify_result.get("evidence", [])
                conflicts_list = verify_result.get("conflicts", [])
                reasons_list = verify_result.get("reasons", [])
                coverage_map = verify_result.get("coverage", {})
                self.logger.log_event("Orchestrator", "SUCCESS", "✅ 数据质量达标，跳出内循环。")
                break
            else:
                feedback = verify_result.get("feedback", "未知原因不合格")
                self.logger.log_event("Orchestrator", "WARNING", f"❌ 稽核被驳回，准备开启下一轮。打回理由: {feedback}")
                current_round += 1

        # 质量门禁兜底：如果重试耗尽仍然没达标
        if not is_pass and Config.REQUIRE_STRICT_EVIDENCE:
            error_msg = "经过多轮检索，仍未获取满足必答清单的确凿证据。为防止大模型幻觉，系统强制熔断！"
            self.logger.log_event("Orchestrator", "FAILED", error_msg)
            raise ValueError(error_msg)

        # 如果宽容模式开启，或者通过了门禁，继续向下执行
        if not is_pass:
            fallback_text = collect_result.get("raw_context", "") if isinstance(collect_result, dict) else str(collect_result or "")
            verified_context = "（注：证据不充分，但已跳过拦截）" + fallback_text

        self.ckpt.mark_done("research", {"verified_context": verified_context})
        self.ckpt.mark_done("verify", {
            "verified_context": verified_context,
            "round": current_round,
            "max_rounds": max_rounds,
            "is_pass": is_pass,
            "evidence": [e.to_dict() if hasattr(e, "to_dict") else e for e in evidence_list],
            "conflicts": conflicts_list,
            "reasons": reasons_list,
            "coverage": coverage_map,
        })
        self._maybe_review("materials")
        return verified_context

    # ------------------------------------------------------------------
    # 阶段 4：结构化提炼（交付渲染官 · 前置）
    # ------------------------------------------------------------------
    def _stage_structure(self, plan_data: dict, verified_context: str) -> dict:
        state = self.ckpt.load()
        if self.resume and self.ckpt.stage_done("structure", state):
            data = self.ckpt.stage_data("structure", state)
            self.logger.log_event("Orchestrator", "INFO", "♻️ 断点续跑：阶段「结构化提炼」已完成，跳过。")
            return data
        self.ckpt.check_pause()
        topic = plan_data.get("topic")
        safe_context = verified_context[:5000] if verified_context else "（无可用底层数据）"
        structure = self.renderer.generate_structure(topic, safe_context)
        self.ckpt.mark_done("structure", structure)
        return structure

    # ------------------------------------------------------------------
    # 阶段 5：内容撰写 + 逻辑稽核交叉校验内循环
    # ------------------------------------------------------------------
    def _stage_write_audit(self, plan_data: dict, structure: dict, verified_context: str) -> str:
        state = self.ckpt.load()
        if self.resume and self.ckpt.stage_done("write", state):
            data = self.ckpt.stage_data("write", state) or {}
            self.logger.log_event("Orchestrator", "INFO", "♻️ 断点续跑：阶段「撰写+逻辑稽核」已完成，跳过。")
            return data.get("markdown_report", "")

        topic = plan_data.get("topic")
        safe_context = verified_context[:5000] if verified_context else "（无可用底层数据）"
        references = structure.get("references", [])
        max_rounds = Config.WRITE_AUDIT_ROUNDS
        current_round = 1
        markdown_report = ""
        feedback = None
        is_pass = False

        while current_round <= max_rounds:
            self.ckpt.check_pause()
            self.logger.log_event("Orchestrator", "INFO", f"=== 开启第 {current_round}/{max_rounds} 轮撰写-稽核交叉校验 ===")
            markdown_report = self.writer.write_report(topic, structure, safe_context, feedback)
            logic_result = self.auditor.verify_logic(topic, markdown_report, references, safe_context)
            is_pass = logic_result.get("is_pass", False)
            if is_pass:
                self.logger.log_event("Orchestrator", "SUCCESS", "✅ 逻辑稽核通过，正文定稿。")
                break
            else:
                feedback = logic_result.get("feedback", "逻辑校验未通过")
                self.logger.log_event("Orchestrator", "WARNING", f"⚠️ 逻辑稽核发现争议，打回修正。意见: {feedback}")
                current_round += 1

        # 交叉校验为软门禁：轮次耗尽仍未通过时，宽容采用当前版本
        if not is_pass:
            self.logger.log_event("Orchestrator", "WARNING", "⚠️ 交叉校验轮次耗尽，采用当前版本正文（逻辑校验为软门禁）。")

        self.ckpt.mark_done("write", {"markdown_report": markdown_report, "is_pass": is_pass, "round": current_round})
        self._maybe_review("draft")
        return markdown_report

    # ------------------------------------------------------------------
    # 阶段 6：渲染排版（交付渲染官 · 后置）
    # ------------------------------------------------------------------
    def _stage_render(self, structure: dict, markdown_report: str) -> str:
        state = self.ckpt.load()
        if self.resume and self.ckpt.stage_done("render", state):
            data = self.ckpt.stage_data("render", state) or {}
            self.logger.log_event("Orchestrator", "INFO", "♻️ 断点续跑：阶段「渲染排版」已完成，跳过。")
            return data.get("docx_path", "")
        self.ckpt.check_pause()
        ai_data = {
            "report_title": structure.get("report_title", ""),
            "publish_date": structure.get("publish_date", ""),
            "core_insights": structure.get("core_insights", ""),
            "markdown_report": markdown_report,
            "charts": structure.get("charts", []),
            "tables": structure.get("tables", []),
            "references": structure.get("references", []),
        }
        docx_path = self.renderer.format_delivery(self.project_name, ai_data)
        self.ckpt.mark_done("render", {"docx_path": docx_path})
        return docx_path
