"""在桌面重建 WitWork 启动入口（幂等，可随时重跑）。

============ 实测结论（2026-09-21，务必先读）============
本机 Windows **不接受纯手写的 .lnk**。即使严格按 MS-SHLLINK 组装，并把
LinkTargetIDList 做到与桌面真实快捷方式逐字节一致（根节点项完全相同、
IDList 步进自校验通过、LinkInfo/StringData 布局自洽），ShellExecute 仍然返回
    OSError 22 / WinError 1155 = ERROR_NO_ASSOCIATION
对照实验证明不是环境问题：同一目录下真实的 Mineradio.lnk / Obsidian.lnk 调用成功。
推测缺的是 Explorer 才会写入的私有块（ExtraData / TrackerDataBlock 等）。
同时：COM 路线也走不通——本机安全策略拦截 WScript.Shell（PowerShell 报
"COM object instantiation can run arbitrary code"），且未安装 pywin32/comtypes。

因此本工具只做**一定能用**的那件事：生成 ASCII + CRLF 的桌面启动 .bat。
想要带图标的 .lnk，请用 Explorer 自己生成（100% 有效）：
    右键该 .bat → 发送到 → 桌面快捷方式

用法：python tools/make_desktop_shortcut.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .../inkrealm
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BAT_PATH = os.path.join(DESKTOP, "万维文 WitWork.bat")

# 纯 ASCII，避免 cmd 以 GBK 解析 UTF-8 中文注释时错位（曾导致 pip install 被撕成
# 'ist'/'all' 两条假命令）；CRLF 为 .bat 规范换行。两者缺一都可能出错。
LINES = [
    "@echo off",
    "REM ============================================================",
    "REM  WitWork launcher (ASCII + CRLF on purpose - do not change)",
    "REM  Forwards to inkrealm\\start.bat, the single source of truth.",
    "REM ============================================================",
    'cd /d "' + ROOT.replace("/", "\\") + '"',
    'call "start.bat"',
    "",
]


def main() -> int:
    if not os.path.isdir(DESKTOP):
        print("找不到桌面目录：", DESKTOP)
        return 1
    data = "\r\n".join(LINES).encode("ascii")
    with open(BAT_PATH, "wb") as f:
        f.write(data)
    ok_ascii = all(b < 128 for b in data)
    print("已生成：", BAT_PATH)
    print("  字节数 = %d | 纯ASCII = %s | CRLF 行数 = %d" % (len(data), ok_ascii, data.count(b"\r\n")))
    print()
    print("提示：如需带图标的快捷方式，请右键该 .bat → 发送到 → 桌面快捷方式")
    print("     （手写 .lnk 在本机不被 Windows 接受，详见本文件顶部说明）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
