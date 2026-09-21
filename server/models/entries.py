"""词条库与词频缓存 数据访问。"""
import json

from server.db import get_conn


def create_entry(book_id, name, category=None, aliases=None, description=None,
                 first_chapter_id=None, kb_item_id=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO entries(book_id, name, category, aliases_json, description, first_chapter_id, kb_item_id)
               VALUES (?,?,?,?,?,?,?)""",
            (book_id, name, category,
             json.dumps(aliases or [], ensure_ascii=False), description, first_chapter_id, kb_item_id),
        )
        conn.commit()
        return get_entry(cur.lastrowid, conn)
    except Exception:
        # 同名已存在则返回既有
        r = conn.execute("SELECT * FROM entries WHERE book_id IS ? AND name=?", (book_id, name)).fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()


def get_entry(eid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        r = conn.execute("SELECT * FROM entries WHERE id=?", (eid,)).fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()


def list_entries(book_id=None, category=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        sql = "SELECT * FROM entries"
        wh, args = [], []
        if book_id is not None:
            wh.append("book_id=?")
            args.append(book_id)
        if category:
            wh.append("category=?")
            args.append(category)
        if wh:
            sql += " WHERE " + " AND ".join(wh)
        sql += " ORDER BY id DESC"
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        if own:
            conn.close()


def update_entry(eid, fields, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cols, vals = [], []
        for f in ("name", "category", "description", "first_chapter_id", "kb_item_id"):
            if f in fields:
                cols.append(f"{f}=?")
                vals.append(fields[f])
        if "aliases" in fields:
            cols.append("aliases_json=?")
            vals.append(json.dumps(fields["aliases"], ensure_ascii=False))
        if not cols:
            return get_entry(eid, conn)
        cols.append("updated_at=datetime('now')")
        conn.execute(f"UPDATE entries SET {','.join(cols)} WHERE id=?", vals + [eid])
        conn.commit()
        return get_entry(eid, conn)
    finally:
        if own:
            conn.close()


def delete_entry(eid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.execute("DELETE FROM entries WHERE id=?", (eid,))
        conn.commit()
    finally:
        if own:
            conn.close()


def all_entry_names(book_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute("SELECT name, aliases_json FROM entries WHERE book_id=?", (book_id,)).fetchall()
        names = set()
        for r in rows:
            names.add(r["name"])
            try:
                names.update(json.loads(r["aliases_json"] or "[]"))
            except Exception:
                pass
        return names
    finally:
        if own:
            conn.close()


# ---------- 词频缓存 ----------
def save_word_freq(book_id, freq: dict, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.execute("DELETE FROM word_freq_cache WHERE book_id IS ?", (book_id,))
        for w, c in freq.items():
            conn.execute(
                "INSERT OR REPLACE INTO word_freq_cache(book_id, word, count, updated_at) VALUES (?,?,?,datetime('now'))",
                (book_id, w, c),
            )
        conn.commit()
    finally:
        if own:
            conn.close()


def get_word_freq(book_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute(
            "SELECT word, count FROM word_freq_cache WHERE book_id IS ? ORDER BY count DESC", (book_id,)
        ).fetchall()
        return [(r["word"], r["count"]) for r in rows]
    finally:
        if own:
            conn.close()
