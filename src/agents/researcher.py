import json
from openai import OpenAI
from src.utils.config import Config
from src.utils.logger import AgentLogger
from src.tools.web_search import WebSearcher
from src.utils.llm_utils import call_llm
from src.utils.source_grade import source_grade

class ResearcherAgent:
    def __init__(self, logger: AgentLogger):
        self.logger = logger
        self.client = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url=Config.BASE_URL)
        self.model = Config.MODEL_NAME
        self.searcher = WebSearcher()

    def collect_data(self, plan_data: dict, feedback: str = None) -> str:
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
        关键词可包含 site: 语法聚焦权威源（如 site:gov.cn、site:bis.doc.gov）；中英文各生成一些。
        请严格按 JSON 输出：
        {
            "search_queries": ["关键词1", "关键词2", "关键词3", "关键词4"]
        }
        """

        try:
            queries = call_llm(
                self.client, self.model, self.logger, "信源研究员", prompt, need_json=True
            ).get("search_queries", [])
            
            # 防御机制：不管大模型生成多少个词，强制只截取前 4 个，控制 API 额度
            queries = queries[:4] 
            
            self.logger.log_event("信源研究员", "ACTION", f"物理截断后，执行搜索词: {queries}")
            
            raw_context = ""
            for q in queries:
                self.logger.log_event("信源研究员", "ACTION", f"正在检索信源: {q}")
                sources = self.searcher.search(q, max_results=5)  # 每次搜索最多返回5条
                raw_context += f"【搜索词: {q}】的返回结果：\n"
                for i, s in enumerate(sources, 1):
                    url = s.get("url", "")
                    title = s.get("title", "")
                    if url:
                        grade, label = source_grade(url, title)
                        raw_context += f"【信源 {i} · {grade}级{label}】标题: {title}\n链接: {url}\n核心事实: {s.get('snippet','')}\n\n"
                    else:
                        raw_context += f"【信源 {i} · 兜底】{title}\n{s.get('snippet','')}\n\n"
                raw_context += "-" * 30 + "\n"
                
            self.logger.log_event("信源研究员", "SUCCESS", "本轮信源检索完毕。")
            return raw_context

        except Exception as e:
            self.logger.log_event("信源研究员", "FAILED", f"信源检索失败: {e}")
            raise e