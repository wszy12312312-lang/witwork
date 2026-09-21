"""人物 API：人物卡 / 关系网 / 出场记录 / 候选抽取。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from server.core import patch as patch_core
from server.services import character as char_svc

router = APIRouter(prefix="/characters", tags=["characters"])


@router.get("")
def list_chars(book_id: int | None = None):
    return char_svc.list_characters(book_id)


@router.post("")
def create_char(payload: dict):
    name = (payload.get("name") or "").strip()
    if not name:
        return JSONResponse(status_code=400, content={"detail": "name 必填"})
    return char_svc.create_character(payload.get("book_id"), name, payload.get("fields") or {})


@router.get("/relations")
def relations(book_id: int | None = None):
    return char_svc.list_relations(book_id)


@router.post("/relations")
def add_relation(payload: dict):
    if not payload.get("from_id") or not payload.get("to_id"):
        return JSONResponse(status_code=400, content={"detail": "from_id/to_id 必填"})
    return char_svc.add_relation(payload.get("book_id"), payload["from_id"], payload["to_id"],
                                 payload.get("relation", ""), payload.get("note"))


@router.delete("/relations/{rid}")
def del_relation(rid: int):
    char_svc.delete_relation(rid)
    return {"ok": True}


@router.post("/extract")
def extract(payload: dict):
    """从对话/正文抽取人物候选 → 产出待确认 patch。"""
    book_id = payload.get("book_id")
    text = payload.get("text", "")
    patches = char_svc.extract_candidates(book_id, text)
    rows = []
    for p in patches:
        try:
            rows.append(patch_core.propose(p, session_id=payload.get("session_id")))
        except ValueError:
            continue
    return {"patches": rows}


@router.post("/scan-appearances")
def scan_appearances(payload: dict):
    """扫描正文，写出场记录（L1 摘要 + L2 原文块）。"""
    recs = char_svc.record_appearances(payload.get("book_id"), payload.get("chapter_id"), payload.get("text", ""))
    return {"records": recs}


@router.get("/{cid}")
def get_char(cid: int):
    c = char_svc.list_characters(None)
    one = next((x for x in c if x["id"] == cid), None)
    if not one:
        return JSONResponse(status_code=404, content={"detail": "人物不存在"})
    return one


@router.put("/{cid}")
def update_char(cid: int, payload: dict):
    return char_svc.update_character(cid, payload)


@router.delete("/{cid}")
def del_char(cid: int):
    char_svc.delete_character(cid)
    return {"ok": True}


@router.get("/{cid}/appearances")
def appearances(cid: int):
    return char_svc.list_appearances(cid)
