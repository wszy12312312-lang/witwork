<script setup lang="ts">
/**
 * 语音输入按钮（threeui 设计语言重制版）
 *
 * 视觉：取自 vendor/threeui 的 CircleButtons（src/shaders/circle-buttons/circle-buttons.css）
 *   · 分层结构 aura / rim(orbit) / face / icon —— 与 threeui 的圆钮同构
 *   · 缓动沿用 threeui 的 --spring: cubic-bezier(0.32, 0.72, 0, 1)
 *   · 按下回弹（scale .92）、hover 微抬、aura 呼吸、orbit 环旋转
 *   · 聆听中用 threeui 风格的等宽「均衡条」脉冲表示正在收音
 *   · 状态气泡是 threeui HUD 样式（切角 + 等宽字 + 细描边）
 *
 * 引擎链路（关键修复）：
 *   1. 云端 Web Speech API —— **不再要求先拿到麦克风**（Electron / 部分内嵌环境里
 *      navigator.mediaDevices 可能缺失，之前那种「先 getUserMedia 再识别」的写法
 *      会直接把本来能用的云端识别也一起废掉，正是写作界面点麦克风没反应的原因）。
 *   2. 云端不可达（国内网络 / 离线，error=network|service-not-allowed）→ 自动切
 *      「本地录音」：MediaRecorder → POST /api/asr/transcribe → faster-whisper 离线转写。
 *   3. 麦克风未授权 / 无设备 / 引擎缺失 → 气泡明确说明原因，不再静默失败。
 *
 * 文本通过 `result` 事件吐给父组件：云端增量吐（不重复插入），本地整段吐一次。
 */
import { ref, onBeforeUnmount } from 'vue';

const props = defineProps<{
  lang?: string;
  title?: string;
}>();

const emit = defineEmits<{ (e: 'result', text: string): void }>();

type Mode = 'idle' | 'cloud' | 'rec' | 'busy';
const mode = ref<Mode>('idle');
const note = ref('');
const noteErr = ref(false);
let noteTimer: number | null = null;

let rec: any = null;
let emittedFinal = '';
let stream: MediaStream | null = null;
let recorder: MediaRecorder | null = null;
let chunks: Blob[] = [];
/** 云端连不上过一次后，本次会话不再反复尝试（避免每次点击都等一轮网络超时） */
let cloudDead = false;

function getSR(): any {
  if (typeof window === 'undefined') return null;
  const w = window as any;
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

function flash(msg: string, isErr = false, ms = 4200) {
  note.value = msg;
  noteErr.value = isErr;
  if (noteTimer) window.clearTimeout(noteTimer);
  if (ms > 0) noteTimer = window.setTimeout(() => (note.value = ''), ms);
}

function releaseStream() {
  if (stream) {
    for (const t of stream.getTracks()) t.stop();
    stream = null;
  }
}

function hasMicApi(): boolean {
  return typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia;
}

async function ensureMic(): Promise<MediaStream> {
  if (!hasMicApi()) throw new Error('no-media-devices');
  return await navigator.mediaDevices.getUserMedia({ audio: true });
}

async function start() {
  if (mode.value !== 'idle') return;
  const SR = getSR();
  // 云端优先，且不依赖 getUserMedia（Electron 里即使没有 mediaDevices 也可能可识别）
  if (SR && !cloudDead) {
    tryCloud(SR);
    return;
  }
  if (!hasMicApi()) {
    flash('此环境无法录音：需要 https 或 localhost 页面，且浏览器允许麦克风', true, 7000);
    return;
  }
  try {
    stream = await ensureMic();
  } catch {
    flash('无法访问麦克风：请在系统与浏览器设置中允许麦克风权限', true, 6000);
    return;
  }
  startLocal();
}

/* ---------- 云端 Web Speech ---------- */

function tryCloud(SR: any) {
  rec = new SR();
  rec.lang = props.lang || 'zh-CN';
  rec.interimResults = true;
  rec.continuous = true;
  emittedFinal = '';

  rec.onresult = (e: any) => {
    let finalNow = '';
    let interimNow = '';
    for (let i = 0; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) finalNow += r[0].transcript;
      else interimNow += r[0].transcript;
    }
    if (finalNow.length > emittedFinal.length) {
      const delta = finalNow.slice(emittedFinal.length);
      emittedFinal = finalNow;
      if (delta.trim()) emit('result', delta);
    }
    if (interimNow) flash(interimNow, false, 0);
  };
  rec.onerror = (e: any) => {
    const err = e?.error || 'unknown';
    if (err === 'network' || err === 'service-not-allowed') {
      cleanupCloud();
      cloudDead = true;
      void startLocalWithMic();
      return;
    }
    if (err === 'no-speech') {
      stopAll();
      flash('没听到说话，再试一次？', true);
      return;
    }
    if (err === 'not-allowed') {
      stopAll();
      flash('麦克风权限被拒绝：请在浏览器地址栏权限设置中允许', true, 6000);
      return;
    }
    if (err === 'audio-capture') {
      stopAll();
      flash('未检测到可用麦克风设备', true, 6000);
      return;
    }
    cleanupCloud();
    cloudDead = true;
    void startLocalWithMic();
  };
  rec.onend = () => {
    if (mode.value === 'cloud') {
      mode.value = 'idle';
      note.value = '';
      releaseStream();
    }
  };
  try {
    rec.start();
    mode.value = 'cloud';
    flash('云端聆听中…', false, 0);
  } catch {
    cleanupCloud();
    cloudDead = true;
    void startLocalWithMic();
  }
}

function cleanupCloud() {
  if (rec) {
    rec.onresult = rec.onerror = rec.onend = null;
    try {
      rec.stop();
    } catch {
      /* ignore */
    }
    rec = null;
  }
}

/* ---------- 本地录音 → 服务端 faster-whisper ---------- */

async function startLocalWithMic() {
  if (!hasMicApi()) {
    flash('云端识别不可达，且此环境无法录音（需 https/localhost + 麦克风）', true, 7000);
    return;
  }
  if (!stream) {
    try {
      stream = await ensureMic();
    } catch {
      flash('无法访问麦克风：请在系统与浏览器设置中允许权限', true, 6000);
      return;
    }
  }
  startLocal();
  flash('已改用本地识别：说完再点一次结束', false, 5000);
}

function startLocal() {
  if (!stream) return;
  chunks = [];
  try {
    recorder = new MediaRecorder(stream);
  } catch {
    stopAll();
    flash('此环境不支持录音（MediaRecorder 不可用）', true, 6000);
    return;
  }
  recorder.ondataavailable = (e: BlobEvent) => {
    if (e.data && e.data.size) chunks.push(e.data);
  };
  recorder.onstop = () => void transcribeLocal();
  recorder.start();
  mode.value = 'rec';
  flash('本地录音中… 说完再点一次开始识别', false, 0);
}

async function transcribeLocal() {
  if (!chunks.length) {
    stopAll();
    flash('没有录到声音', true);
    return;
  }
  mode.value = 'busy';
  flash('本地识别中…', false, 0);
  const blob = new Blob(chunks, { type: recorder?.mimeType || 'audio/webm' });
  chunks = [];
  try {
    const fd = new FormData();
    fd.append('file', blob, 'speech.webm');
    const r = await fetch(`/api/asr/transcribe?lang=${encodeURIComponent(props.lang || 'zh')}`, {
      method: 'POST',
      body: fd,
    });
    const d = await r.json().catch(() => ({}) as any);
    if (!r.ok) throw new Error(String(d?.detail || `HTTP ${r.status}`));
    const text = String(d?.text || '').trim();
    if (text) {
      emit('result', text);
      note.value = '';
    } else {
      flash('没有识别到内容，请靠近麦克风再试', true);
    }
  } catch (e: unknown) {
    const m = String((e as Error)?.message || e);
    flash(
      /501|faster-whisper/i.test(m)
        ? '本地识别引擎未安装：请在服务端 venv 执行 pip install faster-whisper'
        : `本地识别失败：${m}`,
      true,
      7000
    );
  } finally {
    recorder = null;
    releaseStream();
    mode.value = 'idle';
  }
}

/* ---------- 开关 ---------- */

function toggle() {
  if (mode.value === 'cloud') {
    cleanupCloud();
    mode.value = 'idle';
    note.value = '';
    releaseStream();
  } else if (mode.value === 'rec') {
    try {
      recorder?.stop();
    } catch {
      stopAll();
    }
  } else if (mode.value === 'idle') {
    void start();
  }
}

function stopAll() {
  cleanupCloud();
  try {
    recorder?.stop();
  } catch {
    /* ignore */
  }
  recorder = null;
  chunks = [];
  releaseStream();
  mode.value = 'idle';
  note.value = '';
}

onBeforeUnmount(stopAll);
</script>

<template>
  <span class="tu-mic">
    <button
      class="mic"
      :class="mode"
      :title="mode === 'cloud' || mode === 'rec' ? '停止语音输入' : (title || '语音输入')"
      :disabled="mode === 'busy'"
      @click="toggle"
    >
      <span class="aura" aria-hidden="true"></span>
      <span class="orbit" aria-hidden="true"></span>
      <span class="face" aria-hidden="true"></span>
      <span v-if="mode === 'cloud' || mode === 'rec'" class="bars" aria-hidden="true">
        <i></i><i></i><i></i>
      </span>
      <span v-else class="icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round">
          <rect x="9" y="2.6" width="6" height="11" rx="3" />
          <path d="M5.6 11.6a6.4 6.4 0 0 0 12.8 0" />
          <path d="M12 18.2v3.2" />
          <path d="M8.6 21.4h6.8" />
        </svg>
      </span>
    </button>
    <span v-if="note" class="tu-note" :class="{ err: noteErr }">{{ note }}</span>
  </span>
</template>

<style scoped>
/* ===== threeui CircleButtons 同构：aura / orbit(rim) / face / icon 分层 ===== */
.tu-mic {
  position: relative;
  display: inline-flex;
}
.mic {
  --sz: 30px;
  position: relative;
  width: var(--sz);
  height: var(--sz);
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--theme-muted);
  cursor: pointer;
  isolation: isolate;
  transform: translateZ(0);
  transition: transform var(--dur-base) var(--spring), color 0.25s var(--motion);
  -webkit-tap-highlight-color: transparent;
}
.mic:hover:not(:disabled) {
  color: var(--theme-accent-hover);
  transform: translateY(-1px) scale(1.07);
}
.mic:active:not(:disabled) {
  transform: scale(0.9);
  transition-duration: var(--dur-fast);
}
.mic:disabled {
  cursor: progress;
}

.face {
  position: absolute;
  inset: 0;
  z-index: 1;
  border-radius: 50%;
  background: color-mix(in srgb, var(--theme-paper) 70%, transparent);
  border: 1px solid color-mix(in srgb, currentColor 32%, transparent);
  transition: all var(--dur-base) var(--spring);
}
.aura {
  position: absolute;
  inset: -7px;
  z-index: 0;
  border-radius: 50%;
  opacity: 0;
  background: radial-gradient(
    circle at 50% 50%,
    color-mix(in srgb, currentColor 46%, transparent) 0%,
    transparent 70%
  );
  filter: blur(6px);
  transition: opacity var(--dur-base) var(--motion);
}
.mic:hover .aura {
  opacity: 0.6;
}
.orbit {
  position: absolute;
  inset: -3px;
  z-index: 2;
  border-radius: 50%;
  opacity: 0;
  border: 1px dashed color-mix(in srgb, currentColor 55%, transparent);
  transition: opacity var(--dur-base) var(--motion);
}
.icon {
  position: absolute;
  inset: 0;
  z-index: 3;
  display: grid;
  place-items: center;
}
.icon svg {
  width: 52%;
  height: 52%;
  overflow: visible;
}

/* 收音中：threeui 风格等宽均衡条脉冲 */
.bars {
  position: absolute;
  inset: 0;
  z-index: 3;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
}
.bars i {
  width: 2px;
  height: 6px;
  border-radius: 1px;
  background: currentColor;
  animation: tuBar 0.9s var(--motion) infinite;
}
.bars i:nth-child(2) {
  height: 10px;
  animation-delay: 0.15s;
}
.bars i:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes tuBar {
  0%,
  100% {
    transform: scaleY(0.5);
    opacity: 0.55;
  }
  50% {
    transform: scaleY(1.7);
    opacity: 1;
  }
}

/* 状态：聆听 / 录音 / 识别中 */
.mic.cloud,
.mic.rec {
  color: var(--theme-error);
}
.mic.cloud .aura,
.mic.rec .aura {
  opacity: 0.8;
  animation: tuPulse 1.8s var(--motion) infinite;
}
.mic.cloud .orbit,
.mic.rec .orbit {
  opacity: 0.85;
  animation: tuOrbit 3.4s linear infinite;
}
.mic.busy {
  color: var(--theme-accent);
}
.mic.busy .orbit {
  opacity: 1;
  border-style: solid;
  border-top-color: transparent;
  animation: tuOrbit 1s linear infinite;
}
.mic.busy .aura {
  opacity: 0.5;
}
@keyframes tuPulse {
  50% {
    transform: scale(1.28);
    opacity: 0.38;
  }
}
@keyframes tuOrbit {
  to {
    transform: rotate(360deg);
  }
}

/* 状态气泡：threeui HUD 样式（切角 + 等宽 + 细描边） */
.tu-note {
  position: absolute;
  bottom: calc(100% + 8px);
  right: 0;
  z-index: 60;
  --chamfer: 6px;
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.5;
  color: var(--theme-ink-soft);
  background: var(--theme-paper);
  border: 1px solid var(--theme-line);
  padding: 4px 9px;
  max-width: 240px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
  clip-path: polygon(
    var(--chamfer) 0,
    100% 0,
    100% calc(100% - var(--chamfer)),
    calc(100% - var(--chamfer)) 100%,
    0 100%,
    0 var(--chamfer)
  );
  box-shadow: 0 6px 18px color-mix(in srgb, var(--theme-ink) 16%, transparent);
  animation: tuNoteIn var(--dur-base) var(--spring);
}
.tu-note.err {
  color: var(--theme-error);
  border-color: color-mix(in srgb, var(--theme-error) 45%, var(--theme-line));
}
@keyframes tuNoteIn {
  from {
    opacity: 0;
    transform: translateY(6px) scale(0.96);
  }
}

@media (prefers-reduced-motion: reduce) {
  .mic,
  .face,
  .aura,
  .orbit,
  .bars i,
  .tu-note {
    animation: none !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
