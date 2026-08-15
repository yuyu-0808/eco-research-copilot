"""FastAPI 后端入口：组装 API 路由 + WebSocket + CORS + 鉴权 + 统一异常处理。

启动：uvicorn server.main:app --reload
Swagger 文档：http://localhost:8000/docs
"""

import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server.api import projects, research, review, metrics, settings, stats, frameworks
from server import ws
from server.response import ok, fail, code_for_status, CODE_UNAUTHORIZED, CODE_INTERNAL
from server.security import access_token, verify_token

app = FastAPI(title="Eco-Research Copilot API", version="1.0.0")

# 开发期全开 CORS，供 React（Vite dev server）跨域访问；上线后收紧 allow_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------
# 全局异常处理：统一 code/data/message，保留错误现场与错误栈
# ----------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return fail(exc.status_code, code_for_status(exc.status_code), str(exc.detail))


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    # 保留完整错误栈到后端日志，前端只返回不泄露内部细节的通用提示
    traceback.print_exc()
    return fail(500, CODE_INTERNAL, "服务器内部错误，请查看后端日志")


# ----------------------------------------------------------------------
# 单 Token 鉴权中间件：/api/* 默认鉴权，白名单放行
# ----------------------------------------------------------------------
_PUBLIC_PATHS = {"/api/health", "/api/auth/bootstrap"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith(("/docs", "/openapi.json", "/redoc")):
        return await call_next(request)
    if path.startswith("/api/") and path not in _PUBLIC_PATHS:
        # 支持 Authorization: Bearer <token> 头 或 ?token= 查询参数（下载/WS 用）
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else request.query_params.get("token", "")
        if not verify_token(token):
            return fail(401, CODE_UNAUTHORIZED, "未授权：缺少或无效的访问令牌")
    return await call_next(request)


app.include_router(projects.router)
app.include_router(research.router)
app.include_router(review.router)
app.include_router(metrics.router)
app.include_router(settings.router)
app.include_router(stats.router)
app.include_router(frameworks.router)
app.include_router(ws.router)


@app.get("/api/health")
def health():
    return ok({"status": "ok", "service": "eco-research-copilot"})


@app.get("/api/auth/bootstrap")
def bootstrap():
    """前端启动时获取访问令牌（唯一免鉴权入口）。"""
    return ok({"token": access_token()})
