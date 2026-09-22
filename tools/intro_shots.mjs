/**
 * 启动动画真机验收：CDP 直连（零依赖，用 Node 22 内置 WebSocket）
 *
 * 为什么不用 --virtual-time-budget：
 *   虚拟时间下 rAF 几乎不推进（实测 data-phase 永远停在 morph），
 *   根本采不到放大与背景阶段。这里改成**真实时间**跑，
 *   每帧读页面暴露的 window.__witworkIntro（?introdebug=1 开启），
 *   从而量化验证需求 3 的核心：放大过程与背景的
 *   旋转角度 / 角速度 / 方向是否严格连续无跳变。
 *
 * 用法：
 *   node tools/intro_shots.mjs [输出目录] [页面URL]
 * 前置：本地服务已启动（127.0.0.1:8723）
 */
import { spawn } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const OUT = process.argv[2] || '_shots';
const URL_BASE = process.argv[3] || 'http://127.0.0.1:8723/';
const PORT = 9222 + (Number(process.env.INTRO_CDP_PORT_OFFSET) || 0);

const HS = path.join(
  os.homedir(),
  'AppData/Local/ms-playwright/chromium_headless_shell-1243',
  'chrome-headless-shell-win64/chrome-headless-shell.exe'
);

// 与 App.vue 时间轴保持一致（用于断言阈值）
const T_VEL_HOLD = 0.8; // 高速段结束，开始回落
const T_GROW_START = 1.06; // 回落结束 == 放大开始（此刻角速度恰好等于背景速度）
const T_GROW_END = 2.6;
const T_DONE = 3.36;
const BG_VEL_Y = 0.096;
const BG_VEL_X = 0.036;
const SPIN_EXTRA_Y = 2.55;
const S0 = 0.1;
const INTRO_WIRE_O = 0.92; // 待机/坍缩阶段棱球不透明度（与 App.vue 一致）
// 理论上限角加速度：d/dt[SPIN_EXTRA_Y × (1 - smoothstep)] 的峰值
// smoothstep 最大斜率 = 1.5 / 区间长度(0.26s) → 2.55 × 5.769 ≈ 14.71 rad/s²
const MAX_ALPHA = (SPIN_EXTRA_Y * 1.5) / (T_GROW_START - T_VEL_HOLD);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const fails = [];
function check(name, ok, detail = '') {
  console.log(`${ok ? '  PASS  ' : '  FAIL  '}${name}${detail ? '  <- ' + detail : ''}`);
  if (!ok) fails.push(name);
}

function httpJson(pathname) {
  return new Promise((resolve, reject) => {
    const req = http.get({ host: '127.0.0.1', port: PORT, path: pathname, timeout: 3000 }, (res) => {
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

const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'witintro_'));
const url = `${URL_BASE}${URL_BASE.includes('?') ? '&' : '?'}intro=auto&introdebug=1`;

const chrome = spawn(HS, [
  // 受限环境下沙箱初始化会被拦（进程以 STATUS_BREAKPOINT 直接退出）→ 必须关掉
  '--no-sandbox',
  '--disable-gpu',
  '--enable-unsafe-swiftshader',
  '--use-angle=swiftshader',
  '--hide-scrollbars',
  '--force-device-scale-factor=1',
  '--window-size=1600,920',
  '--disable-background-networking',
  '--no-first-run',
  '--no-default-browser-check',
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`,
  'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] });

let chromeErr = '';
chrome.stderr.on('data', (d) => (chromeErr += d.toString()));

const cleanup = () => {
  try { chrome.kill('SIGKILL'); } catch {}
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch {}
};
process.on('exit', cleanup);

// ---------- 1) 等调试端口 ----------
let target = null;
for (let i = 0; i < 80; i++) {
  try {
    const list = await httpJson('/json/list');
    target = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
    if (target) break;
  } catch { /* 还没起来 */ }
  await sleep(250);
}
if (!target) {
  console.error('CDP 调试端口未就绪。chrome stderr:\n', chromeErr.slice(-800));
  process.exit(2);
}
console.log('CDP 就绪，target:', target.id);

// ---------- 2) WebSocket 会话 ----------
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((res, rej) => {
  ws.addEventListener('open', res, { once: true });
  ws.addEventListener('error', () => rej(new Error('ws error')), { once: true });
});

let msgId = 0;
const pending = new Map();
const events = [];
ws.addEventListener('message', (ev) => {
  let m;
  try { m = JSON.parse(ev.data); } catch { return; }
  if (m.id && pending.has(m.id)) {
    const { resolve, reject } = pending.get(m.id);
    pending.delete(m.id);
    m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result);
  } else if (m.method) {
    events.push(m);
  }
});
function send(method, params = {}) {
  const id = ++msgId;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
    setTimeout(() => {
      if (pending.has(id)) { pending.delete(id); reject(new Error(method + ' 超时')); }
    }, 20000);
  });
}

await send('Page.enable');
await send('Runtime.enable');

// ---------- 3) 导航并等待 load ----------
await send('Page.navigate', { url });
for (let i = 0; i < 100; i++) {
  if (events.some((e) => e.method === 'Page.loadEventFired')) break;
  await sleep(50);
}
await sleep(120); // 让首屏渲染稳一下

async function evalJs(expr) {
  const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: false });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text || 'eval exception');
  return r.result?.value;
}

async function shoot(name) {
  try {
    const r = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
    const p = path.join(OUT, name);
    fs.writeFileSync(p, Buffer.from(r.data, 'base64'));
    return fs.statSync(p).size;
  } catch (e) {
    console.log('    截图失败:', name, e.message);
    return 0;
  }
}

// ---------- 4) 真实时间逐帧采样 ----------
const shots = [
  { at: 0.12, name: '01_morph_大字' },
  { at: 0.55, name: '02_morph_旋转' },
  { at: 1.14, name: '03_grow_起步' },
  { at: 1.85, name: '04_grow_中段' },
  { at: 2.72, name: '05_ui_浮现' },
  { at: 3.6, name: '06_bg_就位' },
];
let shotIdx = 0;
const samples = [];
const t0 = Date.now();

while (Date.now() - t0 < 5200) {
  const raw = await evalJs('JSON.stringify(window.__witworkIntro||null)');
  const s = raw ? JSON.parse(raw) : null;
  if (s) {
    s.wall = (Date.now() - t0) / 1000;
    samples.push(s);
    while (shotIdx < shots.length && s.t >= shots[shotIdx].at) {
      const sz = await shoot(`${shots[shotIdx].name}.png`);
      console.log(`  采样 ${s.t.toFixed(3)}s phase=${s.phase} scale=${s.scale.toFixed(4)} 截图 ${shots[shotIdx].name} (${(sz / 1024).toFixed(1)}KB)`);
      shotIdx++;
    }
  }
  await sleep(30);
}

// 补拍还未触发的（例如动画被跳过）
while (shotIdx < shots.length) {
  await shoot(`${shots[shotIdx].name}.png`);
  shotIdx++;
}

console.log('\n================ 断言（真实浏览器实测）================');
check('采到有效帧（>60 帧）', samples.length > 60, `${samples.length} 帧`);

if (samples.length > 10) {
  const first = samples[0], last = samples[samples.length - 1];
  console.log(`  时间跨度 t: ${first.t.toFixed(3)}s → ${last.t.toFixed(3)}s`);
  console.log(`  阶段序列: ${[...new Set(samples.map((s) => s.phase))].join(' → ')}`);

  // A1 方向永不反转
  const negY = samples.filter((s) => s.velY <= 0).length;
  const negX = samples.filter((s) => s.velX <= 0).length;
  check('自转方向全程为正、从未反转', negY === 0 && negX === 0, `velY<=0 帧 ${negY}, velX<=0 帧 ${negX}`);

  // A2 角度单调递增（累加器不重置、不取模）
  let back = 0;
  for (let i = 1; i < samples.length; i++) if (samples[i].spinY < samples[i - 1].spinY) back++;
  check('spinY 单调递增（角度累加器从不重置/取模）', back === 0, `回退 ${back} 帧`);

  // A3 放大相位及之后：角速度恒等于背景角速度（需求 3 的核心）
  const growSamples = samples.filter((s) => s.t >= T_GROW_START + 0.03);
  const dy = Math.max(...growSamples.map((s) => Math.abs(s.velY - BG_VEL_Y)));
  const dx = Math.max(...growSamples.map((s) => Math.abs(s.velX - BG_VEL_X)));
  check(
    `放大及背景阶段角速度严格等于背景速度（Δ<=1e-9）`,
    growSamples.length > 30 && dy < 1e-9 && dx < 1e-9,
    `样本 ${growSamples.length}, maxΔvelY=${dy.toExponential(2)}, maxΔvelX=${dx.toExponential(2)}`
  );

  // A4 角加速度全程有界 → 说明「速度变化始终平滑」，任何阶段都没有阶跃突变。
  //    （这是「连贯无跳变」的严格量化判据：若存在速度阶跃，Δt 内的 Δv/Δt 会远超理论上限。）
  const live = samples.filter((s) => s.t >= 0);
  let maxAlpha = 0, maxAlphaAt = 0;
  for (let i = 1; i < live.length; i++) {
    const dt = live[i].t - live[i - 1].t;
    if (dt <= 1e-6) continue;
    const a = Math.abs(live[i].velY - live[i - 1].velY) / dt;
    if (a > maxAlpha) { maxAlpha = a; maxAlphaAt = live[i].t; }
  }
  check(
    `角加速度全程有界（无阶跃突变，理论上限 ${MAX_ALPHA.toFixed(2)} rad/s²）`,
    maxAlpha <= MAX_ALPHA * 1.06,
    `实测峰值 ${maxAlpha.toFixed(2)} rad/s² @ t=${maxAlphaAt.toFixed(3)}s`
  );

  // A4b 点击后的减速段速度单调回落，不应有反弹
  const dec = live.filter((s) => s.t >= T_VEL_HOLD && s.t < T_GROW_START);
  let bump = 0;
  for (let i = 1; i < dec.length; i++) if (dec[i].velY > dec[i - 1].velY + 1e-9) bump++;
  check('点击后减速段角速度单调回落（无反弹）', bump === 0, `反弹 ${bump} 帧 / 共 ${dec.length} 帧`);

  // A4c 跨界左右极限一致：放大段第一帧角速度必须精确等于背景角速度，
  //     且与「减速段最后一帧按 dt 外推」的结果吻合（证明衔接处无断点）
  const gFirst = live.find((s) => s.t >= T_GROW_START);
  const decLast = dec.length ? dec[dec.length - 1] : null;
  const drift = gFirst && decLast ? Math.abs((BG_VEL_Y - decLast.velY) / (gFirst.t - decLast.t)) : Infinity;
  check(
    '跨界第一帧角速度 == 背景速度 且角加速度不超限',
    !!gFirst && Math.abs(gFirst.velY - BG_VEL_Y) < 1e-9 && drift <= MAX_ALPHA * 1.06,
    gFirst ? `velY=${gFirst.velY} (背景 ${BG_VEL_Y})，交界处 |Δv/Δt|=${drift.toFixed(2)}` : '无样本'
  );

  // A5 缩放：待机与 morph 全程保持在 S0（→ 点击起播零归位跳变）、
  //     放大单调递增、终点精确为 1
  const preGrow = samples.filter((s) => s.t >= 0 && s.t < T_GROW_START);
  const badPre = preGrow.filter((s) => Math.abs(s.scale - S0) > 1e-9).length;
  const growEnd = samples.filter((s) => s.t >= T_GROW_END + 0.05);
  const endScale = growEnd.length ? growEnd[growEnd.length - 1].scale : 0;
  check(
    '放大前全程保持起始缩放 S0（点击起播零归位跳变）',
    preGrow.length > 5 && badPre === 0,
    `样本 ${preGrow.length} 帧, 偏离 S0 的 ${badPre} 帧`
  );
  check('放大到位后缩放 == 1（背景就位）', Math.abs(endScale - 1) < 1e-6, String(endScale));
  let shrink = 0;
  for (let i = 1; i < samples.length; i++) if (samples[i].scale < samples[i - 1].scale - 1e-9) shrink++;
  check('缩放全程单调递增（放大过程无回缩）', shrink === 0, `回缩 ${shrink} 帧`);

  // A5b 需求实现：球体放大时去掉内部小球，只保留线框棱球成为背景
  const growBg = samples.filter((s) => s.t >= T_GROW_START + 0.5);
  const innerLeft = growBg.filter((s) => (s.innerO ?? 0) > 1e-4).length;
  check(
    '放大就位后内部小球已移除（innerO≈0，只留线框棱球）',
    growBg.length > 20 && innerLeft === 0,
    `样本 ${growBg.length} 帧, 残留 ${innerLeft} 帧`
  );
  const morphS = samples.filter((s) => s.t >= 0.35 && s.t < T_GROW_START);
  const innerAppeared = morphS.some((s) => (s.innerO ?? 0) > 0.01);
  check(
    '坍缩(morph)阶段内部小球曾作为内核出现，随后在放大时淡出',
    morphS.length > 5 ? innerAppeared : true,
    `坍缩段 ${morphS.length} 帧, 是否出现=${innerAppeared}`
  );

  // A5c 需求：待机起棱球就在场且不透明度恒定——是**同一只球**直接旋转变大，
  //     不存在「淡入 / 重新放置一只新球」。
  const preGrowO = samples.filter((s) => s.t >= 0 && s.t < T_GROW_START);
  const notSteady = preGrowO.filter((s) => Math.abs(s.wireO - INTRO_WIRE_O) > 0.02).length;
  check(
    `起播前棱球已在场且不透明度恒定=${INTRO_WIRE_O}（同一只球直接放大，无淡入/重放）`,
    preGrowO.length > 5 && notSteady === 0,
    `起播前 ${preGrowO.length} 帧, 偏离 ${INTRO_WIRE_O} 的 ${notSteady} 帧`
  );

  // A6 背景就位后仍在持续转动（未被冻结）
  const afterDone = samples.filter((s) => s.t >= T_DONE + 0.1);
  const span = afterDone.length > 1 ? afterDone[afterDone.length - 1].spinY - afterDone[0].spinY : 0;
  check('覆盖层移除后背景仍在持续转动', afterDone.length > 20 && span > 0.01, `ΔspinY=${span.toFixed(4)} rad / ${afterDone.length} 帧`);

  // A7 阶段齐全
  const ph = new Set(samples.map((s) => s.phase));
  check('阶段序列完整（morph→grow→ui→done）', ['morph', 'grow', 'ui', 'done'].every((x) => ph.has(x)), [...ph].join(','));

  const rows = samples.filter((_, i) => i % Math.max(1, Math.floor(samples.length / 14)) === 0);
  console.log('\n  时序快照（t / phase / scale / spinY / velY）:');
  for (const s of rows) {
    console.log(`    ${s.t.toFixed(3)}s  ${s.phase.padEnd(6)} scale=${s.scale.toFixed(5)}  spinY=${s.spinY.toFixed(4)}  velY=${s.velY.toFixed(5)}`);
  }
}

// 页面端错误（Runtime.exceptionThrown + console.error）
const exc = events.filter((e) => e.method === 'Runtime.exceptionThrown');
const cerr = events.filter(
  (e) => e.method === 'Runtime.consoleAPICalled' && e.params?.type === 'error'
);
check(
  '运行期无 JS 异常 / console.error',
  exc.length === 0 && cerr.length === 0,
  `异常 ${exc.length} 条, console.error ${cerr.length} 条` +
    (exc.length ? `：${exc[0].params?.exceptionDetails?.text || ''}` : '')
);

// 3D 是否真的在渲染（缩放能到 1 且 wireO > 0，说明 WebGL 可用而非降级）
const gl = samples.some((s) => s.wireO > 0.01);
check('WebGL 正常（线框棱球参与渲染，未降级为纯色背景）', gl, `最大 wireO=${Math.max(...samples.map((s) => s.wireO)).toFixed(3)}`);

// ---------- 5) 主题持久化实测（需求 5）----------
// 走真实路径：把「上一次保存的主题」写进服务器设置（= 用户关闭前保存的值），
// 再看启动画面底色是否随之变化；并检查「首帧 → 稳定后」是否发生翻转。
// 测完把服务器设置与 localStorage 都还原并复核，绝不留副作用。
const API = new URL(URL_BASE);

function apiJson(method, pathname, body) {
  return new Promise((resolve, reject) => {
    const data = body === undefined ? null : Buffer.from(JSON.stringify(body));
    const req = http.request(
      {
        host: API.hostname,
        port: API.port || 80,
        path: pathname,
        method,
        headers: data
          ? { 'Content-Type': 'application/json', 'Content-Length': data.length }
          : {},
        timeout: 8000,
      },
      (res) => {
        let b = '';
        res.on('data', (c) => (b += c));
        res.on('end', () => {
          try { resolve(b ? JSON.parse(b) : null); }
          catch { reject(new Error('bad json: ' + b.slice(0, 120))); }
        });
      }
    );
    req.on('error', reject);
    req.on('timeout', () => req.destroy(new Error('api timeout')));
    if (data) req.write(data);
    req.end();
  });
}

function luminance(rgb) {
  const m = /rgba?\(([^)]+)\)/.exec(rgb || '');
  if (!m) return null;
  const [r, g, b] = m[1].split(',').map((x) => Number(x.trim()));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

async function waitFor(expr, ms = 8000, step = 120) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try { if (await evalJs(expr)) return true; } catch { /* 导航中 eval 可能短暂失败 */ }
    await sleep(step);
  }
  return false;
}

const READ_THEME = `(() => {
  const paper = document.querySelector('.intro .paper');
  const shell = document.querySelector('.shell');
  const intro = document.querySelector('.intro');
  return JSON.stringify({
    ready: document.readyState === 'complete',
    html: document.documentElement.getAttribute('data-theme'),
    paper: paper ? getComputedStyle(paper).backgroundColor : null,
    phase: intro ? intro.getAttribute('data-phase') : null,
    shellTheme: shell ? shell.getAttribute('data-theme') : null,
    introPresent: !!intro,
  });
})()`;

/** 设定主题（服务器 + 浏览器缓存），导航到待机启动画面，返回「首帧」与「稳定后」两次读数。 */
async function themeProbe(theme, shotName) {
  await apiJson('PUT', '/api/settings', { theme });
  await evalJs(`localStorage.setItem('inkrealm.theme', ${JSON.stringify(theme)})`);
  await send('Page.navigate', {
    url: `${URL_BASE}${URL_BASE.includes('?') ? '&' : '?'}probe=theme`,
  });
  await waitFor(`document.readyState === 'complete' && !!document.querySelector('.intro .paper')`);
  await sleep(120); // 首帧读数：此时 bootstrap 多半还没回来
  const early = JSON.parse(await evalJs(READ_THEME));
  await sleep(1300); // 稳定后读数：bootstrap 已应用保存的设置
  const late = JSON.parse(await evalJs(READ_THEME));
  await shoot(shotName);
  return { early, late };
}

const origServerTheme = (await apiJson('GET', '/api/settings'))?.config?.theme ?? 'dark';
const origCached = await evalJs(`localStorage.getItem('inkrealm.theme')`);
console.log(`\n  原始主题：服务器=${origServerTheme}, 浏览器缓存=${origCached}`);

const lightT = await themeProbe('light', '07_theme_light_intro.png');
const darkT = await themeProbe('dark', '08_theme_dark_intro.png');
const lL = luminance(lightT.late.paper);
const dL = luminance(darkT.late.paper);

check(
  '保存为亮色 → 启动画面底色为亮色（首帧与稳定后一致，无中途翻转）',
  lightT.early.html === 'light' && lightT.late.html === 'light' && lL !== null && lL > 180,
  `首帧 data-theme=${lightT.early.html} / 稳定后=${lightT.late.html}, paper=${lightT.late.paper}, 亮度=${lL === null ? '—' : lL.toFixed(0)}`
);
check(
  '保存为暗色 → 启动画面底色为暗色（首帧与稳定后一致，无中途翻转）',
  darkT.early.html === 'dark' && darkT.late.html === 'dark' && dL !== null && dL < 80,
  `首帧 data-theme=${darkT.early.html} / 稳定后=${darkT.late.html}, paper=${darkT.late.paper}, 亮度=${dL === null ? '—' : dL.toFixed(0)}`
);
check(
  '两套主题底色确实不同（证明确实在读取保存值，而非写死一种）',
  lL !== null && dL !== null && Math.abs(lL - dL) > 100,
  `Δ亮度=${lL === null || dL === null ? '—' : Math.abs(lL - dL).toFixed(0)}`
);

// ---------- 6) 还原设置并验证「启动与启动后主题一致」----------
const restored = await themeProbe(origServerTheme, '09_theme_restored_intro.png');
await apiJson('PUT', '/api/settings', { theme: origServerTheme });
if (origCached === null) await evalJs(`localStorage.removeItem('inkrealm.theme')`);
else await evalJs(`localStorage.setItem('inkrealm.theme', ${JSON.stringify(origCached)})`);
const back = (await apiJson('GET', '/api/settings'))?.config?.theme;
check(
  '测试后设置已还原（服务器主题回到原值）',
  back === origServerTheme,
  `还原后 服务器=${back}（原 ${origServerTheme}）`
);

await send('Page.navigate', {
  url: `${URL_BASE}${URL_BASE.includes('?') ? '&' : '?'}intro=auto&introdebug=1`,
});
const uiReady = await waitFor(
  `!!document.querySelector('.shell.shell-on') && !document.querySelector('.intro')`,
  12000
);
await sleep(400); // 让主题应用与首屏加载稳定
const after = JSON.parse(
  await evalJs(`(() => {
    const shell = document.querySelector('.shell');
    return JSON.stringify({
      html: document.documentElement.getAttribute('data-theme'),
      shellTheme: shell ? shell.getAttribute('data-theme') : null,
      introGone: !document.querySelector('.intro'),
      uiOn: !!document.querySelector('.shell.shell-on'),
    });
  })()`)
);
await shoot('10_theme_after_intro.png');
check(
  '启动动画结束后覆盖层已卸载、操作层已浮现',
  uiReady && after.introGone === true && after.uiOn === true,
  `等待成功=${uiReady}, intro 已移除=${after.introGone}, shell-on=${after.uiOn}`
);
check(
  '启动时与启动后主题一致（动画背景色即软件主题色）',
  restored.late.html === origServerTheme && after.html === origServerTheme && after.shellTheme === origServerTheme,
  `启动时=${restored.late.html} → 启动后 html=${after.html}, 操作层=${after.shellTheme}（保存值=${origServerTheme}）`
);

// ---------- 7) 降级路径回归 ----------
// 7a) 系统「减少动态效果」→ 不播启动动画，但仍保留 3D 背景
await send('Emulation.setEmulatedMedia', {
  features: [{ name: 'prefers-reduced-motion', value: 'reduce' }],
});
await send('Page.navigate', { url: `${URL_BASE}${URL_BASE.includes('?') ? '&' : '?'}rm=1` });
const rmOk = await waitFor(
  `!!document.querySelector('.shell.shell-on') && !document.querySelector('.intro')`,
  8000
);
const rmCanvas = await evalJs(`!!document.querySelector('canvas')`);
check(
  'reduced-motion → 跳过启动动画，直接进软件（仍保留 3D 背景）',
  rmOk && rmCanvas === true,
  `直接进入=${rmOk}, canvas=${rmCanvas}`
);
await send('Emulation.setEmulatedMedia', { features: [] });

// 7b) ?nofx=1 → 连 3D 都不初始化（纯色降级；自动化截图与低配设备走这条路）
await send('Page.navigate', { url: `${URL_BASE}${URL_BASE.includes('?') ? '&' : '?'}nofx=1` });
const nofxOk = await waitFor(
  `!!document.querySelector('.shell.shell-on') && !document.querySelector('.intro')`,
  8000
);
const nofxCanvas = await evalJs(`!!document.querySelector('canvas')`);
check(
  '?nofx=1 → 跳过启动动画且不初始化 3D（纯色降级）',
  nofxOk && nofxCanvas === false,
  `直接进入=${nofxOk}, canvas=${nofxCanvas}`
);

console.log('\n' + '='.repeat(52));
console.log(fails.length ? `失败 ${fails.length} 项：` + fails.join(', ') : '全部通过 ✅');
console.log('截图输出:', path.resolve(OUT));
ws.close();
chrome.kill('SIGKILL');
process.exit(fails.length ? 1 : 0);
