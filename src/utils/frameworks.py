"""行研标准化框架引擎 2.0。

框架从「单纯章节结构」升级为「章节结构 + 核心指标库 + 分析模型 + 产业链图谱 + 重点公司」
的完整方法论配置，并以 YAML 插件化：新增行业只需在 frameworks/ 目录放一份 yaml 文件，
无需修改核心代码。

设计要点：
- 框架数据存于 frameworks/*.yaml，模块加载时读取；
- match_framework 按关键词匹配，build_plan 纯规则生成研究计划（不依赖 LLM）；
- plan_data 携带完整框架维度（指标库 / 分析模型 / 产业链 / 重点公司），供下游 Agent 注入。
"""

import os
import re

import yaml

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FRAMEWORKS_DIR = os.path.join(_ROOT, "frameworks")


def load_frameworks():
    """从 frameworks/ 目录（含 custom/ 子目录）加载全部行业框架（含 generic 兜底）。

    返回 (industry_frameworks: dict, generic_framework: dict)。
    """
    industry = {}
    generic = None
    if os.path.isdir(_FRAMEWORKS_DIR):
        for root, _dirs, files in os.walk(_FRAMEWORKS_DIR):
            for fn in sorted(files):
                if not (fn.endswith(".yaml") or fn.endswith(".yml")):
                    continue
                path = os.path.join(root, fn)
                try:
                    with open(path, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                except (OSError, yaml.YAMLError):
                    continue
                if not isinstance(data, dict) or not data.get("key"):
                    continue
                data.setdefault("keywords", [])
                data.setdefault("sections", [])
                data.setdefault("metrics_library", {})
                data.setdefault("analysis_models", [])
                data.setdefault("supply_chain", {})
                data.setdefault("key_players", [])
                data["_source"] = os.path.relpath(path, _ROOT)
                if data["key"] == "generic":
                    generic = data
                else:
                    industry[data["key"]] = data
    if generic is None:
        generic = _DEFAULT_GENERIC
    return industry, generic


# 兜底：frameworks/ 目录缺失时的最小通用框架
_DEFAULT_GENERIC = {
    "key": "generic",
    "name": "通用行业研究",
    "keywords": [],
    "metrics_library": {},
    "analysis_models": ["波特五力", "SWOT", "PEST"],
    "supply_chain": {},
    "key_players": [],
    "sections": [
        {"title": "一、行业概览", "question": "市场规模、增速、现状", "metrics": ["市场规模", "增速"], "min_evidence": 2, "min_tier": "B"},
        {"title": "二、产业链 / 价值链分析", "question": "产业链结构、价值分布", "metrics": ["产业链", "价值分布"], "min_evidence": 2, "min_tier": "C"},
        {"title": "三、竞争格局", "question": "市场份额、竞争壁垒", "metrics": ["市场份额", "竞争壁垒"], "min_evidence": 2, "min_tier": "B"},
        {"title": "四、政策环境", "question": "政策、监管", "metrics": ["政策", "监管"], "min_evidence": 2, "min_tier": "A"},
        {"title": "五、趋势研判与投资机会", "question": "趋势、风险、机会", "metrics": ["趋势", "风险", "机会"], "min_evidence": 1, "min_tier": "C"},
    ],
}


# 模块加载时读取一次
INDUSTRY_FRAMEWORKS, GENERIC_FRAMEWORK = load_frameworks()


def reload_frameworks():
    """重新加载框架目录（上传自定义框架后热更新）。返回行业框架 dict。"""
    global INDUSTRY_FRAMEWORKS, GENERIC_FRAMEWORK
    INDUSTRY_FRAMEWORKS, GENERIC_FRAMEWORK = load_frameworks()
    return INDUSTRY_FRAMEWORKS


def get_framework(key: str):
    """按 key 取框架；找不到返回 None。"""
    if not key:
        return None
    if key == "generic":
        return GENERIC_FRAMEWORK
    return INDUSTRY_FRAMEWORKS.get(key)


def list_frameworks() -> list:
    """返回全部框架（行业 + 通用），供前端选择器与预览。"""
    result = [dict(fw) for fw in INDUSTRY_FRAMEWORKS.values()]
    result.append(dict(GENERIC_FRAMEWORK))
    return result


def _kw_hit(keyword: str, text: str) -> bool:
    """关键词命中判断：纯 ASCII 关键词用词边界匹配，避免 ai/it/5g 等短词误命中。"""
    if keyword.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text) is not None
    return keyword in text


def match_framework(topic: str) -> dict:
    """按课题关键词匹配最贴合的行研框架；匹配不到返回通用框架。"""
    t = (topic or "").lower()
    best = None
    best_hits = 0
    for fw in INDUSTRY_FRAMEWORKS.values():
        hits = sum(1 for k in fw.get("keywords", []) if _kw_hit(k, t))
        if hits > best_hits:
            best_hits = hits
            best = fw
    return best if best is not None else GENERIC_FRAMEWORK


def build_plan(topic: str, framework: dict = None) -> dict:
    """基于框架生成标准化研究计划（outline + research_requirements），纯规则、不依赖 LLM。

    返回的 plan_data 携带完整框架维度（指标库 / 分析模型 / 产业链 / 重点公司），
    供下游 Agent 注入 prompt。
    """
    fw = framework if framework is not None else match_framework(topic)
    outline = [s["title"] for s in fw.get("sections", [])]
    research_requirements = []
    for i, s in enumerate(fw.get("sections", []), 1):
        research_requirements.append({
            "question_id": f"q{i}",
            "text": s.get("question", ""),
            "required": True,
            "metrics": s.get("metrics", []),
            "min_evidence": s.get("min_evidence", 1),
            "min_tier": s.get("min_tier", "C"),
            "section": s.get("title", ""),
            # 数值口径契约：比例型章节自动加 0-100% 合理区间约束
            "value_spec": _build_value_spec(s.get("metrics", [])),
        })
    return {
        "topic": topic,
        "framework_name": fw.get("name", "通用"),
        "framework_key": fw.get("key", "generic"),
        "outline": outline,
        "research_requirements": research_requirements,
        # 框架 2.0 新维度
        "metrics_library": fw.get("metrics_library", {}),
        "analysis_models": fw.get("analysis_models", []),
        "supply_chain": fw.get("supply_chain", {}),
        "key_players": fw.get("key_players", []),
    }


# 有界比例型指标关键词：命中则说明该章核心指标应为 0-100% 口径（越界拦截）
# 注意：增速 / 增长率 / 毛利率 / 净利率 / 利润率可 >100% 或为负，故不在此列，避免误报
_BOUNDED_RATIO_KEYS = [
    "渗透率", "份额", "占比", "集中度", "国产化率",
    "利用率", "付费率", "复购率", "转化率",
]


def _build_value_spec(metrics: list) -> dict:
    """根据核心指标判断该章是否需要比例口径约束（0-100% 越界拦截）。"""
    if any(any(k in (m or "") for k in _BOUNDED_RATIO_KEYS) for m in metrics):
        return {"ratio_range": [0, 100], "unit": "%"}
    return None
