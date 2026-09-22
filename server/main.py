"""FastAPI 入口：挂载静态资源 + 路由，启动即建表。

仅监听 127.0.0.1（本地优先，不暴露到公网）。
运行：python -m server.main  （cwd = inkrealm/）
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import server.db as dbm
import server.adapters.providers as _providers_pkg  # 触发 provider 注册
from server.api import (books, chapters, health, providers, sessions, kb, patches, personas,
                        framework, characters, foreshadow, entries, roles, search, beats, history,
                        typeset, stats, export, tools, backup, settings, ai_ops, song, asr)
from server.config import load_config
from server.models import providers as prov_m
from server.models import knowledge as km_m
from server.models import personas as pers_m
from server.services import role as role_svc
from server.services import beat as beat_svc
from server.services import reminder as rem_svc
from server.core import backup as bk

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class SPAStaticFiles(StaticFiles):
    """带缓存策略的静态托管。

    关键：Astro 构建的 `_astro/*` 资源名带内容哈希，每次重新构建都会换名并删除旧文件。
    若浏览器缓存了旧的 index.html，就会去请求已删除的旧哈希资源 → 404 → 整页空白。
    因此 HTML 一律 no-store（每次校验），哈希资源不可变长缓存，其余短缓存。
    """

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        try:
            p = str(path).replace("\\", "/")
            ctype = resp.headers.get("content-type", "")
            # 目录请求('/' → index.html) 时 path 为空，故以 content-type 判定 HTML 最稳妥
            if ctype.startswith("text/html") or p.endswith(".html") or p.endswith(".htm"):
                resp.headers["Cache-Control"] = "no-store, must-revalidate"
                resp.headers["Pragma"] = "no-cache"
                resp.headers["Expires"] = "0"
            elif "/_astro/" in f"/{p.lstrip('/')}":
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                resp.headers.setdefault("Cache-Control", "public, max-age=3600")
        except Exception:
            pass
        return resp


@asynccontextmanager
async def lifespan(app: FastAPI):
    dbm.init_db()
    prov_m.seed_defaults()       # 保证有 mock/ollama 可用
    km_m.seed_default_sections() # M3：默认 8 个知识库分区
    pers_m.seed_default()        # M3：默认人格
    role_svc.seed()              # M4：5 个角色模板
    beat_svc.seed_templates()    # M5：3 个爽点节奏模板
    rem_svc.start_scheduler()    # M5：更新提醒调度（进程内，每 60s）
    bk.start_auto_backup()       # M6：每日自动备份（每小时检查一次）
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="WitWork 万维文", version="0.1.0", lifespan=lifespan)
    # 路由先于静态挂载，确保 /api/* 不被静态目录拦截
    app.include_router(health.router, prefix="/api")
    app.include_router(books.router, prefix="/api")
    app.include_router(chapters.router, prefix="/api")
    app.include_router(providers.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(kb.router, prefix="/api")
    app.include_router(patches.router, prefix="/api")
    app.include_router(personas.router, prefix="/api")
    app.include_router(framework.router, prefix="/api")
    app.include_router(characters.router, prefix="/api")
    app.include_router(foreshadow.router, prefix="/api")
    app.include_router(entries.router, prefix="/api")
    app.include_router(roles.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(beats.router, prefix="/api")
    app.include_router(history.router, prefix="/api")
    app.include_router(typeset.router, prefix="/api")
    app.include_router(stats.router, prefix="/api")
    app.include_router(export.router, prefix="/api")
    app.include_router(tools.router, prefix="/api")
    app.include_router(ai_ops.router, prefix="/api")
    app.include_router(backup.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")
    app.include_router(song.router, prefix="/api")
    app.include_router(asr.router, prefix="/api")
    # 前端静态资源（SPA）；html=True 时目录请求回退到 index.html
    # 用 SPAStaticFiles 注入缓存策略：HTML no-store，哈希资源 immutable（见类注释）
    app.mount("/", SPAStaticFiles(directory=str(WEB_DIR), html=True), name="web")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        "server.main:app",
        host=cfg.get("host", "127.0.0.1"),
        port=int(cfg.get("port", 8723)),
        reload=False,
    )
