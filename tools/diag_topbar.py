"""诊断「顶栏操作层不透明度」为何改了看不出变化。

做法：起一个独立实例（自带 config.json），再用一个注入脚本的本地代理套在页面前，
等 Vue 挂载后把关键计算样式写进 <pre id="__diag">，最后 --dump-dom 取回。
对同一个实例取两次（topbar_alpha=8 / 100）以对比。

用法：
  python tools/diag_topbar.py            # 自起实例诊断
  python tools/diag_topbar.py external   # 诊断用户正在运行的服务（默认 8723）
"""
import json, os, re, subprocess, sys, threading, time, urllib.request, tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = r'C:/Users/wszy1/WorkBuddy/2026-09-18-01-07-46/inkrealm'
PY = os.path.join(ROOT, 'venv', 'Scripts', 'python.exe')
CHROME = r'C:/Users/wszy1/AppData/Local/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-win64/chrome-headless-shell.exe'
APP_PORT, PROXY_PORT = 8793, 8792

PROBE = """
<script>
(function(){
  function cs(sel, prop){
    var el = document.querySelector(sel);
    if(!el) return 'MISSING';
    return getComputedStyle(el).getPropertyValue(prop);
  }
  function box(sel){
    var el = document.querySelector(sel);
    if(!el) return 'MISSING';
    var r = el.getBoundingClientRect(), c = getComputedStyle(el);
    return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),
            z:c.zIndex,pos:c.position,op:c.opacity,bf:(c.backdropFilter||c.webkitBackdropFilter||'').slice(0,40)};
  }
  var tries = 0;
  var iv = setInterval(function(){
    tries++;
    if(!document.querySelector('.topbar') && tries < 80) return;
    clearInterval(iv);
    var shell = document.querySelector('.shell');
    var stage = document.getElementById('stage');
    var out = {
      dataTheme: document.documentElement.getAttribute('data-theme'),
      shellInlineAlpha: shell ? (shell.style.getPropertyValue('--topbar-alpha') || '(none)') : 'NOSHELL',
      shellComputedAlpha: cs('.shell','--topbar-alpha'),
      rootComputedAlpha: getComputedStyle(document.documentElement).getPropertyValue('--topbar-alpha'),
      topbarBg: cs('.topbar','background-color'),
      topbarBackdrop: cs('.topbar','backdrop-filter'),
      topbar: box('.topbar'),
      shell: box('.shell'),
      stageExists: !!stage,
      stageCanvas: !!(stage && stage.querySelector('canvas')),
      stageBox: box('#stage'),
      stageZ: stage ? getComputedStyle(stage).zIndex : '',
      bodyBg: getComputedStyle(document.body).backgroundColor,
      htmlBg: getComputedStyle(document.documentElement).backgroundColor,
      workGridBg: cs('.work-grid','background-color'),
      panelBg: cs('.panel.tree','background-color'),
      panelAlphaVar: cs('.panel.tree','--panel-alpha'),
      panelThemeVar: cs('.panel.tree','--theme-panel'),
      panelAlphaRoot: cs('html','--panel-alpha'),
      fieldAlphaVar: cs('.editor','--field-alpha'),
      editorBg: cs('.editor','background-color'),
      themePaper: cs('body','--theme-paper'),
      themeInk: cs('body','--theme-ink')
    };
    var pre = document.getElementById('__diag');
    if(!pre){ pre = document.createElement('pre'); pre.id='__diag'; document.body.appendChild(pre); }
    pre.textContent = 'DIAG ' + JSON.stringify(out);
  }, 150);
})();
</script>
"""


class Proxy(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def do_GET(self):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d%s' % (APP_PORT, self.path), timeout=20) as r:
                body, ct, status = r.read(), r.headers.get('Content-Type', ''), r.status
        except Exception:
            self.send_response(502); self.send_header('Content-Length', '0'); self.end_headers(); return
        if ct.startswith('text/html'):
            html = body.decode('utf-8', 'replace')
            html = html.replace('</body>', PROBE + '</body>') if '</body>' in html else html + PROBE
            body = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', ct)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)


def set_alpha(alpha):
    with urllib.request.urlopen(
        urllib.request.Request('http://127.0.0.1:%d/api/settings' % APP_PORT, method='PUT',
                               data=json.dumps({'topbar_alpha': alpha}).encode(),
                               headers={'Content-Type': 'application/json'}), timeout=10) as r:
        return json.loads(r.read())['topbar_alpha']


def snapshot(tag):
    p = subprocess.run([CHROME, '--no-sandbox', '--hide-scrollbars', '--window-size=1500,940',
                        '--virtual-time-budget=10000', '--dump-dom',
                        'http://127.0.0.1:%d/' % PROXY_PORT],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
    dom = p.stdout or ''
    m = re.search(r'DIAG (\{.*?\})</pre>', dom, re.S)
    if not m:
        print('  [%s] 未取到诊断输出；DOM 长度 %d' % (tag, len(dom)))
        return None
    d = json.loads(m.group(1))
    print('  --- %s ---' % tag)
    for k in ('dataTheme', 'shellInlineAlpha', 'shellComputedAlpha', 'rootComputedAlpha',
              'topbarBg', 'topbarBackdrop', 'stageExists', 'stageCanvas', 'stageZ',
              'bodyBg', 'themePaper', 'themeInk', 'panelBg'):
        print('    %-20s = %r' % (k, d.get(k)))
    print('    topbar  =', d.get('topbar'))
    print('    stage   =', d.get('stageBox'))
    return d


td = tempfile.mkdtemp(prefix='ir_topbar_')
open(os.path.join(td, 'config.json'), 'w', encoding='utf-8').write(json.dumps(
    {'port': APP_PORT, 'theme': 'dark', 'topbar_alpha': 8}, ensure_ascii=False))

EXTERNAL = len(sys.argv) > 1 and sys.argv[1] == 'external'
if EXTERNAL:
    APP_PORT = int(os.environ.get('INKREALM_PORT', '8723'))

env = dict(os.environ); env['INKREALM_DATA_DIR'] = td; env['PYTHONPATH'] = ROOT
env['PYTHONIOENCODING'] = 'utf-8'; env.pop('NODE_OPTIONS', None)
log = open(os.path.join(td, 's.log'), 'w', encoding='utf-8', errors='replace')
app = None if EXTERNAL else subprocess.Popen([PY, '-m', 'server.main'], cwd=ROOT, env=env,
                                            stdout=log, stderr=subprocess.STDOUT)
srv = None
try:
    if EXTERNAL:
        urllib.request.urlopen('http://127.0.0.1:%d/api/health' % APP_PORT, timeout=5)
        print('诊断目标：正在运行的服务 127.0.0.1:%d' % APP_PORT)
    else:
        for _ in range(80):
            try:
                urllib.request.urlopen('http://127.0.0.1:%d/api/health' % APP_PORT, timeout=2); break
            except Exception:
                time.sleep(0.5)
        else:
            print('服务未起来：')
            print(open(os.path.join(td, 's.log'), encoding='utf-8', errors='replace').read()[-2000:])
            raise SystemExit(1)
    srv = ThreadingHTTPServer(('127.0.0.1', PROXY_PORT), Proxy)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    for a in (8, 100, 8):
        got = set_alpha(a)
        print('  已把 topbar_alpha 设为 %r' % got)
        snapshot('topbar_alpha=%d' % a)
finally:
    if srv:
        srv.shutdown()
    if app is not None:
        app.terminate()
        try:
            app.wait(timeout=10)
        except Exception:
            app.kill()
