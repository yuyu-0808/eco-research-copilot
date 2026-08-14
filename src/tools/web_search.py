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

    def search(self, query: str, max_results: int = 3) -> list:
        """返回结构化信源列表 [{"title","url","snippet"}]；搜索失败返回兜底框架。"""
        try:
            if self.provider == "tavily" and self.tavily_client:
                results = self._tavily_search(query, max_results)
            else:
                results = self._ddg_search(query, max_results)
        except Exception:
            results = []
        if not results:
            return self._fallback_framework(query)
        return results

    def _fallback_framework(self, query: str) -> list:
        """搜索完全失败时的业务级兜底：内置行业分析框架，严禁作为事实引用。"""
        return [{
            "title": f"【搜索降级兜底】{query}",
            "url": "",
            "snippet": (
                "实时检索失败（网络或搜索服务不可用）。以下为内置通用行业分析框架，"
                "【不含实时数据，禁止作为事实引用】：1.行业现状（规模/增速/渗透率，需核实）"
                "2.竞争格局（厂商/份额，需核实）3.政策与趋势（需核实）4.风险提示（需核实）。"
            ),
        }]

    def _tavily_search(self, query: str, max_results: int) -> list:
        try:
            response = self.tavily_client.search(
                query=query, search_depth="advanced", max_results=max_results
            )
            return [
                {"title": res.get("title", ""), "url": res.get("url", ""), "snippet": res.get("content", "")}
                for res in response.get("results", [])
            ]
        except Exception:
            return []

    def _ddg_search(self, query: str, max_results: int) -> list:
        try:
            # 可选代理：仅国内网络使用 DDG 时，在 .env 配置 DDG_PROXY
            proxy = os.getenv("DDG_PROXY", "")
            if proxy:
                os.environ["HTTP_PROXY"] = proxy
                os.environ["HTTPS_PROXY"] = proxy

            results = DDGS().text(query, max_results=max_results)

            if proxy:
                os.environ.pop("HTTP_PROXY", None)
                os.environ.pop("HTTPS_PROXY", None)

            return [
                {"title": r.get("title", ""), "url": r.get("href") or r.get("url") or "", "snippet": r.get("body", "")}
                for r in results
            ]
        except Exception:
            return []
