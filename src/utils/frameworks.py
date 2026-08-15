"""行研标准化框架引擎。

内置行业共识的研究框架：Agent 只负责往对应章节填充证据与内容，
保证输出结构 100% 符合行研规范。

设计要点：
- 每个框架按「行业概览 → 产业链 → 竞争格局 → 政策环境 → 趋势研判」五段式组织；
- 每章带「必答问题 + 核心指标 + 最少证据数 + 最低信源等级」，
  供代码校验器（validator）在采集后逐章核对；
- build_plan 纯规则（不依赖 LLM），架构师在此基础上才做可选微调。
"""

# 标准行研框架库
# 每个框架：
#   name     行业类型名
#   keywords 课题匹配关键词（命中越多越贴合）
#   sections 标准章节，每章含：
#     title        章节标题（即报告大纲）
#     question     该章必答的核心问题
#     metrics      该章需采集的核心指标（代码校验用）
#     min_evidence 该章最少需要的有效证据条数
#     min_tier     该章核心指标要求的最低信源等级

INDUSTRY_FRAMEWORKS = {
    "new_energy": {
        "key": "new_energy",
        "name": "新能源 / 先进制造",
        "keywords": [
            "新能源", "锂电", "锂电池", "光伏", "储能", "风电", "氢能",
            "半导体", "芯片", "集成电路", "eda", "汽车", "整车", "智能驾驶",
            "动力电池", "制造", "工业", "机器人", "充电", "电池",
        ],
        "sections": [
            {"title": "一、行业概览", "question": "行业市场规模、同比增速、渗透率等基础量", "metrics": ["市场规模", "同比增速", "渗透率"], "min_evidence": 2, "min_tier": "B"},
            {"title": "二、产业链分析", "question": "产业链上下游结构及关键环节价值分布", "metrics": ["产业链环节", "成本占比", "关键环节格局"], "min_evidence": 2, "min_tier": "C"},
            {"title": "三、竞争格局", "question": "市场集中度、头部厂商份额与竞争壁垒", "metrics": ["市场集中度", "头部厂商份额", "竞争壁垒"], "min_evidence": 2, "min_tier": "B"},
            {"title": "四、政策环境", "question": "相关政策、补贴细则与监管趋势", "metrics": ["政策名称", "补贴标准", "监管要求"], "min_evidence": 2, "min_tier": "A"},
            {"title": "五、趋势研判与投资机会", "question": "行业发展趋势、风险与投资机会", "metrics": ["发展趋势", "风险点", "投资机会"], "min_evidence": 1, "min_tier": "C"},
        ],
    },
    "tmt": {
        "key": "tmt",
        "name": "TMT / 互联网科技",
        "keywords": [
            "互联网", "软件", "saas", "云计算", "ai", "人工智能", "大模型",
            "游戏", "电商", "社交", "广告", "数据", "5g", "通信", "it", "科技",
            "数字化", "算力",
        ],
        "sections": [
            {"title": "一、行业概览", "question": "行业市场规模、用户规模、增速", "metrics": ["市场规模", "用户规模", "同比增速"], "min_evidence": 2, "min_tier": "B"},
            {"title": "二、商业模式与价值链", "question": "商业模式、收入结构、价值链分布", "metrics": ["商业模式", "收入结构", "价值链"], "min_evidence": 2, "min_tier": "C"},
            {"title": "三、竞争格局", "question": "市场份额、头部玩家、竞争壁垒", "metrics": ["市场份额", "头部玩家", "竞争壁垒"], "min_evidence": 2, "min_tier": "B"},
            {"title": "四、政策与监管", "question": "监管政策、数据合规、行业规范", "metrics": ["监管政策", "合规要求"], "min_evidence": 2, "min_tier": "A"},
            {"title": "五、趋势研判与投资机会", "question": "技术趋势、风险与投资机会", "metrics": ["技术趋势", "风险点", "投资机会"], "min_evidence": 1, "min_tier": "C"},
        ],
    },
    "consumer": {
        "key": "consumer",
        "name": "大消费 / 消费服务",
        "keywords": [
            "消费", "零售", "食品", "饮料", "白酒", "家电", "服装", "美妆",
            "医药", "医疗", "旅游", "餐饮", "教育", "地产", "家居", "免税",
            "化妆品", "品牌",
        ],
        "sections": [
            {"title": "一、行业概览", "question": "市场规模、增速、渗透率", "metrics": ["市场规模", "同比增速", "渗透率"], "min_evidence": 2, "min_tier": "B"},
            {"title": "二、需求与消费结构", "question": "需求驱动、消费结构、用户画像", "metrics": ["需求驱动", "消费结构"], "min_evidence": 2, "min_tier": "C"},
            {"title": "三、竞争格局", "question": "市场集中度、品牌格局、渠道", "metrics": ["市场集中度", "品牌份额", "渠道结构"], "min_evidence": 2, "min_tier": "B"},
            {"title": "四、政策与宏观环境", "question": "相关政策、宏观环境、监管", "metrics": ["政策", "宏观环境"], "min_evidence": 2, "min_tier": "A"},
            {"title": "五、趋势研判与投资机会", "question": "消费趋势、风险与投资机会", "metrics": ["消费趋势", "风险点", "投资机会"], "min_evidence": 1, "min_tier": "C"},
        ],
    },
}

# 通用框架（课题匹配不到任何行业时兜底）
GENERIC_FRAMEWORK = {
    "key": "generic",
    "name": "通用行业研究",
    "sections": [
        {"title": "一、行业概览", "question": "市场规模、增速、现状", "metrics": ["市场规模", "增速"], "min_evidence": 2, "min_tier": "B"},
        {"title": "二、产业链 / 价值链分析", "question": "产业链结构、价值分布", "metrics": ["产业链", "价值分布"], "min_evidence": 2, "min_tier": "C"},
        {"title": "三、竞争格局", "question": "市场份额、竞争壁垒", "metrics": ["市场份额", "竞争壁垒"], "min_evidence": 2, "min_tier": "B"},
        {"title": "四、政策环境", "question": "政策、监管", "metrics": ["政策", "监管"], "min_evidence": 2, "min_tier": "A"},
        {"title": "五、趋势研判与投资机会", "question": "趋势、风险、机会", "metrics": ["趋势", "风险", "机会"], "min_evidence": 1, "min_tier": "C"},
    ],
}


def match_framework(topic: str) -> dict:
    """按课题关键词匹配最贴合的行研框架；匹配不到返回通用框架。"""
    t = (topic or "").lower()
    best = None
    best_hits = 0
    for fw in INDUSTRY_FRAMEWORKS.values():
        hits = sum(1 for k in fw["keywords"] if k in t)
        if hits > best_hits:
            best_hits = hits
            best = fw
    return best if best is not None else GENERIC_FRAMEWORK


def build_plan(topic: str, framework: dict = None) -> dict:
    """基于框架生成标准化研究计划（outline + research_requirements），纯规则、不依赖 LLM。

    每个必答问题附带「数值口径契约」（value_spec）：
    - ratio_range：比例型指标（渗透率/增速/份额等）的合理区间，越界将被代码校验器拦截；
    - unit：核心指标单位提示。

    这是「先定规则再做」的关键：契约在研究开始前就固定下来，后续 Agent 只能在契约内工作。
    """
    fw = framework if framework is not None else match_framework(topic)
    outline = [s["title"] for s in fw["sections"]]
    research_requirements = []
    for i, s in enumerate(fw["sections"], 1):
        research_requirements.append({
            "question_id": f"q{i}",
            "text": s["question"],
            "required": True,
            "metrics": s["metrics"],
            "min_evidence": s["min_evidence"],
            "min_tier": s["min_tier"],
            "section": s["title"],
            # 数值口径契约：比例型章节自动加 0-100% 合理区间约束
            "value_spec": _build_value_spec(s["metrics"]),
        })
    return {
        "topic": topic,
        "framework_name": fw["name"],
        "framework_key": fw.get("key", "generic"),
        "outline": outline,
        "research_requirements": research_requirements,
    }


# 比例型指标关键词：命中则说明该章核心指标应为 0-100% 口径
_RATIO_METRIC_KEYS = [
    "渗透率", "增速", "增长率", "份额", "占比", "集中度",
    "毛利率", "净利率", "利润率", "复购率", "转化率", "国产化率",
]


def _build_value_spec(metrics: list) -> dict:
    """根据核心指标判断该章是否需要比例口径约束（0-100% 越界拦截）。"""
    if any(any(k in (m or "") for k in _RATIO_METRIC_KEYS) for m in metrics):
        return {"ratio_range": [0, 100], "unit": "%"}
    return None
