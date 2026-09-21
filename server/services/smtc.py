"""当前播放歌曲检测（Windows SMTC / 系统媒体传输控件）。

原理：Windows 10/11 的 SMTC 会把任何「愿意上报」的播放器（网易云音乐、QQ 音乐、
Spotify、PotPlayer、foobar2000、Edge / Chrome 网页播放器、Groove 等）的曲名、艺术家、
专辑、播放状态、进度汇总到 GlobalSystemMediaTransportControlsSessionManager。
用 winsdk 直接 WinRT 调它，不弹窗、不注入、不读窗口标题 —— 比 UI 自动化干净得多。

设计要点（务必保留）：
- WinRT 对象与**创建它的线程/公寓**绑定，跨线程直接用会炸。所以这里起一条常驻
  守护线程持有 manager，外部通过队列请求；绝不在每次请求里新起 asyncio.run。
- 结果做短 TTL 缓存：前端 3~5s 轮询，握手一次 manager 并不便宜，缓存避免抖动。
- 任何异常都吞掉并降级成 {"ok": false, "error": ...}：歌曲检测失败绝不能影响写作。

本模块在「只读检测」之外，还提供三类**可选**能力（全部失败降级，绝不拖垮检测）：
1. 专辑封面：读 SMTC 会话的 thumbnail 流，缓存成 PNG 字节（按曲目签名变化才重读）。
2. 传输控制：play / pause / toggle / next / prev，走 SMTC 会话的 try_*_async 方法。
3. 音量控制：读 / 设「当前播放 App」的音频会话音量（需 pycaw，缺失则不可用）。
"""
from __future__ import annotations

import base64
import queue
import threading
import time
import sys

_CACHE_TTL = 1.5          # 秒；小于前端轮询间隔即可
_REQ_TIMEOUT = 2.5        # 单次请求最长等多久
_status_names = {0: "Closed", 1: "Opened", 2: "Changing", 3: "Stopped", 4: "Playing", 5: "Paused"}


def _status_name(raw):
    try:
        return _status_names.get(int(raw), str(raw))
    except Exception:
        return str(raw)


class _SmtcThread(threading.Thread):
    """常驻线程：持有 SMTC manager，串行响应读取 / 控制请求。"""

    def __init__(self):
        super().__init__(daemon=True, name="inkrealm-smtc")
        self.inbox: "queue.Queue" = queue.Queue()
        self._fatal: str | None = None

    def run(self):
        manager = None
        loop = None
        try:
            import asyncio

            from winsdk.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as Mgr,
            )
        except Exception as e:  # winsdk 未安装 / 非 Windows
            self._fatal = "SMTC 不可用（需要 Windows + winsdk）：%s" % e
        else:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                manager = loop.run_until_complete(Mgr.request_async())
                if manager is None:
                    self._fatal = "SMTC 会话管理器不可用"
            except Exception as e:
                self._fatal = "SMTC 初始化失败：%s" % e
                manager = None

        while True:
            item = self.inbox.get()
            if item is None:
                break
            box, ev = item
            if self._fatal is not None or manager is None:
                box["error"] = self._fatal or "SMTC 不可用"
                ev.set()
                continue
            try:
                cmd = box.get("cmd", "read")
                if cmd == "control":
                    box["data"] = loop.run_until_complete(self._control(manager, box.get("action")))
                else:
                    box["data"] = loop.run_until_complete(self._read(manager))
            except Exception as e:
                box["error"] = "SMTC 读取失败：%s" % e
            ev.set()

    # ---- 挑选「当前最该展示」的会话对象（返回 WinRT 对象，非 dict） ----
    # 传输控制只需会话对象本身；按「正在播放」优先、否则取第一个。
    @staticmethod
    def _best_session(manager):
        sessions = list(manager.get_sessions())
        for s in sessions:
            try:
                info = s.get_playback_info()
            except Exception:
                info = None
            try:
                playing = _status_name(info.playback_status) == "Playing" if info is not None else False
            except Exception:
                playing = False
            if playing:
                return s
        return sessions[0] if sessions else None

    @staticmethod
    async def _read_cover(session):
        """读会话缩略图，返回 PNG bytes；无封面 / 失败返回 None。"""
        try:
            props = await session.try_get_media_properties_async()
            if props is None:
                return None
            thumb = getattr(props, "thumbnail", None)
            if thumb is None:
                return None
            stream = await thumb.open_read_async()
            if stream is None:
                return None
            from winsdk.windows.storage.streams import DataReader

            size = int(stream.size)
            if size <= 0 or size > 8 * 1024 * 1024:  # 防御：超过 8MB 不当封面
                return None
            reader = DataReader(stream.get_input_stream_at(0))
            loaded = await reader.load_async(size)  # 实际读到的字节数可能小于请求值
            if not loaded or loaded < 64:  # 太小不可能是有效图片
                return None
            buf = bytearray(loaded)
            reader.read_bytes(buf)
            return bytes(buf)
        except Exception:
            return None

    @staticmethod
    async def _control(manager, action: str):
        session = _SmtcThread._best_session(manager)
        if session is None:
            return {"ok": False, "error": "无可用媒体会话"}
        mapping = {
            "play": session.try_play_async,
            "pause": session.try_pause_async,
            "toggle": session.try_toggle_play_pause_async,
            "next": session.try_skip_next_async,
            "prev": session.try_skip_previous_async,
        }
        fn = mapping.get(action)
        if fn is None:
            return {"ok": False, "error": "未知操作：%s" % action}
        try:
            await fn()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": "传输控制失败：%s" % e}

    @staticmethod
    async def _read(manager):
        sessions = []
        for s in manager.get_sessions():
            try:
                props = await s.try_get_media_properties_async()
            except Exception:
                props = None
            try:
                info = s.get_playback_info()
            except Exception:
                info = None
            try:
                tl = s.get_timeline_properties()
            except Exception:
                tl = None

            status = _status_name(info.playback_status) if info is not None else ""
            item = {
                "appId": s.source_app_user_model_id or "",
                "title": (props.title or "") if props else "",
                "artist": (props.artist or "") if props else "",
                "album": (props.album_title or "") if props else "",
                "status": status,
                "playing": status == "Playing",
                "position": round(tl.position.total_seconds(), 2) if tl else 0.0,
                "duration": round(tl.end_time.total_seconds(), 2) if tl else 0.0,
            }
            sessions.append((s, item))

        # 优先级：正在播放 → 有曲名的 → 第一个
        best = None
        best_obj = None
        for obj, it in sessions:
            if it["playing"] and (it["title"] or it["artist"]):
                best, best_obj = it, obj
                break
        if best is None:
            for obj, it in sessions:
                if it["title"] or it["artist"]:
                    best, best_obj = it, obj
                    break
        if best is None and sessions:
            best, best_obj = sessions[0][1], sessions[0][0]

        # ---- 封面缓存：仅当曲目签名变化才重读缩略图 ----
        # 注意：读取失败（如播放器还没准备好封面）不锁定签名，下次轮询会自动重试；
        # 版本号只在真正拿到封面时 +1，前端据此把「音符占位」换成封面图。
        global _cover_bytes, _cover_sig, _cover_version
        if best is not None:
            sig = "%s|%s|%s" % (best["appId"], best["title"], best["artist"])
            if sig != _cover_sig:
                try:
                    data = await _SmtcThread._read_cover(best_obj)
                except Exception:
                    data = None
                if data:
                    _cover_bytes = data
                    _cover_sig = sig
                    _cover_version += 1
                # 失败时不写 _cover_sig → 下一轮轮询继续重试
        else:
            if _cover_sig:
                _cover_bytes = None
                _cover_sig = ""
                _cover_version += 1

        current = best
        sess_list = [it for _, it in sessions]
        return {
            "ok": True,
            "current": current,
            "sessions": sess_list,
            "count": len(sess_list),
            "cover_version": _cover_version,
        }


_thread: _SmtcThread | None = None
_thread_lock = threading.Lock()
_cache: dict = {}
_cache_at = 0.0

# 封面缓存（模块级，由守护线程独占写）
_cover_bytes: bytes | None = None
_cover_sig: str = ""
_cover_version: int = 0


def _ensure_thread() -> _SmtcThread:
    global _thread
    with _thread_lock:
        if _thread is None or not _thread.is_alive():
            _thread = _SmtcThread()
            _thread.start()
        return _thread


def now_playing(force: bool = False):
    """读取当前播放信息。永不抛异常。"""
    global _cache, _cache_at
    ok_cache = bool(_cache) and _cache.get("ok")
    if (not force) and ok_cache and (time.time() - _cache_at) < _CACHE_TTL:
        return _cache

    try:
        th = _ensure_thread()
    except Exception as e:
        return {"ok": False, "error": "SMTC 线程启动失败：%s" % e}

    box: dict = {}
    ev = threading.Event()
    try:
        th.inbox.put_nowait((box, ev))
    except Exception as e:
        return {"ok": False, "error": "SMTC 请求排队失败：%s" % e}

    if not ev.wait(_REQ_TIMEOUT):
        return {"ok": False, "error": "SMTC 读取超时"}

    if "error" in box:
        res = {"ok": False, "error": box["error"]}
    else:
        res = box.get("data") or {"ok": False, "error": "SMTC 无数据"}

    # 只缓存成功结果：失败要能立刻重试（例如用户刚打开播放器）
    if res.get("ok"):
        _cache = res
        _cache_at = time.time()
    return res


def reset_cache():
    global _cache, _cache_at
    _cache = {}
    _cache_at = 0.0


def control(action: str):
    """传输控制：play / pause / toggle / next / prev。永不抛异常。"""
    try:
        th = _ensure_thread()
    except Exception as e:
        return {"ok": False, "error": "SMTC 线程启动失败：%s" % e}
    box: dict = {"cmd": "control", "action": action}
    ev = threading.Event()
    try:
        th.inbox.put_nowait((box, ev))
    except Exception as e:
        return {"ok": False, "error": "SMTC 控制排队失败：%s" % e}
    if not ev.wait(_REQ_TIMEOUT):
        return {"ok": False, "error": "SMTC 控制超时"}
    return box.get("data") or {"ok": False, "error": "SMTC 控制无返回"}


def get_cover_bytes() -> bytes | None:
    """返回当前缓存的封面 PNG 字节（无则 None）。"""
    return _cover_bytes


def get_cover_version() -> int:
    return _cover_version


# ----------------------------------------------------------------------------
# 音量控制（当前播放 App 的音频会话）。需 pycaw；缺失时后台自动 pip 安装一次。
# ----------------------------------------------------------------------------
# pycaw 安装状态：missing（未装）→ installing（后台安装中）→ ready / failed
_pycaw_state = "missing"
_pycaw_lock = threading.Lock()
_pycaw_started = False


def _install_pycaw_async():
    """首次发现缺 pycaw 时，后台线程 pip 安装（整个进程只尝试一次，避免轮询刷 pip）。"""
    global _pycaw_state, _pycaw_started
    with _pycaw_lock:
        if _pycaw_started or _pycaw_state in ("installing", "ready"):
            return
        _pycaw_started = True
        _pycaw_state = "installing"

    def _worker():
        global _pycaw_state
        try:
            import subprocess
            import sys

            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "pycaw", "psutil"],
                capture_output=True,
                text=True,
                timeout=300,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if r.returncode == 0:
                import importlib

                importlib.import_module("pycaw.pycaw")  # 装完先试 import，能过才算 ready
                _pycaw_state = "ready"
            else:
                _pycaw_state = "failed"
        except Exception:
            _pycaw_state = "failed"

    threading.Thread(target=_worker, daemon=True, name="inkrealm-pycaw-install").start()


def _pycaw_unavailable() -> dict:
    """pycaw 导入失败时的统一返回；Windows 下会顺带触发自动安装。"""
    import sys

    if sys.platform == "win32":
        _install_pycaw_async()
        if _pycaw_state == "installing":
            return {
                "available": False,
                "level": 0,
                "muted": False,
                "installing": True,
                "error": "正在自动安装音量控制组件（pycaw），稍等片刻即可使用",
            }
        return {
            "available": False,
            "level": 0,
            "muted": False,
            "installing": False,
            "error": "pycaw 自动安装失败，请手动执行：pip install pycaw",
        }
    return {"available": False, "level": 0, "muted": False, "error": "音量控制仅支持 Windows"}


# ----------------------------------------------------------------------------
# 音量控制：全部 COM 枚举 / 读 / 写都隔离在独立子进程（见 smtc_volume_worker.py）。
# 主进程只做「pycaw 是否可用」的轻量检查（不碰 COM 对象，安全），并触发一次自动安装；
# 真正的音量读写交给子进程，子进程崩了也不影响写作后端。
import os as _os
import json as _json
import subprocess as _subprocess

_WORKER_PATH = _os.path.join(_os.path.dirname(__file__), "smtc_volume_worker.py")


def _run_volume_worker(mode, app_id="", level=None):
    """在独立子进程里读 / 写音量，崩溃隔离。返回 {available, level, muted, ...}。"""
    try:
        cmd = [sys.executable, _WORKER_PATH, mode, app_id or ""]
        if level is not None:
            cmd.append(str(int(level)))
        r = _subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
    except _subprocess.TimeoutExpired:
        return {"available": False, "level": 0, "muted": False, "error": "音量读取超时（已隔离，不影响写作）"}
    except Exception as e:
        return {"available": False, "level": 0, "muted": False, "error": "音量组件调用失败：%s" % e}
    if r.returncode != 0:
        return {"available": False, "level": 0, "muted": False, "error": "音量组件异常退出（已隔离，不影响写作）"}
    out = (r.stdout or "").strip().splitlines()
    if not out:
        return {"available": False, "level": 0, "muted": False, "error": "音量组件无输出"}
    try:
        return _json.loads(out[-1])
    except Exception:
        return {"available": False, "level": 0, "muted": False, "error": "音量组件返回无法解析"}


def get_volume(app_id=""):
    """读取当前播放 App 的音量。返回 {available, level(0-100), muted, installing?, error}。"""
    try:
        import pycaw  # 主进程仅做可用性检查（不创建 COM 对象，安全）
    except Exception:
        return _pycaw_unavailable()
    return _run_volume_worker("get", app_id)


def set_volume(app_id, level):
    """设置当前播放 App 的音量（0-100）。返回新的音量状态。"""
    try:
        import pycaw
    except Exception:
        return _pycaw_unavailable()
    return _run_volume_worker("set", app_id, level)
