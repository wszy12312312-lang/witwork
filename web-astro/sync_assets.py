#!/usr/bin/env python3
"""把 rhinelab-blog-theme 的离线字体与 font-face 同步进 web-astro（本地优先，无 CDN）。

源：_rhine_study/rhinelab-blog-theme-main/  （本机已解压的主题源码）
目标：web-astro/public/fonts  +  web-astro/src/styles/{misans,mono}.css

仅做增量复制：目标已存在则跳过，便于重复运行。
"""
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = r"C:\Users\wszy1\WorkBuddy\2026-09-18-01-07-46\_rhine_study\rhinelab-blog-theme-main"

Fonts = os.path.join(SRC, "public", "fonts")
Fonts_dst = os.path.join(ROOT, "public", "fonts")

src_misans = os.path.join(SRC, "shared", "misans.css")
src_mono = os.path.join(SRC, "shared", "jetbrains-maple-mono.css")
dst_misans = os.path.join(ROOT, "src", "styles", "misans.css")
dst_mono = os.path.join(ROOT, "src", "styles", "mono.css")


def copy_tree(src, dst):
    if not os.path.isdir(src):
        print("跳过（源缺失）:", src)
        return
    os.makedirs(dst, exist_ok=True)
    n = 0
    for dp, _dn, fn in os.walk(src):
        rel = os.path.relpath(dp, src)
        tdir = os.path.join(dst, rel) if rel != "." else dst
        os.makedirs(tdir, exist_ok=True)
        for f in fn:
            s = os.path.join(dp, f)
            t = os.path.join(tdir, f)
            if not os.path.exists(t):
                shutil.copy2(s, t)
                n += 1
    print(f"字体同步完成: {dst}  (+{n} 新文件)")


def copy_file(src, dst):
    if not os.path.exists(src):
        print("跳过（源缺失）:", src)
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst):
        shutil.copy2(src, dst)
        print("已复制:", os.path.relpath(dst, ROOT))
    else:
        print("已存在(跳过):", os.path.relpath(dst, ROOT))


if __name__ == "__main__":
    copy_tree(Fonts, Fonts_dst)
    copy_file(src_misans, dst_misans)
    copy_file(src_mono, dst_mono)
    print("OK")
