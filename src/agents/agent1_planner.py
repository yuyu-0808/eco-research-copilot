import json
from openai import OpenAI
from src.utils.config import Config
from src.utils.logger import AgentLogger
from src.utils.llm_utils import call_llm

class PlannerAgent:
    def __init__(self, logger: AgentLogger):
        self.logger = logger
        self.client = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url=Config.BASE_URL)
        self.model = Config.MODEL_NAME

    def generate_plan(self, user_topic: str) -> dict:
        """
        接收用户需求，输出调研提纲和确定性的质量门禁清单。
        """
        self.logger.log_event("Agent1_Planner", "START", f"开始规划课题: {user_topic}")
        
        prompt = f"""
        你是一个全球顶级的宏观商业分析总监。
        用户提出的调研课题是："{user_topic}"

        请你对这个课题进行专业拆解，并输出一份必须严格执行的【研究需求清单 (Requirements Gate)】。
        你必须定义出 2 到 3 个极其核心的 "question_id" 和 "text"（必答问题）。
        如果后续智能体搜集不到清单中要求的数据，整个调研将被阻断。

        请严格返回如下 JSON 格式，绝不要输出额外的代码块标记或解释文本：
        {{
          "topic": "{user_topic}",
          "outline": ["1. 行业现状与痛点", "2. 核心市场数据", "3. 政策与趋势推演"],
          "research_requirements": [
            {{"question_id": "q1", "text": "提取目标市场最近两年的具体销量、市场规模或渗透率的准确数值", "required": true}},
            {{"question_id": "q2", "text": "明确具体的行业政策、补贴细则或关键驱动因素", "required": true}}
          ]
        }}
        """

        try:
            plan_data = call_llm(
                self.client, self.model, self.logger, "Agent1_Planner", prompt, need_json=True
            )
            
            # 记录成功日志
            self.logger.log_event(
                "Agent1_Planner", 
                "SUCCESS", 
                f"成功生成提纲与门禁清单，包含 {len(plan_data.get('research_requirements', []))} 个必答问题"
            )
            return plan_data
            
        except Exception as e:
            self.logger.log_event("Agent1_Planner", "FAILED", f"规划阶段发生异常: {e}")
            raise e