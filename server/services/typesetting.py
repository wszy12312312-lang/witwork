"""排版服务：预览渲染（只读）与正文规范（可写回）两条管道，共用 core/typesetting/rules.json。

- renderPreview：把正文渲染为手机阅读器 HTML + 段落索引（供光标联动），**不改动原正文**。
- normalize：按规则改写正文并返回逐处 changes（可逐条勾选/拒绝），**可写回**。
"""
import html
import json
import re
from pathlib import Path

_RULES_PATH = Path(__file__).resolve().parent.parent / "core" / "typesetting" / "rules.json"
_cache = None

_CJK = r"\u4e00-\u9fff"


def load_rules():
    global _cache
    if _cache is None:
        _cache = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    return _cache


def _snip(text, pos, radius=12):
    s = max(0, pos - radius)
    e = min(len(text), pos + radius)
    return text[s:e]


def _apply_spans(text, spans):
    """spans: [(start, end, repl, type)]，从后往前应用，返回 (new_text, changes)。"""
    changes = []
    for start, end, repl, typ in sorted(spans, key=lambda x: -x[0]):
        before = _snip(text, start)
        text = text[:start] + repl + text[end:]
        changes.append({"type": typ, "before": before, "after": _snip(text, start), "pos": start})
    return text, changes


# ---------------- 预览（只读） ----------------
def render_preview(content, options=None):
    rules = load_rules()
    opts = options or {}
    chars_per_page = int(opts.get("chars_per_page") or rules.get("chars_per_page", 350))
    raw = (content or "").replace("\r\n", "\n")
    paras = [p.strip() for p in raw.split("\n") if p.strip()]
    htmls = []
    for i, p in enumerate(paras):
        htmls.append(f'<p class="pv-p" data-i="{i}">{html.escape(p)}</p>')
    words = sum(1 for ch in raw if not ch.isspace())
    pages = max(1, -(-words // chars_per_page)) if chars_per_page else 1
    return {
        "html": "\n".join(htmls),
        "paragraphs": [{"index": i, "text": p} for i, p in enumerate(paras)],
        "words": words,
        "pages": pages,
        "chars_per_page": chars_per_page,
        "rules_version": rules.get("rules_version"),
    }


# ---------------- 规范（可写回） ----------------
def normalize(content, options=None):
    rules = load_rules()
    opts = options or {}
    text = (content or "").replace("\r\n", "\n")
    changes = []

    if opts.get("punctuation_normalize", True):
        text, ch = _do_fullwidth(text, rules)
        changes += ch
        text, ch = _do_quotes(text, rules)
        changes += ch
        text, ch = _do_patterns(text, rules.get("ellipsis_patterns", []), rules.get("ellipsis", "……"), "ellipsis")
        changes += ch
        text, ch = _do_patterns(text, rules.get("dash_patterns", []), rules.get("dash", "——"), "dash")
        changes += ch
        text, ch = _do_repeat(text, rules.get("repeat_converge", []))
        changes += ch

    if opts.get("en_space", True):
        text, ch = _do_en_space(text)
        changes += ch

    text, ch = _do_line_rules(text, rules)
    changes += ch

    if opts.get("split_dialogue", True):
        text, ch = _do_dialogue(text, rules)
        changes += ch

    if rules.get("collapse_blank_lines", True):
        text, ch = _do_blank_lines(text)
        changes += ch

    changes.reverse()  # 应用顺序倒序记录，翻转后按正文顺序呈现
    return {"content": text, "changes": changes, "rules_version": rules.get("rules_version")}


def _do_fullwidth(text, rules):
    spans = []
    for eng, cn in rules.get("fullwidth_map", {}).items():
        for m in re.finditer(re.escape(eng), text):
            i = m.start()
            if eng in (".", ","):  # 小数点/千分位不转
                prev = text[i - 1] if i > 0 else ""
                nxt = text[i + 1] if i + 1 < len(text) else ""
                if prev.isdigit() and nxt.isdigit():
                    continue
            spans.append((i, i + 1, cn, "fullwidth"))
    return _apply_spans(text, spans)


def _do_quotes(text, rules):
    """半角双引号按段落交替成中文左右引号；直角引号「」本身已规范，不动。"""
    qo, qc = rules.get("quote_open", "“"), rules.get("quote_close", "”")
    spans = []
    open_next = True
    for i, ch in enumerate(text):
        if ch == '"':
            spans.append((i, i + 1, qo if open_next else qc, "quote"))
            open_next = not open_next
        elif ch == "\n":
            open_next = True  # 每段重新配对
    return _apply_spans(text, spans)


def _do_patterns(text, patterns, target, typ):
    spans = []
    for p in patterns:
        for m in re.finditer(p, text):
            spans.append((m.start(), m.end(), target, typ))
    return _apply_spans(text, spans)


def _do_repeat(text, pairs):
    """重复标点收敛（如 ！！ → ！），迭代至稳定并记录每处变更。"""
    all_changes = []
    changed = True
    rounds = 0
    while changed and rounds < 5:
        changed = False
        rounds += 1
        spans = []
        for src, dst in pairs:
            for m in re.finditer(re.escape(src), text):
                spans.append((m.start(), m.end(), dst, "repeat"))
        if spans:
            text, ch = _apply_spans(text, spans)
            all_changes += ch
            changed = True
    return text, all_changes


def _do_en_space(text):
    spans = []
    for m in re.finditer(f"([{_CJK}])([A-Za-z0-9])", text):
        spans.append((m.end(1), m.end(1), " ", "en_space"))
    for m in re.finditer(f"([A-Za-z0-9])([{_CJK}])", text):
        spans.append((m.end(1), m.end(1), " ", "en_space"))
    return _apply_spans(text, spans)


def _do_line_rules(text, rules):
    start_forbid = set(rules.get("line_start_forbid", ""))
    end_forbid = set(rules.get("line_end_forbid", ""))
    spans = []
    lines = text.split("\n")
    pos = 0
    for i, line in enumerate(lines):
        if line and line[0] in start_forbid and i > 0:
            # 行首禁则：把该行接到上一行末尾
            spans.append((pos - 1, pos + 1, line[0], "line_start"))
        if line and line[-1] in end_forbid and i < len(lines) - 1:
            spans.append((pos + len(line) - 1, pos + len(line) + 1, line[-1], "line_end"))
        pos += len(line) + 1
    return _apply_spans(text, spans)


def _do_dialogue(text, rules):
    """对话独立成段：仅当引文前后都有**实质**叙述时才拆分。

    约束（避免过度拆分）：
    - 引文前若以冒号/逗号结尾（如「他说：」），说明引文紧跟提示语，不拆；
    - 引文后若不足 3 字或以标点开头（如「，他说」），不拆。
    """
    qo, qc = rules.get("quote_open", "“"), rules.get("quote_close", "”")
    no_split_before = ("：", ":", "，", ",", "、")
    no_split_after = ("，", "。", "！", "？", "：", "、", "；", ",", ".", "!", "?")
    spans = []
    pos = 0
    for para in text.split("\n"):
        if qo in para and qc in para:
            s = para.find(qo)
            e = para.find(qc, s)
            if s > 0 and e != -1:
                prefix = para[:s].rstrip()
                suffix = para[e + 1:].lstrip()
                if prefix and len(prefix) > 4 and not prefix.endswith(no_split_before):
                    spans.append((pos + s, pos + s, "\n", "dialogue"))
                if suffix and len(suffix) > 2 and not suffix.startswith(no_split_after):
                    spans.append((pos + e + 1, pos + e + 1, "\n", "dialogue"))
        pos += len(para) + 1
    return _apply_spans(text, spans)


def _do_blank_lines(text):
    spans = []
    for m in re.finditer(r"\n{3,}", text):
        spans.append((m.start(), m.end(), "\n\n", "blank"))
    return _apply_spans(text, spans)
