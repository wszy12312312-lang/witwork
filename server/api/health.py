from fastapi import APIRouter

from server import db as dbm
from server.config import CONFIG_VERSION

router = APIRouter()


@router.get("/health")
def health():
    try:
        conn = dbm.get_conn()
        ok = conn.execute("SELECT 1").fetchone() is not None
        conn.close()
    except Exception:
        ok = False
    return {
        "status": "ok" if ok else "db_error",
        "version": "0.1.0",
        "config_version": CONFIG_VERSION,
        "db": "ok" if ok else "err",
    }
