<script setup lang="ts">
// rareui「Delete Button」交互：点击垃圾桶→盖子弹开、滑出确认/取消；
// 确认后原位画一个对勾，再触发 confirm。Esc 取消。无对话框、原位确认。
import { ref, onMounted, onBeforeUnmount } from 'vue';

const props = withDefaults(
  defineProps<{
    /** md = 作品行用的标准尺寸；sm = 目录树里章节/卷行用的紧凑尺寸 */
    size?: 'md' | 'sm';
    /** 悬浮提示，例如「删除本章」 */
    title?: string;
  }>(),
  { size: 'md', title: '删除' }
);

const emit = defineEmits<{ (e: 'confirm'): void }>();
const armed = ref(false);
const done = ref(false);

function onMain() {
  if (done.value) return;
  armed.value = !armed.value;
}
function confirm() {
  if (done.value) return;
  done.value = true;
  armed.value = false;
  // 对勾画完后真正执行删除
  setTimeout(() => {
    emit('confirm');
    done.value = false;
  }, 620);
}
function cancel() {
  armed.value = false;
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && armed.value) armed.value = false;
}
onMounted(() => window.addEventListener('keydown', onKey));
onBeforeUnmount(() => window.removeEventListener('keydown', onKey));
</script>

<template>
  <span class="rd" :class="[{ armed, done }, props.size]">
    <button
      class="rd-main"
      :class="{ on: armed || done }"
      type="button"
      :title="done ? '已删除' : props.title"
      @click="onMain"
    >
      <svg class="rd-can" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
        <path class="rd-lid" d="M4 7h16" />
        <path class="rd-lid" d="M9 7V4h6v3" />
        <path class="rd-body" d="M6 7l1 13h10l1-13" />
        <path class="rd-line" d="M10 11v6M14 11v6" />
      </svg>
      <svg v-if="done" class="rd-check" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
        <path d="M5 13l4 4L19 7" />
      </svg>
    </button>

    <span class="rd-panel" v-if="armed">
      <button class="rd-act ok" type="button" title="确认删除" @click.stop="confirm">✓</button>
      <button class="rd-act no" type="button" title="取消" @click.stop="cancel">✕</button>
    </span>
  </span>
</template>

<style scoped>
.rd {
  position: relative;
  display: inline-flex;
  z-index: 20;
}
.rd-main {
  position: relative;
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--theme-line);
  border-radius: 6px;
  background: transparent;
  color: var(--theme-ink-soft);
  cursor: pointer;
  transition: all 0.2s var(--motion);
}
.rd-main:hover {
  border-color: var(--theme-error);
  color: var(--theme-error);
}
.rd-main.on {
  border-color: var(--theme-error);
  color: var(--theme-error);
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
}
.rd-can {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.rd-lid {
  transform-origin: 12px 7px;
  transition: transform 0.25s var(--motion);
}
.rd.armed .rd-lid {
  transform: rotate(-30deg) translateY(-1px);
}
.rd-check {
  position: absolute;
  fill: none;
  stroke: var(--theme-success);
  stroke-width: 2.6;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 26;
  stroke-dashoffset: 26;
  animation: rd-draw 0.45s var(--motion) forwards;
}
@keyframes rd-draw {
  to {
    stroke-dashoffset: 0;
  }
}
.rd-panel {
  position: absolute;
  top: 50%;
  right: calc(100% + 8px);
  transform: translateY(-50%);
  display: flex;
  gap: 6px;
  padding: 5px 7px;
  background: var(--theme-panel);
  border: 1px solid var(--theme-line);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28);
  animation: rd-pop 0.18s var(--motion);
}
@keyframes rd-pop {
  from {
    opacity: 0;
    transform: translateY(-50%) scale(0.85);
  }
  to {
    opacity: 1;
    transform: translateY(-50%) scale(1);
  }
}
.rd-act {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  transition: transform 0.15s var(--motion);
}
.rd-act:hover {
  transform: scale(1.14);
}
.rd-act.ok {
  background: var(--theme-success);
}
.rd-act.no {
  background: var(--theme-error);
}
/* 紧凑变体（目录树的章节 / 卷行）：图标与 md 变体保持同一视觉大小（16px 内占比一致），
 * 按钮壳 24px：图标不再显得过小，同时不撑破树行 */
.rd.sm .rd-main {
  width: 24px;
  height: 24px;
  border-radius: 5px;
}
.rd.sm .rd-main svg {
  width: 14px;
  height: 14px;
}
.rd.sm .rd-check {
  width: 14px;
  height: 14px;
}
.rd.sm .rd-panel {
  right: calc(100% + 4px);
  gap: 4px;
  padding: 3px 5px;
  border-radius: 6px;
}
.rd.sm .rd-act {
  width: 18px;
  height: 18px;
  font-size: 11px;
}
</style>
