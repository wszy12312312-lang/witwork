"""providers 数据访问 + 默认种子。"""
import json

from server.db import get_conn
from server.config import save_config, get

_KINDS_DEFAULT = {
    "mock": {
        "name": "本地演示 (mock)",
        "base_url": None,
        "model": "mock",
        "context_window": 8000,
        "is_local": 1,
    },
    "ollama": {
        "name": "本地 Ollama",
        "base_url": "http://127.0.0.1:11434",
        "model": "qwen2.5:7b",
        "context_window": 32768,
        "is_local": 1,
    },
}


def list_providers(conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM providers ORDER BY is_local DESC, id"
        ).fetchall()
        dpid = get("default_provider_id")
        out = []
        for r in rows:
            d = _row_to_dict(r)
            d["is_default"] = (d["id"] == dpid)
            out.append(d)
        return out
    finally:
        if own:
            conn.close()


def get_provider(pid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        r = conn.execute("SELECT * FROM providers WHERE id=?", (pid,)).fetchone()
        return _row_to_dict(r) if r else None
    finally:
        if own:
            conn.close()


def create_provider(fields: dict, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        pid = fields.get("id") or _slug(fields.get("name", "provider"))
        kind = fields.get("kind", "openai")
        data = {
            "id": pid,
            "kind": kind,
            "name": fields.get("name", pid),
            "base_url": fields.get("base_url"),
            "api_key_ref": fields.get("api_key_ref"),
            "model": fields.get("model"),
            "context_window": int(fields.get("context_window", 8000)),
            "is_local": 1 if fields.get("is_local") else 0,
            "enabled": 1 if fields.get("enabled", True) else 0,
            "extra_json": json.dumps(fields.get("extra") or {}, ensure_ascii=False) if fields.get("extra") else None,
        }
        conn.execute(
            """INSERT INTO providers(id,kind,name,base_url,api_key_ref,model,context_window,is_local,enabled,extra_json)
               VALUES (:id,:kind,:name,:base_url,:api_key_ref,:model,:context_window,:is_local,:enabled,:extra_json)
               ON CONFLICT(id) DO UPDATE SET
                 kind=excluded.kind, name=excluded.name, base_url=excluded.base_url,
                 model=excluded.model, context_window=excluded.context_window,
                 is_local=excluded.is_local, enabled=excluded.enabled, extra_json=excluded.extra_json,
                 updated_at=datetime('now')""",
            data,
        )
        conn.commit()
        return get_provider(pid, conn)
    finally:
        if own:
            conn.close()


def update_provider(pid, fields: dict, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cur = conn.execute("SELECT * FROM providers WHERE id=?", (pid,)).fetchone()
        if not cur:
            return None
        existing = _row_to_dict(cur)
        merged = {**existing, **{k: v for k, v in fields.items() if v is not None}}
        return create_provider(merged, conn)
    finally:
        if own:
            conn.close()


def delete_provider(pid, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.execute("DELETE FROM providers WHERE id=?", (pid,))
        # 若删除的是默认模型，清除默认标记，避免生成路径悬空
        if get("default_provider_id") == pid:
            save_config({"default_provider_id": None})
        conn.commit()
    finally:
        if own:
            conn.close()


def set_default_provider(pid, conn=None):
    """把某 provider 设为默认模型（写 config.default_provider_id）。"""
    own = conn is None
    conn = conn or get_conn()
    try:
        p = get_provider(pid, conn)
        if not p:
            return None
        save_config({"default_provider_id": pid})
        return pid
    finally:
        if own:
            conn.close()


def seed_defaults(conn=None):
    """保证至少有一个可用 provider；默认种子 mock + ollama。"""
    own = conn is None
    conn = conn or get_conn()
    try:
        existing = {r["id"] for r in conn.execute("SELECT id FROM providers").fetchall()}
        for pid, d in _KINDS_DEFAULT.items():
            if pid not in existing:
                create_provider({"id": pid, "kind": pid, **d}, conn)
        # 设置默认 provider（若未设置）
        if not get("default_provider_id"):
            first = conn.execute(
                "SELECT id FROM providers WHERE enabled=1 ORDER BY is_local DESC, id LIMIT 1"
            ).fetchone()
            if first:
                save_config({"default_provider_id": first["id"]})
    finally:
        if own:
            conn.close()


def _slug(name: str) -> str:
    s = "".join(ch for ch in name if ch.isalnum() or ch in "-_").lower()
    return s or "provider"


def _row_to_dict(r) -> dict:
    d = dict(r)
    if d.get("extra_json"):
        try:
            d["extra"] = json.loads(d["extra_json"])
        except json.JSONDecodeError:
            d["extra"] = {}
    else:
        d["extra"] = {}
    return d
