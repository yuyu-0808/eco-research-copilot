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
        """统一对外的搜索接口。搜索失败时返回内置行业分析框架兜底（明确标记非实时数据）。"""
        try:
            if self.provider == "tavily" and self.tavily_client:
                result = self._tavily_search(query, max_results)
            else:
                result = self._ddg_search(query, max_results)
        except Exception:
            result = ""
        # 若搜索失败（返回错误文本或空），走内置框架兜底
        if not result or result.startswith("Tavily 搜索失败") or result.startswith("DDG 搜索失败"):
            return self._fallback_framework(query)
        return result

    def _fallback_framework(self, query: str) -> str:
        """搜索完全失败时的业务级兜底：返回通用分析框架，严禁作为事实引用。"""
        return (
            f"【搜索降级兜底】针对「{query}」的实时检索失败（网络或搜索服务不可用）。\n"
            "以下为内置的通用行业分析框架，仅供分析师参考，【不含实时数据，禁止作为事实引用】：\n"
            "1. 行业现状：目标市场的规模、增速、渗透率现状（需后续核实）。\n"
            "2. 竞争格局：主要厂商、市场份额、竞争壁垒（需后续核实）。\n"
            "3. 政策与趋势：相关政策、补贴细则、技术演进方向（需后续核实）。\n"
            "4. 风险提示：监管、技术、市场等潜在风险（需后续核实）。\n"
            "注意：以上是框架性提示而非搜索结果，分析师应据此展开但不得编造任何具体数据。"
        )

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
            # 可选代理：仅国内网络使用 DDG 时，在 .env 配置 DDG_PROXY（如 http://127.0.0.1:7890）
            proxy = os.getenv("DDG_PROXY", "")
            if proxy:
                os.environ["HTTP_PROXY"] = proxy
                os.environ["HTTPS_PROXY"] = proxy

            results = DDGS().text(query, max_results=max_results)
            search_context = ""
            for i, res in enumerate(results):
                url = res.get('href') or res.get('url') or ''
                search_context += f"【信源 {i+1}】标题: {res.get('title')}\n链接: {url}\n摘要: {res.get('body')}\n\n"

            if proxy:
                os.environ.pop("HTTP_PROXY", None)
                os.environ.pop("HTTPS_PROXY", None)
            return search_context
        except Exception as e:
            return f"DDG 搜索失败 (可能是代理未开): {e}"