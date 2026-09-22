/**
 * AI 写作抽屉冒烟验收（CDP 直连，Node 22 内置 WebSocket，零依赖）
 *
 * 覆盖本次五项改动的静态可验部分：
 *  1/2 历史记录统一一份、按时间倒序，且面板位于「模型」块下方（DOM 顺序断言）
 *  3  语音输入图标已融入输入框右下角（.aw-dir-wrap 内、textarea 右侧留白）
 *  4  输出区关闭按钮：载入一条历史 → 出现「✕ 清空」→ 点击后输出区消失
 *  5  生成动画相关节点存在（.aw-fly 起飞层 / 输出区过渡类）
 *
 * 用法：node tools/aiwrite_smoke.mjs [端口]
 * 前置：本地服务已启动（127.0.0.1:8723）
 */
import { spawn } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const PORT = 9333;
const APP = process.argv[2] || 'http://127.0.0.1:8723/';
const OUT = '_shots_aw';
const HS = path.join(
  os.homedir(),
  'AppData/Local/ms-playwright/chromium_headless_shell-1243',
  'chrome-headless-shell-win64/chrome-headless-shell.exe'
);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const fails = [];
function check(name, ok, detail = '') {
  console.log(`${ok ? '  PASS  ' : '  FAIL  '}${name}${detail ? '  <- ' + detail : ''}`);
  if (!ok) fails.push(name);
}

function httpJson(port, p) {
  return new Promise((resolve, reject) => {
    const req = http.get({ host: '127.0.0.1', port, path: p, timeout: 3000 }, (res) => {
      let b = '';
      res.on('data', (c) => (b += c));
      res.on('end', () => {
        try { resolve(JSON.parse(b)); } catch (e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => req.destroy(new Error('timeout')));
  });
}

if (!fs.existsSync(HS)) {
  console.error('未找到 chrome-headless-shell：', HS);
  process.exit(2);
}
fs.mkdirSync(OUT, { recursive: true });

const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'witaw_'));
const chrome = spawn(HS, [
  '--no-sandbox',
  '--disable-gpu',
  '--enable-unsafe-swiftshader',
  '--hide-scrollbars',
  '--force-device-scale-factor=1',
  '--window-size=1400,900',
  '--disable-background-networking',
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`,
  `${APP}${APP.includes('?') ? '&' : '?'}nofx=1`,
], { stdio: 'ignore' });

async function waitForCDP() {
  // 注意：/json/version 给的是 browser 端点（不支持 Runtime.evaluate），
  // 必须取 /json/list 里的 page target，否则会报 'Runtime.evaluate' wasn't found。
  for (let i = 0; i < 60; i++) {
    try {
      const list = await httpJson(PORT, '/json/list');
      const page = (list || []).find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
      if (page) return page.webSocketDebuggerUrl;
    } catch { /* not yet */ }
    await sleep(500);
  }
  throw new Error('CDP 未就绪');
}

const wsUrl = await waitForCDP();
const ws = new WebSocket(wsUrl);
await new Promise((res, rej) => {
  ws.onopen = res;
  ws.onerror = rej;
});
let seq = 0;
const pending = new Map();
const events = [];
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    pending.get(m.id)(m);
    pending.delete(m.id);
  } else if (m.method) events.push(m);
};
function send(method, params = {}) {
  const id = ++seq;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((res) => pending.set(id, res));
}
async function evalJs(expr) {
  const r = await send('Runtime.evaluate', {
    expression: `(async () => { ${expr} })()`,
    awaitPromise: true,
    returnByValue: true,
  });
  if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 400));
  if (r.error) throw new Error(JSON.stringify(r.error).slice(0, 300));
  const v = r.result?.result?.value;
  // 表达式里没有 return 时返回 undefined 属正常（纯副作用调用），不刷屏
  if (v === undefined && /return\b/.test(String(expr))) console.log('  [evalJs 空返回]', JSON.stringify(r).slice(0, 300));
  return v;
}
/** 取字符串结果（避免对象值在个别 CDP 版本下丢失） */
async function evalStr(expr) {
  const v = await evalJs(expr);
  return typeof v === 'string' ? v : JSON.stringify(v ?? null);
}

await send('Page.enable');
await send('Runtime.enable');

async function waitUntil(fnSrc, timeoutMs = 30000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const v = await evalJs(`return !!(${fnSrc});`).catch(() => false);
    if (v) return true;
    await sleep(400);
  }
  return false;
}

// 预置两条历史（改写 / 续写，不同时间），用于验证「统一一份 + 倒序」
// 必须等真正导航到应用页（about:blank 下 localStorage 会被 SecurityError 拒绝）
await waitUntil(`location.href.startsWith('http') && document.readyState === 'complete' && !!document.querySelector('.tb')`, 60000);
await evalJs(`
  try {
    const now = Date.now();
  const h = [
    { id: 2, ts: now - 60 * 1000, op: 'continue', opLabel: '续写', instruction: '顺着雨夜继续',
      result: '续写示例内容：雨越下越大，他拐进巷口……', bookId: null, chapterId: null, chapterTitle: '第一章' },
    { id: 1, ts: now - 3600 * 1000, op: 'rewrite', opLabel: '改写', instruction: '更口语化',
      result: '改写示例内容：他把伞收了，骂了句鬼天气……', bookId: null, chapterId: null, chapterTitle: '第一章' }
  ];
  localStorage.setItem('inkrealm.aw.history.v1', JSON.stringify(h));
  } catch (e) { /* 非应用页：忽略，下一轮重试 */ }
`);
// 无数据时编辑器工具栏不会出现（AI 写作按钮在编辑器里）→ 先建一部作品 + 一章
async function apiPost(p, body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const req = http.request(
      { host: '127.0.0.1', port: 8723, path: p, method: 'POST', timeout: 8000,
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } },
      (res) => {
        let b = '';
        res.on('data', (c) => (b += c));
        res.on('end', () => {
          try { resolve(JSON.parse(b)); } catch (e) { reject(new Error(b.slice(0, 200))); }
        });
      }
    );
    req.on('error', reject);
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.write(data);
    req.end();
  });
}
const book = await apiPost('/api/books', { title: '冒烟测试作品' });
const chap = await apiPost('/api/chapters', {
  book_id: book.id,
  title: '第一章 雨夜',
  content: '雨越下越大，他拐进巷口，脚下踩到一截断裂的木板。',
});
console.log(`  已建作品 #${book.id} / 章节 #${chap.id}`);

await send('Page.reload', { ignoreCache: true });
await sleep(2500);
await waitUntil(`document.readyState === 'complete' && !!document.querySelector('.tb')`);

// 打开章节（编辑器的「AI 写作」按钮只在打开章节后出现）：先展开作品，再点章节
await waitUntil(`!!document.querySelector('.book-row')`, 30000);
await evalJs(`document.querySelector('.book-row')?.click(); return true;`);
await sleep(900);
await waitUntil(`!!document.querySelector('.ch')`, 30000);
await evalJs(`
  document.querySelector('.ch')?.click();
  return true;
`);
await sleep(1200);

console.log('打开 AI 写作抽屉…');
const diagRaw = await evalJs(`
  const tbs = [...document.querySelectorAll('.tb')].map(b => (b.textContent || '').trim()).filter(Boolean);
  return JSON.stringify({
    tbs,
    hasShell: !!document.querySelector('.shell'),
    hasEditor: !!document.querySelector('.aw-sel'),
    bodyHead: (document.body.innerText || '').slice(0, 200),
  });
`).catch((e) => 'ERR ' + String(e));
console.log('  诊断:', String(diagRaw).slice(0, 900));
const opened = await waitUntil(
  `(() => { const b = [...document.querySelectorAll('.tb')].find(x => (x.textContent||'').includes('AI 写作')); if (!b) return false; b.click(); return true; })()`
);
check('找到并点击「AI 写作」入口', opened);
if (!opened) {
  chrome.kill();
  console.log('\n失败：未能打开抽屉（见上方诊断）');
  process.exit(1);
}
await sleep(900);
const hasDrawer = await waitUntil(`!!document.querySelector('.aw')`, 10000);
check('抽屉已打开', hasDrawer);

// ---- 1/2 历史面板位置与内容 ----
const layout = await evalJs(`
  const aw = document.querySelector('.aw');
  const kids = [...aw.children].map(e => (e.className || '').toString());
  const idx = (c) => kids.findIndex(k => k.startsWith(c));
  return { kids, prov: idx('aw-prov'), hist: idx('aw-hist'), ops: idx('aw-ops'), dir: idx('aw-dir') };
`);
check('历史面板紧随「模型」块之后（DOM 顺序）',
  layout.prov >= 0 && layout.hist === layout.prov + 1,
  `模型块 idx=${layout.prov}, 历史 idx=${layout.hist}`);
check('历史面板位于操作按钮区之上', layout.hist < layout.ops, `历史 ${layout.hist} < 功能按钮 ${layout.ops}`);

await evalJs(`document.querySelector('.aw-hist-toggle')?.click()`);
await sleep(500);
const hist = await evalJs(`
  const items = [...document.querySelectorAll('.aw-hist-item')];
  return items.map(i => ({
    op: i.querySelector('.aw-hist-op')?.textContent?.trim(),
    chap: i.querySelector('.aw-hist-chap')?.textContent?.trim() || '',
    snip: i.querySelector('.aw-hist-snip')?.textContent?.trim().slice(0, 20),
  }));
`);
check('历史为统一一份列表（含多个不同功能）', hist.length === 2, JSON.stringify(hist.map((h) => h.op)));
check('每条标注来源功能', hist.every((h) => !!h.op), hist.map((h) => h.op).join('/'));
check('每条带简要内容摘要', hist.every((h) => !!h.snip), hist.map((h) => h.snip).join(' | '));
check('按时间倒序（最新在前）', hist[0]?.op === '续写' && hist[1]?.op === '改写', hist.map((h) => h.op).join('→'));

// ---- 3 语音图标融入输入框右下角 ----
const mic = await evalJs(`
  const wrap = document.querySelector('.aw-dir-wrap');
  const ta = document.querySelector('.aw-ta');
  const m = wrap?.querySelector('.mic');
  if (!wrap || !ta || !m) return null;
  const wr = wrap.getBoundingClientRect(), mr = m.getBoundingClientRect();
  const cs = getComputedStyle(ta);
  return {
    inWrap: wrap.contains(m),
    padRight: cs.paddingRight,
    rightGap: Math.round(wr.right - mr.right),
    bottomGap: Math.round(wr.bottom - mr.bottom),
    borderless: getComputedStyle(m).borderStyle === 'none' || getComputedStyle(m).borderWidth === '0px',
  };
`);
check('语音图标在输入框容器内（融为一体）', !!mic?.inWrap, JSON.stringify(mic));
check('输入框右侧留出图标位置（不压字）', mic && parseFloat(mic.padRight) >= 30, `padding-right=${mic?.padRight}`);
check('图标贴右下角', mic && mic.rightGap <= 14 && mic.bottomGap <= 14, `right=${mic?.rightGap} bottom=${mic?.bottomGap}`);
check('图标无边框（融入而非悬浮按钮）', !!mic?.borderless);

// ---- 5 生成动画流程：点「生成」→ 方向文字起飞 → 思考等待面板 → 输出区展开 ----
await evalJs(`document.querySelector('.aw-btns .run')?.click()`);
await sleep(160);
const flyOn = await evalJs(`return !!document.querySelector('.aw-fly');`);
check('点击生成后方向文字起飞层出现（飞向等待面板）', flyOn === true, `fly=${flyOn}`);
const taDim = await evalJs(`
  const ta = document.querySelector('.aw-ta');
  return ta ? getComputedStyle(ta).color : '';
`);
// 颜色带 0.3s 过渡，采样时可能停在中途（如 alpha=0.06）→ 只要接近全透明即算「已淡出」
const alpha = (() => {
  const c = String(taDim);
  if (c === 'transparent') return 0;
  const p = c.replace(/rgba?\(|\)/g, '').split(',').map((x) => parseFloat(x));
  return p.length === 4 ? p[3] : 1;
})();
check('思考期间方向文字淡出（不再与等待态重复）', alpha <= 0.25, `color=${taDim} alpha=${alpha}`);
await sleep(900);
const waiting = await evalJs(`
  const plate = document.querySelector('.tw-plate');
  return { has: !!plate, text: (plate?.innerText || '').slice(0, 60) };
`);
check('「思考等待中」面板出现', waiting.has, waiting.text.replace(/\n/g, ' / '));
const shotW = await send('Page.captureScreenshot', {});
fs.writeFileSync(path.join(OUT, '03_aiwrite_思考等待中.png'), Buffer.from(shotW.result.data, 'base64'));
// 立刻停掉，避免长时间占用本地模型
await evalJs(`document.querySelector('.tw-stop')?.click(); document.querySelector('.aw-btns .stop')?.click();`);
await sleep(600);
await evalJs(`window.__awShotDone = true`);
const shot1 = await send('Page.captureScreenshot', {});
fs.writeFileSync(path.join(OUT, '01_aiwrite_抽屉.png'), Buffer.from(shot1.result.data, 'base64'));

// ---- 4 输出区关闭按钮 ----
await evalJs(`document.querySelector('.aw-hist-item')?.click()`);
await sleep(700);
const withResult = await evalJs(`
  return { hasResult: !!document.querySelector('.aw-result'), closeText: document.querySelector('.aw-result-close')?.textContent?.trim() };
`);
check('载入历史后输出区出现', withResult.hasResult);
check('输出区带关闭按钮', !!withResult.closeText, withResult.closeText);
const shot2 = await send('Page.captureScreenshot', {});
fs.writeFileSync(path.join(OUT, '02_aiwrite_输出区.png'), Buffer.from(shot2.result.data, 'base64'));

await evalJs(`document.querySelector('.aw-result-close')?.click()`);
await sleep(800);
const after = await evalJs(`
  return { hasResult: !!document.querySelector('.aw-result'), text: document.querySelector('.aw-text')?.textContent?.trim() || '' };
`);
check('点击关闭后输出区清空并恢复空态', !after.hasResult, `残留文本长度 ${after.text.length}`);

const exc = events.filter((e) => e.method === 'Runtime.exceptionThrown');
check('运行期无 JS 异常', exc.length === 0, `${exc.length} 条`);

chrome.kill();
console.log();
console.log(fails.length ? '失败：' + fails.join('、') : '全部通过 ✅');
console.log('截图输出:', path.resolve(OUT));
process.exit(fails.length ? 1 : 0);
