"""统一响应信封与错误码。

所有 JSON 接口统一返回 {code, data, message} 三元组：
- code=0 表示成功，data 为业务数据；
- code!=0 表示失败，message 为可读错误信息，data 为补充数据（可为 null）。

错误码分段：
- 0     成功
- 1xxx 客户端参数 / 资源错误（400/404/409/422）
- 2xxx 鉴权错误（401/403）
- 5xxx 服务器内部错误（500）
"""

from fastapi.responses import JSONResponse

CODE_OK = 0
CODE_BAD_REQUEST = 1001      # 参数错误 / 校验失败
CODE_NOT_FOUND = 1002        # 资源不存在
CODE_CONFLICT = 1003         # 资源冲突（重复提交等）
CODE_UNAUTHORIZED = 2001     # 未授权 / 令牌无效
CODE_INTERNAL = 5000         # 服务器内部错误

_HTTP_TO_CODE = {
    400: CODE_BAD_REQUEST,
    404: CODE_NOT_FOUND,
    409: CODE_CONFLICT,
    401: CODE_UNAUTHORIZED,
    403: CODE_UNAUTHORIZED,
    422: CODE_BAD_REQUEST,
}


def ok(data=None, message: str = "ok") -> dict:
    """成功响应信封。"""
    return {"code": CODE_OK, "data": data, "message": message}


def fail(status_code: int, code: int, message: str, data=None) -> JSONResponse:
    """失败响应信封（携带对应 HTTP 状态码）。"""
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "data": data, "message": message},
    )


def code_for_status(status_code: int) -> int:
    """把 HTTP 状态码映射为业务错误码。"""
    return _HTTP_TO_CODE.get(status_code, CODE_INTERNAL)
