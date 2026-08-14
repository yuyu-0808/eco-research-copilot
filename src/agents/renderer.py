import os
import re
from openai import OpenAI
from src.utils.config import Config
from src.utils.logger import AgentLogger
from src.utils.llm_utils import call_llm
from src.tools.docx_writer import DocxWriter


class RendererAgent:
    def __init__(self, logger: AgentLogger):
        self.logger = logger
        self.client = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url=Config.BASE_URL)
        self.model = Config.MODEL_NAME

    def generate_structure(self, topic: str, safe_context: str) -> dict:
        """结构化提炼：标题/摘要/大纲/图表/表格/参考文献（正文撰写前的结构定义）。"""
        self.logger.log_event("结构提炼", "START", "开始结构化提炼（标题/图表/表格/参考文献）")
        prompt = f"""
        你是一位【交付渲染官】，负责研究报告的结构化提炼。
        课题：{topic}
        【已核验的数据与信源】：
        {safe_context}

        请完成「结构化提炼」，直接输出纯 JSON（不要代码块标记）：

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
        structure = call_llm(self.client, self.model, self.logger, "结构提炼", prompt, need_json=True)
        self.logger.log_event(
            "结构提炼", "SUCCESS",
            f"结构化提炼完成：{len(structure.get('charts', []))} 张图、{len(structure.get('tables', []))} 张表"
        )
        return structure

    def _polish(self, markdown_report: str) -> str:
        """文字润色：让语言更专业流畅，适当充实分析性表述（保留占位符/引用/标题）"""
        if not markdown_report:
            return markdown_report
        placeholders = re.findall(r'\[\[(?:CHART|TABLE):\d+\]\]', markdown_report)
        prompt = f"""
        你是一位【交付渲染官】。请对下面这篇研究报告正文进行润色：

        1. 语言更专业、流畅、书面化，用词准确。
        2. 可适当补充分析性表述，让论证更充分（但不要引入新的事实或编造数据）。
        3. 严格原样保留：章节标题（## 开头的行）、图表占位符 [[CHART:n]]/[[TABLE:n]]、引用编号 [n]、图表编号（如图1/表1）。
        4. 保持原有章节结构，不要增删章节。
        5. 直接输出润色后的完整 Markdown 正文，不要任何解释、不要代码块标记。

        待润色正文：
        {markdown_report}
        """
        polished = call_llm(
            self.client, self.model, self.logger, "交付渲染官",
            prompt, need_json=False, temperature=0.5
        )
        # 保护：润色后若丢失图表占位符，回退原文，避免图表穿插失效
        polished_placeholders = re.findall(r'\[\[(?:CHART|TABLE):\d+\]\]', polished or "")
        if placeholders and set(polished_placeholders) != set(placeholders):
            self.logger.log_event("交付渲染官", "WARNING", "润色丢失图表占位符，回退原文")
            return markdown_report
        return polished

    def format_delivery(self, project_name: str, ai_data: dict) -> str:
        """文字润色 + 排版，输出最终 Word 文档；排版失败时降级输出 Markdown 并标记风险。"""
        self.logger.log_event("交付渲染官", "START", "开始内容渲染与多格式排版...")

        try:
            # 1. 文字润色
            ai_data["markdown_report"] = self._polish(ai_data.get("markdown_report", ""))
            self.logger.log_event("交付渲染官", "SUCCESS", "文字润色完成")

            # 2. 排版
            writer = DocxWriter(project_name=project_name)
            docx_path = writer.generate_report(ai_data)

            self.logger.log_event("交付渲染官", "SUCCESS", f"研报生成完毕！文件保存在: {docx_path}")
            return docx_path

        except Exception as e:
            # 排版降级：Word 生成失败时，退回输出 Markdown 文件，不阻断流水线
            self.logger.log_event("交付渲染官", "WARNING", f"Word 排版失败，降级输出 Markdown: {e}")
            md_path = self._save_markdown(project_name, ai_data)
            self.logger.log_event("交付渲染官", "WARNING", f"已降级输出 Markdown（风险标记）: {md_path}")
            return md_path

    def _save_markdown(self, project_name: str, ai_data: dict) -> str:
        """排版降级兜底：把 Markdown 正文直接落盘为 .md 文件。"""
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        project_dir = os.path.join(root, "projects", project_name)
        os.makedirs(project_dir, exist_ok=True)
        md_path = os.path.join(project_dir, "05_final_report.md")
        title = ai_data.get("report_title", "调研报告")
        content = ai_data.get("markdown_report", "")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n{content}")
        return md_path
