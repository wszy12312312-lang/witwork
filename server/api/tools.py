"""兼容工具 API：高频词透镜 / AI 味自查 / 合规词自检 / 外部服务探测。"""
from fastapi import APIRouter

from server.models import chapters as chm
from server.services import tools as tools_svc

router = APIRouter(prefix="/tools", tags=["tools"])


def _text(payload: dict):
    ids = payload.get("chapter_ids")
    if ids:
        parts = []
        for cid in ids:
            c = chm.get_chapter(cid)
            if c:
                parts.append(c.get("content") or "")
        return "\n".join(parts)
    return payload.get("text", "")


@router.post("/word-freq")
def word_freq(payload: dict):
    return {"words": tools_svc.word_freq(_text(payload), int(payload.get("top_n", 50)))}


@router.post("/ai-taste")
def ai_taste(payload: dict):
    return tools_svc.ai_taste(_text(payload))


@router.post("/compliance")
def compliance(payload: dict):
    return tools_svc.compliance(_text(payload), payload.get("custom"))


@router.get("/services")
def services():
    return tools_svc.probe_services()
