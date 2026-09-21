"""人物与记忆服务：人物卡 / 关系网 / 出场记录 / 模板实例化 / 上下文注入。

三层记忆：L0 人物卡（characters）、L1 出场记录（章节+摘要）、L2 原文块（excerpt）。
人物与「character」分区条目双向同步（kb_item_id）。
新人物抽取产出 patch，复用 Step 8 写回机制确认后归档。
"""
import json
import re

from server.models import characters as cm
from server.services.knowledge import get_service as get_kb

_NAME_RE = re.compile(r"[\u4e00-\u9fff]{2,4}")


def card_text(c) -> str:
    parts = [f"人物：{c.get('name')}"]
    if c.get("appearance"):
        parts.append("外貌：" + c["appearance"])
    if c.get("personality"):
        parts.append("性格：" + c["personality"])
    if c.get("catchphrase"):
        parts.append("口癖：" + c["catchphrase"])
    if c.get("status_current"):
        parts.append("当前状态：" + c["status_current"])
    if c.get("taboo"):
        parts.append("禁忌：" + c["taboo"])
    return "\n".join(parts)


def _sync_kb(cid):
    """把人物卡同步到 character 分区条目（双向：更新则写新版本）。"""
    c = cm.get_character(cid)
    if not c:
        return None
    kb = get_kb()
    text = card_text(c)
    if c.get("kb_item_id"):
        kb.update_item(c["kb_item_id"], title=c["name"], content=text, reason="人物卡同步")
        return c["kb_item_id"]
    item = kb.ingest_text("character", c["name"], text, source_type="ai", source_ref=f"character:{cid}")
    cm.update_character(cid, {"kb_item_id": item["id"]})
    return item["id"]


def create_character(book_id, name, fields=None):
    c = cm.create_character(book_id, name, fields)
    _sync_kb(c["id"])
    return cm.get_character(c["id"])


def update_character(cid, fields):
    c = cm.update_character(cid, fields)
    _sync_kb(cid)
    return c


def delete_character(cid):
    cm.delete_character(cid)


def list_characters(book_id):
    return cm.list_characters(book_id)


# ---------- 关系 ----------
def add_relation(book_id, from_id, to_id, relation, note=None):
    return cm.add_relation(book_id, from_id, to_id, relation, note)


def list_relations(book_id):
    return cm.list_relations(book_id)


def delete_relation(rid):
    cm.delete_relation(rid)


# ---------- 出场记录 ----------
def record_appearances(book_id, chapter_id, text):
    """扫描正文，为出场人物写 L1 摘要 + L2 原文块。"""
    chars = cm.list_characters(book_id)
    recs = []
    for c in chars:
        names = {c["name"]}
        try:
            names.update(json.loads(c.get("aliases_json") or "[]"))
        except Exception:
            pass
        hit_name = next((n for n in names if n and n in (text or "")), None)
        if not hit_name:
            continue
        idx = (text or "").find(hit_name)
        excerpt = text[max(0, idx - 30): idx + 60]
        recs.append(cm.add_appearance(c["id"], chapter_id, summary=f"出场于第{chapter_id}章", excerpt=excerpt))
    return recs


def list_appearances(character_id):
    return cm.list_appearances(character_id)


# ---------- 抽取候选（复用 patches 机制） ----------
def extract_candidates(book_id, text, session_id=None):
    """从对话/正文抽取新人物候选，产出 patch 列表（待确认）。"""
    existing = {c["name"] for c in cm.list_characters(book_id)}
    cands = {}
    for m in re.finditer(r"([\u4e00-\u9fff]{2,4})(?:，|,)?\s*(?:是|，性格|，)(.{0,40})", text or ""):
        name = m.group(1)
        if name in existing or name in ("但是", "就是", "于是", "而且"):
            continue
        cands.setdefault(name, m.group(2)[:40])
    patches = []
    kb = get_kb()
    for name, desc in list(cands.items())[:5]:
        patches.append({
            "target_type": "kb_item",
            "section": "character",
            "title": name,
            "op": "create",
            "fields": {"content": f"人物：{name}\n{desc}"},
            "reason": "对话中抽取的人物候选",
        })
    _ = kb
    return patches


# ---------- 角色模板 ----------
def list_templates():
    return cm.list_templates()


def instantiate_template(template_id, book_id, name):
    t = cm.get_template(template_id)
    if not t:
        return None
    fields = json.loads(t.get("fields_json") or "[]")
    payload = {f: "" for f in fields} if isinstance(fields, list) else {}
    payload["template_id"] = template_id
    return create_character(book_id, name, payload)


# ---------- 上下文注入 ----------
def build_injection_text(book_id, chapter_text=None):
    """写作时注入出场人物卡摘要（口癖、状态、禁忌）。"""
    chars = cm.list_characters(book_id)
    if not chars:
        return ""
    if chapter_text:
        sel = []
        for c in chars:
            names = {c["name"]}
            try:
                names.update(json.loads(c.get("aliases_json") or "[]"))
            except Exception:
                pass
            if any(n and n in chapter_text for n in names):
                sel.append(c)
        chars = sel or []
    if not chars:
        return ""
    lines = []
    for c in chars:
        bit = [c["name"]]
        if c.get("catchphrase"):
            bit.append("口癖：" + c["catchphrase"])
        if c.get("status_current"):
            bit.append("状态：" + c["status_current"])
        if c.get("taboo"):
            bit.append("禁忌：" + c["taboo"])
        lines.append("、".join(bit))
    return "\n".join(lines)
