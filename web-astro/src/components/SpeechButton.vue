<script setup lang="ts">
/**
 * 语音输入按钮（v2）：云端优先、本地兜底，绝不再「点了没反应」。
 *
 * 引擎链路：
 *  1. 云端 Web Speech API（Chrome/Edge，识别质量最好）；
 *  2. 云端不可达（国内网络 / 离线，error=network|service-not-allowed）→
 *     自动切换「本地录音」：MediaRecorder 录音 → POST /api/asr/transcribe
 *     → 服务端 faster-whisper 离线转写（本产品本地优先，兜底走本地是正解）。
 *  3. 麦克风未授权 / 无设备等硬错误 → 气泡明确告知原因，不再静默失败。
 *
 * 识别文本通过 `result` 事件吐给父组件：
 *  - 云端：final 结果增量吐出（不重复插入）；
 *  - 本地：说完点击停止后整段吐出一次。
 * 父组件负责把文本插入目标输入框光标处。
 */
import { ref, onBeforeUnmount } from 'vue';

const props = defineProps<{
  lang?: string;
  title?: string;
}>();

const emit = defineEmits<{ (e: 'result', text: string): void }>();

type Mode = 'idle' | 'cloud' | 'rec' | 'busy';
const mode = ref<Mode>('idle');
/** 气泡：云端 interim / 本地状态 / 错误原因 */
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

async function ensureMic(): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error('此环境无法访问麦克风');
  return await navigator.mediaDevices.getUserMedia({ audio: true });
}

async function start() {
  if (mode.value !== 'idle') return;
  try {
    stream = await ensureMic();
  } catch {
    flash('无法访问麦克风：请在系统与浏览器设置中允许麦克风权限', true, 6000);
    return;
  }
  const SR = getSR();
  if (SR && !cloudDead) tryCloud(SR);
  else startLocal();
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
    // 只把新增的 final 部分吐给父组件（增量追加，不会重复插入）
    if (finalNow.length > emittedFinal.length) {
      const delta = finalNow.slice(emittedFinal.length);
      emittedFinal = finalNow;
      if (delta.trim()) emit('result', delta);
    }
    if (interimNow) flash(interimNow, false, 0); // 中间结果常驻气泡，结束后清
  };
  rec.onerror = (e: any) => {
    const err = e?.error || 'unknown';
    if (err === 'network' || err === 'service-not-allowed') {
      // 云端识别服务不可达（国内网络 / 离线 / Electron）→ 自动转本地
      cleanupCloud();
      cloudDead = true;
      flash('云端识别不可达，已改用本地识别（说完再点一次结束）', false, 6000);
      startLocal();
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
    flash(`云端识别异常（${err}），已改用本地识别`, false, 6000);
    startLocal();
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
    flash('聆听中…', false, 0);
  } catch {
    cleanupCloud();
    cloudDead = true;
    startLocal();
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

function startLocal() {
  if (!stream) {
    // 理论不可达（start 已拿到 stream）；兜底再取一次
    ensureMic()
      .then((s) => {
        stream = s;
        startLocal();
      })
      .catch(() => flash('无法访问麦克风', true));
    return;
  }
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
    // 手动结束云端：final 已增量吐出，直接收尾
    cleanupCloud();
    mode.value = 'idle';
    note.value = '';
    releaseStream();
  } else if (mode.value === 'rec') {
    try {
      recorder?.stop(); // onstop → transcribeLocal
    } catch {
      stopAll();
    }
  } else if (mode.value === 'idle') {
    void start();
  }
  // busy：识别中，忽略点击
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
  <span class="sb" :class="{ on: mode !== 'idle' }">
    <button
      class="mic"
      :class="{ live: mode === 'cloud' || mode === 'rec', busy: mode === 'busy' }"
      :title="mode === 'cloud' || mode === 'rec' ? '停止语音输入' : (title || '语音输入')"
      :disabled="mode === 'busy'"
      @click="toggle"
    >
      <span class="mic-ico">🎤</span>
      <span v-if="mode === 'cloud' || mode === 'rec'" class="mic-live"></span>
    </button>
    <span v-if="note" class="mic-note" :class="{ err: noteErr }">{{ note }}</span>
  </span>
</template>

<style scoped>
/* 融入输入框右下角：无边框、半透明、贴角，hover / 工作时才醒目 */
.sb {
  position: relative;
  display: inline-flex;
}
.mic {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--theme-muted);
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
  position: relative;
  opacity: 0.5;
  transition: all 0.15s var(--motion);
}
.mic:hover:not(:disabled) {
  opacity: 1;
  color: var(--theme-accent-hover);
  background: color-mix(in srgb, var(--theme-accent) 10%, transparent);
}
.mic:disabled {
  cursor: wait;
  opacity: 0.7;
}
.mic.live {
  opacity: 1;
  color: var(--theme-error);
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
  animation: micBreath 1.2s ease-in-out infinite;
}
.mic.busy {
  opacity: 1;
  color: var(--theme-accent);
}
@keyframes micBreath {
  50% {
    background: color-mix(in srgb, var(--theme-error) 24%, transparent);
  }
}
.mic-live {
  position: absolute;
  top: 0;
  right: 0;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--theme-error);
  animation: micPulse 1s var(--motion) infinite;
}
@keyframes micPulse {
  50% {
    opacity: 0.3;
  }
}
.mic-note {
  position: absolute;
  bottom: 30px;
  right: 0;
  z-index: 60;
  font-size: 11.5px;
  color: var(--theme-ink-soft);
  background: var(--theme-paper);
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 3px 8px;
  max-width: 230px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
  box-shadow: 0 2px 10px color-mix(in srgb, var(--theme-ink) 14%, transparent);
}
.mic-note.err {
  color: var(--theme-error);
  border-color: color-mix(in srgb, var(--theme-error) 45%, var(--theme-line));
}
</style>
