"""行级 diff（快照对比用）。纯标准库，离线可用。"""
import difflib


def line_diff(old_text, new_text):
    a = (old_text or "").splitlines()
    b = (new_text or "").splitlines()
    out = []
    sm = difflib.SequenceMatcher(None, a, b)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for line in a[i1:i2]:
                out.append({"type": "eq", "text": line})
        elif tag == "replace":
            for line in a[i1:i2]:
                out.append({"type": "del", "text": line})
            for line in b[j1:j2]:
                out.append({"type": "add", "text": line})
        elif tag == "delete":
            for line in a[i1:i2]:
                out.append({"type": "del", "text": line})
        elif tag == "insert":
            for line in b[j1:j2]:
                out.append({"type": "add", "text": line})
    return out
