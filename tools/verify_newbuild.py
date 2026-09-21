"""验证「新版」桌面端：后端健康 + 封面 + 音量(带 app_id) + 前端标记。"""
import sys, time, urllib.request, json

BASE = "http://127.0.0.1:8723"


def get(path, timeout=5):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except Exception as e:
        return None, b"", str(e)


def main():
    # 等后端就绪
    for _ in range(40):
        st, _, _ = get("/api/health")
        if st == 200:
            break
        time.sleep(1)
    else:
        print("FAIL: 后端 40s 内未就绪"); sys.exit(1)

    st, body, ct = get("/api/health")
    print("health:", st, body[:80])

    # 封面端点（应 200 image/* 或 ok:false 但结构正常）
    st, body, ct = get("/api/song/cover?v=0")
    print("cover:", st, ct, "bytes=%d" % len(body))

    # 音量带 app_id（结构校验，不要求真有播放器）
    st, body, ct = get("/api/song/volume?app_id=msedge.exe")
    ok = False
    try:
        j = json.loads(body); ok = isinstance(j, dict) and ("available" in j or "installing" in j)
    except Exception:
        pass
    print("volume(app_id=msedge.exe):", st, body[:120], "struct_ok=%s" % ok)

    # 前端标记：抓首页引用的 App.*.js 并查关键字
    st, html, _ = get("/")
    marker_hit = False
    if st == 200:
        import re
        m = re.search(r'/_astro/(App\.[^"]+\.js)', html.decode("utf-8", "replace"))
        if m:
            js_path = "/_astro/" + m.group(1)
            st2, jb, _ = get(js_path)
            for k in ["新增章节", "界面整体不透明度", "/api/song/cover", "正在自动安装音量控制组件", "拖动可调整卷的顺序"]:
                if k.encode("utf-8") in jb:
                    marker_hit = True
            print("frontend bundle:", js_path, "markers_present=%s" % marker_hit)
    print("RESULT:", "PASS" if (st == 200 and marker_hit) else "CHECK")


if __name__ == "__main__":
    main()
