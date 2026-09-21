"""框架共创 API：状态 / 推进 / 回退 / 生成章节骨架。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from server.services import cocreation as co_svc

router = APIRouter(prefix="/sessions", tags=["framework"])


@router.get("/{sid}/framework")
def framework_state(sid: int):
    return co_svc.get_state(sid)


@router.post("/{sid}/framework/advance")
def framework_advance(sid: int, payload: dict):
    return co_svc.advance(sid, payload.get("conclusion", ""), note=payload.get("note"))


@router.post("/{sid}/framework/retreat")
def framework_retreat(sid: int):
    return co_svc.retreat(sid)


@router.post("/{sid}/framework/outline")
def framework_outline(sid: int, payload: dict):
    res = co_svc.generate_outline(sid, payload.get("book_id"))
    if res.get("error"):
        return JSONResponse(status_code=404, content={"detail": res["error"]})
    return res
