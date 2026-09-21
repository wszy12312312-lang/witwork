"""伏笔 API：CRUD / 生命周期动作 / 事件 / 注入 / 回收检测。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from server.services import foreshadow as fs_svc

router = APIRouter(prefix="/foreshadow", tags=["foreshadow"])


@router.get("")
def list_all(book_id: int | None = None, status: str | None = None):
    return fs_svc.list_all(book_id, status)


@router.post("")
def create(payload: dict):
    title = (payload.get("title") or "").strip()
    if not title:
        return JSONResponse(status_code=400, content={"detail": "title 必填"})
    return fs_svc.create(payload.get("book_id"), title, payload.get("content"),
                         payload.get("importance", 3), payload.get("keywords"))


@router.get("/injection")
def injection(book_id: int | None = None):
    return {"text": fs_svc.injection_text(book_id)}


@router.post("/scan")
def scan(payload: dict):
    return {"matches": fs_svc.scan_text(payload.get("book_id"), payload.get("text", ""))}


@router.get("/unresolved")
def unresolved(book_id: int | None = None, min_importance: int = 4):
    return fs_svc.unresolved_high(book_id, min_importance)


@router.get("/{fid}")
def get_one(fid: int):
    f = fs_svc.get(fid)
    if not f:
        return JSONResponse(status_code=404, content={"detail": "伏笔不存在"})
    return f


@router.put("/{fid}")
def update(fid: int, payload: dict):
    return fs_svc.update(fid, payload)


@router.delete("/{fid}")
def delete(fid: int):
    fs_svc.delete(fid)
    return {"ok": True}


@router.post("/{fid}/action")
def action(fid: int, payload: dict):
    act = payload.get("action")
    try:
        return fs_svc.do_action(fid, act, payload.get("chapter_id"), payload.get("note"))
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@router.get("/{fid}/events")
def events(fid: int):
    return fs_svc.events(fid)
