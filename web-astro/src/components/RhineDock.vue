<script setup lang="ts">
// 功能面板：时钟/日期、今日事项、日程倒计时、歌曲信息、专注计时。
// 保留：时钟日期、今日事项、日程倒计时（日程名称+目标日期）、歌曲、专注计时（专注时长+休息时长）。
// 底部功能导航可切换各部件显隐与质感开关。
//
// 歌曲部件两种模式：
//   · 自动：读 Windows SMTC（系统媒体传输控件），任何上报到系统的播放器都能识别
//     （网易云 / QQ 音乐 / Spotify / PotPlayer / Edge / Chrome 网页播放器 …），无需手动填。
//   · 手动：自己填曲名 / 艺术家（不支持 SMTC 的环境或想固定显示时用）。
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { store, saveSettings, refreshSong, songControl, loadSongVolume, setSongVolume } from '../lib/store';
import RareCounter from './RareCounter.vue';

const emit = defineEmits<{ (e: 'close'): void }>();

// ---------- 部件显隐 ----------
const widgets = computed(
  () => new Set((store.hudWidgets || '').split(',').map((s) => s.trim()).filter(Boolean))
);
const show = (k: string) => widgets.value.has(k);
function toggleWidget(k: string) {
  const s = new Set(widgets.value);
  if (s.has(k)) s.delete(k);
  else s.add(k);
  const order = ['time', 'today', 'countdown', 'song', 'focus'];
  saveSettings({ hud_widgets: order.filter((x) => s.has(x)).join(',') });
}

// ---------- 时间日期 ----------
const now = ref(new Date());
let tick: ReturnType<typeof setInterval> | null = null;
const hh = computed(() => now.value.getHours());
const mm = computed(() => now.value.getMinutes());
const ss = computed(() => now.value.getSeconds());
const dateStr = computed(() => {
  const d = now.value;
  const wd = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()];
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}.${p(d.getMonth() + 1)}.${p(d.getDate())} 周${wd}`;
});

// ---------- 今日事项 ----------
const LS_TODO = 'inkrealm.dock.today';
interface Todo { t: string; done: boolean }
const todos = ref<Todo[]>([]);
const newTodo = ref('');
const todayKey = computed(() => {
  const d = now.value;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
});
const todoLeft = computed(() => todos.value.filter((t) => !t.done).length);
function loadTodos() {
  try {
    const o = JSON.parse(localStorage.getItem(LS_TODO) || '{}');
    todos.value = o && o.day === todayKey.value && Array.isArray(o.items) ? o.items : [];
  } catch {
    todos.value = [];
  }
}
function saveTodos() {
  try {
    localStorage.setItem(LS_TODO, JSON.stringify({ day: todayKey.value, items: todos.value }));
  } catch { /* ignore */ }
}
function addTodo() {
  const t = newTodo.value.trim();
  if (!t) return;
  todos.value.push({ t, done: false });
  newTodo.value = '';
  saveTodos();
}
function toggleTodo(i: number) {
  if (todos.value[i]) todos.value[i].done = !todos.value[i].done;
  saveTodos();
}
function delTodo(i: number) {
  todos.value.splice(i, 1);
  saveTodos();
}

// ---------- 日程倒计时 ----------
const LS_CD = 'inkrealm.dock.countdown';
const cdTarget = ref('');
const cdLabel = ref('');
const cdRemain = ref(0);
function loadCd() {
  try {
    const o = JSON.parse(localStorage.getItem(LS_CD) || '{}');
    cdTarget.value = o.target || '';
    cdLabel.value = o.label || '';
  } catch { /* ignore */ }
}
function saveCd() {
  try {
    localStorage.setItem(LS_CD, JSON.stringify({ target: cdTarget.value, label: cdLabel.value }));
  } catch { /* ignore */ }
}
function updateCd() {
  if (!cdTarget.value) { cdRemain.value = 0; return; }
  const t = new Date(cdTarget.value).getTime();
  cdRemain.value = Number.isFinite(t) ? Math.max(0, t - now.value.getTime()) : 0;
}
const cdD = computed(() => Math.floor(cdRemain.value / 86400000));
const cdH = computed(() => Math.floor(cdRemain.value / 3600000) % 24);
const cdM = computed(() => Math.floor(cdRemain.value / 60000) % 60);
const cdS = computed(() => Math.floor(cdRemain.value / 1000) % 60);
const p2 = (n: number) => String(n).padStart(2, '0');

// ---------- 歌曲 ----------
// 手动模式：曲名/艺术家存 localStorage。
// 自动模式：轮询 /api/song/now（后端走 Windows SMTC）。
const LS_SONG = 'inkrealm.dock.song';
const song = reactive({ title: '', artist: '' });
function loadSong() {
  try {
    const o = JSON.parse(localStorage.getItem(LS_SONG) || '{}');
    song.title = o.title || '';
    song.artist = o.artist || '';
  } catch { /* ignore */ }
}
function saveSong() {
  try {
    localStorage.setItem(LS_SONG, JSON.stringify({ title: song.title, artist: song.artist }));
  } catch { /* ignore */ }
}

const SONG_POLL_MS = 4000;
let songTimer: ReturnType<typeof setInterval> | null = null;
const songAuto = computed(() => store.songAutodetect);
const detected = computed(() => (store.song?.ok ? store.song.current || null : null));
const songPct = computed(() => {
  const d = detected.value;
  if (!d || !d.duration) return 0;
  return Math.max(0, Math.min(100, (d.position / d.duration) * 100));
});
function fmtTime(sec: number) {
  const s = Math.max(0, Math.floor(sec || 0));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}
const STATUS_TEXT: Record<string, string> = {
  Playing: '播放中', Paused: '已暂停', Stopped: '已停止',
  Closed: '已关闭', Opened: '已打开', Changing: '切换中',
};
const statusText = (s: string) => STATUS_TEXT[s] || s || '未知';
// 把 SMTC 的 appId（如 electron.app.douyin / Spotify.exe）变成人话
const APP_NAMES: Record<string, string> = {
  cloudmusic: '网易云音乐', qqmusic: 'QQ 音乐', spotify: 'Spotify', msedge: 'Edge',
  chrome: 'Chrome', douyin: '抖音', potplayer: 'PotPlayer', foobar2000: 'foobar2000',
  music: 'Groove 音乐', kugou: '酷狗', kuwo: '酷我', migu: '咪咕音乐', bilibili: '哔哩哔哩',
  vlc: 'VLC', aimp: 'AIMP', itunes: 'iTunes', zunemusic: 'Zune 音乐',
};
function appLabel(id: string) {
  if (!id) return '';
  const clean = id.replace(/\.exe$/i, '');
  const seg = clean.split(/[.!]/).filter(Boolean).pop() || clean;
  const key = seg.toLowerCase().replace(/[^a-z0-9]/g, '');
  return APP_NAMES[key] || seg;
}
function stopSongPoll() {
  if (songTimer) { clearInterval(songTimer); songTimer = null; }
}
function startSongPoll() {
  stopSongPoll();
  // 只在「歌曲部件可见 + 开了自动检测」时轮询，不给后端添无谓负担
  if (!store.songAutodetect || !show('song')) return;
  void refreshSong(true);
  loadVol();
  songTimer = setInterval(() => { void refreshSong(false); loadVol(); }, SONG_POLL_MS);
}
async function toggleAutodetect(on: boolean) {
  await saveSettings({ song_autodetect: on });
}

// ---------- 歌曲：封面 / 传输控制 / 音量 / 旋律可视化 ----------
// 封面：后端把当前曲目缩略图缓存为 PNG，按版本号 bust 前端缓存
const coverUrl = computed(() => (store.songCoverVersion ? '/song/cover?v=' + store.songCoverVersion : ''));
const coverOk = ref(true);
watch(() => store.songCoverVersion, () => { coverOk.value = true; });

// 播放状态（手动模式恒为 false，无系统播放器可控制）
const playing = computed(() => (songAuto.value ? !!detected.value?.playing : false));

// 传输控制（play/pause/toggle/next/prev），走后端 SMTC
async function songCtrl(action: 'play' | 'pause' | 'toggle' | 'next' | 'prev') {
  await songControl(action);
}
function playPause() {
  if (playing.value) void songCtrl('pause');
  else void songCtrl('play');
}

// 音量（当前播放 App 的音频会话）；不可用时滑块禁用
const volModel = computed<number>({
  get: () => store.songVolume?.level ?? 0,
  set: (v: number) => { void setSongVolume(Number(v)); },
});
const volAvailable = computed(() => !!store.songVolume?.available);
function loadVol() { void loadSongVolume(); }

// 旋律可视化：用 rAF 按时间合成一段镜像波形（无真实音频数据时的拟真律动）
const MEL_N = 30;
const mel = ref<number[]>(Array(MEL_N).fill(0.25));
let melRAF = 0;
let melT = 0;
function melStep() {
  melT += 0.14;
  const arr: number[] = [];
  for (let i = 0; i < MEL_N; i++) {
    const base = 0.22 + 0.5 * Math.abs(Math.sin(i * 0.45 + melT));
    const amp = playing.value ? 0.22 : 0.06;
    const jitter = amp * Math.abs(Math.sin(i * 1.2 + melT * 2.3));
    arr.push(Math.min(1, base + jitter));
  }
  mel.value = arr;
  melRAF = requestAnimationFrame(melStep);
}
function startMel() { if (!melRAF) melStep(); }
function stopMel() { if (melRAF) { cancelAnimationFrame(melRAF); melRAF = 0; } }

// ---------- 专注计时（番茄钟） ----------
const LS_FOCUS = 'inkrealm.dock.focus';
const focusTotal = ref(25 * 60);
const focusLeft = ref(25 * 60);
const focusRun = ref(false);
const focusDone = ref(0);
const breakMinutes = ref(5);
let focusTimer: ReturnType<typeof setInterval> | null = null;
let audioCtx: AudioContext | null = null;
function loadFocus() {
  try {
    const o = JSON.parse(localStorage.getItem(LS_FOCUS) || '{}');
    focusTotal.value = Math.max(60, Number(o.minutes || 25) * 60);
    breakMinutes.value = Math.max(1, Math.min(60, Number(o.break || 5)));
    focusDone.value = Number(o.done || 0);
  } catch { /* ignore */ }
  focusLeft.value = focusTotal.value;
}
function saveFocus() {
  try {
    localStorage.setItem(LS_FOCUS, JSON.stringify({ minutes: Math.round(focusTotal.value / 60), break: breakMinutes.value, done: focusDone.value }));
  } catch { /* ignore */ }
}
function chime() {
  try {
    const AC = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return;
    audioCtx = audioCtx || new AC();
    const o = audioCtx.createOscillator();
    const g = audioCtx.createGain();
    o.connect(g);
    g.connect(audioCtx.destination);
    o.type = 'sine';
    o.frequency.value = 880;
    const t = audioCtx.currentTime;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.16, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.9);
    o.start(t);
    o.stop(t + 1);
  } catch { /* ignore */ }
}
function focusStart() {
  if (focusRun.value) return;
  focusRun.value = true;
  focusTimer = setInterval(() => {
    if (focusLeft.value > 0) {
      focusLeft.value--;
      if (focusLeft.value === 0) {
        focusRun.value = false;
        if (focusTimer) clearInterval(focusTimer);
        focusDone.value++;
        chime();
        saveFocus();
      }
    }
  }, 1000);
}
function focusPause() {
  focusRun.value = false;
  if (focusTimer) { clearInterval(focusTimer); focusTimer = null; }
}
function focusReset() {
  focusPause();
  focusLeft.value = focusTotal.value;
}
function setFocusPreset(min: number) {
  focusPause();
  focusTotal.value = min * 60;
  focusLeft.value = min * 60;
  saveFocus();
}
function setBreak(min: number) {
  breakMinutes.value = min;
  saveFocus();
}
const focusPct = computed(() => (focusTotal.value ? 1 - focusLeft.value / focusTotal.value : 0));
const RING_R = 26;
const focusRing = computed(() => {
  const c = 2 * Math.PI * RING_R;
  return { strokeDasharray: String(c), strokeDashoffset: String(c * (1 - focusPct.value)) };
});
const focusMM = computed(() => p2(Math.floor(focusLeft.value / 60)));
const focusSS = computed(() => p2(focusLeft.value % 60));

// ---------- 快速开关 ----------
async function toggleTexture() { await saveSettings({ hud_texture: !store.hudTexture }); }

onMounted(() => {
  loadTodos();
  loadCd();
  loadSong();
  loadFocus();
  updateCd();
  startSongPoll();
  startMel();
  tick = setInterval(() => {
    now.value = new Date();
    updateCd();
  }, 1000);
});
// 开关自动检测 / 显隐歌曲部件 → 重新决定是否轮询
watch([() => store.songAutodetect, () => show('song')], () => startSongPoll());
// 切换播放 App → 重新读取该 App 音量
watch(() => detected.value?.appId, () => loadVol());
onBeforeUnmount(() => {
  if (tick) clearInterval(tick);
  if (focusTimer) clearInterval(focusTimer);
  stopSongPoll();
  stopMel();
});
</script>

<template>
  <div class="rdock" :class="{ tex: store.hudTexture }">
    <!-- 时钟日期：始终置顶 -->
    <section v-if="show('time')" class="rd-head">
      <div class="clock mono">
        <RareCounter :value="hh" :pad-start="2" :separator="''" :duration="0.5" /><span class="sep">:</span><RareCounter
          :value="mm" :pad-start="2" :separator="''" :duration="0.5"
        /><span class="sep">:</span><RareCounter :value="ss" :pad-start="2" :separator="''" :duration="0.4" />
      </div>
      <div class="date mono">{{ dateStr }}</div>
    </section>

    <!-- 功能内容 -->
    <div class="rd-body">
      <section v-if="show('today')" class="w">
        <div class="w-l mono">
          今日事项 <em>{{ todoLeft }} 待办</em>
        </div>
        <div class="row">
          <input v-model="newTodo" placeholder="添加事项…" @keyup.enter="addTodo" />
          <button class="q" @click="addTodo">＋</button>
        </div>
        <ul class="todos">
          <li v-for="(t, i) in todos" :key="i" :class="{ done: t.done }">
            <button class="cb" @click="toggleTodo(i)">{{ t.done ? '✓' : '' }}</button>
            <span class="tt" @click="toggleTodo(i)">{{ t.t }}</span>
            <button class="del" @click="delTodo(i)">✕</button>
          </li>
          <li v-if="!todos.length" class="none mono">— 无事项 —</li>
        </ul>
      </section>

      <section v-if="show('countdown')" class="w">
        <div class="w-l mono">日程倒计时</div>
        <div class="cd mono">
          <span class="cd-u"><b>{{ cdD }}</b>天</span>
          <span class="cd-u"><b>{{ p2(cdH) }}</b>时</span>
          <span class="cd-u"><b>{{ p2(cdM) }}</b>分</span>
          <span class="cd-u"><b>{{ p2(cdS) }}</b>秒</span>
        </div>
        <div class="w-sub mono">{{ cdLabel || '— 未命名日程 —' }}</div>
        <input v-model="cdLabel" class="in" placeholder="日程名称" @change="saveCd" />
        <input v-model="cdTarget" class="in" type="datetime-local" @change="saveCd" />
      </section>

      <section v-if="show('song')" class="w">
        <div class="w-l mono">
          歌曲信息
          <em>{{ songAuto ? (detected ? (detected.playing ? '系统检测·播放中' : '系统检测·已暂停') : '系统检测') : '手动' }}</em>
        </div>

        <!-- 自动：系统 SMTC（Windows 媒体传输控件） -->
        <template v-if="songAuto">
          <div class="song">
            <div class="song-art" :class="{ spin: playing }">
              <img v-if="coverUrl && coverOk" :key="store.songCoverVersion" :src="coverUrl" class="cover" alt="" @error="coverOk = false" />
              <span v-else class="note">♪</span>
            </div>
            <div class="song-meta">
              <div class="st" :title="detected?.title || ''">{{ detected?.title || '—' }}</div>
              <div class="sa">{{ detected?.artist || detected?.album || '—' }}</div>
            </div>
          </div>
          <div class="song-bar" v-if="detected && detected.duration > 0">
            <i :style="{ width: songPct + '%' }"></i>
          </div>
          <!-- 音乐旋律：rAF 合成的镜像波形（threeui 风格的弹性质感） -->
          <svg class="melody" :class="{ paused: !playing }" viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <linearGradient id="melGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="var(--theme-accent)" />
                <stop offset="100%" stop-color="var(--theme-accent)" stop-opacity="0.45" />
              </linearGradient>
            </defs>
            <rect v-for="(h, i) in mel" :key="i"
              :x="(i * (100 / MEL_N) + 0.4).toFixed(2)"
              :y="((24 - h * 22) / 2).toFixed(2)"
              :width="(100 / MEL_N - 0.8).toFixed(2)"
              :height="(h * 22).toFixed(2)"
              rx="0.8" fill="url(#melGrad)" />
          </svg>
          <div class="song-info mono">
            <span>
              <template v-if="detected">{{ detected.playing ? '播放中' : statusText(detected.status) }}</template>
              <template v-else-if="store.songError">检测不可用</template>
              <template v-else>— 无播放 —</template>
            </span>
            <span v-if="detected">{{ fmtTime(detected.position) }} / {{ fmtTime(detected.duration) }}</span>
            <span v-if="detected && detected.appId" class="src">{{ appLabel(detected.appId) }}</span>
          </div>
          <!-- 传输控制 + 音量 -->
          <div class="song-ctrls" v-if="detected">
            <button class="cp" title="上一首" @click="songCtrl('prev')">⏮</button>
            <button class="cp play" :title="playing ? '暂停' : '播放'" @click="playPause">
              <span v-if="playing">⏸</span><span v-else>▶</span>
            </button>
            <button class="cp" title="下一首" @click="songCtrl('next')">⏭</button>
            <div class="vol">
              <span class="vol-ic">🔊</span>
              <input type="range" min="0" max="100" step="1" v-model.number="volModel"
                :disabled="!volAvailable"
                :title="volAvailable ? ('音量 ' + volModel + '%') : '本机不支持音量控制'" />
            </div>
          </div>
          <div v-if="detected && volAvailable === false" class="song-err mono">本机不支持音量控制（需 pycaw）</div>
          <div v-if="store.songError" class="song-err mono" :title="store.songError">检测不可用，可在设置关闭自动检测</div>
        </template>

        <!-- 手动：只读展示，编辑在「设置 → 偏好」 -->
        <template v-else>
          <div class="song">
            <div class="song-art"><span class="note">♪</span></div>
            <div class="song-meta">
              <div class="st" :title="song.title">{{ song.title || '—' }}</div>
              <div class="sa">{{ song.artist || '—' }}</div>
            </div>
          </div>
          <svg class="melody" viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <linearGradient id="melGradM" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="var(--theme-accent)" />
                <stop offset="100%" stop-color="var(--theme-accent)" stop-opacity="0.45" />
              </linearGradient>
            </defs>
            <rect v-for="(h, i) in mel" :key="i"
              :x="(i * (100 / MEL_N) + 0.4).toFixed(2)"
              :y="((24 - h * 22) / 2).toFixed(2)"
              :width="(100 / MEL_N - 0.8).toFixed(2)"
              :height="(h * 22).toFixed(2)"
              rx="0.8" fill="url(#melGradM)" />
          </svg>
          <div class="song-err mono">手动模式 · 在「设置 → 偏好」编辑曲名/艺术家</div>
        </template>
      </section>

      <section v-if="show('focus')" class="w">
        <div class="w-l mono">
          专注计时 <em>{{ focusDone }} 完成</em>
        </div>
        <div class="focus">
          <svg class="ring" viewBox="0 0 64 64" width="70" height="70">
            <circle class="ring-bg" cx="32" cy="32" :r="RING_R" />
            <circle class="ring-fg" cx="32" cy="32" :r="RING_R" :style="focusRing" />
          </svg>
          <div class="fnum mono">{{ focusMM }}:{{ focusSS }}</div>
        </div>
        <div class="f-acts">
          <button class="q" @click="focusRun ? focusPause() : focusStart()">{{ focusRun ? '暂停' : '开始' }}</button>
          <button class="q" @click="focusReset">重置</button>
          <button class="q" @click="setFocusPreset(25)">专注 25′</button>
          <button class="q" @click="setFocusPreset(5)">休息 5′</button>
        </div>
        <div class="break mono">休息时长 {{ breakMinutes }} 分</div>
      </section>
    </div>

    <!-- 底部功能导航 -->
    <footer class="rd-nav">
      <button class="q" :class="{ on: show('time') }" @click="toggleWidget('time')">时钟</button>
      <button class="q" :class="{ on: show('today') }" @click="toggleWidget('today')">事项</button>
      <button class="q" :class="{ on: show('countdown') }" @click="toggleWidget('countdown')">日程</button>
      <button class="q" :class="{ on: show('song') }" @click="toggleWidget('song')">歌曲</button>
      <button class="q" :class="{ on: show('focus') }" @click="toggleWidget('focus')">专注</button>
      <button class="q" :class="{ on: store.hudTexture }" @click="toggleTexture">质感</button>
      <button class="q x" @click="emit('close')">✕</button>
    </footer>
  </div>
</template>

<style scoped>
.rdock {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  border-bottom: 1px solid var(--theme-line);
  background: color-mix(in srgb, var(--theme-panel) var(--panel-alpha), transparent);
  font-family: var(--font-mono);
  font-size: 12px;
}
.rdock.tex {
  background-image: repeating-linear-gradient(
    to bottom,
    color-mix(in srgb, var(--theme-accent) 4%, transparent) 0 1px,
    transparent 1px 3px
  );
}
.rd-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 4px 6px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--theme-field) 70%, transparent);
}
.clock {
  display: flex;
  align-items: baseline;
  font-size: 22px;
  font-weight: 700;
  color: var(--theme-accent);
  letter-spacing: 0.02em;
}
.clock .sep {
  opacity: 0.5;
  animation: blink 2s steps(1) infinite;
}
@keyframes blink { 50% { opacity: 0.15; } }
.date {
  font-size: 11px;
  color: var(--theme-muted);
  margin-left: auto;
}
.rd-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: auto;
  min-height: 0;
  /* 部件区封顶：面板应让位给下面的「作品档案」树（整体有 1.2 倍缩放，
   * 38vh 会把树挤到只剩两三行）。够用即可，超出靠内部滚动。 */
  max-height: 26vh;
}
.w {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--theme-field) 70%, transparent);
  padding: 8px 9px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.w-l {
  font-size: 10.5px;
  letter-spacing: 0.1em;
  color: var(--theme-muted);
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.w-l em { font-style: normal; color: var(--theme-accent); }
.w-sub { font-size: 11px; color: var(--theme-ink-soft); }
.row { display: flex; gap: 6px; }
.row input, .in {
  flex: 1;
  min-width: 0;
  font-family: var(--font-mono);
  font-size: 11.5px;
  padding: 4px 7px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--theme-paper) 60%, transparent);
  color: var(--theme-ink);
}
.row input:focus, .in:focus { outline: none; border-color: var(--theme-accent); }
.todos { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; }
.todos li { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--theme-ink-soft); }
.todos li.done .tt { text-decoration: line-through; color: var(--theme-muted); }
.cb {
  width: 16px; height: 16px; flex: none;
  border: 1px solid var(--theme-line);
  border-radius: 3px;
  background: transparent;
  color: var(--theme-success);
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
}
.tt { flex: 1; min-width: 0; cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.del { border: none; background: transparent; color: var(--theme-muted); cursor: pointer; font-size: 11px; }
.del:hover { color: var(--theme-error); }
.none { font-size: 11px; color: var(--theme-muted); text-align: center; padding: 4px 0; }
.cd { display: flex; gap: 3px; align-items: baseline; }
.cd-u { font-size: 10.5px; color: var(--theme-muted); }
.cd-u b { font-size: 17px; color: var(--theme-accent); margin-right: 2px; }
.song { display: flex; gap: 8px; align-items: center; }
.song-art {
  width: 38px; height: 38px; flex: none;
  display: grid; place-items: center;
  border: 1px solid color-mix(in srgb, var(--theme-line) 80%, var(--theme-accent));
  border-radius: 9px;
  overflow: hidden;
  background: color-mix(in srgb, var(--theme-field) 70%, transparent);
  color: var(--theme-accent);
  font-size: 16px;
  box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 10%, transparent), 0 1px 3px color-mix(in srgb, var(--theme-ink) 18%, transparent);
}
.song-art .cover { width: 100%; height: 100%; object-fit: cover; display: block; }
.song-art .note { font-size: 16px; line-height: 1; }
/* 只有真的在播放时才让唱片转起来 */
.song-art.spin { animation: song-spin 6s linear infinite; }
@keyframes song-spin { to { transform: rotate(360deg); } }
.song-meta { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.st {
  font-size: 12.5px;
  color: var(--theme-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sa {
  font-size: 11px;
  color: var(--theme-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.song-bar {
  height: 3px;
  border-radius: 2px;
  background: color-mix(in srgb, var(--theme-line) 70%, transparent);
  overflow: hidden;
}
.song-bar i {
  display: block;
  height: 100%;
  background: var(--theme-accent);
  transition: width 0.6s linear;
}
.song-info {
  display: flex;
  gap: 8px;
  align-items: baseline;
  font-size: 10.5px;
  color: var(--theme-muted);
}
.song-info .src { margin-left: auto; color: var(--theme-accent); }
.song-ctrls { display: flex; align-items: center; gap: 6px; flex-wrap: nowrap; }
.cp {
  width: 26px; height: 26px; flex: none;
  display: grid; place-items: center;
  border: 1px solid var(--theme-line);
  border-radius: 50%;
  background: color-mix(in srgb, var(--theme-field) 80%, transparent);
  color: var(--theme-ink);
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
  box-shadow: 0 1px 0 color-mix(in srgb, var(--theme-ink) 12%, transparent), inset 0 1px 0 color-mix(in srgb, #fff 8%, transparent);
  transition: transform 0.12s var(--motion), border-color 0.2s var(--motion), color 0.2s var(--motion);
}
.cp:hover { border-color: var(--theme-accent); color: var(--theme-accent-hover); }
.cp:active { transform: scale(0.88); }
.cp.play {
  width: 30px; height: 30px;
  color: var(--theme-accent);
  border-color: color-mix(in srgb, var(--theme-accent) 55%, var(--theme-line));
  background: color-mix(in srgb, var(--theme-accent) 12%, var(--theme-field));
}
.vol { display: flex; align-items: center; gap: 5px; flex: 1; min-width: 0; margin-left: 2px; }
.vol-ic { font-size: 11px; opacity: 0.7; flex: none; }
.vol input[type='range'] { flex: 1; min-width: 0; height: 4px; accent-color: var(--theme-accent); }
.vol input[type='range']:disabled { opacity: 0.4; }
.song-err {
  font-size: 10.5px;
  color: var(--theme-error);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.melody { width: 100%; height: 22px; display: block; }
.melody.paused { opacity: 0.5; }
.melody rect { transition: height 0.12s linear, y 0.12s linear; }
.focus { display: flex; align-items: center; justify-content: center; position: relative; }
.ring { transform: rotate(-90deg); }
.ring-bg { fill: none; stroke: var(--theme-line); stroke-width: 4; }
.ring-fg { fill: none; stroke: var(--theme-accent); stroke-width: 4; stroke-linecap: round; transition: stroke-dashoffset 0.5s linear; }
.fnum { position: absolute; font-size: 15px; color: var(--theme-ink); letter-spacing: 0.04em; }
.f-acts { display: flex; gap: 5px; flex-wrap: wrap; }
.break { font-size: 10.5px; color: var(--theme-muted); text-align: center; }
.rd-nav {
  display: flex;
  gap: 4px;
  padding-top: 6px;
  border-top: 1px solid var(--theme-line);
  flex-wrap: wrap;
}
.q {
  font-family: var(--font-mono);
  font-size: 10.5px;
  padding: 2px 7px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--theme-ink-soft);
  cursor: pointer;
  flex: none;
  transition: all 0.2s var(--motion);
}
.q:hover { border-color: var(--theme-accent); color: var(--theme-accent-hover); }
.q.on { border-color: var(--theme-accent); color: var(--theme-accent-hover); background: color-mix(in srgb, var(--theme-accent) 10%, transparent); }
.q.x:hover { border-color: var(--theme-error); color: var(--theme-error); }
@media (prefers-reduced-motion: reduce) {
  .song-art, .bars i, .clock .sep { animation: none; }
}
</style>
