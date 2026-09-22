"""全路由无人值守探测：遍历后端所有注册路由，用最小载荷逐条调用，
找出返回 5xx 的未处理异常（真正的崩溃点）。

用法：
    PYTHONPATH=. python tools/route_smoke.py

安全设计：
- 通过 INKREALM_DATA_DIR 把数据目录指向临时副本，**绝不触碰用户真实数据**。
- 需要模型的端点（SSE / 嵌入 / LLM 抽取）默认跳过并列明，避免长耗时。
- 判定：2xx=OK，4xx=正常拒绝（假数据导致），5xx=BUG，超时/异常单独列出。
"""
import json
import os
import re
import shutil
import sys
import tempfile
import time

# ---- 必须在导入 server.config 之前重定向数据目录 ----
_TMP = tempfile.mkdtemp(prefix="inkrealm_smoke_")
os.environ["INKREALM_DATA_DIR"] = _TMP
os.environ["INKREALM_DB"] = os.path.join(_TMP, "inkrealm.db")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient  # noqa: E402

from server.main import app  # noqa: E402

# 需要真实模型或重计算的端点：跳过（否则单条可能跑几百秒）
SKIP_PATTERNS = [
    "/ai/ops/operate",          # SSE 流式生成
    "/messages",                # SSE 流式对话
    "/kb/reindex",              # 全量重嵌入
    "/tools/ai-taste",          # LLM 评审
    "/tools/compliance",        # 可能联网/LLM
    "/characters/extract",      # LLM 抽取
    "/characters/scan-appearances",
    "/entries/extract",
    "/entries/normalize",
    "/personas/adjust",
    "/foreshadow/scan",
    "/framework/outline",
    "/beats/suggest",
    "/stats/update-plans",      # 依赖定时调度状态
]

PARAM_ORDER = [
    ("book_id", "book"), ("bid", "book"), ("b", "book"),
    ("volume_id", "volume"),
    ("chapter_id", "chapter"), ("cid", "chapter"),
    ("sid", "session"), ("session_id", "session"),
    ("snapshot_id", "snapshot"),
    ("rid", "replacelog"),
    ("item_id", "kbitem"),
    ("persona_id", "persona"),
    ("character_id", "character"),
    ("fid", "foreshadow"),
    ("eid", "entry"),
    ("beat_id", "beat"),
    ("plan_id", "plan"),
    ("nid", "notification"),
]


def build_fixtures(c):
    fx = {}
    fx["book"] = c.post("/api/books", json={"title": "_smoke_书"}).json()["id"]
    fx["volume"] = c.post(f"/api/books/{fx['book']}/volumes", json={"title": "卷"}).json()["id"]
    ch = c.post("/api/chapters", json={
        "book_id": fx["book"], "volume_id": fx["volume"],
        "title": "章", "content": "正文内容。" * 30}).json()
    fx["chapter"] = ch["id"]
    snap = c.post(f"/api/chapters/{fx['chapter']}/snapshots", json={"content": "快照正文"}).json()
    if isinstance(snap, dict) and snap.get("id"):
        fx["snapshot"] = snap["id"]
    s = c.post("/api/sessions", json={"book_id": fx["book"], "title": "smoke"}).json()
    if isinstance(s, dict) and s.get("id"):
        fx["session"] = s["id"]
    it = c.post("/api/kb/items", json={"section": "", "title": "_smoke_kb", "content": "kb 内容"}).json()
    if isinstance(it, dict) and it.get("id"):
        fx["kbitem"] = it["id"]
    per = c.post("/api/personas", json={"name": "_smoke_人格", "prompt": "你是一位小说家"}).json()
    if isinstance(per, dict) and per.get("id"):
        fx["persona"] = per["id"]
    cha = c.post("/api/characters", json={"book_id": fx["book"], "name": "_smoke_角色"}).json()
    if isinstance(cha, dict) and cha.get("id"):
        fx["character"] = cha["id"]
    fo = c.post("/api/foreshadow", json={"book_id": fx["book"], "title": "_smoke_伏笔", "content": "埋"}).json()
    if isinstance(fo, dict) and fo.get("id"):
        fx["foreshadow"] = fo["id"]
    en = c.post("/api/entries", json={"book_id": fx["book"], "term": "_smoke_词条", "definition": "释义"}).json()
    if isinstance(en, dict) and en.get("id"):
        fx["entry"] = en["id"]
    be = c.post("/api/beats", json={"book_id": fx["book"], "chapter_id": fx["chapter"], "kind": "爽点", "note": "n"}).json()
    if isinstance(be, dict) and be.get("id"):
        fx["beat"] = be["id"]
    r = c.post(f"/api/books/{fx['book']}/replace", json={
        "query": "正文", "replacement": "文本", "scope": "book", "dry_run": False})
    if r.status_code < 300:
        logs = c.get(f"/api/books/{fx['book']}/replace-logs").json()
        if logs:
            fx["replacelog"] = logs[0]["id"]
    plans = c.get(f"/api/stats/update-plans?book_id={fx['book']}")
    if plans.status_code < 300 and isinstance(plans.json(), list) and plans.json():
        fx["plan"] = plans.json()[0].get("id")
    notes = c.get(f"/api/stats/notifications?book_id={fx['book']}")
    if notes.status_code < 300 and isinstance(notes.json(), list) and notes.json():
        fx["notification"] = notes.json()[0].get("id")
    return fx


def resolve_params(path_params, fx):
    """按参数名给出 fixture id；未覆盖的用 999999（测试错误处理路径）。"""
    out = {}
    for p in path_params:
        val = 999999
        for name, key in PARAM_ORDER:
            if p == name or p.startswith(name):
                if key in fx:
                    val = fx[key]
                break
        out[p] = val
    return out


def should_skip(path):
    return any(s in path for s in SKIP_PATTERNS)


def main():
    results = {"ok": [], "client": [], "bug": [], "other": []}
    print(f"临时数据目录: {_TMP}\n")
    try:
        with TestClient(app) as c:
            fx = build_fixtures(c)
            print("夹具 id:", fx, "\n")

            paths = app.openapi()["paths"]
            skipped = []
            for raw_path, ops in sorted(paths.items()):
                if should_skip(raw_path):
                    skipped.append(raw_path)
                    continue
                for method in sorted(ops):
                    mu = method.upper()
                    if mu not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                        continue
                    params = resolve_params(re.findall(r"\{(\w+)\}", raw_path), fx)
                    url = raw_path
                    for k, v in params.items():
                        url = url.replace("{" + k + "}", str(v))
                    try:
                        t0 = time.time()
                        if mu in ("POST", "PUT", "PATCH"):
                            r = c.request(mu, url, json={})
                        else:
                            r = c.request(mu, url)
                        dt = time.time() - t0
                        item = (mu, url, r.status_code, round(dt, 2), r.text[:160])
                        if 200 <= r.status_code < 300:
                            results["ok"].append(item)
                        elif 400 <= r.status_code < 500:
                            results["client"].append(item)
                        else:
                            results["bug"].append(item)
                            print(f"  [5xx] {mu} {url} -> {r.status_code}  {r.text[:120]}")
                    except Exception as e:
                        results["other"].append((mu, url, type(e).__name__, str(e)[:160]))
                        print(f"  [EXC] {mu} {url} -> {type(e).__name__}: {str(e)[:120]}")

        print("\n" + "=" * 62)
        print(f"2xx 正常 : {len(results['ok'])}")
        print(f"4xx 拒绝 : {len(results['client'])}（空载荷/假 id 导致，属正常）")
        print(f"5xx 崩溃 : {len(results['bug'])}")
        print(f"异常抛出 : {len(results['other'])}")
        print(f"跳过(需模型): {len(skipped)} 个路径")
        if skipped:
            for s in sorted(set(skipped)):
                print("   -", s)
        if results["bug"]:
            print("\n---- 5xx 明细 ----")
            for mu, url, st, dt, body in results["bug"]:
                print(f"  {mu:<6} {url} -> {st}  ({dt}s)\n        {body}")
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
        print(f"\n已清理临时数据目录: {_TMP}")


if __name__ == "__main__":
    main()
