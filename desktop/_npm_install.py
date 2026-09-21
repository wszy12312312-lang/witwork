import subprocess

NODE = r"C:\Users\wszy1\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
NPM = r"C:\Users\wszy1\.workbuddy\binaries\node\versions\22.22.2-3\node_modules\npm\bin\npm-cli.js"
DESKTOP = r"C:\Users\wszy1\WorkBuddy\2026-09-18-01-07-46\inkrealm\desktop"
OUT = r"C:\Users\wszy1\WorkBuddy\2026-09-18-01-07-46\inkrealm\desktop\install_out.txt"

p = subprocess.run(
    [NODE, NPM, "install", "--prefix", DESKTOP, "--no-audit", "--no-fund"],
    cwd=DESKTOP,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)
with open(OUT, "w", encoding="utf-8") as f:
    f.write("EXIT=" + str(p.returncode) + "\n")
    f.write("--- STDOUT tail ---\n" + (p.stdout or "")[-6000:] + "\n")
    f.write("--- STDERR tail ---\n" + (p.stderr or "")[-4000:] + "\n")
print("done", p.returncode)
