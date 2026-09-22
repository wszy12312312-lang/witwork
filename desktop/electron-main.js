'use strict';

const { app, BrowserWindow, Menu, dialog, shell, session } = require('electron');
const { spawn } = require('child_process');
const net = require('net');
const path = require('path');
const fs = require('fs');

const PORT = 8723;
const HOST = '127.0.0.1';
const isDev = !app.isPackaged;

// 视觉自检：设 INKREALM_SHOT=<png 路径> 时，窗口就绪后延时截图存盘（便于无人值守检查渲染）
const SHOT_PATH = process.env.INKREALM_SHOT || '';
const SHOT_DELAY = Number(process.env.INKREALM_SHOT_DELAY || 7000);

// 本地离线应用：直接关掉 HTTP 缓存，杜绝「旧 index.html 指向已删除哈希资源 → 白屏」
app.commandLine.appendSwitch('disable-http-cache');

// 项目根：打包后在 resources/inkrealm；开发时就是 desktop 的上一级（inkrealm）
function projectRoot() {
  if (app.isPackaged) return path.join(process.resourcesPath, 'inkrealm');
  return path.resolve(__dirname, '..');
}

// 读取可选的应用配置（打包时生成；用于把数据目录指到「共享书库」）
function appConfig() {
  const cands = [
    path.join(__dirname, 'app-config.json'),
    path.join(process.resourcesPath || '', 'app-config.json'),
  ];
  for (const p of cands) {
    try {
      if (fs.existsSync(p)) return JSON.parse(fs.readFileSync(p, 'utf8'));
    } catch (_) {
      /* ignore */
    }
  }
  return {};
}

// 可写数据目录。优先级：环境变量 > app-config.json 指定的共享书库 > 打包版 userData > 开发版项目 data。
// 「共享书库」的意义：桌面版与网页版共用同一份作品/备份，不会分裂成两套。
function resolveDataDir(root) {
  if (process.env.INKREALM_DATA_DIR) return process.env.INKREALM_DATA_DIR;
  const cfg = appConfig();
  if (cfg.dataDir && fs.existsSync(cfg.dataDir)) return cfg.dataDir;
  if (app.isPackaged) return path.join(app.getPath('userData'), 'inkrealm');
  return path.join(root, 'data');
}

let pyProc = null;
let backendLogPath = null;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.mjs': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.glb': 'model/gltf-binary',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ogg': 'audio/ogg',
  '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav',
  '.txt': 'text/plain; charset=utf-8',
  '.webmanifest': 'application/manifest+json',
};

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  try {
    if (backendLogPath) fs.appendFileSync(backendLogPath, line);
  } catch (_) {
    /* ignore */
  }
  console.log(line.trim());
}

// 检测端口是否已被占用（例如用户已独立运行的 live 服务）
function portInUse(retries = 1) {
  return new Promise((resolve) => {
    const sock = net.connect(PORT, HOST);
    sock.setTimeout(800);
    sock.once('connect', () => {
      sock.destroy();
      resolve(true);
    });
    sock.once('error', () => {
      sock.destroy();
      resolve(false);
    });
    sock.once('timeout', () => {
      sock.destroy();
      resolve(false);
    });
  });
}

// 等待后端端口就绪
function waitForPort(timeoutMs) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      const sock = net.connect(PORT, HOST);
      sock.setTimeout(700);
      sock.once('connect', () => {
        sock.destroy();
        resolve(true);
      });
      sock.once('error', () => {
        sock.destroy();
        if (Date.now() - start > timeoutMs) return reject(new Error('后端启动超时'));
        setTimeout(tick, 500);
      });
      sock.once('timeout', () => {
        sock.destroy();
        if (Date.now() - start > timeoutMs) return reject(new Error('后端启动超时'));
        setTimeout(tick, 500);
      });
    };
    tick();
  });
}

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

function startBackend() {
  const root = projectRoot();
  const py = path.join(root, 'venv', 'Scripts', 'python.exe');
  if (!fs.existsSync(py)) {
    dialog.showErrorBox(
      '缺少 Python 运行环境',
      `未找到后端解释器：\n${py}\n\n请确认已通过 start.bat 初始化 venv，或重新安装桌面版。`
    );
    app.quit();
    return;
  }
  // 首次启动：把只读资源里的 data（打包时随附的 books/备份/配置）播种到可写目录，
  // 做到与网页版「一模一样」。
  const dataDir = resolveDataDir(root);
  const resData = path.join(root, 'data');
  if (!fs.existsSync(dataDir) && fs.existsSync(resData)) {
    try {
      copyDir(resData, dataDir);
      log('首次启动：已从资源目录继承数据 ' + resData);
    } catch (e) {
      log('继承数据失败：' + String(e));
    }
  }
  try {
    fs.mkdirSync(dataDir, { recursive: true });
  } catch (_) {
    /* ignore */
  }
  backendLogPath = path.join(dataDir, 'desktop_backend.log');
  log('启动后端：' + py + '  cwd=' + root + '  data=' + dataDir);
  pyProc = spawn(
    py,
    ['-m', 'server.main'],
    {
      cwd: root,
      env: { ...process.env, PYTHONPATH: root, INKREALM_DATA_DIR: dataDir },
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    }
  );
  pyProc.stdout.on('data', (d) => log('[py] ' + d.toString().trimEnd()));
  pyProc.stderr.on('data', (d) => log('[py!] ' + d.toString().trimEnd()));
  pyProc.on('exit', (code) => log('后端进程退出 code=' + code));
}

function stopBackend() {
  if (pyProc) {
    try {
      pyProc.kill('SIGTERM');
    } catch (_) {
      /* ignore */
    }
    pyProc = null;
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    show: false,
    backgroundColor: '#080a08',
    title: '万维文 WitWork',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  Menu.setApplicationMenu(null); // 无菜单栏，更像原生软件

  // 加载失败兜底：加时间戳强制绕过缓存重试（最多 2 次），避免任何残留缓存造成白屏
  let retries = 0;
  win.webContents.on('did-fail-load', (_e, code, desc, url) => {
    log(`页面加载失败 code=${code} ${desc} ${url}`);
    if (retries < 2) {
      retries++;
      setTimeout(() => win.loadURL(`http://${HOST}:${PORT}/?r=${Date.now()}`), 400);
    }
  });

  win.loadURL(`http://${HOST}:${PORT}/`);
  win.once('ready-to-show', () => {
    win.show();
    maybeShot(win);
  });
  win.on('closed', () => {
    stopBackend();
  });
  return win;
}

// 视觉自检：延时截图存盘（用于无人值守检查真实渲染结果）
async function maybeShot(win) {
  if (!SHOT_PATH) return;
  await new Promise((r) => setTimeout(r, SHOT_DELAY));
  try {
    // 同时抓一份「计算后的颜色」——比肉眼/像素更可靠，能定位配色令牌是否真的生效
    const diag = await win.webContents.executeJavaScript(`(() => {
      const cs = (sel) => { const el = document.querySelector(sel); if (!el) return null;
        const c = getComputedStyle(el);
        return { color: c.color, bg: c.backgroundColor, opacity: c.opacity, display: c.display }; };
      const v = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
      return JSON.stringify({
        dataTheme: document.documentElement.getAttribute('data-theme'),
        html: { bg: getComputedStyle(document.documentElement).backgroundColor,
                color: getComputedStyle(document.documentElement).color },
        body: { bg: getComputedStyle(document.body).backgroundColor,
                color: getComputedStyle(document.body).color },
        vars: { paper: v('--theme-paper'), ink: v('--theme-ink'), inkSoft: v('--theme-ink-soft'),
                inkMute: v('--theme-ink-mute'), muted: v('--theme-muted'), accent: v('--theme-accent'),
                panel: v('--theme-panel'), field: v('--theme-field'), line: v('--theme-line'),
                topbarAlpha: v('--topbar-alpha'), uiScale: v('--ui-scale') },
        el: { topbar: cs('.topbar'), brand: cs('.brand'), tb: cs('.tb'), status: cs('.status'),
              tree: cs('.tree'), editor: cs('.editor'), shell: cs('.shell'),
              dock: cs('.dock'), dockT: cs('.dock-t'), wl: cs('.w-l'), clock: cs('.clock'),
              rcFace: cs('.rc-face') },
        dockSpan: (document.querySelector('.dock')||{}).textContent ? 'yes' : 'no',
      });
    })()`);
    fs.writeFileSync(SHOT_PATH.replace(/\.png$/i, '') + '.json', diag);
    log('DIAG ' + diag);
  } catch (e) {
    log('DIAG_FAIL ' + String(e));
  }
  try {
    const img = await win.webContents.capturePage();
    fs.writeFileSync(SHOT_PATH, img.toPNG());
    log('已截图：' + SHOT_PATH);
    log('SHOT_OK ' + SHOT_PATH);
  } catch (e) {
    log('截图失败：' + String(e));
    log('SHOT_FAIL ' + String(e));
  }
  if (process.env.INKREALM_SHOT_EXIT === '1') app.quit();
}

// 单实例：重复打开时聚焦已有窗口
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const wins = BrowserWindow.getAllWindows();
    if (wins.length) {
      if (wins[0].isMinimized()) wins[0].restore();
      wins[0].focus();
    }
  });

  app.whenReady().then(async () => {
    // 麦克风授权：本地离线写作应用，语音输入需要在前端录音→后端 faster-whisper 识别。
    // 页面跑在 http://127.0.0.1:8723（属安全上下文，navigator.mediaDevices 可用），
    // 但 Electron 默认拒绝媒体权限，必须显式授权，否则 getUserMedia 永远 reject，
    // 本地识别兜底链路拿不到音频流 —— 这正是「编辑器语音输入不可以使用」的根因。
    try {
      session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
        if (permission === 'media' || permission === 'microphone' || permission === 'audioCapture') {
          callback(true);
        } else {
          callback(false);
        }
      });
      // 部分 Electron 版本还会走 permission check（如自动播放/设备枚举），一并放行麦克风类
      if (session.defaultSession.setPermissionCheckHandler) {
        session.defaultSession.setPermissionCheckHandler((_wc, permission) => {
          return permission === 'media' || permission === 'microphone' || permission === 'audioCapture';
        });
      }
      log('已授权麦克风权限（语音输入可用）');
    } catch (e) {
      log('麦克风授权设置失败：' + String(e));
    }

    // 生成桌面快捷方式后立即退出（供构建脚本调用）。
    // 用 Electron 原生 shell.writeShortcutLink —— 本机 COM 被安全策略拦截、手写 .lnk 也不被
    // Windows 接受（ERROR_NO_ASSOCIATION），只有这条原生路径能产出真正可用的 .lnk。
    const mk = process.env.INKREALM_MAKE_SHORTCUT;
    if (mk) {
      const target = process.env.INKREALM_SHORTCUT_TARGET || process.execPath;
      const opts = {
        target,
        cwd: path.dirname(target),
        description: '万维文 WitWork',
        icon: target,
        iconIndex: 0,
      };
      let ok = false; let err = '';
      try {
        ok = shell.writeShortcutLink(mk, 'create', opts);
      } catch (e) {
        err = String(e); console.error('SHORTCUT_FAIL ' + err);
      }
      console.log('SHORTCUT ' + (ok ? 'OK' : 'FAIL') + ' ' + mk + ' -> ' + target);
      app.quit();
      return;
    }
    try {
      const inUse = await portInUse();
      if (!inUse) {
        startBackend();
        await waitForPort(30000);
      } else {
        log('检测到 8723 已在运行，直接复用（不重复启动后端）');
      }
      createWindow();
    } catch (e) {
      dialog.showErrorBox('启动失败', String(e && e.message ? e.message : e));
      stopBackend();
      app.quit();
    }
  });

  app.on('window-all-closed', () => {
    stopBackend();
    app.quit();
  });
}
