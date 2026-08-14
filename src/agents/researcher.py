import json
from openai import OpenAI
from src.utils.config import Config
from src.utils.logger import AgentLogger
from src.tools.web_search import WebSearcher
from src.utils.llm_utils import call_llm
from src.utils.source_grade import source_grade
from src.utils.evidence import EvidenceRecord, records_to_text
from src.utils.validator import infer_publisher


class ResearcherAgent:
    def __init__(self, logger: AgentLogger):
        self.logger = logger
        self.client = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url=Config.BASE_URL)
        self.model = Config.MODEL_NAME
        self.searcher = WebSearcher()

    def collect_data(self, plan_data: dict, feedback: str = None) -> dict:
        """
        采集并结构化信源。

        返回 dict：
            raw_context: 供下游 LLM 阅读的文本块
            evidence:    List[EvidenceRecord]，每条信源已绑定等级/机构/摘录
        """
        topic = plan_data.get("topic")
        requirements = json.dumps(plan_data.get("research_requirements", []), ensure_ascii=False)

        self.logger.log_event("信源研究员", "START", f"开始为课题检索信源: {topic}")

        prompt = f"""
        你是一位【信源研究员】，擅长根据调研课题与必答清单设计精准的多维度检索策略。
        当前调研课题："{topic}"
        我们的必答需求清单是：{requirements}
        """
        if feedback:
            prompt += f"\n上一轮检索被事实稽核官退回，反馈意见：\n{feedback}\n请生成全新的、更具体的搜索词。"
        else:
            prompt += "\n请为我生成 4 个最精准的搜索引擎关键词，覆盖不同维度（数据、政策、厂商/格局等）。"

        prompt += """
        关键词可包含 site: 语法聚焦权威源（如 site:gov.cn）；中英文各生成一些。
        请严格按 JSON 输出：
        {
            "search_queries": ["关键词1", "关键词2", "关键词3", "关键词4"]
        }
        """

        try:
            queries = call_llm(
                self.client, self.model, self.logger, "信源研究员", prompt, need_json=True
            ).get("search_queries", [])
            queries = queries[:4]  # 防御：强制截断，控制 API 额度

            self.logger.log_event("信源研究员", "ACTION", f"执行搜索词: {queries}")

            evidence_list = []
            raw_lines = []
            seen_urls = set()

            for q in queries:
                self.logger.log_event("信源研究员", "ACTION", f"正在检索信源: {q}")
                sources = self.searcher.search(q, max_results=5)
                raw_lines.append(f"【搜索词: {q}】的返回结果：")
                for s in sources:
                    url = s.get("url", "")
                    title = s.get("title", "")
                    snippet = s.get("snippet", "")

                    if url:
                        grade, label = source_grade(url, title)
                    else:
                        grade, label = "B", "兜底信源"

                    # 去重（同 URL 只保留一条）
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    rec = EvidenceRecord(
                        claim=snippet,          # 原始摘录先作 claim，稽核官再提炼
                        excerpt=snippet,
                        source_title=title,
                        source_url=url,
                        source_tier=grade,
                        publisher=infer_publisher(url),
                    )
                    evidence_list.append(rec)

                    raw_lines.append(
                        f"【信源 · {grade}级{label}】标题: {title}\n"
                        f"链接: {url}\n摘录: {snippet}"
                    )
                raw_lines.append("-" * 30)

            raw_context = "\n".join(raw_lines)
            self.logger.log_event(
                "信源研究员", "SUCCESS",
                f"本轮信源检索完毕，采集 {len(evidence_list)} 条结构化证据"
            )
            return {"raw_context": raw_context, "evidence": evidence_list}

        except Exception as e:
            self.logger.log_event("信源研究员", "FAILED", f"信源检索失败: {e}")
            raise e
