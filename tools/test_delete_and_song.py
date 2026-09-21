"""后端回归：单章/单卷删除 + 回收站恢复 + SMTC 歌曲接口 + 设置项。

必须用 `with TestClient(app)`，否则不跑 lifespan（迁移/seed 不会执行）。
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

td = tempfile.mkdtemp(prefix="ir_del_")
os.environ["INKREALM_DATA_DIR"] = td
os.environ["INKREALM_DB"] = os.path.join(td, "t.db")

from fastapi.testclient import TestClient  # noqa: E402
from server.main import app  # noqa: E402

fails = []


def chk(label, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + label + (("  " + str(extra)) if extra else ""))
    if not cond:
        fails.append(label)


with TestClient(app) as c:
    print("== 1. 建作品 / 卷 / 章 ==")
    b = c.post("/api/books", json={"title": "测试书"}).json()
    bid = b["id"]
    v1 = c.post(f"/api/books/{bid}/volumes", json={"title": "第一卷"}).json()
    v2 = c.post(f"/api/books/{bid}/volumes", json={"title": "第二卷"}).json()
    c11 = c.post("/api/chapters", json={"book_id": bid, "volume_id": v1["id"], "title": "1-1"}).json()
    c12 = c.post("/api/chapters", json={"book_id": bid, "volume_id": v1["id"], "title": "1-2"}).json()
    c21 = c.post("/api/chapters", json={"book_id": bid, "volume_id": v2["id"], "title": "2-1"}).json()
    lone = c.post("/api/chapters", json={"book_id": bid, "title": "无卷章"}).json()
    det = c.get(f"/api/books/{bid}").json()
    chk("卷数=2", len(det["volumes"]) == 2, len(det["volumes"]))
    chk("章数=4", len(det["chapters"]) == 4, len(det["chapters"]))

    print("== 2. 单章删除 + 恢复 ==")
    r = c.delete(f"/api/chapters/{c12['id']}")
    chk("DELETE chapter 200", r.status_code == 200, r.text[:120])
    det = c.get(f"/api/books/{bid}").json()
    chk("删后章数=3", len(det["chapters"]) == 3, len(det["chapters"]))
    tr = c.get("/api/books/trash").json()
    chk("回收站含该章", any(x["id"] == c12["id"] for x in tr["chapters"]), tr["chapters"])
    chk("回收站章带作品名", any(x.get("book_title") == "测试书" for x in tr["chapters"]), tr["chapters"][:1])
    r = c.post(f"/api/chapters/{c12['id']}/restore")
    chk("restore chapter 200", r.status_code == 200, r.text[:120])
    det = c.get(f"/api/books/{bid}").json()
    chk("恢复后章数=4", len(det["chapters"]) == 4, len(det["chapters"]))

    print("== 3. 单卷删除（连同其章节）+ 恢复 ==")
    r = c.delete(f"/api/books/volumes/{v1['id']}")
    chk("DELETE volume 200", r.status_code == 200, r.text[:200])
    j = r.json()
    chk("随卷删掉 2 章", j.get("chapters") == 2, j)
    det = c.get(f"/api/books/{bid}").json()
    chk("卷数=1", len(det["volumes"]) == 1, len(det["volumes"]))
    chk("章数=2（只剩卷二 + 无卷章）", len(det["chapters"]) == 2, [x["title"] for x in det["chapters"]])
    tr = c.get("/api/books/trash").json()
    chk("回收站含该卷", any(x["id"] == v1["id"] for x in tr["volumes"]), tr["volumes"])
    chk("随卷删的章不重复列出", not any(x["volume_id"] == v1["id"] for x in tr["chapters"]),
        [(x["title"], x.get("volume_title")) for x in tr["chapters"]])

    r = c.post(f"/api/books/volumes/{v1['id']}/restore")
    chk("restore volume 200", r.status_code == 200, r.text[:200])
    chk("恢复带回 2 章", r.json().get("chapters") == 2, r.json())
    det = c.get(f"/api/books/{bid}").json()
    chk("卷数=2", len(det["volumes"]) == 2, len(det["volumes"]))
    chk("章数=4", len(det["chapters"]) == 4, len(det["chapters"]))

    print("== 4. 精确恢复：单独删的章不会被卷恢复误唤回 ==")
    c.delete(f"/api/chapters/{c11['id']}")           # 先单独删 1-1
    c.delete(f"/api/books/volumes/{v1['id']}")       # 再删整卷（只带上仍在的 1-2）
    r = c.post(f"/api/books/volumes/{v1['id']}/restore").json()
    chk("恢复卷只带回 1 章", r.get("chapters") == 1, r)
    det = c.get(f"/api/books/{bid}").json()
    chk("1-1 仍在回收站未被唤回", c11["id"] not in [x["id"] for x in det["chapters"]],
        [x["title"] for x in det["chapters"]])
    c.post(f"/api/chapters/{c11['id']}/restore")
    det = c.get(f"/api/books/{bid}").json()
    chk("单独恢复 1-1 成功且卷仍在", c11["id"] in [x["id"] for x in det["chapters"]]
        and len(det["volumes"]) == 2, [x["title"] for x in det["chapters"]])

    print("== 5. 404 / 校验 ==")
    chk("删不存在卷 404", c.delete("/api/books/volumes/999999").status_code == 404)
    chk("恢复不存在章 404", c.post("/api/chapters/999999/restore").status_code == 404)
    chk("GET /api/books/trash 未被 {book_id} 吞掉",
        c.get("/api/books/trash").status_code == 200 and "books" in c.get("/api/books/trash").json())

    print("== 6. 歌曲 / SMTC 接口 ==")
    r = c.get("/api/song/now")
    chk("GET /api/song/now 200", r.status_code == 200, r.text[:200])
    j = r.json()
    chk("返回结构含 ok", "ok" in j, j)
    st = c.get("/api/song/status")
    chk("GET /api/song/status 200", st.status_code == 200, st.text[:200])
    print("    song/now =", json.dumps(j, ensure_ascii=False)[:300])
    rr = c.post("/api/song/refresh")
    chk("POST /api/song/refresh 200", rr.status_code == 200, rr.text[:200])

    print("== 7. 设置项 song_autodetect / topbar_alpha ==")
    keys = c.get("/api/settings").json()["keys"]
    chk("DEFAULTS 含 song_autodetect", "song_autodetect" in keys)
    m = c.put("/api/settings", json={"topbar_alpha": 33, "song_autodetect": False}).json()
    chk("topbar_alpha 落库", m.get("topbar_alpha") == 33, m.get("topbar_alpha"))
    chk("song_autodetect 落库", m.get("song_autodetect") is False, m.get("song_autodetect"))
    back = c.get("/api/settings").json()["config"]
    chk("重新读取仍为 33", back.get("topbar_alpha") == 33, back.get("topbar_alpha"))

print()
print("FAILED:", fails if fails else "none")
print("RESULT:", "PASS" if not fails else "FAIL")
