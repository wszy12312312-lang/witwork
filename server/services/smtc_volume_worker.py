"""音量控制子进程 worker（与 smtc.py 配套，必须可被独立 python 进程启动）。

隔离必要性
----------
pycaw 在长时音量轮询中会累积 COM 原生对象并触发进程级 segfault
（本机实测 ~1h17m 后后端崩溃、前端报 Failed to fetch）。这里把「枚举音频会话 +
读 / 写音量」放进独立子进程：每次调用起一个干净进程、做完即退出，操作系统回收
全部 COM 资源 —— 即便单次有轻微泄漏也不会跨调用累积，从根本上消除 segfault。
主进程只通过 IPC 拿一行 JSON 结果；子进程即使崩了也不影响写作后端。

CLI:  python smtc_volume_worker.py <get|set> <app_id> [level]
stdout: 一行 JSON（ensure_ascii=False）。
"""
from __future__ import annotations

import json
import sys


def _proc_image_name(pid: int) -> str:
    """用 ctypes 查进程可执行文件名（不依赖 psutil；pycaw 的 session.Process 在缺 psutil 时恒为 None）。"""
    if not pid:
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
        ]
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return ""
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        try:
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return buf.value
        finally:
            k32.CloseHandle(h)
    except Exception:
        pass
    return ""


def _all_audio_sessions():
    """枚举**所有**渲染端点上的音频会话（覆盖非默认输出设备上的 Edge / HDMI 等）。

    稳定性：本 worker 是「一次性进程」，做完即退，OS 回收全部 COM 资源，故不手动
    Release 包装对象（comtypes 在 GC 时会统一处理）；不存在跨调用累积，也就不会
    触发主进程那种 ~1h 的 segfault。
    """
    try:
        from pycaw.pycaw import AudioUtilities, IAudioSessionControl2  # noqa: F401
        from pycaw.utils import AudioSession
    except Exception:
        return []
    sessions = []
    try:
        import comtypes
        from ctypes import POINTER, cast

        from pycaw.api.audiopolicy import IAudioSessionManager2
        from pycaw.constants import CLSID_MMDeviceEnumerator, DEVICE_STATE, EDataFlow
        from pycaw.pycaw import IMMDeviceEnumerator

        enum = comtypes.CoCreateInstance(
            CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER
        )
        devices = enum.EnumAudioEndpoints(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
        seen = set()
        for i in range(devices.GetCount()):
            dev = devices.Item(i)
            mgr = None
            en = None
            n = 0
            try:
                mgr = cast(
                    dev.Activate(IAudioSessionManager2._iid_, comtypes.CLSCTX_INPROC_SERVER, None),
                    POINTER(IAudioSessionManager2),
                )
                en = mgr.GetSessionEnumerator()
                n = en.GetCount()
            except Exception:
                n = 0
            for j in range(n):
                try:
                    ctl = en.GetSession(j)
                    if ctl is None:
                        continue
                    ctl2 = ctl.QueryInterface(IAudioSessionControl2)
                    if ctl2 is None:
                        continue
                    key = str(getattr(ctl2, "InstanceIdentifier", "") or ctl2.GetProcessId())
                    if key not in seen:
                        seen.add(key)
                        sessions.append(AudioSession(ctl2))  # 持有 ctl2，勿 Release
                except Exception:
                    continue
        if sessions:
            return sessions
    except Exception:
        pass
    # 兜底：退回 pycaw 默认设备枚举
    try:
        return AudioUtilities.GetAllSessions()
    except Exception:
        return []


def _session_proc_name(s) -> str:
    """取音频会话的进程名（小写、含 .exe）；取不到返回空串。"""
    pid = 0
    name = ""
    try:
        pid = int(getattr(s, "ProcessId", 0) or 0)
    except Exception:
        pid = 0
    try:
        p = s.Process  # pycaw 在装了 psutil 时给真 Process 对象
        if p is not None:
            name = p.name() or ""
    except Exception:
        name = ""
    if not name and pid:
        full = _proc_image_name(pid)
        name = full.replace("/", "\\").split("\\")[-1] if full else ""
    return (name or "").lower()


def _match_audio_session(app_id: str):
    """按 SMTC 的 appId 匹配到 pycaw 音频会话（best-effort）。"""
    try:
        from pycaw.pycaw import AudioUtilities
    except Exception:
        return None
    target = (app_id or "").lower()
    segs = [s for s in target.replace("!", ".").split(".") if s]
    best = None
    for s in _all_audio_sessions():
        try:
            if int(getattr(s, "ProcessId", 0) or 0) <= 0:
                continue  # 无进程归属的会话（如系统音）无法对应播放器
        except Exception:
            continue
        name = _session_proc_name(s)
        if not name:
            continue
        if target.endswith(".exe") and name == target:
            return s
        if any(seg and seg in name for seg in segs):
            best = best or s
    return best


def get_volume(app_id: str = ""):
    """读取当前播放 App 的音量。返回 {available, level(0-100), muted, need_pycaw?, error?}。"""
    try:
        from pycaw.pycaw import AudioUtilities  # noqa: F401
    except Exception as e:
        return {"available": False, "level": 0, "muted": False, "need_pycaw": True, "error": "pycaw 不可用：%s" % e}
    try:
        sess = _match_audio_session(app_id)
        if sess is None:
            return {"available": False, "level": 0, "muted": False, "error": "未找到对应音频会话（可能未播放或本机不支持）"}
        v = sess.SimpleAudioVolume
        level = v.GetMasterVolume()
        muted = bool(v.GetMute())
        return {"available": True, "level": int(round(max(0.0, min(1.0, level)) * 100)), "muted": muted}
    except Exception as e:
        return {"available": False, "level": 0, "muted": False, "error": "音量读取失败：%s" % e}


def set_volume(app_id: str, level: int):
    """设置当前播放 App 的音量（0-100）。返回新的音量状态。"""
    try:
        from pycaw.pycaw import AudioUtilities  # noqa: F401
    except Exception as e:
        return {"available": False, "level": 0, "muted": False, "need_pycaw": True, "error": "pycaw 不可用：%s" % e}
    try:
        sess = _match_audio_session(app_id)
        if sess is None:
            return {"available": False, "level": 0, "muted": False, "error": "未找到对应音频会话"}
        v = sess.SimpleAudioVolume
        lvl = max(0.0, min(1.0, float(level) / 100.0))
        v.SetMasterVolume(lvl, None)
        return {"available": True, "level": int(round(lvl * 100)), "muted": bool(v.GetMute())}
    except Exception as e:
        return {"available": False, "level": 0, "muted": False, "error": "音量设置失败：%s" % e}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "get"
    app_id = sys.argv[2] if len(sys.argv) > 2 else ""
    try:
        if mode == "set":
            level = int(sys.argv[3]) if len(sys.argv) > 3 else 0
            out = set_volume(app_id, level)
        else:
            out = get_volume(app_id)
    except Exception as e:  # 任何意外都不让子进程以非零退出（主进程按 JSON 解析）
        out = {"available": False, "level": 0, "muted": False, "error": "音量组件异常：%s" % e}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
