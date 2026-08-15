"""行业框架 API：列表 / 预览 / 上传自定义 YAML。"""

import os
import re

import yaml
from fastapi import APIRouter, HTTPException

from src.utils.frameworks import list_frameworks, reload_frameworks, _FRAMEWORKS_DIR
from server.response import ok

router = APIRouter(prefix="/api/frameworks", tags=["frameworks"])

_CUSTOM_DIR = os.path.join(_FRAMEWORKS_DIR, "custom")
_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@router.get("")
def get_frameworks():
    """返回全部行业框架（含通用），供前端选择器与章节预览。"""
    return ok({"frameworks": list_frameworks()})


@router.post("/upload")
def upload_framework(payload: dict = None):
    """上传自定义行业框架 YAML，保存到 frameworks/custom/ 并热更新。"""
    text = (payload or {}).get("yaml", "")
    text = (text or "").strip()
    if not text:
        raise HTTPException(400, "yaml 内容不能为空")

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise HTTPException(400, f"YAML 解析失败：{e}")

    if not isinstance(data, dict):
        raise HTTPException(400, "框架须为 YAML 映射（key / name / sections）")
    key = str(data.get("key") or "").strip()
    name = str(data.get("name") or "").strip()
    sections = data.get("sections")
    if not key or not name:
        raise HTTPException(400, "缺少 key 或 name")
    if not _KEY_RE.match(key):
        raise HTTPException(400, "key 只能包含字母、数字、下划线、连字符")
    if key == "generic":
        raise HTTPException(400, "key 不能为 generic（系统保留字）")
    if not isinstance(sections, list) or not sections:
        raise HTTPException(400, "sections 须为非空列表")
    for i, s in enumerate(sections, 1):
        if not isinstance(s, dict) or not s.get("title") or not s.get("question"):
            raise HTTPException(400, f"第 {i} 章缺少 title 或 question")

    os.makedirs(_CUSTOM_DIR, exist_ok=True)
    path = os.path.join(_CUSTOM_DIR, f"{key}.yaml")
    # 复用原始 YAML 文本落盘（保留注释与结构）
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

    reload_frameworks()
    return ok({"key": key, "name": name, "sections": len(sections)})
