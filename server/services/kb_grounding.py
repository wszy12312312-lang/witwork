"""AI 写作接地（Grounding）：让 AI 写作的全部操作都能连上知识库。

与 AI 会话（session.py）共用同一套检索/注入链路：
- 知识库检索（设定词条/人物/世界观等）→ 注入「设定依据」；
- 伏笔清单（planned + planted）→ 提醒模型呼应；
- 人物卡（按正文匹配出场）→ 保持人物言行一致。

设计：
- 一次调用返回 (citations, grounding_text)：citations 给前端引用卡，
  grounding_text 直接拼进 system prompt。
- 总开关 config `ai_kb_grounding`（默认开）；`ai_kb_deep_analysis`（默认关）
  打开时检索条数翻倍（更慢但更全）。
- 任何检索失败都不阻断生成（降级为无接地）。
"""
from __future__ import annotations

from server.config import get as cfg_get
from server.services.knowledge import get_service as get_kb
from server.services import foreshadow as fs_svc
from server.services import character as char_svc

# 检索查询文本上限（嵌入模型输入不需要太长）
_QUERY_CAP = 800


def build_grounding(book_id=None, chapter_id=None, query_text: str = ""):
    """返回 (citations, grounding_text)。

    query_text: 用于检索的文本（一般是本次操作的原文/上文/方向/大纲）。
    grounding_text: 拼进 system prompt 的注入文本；无可用内容时为空串。
    """
    if not cfg_get("ai_kb_grounding", True):
        return [], ""

    query = (query_text or "").strip()[:_QUERY_CAP]
    citations: list = []
    parts: list[str] = []

    # ---- 知识库检索 ----
    try:
        kb = get_kb()
        top_k = int(cfg_get("retrieval_top_k", 6))
        if cfg_get("ai_kb_deep_analysis", False):
            top_k = max(top_k * 2, 10)
        hits = kb.retrieve(query, top_k=top_k) if query else []
        citations = kb.format_citations(hits)
        rtext = kb.format_retrieval_text(hits)
        if rtext:
            parts.append(
                "[设定依据（来自知识库，写作时必须遵循；与这些设定冲突的内容一律不要写）]\n"
                + rtext
            )
    except Exception:
        citations = []

    # ---- 伏笔 + 人物卡（需要 book 上下文）----
    if book_id:
        try:
            fi = fs_svc.injection_text(book_id)
            if fi:
                parts.append("[伏笔清单（未回收，注意在合适位置呼应，不要提前泄底）]\n" + fi)
        except Exception:
            pass
        try:
            ci = char_svc.build_injection_text(book_id, chapter_text=query)
            if ci:
                parts.append("[出场人物卡（其言行、口癖、当前状态必须一致）]\n" + ci)
        except Exception:
            pass

    return citations, "\n\n".join(parts)
