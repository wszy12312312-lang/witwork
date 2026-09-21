"""sessions / messages 数据访问。"""
import json

from server.db import get_conn


def create_session(book_id=None, title=None, provider_id=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO sessions(book_id, title, active_provider_id) VALUES (?,?,?)",
            (book_id, title, provider_id),
        )
        conn.commit()
        return get_session(cur.lastrowid, conn)
    finally:
        if own:
            conn.close()


def get_session(sid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        r = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()


def list_sessions(book_id=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        if book_id is not None:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE book_id=? ORDER BY updated_at DESC, id DESC", (book_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def update_session(sid, fields: dict, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cols = [c for c in fields if c in {"title", "active_provider_id", "summary_upto_message_id", "framework_state_json"}]
        if not cols:
            return get_session(sid, conn)
        sets = ", ".join(f"{c}=?" for c in cols) + ", updated_at=datetime('now')"
        vals = [fields[c] for c in cols] + [sid]
        conn.execute(f"UPDATE sessions SET {sets} WHERE id=?", vals)
        conn.commit()
        return get_session(sid, conn)
    finally:
        if own:
            conn.close()


def add_message(session_id, role, content, provider_snapshot=None, token_count=None,
                refs=None, is_summary=0, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        snap = json.dumps(provider_snapshot, ensure_ascii=False) if provider_snapshot else None
        refs_j = json.dumps(refs, ensure_ascii=False) if refs else None
        cur = conn.execute(
            """INSERT INTO messages(session_id, role, content, provider_snapshot_json, token_count, refs_json, is_summary)
               VALUES (?,?,?,?,?,?,?)""",
            (session_id, role, content, snap, token_count, refs_j, 1 if is_summary else 0),
        )
        conn.commit()
        rid = cur.lastrowid
        conn.execute("UPDATE sessions SET updated_at=datetime('now') WHERE id=?", (session_id,))
        conn.commit()
        r = conn.execute("SELECT * FROM messages WHERE id=?", (rid,)).fetchone()
        return dict(r)
    finally:
        if own:
            conn.close()


def list_messages(session_id, conn=None, after_id=None):
    """返回会话消息。

    after_id: 若提供，则只返回 id > after_id 的消息。用于滚动摘要场景，
    排除已经被压缩进摘要（summary_upto_message_id）的旧实时消息，避免
    它们重复进入上下文、造成摘要重复累积与上下文膨胀。
    """
    own = conn is None
    conn = conn or get_conn()
    try:
        if after_id is None:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id=? ORDER BY id ASC", (session_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id=? AND id>? ORDER BY id ASC",
                (session_id, after_id),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def replace_summary(session_id, text, upto_message_id=None, conn=None):
    """删除该会话旧摘要，写入新摘要，并推进 summary_upto_message_id。"""
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.execute("DELETE FROM messages WHERE session_id=? AND is_summary=1", (session_id,))
        cur = conn.execute(
            "INSERT INTO messages(session_id, role, content, is_summary) VALUES (?,?,?,1)",
            (session_id, "system", text),
        )
        conn.execute(
            "UPDATE sessions SET summary_upto_message_id=?, updated_at=datetime('now') WHERE id=?",
            (upto_message_id, session_id),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        if own:
            conn.close()


def delete_session(sid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
        conn.commit()
    finally:
        if own:
            conn.close()
