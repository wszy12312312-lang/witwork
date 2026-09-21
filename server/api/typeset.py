"""排版 API：规则 / 预览渲染 / 一键排版（可写回）。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from server.models import chapters as chm, snapshots as snm
from server.services import typesetting as ts

router = APIRouter(prefix="/typeset", tags=["typeset"])


@router.get("/rules")
def rules():
    return ts.load_rules()


@router.post("/chapters/{cid}/preview")
def preview(cid: int, payload: dict | None = None):
    """只读渲染：不改正文。body 可带 content 覆盖（用于编辑中实时预览）。"""
    body = payload or {}
    content = body.get("content")
    if content is None:
        ch = chm.get_chapter(cid)
        if not ch:
            return JSONResponse(status_code=404, content={"detail": "章节不存在"})
        content = ch.get("content") or ""
    return ts.render_preview(content, body.get("options"))


@router.post("/chapters/{cid}/normalize")
def normalize(cid: int, payload: dict | None = None):
    """dry_run=true 返回逐处 changes 预览；false 才写回（写回前建快照）。"""
    body = payload or {}
    ch = chm.get_chapter(cid)
    if not ch:
        return JSONResponse(status_code=404, content={"detail": "章节不存在"})
    content = body.get("content")
    if content is None:
        content = ch.get("content") or ""
    res = ts.normalize(content, body.get("options"))
    if body.get("dry_run", True):
        return res
    # 写回前建快照（危险操作可撤销）
    snap = snm.create_snapshot(ch.get("book_id"), cid, kind="pre_action",
                               title="一键排版前", content=ch.get("content") or "", trigger="typeset")
    chm.update_chapter(cid, {"content": res["content"]})
    res["snapshot_id"] = snap["id"]
    return res
