"""AI 正文操作引擎：在写作页面直接对原文做 改写/续写/扩写/缩写/创作，以及通读全书给修改意见。

与框架共创（cocreation）不同，这里操作的是「当前正在写的文本」：
- rewrite / expand / shrink：作用于选区（或整章），返回替换后的正文
- continue：在选区/章末之后续写
- create：依据作者方向创作全新段落（参考上下文保持风格一致）
- review：读取全书正文，给出修改意见（不改动正文）

流式以生成器产出事件字典，由 API 层包成 SSE：
  status(多次，阶段进度) / refs(一次) / delta(多次) / done / error

设计要点（本次重构）
1. 提示词分层：角色 → 任务 → 质量清单 → 硬性输出规则。规则部分统一注入，
   避免模型夹带「以下是改写后的内容」这类废话或 Markdown 围栏。
2. 上下文预算：按操作给不同的上下文量。续写只取章末上文、创作只取文风样本，
   避免把整本书塞进 prompt 拖慢首字延迟、甚至被模型上下文静默截断。
3. 温度按操作区分：改写/缩写偏低（稳），创作/续写偏高（活）。
4. 连接方式：provider 解析尊重用户设置的默认模型；生成前先发 status 事件，
   让前端在「等首字」这段时间里也能显示真实进度，而不是一片空白。
"""
from __future__ import annotations

import time

from server.adapters.llm import get_adapter, LLMError
from server.adapters.tokenizer import estimate_tokens
from server.config import get as cfg_get
from server.models import providers as pm, chapters as cm

# ---- 上下文预算（字符）----
# 这些上限是有意设小的：本地模型（如 qwen3:14b）的可用上下文有限，
# 塞太多正文不仅拖慢首字延迟，还会被静默截断，反而丢失最该参考的「最近内容」。
STYLE_SAMPLE_CAP = 6000      # 创作：文风样本（取最近正文）
REVIEW_CONTEXT_CAP = 24000   # 通读全书：正文中上限
CONTINUE_TAIL_CAP = 3000     # 续写：只取章末上文
OP_TEXT_CAP = 12000          # 改写 / 扩写 / 缩写：单次处理的正文上限

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

# 每种操作的「角色 + 任务 + 质量清单」。硬性输出规则在 _BASE_RULES 里统一追加。
_SYSTEM = {
    "rewrite": (
        "你是一位与作者并肩写作的资深小说家，擅长在保留作者个人声口的前提下做精准修订。\n"
        "任务：按【方向】改写【原文】。\n"
        "质量清单：\n"
        "1. 保留作者的人称、视角、时态、叙事节奏与人物说话方式，只改需要改的部分；\n"
        "2. 作者没提到的情节、人名、设定一律不动，严禁自行添加新角色或新支线；\n"
        "3. 改后篇幅与原文大致相当（除非方向里明确要求增减）；\n"
        "4. 修掉原文里明显的语病、重复用词和逻辑不顺，但不要「翻译腔」式重写。"
    ),
    "continue": (
        "你是作者的同写作家，负责接着往下写。\n"
        "任务：顺着【上文】的文风、视角、情绪与剧情走向，自然续写接下来的内容。\n"
        "质量清单：\n"
        "1. 紧接上文的最后一件事继续，不要回溯重述已经写过的情节；\n"
        "2. 沿用上文的段落节奏与句式长短，不要突然变成另一种文体；\n"
        "3. 人物言行与此前保持一致，环境、时间线连续；\n"
        "4. 推进情节或深化人物，不要原地打转、不要空泛抒情；\n"
        "5. 结尾留一个自然的停顿点，便于作者继续。"
    ),
    "expand": (
        "你擅长把骨架写成有血有肉的现场。\n"
        "任务：在不改变原意与文风的前提下扩写【原文】。\n"
        "质量清单：\n"
        "1. 补充感官细节（声音、气味、触感、光线）、人物心理活动、动作层次或环境氛围；\n"
        "2. 每一处补充都要服务情节或人物，不要堆砌辞藻；\n"
        "3. 保留原文全部信息点，不改变原有情节走向；\n"
        "4. 扩写后的文字要与原文无缝融合，读起来像一次写成的。"
    ),
    "shrink": (
        "你是一位惜字如金的编辑。\n"
        "任务：压缩【原文】，保留核心情节与关键信息的文风。\n"
        "质量清单：\n"
        "1. 删掉冗余修饰、重复表述与拖沓的过程描写；\n"
        "2. 保留所有关键情节点、转折与人物动机；\n"
        "3. 保留作者原有的句式气质，不要压成干巴巴的摘要；\n"
        "4. 压缩后仍然通顺连贯，可读作正文而非提纲。"
    ),
    "create": (
        "你是一位与作者并肩写作的资深小说家。\n"
        "任务：按【方向】创作一段全新的小说正文，并让它在文风上与【文风样本】自然衔接。\n"
        "质量清单：\n"
        "1. 仔细模仿文风样本的叙述腔调、句式长度与用词习惯，做到放到原作里不违和；\n"
        "2. 世界观、人物设定与既有情节保持一致，不引入与已知设定冲突的内容；\n"
        "3. 有具体场景、具体动作与对话，避免抽象概述；\n"
        "4. 开篇直接进入情境，不要环境铺垫式套话；\n"
        "5. 若方向里给了场景或情绪要求，必须体现。"
    ),
    "review": (
        "你是一位资深文学编辑，审稿时既尖锐也给得出办法。\n"
        "任务：通读作品正文，结合【方向】（若提供）给出具体、可操作的修改意见。\n"
        "质量清单：\n"
        "1. 按「问题类型 → 具体位置（章节 / 大致段落）→ 修改建议」三段式组织；\n"
        "2. 至少覆盖：节奏与拖沓、信息密度、人物一致性、伏笔与呼应、对话自然度、语病冗余、逻辑漏洞；\n"
        "3. 每条意见都要指出「改哪里、怎么改」，不要只说「这里不够好」；\n"
        "4. 先说最影响阅读的三条（标为「优先修改」），再说其余；\n"
        "5. 只给意见，不要重写正文；可用 Markdown 列表与小标题。"
    ),
    "gen_outline": (
        "你是一位资深小说架构师。\n"
        "任务：把作者的【创作想法】变成一份可直接动笔的章节大纲。\n"
        "质量清单：\n"
        "1. 按叙事顺序列出场景节点，每个节点写清：发生什么、谁在场、冲突或转折是什么；\n"
        "2. 标出情绪走向（如：压抑 → 爆发 → 余味）与关键细节 / 伏笔的埋设位置；\n"
        "3. 给出本章的收束方式，让这一章有完整感；\n"
        "4. 用有序列表或分层条目，语言精炼可执行，不要写正文。"
    ),
    "gen_from_outline": (
        "你是一位与作者并肩写作的资深小说家。\n"
        "任务：严格按【大纲】的顺序与要点，扩写成完整、连贯、有文学质感的章节正文。\n"
        "质量清单：\n"
        "1. 大纲的每个条目都要落实为具体场面：有动作、有细节、有必要的对话；\n"
        "2. 条目之间的过渡自然，场景切换有交代，不要跳跃；\n"
        "3. 人物言行符合设定，情绪变化有层次；\n"
        "4. 保持统一文风：若提供了【文风样本】，以其腔调为准；\n"
        "5. 结尾收束到本章的情绪落点，不要在高潮处硬断。"
    ),
}

# 统一硬性输出规则：这是「提示词工程」里最有效的一段，
# 专治模型爱加开场白、爱加围栏、爱自我总结的毛病。
_BASE_RULES = (
    "\n\n【硬性输出规则】\n"
    "1. 只输出正文内容本身：不要开场白（如「以下是改写后的内容」）、不要说明、"
    "不要总结、不要注释、不要出现「根据您的要求」这类表述。\n"
    "2. 不要使用 Markdown 代码围栏（```），通读全书意见除外（它可以用列表与小标题）。\n"
    "3. 与原文保持同一语言（默认简体中文）、同一人称、同一视角、同一时态。\n"
    "4. 不要复述指令，不要输出与正文无关的任何文字。\n"
    "5. 自然分段，段间空一行。"
)

# 温度按操作区分：稳 / 活
_TEMPERATURE = {
    "rewrite": 0.55,
    "shrink": 0.45,
    "expand": 0.7,
    "continue": 0.8,
    "create": 0.85,
    "review": 0.4,
    "gen_outline": 0.7,
    "gen_from_outline": 0.8,
}

# 阶段事件文案（前端等待 UI 直接展示）
STAGE_LABELS = {
    "prepare": "准备上下文",
    "connect": "连接模型",
    "generating": "模型生成中",
}


def _resolve_provider(provider_id):
    """解析 provider：显式指定 > 用户设置的默认 > 第一个可用。

    修复：以前未指定时直接取「第一个可用」，用户在设置里点的「设为默认」对 AI 写作不生效。
    """
    if provider_id:
        p = pm.get_provider(provider_id)
        if p and p.get("enabled"):
            return p
    default_id = cfg_get("default_provider_id")
    if default_id:
        p = pm.get_provider(default_id)
        if p and p.get("enabled"):
            return p
    enabled = [p for p in pm.list_providers() if p.get("enabled")]
    if not enabled:
        return None
    # 兜底必须避开 mock：mock 是离线演示占位模型，通常排在最前，
    # 若直接取第一个，用户没设默认模型时点「生成」会得到「演示模式」占位回复。
    real = [p for p in enabled if (p.get("kind") or "").lower() != "mock"]
    return real[0] if real else enabled[0]


def _tail(text: str, cap: int) -> str:
    """取末尾 cap 字，并标注前面已省略（续写只需要最近的语境）。"""
    t = text or ""
    if len(t) <= cap:
        return t
    return "…（更早的内容已省略）\n" + t[-cap:]


def _head(text: str, cap: int) -> str:
    t = text or ""
    if len(t) <= cap:
        return t
    return t[:cap] + "\n…（后文因长度限制已省略）"


def _chapter_manifest(book_id) -> str:
    """全书章节清单（标题 + 字数）：便宜但信息量大，让模型知道整体结构。"""
    if not book_id:
        return ""
    chs = cm.list_chapters(book_id)
    if not chs:
        return ""
    lines = [f"{i}. 《{c.get('title') or '未命名'}》约 {c.get('words') or 0} 字"
             for i, c in enumerate(chs, 1)]
    return "\n".join(lines)


def _book_context(book_id, cap: int) -> str:
    """拼接全书正文（含章节标题），用于 review 的上下文。超长截断。"""
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
        if total + len(block) > cap:
            remain = cap - total
            if remain > 200:
                parts.append(block[:remain] + "\n…（已截断）")
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)


def _style_sample(book_id, chapter_id, fallback_text: str = "") -> str:
    """文风样本：优先当前章末尾，其次最近有正文的章节末尾。"""
    if chapter_id:
        ch = cm.get_chapter(chapter_id)
        body = (ch or {}).get("content") or ""
        if body.strip():
            return _tail(body, STYLE_SAMPLE_CAP)
    if fallback_text and fallback_text.strip():
        return _tail(fallback_text, STYLE_SAMPLE_CAP)
    if book_id:
        chs = cm.list_chapters(book_id)
        for ch in reversed(chs or []):
            full = cm.get_chapter(ch["id"])
            body = (full or {}).get("content") or ""
            if body.strip():
                return _tail(body, STYLE_SAMPLE_CAP)
    return ""


def _length_hint(target_words) -> str:
    """篇幅要求（可选）：把用户的篇幅选择翻译成明确指令。"""
    try:
        n = int(target_words)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    return f"目标篇幅：约 {n} 字（允许 ±20% 浮动，宁可写足也不要为凑数注水）。"


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
    params: 附加参数，目前支持 target_words（目标字数）、temperature（覆盖默认温度）。
    """
    started = time.time()

    def elapsed_ms():
        return int((time.time() - started) * 1000)

    if operation not in OPERATIONS:
        yield {"type": "error", "data": f"未知操作：{operation}"}
        return

    params = params or {}
    provider = _resolve_provider(provider_id)
    if not provider:
        yield {"type": "error", "data": "没有可用的模型 provider，请先在「设置 → 模型」中添加并启用"}
        return

    yield {"type": "status", "data": {"stage": "prepare", "label": STAGE_LABELS["prepare"]}}

    instruction = (instruction or "").strip()
    manifest = _chapter_manifest(book_id)

    # ---- 组装 user 内容（按操作给不同的上下文预算）----
    if operation == "review":
        context_text = _book_context(book_id, REVIEW_CONTEXT_CAP)
        user_content = ""
        if manifest:
            user_content += "【全书章节清单】\n" + manifest + "\n\n"
        user_content += "【全书正文】\n" + (context_text or "（该书暂无正文）")
        if instruction:
            user_content += f"\n\n【方向】\n{instruction}"
    elif operation == "create":
        sample = _style_sample(book_id, chapter_id, text or "")
        user_content = ""
        if manifest:
            user_content += "【全书章节清单】\n" + manifest + "\n\n"
        if sample:
            user_content += "【文风样本（务必模仿其腔调）】\n" + sample + "\n\n"
        user_content += "【方向】\n" + (instruction or "（请自由发挥，写一段精彩的小说正文）")
        hint = _length_hint(params.get("target_words"))
        if hint:
            user_content += "\n\n" + hint
    elif operation == "gen_outline":
        user_content = "【创作想法】\n" + (instruction or text or "（请自由发挥，给出一个写作想法）")
    elif operation == "gen_from_outline":
        sample = _style_sample(book_id, chapter_id)
        user_content = "【大纲】\n" + (text or instruction or "（请给出一个大纲）")
        extra = instruction if instruction and instruction != (text or "") else ""
        if extra:
            user_content += f"\n\n【补充方向】\n{extra}"
        if sample:
            user_content += "\n\n【文风样本（务必模仿其腔调）】\n" + sample
        hint = _length_hint(params.get("target_words"))
        if hint:
            user_content += "\n\n" + hint
    elif operation == "continue":
        # 续写只取章末上文：最近的语境才决定下一句怎么写。
        if chapter_id:
            ch = cm.get_chapter(chapter_id)
            src_text = (ch.get("content") or "") if ch else (text or "")
        else:
            src_text = text or ""
        user_content = "【上文】\n" + _tail(src_text, CONTINUE_TAIL_CAP)
        if instruction:
            user_content += f"\n\n【方向】\n{instruction}"
        hint = _length_hint(params.get("target_words"))
        if hint:
            user_content += "\n\n" + hint
    else:  # rewrite / expand / shrink
        src_text = text or ""
        user_content = "【原文】\n" + _head(src_text, OP_TEXT_CAP)
        if instruction:
            user_content += f"\n\n【方向】\n{instruction}"

    system_prompt = _SYSTEM[operation] + _BASE_RULES
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    yield {"type": "status", "data": {"stage": "connect", "label": STAGE_LABELS["connect"]}}
    try:
        adapter = get_adapter(provider)
    except LLMError as e:
        yield {"type": "error", "data": f"provider 初始化失败：{e}"}
        return

    # 温度：操作默认值，允许 params 覆盖
    gen_params = dict(params or {})
    gen_params.setdefault("temperature", _TEMPERATURE.get(operation, 0.7))

    yield {"type": "refs", "data": []}
    provider_snapshot = {"kind": provider["kind"], "model": provider.get("model")}
    yield {"type": "status", "data": {"stage": "generating", "label": STAGE_LABELS["generating"]}}

    caps = adapter.capabilities()
    try:
        if not caps.get("streaming"):
            full = "".join(adapter.stream(messages, gen_params))
            yield {"type": "delta", "data": full}
        else:
            buf = []
            for delta in adapter.stream(messages, gen_params):
                buf.append(delta)
                yield {"type": "delta", "data": delta}
            full = "".join(buf)
        yield {
            "type": "done",
            "data": {
                "tokens": estimate_tokens(full),
                "chars": len(full or ""),
                "operation": operation,
                "provider": provider_snapshot,
                "elapsed_ms": elapsed_ms(),
            },
        }
    except LLMError as e:
        yield {"type": "error", "data": str(e), "stage": "generating"}
    except Exception as e:  # 兜底：任何中断都要让前端退出等待态
        yield {"type": "error", "data": f"生成中断：{e}", "stage": "generating"}
