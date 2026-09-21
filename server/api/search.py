"""全文搜索与替换 API。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from server.services import search as search_svc

router = APIRouter(prefix="/books", tags=["search"])


@router.post("/{bid}/search")
def do_search(bid: int, payload: dict):
    return search_svc.search(
        bid, payload.get("query", ""),
        use_regex=bool(payload.get("use_regex")),
        case_sensitive=bool(payload.get("case_sensitive")),
        scope=payload.get("scope", "book"),
        volume_id=payload.get("volume_id"),
        chapter_id=payload.get("chapter_id"),
        limit=int(payload.get("limit", 500)),
    )


@router.post("/{bid}/replace")
def do_replace(bid: int, payload: dict):
    """dry_run=true 返回 diff 预览；false 才真正替换。"""
    return search_svc.replace(
        bid, payload.get("query", ""), payload.get("replacement", ""),
        use_regex=bool(payload.get("use_regex")),
        case_sensitive=bool(payload.get("case_sensitive")),
        scope=payload.get("scope", "book"),
        volume_id=payload.get("volume_id"),
        chapter_id=payload.get("chapter_id"),
        chapter_ids=payload.get("chapter_ids"),
        dry_run=bool(payload.get("dry_run", True)),
    )


@router.get("/{bid}/replace-logs")
def logs(bid: int):
    return search_svc.list_logs(bid)


@router.post("/replace-logs/{rid}/undo")
def undo(rid: int):
    try:
        return search_svc.undo_replace(rid)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})
