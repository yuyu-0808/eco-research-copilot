import re
from openai import OpenAI
from src.utils.config import Config
from src.utils.logger import AgentLogger
from src.utils.llm_utils import call_llm
from src.tools.docx_writer import DocxWriter


class FormatterAgent:
    def __init__(self, logger: AgentLogger):
        self.logger = logger
        self.client = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url=Config.BASE_URL)
        self.model = Config.MODEL_NAME

    def _polish(self, markdown_report: str) -> str:
        """文字润色：让语言更专业流畅，适当充实分析性表述（保留占位符/引用/标题）"""
        if not markdown_report:
            return markdown_report
        placeholders = re.findall(r'\[\[(?:CHART|TABLE):\d+\]\]', markdown_report)
        prompt = f"""
        你是一位资深文字编辑。请对下面这篇研究报告正文进行润色：

        1. 语言更专业、流畅、书面化，用词准确。
        2. 可适当补充分析性表述，让论证更充分（但不要引入新的事实或编造数据）。
        3. 严格原样保留：章节标题（## 开头的行）、图表占位符 [[CHART:n]]/[[TABLE:n]]、引用编号 [n]、图表编号（如图1/表1）。
        4. 保持原有章节结构，不要增删章节。
        5. 直接输出润色后的完整 Markdown 正文，不要任何解释、不要代码块标记。

        待润色正文：
        {markdown_report}
        """
        polished = call_llm(
            self.client, self.model, self.logger, "Agent5_Formatter",
            prompt, need_json=False, temperature=0.5
        )
        # 保护：润色后若丢失图表占位符，回退原文，避免图表穿插失效
        polished_placeholders = re.findall(r'\[\[(?:CHART|TABLE):\d+\]\]', polished or "")
        if placeholders and set(polished_placeholders) != set(placeholders):
            self.logger.log_event("Agent5_Formatter", "WARNING", "润色丢失图表占位符，回退原文")
            return markdown_report
        return polished

    def format_delivery(self, project_name: str, ai_data: dict) -> str:
        """文字润色 + 排版，输出最终 Word 文档"""
        self.logger.log_event("Agent5_Formatter", "START", "开始文字润色与排版...")

        try:
            # 1. 文字润色
            ai_data["markdown_report"] = self._polish(ai_data.get("markdown_report", ""))
            self.logger.log_event("Agent5_Formatter", "SUCCESS", "文字润色完成")

            # 2. 排版
            writer = DocxWriter(project_name=project_name)
            docx_path = writer.generate_report(ai_data)

            self.logger.log_event("Agent5_Formatter", "SUCCESS", f"研报生成完毕！文件保存在: {docx_path}")
            return docx_path

        except Exception as e:
            self.logger.log_event("Agent5_Formatter", "FAILED", f"Word 引擎注入失败: {e}")
            raise e
