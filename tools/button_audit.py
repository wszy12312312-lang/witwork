"""按钮审计：扫描 web-astro/src 下所有 .vue 组件里的 <button>，
找出「绑定缺失 / 处理函数不存在」等隐患。

用法：
    python tools/button_audit.py            # 打印报告
    python tools/button_audit.py --json     # 输出 JSON（供后续脚本消费）

设计说明：
- Vue 模板与脚本分开解析，避免正则跨区误匹配。
- 只取 @click 表达式的「头部标识符」（调用者本身）：参数里的 v-for 别名
  不是脚本变量，不该被判定为未定义。
- 先剥离字符串字面量，避免 emit('close') 里的 close 被当成标识符。
- 支持事件修饰符写法：@click.stop / @click.prevent 等。
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "web-astro" / "src"

# 内联赋值（xxx = ...、xxx++）不需要再查函数定义
ASSIGN_RE = re.compile(r"^[\w$.\[\]'\"]+\s*(\+\+|--|[-+*/]?=)")
IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")
STR_RE = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`(?:[^`\\]|\\.)*`")
ALLOW = {
    "emit", "$event", "true", "false", "null", "undefined", "console", "window",
    "document", "localStorage", "JSON", "String", "Number", "Boolean", "Object",
    "Array", "Math", "Date", "setTimeout", "clearTimeout", "alert", "confirm",
}


def split_vue(text: str):
    """返回 (template 片段列表, script 文本)。"""
    scripts = [m.group(1) for m in re.finditer(r"<script\b[^>]*>(.*?)</script>", text, re.S)]
    templates = [m.group(1) for m in re.finditer(r"<template\b[^>]*>(.*?)</template>", text, re.S)]
    return templates, "\n".join(scripts)


def collect_defined(script: str) -> set:
    """脚本里定义的标识符。"""
    names = set()
    for pat in (
        r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)",
        r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)",
        r"\bclass\s+([A-Za-z_$][\w$]*)",
    ):
        names |= set(re.findall(pat, script))
    for m in re.finditer(r"import\s+(?:([A-Za-z_$][\w$]*)\s*,?\s*)?(?:\{([^}]*)\})?\s*from", script):
        if m.group(1):
            names.add(m.group(1))
        if m.group(2):
            for part in m.group(2).split(","):
                part = part.strip()
                if part:
                    names.add(part.split(" as ")[-1].strip())
    for m in re.finditer(r"(?:const|let|var)\s*\{([^}]*)\}\s*=", script):
        for part in m.group(1).split(","):
            part = part.strip()
            if part:
                names.add(part.split(":")[-1].strip())
    return names


def extract_buttons(tpl: str):
    """提取 <button ...> 的属性串。

    不能简单用 `[^>]*`：属性值里可能出现 `>`（如 v-if="unread > 0"），
    会被误判为标签结束，导致后面的 @click 被截断。这里做引号感知扫描。
    """
    out = []
    for m in re.finditer(r"<button\b", tpl):
        i, quote = m.end(), None
        while i < len(tpl):
            ch = tpl[i]
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "'\"":
                quote = ch
            elif ch == ">":
                break
            i += 1
        out.append((m.start(), tpl[m.end():i]))
    return out


def attr(attrs: str, name: str):
    """匹配 name / :name / @name，允许事件修饰符 @click.stop。"""
    m = re.search(
        r"(?:^|\s)([:@]?)" + re.escape(name) + r"(?:\.[\w.]+)*\s*=\s*\"([^\"]*)\"",
        attrs, re.S)
    return (m.group(1) + name, m.group(2).strip()) if m else None


def head_ident(expr: str):
    """表达式头部标识符；赋值语句与空表达式返回 None。"""
    expr = STR_RE.sub(" ", expr).strip()
    if not expr or ASSIGN_RE.match(expr):
        return None
    m = IDENT_RE.match(expr)
    return m.group(0) if m else None


def audit():
    report = []
    for f in sorted(SRC.rglob("*.vue")):
        text = f.read_text(encoding="utf-8", errors="replace")
        templates, script = split_vue(text)
        defined = collect_defined(script)
        rel = f.relative_to(ROOT).as_posix()
        for tpl in templates:
            for pos, attrs in extract_buttons(tpl):
                click = attr(attrs, "click")
                disabled = attr(attrs, "disabled")
                label = " ".join(tpl[pos:pos + 400].split())[:90]
                issues = []
                if click is None:
                    d = (disabled[1] if disabled else "").strip()
                    if d in ("", "true"):
                        issues.append("无 @click 且未禁用")
                else:
                    r = head_ident(click[1])
                    if r and r not in ALLOW and r not in defined:
                        issues.append(f"处理函数/变量未定义: {r}")
                if issues:
                    report.append({
                        "file": rel,
                        "label": label,
                        "click": click[1] if click else None,
                        "disabled": disabled[1] if disabled else None,
                        "issues": issues,
                    })
    return report


def main():
    rep = audit()
    if "--json" in sys.argv:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return
    print(f"扫描目录: {SRC}")
    print(f"可疑按钮: {len(rep)} 个\n")
    for r in rep:
        print(f"[{r['file']}]")
        print(f"   按钮    : {r['label']}")
        print(f"   @click  : {r['click']}")
        if r["disabled"]:
            print(f"   disabled: {r['disabled']}")
        print(f"   问题    : {'; '.join(r['issues'])}")
        print()


if __name__ == "__main__":
    main()
