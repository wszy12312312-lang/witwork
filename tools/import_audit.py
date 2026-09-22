"""导入一致性审计：检查每个 .vue 组件从 store / api 导入的成员是否真的被导出，
以及组件里调用的 api.xxx() 是否存在。这类问题会让按钮直接抛错（点不动）。

用法：
    python tools/import_audit.py

说明：
- 会识别多种导出形态：export function/const/let/interface/type/enum/class、
  `export { a, b as c }`、`export type { a } from './api'`。
- 类型（type-only）导入缺失不会导致运行时报错（编译期会被剔除），但仍是
  真实的不一致，本工具同样报告，便于顺手修掉。
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "web-astro" / "src"


def exports_of(path: pathlib.Path) -> set:
    s = path.read_text(encoding="utf-8")
    names = set()
    names |= set(re.findall(r"export\s+(?:async\s+)?function\s+(\w+)", s))
    names |= set(re.findall(r"export\s+const\s+(\w+)", s))
    names |= set(re.findall(r"export\s+let\s+(\w+)", s))
    names |= set(re.findall(r"export\s+(?:interface|type|enum|class)\s+(\w+)", s))
    for m in re.finditer(r"export\s+(?:type\s+)?\{([^}]*)\}", s):
        for part in m.group(1).split(","):
            part = part.strip()
            if part:
                names.add(part.split(" as ")[-1].strip())
    return names


def api_methods() -> set:
    """api 对象上的方法名（两个空格缩进的键）。"""
    s = (SRC / "lib" / "api.ts").read_text(encoding="utf-8")
    body = s[s.index("export const api = {"):]
    return set(re.findall(r"^\s{2}(\w+)\s*:", body, re.M))


def audit():
    store_exports = exports_of(SRC / "lib" / "store.ts")
    api_exports = exports_of(SRC / "lib" / "api.ts")
    methods = api_methods()
    api_all = api_exports | methods | {"api"}

    problems = []
    for f in sorted(SRC.rglob("*.vue")):
        t = f.read_text(encoding="utf-8", errors="replace")
        rel = f.relative_to(SRC).as_posix()
        for m in re.finditer(r"import\s*\{([^}]*)\}\s*from\s*'([^']*)'", t, re.S):
            src = m.group(2)
            for raw in m.group(1).split(","):
                n = raw.strip().replace("type ", "").strip()
                if not n:
                    continue
                if "store" in src and n not in store_exports:
                    problems.append(f"{rel}: store 未导出 '{n}'")
                if re.search(r"(^|/)api$", src) and n not in api_all:
                    problems.append(f"{rel}: api 未导出 '{n}'")
        for m in re.finditer(r"\bapi\.(\w+)\s*\(", t):
            if m.group(1) not in methods:
                problems.append(f"{rel}: 调用了不存在的 api.{m.group(1)}()")
    return store_exports, api_all, methods, sorted(set(problems))


def main():
    store_exports, api_all, methods, problems = audit()
    print(f"store 导出 {len(store_exports)} 个 | api 导出 {len(api_all)} 个 | api 方法 {len(methods)} 个\n")
    if problems:
        print(f"问题 {len(problems)} 条：")
        for p in problems:
            print("  ✗", p)
        sys.exit(1)
    print("全部一致 ✅ 组件导入与调用的 store/api 成员都存在")


if __name__ == "__main__":
    main()
