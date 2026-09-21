"""结构化写回：校验 AI 提议补丁、应用写库、回滚。

补丁 JSON 形态（来自 AI 输出）：
  {"patches":[{"target_type":"kb_item","section":"worldview","title":"星尘",
               "op":"create","fields":{"content":"…"},"reason":"…"}]}

流程：extractor 抽取 → propose 落库（pending / 自动落库 applied）→
前端勾选 → apply_patch 写 kb_item+version+重索引 / reject_patch 拒绝。
"""
import json

from server.db import get_conn
from server.models import knowledge as km
from server.services.knowledge import get_service

ALLOWED_FIELDS = {
    "kb_item": {"title", "content"},
}

VALID_OPS = {"create", "update", "delete"}


def validate(patch: dict):
    """返回 (ok, error, normalized)。"""
    if not isinstance(patch, dict):
        return False, "补丁不是对象", None
    tt = patch.get("target_type")
    if tt not in ALLOWED_FIELDS:
        return False, f"不支持的 target_type: {tt}", None
    op = patch.get("op")
    if op not in VALID_OPS:
        return False, f"不支持的 op: {op}", None
    section = (patch.get("section") or "").strip()
    title = (patch.get("title") or "").strip()
    if not section:
        return False, "缺少 section", None
    if op != "delete" and not title:
        return False, "create/update 需要 title", None
    fields = patch.get("fields") or {}
    if not isinstance(fields, dict):
        return False, "fields 必须是对象", None
    bad = set(fields) - ALLOWED_FIELDS[tt]
    if bad:
        return False, f"非法字段: {sorted(bad)}", None
    norm = {
        "target_type": tt,
        "section": section,
        "title": title,
        "op": op,
        "fields": fields,
        "reason": (patch.get("reason") or "").strip(),
    }
    return True, None, norm


def resolve_item(section, title, conn):
    rows = conn.execute(
        "SELECT * FROM kb_items WHERE section=? AND title=?", (section, title)
    ).fetchall()
    return dict(rows[0]) if rows else None


def propose(patch: dict, session_id=None, auto=False):
    """落库一条提议；auto=True 且为无同名 create 时直接应用。返回 patches 行。"""
    ok, err, norm = validate(patch)
    if not ok:
        raise ValueError(err)
    conn = get_conn()
    try:
        current = None
        if norm["op"] in ("update", "delete"):
            cur = resolve_item(norm["section"], norm["title"], conn)
            if cur:
                current = {"title": cur["title"], "content": cur["content"]}
        status = "pending"
        applied_at = None
        # 自动落库：仅 create 且无同名
        if auto and norm["op"] == "create" and not resolve_item(norm["section"], norm["title"], conn):
            status = "applied"
            applied_at = _now()
        cur = conn.execute(
            """INSERT INTO patches(session_id, target_type, section, title, op, fields_json, reason, status, current_value_json, applied_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (session_id, norm["target_type"], norm["section"], norm["title"], norm["op"],
             json.dumps(norm["fields"], ensure_ascii=False), norm["reason"], status,
             json.dumps(current, ensure_ascii=False) if current else None, applied_at),
        )
        pid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    row = _get_patch(pid)
    if status == "applied":
        apply_patch(pid)
        row = _get_patch(pid)
    return row


def apply_patch(patch_id):
    row = _get_patch(patch_id)
    if not row:
        raise ValueError("补丁不存在")
    if row["status"] == "applied":
        return row
    norm = {
        "target_type": row["target_type"],
        "section": row["section"],
        "title": row["title"],
        "op": row["op"],
        "fields": json.loads(row["fields_json"]),
        "reason": row["reason"],
    }
    svc = get_service()
    conn = get_conn()
    try:
        if norm["op"] == "delete":
            it = resolve_item(norm["section"], norm["title"], conn)
            if not it:
                raise ValueError("目标条目不存在，无法删除")
            km.delete_item(it["id"], conn)
        elif norm["op"] == "create":
            existing = resolve_item(norm["section"], norm["title"], conn)
            if existing:
                # 同名冲突：转 update
                svc.update_item(existing["id"], title=norm["title"], content=norm["fields"].get("content"),
                                reason=norm["reason"] or "AI 写回（同名合并）")
            else:
                svc.ingest_text(norm["section"], norm["title"], norm["fields"].get("content", ""),
                                source_type="ai", source_ref=f"patch:{patch_id}")
        else:  # update
            it = resolve_item(norm["section"], norm["title"], conn)
            if not it:
                svc.ingest_text(norm["section"], norm["title"], norm["fields"].get("content", ""),
                                source_type="ai", source_ref=f"patch:{patch_id}")
            else:
                svc.update_item(it["id"], title=norm.get("fields", {}).get("title"), content=norm["fields"].get("content"),
                                reason=norm["reason"] or "AI 写回", source_message_id=None)
        conn.execute("UPDATE patches SET status='applied', applied_at=? WHERE id=?", (_now(), patch_id))
        conn.commit()
    finally:
        conn.close()
    return _get_patch(patch_id)


def reject_patch(patch_id):
    conn = get_conn()
    try:
        conn.execute("UPDATE patches SET status='rejected' WHERE id=?", (patch_id,))
        conn.commit()
    finally:
        conn.close()
    return _get_patch(patch_id)


def list_patches(session_id=None, status=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        sql = "SELECT * FROM patches"
        wheres, args = [], []
        if session_id is not None:
            wheres.append("session_id=?")
            args.append(session_id)
        if status:
            wheres.append("status=?")
            args.append(status)
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        sql += " ORDER BY id DESC"
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def _get_patch(pid):
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM patches WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def _now():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
