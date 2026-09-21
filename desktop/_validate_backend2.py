import subprocess, os, time, tempfile, urllib.request, json

INK = r"C:\Users\wszy1\WorkBuddy\2026-09-18-01-07-46\inkrealm"
PY = os.path.join(INK, "venv", "Scripts", "python.exe")
TMP = tempfile.mkdtemp(prefix="ir_val2_")
CFG = os.path.join(TMP, "config.json")
PORT = 8799
json.dump({"port": PORT, "config_version": 1}, open(CFG, "w", encoding="utf-8"))
env = dict(os.environ)
env["PYTHONPATH"] = INK
env["INKREALM_DATA_DIR"] = TMP
env["INKREALM_CONFIG"] = CFG

print("spawn backend on port", PORT, "data=", TMP)
p = subprocess.Popen([PY, "-m", "server.main"], cwd=INK, env=env,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")

ok = False
for _ in range(60):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=2) as r:
            if r.status == 200:
                ok = True
                break
    except Exception:
        time.sleep(0.5)
print("port ready:", ok)

if ok:
    html = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=5).read().decode("utf-8", "replace")
    print("index.html bytes:", len(html), "has app mount:", ('id="app"' in html or "id='app'" in html))
    try:
        api = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/books", timeout=5).read().decode("utf-8", "replace")
        print("api/books OK len:", len(api), "head:", api[:100])
    except Exception as e:
        print("api/books err:", str(e)[:200])
    print("db created in TMP data dir:", os.path.exists(os.path.join(TMP, "inkrealm.db")))
    print("config used TMP:", os.path.exists(os.path.join(TMP, "config.json")))
    print("uploads dir in TMP:", os.path.isdir(os.path.join(TMP, "uploads")))
    print("backups dir in TMP:", os.path.isdir(os.path.join(TMP, "backups")))

p.terminate()
try:
    p.wait(timeout=10)
except Exception:
    p.kill()
print("backend stopped")
