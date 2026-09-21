"""人格数据访问。"""
import json

from server.db import get_conn


def list_personas(conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute("SELECT * FROM personas ORDER BY built_in DESC, active DESC, id ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def get_persona(pid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        r = conn.execute("SELECT * FROM personas WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()


def get_active(conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        r = conn.execute("SELECT * FROM personas WHERE active=1 ORDER BY id ASC").fetchone()
        if not r:
            r = conn.execute("SELECT * FROM personas ORDER BY built_in DESC, id ASC").fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()


def create_persona(data: dict, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO personas(name, system_prompt, tone, style_tags_json, focus, methods_json, temperature, forbidden_json, is_default, active, built_in)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data.get("name", "未命名人格"),
                data.get("system_prompt", ""),
                data.get("tone"),
                json.dumps(data.get("style_tags") or [], ensure_ascii=False),
                data.get("focus"),
                json.dumps(data.get("methods") or [], ensure_ascii=False),
                float(data.get("temperature", 0.8)),
                json.dumps(data.get("forbidden") or [], ensure_ascii=False),
                1 if data.get("is_default") else 0,
                1 if data.get("active") else 0,
                1 if data.get("built_in") else 0,
            ),
        )
        conn.commit()
        return get_persona(cur.lastrowid, conn)
    finally:
        if own:
            conn.close()


def update_persona(pid, data: dict, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cols = []
        vals = []
        for f in ("name", "system_prompt", "tone", "focus", "temperature"):
            if f in data:
                cols.append(f"{f}=?")
                vals.append(data[f])
        if "style_tags" in data:
            cols.append("style_tags_json=?")
            vals.append(json.dumps(data["style_tags"], ensure_ascii=False))
        if "methods" in data:
            cols.append("methods_json=?")
            vals.append(json.dumps(data["methods"], ensure_ascii=False))
        if "forbidden" in data:
            cols.append("forbidden_json=?")
            vals.append(json.dumps(data["forbidden"], ensure_ascii=False))
        if "active" in data:
            cols.append("active=?")
            vals.append(1 if data["active"] else 0)
        if not cols:
            return get_persona(pid, conn)
        cols.append("updated_at=datetime('now')")
        conn.execute(f"UPDATE personas SET {','.join(cols)} WHERE id=?", vals + [pid])
        conn.commit()
        return get_persona(pid, conn)
    finally:
        if own:
            conn.close()


def set_active(pid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.execute("UPDATE personas SET active=0")
        conn.execute("UPDATE personas SET active=1 WHERE id=?", (pid,))
        conn.commit()
    finally:
        if own:
            conn.close()


def delete_persona(pid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.execute("DELETE FROM persona_versions WHERE persona_id=?", (pid,))
        conn.execute("DELETE FROM personas WHERE id=?", (pid,))
        conn.commit()
    finally:
        if own:
            conn.close()


def add_version(pid, snapshot: dict, note=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO persona_versions(persona_id, snapshot_json, note) VALUES (?,?,?)",
            (pid, json.dumps(snapshot, ensure_ascii=False), note),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM persona_versions WHERE id=?", (cur.lastrowid,)).fetchone())
    finally:
        if own:
            conn.close()


def list_versions(pid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute("SELECT * FROM persona_versions WHERE persona_id=? ORDER BY id DESC", (pid,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def seed_default():
    """幂等：无 built_in 人格时种入默认万维文人格。"""
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM personas WHERE built_in=1 LIMIT 1").fetchone():
            return
        create_persona({
            "name": "默认万维文",
            "system_prompt": (
                "你是小说家的写作协作者「万维文」。你深谙长篇叙事，尊重作者已建立的世界观、人物与时间线。"
                "回答优先依据知识库检索结果，不得与设定矛盾；引用资料时末尾标注【引用】[n]。"
                "语气克制、专业，少废话。涉及新增或修正设定时，用 ```json{\"patches\":[...]}``` 提出结构化写回提议，"
                "不要直接编造与已有设定冲突的内容。"
            ),
            "tone": "克制、专业、少形容词",
            "style_tags": ["长篇", "世界观一致", "强逻辑"],
            "focus": "一致性优先、设定可追溯",
            "methods": ["三幕", "英雄之旅", "雪花"],
            "temperature": 0.7,
            "forbidden": ["与已有人物重名", "无依据的时间跳跃"],
            "is_default": True,
            "active": True,
            "built_in": True,
        }, conn)
    finally:
        conn.close()
