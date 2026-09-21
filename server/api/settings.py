"""设置 API：读写 data/config.json（仅 DEFAULTS 中的键会被持久化）。"""
from fastapi import APIRouter

from server.config import DEFAULTS, load_config, reload, save_config

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings():
    cfg = reload()
    return {"config": cfg, "keys": sorted(DEFAULTS.keys())}


@router.put("")
def put_settings(payload: dict):
    return save_config(payload or {})
