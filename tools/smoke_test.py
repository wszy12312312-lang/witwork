"""M1 冒烟测试：覆盖 health / books / chapters / 导出 / 快照 / diff。

运行（mock，无需模型）：
  python tools/smoke_test.py
使用独立临时库，不污染 data/inkrealm.db。
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 用临时库，避免污染开发库
_tmp = Path(tempfile.gettempdir()) / "inkrealm_smoke_test.db"
if _tmp.exists():
    _tmp.unlink()
os.environ["INKREALM_DB"] = str(_tmp)

# 临时配置（与开发库同样的隔离思路），避免改写 data/config.json
_tmp_cfg = Path(tempfile.gettempdir()) / "inkrealm_smoke_test.json"
if _tmp_cfg.exists():
    _tmp_cfg.unlink()
os.environ["INKREALM_CONFIG"] = str(_tmp_cfg)

from fastapi.testclient import TestClient
from server.main import create_app


def main():
    app = create_app()
    with TestClient(app) as c:
        # 1) health
        r = c.get("/api/health")
        assert r.status_code == 200, r.status_code
        assert r.json()["db"] == "ok", r.json()
        print("[1] health ok:", r.json())

        # 2) 新建作品
        b = c.post("/api/books", json={"title": "测试作品"}).json()
        bid = b["id"]
        assert b["title"] == "测试作品"
        print("[2] create book ok id=", bid)

        # 3) 建 3 章，输入约 1000 字
        cids = []
        base = "春去秋来，江湖路远。" * 100  # 1000 字
        for i in range(3):
            ch = c.post(
                "/api/chapters",
                json={"book_id": bid, "title": f"第{i+1}章", "content": base},
            ).json()
            cids.append(ch["id"])
        detail = c.get(f"/api/books/{bid}").json()
        assert len(detail["chapters"]) == 3, detail["chapters"]
        print("[3] create 3 chapters ok")

        # 4) 改第 1 章内容为 2500 字，验证字数统计
        big = "山高水长，云淡风轻。" * 250  # 2500 字
        c.put(f"/api/chapters/{cids[0]}", json={"content": big})
        ch0 = c.get(f"/api/chapters/{cids[0]}").json()
        assert ch0["words"] == 2500, ch0["words"]
        print("[4] update + word count ok words=", ch0["words"])

        # 5) 刷新后内容仍在（重新取详情）
        ch0b = c.get(f"/api/chapters/{cids[0]}").json()
        assert ch0b["content"] == big
        print("[5] content persists ok")

        # 6) 手动快照
        snap = c.post(f"/api/chapters/{cids[0]}/snapshots", json={"title": "快照1"}).json()
        assert snap["words"] == 2500
        print("[6] snapshot ok id=", snap["id"])

        # 7) 修改后恢复快照
        c.put(f"/api/chapters/{cids[0]}", json={"content": "被改动了"})
        c.post(f"/api/chapters/snapshots/{snap['id']}/restore")
        restored = c.get(f"/api/chapters/{cids[0]}").json()
        assert restored["content"] == big, restored["content"][:20]
        print("[7] restore snapshot ok")

        # 8) diff 快照 -> 当前
        d = c.get(f"/api/chapters/{cids[0]}/diff?snapshot_id={snap['id']}").json()
        assert "diff" in d and isinstance(d["diff"], list)
        print("[8] diff ok lines=", len(d["diff"]))

        # 9) 导出 TXT
        r = c.get(f"/api/books/{bid}/export?fmt=txt")
        assert r.status_code == 200
        assert "测试作品" in r.text and "第1章" in r.text
        print("[9] export txt ok bytes=", len(r.text))

        # 10) 软删除 + 列表不再出现（不含回收站）
        c.delete(f"/api/chapters/{cids[2]}")
        detail2 = c.get(f"/api/books/{bid}").json()
        assert len(detail2["chapters"]) == 2, detail2["chapters"]
        print("[10] soft delete ok")

        # 11) 前端静态资源可达（零构建 Vue 运行时）
        # 注意：Windows 大小写不敏感，入口名为 main.js（与 App.js 区分）
        idx = c.get("/")
        assert idx.status_code == 200 and '<div id="app">' in idx.text
        vue = c.get("/vendor/vue.esm-browser.prod.js")
        assert vue.status_code == 200 and vue.headers["content-type"].startswith("text/javascript")
        mainjs = c.get("/src/main.js")
        assert mainjs.status_code == 200 and "createApp" in mainjs.text
        print("[11] frontend static served ok (index/vue/main)")

        # 12) Providers（M2）：默认种子 mock/ollama，连通性探测不崩溃
        provs = c.get("/api/providers").json()
        assert any(p["id"] == "mock" for p in provs), provs
        mt = c.get("/api/providers/test/mock").json()
        assert mt["ok"] is True, mt
        print("[12] providers seeded + mock test ok:", [p["id"] for p in provs])

        # 13) 会话 SSE（M2）：refs -> delta* -> done，且持久化一问一答
        import json as _json
        sid = c.post("/api/sessions", json={"title": "smoke"}).json()["id"]
        r = c.post(f"/api/sessions/{sid}/messages", json={"content": "写一段开场白"})
        events = [ _json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ") ]
        etypes = [e["type"] for e in events]
        assert "refs" in etypes and "delta" in etypes and "done" in etypes, etypes
        assert "error" not in etypes, events
        s = c.get(f"/api/sessions/{sid}").json()
        assert len(s["messages"]) == 2 and s["messages"][-1]["role"] == "assistant"
        print("[13] session SSE ok (refs/delta/done, 1Q1A persisted)")

        # 14) 热切换 + 滚动摘要（M2）：切到极小窗口 provider 触发摘要
        c.post("/api/providers", json={"id": "tiny", "kind": "mock", "name": "tiny", "context_window": 200})
        c.patch(f"/api/sessions/{sid}/provider", json={"provider_id": "tiny"})
        for i in range(12):
            rr = c.post(f"/api/sessions/{sid}/messages", json={"content": f"第{i}轮长内容用于触发滚动摘要机制测试"})
            assert "error" not in rr.text, rr.text
        s2 = c.get(f"/api/sessions/{sid}").json()
        summ = [m for m in s2["messages"] if m.get("is_summary")]
        assert len(summ) >= 1, "应生成滚动摘要"
        print("[14] hot-switch + rolling summary ok (summary msgs=", len(summ), ")")

        # ---------- M3：知识库 / 检索 / 写回 / 人格 / 框架 ----------
        # 15) 默认分区已种子（8 个）
        secs = c.get("/api/kb/sections").json()
        skeys = {s["key"] for s in secs}
        for k in ("worldview", "geography", "faction", "plot", "character", "style", "timeline", "misc"):
            assert k in skeys, skeys
        print("[15] kb default sections seeded:", len(secs))

        # 16) 入库 + 检索命中（哈希向量 + FTS/LIKE 兜底）
        c.post("/api/kb/items", json={"section": "worldview", "title": "星尘", "content": "星尘是悬浮于苍穹之上的能量尘埃，凡人不可见。"})
        ret = c.post("/api/kb/retrieve", json={"query": "星尘", "sections": ["worldview"]}).json()
        assert ret["hits"] and ret["hits"][0]["title"] == "星尘", ret
        print("[16] kb ingest + retrieve ok hits=", len(ret["hits"]))

        # 17) 分区隔离：geography 条目不被 worldview 过滤检索命中
        c.post("/api/kb/items", json={"section": "geography", "title": "东海", "content": "东海是大陆东缘的浩瀚海域。"})
        ret_w = c.post("/api/kb/retrieve", json={"query": "东海", "sections": ["worldview"]}).json()
        assert not ret_w["hits"], ret_w
        ret_all = c.post("/api/kb/retrieve", json={"query": "东海"}).json()
        assert any(h["title"] == "东海" for h in ret_all["hits"]), ret_all
        print("[17] kb partition isolation ok")

        # 18) 版本 + 回滚
        it = c.post("/api/kb/items", json={"section": "plot", "title": "主线", "content": "初版大纲"}).json()
        c.put(f"/api/kb/items/{it['id']}", json={"content": "改版大纲"})
        # version_id 是全局自增，取该条目最旧的那条版本
        vers = c.get(f"/api/kb/items/{it['id']}/versions").json()
        v1 = vers[-1]["id"]
        c.post(f"/api/kb/items/{it['id']}/rollback", json={"version_id": v1})
        itb = c.get(f"/api/kb/items/{it['id']}").json()
        assert itb["content"] == "初版大纲", itb["content"]
        print("[18] kb version + rollback ok")

        # 19) 结构化写回：propose(待确认) -> apply 写库
        from server.core import patch as patch_core
        prop = patch_core.propose(
            {"target_type": "kb_item", "section": "character", "title": "林惊羽", "op": "create",
             "fields": {"content": "林惊羽，少年剑客，性情孤傲。"}},
            session_id=sid, auto=False,
        )
        assert prop["status"] == "pending", prop
        rap = c.post(f"/api/patches/{prop['id']}/apply")
        assert rap.status_code == 200 and rap.json()["status"] == "applied", rap.text
        chars = c.get("/api/kb/items?section=character").json()
        assert any(x["title"] == "林惊羽" for x in chars), chars
        print("[19] patch write-back ok (pending -> applied -> kb item)")

        # 20) 人格：默认种子 + 创建 + 激活 + 自然语言调整(overlay)
        pers = c.get("/api/personas").json()
        assert any(p["name"] == "默认万维文" and p["active"] for p in pers), pers
        newp = c.post("/api/personas", json={"name": "冷峻体", "tone": "冷峻", "temperature": 0.5}).json()
        c.post(f"/api/personas/{newp['id']}/activate")
        pers2 = c.get("/api/personas").json()
        assert any(p["id"] == newp["id"] and p["active"] for p in pers2), pers2
        adj = c.post("/api/personas/adjust", json={"session_id": sid, "statement": "语气改为冷峻、少形容词"}).json()
        assert adj.get("overlay", {}).get("statements", []), adj
        print("[20] personas ok (default/active/adjust overlay)")

        # 21) 检索注入（Step 7）：会话命中知识库并带引用卡
        r = c.post(f"/api/sessions/{sid}/messages", json={"content": "星尘是什么"})
        evs = [_json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")]
        refs_ev = next((e for e in evs if e["type"] == "refs"), None)
        assert refs_ev and any(h["title"] == "星尘" for h in refs_ev["data"]), evs
        print("[21] retrieval injection (Step 7) ok: refs carry citation")

        # 22) 框架共创：推进写回 + 回退标待复核 + 生成章节骨架
        fw = c.get(f"/api/sessions/{sid}/framework").json()
        assert fw["phase"] == "brief", fw
        c.post(f"/api/sessions/{sid}/framework/advance", json={"conclusion": "一句话：少年剑客寻回星尘。"})
        c.post(f"/api/sessions/{sid}/framework/advance", json={"conclusion": "世界观：星尘是能量尘埃。"})
        fw2 = c.get(f"/api/sessions/{sid}/framework").json()
        assert fw2["phase"] == "faction", fw2
        c.post(f"/api/sessions/{sid}/framework/retreat")
        fw3 = c.get(f"/api/sessions/{sid}/framework").json()
        assert "faction" in fw3["needs_review"], fw3
        for conc in [
            "势力：正道联盟 vs 星尘教。",
            "情节：寻回星尘，三幕结构。",
            "人物：林惊羽，动机复仇。",
            "大纲：\n第1章 启程\n第2章 迷雾\n第3章 决战",
        ]:
            c.post(f"/api/sessions/{sid}/framework/advance", json={"conclusion": conc})
        fw4 = c.get(f"/api/sessions/{sid}/framework").json()
        assert fw4["phase"] == "outline", fw4
        wv = c.get("/api/kb/items?section=worldview").json()
        assert any("框架#" in (x["title"] or "") for x in wv), wv
        out = c.post(f"/api/sessions/{sid}/framework/outline", json={"book_id": bid}).json()
        assert out["count"] >= 1, out
        bdetail = c.get(f"/api/books/{bid}").json()
        assert any(v["title"] == "框架大纲" for v in bdetail["volumes"]), bdetail["volumes"]
        print("[22] framework cocreation ok (advance/retreat/outline chapters=", out["count"], ")")

        # ---------- M4：人物 / 伏笔 / 词条 / 角色模板 ----------
        # 23) 角色模板种子 + 用模板建角色（副本）
        tpls = c.get("/api/roles").json()
        assert len(tpls) >= 5, tpls
        t0 = tpls[0]
        made = c.post(f"/api/roles/{t0['id']}/instantiate", json={"book_id": bid, "name": "苏沐"}).json()
        assert made["name"] == "苏沐" and made["template_id"] == t0["id"], made
        print("[23] role templates ok (", len(tpls), ") + instantiate copy")

        # 24) 人物：创建 → 同步 character 分区 → 关系 → 出场记录
        ch1 = c.post("/api/characters", json={"book_id": bid, "name": "林惊羽",
                     "fields": {"catchphrase": "哼", "status_current": "重伤", "taboo": "不提师门"}}).json()
        assert ch1.get("kb_item_id"), ch1
        kbchars = c.get("/api/kb/items?section=character").json()
        assert any(x["title"] == "林惊羽" for x in kbchars), kbchars
        c.post("/api/characters/relations", json={"book_id": bid, "from_id": ch1["id"], "to_id": made["id"], "relation": "师徒"})
        rels = c.get("/api/characters/relations", params={"book_id": bid}).json()
        assert any(r["relation"] == "师徒" for r in rels), rels
        rec = c.post("/api/characters/scan-appearances", json={"book_id": bid, "chapter_id": cids[0], "text": "林惊羽拔剑而出。"}).json()
        assert rec["records"], rec
        print("[24] characters ok (kb sync/relation/appearance)")

        # 25) 伏笔全生命周期：create→plant→call→resolve，事件 4 条，scan 命中
        f = c.post("/api/foreshadow", json={"book_id": bid, "title": "断剑", "content": "决战重铸",
                                            "importance": 5, "keywords": "断剑"}).json()
        for act in ("plant", "call", "resolve"):
            f = c.post(f"/api/foreshadow/{f['id']}/action", json={"action": act, "chapter_id": cids[0]}).json()
        assert f["status"] == "resolved", f
        evs2 = c.get(f"/api/foreshadow/{f['id']}/events").json()
        assert len(evs2) == 4, evs2  # create + plant + call + resolve
        scan = c.post("/api/foreshadow/scan", json={"book_id": bid, "text": "他握紧断剑"}).json()
        assert not scan["matches"], scan  # 已回收，不再提示
        print("[25] foreshadow lifecycle ok (events=", len(evs2), ")")

        # 26) 词条：创建 + 抽词 + 异写归一化改写正文
        ech = c.post("/api/chapters", json={"book_id": bid, "title": "词条章", "content": "星辰闪烁，星辰又落。"}).json()
        e = c.post("/api/entries", json={"book_id": bid, "name": "星尘", "aliases": ["星辰"]}).json()
        cand = c.post("/api/entries/extract", json={"book_id": bid, "chapter_ids": [ech["id"]]}).json()
        assert "candidates" in cand, cand
        norm = c.post("/api/entries/normalize", json={"book_id": bid, "chapter_ids": [ech["id"]]}).json()
        total = sum(norm["replaced"].values())
        assert total == 2, norm
        after = c.get(f"/api/chapters/{ech['id']}").json()
        assert "星尘" in after["content"] and "星辰" not in after["content"], after["content"]
        print("[26] entries ok (extract/normalize replaced=", total, ")")

        # 27) 伏笔与人物卡注入上下文（已回收的不注入，planned/planted 才注入）
        inj = c.get("/api/foreshadow/injection", params={"book_id": bid}).json()
        assert "断剑" not in inj["text"], inj  # 已回收，不再注入（正确行为）
        c.post("/api/foreshadow", json={"book_id": bid, "title": "玉佩", "content": "身世信物",
                                        "importance": 4, "keywords": "玉佩"})
        inj2 = c.get("/api/foreshadow/injection", params={"book_id": bid}).json()
        assert "玉佩" in inj2["text"], inj2
        sess = c.post("/api/sessions", json={"book_id": bid, "title": "m4"}).json()
        r = c.post(f"/api/sessions/{sess['id']}/messages", json={"content": "林惊羽与玉佩"})
        assert "error" not in r.text, r.text[:200]
        print("[27] foreshadow+character injected into session ok")

        # ---------- M5：搜索替换 / 撤销栈 / 爽点 ----------
        # 28) 回归：书籍列表可列（books 无 sort_order 列，曾导致 500）
        bl = c.get("/api/books").json()
        assert any(x["id"] == bid for x in bl), bl
        print("[28] GET /api/books ok (list_books 排序回归)")

        # 29) 搜索 → 预览 → 全部替换 → 撤销恢复
        sres = c.post(f"/api/books/{bid}/search", json={"query": "江湖路远"}).json()
        assert sres["total"] > 0, sres
        assert all(h["line"] >= 1 and h["col"] >= 1 for h in sres["hits"]), sres["hits"][:2]
        prev = c.post(f"/api/books/{bid}/replace", json={"query": "江湖路远", "replacement": "山河依旧", "dry_run": True}).json()
        assert prev["total"] > 0 and prev["results"], prev
        appl = c.post(f"/api/books/{bid}/replace", json={"query": "江湖路远", "replacement": "山河依旧", "dry_run": False}).json()
        assert appl["total"] == prev["total"], (appl, prev)
        after = c.get(f"/api/chapters/{cids[1]}").json()
        assert "山河依旧" in after["content"] and "江湖路远" not in after["content"], after["content"][:40]
        lg = c.get(f"/api/books/{bid}/replace-logs").json()
        assert lg and lg[0]["undone"] == 0, lg
        ur = c.post(f"/api/books/replace-logs/{lg[0]['id']}/undo")
        assert ur.status_code == 200 and ur.json()["undone"] == 1, ur.text
        restored = c.get(f"/api/chapters/{cids[1]}").json()
        assert "江湖路远" in restored["content"], restored["content"][:40]
        print("[29] search/replace/undo ok (replaced=", appl["total"], ")")

        # 30) 撤销栈：push/undo/redo + 状态
        c.post(f"/api/chapters/{cids[0]}/history/push", json={"content": "A", "label": "编辑"})
        c.post(f"/api/chapters/{cids[0]}/history/push", json={"content": "B", "label": "编辑"})
        st = c.get(f"/api/chapters/{cids[0]}/history/status").json()
        assert st["can_undo"] and not st["can_redo"], st
        u1 = c.post(f"/api/chapters/{cids[0]}/history/undo").json()
        assert u1["content"] == "A", u1
        r1 = c.post(f"/api/chapters/{cids[0]}/history/redo").json()
        assert r1["content"] == "B", r1
        print("[30] undo stack ok (depth=", st["depth"], ")")

        # 31) 爽点：模板 + 标注 + 指标 + 建议
        bts = c.get("/api/beats/templates").json()
        assert len(bts) >= 3, bts
        mk = c.post("/api/beats", json={"book_id": bid, "chapter_id": cids[0], "kind": "payoff", "strength": 4}).json()
        assert mk["kind"] == "payoff", mk
        mt = c.get("/api/beats/metrics", params={"book_id": bid, "template_id": bts[0]["id"]}).json()
        assert mt["total_marks"] >= 1 and mt["per_chapter"], mt
        sg = c.get("/api/beats/suggest", params={"book_id": bid, "template_id": bts[0]["id"]}).json()
        assert "suggestions" in sg, sg
        print("[31] beats ok (templates=", len(bts), "marks=", mt["total_marks"], ")")

        # ---------- M5：手机预览 / 排版 / 统计 / 提醒 ----------
        # 32) 排版规则 + 预览只读 + 规范化逐处 changes
        rules = c.get("/api/typeset/rules").json()
        assert rules.get("rules_version"), rules
        messy = '他说:"真的吗..." --不骗你!!\n。行首标点'
        tch = c.post("/api/chapters", json={"book_id": bid, "title": "排版章", "content": messy}).json()
        pv = c.post(f"/api/typeset/chapters/{tch['id']}/preview", json={"content": messy}).json()
        assert '<p class="pv-p"' in pv["html"] and pv["pages"] >= 1, pv
        assert c.get(f"/api/chapters/{tch['id']}").json()["content"] == messy, "预览不得改动正文"
        nz = c.post(f"/api/typeset/chapters/{tch['id']}/normalize", json={"content": messy, "dry_run": True}).json()
        assert nz["changes"], nz
        norm = nz["content"]
        for must in ("：", "……", "——", "“"):
            assert must in norm, (must, norm)
        assert "!!" not in norm, norm
        print("[32] typeset ok (changes=", len(nz["changes"]), ", preview read-only)")

        # 33) 排版写回 + 自动建快照
        ap = c.post(f"/api/typeset/chapters/{tch['id']}/normalize", json={"content": messy, "dry_run": False}).json()
        assert ap.get("snapshot_id"), ap
        saved = c.get(f"/api/chapters/{tch['id']}").json()
        assert saved["content"] == norm, saved["content"]
        snaps = c.get(f"/api/chapters/{tch['id']}/snapshots").json()
        assert any(s["trigger"] == "typeset" for s in snaps), snaps
        print("[33] typeset apply ok (snapshot built)")

        # 34) 统计：保存时 diff 计净增（新增/删除分别计）
        c.put("/api/stats/goals", json={"book_id": bid, "daily_words": 2000})
        before = c.get("/api/stats/today", params={"book_id": bid}).json()["net"]
        sch = c.post("/api/chapters", json={"book_id": bid, "title": "统计章", "content": "甲乙丙"}).json()
        c.put(f"/api/chapters/{sch['id']}", json={"content": "甲乙丙丁戊"})
        after_add = c.get("/api/stats/today", params={"book_id": bid}).json()["net"]
        assert after_add == before + 2, (before, after_add)
        c.put(f"/api/chapters/{sch['id']}", json={"content": "甲乙丙"})
        after_del = c.get("/api/stats/today", params={"book_id": bid}).json()["net"]
        assert after_del == before, (before, after_del)
        hm = c.get("/api/stats/heatmap", params={"book_id": bid}).json()
        assert any(d["net"] != 0 for d in hm), hm
        print("[34] stats ok (net +2 then -2 back to", before, ")")

        # 35) 更新提醒链路
        nt = c.post("/api/stats/reminders/test", json={"book_id": bid}).json()
        assert nt["kind"] == "test", nt
        lst = c.get("/api/stats/notifications").json()
        assert any(n["id"] == nt["id"] for n in lst), lst
        print("[35] reminder ok (notification created)")

        # ---------- M5 Step18：Word 导出与兼容工具 ----------
        # 36) 一键导出 Word（导出前经排版引擎，写 rules_version）
        ed = c.post("/api/export/docx", json={"book_id": bid, "filename": "smoke_export.docx",
                                              "style": {"font": "宋体", "size": 12, "cover": True, "toc": True}}).json()
        assert ed["chapters"] >= 1 and ed["bytes"] > 1000, ed
        assert ed.get("rules_version") == rules["rules_version"], ed
        dl = c.get("/api/export/file", params={"name": "smoke_export.docx"})
        assert dl.status_code == 200, dl.status_code
        assert "wordprocessingml" in dl.headers.get("content-type", ""), dl.headers
        print("[36] export docx ok (chapters=", ed["chapters"], "bytes=", ed["bytes"], ")")

        # 37) 高频词透镜 + AI 味自查
        wf = c.post("/api/tools/word-freq", json={"chapter_ids": [cids[0]], "top_n": 10}).json()
        assert "words" in wf, wf
        at = c.post("/api/tools/ai-taste", json={"text": "首先，随着时间推移。此外，值得注意的是结果。总之，这是一个开始。"}).json()
        assert 0 <= at["score"] <= 100 and at["paragraphs"], at
        print("[37] tools ok (words=", len(wf["words"]), "ai_score=", at["score"], ")")

        # 38) 合规自检 + 外部服务探测（未启动应返回 available=False 而非报错）
        cp = c.post("/api/tools/compliance", json={"text": "加我微信详聊，也可加群。", "custom": ["测试词"]}).json()
        assert cp["total"] >= 2 and any(h["word"] == "微信" for h in cp["hits"]), cp
        sv = c.get("/api/tools/services").json()
        assert "sd_webui" in sv and sv["sd_webui"]["available"] in (True, False), sv
        assert all("hint" in v for v in sv.values()), sv
        print("[38] compliance + service probe ok (hits=", cp["total"], ")")

        # ---------- M6：设置 / 备份 / 导出 收口 ----------
        # 39) 设置读写（隔离的临时 config）
        sc = c.get("/api/settings").json()
        assert "theme" in sc["config"] and "layout_scheme" in sc["config"], sc
        sp = c.put("/api/settings", json={"theme": "light", "layout_scheme": "B"}).json()
        assert sp["theme"] == "light" and sp["layout_scheme"] == "B", sp
        c.put("/api/settings", json={"theme": "dark", "layout_scheme": "A"})
        print("[39] settings get/put ok (isolated config)")

        # 40) 备份：创建 / 列表 / 演练 / 删除
        bk = c.post("/api/backup/create", json={"tag": "smoke"}).json()
        assert bk["name"].endswith(".zip") and bk["files"] >= 1, bk
        lst = c.get("/api/backup/list").json()
        assert any(b["name"] == bk["name"] for b in lst), lst
        dr = c.post("/api/backup/drill", json={"name": bk["name"]}).json()
        assert dr["ok"] and dr["tables"] > 0, dr
        pol = c.get("/api/backup/policy").json()
        assert "keep_n" in pol and "auto_daily" in pol, pol
        c.put("/api/backup/policy", json={"keep_n": 5, "auto_daily": True, "exclude_secrets": True})
        dl = c.request("DELETE", "/api/backup/delete", json={"name": bk["name"]}).json()
        assert dl["deleted"], dl
        assert not any(b["name"] == bk["name"] for b in c.get("/api/backup/list").json()), "删除后不应仍在列表"
        print("[40] backup create/list/drill/policy/delete ok")

        # 41) 导出 MD / EPUB / 设定
        md = c.post("/api/export/md", json={"book_id": bid}).json()
        assert md["download_url"] and md["bytes"] > 0, md
        ep = c.post("/api/export/epub", json={"book_id": bid}).json()
        assert ep["chapters"] >= 1 and ep["download_url"], ep
        fwm = c.post("/api/export/framework", json={"book_id": bid, "fmt": "md"}).json()
        fwj = c.post("/api/export/framework", json={"book_id": bid, "fmt": "json"}).json()
        assert fwm["download_url"] and fwj["download_url"], (fwm, fwj)
        # 下载 MIME：md -> text/markdown；epub -> application/epub+zip
        mdl = c.get("/api/export/file", params={"name": md["path"].split("\\")[-1].split("/")[-1]})
        assert "text/markdown" in mdl.headers.get("content-type", ""), mdl.headers
        epl = c.get("/api/export/file", params={"name": ep["path"].split("\\")[-1].split("/")[-1]})
        assert "application/epub+zip" in epl.headers.get("content-type", ""), epl.headers
        print("[41] export md/epub/framework + download mime ok")

        # 42) 全量重索引端点（切换嵌入模型后必做；此处 hash 模式同样可用）
        ri = c.post("/api/kb/reindex").json()
        assert ri["reindexed"] >= 1 and "mode" in ri and "dim" in ri, ri
        print("[42] kb reindex ok (reindexed=", ri["reindexed"], "mode=", ri["mode"], "dim=", ri["dim"], ")")

        # 清理本测试产生的导出文件
        for fn in (md["path"], ep["path"], fwm["path"], fwj["path"]):
            try:
                Path(fn).unlink()
            except Exception:
                pass
        for extra in ("smoke_export.docx",):
            try:
                (Path(__file__).resolve().parent.parent / "data" / "exports" / extra).unlink()
            except Exception:
                pass

    print("\nSMOKE_OK ✅")


if __name__ == "__main__":
    main()
