"""FastAPI 后端入口：组装 API 路由 + WebSocket + CORS。

启动：uvicorn server.main:app --reload
Swagger 文档：http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.api import projects, research, review, metrics
from server import ws

app = FastAPI(title="Eco-Research Copilot API", version="1.0.0")

# 开发期全开 CORS，供 React（Vite dev server）跨域访问；上线后收紧 allow_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(research.router)
app.include_router(review.router)
app.include_router(metrics.router)
app.include_router(ws.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "eco-research-copilot"}
