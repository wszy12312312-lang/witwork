"""编辑历史：按章节独立的撤销栈（深度 200），持久化到 edit_history。

- 写入（编辑）→ push；撤销 → undo 返回上一版内容；重做 → redo。
- 状态含 can_undo / can_redo / 剩余步数，供界面禁用态与提示。
- 内存栈为主，启动时可从 edit_history 重建，保证重启后仍可撤销。
"""
from server.db import get_conn

MAX_DEPTH = 200


def _persist(cid, content, label=None):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO edit_history(chapter_id, content, label) VALUES (?,?,?)",
            (cid, content, label),
        )
        conn.commit()
    finally:
        conn.close()


def _load(cid):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT content FROM edit_history WHERE chapter_id=? ORDER BY id ASC", (cid,)
        ).fetchall()
        stack = [r["content"] for r in rows]
        return stack[-MAX_DEPTH:] if len(stack) > MAX_DEPTH else stack
    finally:
        conn.close()


class HistoryService:
    def __init__(self):
        self.state = {}  # cid -> {"stack": [...], "idx": int}

    def _ensure(self, cid):
        st = self.state.get(cid)
        if st is None:
            stack = _load(cid)
            st = {"stack": stack, "idx": len(stack) - 1}
            self.state[cid] = st
        return st

    def push(self, cid, content, label=None):
        st = self._ensure(cid)
        # 丢弃 redo 分支
        st["stack"] = st["stack"][: st["idx"] + 1]
        if st["stack"] and st["stack"][-1] == content:
            return self.status(cid)  # 内容未变，不入栈
        st["stack"].append(content)
        if len(st["stack"]) > MAX_DEPTH:
            st["stack"] = st["stack"][-MAX_DEPTH:]
        st["idx"] = len(st["stack"]) - 1
        _persist(cid, content, label)
        return self.status(cid)

    def undo(self, cid):
        st = self._ensure(cid)
        if st["idx"] <= 0:
            return {"content": None, "status": self.status(cid)}
        st["idx"] -= 1
        return {"content": st["stack"][st["idx"]], "status": self.status(cid)}

    def redo(self, cid):
        st = self._ensure(cid)
        if st["idx"] >= len(st["stack"]) - 1:
            return {"content": None, "status": self.status(cid)}
        st["idx"] += 1
        return {"content": st["stack"][st["idx"]], "status": self.status(cid)}

    def status(self, cid):
        st = self._ensure(cid)
        return {"can_undo": st["idx"] > 0, "can_redo": st["idx"] < len(st["stack"]) - 1,
                "undo_left": st["idx"], "redo_left": len(st["stack"]) - 1 - st["idx"],
                "depth": len(st["stack"])}


_svc = None


def get_service():
    global _svc
    if _svc is None:
        _svc = HistoryService()
    return _svc
