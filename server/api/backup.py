"""备份 API：列表 / 创建 / 恢复 / 演练 / 策略。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from server.core import backup as bk

router = APIRouter(prefix="/backup", tags=["backup"])


@router.get("/list")
def list_backups():
    return bk.list_backups()


@router.post("/create")
def create(payload: dict | None = None):
    body = payload or {}
    return bk.create_backup(body.get("tag"), include_uploads=body.get("include_uploads", True))


@router.post("/restore")
def restore(payload: dict):
    try:
        return bk.restore_backup(payload.get("name"), include_uploads=payload.get("include_uploads", True))
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@router.post("/drill")
def drill(payload: dict):
    """恢复演练：只校验，不落盘。"""
    try:
        return bk.drill(payload.get("name"))
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@router.get("/policy")
def policy():
    return bk.get_policy()


@router.put("/policy")
def set_policy(payload: dict):
    return bk.set_policy(**payload)


@router.delete("/delete")
def delete(payload: dict):
    try:
        return bk.delete_backup(payload.get("name"))
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})
