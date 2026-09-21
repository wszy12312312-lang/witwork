"""B1 回归测试：滚动摘要必须按 summary_upto_message_id 持久裁剪，跨轮不重复压缩。

关键不变量（修复后必须满足）：
  1) 跨多轮 build()，sessions.summary_upto_message_id 必须单调前进（旧 bug 会回退）。
  2) 任意一条消息最多被压缩进摘要一次（被压缩过的旧消息不再进入 live）。
  3) 被压缩的消息仍保留在 DB（保留用户可见聊天记录，仅从 AI 上下文过滤）。

运行（mock，无需模型）：
  python tools/test_rolling_summary.py
使用独立临时库，不污染 data/inkrealm.db。
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = Path(tempfile.gettempdir()) / "inkrealm_rollsum_test.db"
if _tmp.exists():
    _tmp.unlink()
os.environ["INKREALM_DB"] = str(_tmp)
_tmp_cfg = Path(tempfile.gettempdir()) / "inkrealm_rollsum_test.json"
if _tmp_cfg.exists():
    _tmp_cfg.unlink()
os.environ["INKREALM_CONFIG"] = str(_tmp_cfg)

from fastapi.testclient import TestClient
from server.main import create_app
from server.models import sessions as sm
from server.services.context import ContextBuilder


def main():
    app = create_app()
    with TestClient(app) as c:
        provider_row = {"context_window": 200}
        sid = sm.create_session(title="rollsum")["id"]

        added = 0
        def add_turn(n_from, n_to):
            nonlocal added
            for i in range(n_from, n_to + 1):
                sm.add_message(sid, "user", f"MSG{i} 内容占位用于触发滚动摘要压缩机制测试消息编号{i}")
                added += 1

        def upto():
            return sm.get_session(sid).get("summary_upto_message_id")

        def live_ids():
            s = sm.get_session(sid)
            msgs = sm.list_messages(sid, after_id=s.get("summary_upto_message_id"))
            return [m["id"] for m in msgs if not m.get("is_summary")]

        def live_row_count():
            return len([m for m in sm.list_messages(sid) if not m.get("is_summary")])

        builder = ContextBuilder()

        # 第 1 轮：30 条消息，强制压缩
        add_turn(1, 30)
        builder.build(sid, provider_row, adapter=None)
        upto1 = upto()
        assert upto1 is not None and upto1 >= 1, f"应已压缩并设置指针，upto1={upto1}"
        assert not any(i <= upto1 for i in live_ids()), "被压缩消息仍残留于 live（B1 未修复）"
        print(f"[T1] summary_upto={upto1}，live 剩余 {len(live_ids())}")

        # 第 2 轮：再追加 20 条模拟连续对话，再次 build
        add_turn(31, 50)
        builder.build(sid, provider_row, adapter=None)
        upto2 = upto()
        assert upto2 is not None and upto2 > upto1, (
            f"旧 bug：summary_upto 回退/不前进 ({upto1} -> {upto2})，导致已压缩消息被重复压缩"
        )
        assert not any(i <= upto2 for i in live_ids()), "第 1/2 轮已压缩消息又进入 live"
        print(f"[T2] summary_upto={upto2}（前进），live 剩余 {len(live_ids())}")

        # 第 3 轮：继续追加并 build，确认长期单调
        add_turn(51, 80)
        builder.build(sid, provider_row, adapter=None)
        upto3 = upto()
        assert upto3 > upto2, f"summary_upto 未单调前进 ({upto2} -> {upto3})"
        assert not any(i <= upto3 for i in live_ids()), "已压缩消息又进入 live"
        print(f"[T3] summary_upto={upto3}（前进），live 剩余 {len(live_ids())}")

        # 单调前进（核心 B1 不变量）
        assert upto1 < upto2 < upto3, f"summary_upto 非单调：{upto1},{upto2},{upto3}"

        # 历史保留：被压缩的消息仍存在于 DB（仅从上下文过滤，不删除）
        assert live_row_count() == added, (
            f"被压缩消息被误删（应保留聊天记录）：live 行数 {live_row_count()} != 已写入 {added}"
        )
        print(f"[H] 历史保留 OK：{live_row_count()} 条聊天消息仍在 DB 中（未删除）")

        # 上下文有界：live 只占未压缩尾部，远小于总消息数
        assert len(live_ids()) < added, "live 未收缩到未压缩区间"
        print(f"[B] 上下文有界 OK：live={len(live_ids())} << 总消息={added}")

    print("\nROLLING_SUMMARY_OK ✅")


if __name__ == "__main__":
    main()
