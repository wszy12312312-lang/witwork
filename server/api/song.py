"""歌曲 API：通过 Windows SMTC 检测当前播放的歌曲（供功能面板「歌曲信息」部件用）。

- GET  /api/song/now      → 当前播放（含会话列表、封面版本号）
- GET  /api/song/status   → 探测能力是否可用（用于前端提示「本机不支持自动检测」）
- POST /api/song/refresh  → 清缓存并强制重读（保留兼容，UI 不再直接调用）
- POST /api/song/control  → 传输控制：{"action": "play"|"pause"|"toggle"|"next"|"prev"}
- GET  /api/song/cover    → 当前曲目封面 PNG 字节（无封面返回 204）
- GET  /api/song/volume   → 当前播放 App 音量：?app_id=...
- POST /api/song/volume   → 设置音量：{"app_id": "...", "level": 0-100}
"""
from fastapi import APIRouter, Response
from pydantic import BaseModel

from server.services import smtc

router = APIRouter(prefix="/song", tags=["song"])


@router.get("/now")
def song_now(force: bool = False):
    return smtc.now_playing(force=force)


@router.get("/status")
def song_status():
    r = smtc.now_playing()
    return {
        "available": bool(r.get("ok")),
        "count": r.get("count", 0),
        "error": r.get("error", ""),
    }


@router.post("/refresh")
def song_refresh():
    smtc.reset_cache()
    return smtc.now_playing(force=True)


@router.post("/control")
def song_control(payload: dict):
    action = (payload or {}).get("action") if isinstance(payload, dict) else None
    if action not in ("play", "pause", "toggle", "next", "prev"):
        return {"ok": False, "error": "未知操作"}
    return smtc.control(action)


@router.get("/cover")
def song_cover():
    data = smtc.get_cover_bytes()
    if not data:
        return Response(status_code=204)
    return Response(content=data, media_type=_sniff_image_mime(data), headers={"Cache-Control": "no-store"})


def _sniff_image_mime(data: bytes) -> str:
    """SMTC 缩略图可能是 PNG/JPEG/WebP 等，按魔数判定，避免 Content-Type 造假导致浏览器拒渲染。"""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"\x42\x4d\x00":  # BMP（Windows 常见）
        return "image/bmp"
    return "application/octet-stream"


class VolumeSet(BaseModel):
    app_id: str = ""
    level: int = 0


@router.get("/volume")
def song_volume_get(app_id: str = ""):
    return smtc.get_volume(app_id)


@router.post("/volume")
def song_volume_set(payload: VolumeSet):
    return smtc.set_volume(payload.app_id, payload.level)
