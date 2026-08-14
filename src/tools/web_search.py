import os
from tavily import TavilyClient
from duckduckgo_search import DDGS
from src.utils.config import Config

class WebSearcher:
    def __init__(self):
        self.provider = Config.SEARCH_PROVIDER
        
        # 初始化 Tavily (如果有秘钥)
        if self.provider == "tavily" and Config.TAVILY_API_KEY:
            self.tavily_client = TavilyClient(api_key=Config.TAVILY_API_KEY)
        else:
            self.tavily_client = None

    def search(self, query: str, max_results: int = 3) -> str:
        """统一对外的搜索接口"""
        if self.provider == "tavily" and self.tavily_client:
            return self._tavily_search(query, max_results)
        else:
            return self._ddg_search(query, max_results)

    def _tavily_search(self, query: str, max_results: int) -> str:
        try:
            response = self.tavily_client.search(query=query, search_depth="advanced", max_results=max_results)
            search_context = ""
            for i, res in enumerate(response.get("results", [])):
                url = res.get('url') or ''
                search_context += f"【信源 {i+1}】标题: {res.get('title')}\n链接: {url}\n核心事实: {res.get('content')}\n\n"
            return search_context
        except Exception as e:
            return f"Tavily 搜索失败: {e}"

    def _ddg_search(self, query: str, max_results: int) -> str:
        try:
            # 开启强制本地代理（针对国内网络）
            os.environ["HTTP_PROXY"] = "http://127.0.0.1:7897"
            os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"
            
            results = DDGS().text(query, max_results=max_results)
            search_context = ""
            for i, res in enumerate(results):
                url = res.get('href') or res.get('url') or ''
                search_context += f"【信源 {i+1}】标题: {res.get('title')}\n链接: {url}\n摘要: {res.get('body')}\n\n"
                
            os.environ.pop("HTTP_PROXY", None)
            os.environ.pop("HTTPS_PROXY", None)
            return search_context
        except Exception as e:
            return f"DDG 搜索失败 (可能是代理未开): {e}"