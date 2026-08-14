from openai import OpenAI
from src.utils.config import Config
from src.utils.logger import AgentLogger
from src.utils.llm_utils import call_llm


class WriterAgent:
    def __init__(self, logger: AgentLogger):
        self.logger = logger
        self.client = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url=Config.BASE_URL)
        self.model = Config.MODEL_NAME

    def write_report(self, topic: str, structure: dict, safe_context: str, feedback: str = None) -> str:
        """根据结构化提炼结果，撰写研究报告正文（标准一次性 / 深度分章）。feedback 为稽核官打回意见。"""
        mode_label = "深度分章" if Config.REPORT_MODE == "deep" else "标准"
        suffix = "（修订稿）" if feedback else ""
        self.logger.log_event("内容撰写师", "START", f"开始撰写正文[{mode_label}模式]{suffix}")

        outline = structure.get("outline", [])
        references = structure.get("references", [])
        charts = structure.get("charts", [])
        tables = structure.get("tables", [])

        if Config.REPORT_MODE == "deep":
            markdown_report = self._gen_body_deep(topic, outline, safe_context, references, charts, tables, feedback)
            self.logger.log_event("内容撰写师", "SUCCESS", "深度模式正文撰写完成（分章生成）")
        else:
            markdown_report = self._gen_body(topic, outline, safe_context, references, charts, tables, feedback)
            self.logger.log_event("内容撰写师", "SUCCESS", "标准模式正文撰写完成")
        return markdown_report

    def _gen_body(self, topic: str, outline, safe_context: str, references, charts, tables, feedback: str = None) -> str:
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
        if feedback:
            prompt += f"\n\n【重要：上一版被事实稽核官驳回，修改意见如下，请据此修正相关问题】\n{feedback}\n"
        return call_llm(self.client, self.model, self.logger, "内容撰写师", prompt, need_json=False, temperature=0.7)

    def _gen_body_deep(self, topic: str, outline, safe_context: str, references, charts, tables, feedback: str = None) -> str:
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
            if feedback:
                prompt += f"\n\n【重要：上一版被事实稽核官驳回，修改意见如下，请据此修正】\n{feedback}\n"
            section = call_llm(self.client, self.model, self.logger, "内容撰写师", prompt, need_json=False, temperature=0.7)
            sections.append(section.strip())
        return "\n\n".join(sections)
