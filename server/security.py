"""本地单 Token 鉴权。

后端首次启动时自动生成随机 Secret Token，写入 .env（ACCESS_TOKEN 字段），
前端通过 /api/auth/bootstrap 获取后自动携带。适用于本地单机单用户开源工具：
不做用户名密码 / 多用户登录体系，避免过度设计。

安全提示：若把服务暴露到公网，该 Token 是唯一防护，禁止泄露。
"""

import os
import secrets

from dotenv import load_dotenv, set_key

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_PATH = os.path.join(_ROOT, ".env")
_TOKEN_ENV = "ACCESS_TOKEN"

_token = None


def access_token() -> str:
    """获取（或首次生成）访问令牌。惰性生成，启动后首次访问时落盘。"""
    global _token
    if _token is not None:
        return _token
    load_dotenv(override=True)
    token = os.getenv(_TOKEN_ENV, "")
    if not token:
        token = secrets.token_hex(32)
        try:
            set_key(_ENV_PATH, _TOKEN_ENV, token)
        except OSError:
            pass  # 写盘失败不阻断启动，令牌仍在本进程内有效
    _token = token
    return _token


def verify_token(token: str) -> bool:
    """校验令牌是否匹配（常量时间比较，防时序攻击）。"""
    if not token:
        return False
    return secrets.compare_digest(token, access_token())
