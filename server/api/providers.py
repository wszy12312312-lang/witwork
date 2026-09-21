"""Provider 管理 + 连通性探测。"""
import httpx

from fastapi import APIRouter, HTTPException

import server.adapters.providers as _reg  # 触发注册
from server.adapters.llm import get_adapter, LLMError
from server.models import providers as pm

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("")
def list_providers():
    return pm.list_providers()


@router.post("")
def create_provider(payload: dict):
    p = pm.create_provider(payload)
    return p


@router.put("/{pid}")
def update_provider(pid: str, payload: dict):
    p = pm.update_provider(pid, payload)
    if not p:
        raise HTTPException(404, "provider 不存在")
    return p


@router.delete("/{pid}")
def delete_provider(pid: str):
    pm.delete_provider(pid)
    return {"ok": True}


@router.post("/default")
def set_default_provider(payload: dict):
    """把某个 provider 设为默认模型。"""
    pid = payload.get("id")
    if not pid:
        raise HTTPException(400, "缺少 id")
    res = pm.set_default_provider(pid)
    if not res:
        raise HTTPException(404, "provider 不存在")
    return {"ok": True, "default_provider_id": pid}


@router.get("/discover")
def discover_models(base_url: str = None):
    """探测本地 Ollama 已安装模型（用于新建 provider 时一键拉取）。"""
    url = (base_url or "http://127.0.0.1:11434").rstrip("/") + "/api/tags"
    try:
        r = httpx.get(url, timeout=10, trust_env=False)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            return {"base_url": (base_url or "http://127.0.0.1:11434"), "ok": True, "models": models}
        return {"base_url": (base_url or "http://127.0.0.1:11434"), "ok": False,
                "error": f"HTTP {r.status_code}", "models": []}
    except Exception as e:
        return {"base_url": (base_url or "http://127.0.0.1:11434"), "ok": False,
                "error": str(e), "models": []}


@router.get("/test/{pid}")
def test_provider(pid: str):
    """连通性与能力探测：失败返回明确错误而非崩溃。"""
    p = pm.get_provider(pid)
    if not p:
        raise HTTPException(404, "provider 不存在")
    try:
        adapter = get_adapter(p)
    except LLMError as e:
        return {"id": pid, "ok": False, "error": f"初始化失败：{e}", "capabilities": {}, "models": []}
    try:
        health = adapter.health()
    except Exception as e:  # 任何异常都不应让接口崩溃
        health = {"ok": False, "error": str(e), "models": []}
    return {
        "id": pid,
        "ok": bool(health.get("ok")),
        "error": health.get("error", ""),
        "models": health.get("models", []),
        "capabilities": adapter.capabilities(),
    }
