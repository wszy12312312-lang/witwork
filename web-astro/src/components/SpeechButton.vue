<script setup lang="ts">
/**
 * 语音输入按钮（Web Speech API，默认中文 zh-CN）。
 *
 * - 识别到的一句话（final 结果）通过 `result` 事件增量吐出，
 *   父组件负责把文本插入到目标输入框的光标处。
 * - 中间结果（interim）只显示在按钮气泡上，不插入，避免重复。
 * - 浏览器不支持时整个按钮不渲染（Electron / Chrome / Edge 可用）。
 */
import { ref, onBeforeUnmount } from 'vue';

const props = defineProps<{
  lang?: string;
  title?: string;
}>();

const emit = defineEmits<{ (e: 'result', text: string): void }>();

function getSR(): any {
  if (typeof window === 'undefined') return null;
  const w = window as any;
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}
const supported = !!getSR();

const listening = ref(false);
const interim = ref('');
let rec: any = null;
let emittedFinal = '';

function start() {
  const SR = getSR();
  if (!SR || listening.value) return;
  rec = new SR();
  rec.lang = props.lang || 'zh-CN';
  rec.interimResults = true;
  rec.continuous = true;
  emittedFinal = '';
  interim.value = '';

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
    interim.value = interimNow;
  };
  rec.onend = () => {
    listening.value = false;
    interim.value = '';
  };
  rec.onerror = () => {
    listening.value = false;
    interim.value = '';
  };
  try {
    rec.start();
    listening.value = true;
  } catch {
    listening.value = false;
  }
}

function stop() {
  if (rec) {
    try {
      rec.stop();
    } catch {
      /* ignore */
    }
    rec = null;
  }
  listening.value = false;
  interim.value = '';
}

function toggle() {
  if (listening.value) stop();
  else start();
}

onBeforeUnmount(stop);
</script>

<template>
  <span v-if="supported" class="sb">
    <button
      class="mic"
      :class="{ live: listening }"
      :title="listening ? '停止语音输入' : (title || '语音输入')"
      @click="toggle"
    >
      <span class="mic-ico">🎤</span>
      <span v-if="listening" class="mic-live"></span>
    </button>
    <span v-if="listening && interim" class="mic-interim">{{ interim }}</span>
  </span>
</template>

<style scoped>
.sb {
  position: relative;
  display: inline-flex;
}
.mic {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--theme-line);
  border-radius: 50%;
  background: var(--theme-field);
  color: var(--theme-ink-soft);
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
  position: relative;
  transition: all 0.15s var(--motion);
}
.mic:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.mic.live {
  border-color: var(--theme-error);
  color: var(--theme-error);
  background: color-mix(in srgb, var(--theme-error) 10%, var(--theme-field));
}
.mic-live {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--theme-error);
  animation: micPulse 1s var(--motion) infinite;
}
@keyframes micPulse {
  50% {
    opacity: 0.35;
  }
}
.mic-interim {
  position: absolute;
  bottom: 32px;
  right: 0;
  z-index: 60;
  font-size: 11.5px;
  color: var(--theme-muted);
  background: var(--theme-paper);
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 3px 8px;
  max-width: 220px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
}
</style>
