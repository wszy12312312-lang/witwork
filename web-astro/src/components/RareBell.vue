<script setup lang="ts">
// rareui「Notification bell」交互：有未读时铃铛轻微摇摆、红点脉冲计数，
// 点击展开下拉面板（淡入+下滑），逐条「已读」/一键全部已读。
// 数据源即后端提醒服务（stats/notifications），每分钟轮询一次。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { store, loadNotifications, readNotification } from '../lib/store';

const open = ref(false);
const root = ref<HTMLElement | null>(null);
const list = computed(() => store.statsNotifications || []);
const unread = computed(() => list.value.filter((n) => !n.read).length);

let poll: ReturnType<typeof setInterval> | null = null;

async function toggle() {
  open.value = !open.value;
  if (open.value) await loadNotifications();
}
function close() {
  open.value = false;
}
async function markOne(id?: number) {
  await readNotification(id);
}
function onDoc(e: MouseEvent) {
  if (!open.value) return;
  if (root.value && !root.value.contains(e.target as Node)) close();
}

onMounted(async () => {
  await loadNotifications();
  document.addEventListener('click', onDoc);
  poll = setInterval(() => {
    if (!open.value) loadNotifications();
  }, 60000);
});
onBeforeUnmount(() => {
  document.removeEventListener('click', onDoc);
  if (poll) clearInterval(poll);
});
</script>

<template>
  <span ref="root" class="rb">
    <button class="rb-btn" :class="{ ring: unread > 0, on: open }" type="button" title="提醒" @click.stop="toggle">
      <svg class="rb-ico" viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
        <path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6" />
        <path d="M10.5 20a1.6 1.6 0 0 0 3 0" />
      </svg>
      <span v-if="unread > 0" class="rb-badge">{{ unread > 99 ? '99+' : unread }}</span>
    </button>

    <Transition name="rb-pop">
      <div v-if="open" class="rb-panel" @click.stop>
        <div class="rb-head">
          <span class="rb-title">提醒</span>
          <button v-if="unread > 0" class="rb-all" @click="markOne()">全部已读</button>
        </div>
        <div class="rb-list">
          <div
            v-for="n in list"
            :key="n.id"
            class="rb-row"
            :class="{ unread: !n.read }"
            @click="!n.read && markOne(n.id)"
          >
            <span class="rb-dot" :class="{ on: !n.read }"></span>
            <div class="rb-body">
              <div class="rb-t">{{ n.title || '提醒' }}</div>
              <div class="rb-c">{{ n.body }}</div>
            </div>
          </div>
          <div v-if="!list.length" class="rb-empty">暂无提醒</div>
        </div>
      </div>
    </Transition>
  </span>
</template>

<style scoped>
.rb {
  position: relative;
  display: inline-flex;
}
.rb-btn {
  position: relative;
  width: 30px;
  height: 30px;
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
.rb-btn:hover,
.rb-btn.on {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
  background: var(--theme-field);
}
.rb-ico {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
  transform-origin: 12px 6px;
}
/* 未读时铃铛摇摆 */
.rb-btn.ring .rb-ico {
  animation: rb-ring 2.4s var(--motion) infinite;
}
@keyframes rb-ring {
  0%, 62%, 100% { transform: rotate(0deg); }
  70% { transform: rotate(12deg); }
  78% { transform: rotate(-10deg); }
  86% { transform: rotate(6deg); }
  94% { transform: rotate(-3deg); }
}
.rb-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 9px;
  background: var(--theme-error);
  color: #2a0f0a;
  font-size: 10px;
  font-weight: 700;
  line-height: 16px;
  text-align: center;
  font-family: var(--font-mono);
  animation: rb-pulse 1.8s ease-out infinite;
}
@keyframes rb-pulse {
  0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--theme-error) 60%, transparent); }
  70%, 100% { box-shadow: 0 0 0 7px transparent; }
}
.rb-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: min(320px, 82vw);
  max-height: 380px;
  display: flex;
  flex-direction: column;
  background: var(--theme-paper);
  border: 1px solid var(--theme-line);
  border-radius: var(--radius);
  box-shadow: var(--shadow-panel);
  overflow: hidden;
  z-index: 30;
}
.rb-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  border-bottom: 1px solid var(--theme-line);
}
.rb-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--theme-ink);
}
.rb-all {
  font-size: 11px;
  padding: 2px 8px;
  border: 1px solid var(--theme-line);
  border-radius: 4px;
  background: transparent;
  color: var(--theme-ink-soft);
  cursor: pointer;
}
.rb-all:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.rb-list {
  overflow: auto;
}
.rb-row {
  display: flex;
  gap: 8px;
  padding: 9px 12px;
  border-bottom: 1px solid color-mix(in srgb, var(--theme-line) 55%, transparent);
  cursor: pointer;
  transition: background 0.2s var(--motion);
}
.rb-row:hover {
  background: var(--theme-field);
}
.rb-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-top: 6px;
  flex: none;
  background: var(--theme-line);
}
.rb-dot.on {
  background: var(--theme-accent);
}
.rb-body {
  min-width: 0;
}
.rb-t {
  font-size: 12.5px;
  color: var(--theme-ink);
  font-weight: 600;
}
.rb-row.unread .rb-t {
  color: var(--theme-accent-hover);
}
.rb-c {
  font-size: 12px;
  color: var(--theme-ink-soft);
  line-height: 1.5;
}
.rb-empty {
  padding: 16px 12px;
  font-size: 12px;
  color: var(--theme-muted);
  text-align: center;
}
/* 下拉：淡入 + 轻微下滑 */
.rb-pop-enter-active,
.rb-pop-leave-active {
  transition: opacity 0.2s var(--motion), transform 0.2s var(--motion);
}
.rb-pop-enter-from,
.rb-pop-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
@media (prefers-reduced-motion: reduce) {
  .rb-btn.ring .rb-ico,
  .rb-badge {
    animation: none;
  }
}
</style>
