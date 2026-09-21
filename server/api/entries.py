"""词条 API：CRUD / 从正文抽取候选 / 异写归一化。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from server.models import chapters as chm
from server.services import entry as entry_svc

router = APIRouter(prefix="/entries", tags=["entries"])


@router.get("")
def list_all(book_id: int | None = None, category: str | None = None):
    return entry_svc.list_all(book_id, category)


@router.post("")
def create(payload: dict):
    name = (payload.get("name") or "").strip()
    if not name:
        return JSONResponse(status_code=400, content={"detail": "name 必填"})
    return entry_svc.create(payload.get("book_id"), name, payload.get("category"),
                            payload.get("aliases"), payload.get("description"),
                            payload.get("first_chapter_id"))


@router.post("/extract")
def extract(payload: dict):
    """从正文抽取候选词条（新词发现）。texts 可为字符串数组，或 chapter_ids 取章节正文。"""
    texts = payload.get("texts")
    if not texts:
        ids = payload.get("chapter_ids") or []
        texts = []
        for cid in ids:
            ch = chm.get_chapter(cid)
            if ch:
                texts.append(ch.get("content") or "")
    cands = entry_svc.extract(payload.get("book_id"), texts,
                              top_n=int(payload.get("top_n", 30)),
                              min_count=int(payload.get("min_count", 2)))
    return {"candidates": cands}


@router.post("/normalize")
def normalize(payload: dict):
    """按规范词形统一异写。"""
    counts = entry_svc.normalize(payload.get("book_id"), payload.get("chapter_ids"))
    return {"replaced": counts}


@router.get("/{eid}")
def get_one(eid: int):
    e = entry_svc.get(eid)
    if not e:
        return JSONResponse(status_code=404, content={"detail": "词条不存在"})
    return e


@router.put("/{eid}")
def update(eid: int, payload: dict):
    return entry_svc.update(eid, payload)


@router.delete("/{eid}")
def delete(eid: int):
    entry_svc.delete(eid)
    return {"ok": True}
