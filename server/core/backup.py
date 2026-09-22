"""备份与恢复：一键 zip 备份（db/config/uploads，可选排除密钥）、保留策略、
自动每日备份、恢复演练（只校验不落盘）。

- 备份落在 data/backups/backup-YYYYmmdd-HHMMSS.zip
- 恢复前自动再打一份 pre-restore 备份，避免误操作不可逆
- 演练（drill）解压到临时目录做 integrity_check，不碰线上数据
"""
import sqlite3
import tempfile
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

from server.config import BACKUP_DIR, CONFIG_PATH, DATA_DIR, DB_PATH, SECRETS_PATH, UPLOAD_DIR

DEFAULT_KEEP = 7
_policy = {"keep_n": DEFAULT_KEEP, "auto_daily": True, "exclude_secrets": True}


def get_policy():
    return dict(_policy)


def set_policy(**kw):
    for k in ("keep_n", "auto_daily", "exclude_secrets"):
        if k in kw and kw[k] is not None:
            _policy[k] = kw[k]
    return get_policy()


def _entries(include_uploads=True, exclude_secrets=True):
    items = []
    if DB_PATH.exists():
        items.append(("db/" + DB_PATH.name, DB_PATH))
    if CONFIG_PATH.exists():
        items.append(("config.json", CONFIG_PATH))
    if include_uploads and UPLOAD_DIR.exists():
        for p in UPLOAD_DIR.rglob("*"):
            if p.is_file():
                items.append(("uploads/" + str(p.relative_to(UPLOAD_DIR)).replace("\\", "/"), p))
    if not exclude_secrets and SECRETS_PATH.exists():
        items.append(("secrets.enc", SECRETS_PATH))
    return items


def create_backup(tag=None, include_uploads=True):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    name = tag or ("backup-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    if not name.endswith(".zip"):
        name += ".zip"
    out = BACKUP_DIR / name
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, p in _entries(include_uploads, _policy["exclude_secrets"]):
            z.write(p, arc)
            n += 1
    apply_retention()
    return {"name": name, "path": str(out), "bytes": out.stat().st_size, "files": n,
            "created_at": datetime.now().isoformat(timespec="seconds")}


def _resolve_backup(name) -> Path:
    """把备份文件名解析为绝对路径。

    以前直接 `BACKUP_DIR / name`，name 为 None / 非字符串时会抛
    TypeError: unsupported operand type(s) for /: 'WindowsPath' and 'NoneType'，
    而调用方只捕获 ValueError → 变成 500。这里统一转成 ValueError（→400）。
    同时拒绝带路径分隔符的名字，避免越权读到 backups/ 之外的文件。
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("缺少备份文件名")
    n = name.strip()
    if n != Path(n).name:
        raise ValueError("备份文件名非法（不允许包含路径分隔符）")
    src = BACKUP_DIR / n
    if not src.exists():
        raise ValueError("备份不存在")
    return src


def _safe_join(base: Path, rel: str) -> Path:
    """把 zip 内的相对路径安全地拼到 base 下，阻止 ../ 逃逸（zip slip）。"""
    target = (base / rel).resolve()
    base_r = base.resolve()
    if target != base_r and base_r not in target.parents:
        raise ValueError(f"备份内含非法路径：{rel}")
    return target


def list_backups():
    if not BACKUP_DIR.exists():
        return []
    rows = []
    for p in sorted(BACKUP_DIR.glob("*.zip"), key=lambda x: -x.stat().st_mtime):
        rows.append({"name": p.name, "bytes": p.stat().st_size,
                     "created_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")})
    return rows


def apply_retention():
    keep = int(_policy.get("keep_n", DEFAULT_KEEP) or DEFAULT_KEEP)
    bks = list_backups()
    removed = []
    for b in bks[keep:]:
        try:
            (BACKUP_DIR / b["name"]).unlink()
            removed.append(b["name"])
        except Exception:
            pass
    return removed


def delete_backup(name):
    src = _resolve_backup(name)
    src.unlink()
    return {"name": src.name, "deleted": True}


def restore_backup(name, include_uploads=True):
    """恢复：先打 pre-restore 备份，再解压覆盖。"""
    src = _resolve_backup(name)
    pre = create_backup("pre-restore-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    restored = []
    with zipfile.ZipFile(src) as z:
        for info in z.infolist():
            arc = info.filename
            if arc.startswith("db/"):
                target = DATA_DIR / Path(arc).name
            elif arc == "config.json":
                target = CONFIG_PATH
            elif arc.startswith("uploads/"):
                if not include_uploads:
                    continue
                target = _safe_join(UPLOAD_DIR, arc[len("uploads/"):])
                target.parent.mkdir(parents=True, exist_ok=True)
            elif arc == "secrets.enc":
                target = SECRETS_PATH
            else:
                continue
            with z.open(info) as f, open(target, "wb") as o:
                o.write(f.read())
            restored.append(arc)
    return {"restored": restored, "pre_backup": pre["name"]}


def drill(name):
    """恢复演练：解压到临时目录校验完整性，不改动线上数据。"""
    src = _resolve_backup(name)
    tmp = Path(tempfile.mkdtemp(prefix="inkrealm_drill_"))
    ok, tables, err = False, 0, None
    try:
        with zipfile.ZipFile(src) as z:
            z.extractall(tmp)
        dbs = list((tmp / "db").glob("*.db")) if (tmp / "db").exists() else list(tmp.rglob("*.db"))
        if not dbs:
            err = "备份中没有数据库文件"
        else:
            conn = sqlite3.connect(str(dbs[0]))
            try:
                r = conn.execute("PRAGMA integrity_check").fetchone()
                ok = (r and r[0] == "ok")
                tables = conn.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table'"
                ).fetchone()[0]
            finally:
                conn.close()
    except Exception as e:
        err = str(e)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    return {"ok": ok, "tables": tables, "error": err}


# ---------- 自动每日备份 ----------
_last_day = None
_started = False


def _loop():
    global _last_day
    while True:
        try:
            if _policy.get("auto_daily"):
                today = datetime.now().strftime("%Y%m%d")
                if _last_day != today:
                    if list((BACKUP_DIR).glob(f"backup-{today}-*.zip")) if BACKUP_DIR.exists() else []:
                        _last_day = today
                    else:
                        create_backup()
                        _last_day = today
        except Exception:
            pass
        time.sleep(3600)


def start_auto_backup():
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
