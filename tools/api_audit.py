"""接口审计：把前端 api.ts 里声明的所有请求路径，与后端 FastAPI 真实注册的
路由逐条比对，找出「前端在调、后端没有」的 404 隐患（按钮点了没反应的常见根因）。

用法：
    python tools/api_audit.py            # 打印报告
    python tools/api_audit.py --json

注意：
- 需在 inkrealm 根目录、PYTHONPATH=. 下运行。
- 新版 FastAPI 用惰性 _IncludedRouter，app.routes 看不到嵌套路由，
  因此从 app.openapi()['paths'] 取权威路由表。
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
API_TS = ROOT / "web-astro" / "src" / "lib" / "api.ts"

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
API_PREFIX = "/api"  # api.ts 里 `const BASE = '/api'`，后端路由也统一挂在该前缀下
STR = r"(`[^`]*`|'[^']*'|\"[^\"]*\")"


def strip_template(expr: str) -> str:
    """把 JS 模板串里的 ${...}（支持嵌套）替换为 {}，便于与后端路由比对。"""
    out, i = [], 0
    while i < len(expr):
        if expr.startswith("${", i):
            depth, i = 1, i + 2
            while i < len(expr) and depth:
                if expr[i] == "{":
                    depth += 1
                elif expr[i] == "}":
                    depth -= 1
                i += 1
            out.append("{}")
        else:
            out.append(expr[i])
            i += 1
    return "".join(out)


def norm_path(raw: str) -> str:
    """归一化：去模板变量、去查询串。"""
    p = strip_template(raw)
    p = p.split("?")[0]
    # 模板变量紧跟在路径尾部（前面不是斜杠）时属于查询参数，
    # 如 /providers/discover${baseUrl ? '?x' : ''} —— 去掉尾部 {}
    p = re.sub(r"(?<=[^/])\{\}$", "", p)
    return p


def frontend_calls(src: str):
    """抽取 (path, method)。"""
    out = []
    # getJSON<T>('/x')            → GET
    for m in re.finditer(r"\bgetJSON\s*(?:<[^>]*>)?\s*\(\s*" + STR, src):
        out.append((m.group(1)[1:-1], "GET"))
    # send<T>('/x', 'POST', ...)  → 显式方法
    for m in re.finditer(r"\bsend\s*(?:<[^>]*>)?\s*\(\s*" + STR + r"\s*,\s*['\"`](\w+)['\"`]", src):
        out.append((m.group(1)[1:-1], m.group(2).upper()))
    # fetch(`${BASE}/x`)          → 流式接口，统一 POST（SSE 走 POST）
    # 注意：通用传输 helper 内的 `fetch(`${BASE}${path}`)` 不是真实端点
    #（path 是变量，无法静态解析），必须跳过 —— 否则会长期产生一条
    #「POST /api{} 未匹配」的假阳性，掩盖真实问题。
    for m in re.finditer(r"fetch\(\s*`\$\{BASE\}([^`]*)`", src):
        grp = m.group(1)
        if grp.lstrip().startswith("${"):
            continue
        out.append((grp, "POST"))
    return [(norm_path(p), mth) for p, mth in out]


def backend_routes():
    """从 OpenAPI 文档取 (path, method)，这是 FastAPI 的权威路由表。"""
    from server.main import app  # noqa: WPS433（延迟导入，需 PYTHONPATH）

    paths = app.openapi().get("paths", {})
    routes = []
    for path, ops in paths.items():
        for m in ops:
            mu = m.upper()
            if mu in METHODS:
                routes.append((path, mu))
    return routes


def to_regex(route_path: str):
    """FastAPI 的 /books/{id} → ^/books/[^/]+$"""
    parts = re.split(r"\{[^}]*\}", route_path)
    return "^" + r"[^/]+".join(re.escape(p) for p in parts) + "$"


def match(path: str, method: str, routes):
    for rp, rm in routes:
        if rm == method and re.match(to_regex(rp), path):
            return rp
    return None


def main():
    src = API_TS.read_text(encoding="utf-8")
    calls = [(API_PREFIX + p, m) for p, m in frontend_calls(src)]
    routes = backend_routes()

    missing, ok = [], 0
    for path, method in calls:
        if not path.startswith("/"):
            continue  # 动态拼接的路径跳过
        hit = match(path, method, routes)
        if hit:
            ok += 1
        else:
            missing.append({"path": path, "method": method})

    seen, uniq = set(), []
    for m in missing:
        key = (m["path"], m["method"])
        if key not in seen:
            seen.add(key)
            uniq.append(m)

    if "--json" in sys.argv:
        print(json.dumps({"ok": ok, "missing": uniq, "routes": len(routes)},
                         ensure_ascii=False, indent=2))
        return

    print(f"后端注册的路由: {len(routes)} 条")
    print(f"前端声明的请求: {len(calls)} 条，匹配成功 {ok} 条\n")
    if not uniq:
        print("全部匹配 ✅ 不存在「前端在调、后端没有」的接口")
    else:
        print(f"未匹配（需人工确认是否为 404）: {len(uniq)} 条")
        for m in uniq:
            print(f"   {m['method']:<6} {m['path']}")


if __name__ == "__main__":
    main()
