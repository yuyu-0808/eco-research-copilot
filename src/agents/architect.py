import json
from openai import OpenAI
from src.utils.config import Config
from src.utils.logger import AgentLogger
from src.utils.llm_utils import call_llm
from src.utils.frameworks import match_framework, build_plan


class ArchitectAgent:
    def __init__(self, logger: AgentLogger):
        self.logger = logger
        self.client = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url=Config.BASE_URL)
        self.model = Config.MODEL_NAME

    def generate_plan(self, user_topic: str) -> dict:
        """
        内核：内置行研框架兜底 + LLM 仅微调。

        保证：
        - 输出结构 100% 符合行研规范（框架兜底）；
        - LLM 完全失败时，仍能返回标准研究计划。
        """
        self.logger.log_event("课题架构师", "START", f"开始按行研框架拆解课题: {user_topic}")

        # 1. 匹配内置框架，生成标准研究计划（纯规则，不依赖 LLM）
        framework = match_framework(user_topic)
        plan_data = build_plan(user_topic, framework)
        self.logger.log_event(
            "课题架构师", "INFO",
            f"已匹配行研框架：{framework.get('name', '通用')}，共 {len(plan_data['outline'])} 个标准章节"
        )

        # 2. 可选：LLM 在框架内微调（补充行业特有维度、精准化必答问题表述）
        #    结构不动，只在现有章节/问题上做语义增强；失败则用框架兜底。
        try:
            plan_data = self._refine_by_llm(plan_data, user_topic)
        except Exception as e:
            self.logger.log_event("课题架构师", "WARNING", f"LLM 微调失败，使用内置框架兜底: {e}")

        self.logger.log_event(
            "课题架构师", "SUCCESS",
            f"研究框架就绪：{len(plan_data.get('research_requirements', []))} 个必答问题，"
            f"框架 {plan_data.get('framework_name', '')}"
        )
        return plan_data

    def _refine_by_llm(self, plan_data: dict, user_topic: str) -> dict:
        """让 LLM 在【固定章节结构不变】的前提下，微调必答问题的表述与核心指标。

        只允许改写 research_requirements 里每条的 text/metrics，
        严禁改动 outline、question_id、min_evidence、min_tier、section。
        """
        requirements = plan_data.get("research_requirements", [])
        outline = plan_data.get("outline", [])
        metrics_library = plan_data.get("metrics_library", {})
        analysis_models = plan_data.get("analysis_models", [])
        supply_chain = plan_data.get("supply_chain", {})
        key_players = plan_data.get("key_players", [])
        prompt = f"""
        你是资深【课题架构师】。已有一个标准行研框架，请在【不改变章节结构】的前提下，
        针对课题 "{user_topic}" 微调每个必答问题的表述，使其更贴合该行业的具体数据维度。

        【固定大纲（严禁改动章节标题与顺序）】：
        {json.dumps(outline, ensure_ascii=False)}

        【当前必答问题（含约束字段）】：
        {json.dumps(requirements, ensure_ascii=False)}

        【行业核心指标库（微调 metrics 时优先从库中选真实指标名）】：
        {json.dumps(metrics_library, ensure_ascii=False)}

        【分析模型】：
        {json.dumps(analysis_models, ensure_ascii=False)}

        【产业链图谱（上下游环节）】：
        {json.dumps(supply_chain, ensure_ascii=False)}

        【重点公司】：
        {json.dumps(key_players, ensure_ascii=False)}

        要求：
        1. 只输出与输入条数相同的 research_requirements 数组，逐条对应；
        2. 每条保留 question_id / required / min_evidence / min_tier / section 原值不变；
        3. 只可微调 text（必答问题表述，更具体化）和 metrics（核心指标，优先替换为行业核心指标库中的真实指标名）；
        4. 严禁新增、删除或调整章节；严禁改变 question_id 与 section 的对应关系。

        严格输出 JSON：{{"research_requirements": [...]}}
        """
        try:
            result = call_llm(
                self.client, self.model, self.logger, "课题架构师", prompt, need_json=True
            )
            refined = result.get("research_requirements", [])
            if not refined or len(refined) != len(requirements):
                self.logger.log_event("课题架构师", "WARNING", "LLM 微调条数不匹配，回退框架原值")
                return plan_data
            # 强制保护：question_id / section / 约束字段以框架为准，只采纳 text/metrics 微调
            for i, item in enumerate(refined):
                if i >= len(requirements):
                    break
                base = requirements[i]
                base["text"] = item.get("text", base["text"])
                base["metrics"] = item.get("metrics", base["metrics"])
            plan_data["research_requirements"] = requirements
            self.logger.log_event("课题架构师", "INFO", "LLM 微调完成（结构不变，问题表述已行业化）")
            return plan_data
        except Exception:
            raise
