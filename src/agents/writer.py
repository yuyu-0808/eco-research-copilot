from openai import OpenAI
from src.utils.config import Config
from src.utils.logger import AgentLogger
from src.utils.llm_utils import call_llm


class WriterAgent:
    def __init__(self, logger: AgentLogger):
        self.logger = logger
        self.client = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url=Config.BASE_URL)
        self.model = Config.MODEL_NAME

    def _gen_structure(self, topic: str, safe_context: str) -> dict:
        """第一步：结构化提炼（短 JSON，含标题/洞察/大纲/多图表/多表格/参考文献）"""
        prompt = f"""
        你是一位【内容撰写师】。
        课题：{topic}
        【已核验的数据与信源】：
        {safe_context}

        请完成第一阶段的「结构化提炼」，直接输出纯 JSON（不要代码块标记）：

        1. report_title：一个客观、正式的学术研究报告标题，例如「泰国新能源汽车市场渗透率的演变、动因与政策影响」。禁止营销号风格（堆砌数字、反问句、感叹号、问号）。
        2. publish_date：发布日期，格式「2026年08月」。
        3. core_insights：一段 150 到 250 字的摘要，概括本报告的核心数据、关键发现、主要结论与政策含义，要有分析性论述而非简单罗列数字。
        4. outline：研究报告的 5 个章节标题，用「一、二、三...」编号。
        5. charts：2 到 4 张图。根据数据性质自选类型：时间趋势用 line，分类对比用 bar，占比结构用 pie。每张图给出 title（完整图题，如「图1：XX趋势」）、label（图例用，指标名+单位，如「销量(万辆)」）、labels（分类或年份标签）、data（数值数组）。
        6. tables：1 到 2 张表。每张表给出 title、headers（表头）、rows（数据行数组）。
        7. references：参考文献列表，只引用【已核验的数据与信源】里真实出现过的来源（标题+URL），严禁编造。

        严格按以下 JSON 结构输出：
        {{
            "report_title": "学术化标题",
            "publish_date": "2026年08月",
            "core_insights": "一段150-250字的摘要，含核心数据、关键发现、主要结论与政策含义",
            "outline": ["一、引言", "二、市场现状", "三、竞争格局", "四、趋势研判", "五、结论与建议"],
            "charts": [
                {{"type": "line", "title": "图1：销量趋势", "label": "销量(万辆)", "labels": ["2020","2021","2022","2023","2024"], "data": [1,2,3,4,5]}},
                {{"type": "bar", "title": "图2：厂商份额对比", "label": "市场份额(%)", "labels": ["A","B","C"], "data": [10,20,30]}},
                {{"type": "pie", "title": "图3：结构占比", "label": "占比(%)", "labels": ["X","Y"], "data": [60,40]}}
            ],
            "tables": [
                {{"title": "表1：政策梳理", "headers": ["政策", "年份", "内容"], "rows": [["a","b","c"],["d","e","f"]]}}
            ],
            "references": [
                {{"index": 1, "title": "信源标题", "url": "https://..."}}
            ]
        }}
        """
        return call_llm(self.client, self.model, self.logger, "内容撰写师", prompt, need_json=True)

    def _gen_body(self, topic: str, outline, safe_context: str, references, charts, tables) -> str:
        """模式一（标准）：一次性生成全文，降字数 + 强完整性约束"""
        outline_text = "\n".join(str(o) for o in (outline or []))
        ref_text = "\n".join(f"[{r.get('index')}] {r.get('title')}（{r.get('url')}）" for r in (references or []))
        chart_text = "\n".join(f"图{i}：{c.get('title')}" for i, c in enumerate(charts or [], 1)) or "（无）"
        table_text = "\n".join(f"表{i}：{t.get('title')}" for i, t in enumerate(tables or [], 1)) or "（无）"
        prompt = f"""
        你是一位【内容撰写师】。请基于以下研究大纲和已核验的数据，撰写一篇学术风格的深度研究报告正文。

        课题：{topic}
        【章节大纲】：
        {outline_text}
        【已核验的数据与信源】：
        {safe_context}
        【参考文献（正文用编号引用）】：
        {ref_text}
        【已生成的图表（正文需引用并分析）】：
        {chart_text}
        【已生成的表格（正文需引用）】：
        {table_text}

        【写作要求】：
        1. 严格按章节大纲组织，每个章节用 Markdown 的 ## 二级标题开头（如「## 一、引言」）。
        2. 每章要有分析性论证：数据解读、因果分析、横向对比、趋势研判，像学术论文正文，而非简单罗列数字。
        3. 关键数据或结论后用方括号标注引用编号，如 [1]、[2]，对应上面的参考文献；若参考文献为空则不要编造编号。
        4. 【图表穿插】在正文相关段落用文字分析图表，例如「如图1所示，销量呈现加速上升趋势」；并在希望插入图表的位置单独一行写占位符 [[CHART:编号]] 或 [[TABLE:编号]]（编号对应上面图表的序号），图表应放在与之相关的分析段落附近。
        5. 全文控制在 1500 到 2000 字之间。
        6. 【完整性（极其重要）】必须严格按大纲顺序，把全部章节的标题和正文都写完整，任何一章都不得跳过、不得只写标题不写正文。
        7. 【结论要充实】最后一个章节（结论与建议/结论与政策建议）必须写得充分：总结核心发现时要引用具体数据 [n]，政策建议要分层（如企业层面、政府层面）并给出可操作的具体措施，该章节单独不少于 300 字。
        8. 直接输出 Markdown 正文，不要输出 JSON、不要代码块标记、不要重复报告标题。

        请开始撰写正文：
        """
        return call_llm(self.client, self.model, self.logger, "内容撰写师", prompt, need_json=False, temperature=0.7)

    def _gen_body_deep(self, topic: str, outline, safe_context: str, references, charts, tables) -> str:
        """模式二（深度）：分章生成，每章一次请求，内容更充实、不易截断"""
        ref_text = "\n".join(f"[{r.get('index')}] {r.get('title')}（{r.get('url')}）" for r in (references or []))
        chart_text = "\n".join(f"图{i}：{c.get('title')}" for i, c in enumerate(charts or [], 1)) or "（无）"
        table_text = "\n".join(f"表{i}：{t.get('title')}" for i, t in enumerate(tables or [], 1)) or "（无）"
        outline = outline or ["一、引言", "二、正文", "三、结论与建议"]
        sections = []
        for i, sec in enumerate(outline, 1):
            self.logger.log_event("内容撰写师", "ACTION", f"深度模式：撰写第 {i}/{len(outline)} 章「{sec}」...")
            prompt = f"""
            你是一位【内容撰写师】。请撰写研究报告的【{sec}】这一章节。

            课题：{topic}
            【已核验的数据与信源】：
            {safe_context}
            【参考文献（正文用编号引用）】：
            {ref_text}
            【可用图表（需引用时用占位符）】：
            {chart_text}
            {table_text}

            【写作要求】：
            1. 用 Markdown 的 ## 二级标题「## {sec}」作为本章开头。
            2. 本章要有分析性论证：数据解读、因果分析、横向对比、趋势研判，像学术论文正文。
            3. 关键数据或结论后用方括号标注引用编号 [n]；可引用图表，用 [[CHART:编号]] / [[TABLE:编号]] 占位符。
            4. 本章 400 到 600 字。
            5. 只输出本章内容，不要输出 JSON、不要代码块标记、不要其他章节。

            请撰写【{sec}】这一章：
            """
            section = call_llm(self.client, self.model, self.logger, "内容撰写师", prompt, need_json=False, temperature=0.7)
            sections.append(section.strip())
        return "\n\n".join(sections)

    def analyze(self, plan_data: dict, verified_context: str) -> dict:
        topic = plan_data.get("topic")
        mode_label = "深度分章" if Config.REPORT_MODE == "deep" else "标准"
        self.logger.log_event("内容撰写师", "START", f"开始内容撰写（结构化提炼 + 正文撰写[{mode_label}模式]）")

        # 截断超长上下文，防止撑爆 Token 上限
        safe_context = verified_context[:5000] if verified_context else "（无可用底层数据）"

        # 第一步：结构化提炼（标题/洞察/大纲/多图表/多表格/参考文献）
        structure = self._gen_structure(topic, safe_context)
        self.logger.log_event(
            "内容撰写师", "SUCCESS",
            f"结构化提炼完成：{len(structure.get('charts', []))} 张图、{len(structure.get('tables', []))} 张表"
        )

        # 第二步：正文撰写（标准一次性 / 深度分章）
        if Config.REPORT_MODE == "deep":
            markdown_report = self._gen_body_deep(
                topic,
                structure.get("outline", []),
                safe_context,
                structure.get("references", []),
                structure.get("charts", []),
                structure.get("tables", []),
            )
            self.logger.log_event("内容撰写师", "SUCCESS", "深度模式正文撰写完成（分章生成）")
        else:
            markdown_report = self._gen_body(
                topic,
                structure.get("outline", []),
                safe_context,
                structure.get("references", []),
                structure.get("charts", []),
                structure.get("tables", []),
            )
            self.logger.log_event("内容撰写师", "SUCCESS", "标准模式正文撰写完成")

        return {
            "report_title": structure.get("report_title", ""),
            "publish_date": structure.get("publish_date", ""),
            "core_insights": structure.get("core_insights", ""),
            "markdown_report": markdown_report,
            "charts": structure.get("charts", []),
            "tables": structure.get("tables", []),
            "references": structure.get("references", []),
        }
