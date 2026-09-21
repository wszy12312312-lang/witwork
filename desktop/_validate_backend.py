import subprocess, os, time, tempfile, urllib.request, sys

INK = r"C:\Users\wszy1\WorkBuddy\2026-09-18-01-07-46\inkrealm"
PY = os.path.join(INK, "venv", "Scripts", "python.exe")
TMP = tempfile.mkdtemp(prefix="ir_val_")
env = dict(os.environ)
env["PYTHONPATH"] = INK
env["INKREALM_DATA_DIR"] = TMP

print("spawn backend cwd=", INK, "data=", TMP)
p = subprocess.Popen([PY, "-m", "server.main"], cwd=INK, env=env,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")

# wait for port
ok = False
for _ in range(60):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8723/", timeout=2) as r:
            if r.status == 200:
                ok = True
                break
    except Exception:
        time.sleep(0.5)
print("port ready:", ok)

if ok:
    # fetch SPA html
    html = urllib.request.urlopen("http://127.0.0.1:8723/", timeout=5).read().decode("utf-8", "replace")
    print("index.html bytes:", len(html), "has <div id=app>:", "<div id=\"app\"" in html or 'id="app"' in html)
    # fetch an API
    try:
        api = urllib.request.urlopen("http://127.0.0.1:8723/api/books", timeout=5).read().decode("utf-8", "replace")
        print("api/books status OK, len:", len(api), "head:", api[:120])
    except Exception as e:
        print("api/books err:", String(e)[:200] if (String:=str) else e)
    # confirm db created in TMP (data dir redirect worked)
    print("db in TMP:", os.path.exists(os.path.join(TMP, "inkrealm.db")))
    print("config in TMP:", os.path.exists(os.path.join(TMP, "config.json")))

# dump backend log tail
try:
    out = p.stdout.read(4000) if p.poll() is None else ""
except Exception:
    out = ""
print("--- backend stdout tail ---")
print(out[-2000:] if out else "(running, not captured)")
p.terminate()
try:
    p.wait(timeout=10)
except Exception:
    p.kill()
print("backend stopped")
