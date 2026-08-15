"""WebSocket：把项目进度（阶段状态 / 日志 / 状态变化）实时推给前端。

实现方式：轮询项目目录下的 checkpoint.json + run_log.jsonl（复用 helpers 纯函数），
无需改动核心逻辑；前端断线重连后重新拉全量状态即可。
"""

import asyncio
import json
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.ui.helpers import read_log, load_checkpoint, derive_stages, PROJECTS_DIR
from server.security import verify_token

router = APIRouter()

_POLL_SECONDS = 1.0


@router.websocket("/ws/projects/{project_id}")
async def ws_project(websocket: WebSocket, project_id: str):
    # 鉴权：token 通过查询参数传入（WebSocket 握手无法带自定义 header）
    token = websocket.query_params.get("token", "")
    if not verify_token(token):
        await websocket.close(code=4001)
        return

    await websocket.accept()
    d = os.path.join(PROJECTS_DIR, project_id)
    sent_logs = 0  # 已推送的日志条数（增量推送）

    try:
        while True:
            entries = read_log(d)
            ck = load_checkpoint(d) or {}

            new_logs = entries[sent_logs:]
            sent_logs = len(entries)

            payload = {
                "type": "progress",
                "project_id": project_id,
                "status": ck.get("status"),
                "current_stage": ck.get("current_stage"),
                "review_stage": ck.get("review_stage"),
                "stages": derive_stages(entries) if entries else ["pending"] * 6,
                "new_logs": new_logs,
            }
            await websocket.send_text(json.dumps(payload, ensure_ascii=False, default=str))

            if ck.get("status") in ("completed", "failed"):
                break
            await asyncio.sleep(_POLL_SECONDS)
    except WebSocketDisconnect:
        pass
