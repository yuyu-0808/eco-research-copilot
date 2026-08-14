import os
import re
from urllib.parse import urlparse, parse_qs, unquote

from tavily import TavilyClient
from src.utils.config import Config


def _import_ddgs():
    """兼容导入 DDG 库：优先新库 ddgs，回落旧库 duckduckgo_search。"""
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    return DDGS


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

    # ------------------------------------------------------------------
    # DuckDuckGo：双通道（库优先，HTML 接口兜底）
    # ------------------------------------------------------------------
    def _ddg_search(self, query: str, max_results: int) -> list:
        # 通道 1：ddgs / duckduckgo-search 库
        try:
            return self._ddg_library(query, max_results)
        except Exception:
            pass
        # 通道 2：DDG 纯 HTML 接口兜底
        try:
            return self._ddg_html(query, max_results)
        except Exception:
            pass
        return []

    def _ddg_library(self, query: str, max_results: int) -> list:
        DDGS = _import_ddgs()
        proxy = os.getenv("DDG_PROXY", "")
        if proxy:
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy

        results = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href") or r.get("url") or "",
                        "snippet": r.get("body", ""),
                    })
        finally:
            if proxy:
                os.environ.pop("HTTP_PROXY", None)
                os.environ.pop("HTTPS_PROXY", None)
        return results

    def _ddg_html(self, query: str, max_results: int) -> list:
        """DDG 纯 HTML 接口兜底：直接抓 html.duckduckgo.com，正则解析结果。"""
        import requests

        proxy = os.getenv("DDG_PROXY", "")
        proxies = {"http": proxy, "https": proxy} if proxy else None
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (research-agent)"},
            proxies=proxies,
            timeout=15,
        )
        resp.raise_for_status()

        results = []
        for m in re.finditer(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', resp.text):
            href = m.group(1)
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            results.append({
                "title": title,
                "url": self._decode_ddg_url(href),
                "snippet": "",
            })
            if len(results) >= max_results:
                break
        return results

    @staticmethod
    def _decode_ddg_url(href: str) -> str:
        """把 DDG 的 //duckduckgo.com/l/?uddg=<url> 跳转链接解码成真实 URL。"""
        try:
            if "uddg=" in href:
                full = href if href.startswith("http") else "https:" + href
                return unquote(parse_qs(urlparse(full).query).get("uddg", [href])[0])
        except Exception:
            pass
        return href
