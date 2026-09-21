"""导出 API：Word（python-docx）+ 导出模板。"""
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from server.models import chapters as chm
from server.services import export_docx as ex
from server.services import export_ebook as eb

router = APIRouter(prefix="/export", tags=["export"])


def _with_url(res, mime):
    name = res["path"].split("\\")[-1].split("/")[-1]
    res["download_url"] = "/api/export/file?name=" + quote(name)
    res["mime"] = mime
    return res


@router.get("/templates")
def templates():
    return ex.list_templates()


@router.post("/templates")
def add_template(payload: dict):
    return ex.create_template(payload.get("name", "样式"), payload.get("style") or {})


def _gather_text(payload: dict):
    """从 chapter_ids 取正文；否则用 payload.text。"""
    ids = payload.get("chapter_ids")
    if ids:
        parts = []
        for cid in ids:
            c = chm.get_chapter(cid)
            if c:
                parts.append(c.get("content") or "")
        return "\n".join(parts)
    return payload.get("text", "")


@router.post("/docx")
def export_docx(payload: dict):
    book_id = payload.get("book_id")
    if not book_id:
        return JSONResponse(status_code=400, content={"detail": "book_id 必填"})
    try:
        res = ex.export_book(book_id, payload.get("style"),
                             typeset=payload.get("typeset", True),
                             filename=payload.get("filename"))
    except ValueError as e:
        return JSONResponse(status_code=404, content={"detail": str(e)})
    except ImportError:
        return JSONResponse(status_code=501, content={"detail": "未安装 python-docx，无法导出 Word"})
    return _with_url(res, "docx")


@router.post("/md")
def export_md(payload: dict):
    book_id = payload.get("book_id")
    if not book_id:
        return JSONResponse(status_code=400, content={"detail": "book_id 必填"})
    try:
        return _with_url(eb.export_md(book_id, payload.get("typeset", True)), "md")
    except ValueError as e:
        return JSONResponse(status_code=404, content={"detail": str(e)})


@router.post("/epub")
def export_epub(payload: dict):
    book_id = payload.get("book_id")
    if not book_id:
        return JSONResponse(status_code=400, content={"detail": "book_id 必填"})
    try:
        return _with_url(eb.export_epub(book_id, payload.get("typeset", True), payload.get("filename")), "epub")
    except ValueError as e:
        return JSONResponse(status_code=404, content={"detail": str(e)})


@router.post("/framework")
def export_framework(payload: dict):
    """设定导出：fmt=md | json。"""
    book_id = payload.get("book_id")
    if not book_id:
        return JSONResponse(status_code=400, content={"detail": "book_id 必填"})
    fmt = (payload.get("fmt") or "md").lower()
    try:
        res = eb.export_framework_md(book_id) if fmt == "md" else eb.export_framework_json(book_id)
    except ValueError as e:
        return JSONResponse(status_code=404, content={"detail": str(e)})
    return _with_url(res, fmt)


@router.get("/file")
def download(name: str):
    p = ex.EXPORT_DIR / name
    if not p.exists():
        return JSONResponse(status_code=404, content={"detail": "文件不存在"})
    # 按扩展名给正确 MIME，避免 MD/EPUB 被当成 docx
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    lower = name.lower()
    if lower.endswith(".md"):
        mime = "text/markdown; charset=utf-8"
    elif lower.endswith(".epub"):
        mime = "application/epub+zip"
    elif lower.endswith(".json"):
        mime = "application/json"
    return FileResponse(str(p), filename=name, media_type=mime)
