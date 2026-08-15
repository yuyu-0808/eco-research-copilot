"""可视化配置中心 API：读取 / 更新系统参数（写入 .env + 内存即时生效）。

「立即生效」原理：把新值同时写入 .env（持久化，重启后仍生效）与 Config 类属性
（当前进程内即时生效，下一次任务即用新配置）。API 密钥只返回「是否已配置」，
不返回明文；仅当提交了非空新密钥时才更新。
"""

import os

from fastapi import APIRouter, HTTPException
from dotenv import set_key

from src.utils.config import Config
from server.response import ok

router = APIRouter(prefix="/api/settings", tags=["settings"])

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ENV_PATH = os.path.join(_ROOT, ".env")

# 前端字段名 -> (Config 属性名 / 环境变量名, 类型转换：str/int/"bool")
_FIELDS = {
    "model_name": ("MODEL_NAME", str),
    "backup_model": ("BACKUP_MODEL", str),
    "base_url": ("BASE_URL", str),
    "search_provider": ("SEARCH_PROVIDER", str),
    "max_collect_rounds": ("MAX_COLLECT_ROUNDS", int),
    "write_audit_rounds": ("WRITE_AUDIT_ROUNDS", int),
    "require_strict_evidence": ("REQUIRE_STRICT_EVIDENCE", "bool"),
    "report_mode": ("REPORT_MODE", str),
    "review_mode": ("REVIEW_MODE", str),
    "stage_retry": ("STAGE_RETRY", int),
    "report_disclaimer": ("REPORT_DISCLAIMER", str),
    "report_header": ("REPORT_HEADER", str),
    "report_footer": ("REPORT_FOOTER", str),
    "report_logo": ("REPORT_LOGO", str),
}

# 密钥字段（明文不返回，仅返回是否已配置）
_SECRET_FIELDS = [
    ("deepseek_api_key", "DEEPSEEK_API_KEY"),
    ("tavily_api_key", "TAVILY_API_KEY"),
]


def _mask(key: str) -> str:
    """密钥脱敏：保留前 4 位 + 后 4 位，中间打码。"""
    if not key:
        return ''
    if len(key) <= 8:
        return '****'
    return f"{key[:4]}****{key[-4:]}"


@router.get("")
def get_settings():
    return ok({
        "model_name": Config.MODEL_NAME,
        "backup_model": Config.BACKUP_MODEL,
        "base_url": Config.BASE_URL,
        "deepseek_api_key_set": bool(Config.DEEPSEEK_API_KEY),
        "deepseek_api_key_masked": _mask(Config.DEEPSEEK_API_KEY),
        "tavily_api_key_set": bool(Config.TAVILY_API_KEY),
        "tavily_api_key_masked": _mask(Config.TAVILY_API_KEY),
        "search_provider": Config.SEARCH_PROVIDER,
        "max_collect_rounds": Config.MAX_COLLECT_ROUNDS,
        "write_audit_rounds": Config.WRITE_AUDIT_ROUNDS,
        "require_strict_evidence": Config.REQUIRE_STRICT_EVIDENCE,
        "report_mode": Config.REPORT_MODE,
        "review_mode": Config.REVIEW_MODE,
        "stage_retry": Config.STAGE_RETRY,
        "report_disclaimer": Config.REPORT_DISCLAIMER,
        "report_header": Config.REPORT_HEADER,
        "report_footer": Config.REPORT_FOOTER,
        "report_logo": Config.REPORT_LOGO,
    })


@router.put("")
def update_settings(payload: dict = None):
    payload = payload or {}
    updated = []

    # 1. API 密钥（仅当提交非空新值才更新）
    for field, attr in _SECRET_FIELDS:
        val = (payload.get(field) or "").strip()
        if val:
            set_key(_ENV_PATH, attr, val)
            setattr(Config, attr, val)
            updated.append(field)

    # 2. 普通字段
    for field, (attr, cast) in _FIELDS.items():
        if field not in payload or payload[field] is None:
            continue
        if cast == "bool":
            coerced = str(payload[field]).lower() in ("true", "1", "yes", "on")
        else:
            coerced = cast(payload[field])
        set_key(_ENV_PATH, attr, str(coerced))
        setattr(Config, attr, coerced)
        updated.append(field)

    if not updated:
        raise HTTPException(400, "没有可更新的字段")
    return ok({"updated": updated})


# 非密钥配置的默认值（与 src/utils/config.py 的代码默认保持一致；重置时写回）
_DEFAULTS = {
    "MODEL_NAME": "deepseek-chat",
    "BACKUP_MODEL": "",
    "BASE_URL": "https://api.deepseek.com",
    "SEARCH_PROVIDER": "tavily",
    "MAX_COLLECT_ROUNDS": "3",
    "WRITE_AUDIT_ROUNDS": "2",
    "REQUIRE_STRICT_EVIDENCE": "True",
    "REPORT_MODE": "standard",
    "REPORT_FORMAT": "docx",
    "STAGE_RETRY": "2",
    "REVIEW_MODE": "auto",
    "REPORT_DISCLAIMER": "",
    "REPORT_HEADER": "",
    "REPORT_FOOTER": "",
    "REPORT_LOGO": "",
}


@router.post("/reset")
def reset_settings():
    """重置所有非密钥配置到默认值（写回 .env + 内存即时生效）。"""
    updated = []
    for attr, val in _DEFAULTS.items():
        set_key(_ENV_PATH, attr, val)
        setattr(Config, attr, val)
        updated.append(attr)
    return ok({"updated": updated})
