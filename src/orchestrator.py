import os
from src.utils.logger import AgentLogger
from src.utils.config import Config
from src.agents.agent1_planner import PlannerAgent
from src.agents.agent2_scraper import ScraperAgent
from src.agents.agent3_verifier import VerifierAgent
from src.agents.agent4_analyst import AnalystAgent
from src.agents.agent5_formatter import FormatterAgent

class ResearchOrchestrator:
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.logger = AgentLogger(project_name)
        
        # 初始化 5 大智能体 (各司其职，互不干涉)
        self.planner = PlannerAgent(self.logger)
        self.scraper = ScraperAgent(self.logger)
        self.verifier = VerifierAgent(self.logger)
        self.analyst = AnalystAgent(self.logger)
        self.formatter = FormatterAgent(self.logger)

    def run(self, user_topic: str) -> dict:
        self.logger.log_event("Orchestrator", "START", f"开始执行调研流水线: {user_topic}")
        
        try:
            # 阶段 1：战略规划 (立下军令状)
            plan_data = self.planner.generate_plan(user_topic)
            
            # 阶段 2 & 3：采集与验证的内循环 (核心壁垒：防幻觉质量门)
            max_rounds = Config.MAX_COLLECT_ROUNDS
            current_round = 1
            verified_context = ""
            feedback = None
            is_pass = False
            
            while current_round <= max_rounds:
                self.logger.log_event("Orchestrator", "INFO", f"=== 开启第 {current_round}/{max_rounds} 轮情报质检循环 ===")
                
                # Agent 2 执行抓取
                raw_context = self.scraper.collect_data(plan_data, feedback)
                
                # Agent 3 执行质检
                verify_result = self.verifier.verify_data(plan_data, raw_context)
                is_pass = verify_result.get("is_pass", False)
                
                if is_pass:
                    verified_context = verify_result.get("verified_context", "")
                    self.logger.log_event("Orchestrator", "SUCCESS", "✅ 数据质量达标，跳出内循环。")
                    break
                else:
                    feedback = verify_result.get("feedback", "未知原因不合格")
                    self.logger.log_event("Orchestrator", "WARNING", f"❌ 质检被驳回，准备开启下一轮。打回理由: {feedback}")
                    current_round += 1
            
            # 质量门禁兜底：如果重试耗尽仍然没达标
            if not is_pass and Config.REQUIRE_STRICT_EVIDENCE:
                error_msg = "经过多轮搜刮，仍未获取满足必答清单的确凿证据。为防止大模型幻觉，系统强制熔断！"
                self.logger.log_event("Orchestrator", "FAILED", error_msg)
                raise ValueError(error_msg)
            
            # 如果宽容模式开启，或者通过了门禁，继续向下执行
            if not is_pass:
                verified_context = "（注：证据不充分，但已跳过拦截）" + raw_context
            
            # 阶段 4：经济分析推演
            ai_data = self.analyst.analyze(plan_data, verified_context)
            
            # 阶段 5：排版交付
            docx_path = self.formatter.format_delivery(self.project_name, ai_data)
            
            self.logger.log_event("Orchestrator", "SUCCESS", "🎉 全链路自动调研圆满完成！")
            
            return {
                "plan_data": plan_data,
                "ai_data": ai_data,
                "docx_path": docx_path
            }

        except Exception as e:
            self.logger.log_event("Orchestrator", "ERROR", f"🚨 流水线异常中断: {e}")
            raise e