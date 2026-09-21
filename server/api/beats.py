"""爽点节奏 API。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from server.services import beat as beat_svc

router = APIRouter(prefix="/beats", tags=["beats"])


@router.get("")
def marks(book_id: int | None = None, chapter_id: int | None = None):
    return beat_svc.list_marks(book_id, chapter_id)


@router.post("")
def add(payload: dict):
    try:
        return beat_svc.add_mark(payload.get("book_id"), payload.get("chapter_id"),
                                 payload.get("kind", "payoff"), payload.get("strength", 3),
                                 payload.get("offset", 0), payload.get("text"),
                                 payload.get("source", "manual"))
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@router.delete("/{mid}")
def delete(mid: int):
    beat_svc.delete_mark(mid)
    return {"ok": True}


@router.get("/templates")
def templates():
    return beat_svc.list_templates()


@router.get("/metrics")
def metrics(book_id: int | None = None, template_id: int | None = None, flat_threshold: int = 3000):
    return beat_svc.metrics(book_id, template_id, flat_threshold)


@router.get("/suggest")
def suggest(book_id: int | None = None, template_id: int | None = None, flat_threshold: int = 3000):
    return {"suggestions": beat_svc.suggest(book_id, template_id, flat_threshold)}
