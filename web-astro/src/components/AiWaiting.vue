<script setup lang="ts">
/**
 * AI 等待 / 生成中 UI（threeui 设计语言）
 *
 * 取自 threeui 的 UplinkLoader（src/shaders/uplink-loader）：
 *   · 切角面板（clip-path 斜切 + 内外双层描边）
 *   · 四角定位标记（十字角标 .brk）
 *   · 等宽数字读数（大字 + 单位小字 + 霓虹光晕）
 *   · 扫光进度条 + 径向光雾（.haze）
 *   · 骨架微光（等待首字时占位）
 * 配色改用本主题的 accent，因此亮 / 暗 / 棕褐三套主题都能自适应。
 */
import { computed } from 'vue';

const props = defineProps<{
  /** 当前阶段：prepare | connect | generating */
  stage: string;
  /** 已耗时（毫秒） */
  elapsedMs: number;
  /** 是否已收到首个 token（收到后切换到「流式输出中」的表现） */
  hasText?: boolean;
  /** 操作名，如「续写」 */
  opLabel?: string;
}>();

const emit = defineEmits<{ (e: 'stop'): void }>();

const STAGES = [
  { key: 'prepare', label: '准备上下文' },
  { key: 'connect', label: '连接模型' },
  { key: 'generating', label: '生成正文' },
];

const order = computed(() => STAGES.map((s) => s.key));
const currentIndex = computed(() => {
  const i = order.value.indexOf(props.stage);
  return i < 0 ? 0 : i;
});

const seconds = computed(() => (props.elapsedMs / 1000).toFixed(1));

const statusText = computed(() => {
  if (props.hasText) return '正在流式输出…';
  const s = STAGES.find((x) => x.key === props.stage);
  return `思考等待中 · ${s ? s.label : '准备'}…`;
});

function stageState(key: string) {
  const i = order.value.indexOf(key);
  if (i < currentIndex.value) return 'done';
  if (i === currentIndex.value) return props.hasText && key === 'generating' ? 'done' : 'active';
  return 'idle';
}
</script>

<template>
  <div class="tw-plate" role="status" aria-live="polite">
    <div class="tw-plate-in">
      <span class="brk tl" aria-hidden="true"></span>
      <span class="brk tr" aria-hidden="true"></span>
      <span class="brk bl" aria-hidden="true"></span>
      <span class="brk br" aria-hidden="true"></span>

      <div class="tw-head">
        <div class="tw-readout mono">
          <b>{{ seconds }}</b><u>s</u>
        </div>
        <div class="tw-meta">
          <div class="tw-status">{{ statusText }}</div>
          <div class="tw-sub mono">
            {{ opLabel || 'AI' }} · {{ hasText ? '已开始输出' : '等待模型首字' }}
          </div>
        </div>
        <button class="tw-stop" @click="emit('stop')" title="停止生成">■ 停止</button>
      </div>

      <div class="tw-bar">
        <div class="tw-haze" aria-hidden="true"></div>
        <div class="tw-sweep" aria-hidden="true"></div>
      </div>

      <ol class="tw-stages">
        <li v-for="s in STAGES" :key="s.key" :class="stageState(s.key)">
          <span class="tw-dot" aria-hidden="true"></span>{{ s.label }}
        </li>
      </ol>

      <!-- 等首字期间用骨架屏占位，明确告诉用户「在跑，还没出字」 -->
      <div v-if="!hasText" class="tw-skel" aria-hidden="true">
        <span class="ln" style="width: 92%"></span>
        <span class="ln" style="width: 78%"></span>
        <span class="ln" style="width: 86%"></span>
        <span class="ln" style="width: 64%"></span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tw-plate {
  --chamfer: 12px;
  background: color-mix(in srgb, var(--theme-accent) 34%, transparent);
  clip-path: polygon(
    var(--chamfer) 0,
    100% 0,
    100% calc(100% - var(--chamfer)),
    calc(100% - var(--chamfer)) 100%,
    0 100%,
    0 var(--chamfer)
  );
  padding: 1.2px;
}
.tw-plate-in {
  position: relative;
  padding: 14px 16px 12px;
  background: var(--theme-field);
  clip-path: polygon(
    calc(var(--chamfer) - 0.6px) 0,
    100% 0,
    100% calc(100% - var(--chamfer) + 0.6px),
    calc(100% - var(--chamfer) + 0.6px) 100%,
    0 100%,
    0 calc(var(--chamfer) - 0.6px)
  );
}

/* 四角定位标记（threeui .brk） */
.brk {
  position: absolute;
  width: 9px;
  height: 9px;
  pointer-events: none;
}
.brk::before,
.brk::after {
  content: '';
  position: absolute;
  background: var(--theme-accent);
  opacity: 0.75;
}
.brk::before { width: 9px; height: 1.2px; }
.brk::after { width: 1.2px; height: 9px; }
.brk.tl { left: 6px; top: 6px; }
.brk.tl::before { left: 0; top: 0; }
.brk.tl::after { left: 0; top: 0; }
.brk.tr { right: 6px; top: 6px; }
.brk.tr::before { right: 0; top: 0; }
.brk.tr::after { right: 0; top: 0; }
.brk.bl { left: 6px; bottom: 6px; }
.brk.bl::before { left: 0; bottom: 0; }
.brk.bl::after { left: 0; bottom: 0; }
.brk.br { right: 6px; bottom: 6px; }
.brk.br::before { right: 0; bottom: 0; }
.brk.br::after { right: 0; bottom: 0; }

.tw-head {
  display: flex;
  align-items: center;
  gap: 14px;
}

/* 等宽读数（threeui .readout） */
.tw-readout {
  line-height: 1;
  white-space: nowrap;
  color: var(--theme-accent);
  text-shadow: 0 0 6px color-mix(in srgb, var(--theme-accent) 45%, transparent);
  animation: neon 4.3s steps(1, end) infinite;
  min-width: 74px;
}
.tw-readout b {
  font-size: 30px;
  font-weight: 300;
  letter-spacing: 1.4px;
}
.tw-readout u {
  font-size: 13px;
  text-decoration: none;
  opacity: 0.7;
  margin-left: 3px;
}
@keyframes neon {
  0%, 40% { opacity: 1; }
  41% { opacity: 0.6; }
  42% { opacity: 1; }
  70% { opacity: 1; }
  70.5% { opacity: 0.5; }
  71.5% { opacity: 1; }
}

.tw-meta {
  flex: 1;
  min-width: 0;
}
.tw-status {
  font-size: 13px;
  color: var(--theme-ink);
}
.tw-sub {
  font-size: 11.5px;
  color: var(--theme-muted);
  margin-top: 2px;
}

.tw-stop {
  flex: none;
  font-size: 12px;
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--theme-error);
  color: var(--theme-error);
  background: transparent;
}
.tw-stop:hover {
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
}

/* 进度条：底槽 + 扫光 + 径向光雾（threeui .haze） */
.tw-bar {
  position: relative;
  height: 3px;
  margin: 12px 0 10px;
  border-radius: 2px;
  overflow: hidden;
  background: color-mix(in srgb, var(--theme-line) 70%, transparent);
}
.tw-sweep {
  position: absolute;
  inset: 0;
  width: 42%;
  background: linear-gradient(
    90deg,
    transparent,
    color-mix(in srgb, var(--theme-accent) 85%, transparent),
    transparent
  );
  animation: sweep 1.35s var(--motion) infinite;
}
@keyframes sweep {
  0% { transform: translateX(-110%); }
  100% { transform: translateX(320%); }
}
.tw-haze {
  position: absolute;
  left: 0;
  top: 50%;
  width: 120px;
  height: 40px;
  transform: translate(-40px, -20px);
  background: radial-gradient(
    ellipse 50% 50% at center,
    color-mix(in srgb, var(--theme-accent) 26%, transparent) 0%,
    color-mix(in srgb, var(--theme-accent) 12%, transparent) 45%,
    transparent 100%
  );
  filter: blur(5px);
  animation: sweep 1.35s var(--motion) infinite;
}

.tw-stages {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  list-style: none;
  margin: 0 0 10px;
  padding: 0;
  font-size: 11.5px;
}
.tw-stages li {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--theme-muted);
}
.tw-stages li.active { color: var(--theme-ink); }
.tw-stages li.done { color: var(--theme-accent); }
.tw-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.45;
}
.tw-stages li.active .tw-dot {
  opacity: 1;
  animation: pulse 1s var(--motion) infinite;
}
.tw-stages li.done .tw-dot { opacity: 1; }
@keyframes pulse {
  50% { opacity: 0.3; }
}

/* 骨架微光 */
.tw-skel {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.tw-skel .ln {
  height: 9px;
  border-radius: 4px;
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--theme-line) 55%, transparent) 0%,
    color-mix(in srgb, var(--theme-line) 90%, transparent) 38%,
    color-mix(in srgb, var(--theme-line) 55%, transparent) 76%
  );
  background-size: 220% 100%;
  animation: shimmer 1.5s linear infinite;
}
@keyframes shimmer {
  0% { background-position: 120% 0; }
  100% { background-position: -120% 0; }
}
</style>
