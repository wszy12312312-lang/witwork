"""会话服务：建会话、流式生成、持久化。

流式以生成器产出事件字典，由 API 层包成 SSE。
事件类型：refs(一次) / delta(多次) / done / error。

Step 7：生成前调用知识库检索注入检索文本 + 引用卡，并注入当前人格文本；
生成后从输出抽取结构化写回补丁落库（自动落库策略），assistant 消息带 refs_json。
"""
from server.adapters.llm import get_adapter, LLMError
from server.adapters.tokenizer import estimate_tokens
from server.config import get as cfg_get
from server.models import sessions as sm, providers as pm
from server.services import context as ctx_mod
from server.services.knowledge import get_service as get_kb
from server.services import persona as persona_svc
from server.services import foreshadow as fs_svc
from server.services import character as char_svc
from server.core import extractor
from server.core import patch as patch_core


def _default_enabled_provider_id():
    """未显式指定时，优先用 config.default_provider_id（若启用），否则第一个启用的。"""
    dpid = cfg_get("default_provider_id")
    defaults = pm.list_providers()
    enabled = [p for p in defaults if p.get("enabled")]
    for p in enabled:
        if p["id"] == dpid:
            return p["id"]
    return enabled[0]["id"] if enabled else None


def create_session(book_id=None, title=None, provider_id=None):
    if not provider_id:
        provider_id = _default_enabled_provider_id()
    return sm.create_session(book_id=book_id, title=title, provider_id=provider_id)


def _resolve_provider(provider_id):
    if provider_id:
        p = pm.get_provider(provider_id)
        if p and p.get("enabled"):
            return p
    defaults = pm.list_providers()
    enabled = [p for p in defaults if p.get("enabled")]
    dpid = cfg_get("default_provider_id")
    for p in enabled:
        if p["id"] == dpid:
            return p
    if not enabled:
        return None
    # 与 ai_ops 保持一致：兜底避开 mock 演示占位模型
    real = [p for p in enabled if (p.get("kind") or "").lower() != "mock"]
    return real[0] if real else enabled[0]


def _retrieve_and_persona(session_id, user_content, book_id=None):
    """检索 + 人格 + 伏笔/人物卡注入文本（Step 7 / 12.4 / 13.4）。"""
    kb = get_kb()
    hits = kb.retrieve(user_content)
    citations = kb.format_citations(hits)
    retrieval_text = kb.format_retrieval_text(hits)
    persona_text = persona_svc.build_persona_text(session_id)
    ftext = ""
    if book_id:
        parts = []
        fi = fs_svc.injection_text(book_id)
        if fi:
            parts.append("[伏笔清单（未回收）]\n" + fi)
        ci = char_svc.build_injection_text(book_id, chapter_text=user_content)
        if ci:
            parts.append("[出场人物卡]\n" + ci)
        ftext = "\n".join(parts)
    return citations, retrieval_text, persona_text, ftext


def _finalize_assistant(session_id, full, citations, provider_snapshot):
    """剥离补丁围栏、抽取写回提议落库、存干净正文（带引用）。"""
    clean = extractor.strip_patches(full)
    auto = bool(cfg_get("auto_writeback", False))
    for p in extractor.extract_patches(full):
        try:
            patch_core.propose(p, session_id=session_id, auto=auto)
        except Exception:
            pass
    return sm.add_message(session_id, "assistant", clean, provider_snapshot=provider_snapshot,
                           token_count=estimate_tokens(clean), refs=citations)


def send_message_stream(session_id, user_content, provider_id=None, params=None):
    """生成器：产出 {type, data} 事件。"""
    session = sm.get_session(session_id)
    if not session:
        yield {"type": "error", "data": "会话不存在"}
        return

    provider = _resolve_provider(provider_id or session.get("active_provider_id"))
    if not provider:
        yield {"type": "error", "data": "没有可用的模型 provider，请先在设置中添加"}
        return

    sm.add_message(session_id, "user", user_content)
    if provider_id and provider_id != session.get("active_provider_id"):
        sm.update_session(session_id, {"active_provider_id": provider_id})

    # 检索 + 人格 + 伏笔/人物卡（Step 7 / 12 / 13）
    citations, retrieval_text, persona_text, ftext = _retrieve_and_persona(
        session_id, user_content, book_id=session.get("book_id")
    )
    yield {"type": "refs", "data": citations}

    try:
        adapter = get_adapter(provider)
    except LLMError as e:
        yield {"type": "error", "data": f"provider 初始化失败：{e}"}
        return

    builder = ctx_mod.ContextBuilder()
    ctx = builder.build(session_id, provider, adapter, persona_text=persona_text,
                        retrieval_text=retrieval_text, foreshadow_text=ftext)
    llm_messages = ctx["messages"]
    caps = adapter.capabilities()
    provider_snapshot = {"kind": provider["kind"], "model": provider.get("model")}

    if not caps.get("streaming"):
        try:
            full = _collect(adapter, llm_messages, params)
            msg = _finalize_assistant(session_id, full, citations, provider_snapshot)
            yield {"type": "delta", "data": extractor.strip_patches(full)}
            yield {"type": "done", "data": {"tokens": estimate_tokens(full), "summarized": ctx.get("summarized"),
                                            "message_id": msg["id"]}}
        except LLMError as e:
            yield {"type": "error", "data": str(e)}
        return

    try:
        buf = []
        for delta in adapter.stream(llm_messages, params):
            buf.append(delta)
            yield {"type": "delta", "data": delta}
        full = "".join(buf)
        msg = _finalize_assistant(session_id, full, citations, provider_snapshot)
        yield {"type": "done", "data": {"tokens": estimate_tokens(full), "ctx_tokens": ctx.get("tokens"),
                                        "summarized": ctx.get("summarized"), "message_id": msg["id"]}}
    except LLMError as e:
        yield {"type": "error", "data": str(e)}
    except Exception as e:
        yield {"type": "error", "data": f"生成中断：{e}"}


def _collect(adapter, messages, params):
    return "".join(adapter.stream(messages, params))
