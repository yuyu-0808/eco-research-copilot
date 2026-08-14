import json
from openai import OpenAI
from src.utils.config import Config
from src.utils.logger import AgentLogger
from src.utils.llm_utils import call_llm


class VerifierAgent:
    def __init__(self, logger: AgentLogger):
        self.logger = logger
        self.client = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url=Config.BASE_URL)
        self.model = Config.MODEL_NAME

    def verify_data(self, plan_data: dict, raw_context: str) -> dict:
        requirements = json.dumps(plan_data.get("research_requirements", []), ensure_ascii=False)
        self.logger.log_event("Agent3_Verifier", "START", "质检官(宽容的漏斗)开始过滤数据")

        prompt = f"""
        你是一个【宽容且高效的信息提炼官（宽容的漏斗）】。
        你的任务是从实习生抓取回来的【原始素材】中“淘金”，并提取有用信息。

        【必答需求清单】：
        {requirements}

        【原始素材】：
        {raw_context}

        【提炼规则 (必须严格执行)】：
        1. 过滤垃圾：如果素材中包含无关信息或极低质量的营销号内容（D级信源），【不要报错】，直接默默丢弃它们即可。
        2. 提取真金：只要在素材中找到了哪怕一点点有用的、权威的数据（S/A/B级），就将其提炼到 verified_context 中。
        3. 保留来源：每条提炼出来的事实，必须在其后标注原始来源，格式为「（来源：标题 链接）」，严禁丢失来源信息，供下游分析师引用。
        4. 宽容放行：只要你提炼出了任何有价值的信息，就强制设置 "is_pass": true。「有价值」包括两类：① 精确数据（数值、统计）；② 权威定性信息（政策表述、官方表态、行业趋势、研究报告结论）。若某必答问题只拿到定性信息而缺精确数字，也要放行，并在 verified_context 中如实标注「精确数据待核实」。
        5. 极端情况：只有当所有原始素材【全部都是垃圾】、【完全毫无用处】（连任何相关的定性信息都没有）时，才设置 "is_pass": false，并给出 feedback。不要因为「缺精确数字」就打回，只要搜到了相关权威信息就应放行。
        6. JSON 转义（极其重要）：verified_context 的内容中若出现英文双引号，必须转义为 \\"，或直接改用中文引号「」；换行请用 \\n 表示。否则会导致 JSON 解析失败。

        请严格按 JSON 输出（is_pass 必须是布尔值 true 或 false）：
        {{
            "is_pass": true,
            "feedback": "仅当 is_pass 为 false 时填写：指导下一轮该搜什么词",
            "verified_context": "当 is_pass 为 true 时填写：提炼后的高纯度事实数据，每条事实必须附带（来源：标题 链接）"
        }}
        """

        try:
            verification_result = call_llm(
                self.client, self.model, self.logger, "Agent3_Verifier", prompt, need_json=True
            )

            is_pass = verification_result.get("is_pass", False)
            if is_pass:
                self.logger.log_event("Agent3_Verifier", "SUCCESS", "过滤掉垃圾信息，提取真金成功，予以放行！")
            else:
                self.logger.log_event("Agent3_Verifier", "ACTION", f"全是无效噪音，打回重搜。反馈: {verification_result.get('feedback')}")

            return verification_result

        except Exception as e:
            self.logger.log_event("Agent3_Verifier", "FAILED", f"过滤过程发生异常: {e}")
            raise e
