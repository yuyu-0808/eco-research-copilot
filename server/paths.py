"""项目路径安全解析：统一校验 project_id 与导出文件路径，防止路径穿越。

四个 API 模块（projects / research / review / export）都曾各自实现相同的 `_dir()`，
对 project_id 完全不做校验，导致 `../` 可删除仓库根目录、篡改 docx_path 可任意读文件。
此处收敛为单一实现，供各模块复用。
"""

import os

from fastapi import HTTPException

from src.ui.helpers import PROJECTS_DIR


def resolve_project_dir(project_id: str) -> str:
    """校验并解析项目目录路径，防止 `../` 路径穿越删除 / 读取任意文件。"""
    if not project_id or not isinstance(project_id, str):
        raise HTTPException(400, "非法的项目 ID")
    if (
        os.path.isabs(project_id)
        or ".." in project_id
        or "/" in project_id
        or "\\" in project_id
    ):
        raise HTTPException(400, "非法的项目 ID")

    d = os.path.join(PROJECTS_DIR, project_id)

    # 防御性兜底：解析后的真实路径必须仍位于项目目录内
    real_root = os.path.realpath(PROJECTS_DIR)
    real_d = os.path.realpath(d)
    if real_d != real_root and not real_d.startswith(real_root + os.sep):
        raise HTTPException(400, "非法的项目 ID")

    if not os.path.isdir(d):
        raise HTTPException(404, f"项目不存在: {project_id}")
    return d


def resolve_report_file(project_dir: str, file_path: str) -> str:
    """校验导出文件路径必须位于项目目录内，防止任意文件读取。

    返回解析后的真实路径（绝对路径）。
    """
    if not file_path:
        raise HTTPException(404, "报告文件不存在")

    real_dir = os.path.realpath(project_dir)
    real_file = os.path.realpath(file_path)
    if real_file != real_dir and not real_file.startswith(real_dir + os.sep):
        raise HTTPException(400, "非法的文件路径")
    return real_file
