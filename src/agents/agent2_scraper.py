import json
from openai import OpenAI
from src.utils.config import Config
from src.utils.logger import AgentLogger
from src.tools.web_search import WebSearcher
from src.utils.llm_utils import call_llm

class ScraperAgent:
    def __init__(self, logger: AgentLogger):
        self.logger = logger
        self.client = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url=Config.BASE_URL)
        self.model = Config.MODEL_NAME
        self.searcher = WebSearcher()

    def collect_data(self, plan_data: dict, feedback: str = None) -> str:
        topic = plan_data.get("topic")
        requirements = json.dumps(plan_data.get("research_requirements", []), ensure_ascii=False)
        
        self.logger.log_event("Agent2_Scraper", "START", f"开始为课题搜集情报: {topic}")
        
        prompt = f"""
        当前调研课题："{topic}"
        我们的必答需求清单是：{requirements}
        """
        if feedback:
            prompt += f"\n上一轮抓取被质检官退回，反馈意见：\n{feedback}\n请生成全新的、更具体的搜索词。"
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
                self.client, self.model, self.logger, "Agent2_Scraper", prompt, need_json=True
            ).get("search_queries", [])
            
            # 防御机制：不管大模型生成多少个词，强制只截取前 4 个，控制 API 额度
            queries = queries[:4] 
            
            self.logger.log_event("Agent2_Scraper", "ACTION", f"物理截断后，执行搜索词: {queries}")
            
            raw_context = ""
            for q in queries:
                self.logger.log_event("Agent2_Scraper", "ACTION", f"正在请求 Tavily: {q}")
                result = self.searcher.search(q, max_results=5) # 每次搜索最多返回5条结果
                raw_context += f"【搜索词: {q}】的返回结果：\n{result}\n" + "-"*30 + "\n"
                
            self.logger.log_event("Agent2_Scraper", "SUCCESS", "本轮情报搜集完毕。")
            return raw_context

        except Exception as e:
            self.logger.log_event("Agent2_Scraper", "FAILED", f"情报抓取失败: {e}")
            raise e