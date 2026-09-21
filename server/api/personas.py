"""人格 API：CRUD / 激活 / 版本 / 自然语言调整。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from server.models import personas as pm
from server.services import persona as persona_svc

router = APIRouter(prefix="/personas", tags=["personas"])


@router.get("")
def list_personas():
    return pm.list_personas()


@router.post("")
def create_persona(payload: dict):
    return pm.create_persona(payload)


@router.get("/{pid}")
def get_persona(pid: int):
    p = pm.get_persona(pid)
    if not p:
        return JSONResponse(status_code=404, content={"detail": "人格不存在"})
    return p


@router.put("/{pid}")
def update_persona(pid: int, payload: dict):
    return pm.update_persona(pid, payload)


@router.delete("/{pid}")
def delete_persona(pid: int):
    pm.delete_persona(pid)
    return {"ok": True}


@router.post("/{pid}/activate")
def activate(pid: int):
    pm.set_active(pid)
    return pm.get_persona(pid)


@router.get("/{pid}/versions")
def versions(pid: int):
    return pm.list_versions(pid)


@router.post("/adjust")
def adjust(payload: dict):
    """自然语言调整当前会话的人格（overlay 立即生效 + 记版本）。"""
    sid = payload.get("session_id")
    statement = (payload.get("statement") or "").strip()
    if not sid or not statement:
        return JSONResponse(status_code=400, content={"detail": "session_id 与 statement 必填"})
    return persona_svc.parse_adjust(sid, statement)
