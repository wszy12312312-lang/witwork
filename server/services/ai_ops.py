"""AI 正文操作引擎：在写作页面直接对原文做 改写/续写/扩写/缩写/创作，以及通读全书给修改意见。

与框架共创（cocreation）不同，这里操作的是「当前正在写的文本」：
- rewrite / expand / shrink：作用于选区（或整章），返回替换后的正文
- continue：在选区/章末之后续写
- create：依据作者方向创作全新段落（参考上下文保持风格一致）
- review：读取全书正文，给出修改意见（不改动正文）

流式以生成器产出事件字典，由 API 层包成 SSE：refs(一次) / delta(多次) / done / error。
"""
from __future__ import annotations

from server.adapters.llm import get_adapter, LLMError
from server.adapters.tokenizer import estimate_tokens
from server.config import get as cfg_get
from server.models import providers as pm, chapters as cm, books as bm

# 上下文软上限（字符），超过则截断，避免超出模型上下文
BOOK_CONTEXT_CAP = 60000

OPERATIONS = {
    "rewrite": "改写",
    "continue": "续写",
    "expand": "扩写",
    "shrink": "缩写",
    "create": "创作",
    "review": "通读全书修改意见",
    "gen_outline": "想法转大纲",
    "gen_from_outline": "按大纲生成正文",
}

_SYSTEM = {
    "rewrite": (
        "你是一位与作者并肩写作的资深小说家。下面【原文】是作者写的一段文字，【方向】是作者希望调整的大致想法。"
        "请严格按【方向】改写【原文】：保持作者原有文风、人称、视角与基本情节，只改动作者希望调整的部分。"
        "直接输出改写后的完整正文，不要任何解释、不要标题、不要使用代码块或 Markdown 围栏。"
    ),
    "continue": (
        "你是作者的同写作家。请严格顺着【上文】的文风、视角、情绪与剧情走向，自然续写接下来的内容。"
        "不要重复【上文】已有文字，不要总结，直接写出新的续写正文。只输出续写内容，不要解释或标题。"
    ),
    "expand": (
        "请在不改变原意、不改变文风的前提下，对【原文】进行扩写：补充感官细节、人物心理、环境氛围或动作层次，"
        "使文字更丰满生动。直接输出扩写后的完整段落（包含原文并做扩展），不要解释或标题。"
    ),
    "shrink": (
        "请压缩【原文】，保留核心情节、关键信息与原有文风，删除冗余与啰嗦表达，使文字更紧凑有力。"
        "直接输出缩写后的正文，不要解释或标题。"
    ),
    "create": (
        "请根据【方向】创作一段全新的小说正文。可参考【上下文】把握作品的整体文风、世界观与人物，"
        "使新内容与已有文本风格一致、可自然衔接。直接输出正文，不要解释、不要另起标题（除非情节需要）。"
    ),
    "review": (
        "你是资深文学编辑。请通读整部作品（【全书正文】），结合【方向】（若提供）给出具体、可操作的修改意见。"
        "按「问题类型 → 具体位置（章节/大致段落）→ 修改建议」组织，至少覆盖：节奏与拖沓、信息密度、"
        "人物一致性、伏笔与呼应、对话自然度、语病与冗余、逻辑漏洞。不要改写正文，只列修改意见，可用 Markdown 列表。"
    ),
    "gen_outline": (
        "你是一位资深小说架构师。作者给了你一个写作想法或若干素材要点（【创作想法】），"
        "请据此生成一份结构清晰、可执行的章节大纲。大纲应列出本节要写的核心情节节点、场景顺序、"
        "人物动作与情绪走向、关键细节与伏笔位置，用有序列表或分层条目呈现，便于后续据此生成正文。"
        "不要写正文，只给大纲，语言精炼、可执行。"
    ),
    "gen_from_outline": (
        "你是一位与作者并肩写作的资深小说家。下面是作者拟定的【大纲】（有序的情节 / 场景条目）。"
        "请严格按大纲的顺序与要点，扩写成一份完整、连贯、有文学质感的章节正文：保持文风统一，"
        "把每个提纲要点都充分展开为具体描写与对话，人物言行符合设定，节奏自然。"
        "直接输出正文，不要解释、不要另起标题（除非剧情需要）。"
    ),
}


def _resolve_provider(provider_id):
    if provider_id:
        p = pm.get_provider(provider_id)
        if p and p.get("enabled"):
            return p
    defaults = pm.list_providers()
    enabled = [p for p in defaults if p.get("enabled")]
    return enabled[0] if enabled else None


def _book_context(book_id: int | None) -> str:
    """拼接全书正文（含章节标题），用于 create/review 的上下文。超长截断。"""
    if not book_id:
        return ""
    chs = cm.list_chapters(book_id)
    if not chs:
        return ""
    parts = []
    total = 0
    for ch in chs:
        full = cm.get_chapter(ch["id"])
        if not full:
            continue
        body = full.get("content") or ""
        if not body.strip():
            continue
        block = f"## 《{ch.get('title') or '未命名'}》\n{body}"
        if total + len(block) > BOOK_CONTEXT_CAP:
            # 截断到上限
            remain = BOOK_CONTEXT_CAP - total
            if remain > 200:
                parts.append(block[:remain] + "\n…（已截断）")
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)


def operate_stream(
    book_id,
    chapter_id,
    operation,
    text,
    instruction,
    scope,
    provider_id=None,
    params=None,
):
    """生成器：产出 {type, data} 事件。

    text: 当前传入的源文本（选区或整章）；scope=book 时忽略 text，改用全书正文。
    instruction: 作者的大体方向（可为空）。
    """
    if operation not in OPERATIONS:
        yield {"type": "error", "data": f"未知操作：{operation}"}
        return

    provider = _resolve_provider(provider_id)
    if not provider:
        yield {"type": "error", "data": "没有可用的模型 provider，请先在设置中添加"}
        return

    # 取上下文
    if scope == "book":
        context_text = _book_context(book_id)
        src_text = ""
    else:
        # 当前章用于上下文（create/continue 参考风格）
        context_text = _book_context(book_id) if operation in ("create", "continue") else ""
        # 单章正文（用于 continue 的「上文」）
        if chapter_id and operation == "continue":
            ch = cm.get_chapter(chapter_id)
            src_text = (ch.get("content") or "") if ch else (text or "")
        else:
            src_text = text or ""

    instruction = (instruction or "").strip()

    # 组装 user 内容
    if operation == "review":
        user_content = "【全书正文】\n" + (context_text or "（该书暂无正文）")
        if instruction:
            user_content += f"\n\n【方向】\n{instruction}"
    elif operation == "create":
        user_content = ""
        if context_text:
            user_content += "【上下文（供把握风格）】\n" + context_text + "\n\n"
        user_content += "【方向】\n" + (instruction or "（请自由发挥，写一段精彩的小说正文）")
    elif operation == "gen_outline":
        user_content = "【创作想法】\n" + (instruction or text or "（请自由发挥，给出一个写作想法）")
    elif operation == "gen_from_outline":
        user_content = "【大纲】\n" + (text or instruction or "（请给出一个大纲）")
        extra = instruction if instruction and instruction != (text or "") else ""
        if extra:
            user_content += f"\n\n【补充方向】\n{extra}"
    elif operation == "continue":
        user_content = "【上文】\n" + (src_text or text or "")
    else:  # rewrite / expand / shrink
        user_content = "【原文】\n" + (src_text or text or "")
        if instruction:
            user_content += f"\n\n【方向】\n{instruction}"

    messages = [
        {"role": "system", "content": _SYSTEM[operation]},
        {"role": "user", "content": user_content},
    ]

    try:
        adapter = get_adapter(provider)
    except LLMError as e:
        yield {"type": "error", "data": f"provider 初始化失败：{e}"}
        return

    yield {"type": "refs", "data": []}
    caps = adapter.capabilities()
    provider_snapshot = {"kind": provider["kind"], "model": provider.get("model")}

    if not caps.get("streaming"):
        try:
            full = "".join(adapter.stream(messages, params))
            yield {"type": "delta", "data": full}
            yield {"type": "done", "data": {"tokens": estimate_tokens(full), "operation": operation,
                                            "provider": provider_snapshot}}
        except LLMError as e:
            yield {"type": "error", "data": str(e)}
        return

    try:
        buf = []
        for delta in adapter.stream(messages, params):
            buf.append(delta)
            yield {"type": "delta", "data": delta}
        full = "".join(buf)
        yield {"type": "done", "data": {"tokens": estimate_tokens(full), "operation": operation,
                                        "provider": provider_snapshot}}
    except LLMError as e:
        yield {"type": "error", "data": str(e)}
    except Exception as e:
        yield {"type": "error", "data": f"生成中断：{e}"}
