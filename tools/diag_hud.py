"""诊断莱茵 HUD 是否真的「显示」出来。

之前的验证只证明 DOM 里有 HUD 文本，没证明它可见。这里在代理层往页面尾部注入
一段脚本：等 .dock 出现后，把 .rh / .dock 的 getBoundingClientRect、computed
display/visibility/opacity/zIndex 以及 data-theme 写进 <pre id="__diag">，
再用 headless 的 --dump-dom 取回（虚拟时间下定时器会立刻推进）。
"""
import json, os, re, subprocess, sys, threading, time, urllib.request, tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = r'C:/Users/wszy1/WorkBuddy/2026-09-18-01-07-46/inkrealm'
PY = os.path.join(ROOT, 'venv', 'Scripts', 'python.exe')
CHROME = r'C:/Users/wszy1/AppData/Local/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-win64/chrome-headless-shell.exe'
APP_PORT, PROXY_PORT = 8791, 8790

PROBE = """
<script>
(function(){
  var tries = 0;
  function box(el){
    if(!el) return 'MISSING';
    var r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),
            display:cs.display,visibility:cs.visibility,opacity:cs.opacity,
            zIndex:cs.zIndex,position:cs.position,transform:cs.transform.slice(0,40)};
  }
  function report(){
    var rh = document.querySelector('.rh'), dock = document.querySelector('.dock');
    var out = {
      dataTheme: document.documentElement.getAttribute('data-theme'),
      shellTheme: (document.querySelector('.shell')||{getAttribute:function(){return null}}).getAttribute('data-theme'),
      topbarAlpha: getComputedStyle(document.documentElement).getPropertyValue('--topbar-alpha'),
      hasRh: !!rh, hasDock: !!dock,
      rh: box(rh), dock: box(dock),
      dockText: dock ? dock.textContent.replace(/\\s+/g,' ').trim().slice(0,150) : '',
      hudMargin: rh ? getComputedStyle(rh).getPropertyValue('--hud-margin') : '',
      bodyBg: getComputedStyle(document.body).backgroundColor,
      shellCount: document.querySelectorAll('.shell').length,
      terminalBtn: !!Array.prototype.find.call(document.querySelectorAll('button'), function(b){return b.textContent.trim()==='终端';})
    };
    var pre = document.getElementById('__diag');
    if(!pre){ pre = document.createElement('pre'); pre.id='__diag'; document.body.appendChild(pre); }
    pre.textContent = 'DIAG ' + JSON.stringify(out);
  }
  var iv = setInterval(function(){ tries++; if((document.querySelector('.dock') && document.querySelector('.rh')) || tries>60){ clearInterval(iv); report(); } }, 120);
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


td = tempfile.mkdtemp(prefix='ir_diag_')
open(os.path.join(td, 'config.json'), 'w', encoding='utf-8').write(json.dumps({
    'port': APP_PORT, 'theme': 'rhine', 'hud_enabled': True, 'rhine_tone': 'dark',
    'hud_texture': True, 'topbar_alpha': 70, 'hud_margins': 22, 'ripple_enabled': True,
}, ensure_ascii=False))

# 传入 external 时：不打自己的实例，直接诊断用户正在运行的服务（默认 8723）
EXTERNAL = len(sys.argv) > 1 and sys.argv[1] == 'external'
if EXTERNAL:
    APP_PORT = int(os.environ.get('INKREALM_PORT', '8723'))

env = dict(os.environ); env['INKREALM_DATA_DIR'] = td; env['PYTHONPATH'] = ROOT; env['PYTHONIOENCODING'] = 'utf-8'
log = open(os.path.join(td, 's.log'), 'w', encoding='utf-8', errors='replace')
app = None if EXTERNAL else subprocess.Popen([PY, '-m', 'server.main'], cwd=ROOT, env=env,
                                             stdout=log, stderr=subprocess.STDOUT)
srv = None
try:
    if not EXTERNAL:
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:%d/api/health' % APP_PORT, timeout=2); break
            except Exception:
                time.sleep(0.5)
    else:
        urllib.request.urlopen('http://127.0.0.1:%d/api/health' % APP_PORT, timeout=5)
        print('诊断目标：用户正在运行的服务 127.0.0.1:%d' % APP_PORT)
    srv = ThreadingHTTPServer(('127.0.0.1', PROXY_PORT), Proxy)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    p = subprocess.run([CHROME, '--no-sandbox', '--hide-scrollbars', '--window-size=1500,940',
                        '--virtual-time-budget=12000', '--dump-dom',
                        'http://127.0.0.1:%d/' % PROXY_PORT],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
    dom = p.stdout or ''
    m = re.search(r'DIAG (\{.*?\})</pre>', dom, re.S)
    if m:
        d = json.loads(m.group(1))
        for k in ('dataTheme', 'shellTheme', 'topbarAlpha', 'hasRh', 'hasDock', 'hudMargin', 'bodyBg', 'shellCount', 'terminalBtn'):
            print('  %-12s = %r' % (k, d.get(k)))
        print('  rh   =', d.get('rh'))
        print('  dock =', d.get('dock'))
        print('  dockText =', d.get('dockText'))
    else:
        print('未取到诊断输出；DOM 长度', len(dom))
        print('含 .dock:', 'class="dock"' in dom, '| 含 RHINE LAB:', 'RHINE LAB' in dom)
        print(dom[-1500:])
finally:
    if srv:
        srv.shutdown()
    if app is not None:
        app.terminate()
        try:
            app.wait(timeout=10)
        except Exception:
            app.kill()
