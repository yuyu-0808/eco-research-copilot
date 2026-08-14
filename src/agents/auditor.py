import json
from openai import OpenAI
from src.utils.config import Config
from src.utils.logger import AgentLogger
from src.utils.llm_utils import call_llm


class AuditorAgent:
    def __init__(self, logger: AgentLogger):
        self.logger = logger
        self.client = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url=Config.BASE_URL)
        self.model = Config.MODEL_NAME

    def verify_data(self, plan_data: dict, raw_context: str) -> dict:
        requirements = json.dumps(plan_data.get("research_requirements", []), ensure_ascii=False)
        self.logger.log_event("事实稽核官", "START", "开始校验信源数据真实性")

        prompt = f"""
        你是一位【事实稽核官】，负责从信源研究员检索回来的【原始素材】中甄别真伪、提炼高纯度事实。
        你的任务是“淘金”：过滤垃圾，只留下权威、可溯源的真实数据。

        【必答需求清单】：
        {requirements}

        【原始素材】：
        {raw_context}

        【提炼规则 (必须严格执行)】：
        1. 信源分级采信：每条信源已标注等级（S官方/A权威/B一般/D低质）。S/A级优先采信；B级谨慎对待（仅当无更优信源时用）；D级（低质/营销号）直接丢弃，【不要报错】。
        2. 提取真金：优先从 S/A 级信源提炼有用数据；若某必答问题只有 B 级信源支撑，也提炼但保留其来源等级，供下游判断。
        3. 保留来源：每条提炼出来的事实，必须在其后标注原始来源，格式为「（来源：标题 链接）」，严禁丢失来源信息，供下游内容撰写师引用。
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
                self.client, self.model, self.logger, "事实稽核官", prompt, need_json=True
            )

            is_pass = verification_result.get("is_pass", False)
            if is_pass:
                self.logger.log_event("事实稽核官", "SUCCESS", "数据真实性校验通过，提取真金成功，予以放行！")
            else:
                self.logger.log_event("事实稽核官", "ACTION", f"全是无效噪音，打回重搜。反馈: {verification_result.get('feedback')}")

            return verification_result

        except Exception as e:
            self.logger.log_event("事实稽核官", "FAILED", f"事实稽核过程发生异常: {e}")
            raise e

    def verify_logic(self, topic: str, markdown_report: str, references: list, safe_context: str) -> dict:
        """逻辑校验：论据溯源 + 逻辑矛盾排查，用于撰写-稽核交叉校验循环。"""
        ref_text = "\n".join(f"[{r.get('index')}] {r.get('title')}" for r in (references or [])) or "（无）"
        self.logger.log_event("逻辑稽核", "START", "开始逻辑校验（论据溯源 + 逻辑矛盾排查）")

        prompt = f"""
        你是一位【事实稽核官】，负责对研究报告正文做「逻辑校验」。

        课题：{topic}
        【参考文献清单（正文用 [n] 引用）】：
        {ref_text}

        【待校验正文】：
        {markdown_report}

        【校验规则】：
        1. 论据溯源：正文中的关键数据、结论是否用 [n] 标注了引用编号？引用编号是否都在参考文献清单中存在？若正文出现精确数据却无任何引用来源，视为「疑似编造」，需打回。
        2. 逻辑矛盾：正文前后是否存在数据不一致、结论互相矛盾、因果跳跃等逻辑问题？
        3. 宽容原则：只对「硬伤」打回（无来源的精确数据、明显的逻辑矛盾）。一般性表述、修辞、章节详略不均等非硬伤，应放行。

        请严格按 JSON 输出（is_pass 必须是布尔值）：
        {{
            "is_pass": true,
            "feedback": "仅当 is_pass=false 时填写：指出具体哪一处无溯源或逻辑矛盾，指导撰写师如何修改"
        }}
        """

        try:
            result = call_llm(self.client, self.model, self.logger, "逻辑稽核", prompt, need_json=True)
            is_pass = result.get("is_pass", False)
            if is_pass:
                self.logger.log_event("逻辑稽核", "SUCCESS", "逻辑校验通过，论据溯源完整、无逻辑矛盾。")
            else:
                self.logger.log_event("逻辑稽核", "ACTION", f"逻辑校验发现争议，打回修正。意见: {result.get('feedback')}")
            return result

        except Exception as e:
            self.logger.log_event("逻辑稽核", "FAILED", f"逻辑校验发生异常: {e}")
            raise e
