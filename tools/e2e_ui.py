"""UI 端到端验收（无头 Chromium，真实点击 + 真实网络）。

为什么这么做：早期版本用 `--virtual-time-budget` + `--dump-dom`，虚拟时钟会把 9s 的等待
瞬间走完，而真实 fetch 还没回来 → 写操作（删除）拿不到结果，被误判成失败。
现在改成：页面把结果 POST 回本地代理，主机侧按真实时间等待；代理同时转发页面的
GET/POST/PUT/DELETE（否则页面里的 fetch 会打到代理而不是后端）。

两趟：
  A) 截图趟：--virtual-time-budget + --screenshot，只读（打开作品 / 目录树 / 功能面板），
     并临时强制显示「悬停才出现」的删除按钮，便于肉眼核对。
  B) 验收趟：真实时间，跑完整流程（改透明度 → 删章节 → 回收站恢复 → 删整卷 → 恢复），
     结果 POST 回主机。

覆盖本次四项改动：
  1. 顶栏（操作层）不透明度可改（拖动即时生效 + 松手落库）
  2. 歌曲部件接 Windows SMTC
  3. 单章 / 单卷删除按钮 + 回收站三类恢复
  4. 暗色确实变暗，且 :root 令牌生效（面板实底 / 1.2 倍 / 圆角 / MiSans）

用法：
  python tools/e2e_ui.py            # dark
  python tools/e2e_ui.py light      # 换主题
  python tools/e2e_ui.py dark shot  # 额外存截图
"""
import json, os, re, subprocess, sys, threading, time, urllib.request, tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 本机若启用了系统代理（Windows 注册表 ProxyEnable），urllib 默认会把 127.0.0.1 也走代理，
# 导致本地后端 / 代理转发全部 502。验收是纯本地环路，强制直连，绕过一切代理。
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

ROOT = r'C:/Users/wszy1/WorkBuddy/2026-09-18-01-07-46/inkrealm'
PY = os.path.join(ROOT, 'venv', 'Scripts', 'python.exe')
CHROME = r'C:/Users/wszy1/AppData/Local/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-win64/chrome-headless-shell.exe'
APP_PORT, PROXY_PORT = 8795, 8794

THEME = sys.argv[1] if len(sys.argv) > 1 else 'dark'
WANT_SHOT = len(sys.argv) > 2 and sys.argv[2] == 'shot'
SHOT = os.path.join(ROOT, '_e2e_ui_%s.png' % THEME)

COMMON = r"""
<script>
window.__ir = (function(){
  function q(s, r){ return (r||document).querySelector(s); }
  function qa(s, r){ return Array.prototype.slice.call((r||document).querySelectorAll(s)); }
  function cs(el, p){ return el ? getComputedStyle(el).getPropertyValue(p) : 'MISSING'; }
  function txt(el){ return el ? (el.textContent||'').replace(/\s+/g,' ').trim() : ''; }
  function sleep(ms){ return new Promise(function(r){ setTimeout(r, ms); }); }
  async function waitFor(fn, ms, label, errs){
    var t0 = Date.now();
    while (Date.now() - t0 < (ms||10000)) {
      try { var v = fn(); if (v) return v; } catch(e){ if(errs) errs.push(label+': '+e.message); }
      await sleep(100);
    }
    return null;
  }
  function btns(){ return qa('.top-actions button'); }
  function byText(list, t){ return list.filter(function(b){ return txt(b) === t; })[0]; }
  return { q:q, qa:qa, cs:cs, txt:txt, sleep:sleep, waitFor:waitFor, btns:btns, byText:byText };
})();
</script>
"""

# ---------- 截图趟（只读） ----------
SHOT_PROBE = COMMON + r"""
<script>
(function(){
  var I = window.__ir;
  (async function(){
    var msg = {ok: true, shot: true};
    try {
      await I.waitFor(function(){ return I.q('.shell') && I.q('.book-row'); }, 20000);
      I.q('.book-row').click();
      await I.waitFor(function(){ return I.q('.vol-row'); }, 12000);
      var st = document.createElement('style');
      st.textContent = '.row-del{opacity:1 !important}';
      document.head.appendChild(st);
      await I.waitFor(function(){ return I.q('.rdock'); }, 10000);
      // 打开设置抽屉，展示顶栏透明度滑块；不改数值，避免破坏后续验收趟的基线 78%
      var setBtn = I.byText(I.btns(), '设置');
      if (setBtn) { setBtn.click(); await I.waitFor(function(){ return I.q('.set-drawer'); }, 10000); }
      // 展开歌曲部件，展示 SMTC 检测界面
      var term = I.byText(I.btns(), '终端');
      if (term) { term.click(); await I.sleep(600); }
      var songBtn = I.qa('.rdock .w-l, .rdock button, .rdock [role="button"]').filter(function(e){ return /歌曲/.test(I.txt(e)); })[0];
      if (songBtn) { songBtn.click(); await I.sleep(800); }
      await I.sleep(1200);
      msg.chDel = I.qa('.row-del').length;
      msg.volDel = I.qa('.vol-row .rd').length;
      msg.settingsOpen = !!I.q('.set-drawer');
      msg.songOpen = !!I.q('.song-info, .song-widget, [class*="song"]');
    } catch(e) { msg.ok = false; msg.error = String(e); }
    var pre = document.createElement('pre'); pre.id='__diag'; document.body.appendChild(pre);
    pre.textContent = 'DIAG ' + JSON.stringify(msg);
  })();
})();
</script>
"""

# ---------- 验收趟（真实时间，结果 POST 回主机） ----------
VERIFY_PROBE = COMMON + r"""
<script>
(function(){
  var I = window.__ir;
  var out = { steps: [], errors: [] };
  function log(s){ out.steps.push(s); }
  function done(){
    try {
      fetch('/__diag__', { method: 'POST', cache: 'no-store',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(out) });
    } catch(e) {}
    var pre = document.getElementById('__diag');
    if(!pre){ pre = document.createElement('pre'); pre.id='__diag'; document.body.appendChild(pre); }
    pre.textContent = 'DIAG ' + JSON.stringify(out);
  }
  (async function(){
    try {
      await I.waitFor(function(){ return I.q('.shell') && I.q('.book-row'); }, 25000, 'wait shell', out.errors);
      log('mounted');

      // ---- 第 4 项：令牌 + 主题 ----
      // 必须等主题真的切到期望值：bootstrap 里 loadBooks 早于 loadSettings，
      // 只等 .book-row 会在主题应用前就读到默认暗色，误判成「亮色不亮」。
      await I.waitFor(function(){
        return document.documentElement.getAttribute('data-theme') === '__EXPECTED_THEME__'
            && I.cs(document.body, '--theme-paper');
      }, 20000, 'wait theme', out.errors);
      var shell = I.q('.shell'), panel = I.q('.panel.tree'), topbar = I.q('.topbar');
      out.theme = document.documentElement.getAttribute('data-theme');
      out.bodyBg = getComputedStyle(document.body).backgroundColor;
      out.themePaper = I.cs(document.body, '--theme-paper');
      out.themeInk = I.cs(document.body, '--theme-ink');
      out.panelAlphaVar = I.cs(panel, '--panel-alpha');
      out.panelBg = panel ? getComputedStyle(panel).backgroundColor : 'MISSING';
      out.uiScale = I.cs(document.documentElement, '--ui-scale');
      out.fontFamily = getComputedStyle(document.body).fontFamily.slice(0, 60);
      out.radius = panel ? getComputedStyle(panel).borderRadius : 'MISSING';
      out.motionVar = I.cs(document.body, '--motion').slice(0, 40);
      out.scrimVar = I.cs(document.body, '--theme-scrim');
      log('tokens ok');

      // ---- 第 3 项：目录树按钮 ----
      I.q('.book-row').click();
      await I.waitFor(function(){ return I.q('.vol-row'); }, 15000, 'wait vol', out.errors);
      out.volRows = I.qa('.vol-row').length;
      out.chRows = I.qa('.ch').length;
      out.chDeleteButtons = I.qa('.row-del').length;
      out.volDeleteButtons = I.qa('.vol-row .rd').length;
      out.bookDeleteButtons = I.qa('.book-row .rd').length;
      log('tree vol=' + out.volRows + ' ch=' + out.chRows + ' chDel=' + out.chDeleteButtons
          + ' volDel=' + out.volDeleteButtons);

      // ---- 第 1 项：顶栏不透明度 ----
      var setBtn = I.byText(I.btns(), '设置');
      if (setBtn) setBtn.click();
      await I.waitFor(function(){ return I.q('.set-drawer'); }, 10000, 'wait drawer', out.errors);
      var rng = I.q('.set-drawer input[type=range]');
      out.alphaBefore = I.cs(shell, '--topbar-alpha');
      out.topbarBgBefore = topbar ? getComputedStyle(topbar).backgroundColor : 'MISSING';
      if (rng) {
        out.rangeLabel = I.txt(I.q('span', rng.closest('label')));
        rng.value = '15';
        rng.dispatchEvent(new Event('input', { bubbles: true }));
        await I.sleep(500);
        out.alphaAfterInput = I.cs(shell, '--topbar-alpha');
        out.topbarBgAfterInput = topbar ? getComputedStyle(topbar).backgroundColor : 'MISSING';
        rng.dispatchEvent(new Event('change', { bubbles: true }));
        await I.sleep(2000);
        out.alphaSaved = I.cs(shell, '--topbar-alpha');
        try {
          var cfg = await (await fetch('/api/settings', { cache: 'no-store' })).json();
          out.alphaPersisted = cfg.config.topbar_alpha;
        } catch (e) { out.errors.push('read settings: ' + e.message); }
        log('alpha ' + out.alphaBefore + ' -> ' + out.alphaAfterInput + ' -> persisted ' + out.alphaPersisted);
        rng.value = '78';
        rng.dispatchEvent(new Event('input', { bubbles: true }));
        rng.dispatchEvent(new Event('change', { bubbles: true }));
        await I.sleep(1500);
      } else { out.errors.push('range input not found'); }
      var xb = I.q('.set-drawer .x'); if (xb) xb.click();
      await I.sleep(600);

      // ---- 第 2 项：歌曲部件 ----
      var term = I.byText(I.btns(), '终端');
      if (term) term.click();
      await I.waitFor(function(){ return I.q('.rdock'); }, 10000, 'wait dock', out.errors);
      out.dockExists = !!I.q('.rdock');
      var songLabel = I.qa('.w-l').filter(function(e){ return /歌曲/.test(I.txt(e)); })[0];
      out.dockSongSection = !!songLabel;
      out.dockSongAutoBadge = I.txt(songLabel);
      out.dockSongInfo = I.txt(I.q('.song-info'));
      try {
        var sg = await (await fetch('/api/song/now', { cache: 'no-store' })).json();
        out.songApi = { ok: sg.ok, count: sg.count, title: sg.current && sg.current.title,
                        app: sg.current && sg.current.appId, playing: sg.current && sg.current.playing };
      } catch (e) { out.errors.push('song api: ' + e.message); }
      log('dock=' + out.dockExists + ' song=' + JSON.stringify(out.songApi));

      // ---- 第 3 项：删章节（真实点击）----
      var chBefore = I.qa('.ch').length;
      out.chBeforeDelete = chBefore;
      var delBtn = I.q('.ch .row-del .rd-main');
      if (delBtn) {
        delBtn.click();
        await I.sleep(350);
        out.confirmPanelShown = !!I.q('.ch .row-del .rd-panel');
        var ok = I.q('.ch .row-del .rd-act.ok');
        if (ok) { ok.click(); out.confirmClicked = true; }
        else out.errors.push('confirm ok button missing');
        await I.waitFor(function(){ return I.qa('.ch').length < chBefore; }, 20000, 'wait ch delete', out.errors);
      } else { out.errors.push('chapter delete button not found'); }
      out.chAfterDelete = I.qa('.ch').length;
      log('chapter ' + chBefore + ' -> ' + out.chAfterDelete);

      // ---- 第 3 项：回收站 ----
      var tb = I.byText(I.qa('.panel-head button'), '回收站');
      if (tb) tb.click();
      await I.waitFor(function(){ return I.q('.trash-sec'); }, 15000, 'wait trash', out.errors);
      await I.sleep(800);
      out.trashSections = I.qa('.trash-sec').map(I.txt);
      out.trashRows = I.qa('.trash-row').length;
      out.trashMetas = I.qa('.trash-row .meta').map(I.txt);
      log('trash ' + JSON.stringify(out.trashSections) + ' rows=' + out.trashRows);

      var rb = I.qa('.trash-row .mini').filter(function(b){ return I.txt(b) === '恢复'; })[0];
      if (rb) { rb.click(); await I.sleep(3000); }
      out.trashRowsAfterRestore = I.qa('.trash-row').length;
      var back = I.byText(I.qa('.panel-head button'), '返回作品');
      if (back) back.click();
      await I.sleep(2500);
      out.chAfterRestore = I.qa('.ch').length;
      log('restore -> trash ' + out.trashRowsAfterRestore + ' ch ' + out.chAfterRestore);

      // ---- 删整卷 → 章节一起收起 → 恢复 ----
      var volDel = I.q('.vol-row .rd-main');
      if (volDel) {
        var volBefore = I.qa('.vol-row').length, chB2 = I.qa('.ch').length;
        volDel.click();
        await I.sleep(350);
        var ok2 = I.q('.vol-row .rd-act.ok');
        if (ok2) ok2.click();
        else out.errors.push('volume confirm ok missing');
        await I.waitFor(function(){ return I.qa('.vol-row').length < volBefore; }, 20000, 'wait vol delete', out.errors);
        out.volBeforeDelete = volBefore;
        out.volAfterDelete = I.qa('.vol-row').length;
        out.chBeforeVolDelete = chB2;
        out.chAfterVolDelete = I.qa('.ch').length;
        var tb2 = I.byText(I.qa('.panel-head button'), '回收站');
        if (tb2) tb2.click();
        await I.waitFor(function(){ return I.q('.trash-sec'); }, 15000, 'wait trash2', out.errors);
        await I.sleep(800);
        out.trashSections2 = I.qa('.trash-sec').map(I.txt);
        out.trashMetas2 = I.qa('.trash-row .meta').map(I.txt);
        var rv = I.qa('.trash-row .mini').filter(function(b){ return I.txt(b) === '恢复'; });
        if (rv.length) { rv[0].click(); await I.sleep(3000); }
        var back2 = I.byText(I.qa('.panel-head button'), '返回作品');
        if (back2) back2.click();
        await I.sleep(2500);
        out.volAfterRestore = I.qa('.vol-row').length;
        out.chAfterVolRestore = I.qa('.ch').length;
        log('volume ' + out.volBeforeDelete + ' -> ' + out.volAfterDelete + ' -> ' + out.volAfterRestore
            + ' | ch ' + out.chBeforeVolDelete + ' -> ' + out.chAfterVolDelete + ' -> ' + out.chAfterVolRestore);
      } else { out.errors.push('volume delete button not found'); }
    } catch (e) {
      out.errors.push('FATAL: ' + (e && (e.stack || e.message)));
    }
    done();
  })();
})();
</script>
"""

STATE = {'diag': None}
DIAG_EV = threading.Event()
PROX_COUNT = {'n': 0}


class Proxy(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def _send(self, body, ct, status):
        if ct.startswith('text/html'):
            html = body.decode('utf-8', 'replace')
            probe = SHOT_PROBE if 'shot=1' in self.path else VERIFY_PROBE
            probe = probe.replace('__EXPECTED_THEME__', THEME)
            html = html.replace('</body>', probe + '</body>') if '</body>' in html else html + probe
            body = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', ct)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d%s' % (APP_PORT, self.path), timeout=20) as r:
                self._send(r.read(), r.headers.get('Content-Type', ''), r.status)
        except Exception:
            self.send_response(502); self.send_header('Content-Length', '0'); self.end_headers()

    def _forward(self, method):
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n) if n else None
        try:
            req = urllib.request.Request('http://127.0.0.1:%d%s' % (APP_PORT, self.path), data=raw, method=method,
                                         headers={'Content-Type': self.headers.get('Content-Type', 'application/json')})
            with urllib.request.urlopen(req, timeout=30) as r:
                self._send(r.read(), r.headers.get('Content-Type', ''), r.status)
        except urllib.error.HTTPError as e:
            self._send(e.read(), e.headers.get('Content-Type', 'application/json'), e.code)
        except Exception as e:
            self._send(json.dumps({'error': str(e)}).encode(), 'application/json', 502)

    def do_POST(self):
        if self.path.startswith('/__diag__'):
            n = int(self.headers.get('Content-Length') or 0)
            raw = self.rfile.read(n)
            try:
                STATE['diag'] = json.loads(raw.decode('utf-8'))
            except Exception as e:
                STATE['diag'] = {'errors': ['bad diag payload: %s' % e]}
            DIAG_EV.set()
            self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers()
            self.wfile.write(b'ok')
            return
        self._forward('POST')

    def do_PUT(self):
        self._forward('PUT')

    def do_DELETE(self):
        self._forward('DELETE')


def post(path, payload=None):
    req = urllib.request.Request('http://127.0.0.1:%d%s' % (APP_PORT, path), method='POST',
                                 data=json.dumps(payload or {}).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def get(path):
    with urllib.request.urlopen('http://127.0.0.1:%d%s' % (APP_PORT, path), timeout=10) as r:
        return json.loads(r.read())


fails = []


def check(label, cond, extra=''):
    print(('  OK  ' if cond else ' FAIL ') + label + (('   ' + str(extra)) if extra else ''))
    if not cond:
        fails.append(label)


td = tempfile.mkdtemp(prefix='ir_e2e_')
open(os.path.join(td, 'config.json'), 'w', encoding='utf-8').write(json.dumps(
    {'port': APP_PORT, 'theme': THEME, 'hud_enabled': True, 'hud_texture': True,
     'topbar_alpha': 78, 'song_autodetect': True}, ensure_ascii=False))

env = dict(os.environ); env['INKREALM_DATA_DIR'] = td; env['PYTHONPATH'] = ROOT
env['PYTHONIOENCODING'] = 'utf-8'; env.pop('NODE_OPTIONS', None)
logf = open(os.path.join(td, 's.log'), 'w', encoding='utf-8', errors='replace')
proc = subprocess.Popen([PY, '-m', 'server.main'], cwd=ROOT, env=env, stdout=logf, stderr=subprocess.STDOUT)
srv = None
chrome = None
try:
    for _ in range(80):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/api/health' % APP_PORT, timeout=2); break
        except Exception:
            time.sleep(0.5)
    else:
        print('服务未启动'); print(open(os.path.join(td, 's.log'), encoding='utf-8', errors='replace').read()[-1500:])
        raise SystemExit(1)

    b = post('/api/books', {'title': '验收作品'})
    bid = b['id']
    v1 = post('/api/books/%d/volumes' % bid, {'title': '第一卷'})
    v2 = post('/api/books/%d/volumes' % bid, {'title': '第二卷'})
    for t, vid in (('1-1', v1['id']), ('1-2', v1['id']), ('2-1', v2['id']), ('无卷章', None)):
        post('/api/chapters', {'book_id': bid, 'volume_id': vid, 'title': t})
    before = get('/api/books/%d' % bid)
    print('  种子数据：卷 %d / 章 %d （主题 %s）' % (len(before['volumes']), len(before['chapters']), THEME))

    class QuietProxy(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            # Chrome 收结果后会立刻被 kill，残留连接会抛 ConnectionResetError，
            # 这是预期噪声，不必刷屏。
            pass

    srv = QuietProxy(('127.0.0.1', PROXY_PORT), Proxy)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    if WANT_SHOT:
        r = subprocess.run([CHROME, '--no-sandbox', '--hide-scrollbars', '--force-device-scale-factor=1',
                            '--window-size=1500,940', '--virtual-time-budget=30000',
                            '--screenshot=' + SHOT, 'http://127.0.0.1:%d/?shot=1' % PROXY_PORT],
                           capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=240)
        print('  截图趟 rc=%s ->' % r.returncode, SHOT if os.path.exists(SHOT) else 'MISSING')

    DIAG_EV.clear(); STATE['diag'] = None
    chrome = subprocess.Popen([CHROME, '--no-sandbox', '--hide-scrollbars',
                               '--window-size=1500,940', 'http://127.0.0.1:%d/' % PROXY_PORT],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not DIAG_EV.wait(360):
        print('  验收趟超时（360s）未回传结果')
        raise SystemExit(1)
    d = STATE['diag'] or {}
    chrome.terminate()
    try:
        chrome.wait(timeout=10)
    except Exception:
        chrome.kill()
    chrome = None

    print('===== 主题 %s =====' % THEME)
    for k in ('theme', 'bodyBg', 'themePaper', 'themeInk', 'panelAlphaVar', 'panelBg',
              'uiScale', 'fontFamily', 'radius', 'motionVar', 'scrimVar'):
        print('  %-16s = %r' % (k, d.get(k)))
    nums = [int(x) for x in re.findall(r'\d+', str(d.get('bodyBg', 'rgb(128,128,128)')))[:3]] or [128, 128, 128]
    if THEME == 'dark':
        check('暗色：body 背景确实变深', sum(nums) < 220, d.get('bodyBg'))
        check('暗色：--theme-paper 为深色', str(d.get('themePaper')).lower() == '#14130f', d.get('themePaper'))
    else:
        check('亮色：body 背景确实变亮', sum(nums) > 600, d.get('bodyBg'))
    check('--panel-alpha 生效（:root 没被注释吃掉）', str(d.get('panelAlphaVar')).strip() == '100%', d.get('panelAlphaVar'))
    check('面板是实底不是透明', str(d.get('panelBg')) not in ('rgba(0, 0, 0, 0)', 'MISSING'), d.get('panelBg'))
    check('--ui-scale 生效 = 1.2', str(d.get('uiScale')).strip() == '1.2', d.get('uiScale'))
    check('--motion 生效', 'cubic-bezier' in str(d.get('motionVar')), d.get('motionVar'))
    check('字体走 --font-sans', 'MiSans' in str(d.get('fontFamily')), d.get('fontFamily'))
    check('圆角非 0', str(d.get('radius')) not in ('0px', 'MISSING'), d.get('radius'))

    print('--- 第 1 项：顶栏（操作层）不透明度 ---')
    print('  label =', d.get('rangeLabel'))
    print('  %s -> %s -> %s' % (d.get('alphaBefore'), d.get('alphaAfterInput'), d.get('alphaSaved')))
    print('  顶栏底色 %s -> %s' % (d.get('topbarBgBefore'), d.get('topbarBgAfterInput')))
    check('滑块存在', bool(d.get('rangeLabel')), d.get('rangeLabel'))
    check('拖动即时生效（--topbar-alpha 立刻变 15%）', str(d.get('alphaAfterInput')).strip() == '15%', d.get('alphaAfterInput'))
    check('顶栏底色跟着透明化', d.get('topbarBgAfterInput') != d.get('topbarBgBefore'),
          '%s -> %s' % (d.get('topbarBgBefore'), d.get('topbarBgAfterInput')))
    check('松手后落库 topbar_alpha=15', d.get('alphaPersisted') == 15, d.get('alphaPersisted'))
    check('复位后重新读出 78', get('/api/settings')['config'].get('topbar_alpha') == 78,
          get('/api/settings')['config'].get('topbar_alpha'))

    print('--- 第 2 项：SMTC 歌曲 ---')
    print('  dock=%s 歌曲部件=%s 徽标=%r 信息=%r' % (d.get('dockExists'), d.get('dockSongSection'),
                                                    d.get('dockSongAutoBadge'), d.get('dockSongInfo')))
    print('  /api/song/now =', json.dumps(d.get('songApi'), ensure_ascii=False))
    check('功能面板出现', bool(d.get('dockExists')))
    check('歌曲部件渲染', bool(d.get('dockSongSection')), d.get('dockSongAutoBadge'))
    check('显示系统检测徽标', '系统检测' in str(d.get('dockSongAutoBadge')), d.get('dockSongAutoBadge'))
    check('SMTC 接口可用', bool((d.get('songApi') or {}).get('ok')), d.get('songApi'))
    if (d.get('songApi') or {}).get('ok') and (d.get('songApi') or {}).get('title'):
        print('  → 实际检测到：%s（%s）' % (d['songApi']['title'], d['songApi']['app']))

    print('--- 第 3 项：单章 / 单卷删除 + 回收站 ---')
    print('  树：卷行 %s / 章行 %s / 章删除钮 %s / 卷删除钮 %s / 作品删除钮 %s'
          % (d.get('volRows'), d.get('chRows'), d.get('chDeleteButtons'),
             d.get('volDeleteButtons'), d.get('bookDeleteButtons')))
    check('每个章节行都有删除按钮', d.get('chDeleteButtons') == d.get('chRows'),
          '%s vs %s' % (d.get('chDeleteButtons'), d.get('chRows')))
    check('每个卷行都有删除按钮', d.get('volDeleteButtons') == d.get('volRows'),
          '%s vs %s' % (d.get('volDeleteButtons'), d.get('volRows')))
    check('作品行仍有删除按钮', bool(d.get('bookDeleteButtons')))
    check('章节确认气泡能弹出', bool(d.get('confirmPanelShown')))
    check('点确认后章节从树里消失', d.get('chAfterDelete') == (d.get('chBeforeDelete') or 0) - 1,
          '%s -> %s' % (d.get('chBeforeDelete'), d.get('chAfterDelete')))
    check('回收站有分类标题且含「章节」', '章节' in (d.get('trashSections') or []), d.get('trashSections'))
    check('回收站列出了删掉的章节', bool(d.get('trashRows')), d.get('trashRows'))
    check('章节行显示所属作品', any('验收作品' in str(m) for m in (d.get('trashMetas') or [])), d.get('trashMetas'))
    _before_rows = d.get('trashRows') if d.get('trashRows') is not None else -1
    _after_rows = d.get('trashRowsAfterRestore') if d.get('trashRowsAfterRestore') is not None else 99
    check('恢复后回收站条目减少', _after_rows < _before_rows,
          '%s -> %s' % (_before_rows, _after_rows))
    check('恢复后章节回到树里', d.get('chAfterRestore') == d.get('chBeforeDelete'),
          '%s vs %s' % (d.get('chAfterRestore'), d.get('chBeforeDelete')))
    check('删整卷后卷行减少', d.get('volAfterDelete') == (d.get('volBeforeDelete') or 0) - 1,
          '%s -> %s' % (d.get('volBeforeDelete'), d.get('volAfterDelete')))
    _cvb = d.get('chBeforeVolDelete') if d.get('chBeforeVolDelete') is not None else -1
    _cva = d.get('chAfterVolDelete') if d.get('chAfterVolDelete') is not None else 99
    check('删整卷同时收起其章节', _cva < _cvb, '%s -> %s' % (_cvb, _cva))
    check('回收站有「卷」分类', '卷' in (d.get('trashSections2') or []), d.get('trashSections2'))
    check('卷条目显示「含 N 章」', any('含' in str(m) and '章' in str(m) for m in (d.get('trashMetas2') or [])),
          d.get('trashMetas2'))
    check('恢复卷后卷行回来', d.get('volAfterRestore') == d.get('volBeforeDelete'),
          '%s vs %s' % (d.get('volAfterRestore'), d.get('volBeforeDelete')))
    check('恢复卷后章节也回来', d.get('chAfterVolRestore') == d.get('chBeforeVolDelete'),
          '%s vs %s' % (d.get('chAfterVolRestore'), d.get('chBeforeVolDelete')))

    after = get('/api/books/%d' % bid)
    check('后端最终一致（卷/章数量复原）',
          len(after['volumes']) == len(before['volumes']) and len(after['chapters']) == len(before['chapters']),
          'vol %d/%d ch %d/%d' % (len(after['volumes']), len(before['volumes']),
                                  len(after['chapters']), len(before['chapters'])))
    if d.get('errors'):
        print('  JS/流程问题：')
        for e in d['errors']:
            print('    -', e)
    check('无 JS 错误', not d.get('errors'), d.get('errors'))
    if WANT_SHOT:
        print('  截图：', SHOT if os.path.exists(SHOT) else 'MISSING')
finally:
    if chrome:
        chrome.terminate()
    if srv:
        srv.shutdown()
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()

print()
print('FAILED:', fails if fails else 'none')
print('RESULT:', 'PASS' if not fails else 'FAIL')
