"""ContextBuilder：按预算分配上下文，超预算从最旧消息滚动摘要。

预算比例（占 context_window）：
  人格 10% / 摘要 15% / 检索 25% / 伏笔与人物 10% / 最近对话 30% / 预留输出 10%。
预留 10% 不发送；其余 90% 为输入预算。
摘要优先复用 provider（小任务），无 provider 时退化为拼接。
"""
from server.adapters.tokenizer import estimate_messages
from server.models import sessions as sm


class ContextBuilder:
    # 固定预算占比
    R_PERSONA = 0.10
    R_SUMMARY = 0.15
    R_RETRIEVAL = 0.25
    R_FORESHADOW = 0.10
    R_RECENT = 0.30
    R_RESERVE = 0.10  # 不发送

    def build(self, session_id, provider_row, adapter=None,
              persona_text=None, retrieval_text=None, foreshadow_text=None,
              max_rounds=3):
        cw = int(provider_row.get("context_window") or 8000)
        total_input = int(cw * (1 - self.R_RESERVE))

        fixed = []
        if persona_text:
            fixed.append(("system", persona_text))
        if retrieval_text:
            fixed.append(("system", "[知识检索]\n" + retrieval_text))
        if foreshadow_text:
            fixed.append(("system", "[伏笔与人物]\n" + foreshadow_text))
        fixed_tokens = estimate_messages([{"role": r, "content": c} for r, c in fixed])
        live_budget = total_input - fixed_tokens

        # 读取会话的「已压缩指针」：已被卷进摘要（summary_upto_message_id）的旧
        # 实时消息不再纳入本次 live，避免每轮重新压缩已压缩内容导致摘要重复累积。
        # 注意：这里只做上下文过滤，不删除 DB 中的消息，以保留用户可见的完整聊天记录。
        session = sm.get_session(session_id) or {}
        after_id = session.get("summary_upto_message_id")

        msgs = sm.list_messages(session_id, after_id=after_id)
        summary_rows = [m for m in msgs if m.get("is_summary")]
        live = [m for m in msgs if not m.get("is_summary")]
        existing_summary = summary_rows[-1]["content"] if summary_rows else None

        for _ in range(max_rounds + 1):
            candidate = [{"role": r, "content": c} for r, c in fixed]
            if existing_summary:
                candidate.append({"role": "system", "content": "此前对话摘要：\n" + existing_summary})
            candidate += [{"role": ("user" if m["role"] == "user" else "assistant"), "content": m["content"]} for m in live]

            if estimate_messages(candidate) <= live_budget or len(live) <= 1:
                return {
                    "messages": candidate,
                    "tokens": estimate_messages(candidate),
                    "summary_id": summary_rows[-1]["id"] if summary_rows else None,
                    "live_count": len(live),
                    "summarized": existing_summary is not None,
                }

            # 超预算：压缩最旧的一部分
            drop_n = max(1, len(live) // 3)
            dropped = live[:drop_n]
            last_dropped_id = dropped[-1]["id"]
            live = live[drop_n:]
            dropped_text = (existing_summary + "\n" + self._format(dropped)) if existing_summary else self._format(dropped)
            existing_summary = self._summarize(adapter, dropped_text)
            sid = sm.replace_summary(session_id, existing_summary, last_dropped_id)
            summary_rows = [{"id": sid, "content": existing_summary}]

        # 极端情况下仍返回（可能略超预算，但不丢最新消息）
        candidate = [{"role": r, "content": c} for r, c in fixed]
        if existing_summary:
            candidate.append({"role": "system", "content": "此前对话摘要：\n" + existing_summary})
        candidate += [{"role": ("user" if m["role"] == "user" else "assistant"), "content": m["content"]} for m in live]
        return {
            "messages": candidate,
            "tokens": estimate_messages(candidate),
            "summary_id": summary_rows[-1]["id"] if summary_rows else None,
            "live_count": len(live),
            "summarized": existing_summary is not None,
        }

    def _format(self, msgs) -> str:
        return "\n".join(f"{m['role']}: {m['content']}" for m in msgs)

    def _summarize(self, adapter, text) -> str:
        if not adapter:
            return "[摘要] " + text[-600:]
        prompt = (
            "请用一段简洁的中文概括以下对话要点，保留关键设定、决策与未决问题，"
            "不要复述过程：\n\n" + text
        )
        try:
            parts = []
            for delta in adapter.stream([{"role": "user", "content": prompt}], {"temperature": 0.3}):
                parts.append(delta)
            out = "".join(parts).strip()
            return out or ("[摘要] " + text[-600:])
        except Exception:
            return "[摘要] " + text[-600:]
