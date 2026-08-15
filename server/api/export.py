"""交付物导出 API：Word / PDF / Markdown 一键下载。

从 result.json 读取报告内容，Word 直接返回已生成的 docx；Markdown 与 PDF
在导出时动态生成并落盘到项目目录（与 docx 并列，可重复导出）。
"""

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.ui.helpers import load_result, PROJECTS_DIR
from src.utils.config import Config
from src.tools.pdf_writer import generate_pdf
from server.response import ok

router = APIRouter(prefix="/api/projects/{project_id}/export", tags=["export"])


def _dir(project_id: str) -> str:
    d = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.isdir(d):
        raise HTTPException(404, f"项目不存在: {project_id}")
    return d


def _result(project_id: str) -> dict:
    d = _dir(project_id)
    result = load_result(d)
    if not result:
        raise HTTPException(404, "该项目尚未生成报告结果")
    return result


@router.get("/docx")
def export_docx(project_id: str):
    """下载 Word 报告（渲染阶段已生成，直接返回）。"""
    result = _result(project_id)
    docx_path = result.get("docx_path", "")
    if not docx_path or not os.path.exists(docx_path):
        raise HTTPException(404, "Word 文件不存在，可能渲染阶段未完成")
    return FileResponse(
        docx_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{project_id}_报告.docx",
    )


@router.get("/markdown")
def export_markdown(project_id: str):
    """下载 Markdown 报告（正文 + 标题）。"""
    result = _result(project_id)
    ai = result.get("ai_data", {}) or {}
    title = ai.get("report_title", "") or result.get("topic", "调研报告")
    md = ai.get("markdown_report", "") or ""
    out_path = os.path.join(_dir(project_id), "05_final_report.md")
    content = f"# {title}\n\n{md}"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return FileResponse(
        out_path,
        media_type="text/markdown",
        filename=f"{title}.md",
    )


@router.get("/pdf")
def export_pdf(project_id: str):
    """下载 PDF 报告（动态生成，券商研报风格）。"""
    result = _result(project_id)
    ai = dict(result.get("ai_data", {}) or {})
    ai["report_title"] = ai.get("report_title") or result.get("topic", "调研报告")
    ai["references"] = ai.get("references", []) or []
    ai["disclaimer"] = Config.REPORT_DISCLAIMER
    out_path = os.path.join(_dir(project_id), "05_final_report.pdf")
    try:
        generate_pdf(ai, out_path)
    except Exception as e:
        raise HTTPException(500, f"PDF 生成失败：{e}")
    return FileResponse(
        out_path,
        media_type="application/pdf",
        filename=f"{ai['report_title']}.pdf",
    )


@router.get("/formats")
def export_formats(project_id: str):
    """列出可用的导出格式（供前端决定显示哪些按钮）。"""
    result = _result(project_id)
    docx_path = result.get("docx_path", "")
    return ok({
        "docx": bool(docx_path and os.path.exists(docx_path)),
        "markdown": bool(result.get("ai_data", {}).get("markdown_report")),
        "pdf": True,
    })
