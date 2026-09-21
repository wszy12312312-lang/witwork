"""全局配置：单一真源（config_version + 默认值 + data/config.json）。

- 所有默认值集中在此，禁止在别处硬编码可配置项。
- 用户覆盖写在 data/config.json，启动时合并。
- 测试可通过环境变量 INKREALM_DB 覆盖数据库路径。
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 允许部署时把数据目录重定向到可写位置（如打包后的 userData）。
# 桌面版 Electron 主进程在首次运行会把只读资源里的 data 播种到可写目录并设置此变量。
_DATA_ENV = os.environ.get("INKREALM_DATA_DIR")
DATA_DIR = Path(_DATA_ENV) if _DATA_ENV else ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_VERSION = 1

_db_env = os.environ.get("INKREALM_DB")
DB_PATH = Path(_db_env) if _db_env else DATA_DIR / "inkrealm.db"
SECRETS_PATH = DATA_DIR / "secrets.enc"
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

DEFAULTS = {
    "config_version": CONFIG_VERSION,
    "host": "127.0.0.1",
    "port": 8723,
    "theme": "dark",                 # dark | light | sepia
    "editor_font_size": 18,
    "editor_line_height": 1.8,
    "editor_page_width": 720,
    "ai_panel_side": "left",         # left | right
    "layout_scheme": "A",            # A | B
    "default_provider_id": None,
    "embedding": "hash",             # hash | bge-m3 | nomic-embed-text
    "embedding_base_url": "http://127.0.0.1:11434/v1/embeddings",
    "retrieval_top_k": 6,
    "auto_writeback": False,         # 仅 create 且无同名时自动落库
    "autosave_delay_ms": 1500,
    "auto_typeset": False,
    "punctuation_normalize": True,
    "phone_chars_per_page": 350,     # 150-800
    "break_days_warn": 3,
    # 手机预览外观（与手机预览面板双向同步）
    "preview_theme": "dark",         # dark | sepia | paper | green | parch
    "preview_font_family": "default",  # default | song | hei | kai | fangsong | mono
    "preview_indent": 2,             # 段首缩进（字符）
    "preview_para_gap": 8,           # 段间距 (px)
    # ---- 最表层 UI（顶栏）与功能面板 ----
    # 注意：save_config 只持久化出现在 DEFAULTS 中的键，新增可配置项必须登记在此。
    "topbar_alpha": 78,              # 顶栏操作层不透明度 0-100（所有预设通用）
    "hud_enabled": False,            # 是否开启左侧功能面板
    "hud_texture": True,             # 功能面板质感：扫线
    "hud_widgets": "time,today,countdown,song,focus",  # 功能面板启用的部件
    "song_autodetect": True,        # 歌曲部件：用系统 SMTC 自动检测当前播放（关＝纯手动填写）
    "editor_ruled_lines": False,    # 写作区信纸横线（随滚动对齐行高）
    "ai_timeout": 300,              # AI 单次请求超时（秒）：本地大模型首字慢，60s 会被中途掐断
    "config_version": CONFIG_VERSION,
}

_config_cache = None


def load_config():
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    data = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(user, dict):
                data.update(user)
        except Exception:
            pass
    data["config_version"] = CONFIG_VERSION
    _config_cache = data
    return data


CONFIG_PATH = Path(os.environ.get("INKREALM_CONFIG")) if os.environ.get("INKREALM_CONFIG") else DATA_DIR / "config.json"


def save_config(data: dict):
    global _config_cache
    # 以「已加载的配置（默认 + 用户覆盖）」为基底合并，避免只从 DEFAULTS 重建时
    # 把用户自定义项（如 embedding=bge-m3）覆盖回默认值。
    base = load_config()
    merged = dict(base)
    merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    merged["config_version"] = CONFIG_VERSION
    CONFIG_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    _config_cache = merged
    return merged


def get(key, default=None):
    return load_config().get(key, default)


def reload():
    global _config_cache
    _config_cache = None
    return load_config()
