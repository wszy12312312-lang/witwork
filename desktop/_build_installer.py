"""定稿·出安装包：用本地代理把 electron-builder 的二进制下载请求转到 npmmirror。

本机连 GitHub 被墙，electron-builder 打 nsis 安装包需要 nsis-resources / nsis 两份资源，
默认从 GitHub 拉会超时。npmmirror 可达，但 electron-builder 的 Go 下载器默认 UA 被镜像挡成 404。
本脚本在 127.0.0.1:8731 起一个极简代理（用浏览器 UA 从 npmmirror 取文件），
把 ELECTRON_BUILDER_BINARIES_MIRROR 指向它，再跑 electron-builder --win 出 nsis 安装包。
"""
import os
import sys
import time
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import subprocess

R = r'C:/Users/wszy1/WorkBuddy/2026-09-18-01-07-46/inkrealm/desktop'
NODE = r'C:/Users/wszy1/.workbuddy/binaries/node/versions/22.22.2-3/node.exe'
UPSTREAM = 'https://registry.npmmirror.com/-/binary/electron-builder-binaries'
PROXY_PORT = 8731
# 必须带结尾斜杠：electron-builder 拼 URL 时不会自己加分隔符
MIRROR = f'http://127.0.0.1:{PROXY_PORT}/'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        rel = self.path.lstrip('/')
        url = UPSTREAM.rstrip('/') + '/' + rel
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            self.send_response(200)
            self.send_header('Content-Type', r.headers.get('Content-Type', 'application/octet-stream'))
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:  # noqa: BLE001
            msg = f'proxy error: {e}'.encode()
            self.send_response(502)
            self.send_header('Content-Length', str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, *a):  # 静默
        pass


def main():
    srv = ThreadingHTTPServer(('127.0.0.1', PROXY_PORT), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    print(f'proxy up: {MIRROR} -> {UPSTREAM}')

    env = dict(os.environ)
    env.pop('ELECTRON_RUN_AS_NODE', None)
    env.pop('NODE_OPTIONS', None)
    env['CSC_IDENTITY_AUTO_DISCOVERY'] = 'false'
    env['ELECTRON_BUILDER_BINARIES_MIRROR'] = MIRROR

    t0 = time.time()
    p = subprocess.run(
        [NODE, 'node_modules/electron-builder/cli.js', '--win', '--publish', 'never'],
        cwd=R, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace',
    )
    print(f'=== rc={p.returncode}  elapsed={time.time()-t0:.1f}s ===')
    out = (p.stdout or '').strip()
    print('--- STDOUT ---')
    print(out[-2800:])
    print('--- STDERR ---')
    print((p.stderr or '').strip()[-1500:])

    srv.shutdown()
    # 列出产物
    dist = os.path.join(R, 'dist')
    print('--- dist ---')
    for f in sorted(os.listdir(dist)):
        fp = os.path.join(dist, f)
        print(f'  {f}  {os.path.getsize(fp)//1024} KB' if os.path.isfile(fp) else f'  {f}/')


if __name__ == '__main__':
    main()
