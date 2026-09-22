"""本地语音识别（faster-whisper，完全离线）。

产品是「本地优先、离线无云」，而浏览器 Web Speech API 依赖 Google 云识别服务，
在国内网络 / 桌面离线场景下基本不可用。这里提供本地兜底：
浏览器 MediaRecorder 录音 → POST /api/asr/transcribe → faster-whisper 转文字。

- 模型懒加载：第一次真正用到才载入（载入耗时数秒，之后常驻内存）。
- faster-whisper 未安装时返回 501 + 明确提示，前端会把原因显示给用户，
  不再像 Web Speech 那样静默失败。
- 模型名可在设置配置 `asr_model`（tiny/base/small/medium，默认 small，中文 small 起步可懂）。
"""

import os
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile

from server.config import get as cfg_get

router = APIRouter()

_model = None
_model_name = None


def _get_model():
    global _model, _model_name
    name = str(cfg_get("asr_model") or "small")
    if _model is None or _model_name != name:
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise HTTPException(
                501,
                "本地语音识别未就绪：缺少 faster-whisper。请在服务 venv 中执行 pip install faster-whisper",
            ) from e
        # 模型权重自动下载走国内可达的 HF 镜像（已下载过则直接命中本地缓存）
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        # 本机若开了 Windows 系统代理，huggingface_hub 会把请求也走代理 → 502 Bad Gateway。
        # 这里是本机离线识别（甚至根本不需要联网），一律直连。
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "*"
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
            os.environ.pop(k, None)
        try:
            # 优先只用本地缓存：已下载过就不再联网校验（联网校验在本机代理下会 502）
            _model = WhisperModel(name, device="cpu", compute_type="int8", local_files_only=True)
        except Exception:
            # 缓存里没有 → 联网下载一次（HF 镜像 + 直连）
            _model = WhisperModel(name, device="cpu", compute_type="int8")
        _model_name = name
    return _model


@router.get("/asr/status")
def asr_status():
    """前端探测：本地识别是否可用（决定语音按钮走云端 Web Speech 还是本地录音）。"""
    try:
        import faster_whisper  # noqa: F401

        installed = True
    except ImportError:
        installed = False
    return {"installed": installed, "model": cfg_get("asr_model") or "small"}


@router.post("/asr/transcribe")
async def asr_transcribe(file: UploadFile = File(...), lang: str = "zh"):
    data = await file.read()
    if not data:
        raise HTTPException(400, "空音频")

    suffix = ".webm"
    fname = (file.filename or "").lower()
    for ext in (".webm", ".ogg", ".mp3", ".wav", ".m4a", ".aac"):
        if fname.endswith(ext):
            suffix = ext
            break

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
        tmp.close()
        model = _get_model()
        segments, info = model.transcribe(
            tmp.name,
            language=None if lang in ("auto", "") else lang,
            vad_filter=True,
        )
        text = "".join(s.text for s in segments).strip()
        return {"text": text, "language": info.language, "duration": round(info.duration or 0, 2)}
    except HTTPException:
        raise
    except Exception as e:  # 模型下载失败 / 音频解码失败等
        raise HTTPException(500, f"本地识别失败：{e}") from e
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass
