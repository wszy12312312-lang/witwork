"""会话与 SSE 流式生成。"""
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse

import server.adapters.providers as _reg  # 触发注册
from server.models import books as book_m
from server.models import sessions as sm
from server.services import session as sess_svc

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
def list_sessions(book_id: int | None = None):
    return sm.list_sessions(book_id)


@router.post("")
def create_session(payload: dict):
    book_id = payload.get("book_id")
    # 校验作品：sessions.book_id 有外键约束，以前 book_id 为空/不存在时会抛出
    # sqlite3.IntegrityError 变成 500，前端只看到「新建会话失败」。
    book = book_m.get_book(book_id) if book_id else None
    if not book or book.get("deleted_at"):
        raise HTTPException(404, "作品不存在或已在回收站，请先新建或打开一个作品")
    return sess_svc.create_session(
        book_id=book_id,
        title=payload.get("title"),
        provider_id=payload.get("provider_id"),
    )


@router.get("/{sid}")
def get_session(sid: int):
    s = sm.get_session(sid)
    if not s:
        return JSONResponse(status_code=404, content={"detail": "会话不存在"})
    s["messages"] = sm.list_messages(sid)
    return s


@router.delete("/{sid}")
def delete_session(sid: int):
    sm.delete_session(sid)
    return {"ok": True}


@router.patch("/{sid}/provider")
def set_provider(sid: int, payload: dict):
    """Step 10：热切换模型。更新活跃 provider（上下文预算在下次生成时由 ContextBuilder 重算）。"""
    s = sm.get_session(sid)
    if not s:
        return JSONResponse(status_code=404, content={"detail": "会话不存在"})
    sm.update_session(sid, {"active_provider_id": payload.get("provider_id")})
    return sm.get_session(sid)


@router.post("/{sid}/messages")
async def post_message(sid: int, payload: dict, request: Request):
    """SSE：refs -> delta* -> done | error。客户端断开即停止，不残留半截。"""
    user_content = (payload.get("content") or "").strip()
    if not user_content:
        return JSONResponse(status_code=400, content={"detail": "内容为空"})

    async def event_stream():
        gen = sess_svc.send_message_stream(
            sid, user_content,
            provider_id=payload.get("provider_id"),
            params=payload.get("params"),
        )
        for event in gen:
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
