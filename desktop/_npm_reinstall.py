import subprocess, os, time

NODE = r"C:\Users\wszy1\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
NPM = r"C:\Users\wszy1\.workbuddy\binaries\node\versions\22.22.2-3\node_modules\npm\bin\npm-cli.js"
DESKTOP = r"C:\Users\wszy1\WorkBuddy\2026-09-18-01-07-46\inkrealm\desktop"
OUT = DESKTOP + r"\reinstall_out.txt"
NM = os.path.join(DESKTOP, "node_modules")
EMPTY = os.path.join(DESKTOP, "_empty")

def log(s):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(s + "\n")

open(OUT, "w", encoding="utf-8").close()
log("=== reinstall start " + time.strftime("%H:%M:%S"))

# 1) fast delete via robocopy mirror from empty dir (handles long paths)
os.makedirs(EMPTY, exist_ok=True)
if os.path.isdir(NM):
    log("robocopy /MIR delete node_modules ...")
    t0 = time.time()
    subprocess.run(
        ["cmd.exe", "/c", "robocopy", "/MIR", EMPTY, NM, "/NFL", "/NDL", "/NJH", "/NJS", "/NP"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200,
    )
    subprocess.run(["cmd.exe", "/c", "rmdir", "/s", "/q", NM],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    log("delete done in %.1fs; exists=%s" % (time.time() - t0, os.path.isdir(NM)))

# 2) clean install from npm cache (prefer-offline -> no network; electron binary reused from %LOCALAPPDATA%/electron/Cache)
env = dict(os.environ)
env["ELECTRON_SKIP_BINARY_DOWNLOAD"] = "0"
log("npm install --prefer-offline ...")
p = subprocess.run(
    [NODE, NPM, "install", "--prefix", DESKTOP, "--prefer-offline",
     "--no-audit", "--no-fund", "--no-optional"],
    cwd=DESKTOP, env=env, capture_output=True, text=True,
    encoding="utf-8", errors="replace", timeout=1800,
)
log("EXIT=" + str(p.returncode))
log("--- STDOUT tail ---\n" + (p.stdout or "")[-5000:])
log("--- STDERR tail ---\n" + (p.stderr or "")[-4000:])
print("done", p.returncode)
