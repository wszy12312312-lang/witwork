"""角色库 API：模板列表/新建/实例化为角色（副本）。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from server.services import role as role_svc

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("")
def list_templates():
    return role_svc.list_templates()


@router.post("")
def create_template(payload: dict):
    name = (payload.get("name") or "").strip()
    if not name:
        return JSONResponse(status_code=400, content={"detail": "name 必填"})
    return role_svc.create_template(name, payload.get("category", "配角"),
                                    payload.get("fields") or [], payload.get("is_global", 0))


@router.post("/{tid}/instantiate")
def instantiate(tid: int, payload: dict):
    name = (payload.get("name") or "").strip()
    if not name:
        return JSONResponse(status_code=400, content={"detail": "name 必填"})
    c = role_svc.instantiate(tid, payload.get("book_id"), name)
    if not c:
        return JSONResponse(status_code=404, content={"detail": "模板不存在"})
    return c
