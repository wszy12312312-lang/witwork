#!/usr/bin/env python3
"""把 web-astro 构建产物部署为 FastAPI 托管的前端。

流程（可逆）：
  1. 先 npm run build 生成 web-astro/dist
  2. 本脚本把当前 web/ 改名为 web.bak（保留旧零构建前端作为回退）
  3. 复制 dist/ -> web/，FastAPI(server/main.py) 即刻托管新版

回退：把 web.bak 改名回 web/ 即可。
"""
import glob
import os
import re
import sys
from datetime import datetime
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))          # .../inkrealm/web-astro
PROJECT = os.path.dirname(ROOT)                              # .../inkrealm
DIST = os.path.join(ROOT, "dist")                           # 构建产物
WEB = os.path.join(PROJECT, "web")                          # 真正被 FastAPI 托管的前端
BAK = os.path.join(PROJECT, "web.bak")                      # 旧前端回退


# ---- CSS 体检：拦「注释提前收尾」这一类事故 ----
# 历史事故：tokens.css 头注释里误写了注释收尾符号（星号+斜杠），其后的 :root 规则
# 选择器被污染成非法值 → 浏览器把整条 :root 丢掉 → 只写在 :root 的令牌全部失效
# （面板全透明、无 1.2 倍放大、圆角变直角、字体退回系统默认）。
# 这类问题构建不会报错、页面也不报错，只能靠断言拦。部署前必跑。
REQUIRED_TOKENS = [
    "--panel-alpha",
    "--ui-scale",
    "--font-sans",
    "--radius",
    "--motion",
    "--theme-scrim",
    "--topbar-alpha",
]


def check_css(dist_dir):
    """返回问题列表；空列表 = 通过。

    注意：Astro 会把 CSS 拆成多个 bundle（全局令牌+字体一个、各组件 scoped 样式一个），
    所以 `:root` 只会出现在其中一个里 —— 断言必须在「所有被引用 CSS 的并集」上做，
    不能要求每个文件都有 :root。
    """
    import re as _re
    problems = []
    # 只体检 index.html 真正引用的 CSS：dist/_astro 里的哈希文件每次构建都会换名，
    # 目录里可能残留旧文件（本机 SafeDelete shim 拦批量删除，不主动清理），
    # 把残留一起体检会误报。
    index_html = os.path.join(dist_dir, "index.html")
    if not os.path.exists(index_html):
        return ["dist/index.html 不存在"]
    html = open(index_html, encoding="utf-8", errors="replace").read()
    refs = _re.findall(r"/_astro/([A-Za-z0-9._-]+\.css)", html)
    if not refs:
        return ["index.html 没有引用任何 _astro/*.css"]

    parts = []
    for name in sorted(set(refs)):
        f = os.path.join(dist_dir, "_astro", name)
        if not os.path.exists(f):
            problems.append("index.html 引用了不存在的 %s" % name)
            continue
        text = open(f, encoding="utf-8", errors="replace").read()
        parts.append((name, text))
        # 去掉所有完整注释后若仍出现注释收尾符号 → 说明有注释被提前收尾
        stripped = _re.sub(r"/\*.*?\*/", "", text, flags=_re.S)
        if "*/" in stripped:
            i = stripped.index("*/")
            problems.append("%s: 存在游离的注释收尾符号（注释被提前收尾），附近片段 = %r"
                            % (name, stripped[max(0, i - 120):i + 40]))

    # 并集上必须有 :root，且关键令牌都在这个 :root 里
    joined = "".join(t for _, t in parts)
    m = _re.search(r":root\s*\{", joined)
    if not m:
        problems.append("所有被引用的 CSS 里都找不到 :root 规则（很可能被前面的注释吃掉了）")
    else:
        block = joined[m.start():m.start() + 4000]
        missing = [tok for tok in REQUIRED_TOKENS if tok not in block]
        if missing:
            problems.append(":root 里缺少令牌：%s" % ", ".join(missing))
    return problems


def main():
    if not os.path.isdir(DIST):
        print("未找到 web-astro/dist，请先在该目录执行 `npm run build`。")
        sys.exit(1)
    problems = check_css(DIST)
    if problems:
        print("CSS 体检未通过，已中止部署：")
        for p in problems:
            print("  -", p)
        sys.exit(2)
    print("CSS 体检通过（:root 与关键令牌齐全）")
    if os.path.isdir(WEB):
        # 保留历史构建：旧 web.bak 改名为带时间戳的备份，避免误删（曾因路径 bug 误删过零构建前端）
        if os.path.isdir(BAK):
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            os.rename(BAK, BAK + "." + ts)
        os.rename(WEB, BAK)
        print("已备份旧前端 -> web.bak")
    os.makedirs(WEB, exist_ok=True)
    for name in os.listdir(DIST):
        s = os.path.join(DIST, name)
        d = os.path.join(WEB, name)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
    print("已部署 web-astro/dist -> web/（FastAPI 将托管新版前端）")


if __name__ == "__main__":
    main()
