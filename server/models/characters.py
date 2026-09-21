"""人物 / 关系 / 出场记录 / 角色模板 数据访问。"""
import json

from server.db import get_conn


def create_character(book_id, name, fields=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    f = fields or {}
    try:
        cur = conn.execute(
            """INSERT INTO characters(book_id, name, aliases_json, appearance, personality,
               catchphrase, status_current, taboo, kb_item_id, template_id)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (book_id, name,
             json.dumps(f.get("aliases") or [], ensure_ascii=False),
             f.get("appearance"), f.get("personality"), f.get("catchphrase"),
             f.get("status_current"), f.get("taboo"),
             f.get("kb_item_id"), f.get("template_id")),
        )
        conn.commit()
        return get_character(cur.lastrowid, conn)
    finally:
        if own:
            conn.close()


def get_character(cid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        r = conn.execute("SELECT * FROM characters WHERE id=?", (cid,)).fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()


def list_characters(book_id=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        if book_id is not None:
            rows = conn.execute("SELECT * FROM characters WHERE book_id=? ORDER BY id", (book_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM characters ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def update_character(cid, fields, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cols, vals = [], []
        for f in ("name", "appearance", "personality", "catchphrase", "status_current", "taboo", "kb_item_id", "template_id"):
            if f in fields:
                cols.append(f"{f}=?")
                vals.append(fields[f])
        if "aliases" in fields:
            cols.append("aliases_json=?")
            vals.append(json.dumps(fields["aliases"], ensure_ascii=False))
        if not cols:
            return get_character(cid, conn)
        cols.append("updated_at=datetime('now')")
        conn.execute(f"UPDATE characters SET {','.join(cols)} WHERE id=?", vals + [cid])
        conn.commit()
        return get_character(cid, conn)
    finally:
        if own:
            conn.close()


def delete_character(cid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.execute("DELETE FROM character_relations WHERE from_id=? OR to_id=?", (cid, cid))
        conn.execute("DELETE FROM character_appearances WHERE character_id=?", (cid,))
        conn.execute("DELETE FROM characters WHERE id=?", (cid,))
        conn.commit()
    finally:
        if own:
            conn.close()


# ---------- 关系 ----------
def add_relation(book_id, from_id, to_id, relation, note=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO character_relations(book_id, from_id, to_id, relation, note) VALUES (?,?,?,?,?)",
            (book_id, from_id, to_id, relation, note),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM character_relations WHERE id=?", (cur.lastrowid,)).fetchone())
    finally:
        if own:
            conn.close()


def list_relations(book_id=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        if book_id is not None:
            rows = conn.execute(
                "SELECT * FROM character_relations WHERE book_id=? ORDER BY id", (book_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM character_relations ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def delete_relation(rid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.execute("DELETE FROM character_relations WHERE id=?", (rid,))
        conn.commit()
    finally:
        if own:
            conn.close()


# ---------- 出场记录 ----------
def add_appearance(character_id, chapter_id=None, summary=None, excerpt=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO character_appearances(character_id, chapter_id, summary, excerpt) VALUES (?,?,?,?)",
            (character_id, chapter_id, summary, excerpt),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM character_appearances WHERE id=?", (cur.lastrowid,)).fetchone())
    finally:
        if own:
            conn.close()


def list_appearances(character_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM character_appearances WHERE character_id=? ORDER BY id DESC", (character_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


# ---------- 角色模板 ----------
DEFAULT_TEMPLATES = [
    ("主角模板", "主角", ["appearance", "personality", "catchphrase", "status_current", "taboo"]),
    ("反派模板", "反派", ["appearance", "personality", "catchphrase", "status_current", "taboo"]),
    ("配角模板", "配角", ["appearance", "personality", "catchphrase", "status_current"]),
    ("群像模板", "群像", ["appearance", "personality"]),
    ("组织模板", "组织", ["personality", "status_current", "taboo"]),
]


def seed_templates():
    conn = get_conn()
    try:
        for name, cat, fields in DEFAULT_TEMPLATES:
            if conn.execute("SELECT 1 FROM role_library WHERE name=? AND built_in=1", (name,)).fetchone():
                continue
            conn.execute(
                "INSERT INTO role_library(name, category, fields_json, is_global, built_in) VALUES (?,?,?,1,1)",
                (name, cat, json.dumps(fields, ensure_ascii=False)),
            )
        conn.commit()
    finally:
        conn.close()


def list_templates(conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute("SELECT * FROM role_library ORDER BY built_in DESC, id").fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def get_template(tid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        r = conn.execute("SELECT * FROM role_library WHERE id=?", (tid,)).fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()


def create_template(name, category, fields, is_global=0, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO role_library(name, category, fields_json, is_global) VALUES (?,?,?,?)",
            (name, category, json.dumps(fields, ensure_ascii=False), is_global),
        )
        conn.commit()
        return get_template(cur.lastrowid, conn)
    finally:
        if own:
            conn.close()
