import subprocess, os, sys, time

NODE = r"C:\Users\wszy1\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
INK = r"C:\Users\wszy1\WorkBuddy\2026-09-18-01-07-46\inkrealm"
DESKTOP = os.path.join(INK, "desktop")
OUT = os.path.join(DESKTOP, "pack_out.txt")

def log(s):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(s + "\n")

open(OUT, "w", encoding="utf-8").close()
log("=== pack start " + time.strftime("%H:%M:%S"))

# 0) 确保前端是最新生产构建（web-astro/dist -> web/）
deploy = os.path.join(INK, "web-astro", "deploy_astro.py")
if os.path.exists(deploy):
    log("refresh web/ via deploy_astro.py ...")
    vpy = os.path.join(INK, "venv", "Scripts", "python.exe")
    r = subprocess.run([vpy, deploy], cwd=INK, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    log("deploy rc=%s\n%s" % (r.returncode, (r.stdout or "")[-1500:]))

# 1) electron-builder 打包（使用本地 electron/dist，避免重新下载二进制）
builder = os.path.join(DESKTOP, "node_modules", "electron-builder", "cli.js")
log("electron-builder build ...")
env = dict(os.environ)
env["NODE_PATH"] = os.path.join(DESKTOP, "node_modules")
p = subprocess.run(
    [NODE, builder, "build", "--win", "nsis", "--config", os.path.join(DESKTOP, "package.json")],
    cwd=DESKTOP, env=env, capture_output=True, text=True,
    encoding="utf-8", errors="replace", timeout=1800,
)
log("EXIT=" + str(p.returncode))
log("--- STDOUT tail ---\n" + (p.stdout or "")[-6000:])
log("--- STDERR tail ---\n" + (p.stderr or "")[-5000:])
print("done", p.returncode)
