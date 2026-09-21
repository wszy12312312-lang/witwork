"""一次性截图：打开实时应用（8723）的「设置 → 模型」页，验证模型管理 UI。
复用 e2e_ui.py 的代理注入思路，但指向已运行的实时后端（含 qwen3:14b 默认）。
"""
import os, sys, subprocess, threading, urllib.request, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
ROOT = r'C:/Users/wszy1/WorkBuddy/2026-09-18-01-07-46/inkrealm'
CHROME = r'C:/Users/wszy1/AppData/Local/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-win64/chrome-headless-shell.exe'
LIVE = 8723
PROXY = 8796
OUT = os.path.join(ROOT, '_e2e_model.png')

COMMON = r"""
<script>
window.__ir = (function(){
  function q(s,r){ return (r||document).querySelector(s); }
  function qa(s,r){ return Array.prototype.slice.call((r||document).querySelectorAll(s)); }
  function txt(el){ return el ? (el.textContent||'').replace(/\s+/g,' ').trim() : ''; }
  function sleep(ms){ return new Promise(function(r){ setTimeout(r, ms); }); }
  async function waitFor(fn, ms){ var t0=Date.now(); while(Date.now()-t0<(ms||10000)){ try{ if(fn()) return fn(); }catch(e){} await sleep(100);} return null; }
  function btns(){ return qa('.top-actions button'); }
  function byText(list,t){ return list.filter(function(b){ return txt(b)===t; })[0]; }
  return {q:q,qa:qa,txt:txt,sleep:sleep,waitFor:waitFor,btns:btns,byText:byText};
})();
</script>
"""
PROBE = COMMON + r"""
<script>
(function(){
  var I = window.__ir;
  var msg = {ok:true, shot:true};
  (async function(){
    try {
      await I.waitFor(function(){ return I.q('.shell'); }, 20000);
      var setBtn = I.byText(I.btns(), '设置');
      if (setBtn) { setBtn.click(); await I.waitFor(function(){ return I.q('.set-drawer'); }, 10000); }
      var modelTab = I.byText(I.qa('.set-drawer .tab'), '模型');
      if (modelTab) { modelTab.click(); await I.sleep(800); }
      await I.waitFor(function(){ return I.q('.pr-row'); }, 10000);
      msg.modelTabOpen = !!I.q('.pr-row');
      msg.providerRows = I.qa('.pr-row').length;
      msg.defaultShown = I.qa('.pr-star').length;
      msg.hasAddBtn = !!I.byText(I.qa('.set-drawer .acts button'), '+ 新增模型');
      msg.hasDiscover = !!I.byText(I.qa('.set-drawer .acts button'), '探测本地 Ollama');
      // 展开新增表单，确认字段齐全
      var add = I.byText(I.qa('.set-drawer .acts button'), '+ 新增模型');
      if (add) { add.click(); await I.sleep(500); }
      msg.formShown = !!I.q('.mform');
      msg.kindOptions = I.qa('.mform select').length;
    } catch(e) { msg.ok=false; msg.error=String(e); }
    var pre=document.createElement('pre'); pre.id='__diag'; document.body.appendChild(pre);
    pre.textContent='DIAG '+JSON.stringify(msg);
  })();
})();
</script>
"""


class Proxy(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *a): pass
    def _send(self, body, ct, status):
        if ct.startswith('text/html'):
            html = body.decode('utf-8', 'replace')
            if '</body>' in html:
                html = html.replace('</body>', PROBE + '</body>')
            else:
                html = html + PROBE
            body = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', ct)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d%s' % (LIVE, self.path), timeout=20) as r:
                self._send(r.read(), r.headers.get('Content-Type', ''), r.status)
        except Exception:
            self.send_response(502); self.send_header('Content-Length', '0'); self.end_headers()


def main():
    srv = ThreadingHTTPServer(('127.0.0.1', PROXY), Proxy)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = subprocess.run([CHROME, '--no-sandbox', '--hide-scrollbars', '--force-device-scale-factor=1',
                            '--window-size=900,1000', '--virtual-time-budget=30000',
                            '--screenshot=' + OUT, 'http://127.0.0.1:%d/?shot=1' % PROXY],
                           capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=240)
        print('chrome rc=%s' % r.returncode, '->', OUT if os.path.exists(OUT) else 'MISSING')
    finally:
        srv.shutdown()


if __name__ == '__main__':
    main()
