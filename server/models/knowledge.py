"""分区知识库数据访问（无业务逻辑）。"""
from server.db import get_conn


# ---------- 分区 ----------
def list_sections(conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute("SELECT * FROM kb_sections ORDER BY built_in DESC, id ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def get_section(key, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        r = conn.execute("SELECT * FROM kb_sections WHERE key=?", (key,)).fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()


def create_section(key, title, description=None, built_in=0, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO kb_sections(key, title, description, built_in) VALUES (?,?,?,?)",
            (key, title, description, built_in),
        )
        conn.commit()
        return get_section(key, conn)
    finally:
        if own:
            conn.close()


def ensure_section(key, title, description=None, conn=None):
    existing = get_section(key, conn)
    if existing:
        return existing
    return create_section(key, title, description, conn=conn)


# ---------- 条目 ----------
def list_items(section=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        if section:
            rows = conn.execute(
                "SELECT * FROM kb_items WHERE section=? ORDER BY updated_at DESC, id DESC", (section,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM kb_items ORDER BY updated_at DESC, id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def get_item(item_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        r = conn.execute("SELECT * FROM kb_items WHERE id=?", (item_id,)).fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()


def create_item(section, title, content="", source_type="manual", source_ref=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO kb_items(section, title, content, source_type, source_ref) VALUES (?,?,?,?,?)",
            (section, title, content, source_type, source_ref),
        )
        conn.commit()
        return get_item(cur.lastrowid, conn)
    finally:
        if own:
            conn.close()


def update_item(item_id, title=None, content=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        sets, vals = [], []
        if title is not None:
            sets.append("title=?")
            vals.append(title)
        if content is not None:
            sets.append("content=?")
            vals.append(content)
        if not sets:
            return get_item(item_id, conn)
        sets.append("updated_at=datetime('now')")
        conn.execute(f"UPDATE kb_items SET {','.join(sets)} WHERE id=?", vals + [item_id])
        conn.commit()
        return get_item(item_id, conn)
    finally:
        if own:
            conn.close()


def delete_item(item_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        old = conn.execute("SELECT id FROM kb_chunks WHERE item_id=?", (item_id,)).fetchall()
        for r in old:
            conn.execute("DELETE FROM kb_fts WHERE rowid=?", (r["id"],))
        conn.execute("DELETE FROM kb_chunks WHERE item_id=?", (item_id,))
        conn.execute("DELETE FROM kb_item_versions WHERE item_id=?", (item_id,))
        conn.execute("DELETE FROM kb_items WHERE id=?", (item_id,))
        conn.commit()
    finally:
        if own:
            conn.close()


# ---------- 版本 ----------
def add_version(item_id, content, reason=None, source_message_id=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO kb_item_versions(item_id, content, reason, source_message_id) VALUES (?,?,?,?)",
            (item_id, content, reason, source_message_id),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM kb_item_versions WHERE id=?", (cur.lastrowid,)).fetchone())
    finally:
        if own:
            conn.close()


def list_versions(item_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM kb_item_versions WHERE item_id=? ORDER BY id DESC", (item_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def set_current_version(item_id, version_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.execute("UPDATE kb_items SET current_version_id=? WHERE id=?", (version_id, item_id))
        conn.commit()
    finally:
        if own:
            conn.close()


# ---------- 切块 + 向量 ----------
def replace_chunks(item_id, chunks, conn=None):
    """chunks: [(text, embedding_blob, tokens), ...]。删除旧块与 FTS，写入新块。"""
    own = conn is None
    conn = conn or get_conn()
    try:
        old = conn.execute("SELECT id FROM kb_chunks WHERE item_id=?", (item_id,)).fetchall()
        for r in old:
            conn.execute("DELETE FROM kb_fts WHERE rowid=?", (r["id"],))
        conn.execute("DELETE FROM kb_chunks WHERE item_id=?", (item_id,))
        for idx, (text, blob, tokens) in enumerate(chunks):
            cur = conn.execute(
                "INSERT INTO kb_chunks(item_id, idx, text, embedding, tokens) VALUES (?,?,?,?,?)",
                (item_id, idx, text, blob, tokens),
            )
            cid = cur.lastrowid
            conn.execute("INSERT INTO kb_fts(rowid, text) VALUES (?,?)", (cid, text))
        conn.commit()
    finally:
        if own:
            conn.close()


def list_chunks(item_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute(
            "SELECT id, item_id, idx, text, embedding, tokens FROM kb_chunks WHERE item_id=? ORDER BY idx ASC",
            (item_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def candidate_chunks(sections=None, conn=None):
    """检索候选：返回块及其所属 item 的分区/标题，用于向量与关键词打分。"""
    own = conn is None
    conn = conn or get_conn()
    try:
        sql = (
            "SELECT c.id, c.item_id, c.idx, c.text, c.embedding, i.section, i.title "
            "FROM kb_chunks c JOIN kb_items i ON i.id=c.item_id"
        )
        args = []
        if sections:
            ph = ",".join("?" for _ in sections)
            sql += f" WHERE i.section IN ({ph})"
            args = list(sections)
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def fts_match(query, sections=None, conn=None):
    """FTS5 trigram 匹配（查询≥3字）。返回 {chunk_id: bm25_score}。"""
    if len(query.strip()) < 3:
        return {}
    own = conn is None
    conn = conn or get_conn()
    try:
        sql = (
            "SELECT c.id AS chunk_id, bm25(kb_fts) AS s "
            "FROM kb_fts f JOIN kb_chunks c ON c.id=f.rowid "
            "JOIN kb_items i ON i.id=c.item_id "
            "WHERE kb_fts MATCH ?"
        )
        args = [query]
        if sections:
            ph = ",".join("?" for _ in sections)
            sql += f" AND i.section IN ({ph})"
            args += list(sections)
        rows = conn.execute(sql, args).fetchall()
        return {r["chunk_id"]: r["s"] for r in rows}
    except Exception:
        return {}
    finally:
        if own:
            conn.close()


def like_match(query, sections=None, conn=None):
    """LIKE 兜底（含 <3 字短词）。返回命中 chunk_id 集合。"""
    own = conn is None
    conn = conn or get_conn()
    try:
        sql = (
            "SELECT c.id AS chunk_id FROM kb_chunks c JOIN kb_items i ON i.id=c.item_id "
            "WHERE c.text LIKE ?"
        )
        args = ["%" + query + "%"]
        if sections:
            ph = ",".join("?" for _ in sections)
            sql += f" AND i.section IN ({ph})"
            args += list(sections)
        rows = conn.execute(sql, args).fetchall()
        return {r["chunk_id"] for r in rows}
    finally:
        if own:
            conn.close()


DEFAULT_SECTIONS = [
    ("worldview", "世界观"), ("geography", "地理"), ("faction", "势力"), ("plot", "情节"),
    ("character", "人物"), ("style", "文风"), ("timeline", "时间线"), ("misc", "杂项"),
]


def seed_default_sections():
    """幂等：种入 8 个默认分区。"""
    for key, title in DEFAULT_SECTIONS:
        ensure_section(key, title)

