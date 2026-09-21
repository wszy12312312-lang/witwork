"""框架共创引擎：阶段机 + 每阶段必答项 + 三段式输出 + 推进/回退 + 一键生成章节骨架。

阶段：brief → worldview → faction → plotline → character → outline → confirmed
状态存于 sessions.framework_state_json.cocreation = {phase, data, needs_review, history}。
每阶段结论经知识库写回对应分区（worldview/faction/plot/character）。
回退后下游阶段标记 needs_review。
"""
import json
import re

from server.models import sessions as sm
from server.services.knowledge import get_service as get_kb

PHASES = ["brief", "worldview", "faction", "plotline", "character", "outline", "confirmed"]
PHASE_LABEL = {
    "brief": "一句话框架", "worldview": "世界观", "faction": "势力", "plotline": "情节线",
    "character": "人物", "outline": "大纲", "confirmed": "已确认",
}
SECTION_OF = {"worldview": "worldview", "faction": "faction", "plotline": "plot", "character": "character"}
REQUIRED = {
    "brief": ["一句话核心创意是什么？", "目标读者与体裁？"],
    "worldview": ["世界的基本法则 / 力量体系是什么？", "核心冲突的根源是什么？"],
    "faction": ["有哪些主要势力？", "势力之间的核心矛盾是什么？"],
    "plotline": ["主线目标与三幕结构？", "关键转折与高潮在哪里？"],
    "character": ["主角是谁，动机与缺陷？", "关键配角及其作用？"],
    "outline": ["分卷与章节骨架如何安排？", "需要预埋哪些伏笔？"],
}


def _load(session_id):
    s = sm.get_session(session_id)
    if not s:
        return None
    try:
        st = json.loads(s.get("framework_state_json") or "{}")
    except Exception:
        st = {}
    co = st.get("cocreation") or {"phase": "brief", "data": {}, "needs_review": [], "history": []}
    return co, st


def _save(session_id, co, st=None):
    if st is None:
        s = sm.get_session(session_id)
        st = json.loads(s.get("framework_state_json") or "{}") if s else {}
    st["cocreation"] = co
    sm.update_session(session_id, {"framework_state_json": json.dumps(st, ensure_ascii=False)})


def get_state(session_id):
    loaded = _load(session_id)
    if not loaded:
        return {"error": "会话不存在"}
    co, _ = loaded
    phase = co["phase"]
    return {
        "phase": phase,
        "phase_label": PHASE_LABEL.get(phase, phase),
        "required": REQUIRED.get(phase, []),
        "data": co.get("data", {}),
        "needs_review": co.get("needs_review", []),
        "history": co.get("history", []),
        "confirmed": phase == "confirmed",
    }


def next_prompt(session_id):
    """返回引导者本轮要问的问题（含 2-3 备选的指令）。"""
    st = get_state(session_id)
    if st.get("error"):
        return st
    phase = st["phase"]
    req = st["required"]
    prompt = (
        f"现在我们细化【{st['phase_label']}】。请回答以下问题（每个尽量给 2-3 个备选方案供我选择）：\n"
        + "\n".join(f"- {q}" for q in req)
        + "\n\n请给出三段式回复：①结论 ②待确认问题（含备选）③下一步。"
    )
    return {"phase": phase, "prompt": prompt, "required": req}


def advance(session_id, conclusion, note=None):
    loaded = _load(session_id)
    if not loaded:
        return {"error": "会话不存在"}
    co, st = loaded
    phase = co["phase"]
    co.setdefault("data", {})[phase] = conclusion
    co.setdefault("history", []).append({"phase": phase, "conclusion": conclusion, "note": note})
    # 写回知识库（非 brief/outline）
    if phase in SECTION_OF:
        kb = get_kb()
        title = f"框架#{session_id}·{PHASE_LABEL[phase]}"
        kb.ingest_text(SECTION_OF[phase], title, conclusion, source_type="ai", source_ref=f"cocreation:{session_id}")
    # 推进
    idx = PHASES.index(phase)
    if idx < len(PHASES) - 1:
        co["phase"] = PHASES[idx + 1]
        co["needs_review"] = []
    _save(session_id, co, st)
    return get_state(session_id)


def retreat(session_id):
    loaded = _load(session_id)
    if not loaded:
        return {"error": "会话不存在"}
    co, st = loaded
    idx = PHASES.index(co["phase"])
    if idx <= 0:
        return get_state(session_id)
    new_idx = idx - 1
    co["phase"] = PHASES[new_idx]
    # 下游（new_idx 之后）标记待复核
    co["needs_review"] = PHASES[new_idx + 1: idx + 1]
    _save(session_id, co, st)
    return get_state(session_id)


def generate_outline(session_id, book_id):
    """从 outline 结论生成章节骨架（卷+章）与 planned 伏笔列表。"""
    loaded = _load(session_id)
    if not loaded:
        return {"error": "会话不存在"}
    co, _ = loaded
    outline = co.get("data", {}).get("outline", "")
    kb = get_kb()
    # 解析章节标题
    ch_titles = re.findall(r"(?:^|\n)\s*(?:第\s*\d+\s*[章卷]|\d+[\.\、]\s*[^，。\n]{2,30})", outline)
    ch_titles = [t.strip(" .、") for t in ch_titles if t.strip(" .、")]
    if not ch_titles:
        ch_titles = ["第1章", "第2章", "第3章"]
    planned = [ln.strip(" -、") for ln in outline.splitlines() if "伏笔" in ln]
    created = []
    if book_id:
        from server.models import books as bm, chapters as cm
        vol = bm.create_volume(book_id, "框架大纲")
        for t in ch_titles:
            ch = cm.create_chapter(book_id, t, vol["id"])
            created.append({"id": ch["id"], "title": t})
        co.setdefault("data", {})["_outline_created"] = len(created)
        _save(session_id, co)
    co.setdefault("data", {})["planned_foreshadows"] = planned
    return {"chapters": created, "planned_foreshadows": planned, "count": len(created)}
