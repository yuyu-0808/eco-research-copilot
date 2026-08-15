import os
from dotenv import load_dotenv

# 加载根目录下的 .env 文件
load_dotenv()

class Config:
    # 核心大模型配置
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com")
    MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")

    # 容错降级：备用模型（主模型重试耗尽后自动切换；留空则不启用）
    BACKUP_MODEL = os.getenv("BACKUP_MODEL", "")

    # 搜索与工具配置 (支持灵活切换)
    SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "tavily")  # 可选 'tavily' 或 'ddg'
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

    # 业务边界控制
    MAX_COLLECT_ROUNDS = int(os.getenv("MAX_COLLECT_ROUNDS", "3"))  # 信源检索→事实稽核 最大循环次数
    WRITE_AUDIT_ROUNDS = int(os.getenv("WRITE_AUDIT_ROUNDS", "2"))  # 内容撰写→逻辑稽核 交叉校验最大轮数
    EVIDENCE_BATCH_SIZE = int(os.getenv("EVIDENCE_BATCH_SIZE", "5"))  # 事实稽核官分批提炼：每批证据条数（防长 prompt 触发思维链爆 token）
    EVIDENCE_PER_SOURCE_MAX = int(os.getenv("EVIDENCE_PER_SOURCE_MAX", "2"))  # 同源证据聚合：同一信源同一章节最多保留条数（砍冗余拆分，控制证据总量）
    EVIDENCE_PER_SECTION_MAX = int(os.getenv("EVIDENCE_PER_SECTION_MAX", "8"))  # 单章证据上限：达标后不再为该章检索，避免章节间证据失衡
    REQUIRE_STRICT_EVIDENCE = os.getenv("REQUIRE_STRICT_EVIDENCE", "True").lower() in ("true", "1")  # 是否开启质量门禁

    # 新增：API 速率限制配置（防止频繁调用触发限流）
    API_RATE_LIMIT_SECONDS = int(os.getenv("API_RATE_LIMIT_SECONDS", "5"))  # 每次API调用最小间隔秒数
    MAX_RETRY_WAIT_SECONDS = int(os.getenv("MAX_RETRY_WAIT_SECONDS", "30"))  # 最大重试等待时间

    # 报告正文生成模式：standard（一次性生成，快）/ deep（分章生成，更充实）
    REPORT_MODE = os.getenv("REPORT_MODE", "standard")

    # 交付格式（渲染器插件）：docx / markdown
    REPORT_FORMAT = os.getenv("REPORT_FORMAT", "docx")

    # 阶段级自动重试次数：单个阶段因超时 / API 异常失败后自动重试 N 次（在 call_llm 内部重试之上再加一层兜底）
    STAGE_RETRY = int(os.getenv("STAGE_RETRY", "2"))

    # 人机协同模式：auto（全自动，默认）/ manual（三阶段确认：框架→素材→终稿）
    REVIEW_MODE = os.getenv("REVIEW_MODE", "auto")

    # 报告模板自定义（Word / PDF 通用）
    REPORT_DISCLAIMER = os.getenv("REPORT_DISCLAIMER", "")  # 免责声明（空 = 用内置默认）
    REPORT_HEADER = os.getenv("REPORT_HEADER", "")          # 页眉文本（空 = 用报告标题）
    REPORT_FOOTER = os.getenv("REPORT_FOOTER", "")          # 页脚文本（空 = 用自动页码）
    REPORT_LOGO = os.getenv("REPORT_LOGO", "")              # Logo 图片路径（空 = 不显示）

    @classmethod
    def validate(cls):
        """启动时自检密钥是否完整"""
        if not cls.DEEPSEEK_API_KEY:
            raise ValueError("[ERROR] 致命错误: DEEPSEEK_API_KEY 未配置，请检查 .env 文件！")
