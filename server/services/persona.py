"""人格服务：有效人格文本构建、自然语言调整（overlay 即时生效并记版本）。

人格文本 = 基础 system_prompt + 本次会话 overlay（来自 sessions.framework_state_json.persona_overlay）。
overlay 包含 statements（原话，必记）与 fields（从 LLM 解析出的字段覆盖，尽力而为）。
"""
import json

from server.adapters.llm import get_adapter, LLMError
from server.models import personas as pm, sessions as sm


def active_persona():
    return pm.get_active()


def build_persona_text(session_id=None):
    """返回注入上下文的有效人格系统提示词。"""
    p = pm.get_active()
    if not p:
        return ""
    base = p.get("system_prompt") or ""
    overlay = _load_overlay(session_id) if session_id else None
    extra = []
    if overlay:
        for s in overlay.get("statements", []):
            extra.append("【本会话人格覆盖】" + s)
        if overlay.get("fields"):
            extra.append("【本会话人格字段覆盖】" + json.dumps(overlay["fields"], ensure_ascii=False))
    if extra:
        return base + "\n\n" + "\n".join(extra)
    return base


def _load_overlay(session_id):
    s = sm.get_session(session_id) if session_id else None
    if not s:
        return {}
    try:
        st = json.loads(s.get("framework_state_json") or "{}")
    except Exception:
        st = {}
    return st.get("persona_overlay", {})


def _save_overlay(session_id, overlay):
    s = sm.get_session(session_id) if session_id else None
    if not s:
        return
    try:
        st = json.loads(s.get("framework_state_json") or "{}")
    except Exception:
        st = {}
    st["persona_overlay"] = overlay
    sm.update_session(session_id, {"framework_state_json": json.dumps(st, ensure_ascii=False)})


def parse_adjust(session_id, statement):
    """自然语言调整人格：解析字段覆盖（尽力而为）+ 记录原话，立即作为 overlay 生效。"""
    p = pm.get_active()
    overlay = _load_overlay(session_id)
    if "statements" not in overlay:
        overlay["statements"] = []
    if "fields" not in overlay:
        overlay["fields"] = {}

    prompt = (
        "你是人格解析器。基于当前人格设定，把用户的自然语言调整指令解析为可覆盖的字段 JSON。\n"
        f"当前人格：{json.dumps(_persona_public(p), ensure_ascii=False)}\n"
        f"用户指令：{statement}\n"
        "只输出 JSON：{\"fields\":{可覆盖字段}, \"note\":\"一句话说明\"}。"
        "可覆盖字段仅限：tone, style_tags(数组), focus, methods(数组), temperature(数字), forbidden(数组)。"
        "若无明确字段变化，fields 为空对象。"
    )
    fields = {}
    try:
        provider = sm.get_session(session_id) if session_id else None
        pid = provider.get("active_provider_id") if provider else None
        from server.models import providers as prov_m
        prov = prov_m.get_provider(pid) if pid else None
        if prov:
            adapter = get_adapter(prov)
            out = "".join(adapter.stream([{"role": "user", "content": prompt}], {"temperature": 0.2}))
            fields = _parse_fields(out)
    except (LLMError, Exception):
        fields = {}

    if fields:
        overlay["fields"].update(fields)
    overlay["statements"].append(statement)
    _save_overlay(session_id, overlay)

    # 记版本（含原话）
    if p:
        snapshot = _persona_public(p)
        snapshot["overlay_at_adjust"] = overlay
        pm.add_version(p["id"], snapshot, note=f"调整：{statement}")

    return {"overlay": overlay, "fields": fields}


def _persona_public(p):
    if not p:
        return {}
    return {
        "name": p.get("name"),
        "tone": p.get("tone"),
        "style_tags": json.loads(p.get("style_tags_json") or "[]"),
        "focus": p.get("focus"),
        "methods": json.loads(p.get("methods_json") or "[]"),
        "temperature": p.get("temperature"),
        "forbidden": json.loads(p.get("forbidden_json") or "[]"),
    }


def _parse_fields(text):
    try:
        s = text[text.index("{"):]
        s = s[: s.rindex("}") + 1]
        obj = json.loads(s)
        f = obj.get("fields") or {}
        allowed = {"tone", "style_tags", "focus", "methods", "temperature", "forbidden"}
        return {k: v for k, v in f.items() if k in allowed}
    except Exception:
        return {}
