"""编辑历史 API：撤销栈 push / undo / redo / 状态。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from server.services.history import get_service

router = APIRouter(prefix="/chapters", tags=["history"])


@router.post("/{cid}/history/push")
def push(cid: int, payload: dict):
    if payload.get("content") is None:
        return JSONResponse(status_code=400, content={"detail": "content 必填"})
    return get_service().push(cid, payload["content"], payload.get("label"))


@router.post("/{cid}/history/undo")
def undo(cid: int):
    return get_service().undo(cid)


@router.post("/{cid}/history/redo")
def redo(cid: int):
    return get_service().redo(cid)


@router.get("/{cid}/history/status")
def status(cid: int):
    return get_service().status(cid)
