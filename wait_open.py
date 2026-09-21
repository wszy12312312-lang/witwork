"""启动辅助：等服务健康检查通过后再打开浏览器（最多等 60s）。

由 start.bat 调用；服务已在后台启动，这里只负责「等就绪→开浏览器」。
若服务已在运行（重复双击 start.bat），则直接打开浏览器、不重复拉起服务。

退出码：0=已就绪并打开浏览器；1=等待超时（供 start.bat 判断并停在窗口里显示提示）。
"""
import sys
import time
import webbrowser
import urllib.request

URL = "http://127.0.0.1:8723/"


def health() -> bool:
    try:
        urllib.request.urlopen(URL + "api/health", timeout=2)
        return True
    except Exception:
        return False


def say(msg: str) -> None:
    """控制台可能是 GBK 码页，避免个别字符导致 UnicodeEncodeError 中断启动流程。"""
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode("utf-8", "replace").decode("ascii", "replace"))
        except Exception:
            pass


def main() -> int:
    for _ in range(60):
        if health():
            webbrowser.open(URL)
            say("万维文已就绪：" + URL)
            return 0
        time.sleep(1)
    say("等待服务超时。请手动运行：venv\\Scripts\\python.exe -m server.main")
    say("然后浏览器打开：" + URL)
    return 1


if __name__ == "__main__":
    sys.exit(main())
