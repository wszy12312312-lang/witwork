"""知识库 API：分区 / 条目 / 入库 / 检索 / 版本回滚。"""
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from server.config import UPLOAD_DIR
from server.models import knowledge as km
from server.services.knowledge import get_service

router = APIRouter(prefix="/kb", tags=["kb"])


@router.get("/sections")
def get_sections():
    return km.list_sections()


@router.post("/sections")
def post_section(payload: dict):
    key = (payload.get("key") or "").strip().lower()
    if not key:
        return JSONResponse(status_code=400, content={"detail": "key 必填"})
    if km.get_section(key):
        return JSONResponse(status_code=409, content={"detail": "分区已存在"})
    return km.create_section(key, payload.get("title", key), payload.get("description"))


@router.get("/items")
def get_items(section: str | None = None):
    return km.list_items(section)


@router.post("/items")
def post_item(payload: dict):
    section = (payload.get("section") or "").strip()
    title = (payload.get("title") or "").strip()
    if not section or not title:
        return JSONResponse(status_code=400, content={"detail": "section 与 title 必填"})
    svc = get_service()
    item = svc.ingest_text(section, title, payload.get("content", ""), source_type="manual")
    return item


@router.get("/items/{item_id}")
def get_item(item_id: int):
    it = km.get_item(item_id)
    if not it:
        return JSONResponse(status_code=404, content={"detail": "条目不存在"})
    it["versions"] = km.list_versions(item_id)
    return it


@router.put("/items/{item_id}")
def put_item(item_id: int, payload: dict):
    svc = get_service()
    try:
        return svc.update_item(item_id, title=payload.get("title"), content=payload.get("content"),
                               reason=payload.get("reason", "编辑"))
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@router.delete("/items/{item_id}")
def del_item(item_id: int):
    km.delete_item(item_id)
    return {"ok": True}


@router.get("/items/{item_id}/versions")
def get_versions(item_id: int):
    return km.list_versions(item_id)


@router.post("/items/{item_id}/rollback")
def rollback(item_id: int, payload: dict):
    svc = get_service()
    vid = payload.get("version_id")
    if not vid:
        return JSONResponse(status_code=400, content={"detail": "version_id 必填"})
    it = svc.rollback_version(item_id, vid)
    if not it:
        return JSONResponse(status_code=404, content={"detail": "版本不存在"})
    return it


@router.post("/ingest")
async def ingest(request: Request):
    """文件入库（txt/md）。multipart 表单（file + section）或 JSON {section, path}。"""
    ctype = request.headers.get("content-type", "")
    svc = get_service()
    if "multipart" in ctype or "form" in ctype:
        form = await request.form()
        file = form.get("file")
        section = (form.get("section") or "misc").strip() or "misc"
        if not file:
            return JSONResponse(status_code=400, content={"detail": "缺少 file"})
        ext = os.path.splitext(getattr(file, "filename", "") or "")[1].lower()
        if ext not in (".txt", ".md"):
            return JSONResponse(status_code=400, content={"detail": "仅支持 txt/md"})
        dest = os.path.join(str(UPLOAD_DIR), os.path.basename(getattr(file, "filename", "") or "upload.txt"))
        content = await file.read()
        open(dest, "wb").write(content)
        return {"items": svc.ingest_file(section, dest)}
    # JSON 形式
    try:
        body = await request.json()
    except Exception:
        body = {}
    section = (body.get("section") or "misc").strip() or "misc"
    path = body.get("path")
    if path and os.path.exists(path):
        return {"items": svc.ingest_file(section, path)}
    return JSONResponse(status_code=400, content={"detail": "需上传文件或提供 path"})


@router.post("/retrieve")
def retrieve(payload: dict):
    svc = get_service()
    hits = svc.retrieve(payload.get("query", ""), sections=payload.get("sections"), top_k=payload.get("top_k"))
    return {"hits": hits}


@router.post("/reindex")
def reindex(payload: dict | None = None):
    """用当前 embedding 配置（config.embedding）对全库切块重嵌入。

    - 切换嵌入模型（如 hash -> bge-m3）后必须调用，否则旧维度向量与新查询维度不匹配，检索失效。
    - 可选 payload: {"section": "worldview"} 仅重索引某分区。
    """
    svc = get_service()
    try:
        return svc.reindex_all(section=(payload or {}).get("section"))
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
