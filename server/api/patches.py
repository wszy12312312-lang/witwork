"""结构化写回提议 API：列出 / 应用 / 拒绝。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from server.core import patch as patch_core

router = APIRouter(prefix="/patches", tags=["patches"])


@router.get("")
def list_patches(session_id: int | None = None, status: str | None = None):
    return patch_core.list_patches(session_id=session_id, status=status)


@router.post("/{pid}/apply")
def apply_patch(pid: int):
    try:
        return patch_core.apply_patch(pid)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@router.post("/{pid}/reject")
def reject_patch(pid: int):
    return patch_core.reject_patch(pid)
