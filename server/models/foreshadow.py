"""伏笔与伏笔事件 数据访问。"""
from server.db import get_conn

VALID_STATUS = {"planned", "planted", "called", "resolved", "abandoned"}
VALID_ACTIONS = {"create", "plant", "call", "resolve", "abandon", "reopen"}
ACTION_STATUS = {
    "plant": "planted", "call": "called", "resolve": "resolved",
    "abandon": "abandoned", "reopen": "planted",
}


def create_foreshadowing(book_id, title, content=None, importance=3, keywords=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO foreshadowings(book_id, title, content, importance, keywords) VALUES (?,?,?,?,?)",
            (book_id, title, content, int(importance or 3), keywords),
        )
        conn.commit()
        fid = cur.lastrowid
        add_event(fid, "create", None, conn=conn)
        return get_foreshadowing(fid, conn)
    finally:
        if own:
            conn.close()


def get_foreshadowing(fid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        r = conn.execute("SELECT * FROM foreshadowings WHERE id=?", (fid,)).fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()


def list_foreshadowings(book_id=None, status=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        sql = "SELECT * FROM foreshadowings"
        wh, args = [], []
        if book_id is not None:
            wh.append("book_id=?")
            args.append(book_id)
        if status:
            wh.append("status=?")
            args.append(status)
        if wh:
            sql += " WHERE " + " AND ".join(wh)
        sql += " ORDER BY importance DESC, id DESC"
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def update_foreshadowing(fid, fields, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cols, vals = [], []
        for f in ("title", "content", "keywords", "planted_chapter_id", "resolved_chapter_id"):
            if f in fields:
                cols.append(f"{f}=?")
                vals.append(fields[f])
        if "importance" in fields:
            cols.append("importance=?")
            vals.append(int(fields["importance"]))
        if not cols:
            return get_foreshadowing(fid, conn)
        cols.append("updated_at=datetime('now')")
        conn.execute(f"UPDATE foreshadowings SET {','.join(cols)} WHERE id=?", vals + [fid])
        conn.commit()
        return get_foreshadowing(fid, conn)
    finally:
        if own:
            conn.close()


def set_status(fid, status, chapter_id=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cols = ["status=?"]
        vals = [status]
        if status == "planted" and chapter_id:
            cols.append("planted_chapter_id=?")
            vals.append(chapter_id)
        if status == "resolved" and chapter_id:
            cols.append("resolved_chapter_id=?")
            vals.append(chapter_id)
        cols.append("updated_at=datetime('now')")
        conn.execute(f"UPDATE foreshadowings SET {','.join(cols)} WHERE id=?", vals + [fid])
        conn.commit()
        return get_foreshadowing(fid, conn)
    finally:
        if own:
            conn.close()


def delete_foreshadowing(fid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.execute("DELETE FROM foreshadow_events WHERE foreshadowing_id=?", (fid,))
        conn.execute("DELETE FROM foreshadowings WHERE id=?", (fid,))
        conn.commit()
    finally:
        if own:
            conn.close()


def add_event(fid, action, chapter_id=None, note=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO foreshadow_events(foreshadowing_id, action, chapter_id, note) VALUES (?,?,?,?)",
            (fid, action, chapter_id, note),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM foreshadow_events WHERE id=?", (cur.lastrowid,)).fetchone())
    finally:
        if own:
            conn.close()


def list_events(fid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM foreshadow_events WHERE foreshadowing_id=? ORDER BY id", (fid,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()
