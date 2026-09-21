"""AI 正文操作接口：在写作页面对原文做改写/续写/扩写/缩写/创作，或通读全书给修改意见。

SSE 事件：refs(一次) / delta(多次) / done | error。客户端断开即停止。
"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse

from server.services import ai_ops as svc

router = APIRouter(prefix="/ai/ops", tags=["ai-ops"])


@router.post("/operate")
async def operate(payload: dict, request: Request):
    operation = (payload.get("operation") or "").strip()
    if not operation:
        return JSONResponse(status_code=400, content={"detail": "operation 必填"})

    book_id = payload.get("book_id")
    chapter_id = payload.get("chapter_id")
    text = payload.get("text") or ""
    instruction = payload.get("instruction") or ""
    scope = payload.get("scope") or "chapter"
    provider_id = payload.get("provider_id")

    async def event_stream():
        gen = svc.operate_stream(
            book_id=book_id,
            chapter_id=chapter_id,
            operation=operation,
            text=text,
            instruction=instruction,
            scope=scope,
            provider_id=provider_id,
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
