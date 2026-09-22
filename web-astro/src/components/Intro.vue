<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue';

/**
 * 启动动画覆盖层（万维文 WitWork）
 *
 * 视觉语言取自 threeui / DesignCode：细网格、暖杏金辉光、扫线、四角括线、
 * 等宽微标签；落到本项目就是「暖色档案终端」的调性。
 *
 * 职责边界：本组件只负责「画面」，不碰 Three.js。棱球的放大与旋转由 App.vue
 * 的单一动画循环驱动（保证旋转角/角速度/方向在放大→背景的交接处绝对连续）。
 * 组件通过 phase 属性表现四个阶段：
 *   idle  初始：三个大字 + 动态背景（网格/辉光/扫线）；大字后方就是那只
 *         从待机起就在缓慢自转的 WebGL 棱球（App.vue 驱动）
 *   morph 点击后：大字旋转坍缩；棱球就是待机那只，持续自转不重置
 *   grow  放大：同一只棱球平滑放大成为背景（由 App.vue 驱动）
 *   ui    就位：操作层 UI 渐显，覆盖层整体淡出
 */
const props = defineProps<{ phase: 'idle' | 'morph' | 'grow' | 'ui' | 'done' }>();
const emit = defineEmits<{ (e: 'launch'): void; (e: 'skip'): void }>();

const chars = ['万', '维', '文'];

// 键盘：Enter / 空格启动，Esc 跳过（桌面端体验）
function onKey(ev: KeyboardEvent) {
  if (props.phase !== 'idle') return;
  if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'Spacebar') {
    ev.preventDefault();
    emit('launch');
  } else if (ev.key === 'Escape') {
    emit('skip');
  }
}
if (typeof window !== 'undefined') {
  // 只在整个页面存活期内挂一次，卸载时摘掉，避免残留监听
  onMounted(() => window.addEventListener('keydown', onKey));
  onBeforeUnmount(() => window.removeEventListener('keydown', onKey));
}
</script>

<template>
  <div class="intro" :data-phase="phase" aria-label="万维文启动画面">
    <!-- ① 底色交给 body（同一主题色，data-theme 预置）；paper 本身保持透明，
         让 WebGL 棱球从待机起就透出在大字后方。保留元素与背景值供自动化验收
         读取主题底色（getComputedStyle 不受 opacity 影响）。 -->
    <div class="paper"></div>

    <!-- ② 装饰层：细网格 + 暖杏金辉光 + 扫线 -->
    <div class="deco" aria-hidden="true">
      <div class="grid"></div>
      <div class="glow g1"></div>
      <div class="glow g2"></div>
      <div class="glow g3"></div>
      <div class="scan"></div>
      <div class="vignette"></div>
    </div>

    <!-- ③ 四角括线 + 等宽微标签（threeui 式仪表感） -->
    <div class="corner tl" aria-hidden="true"><i></i><span class="mono">WITWORK // BOOT</span></div>
    <div class="corner tr" aria-hidden="true"><span class="mono">LOCAL-FIRST</span><i></i></div>
    <div class="corner bl" aria-hidden="true"><i></i><span class="mono">汇万千思路 · 写一纸文章</span></div>
    <div class="corner br" aria-hidden="true"><span class="mono">v1.0</span><i></i></div>

    <!-- ④ 主视觉：三个中文大字（大字后方就是那只从待机起就在自转的 WebGL 棱球） -->
    <div class="logo" role="img" aria-label="万维文">
      <span
        v-for="(c, i) in chars"
        :key="i"
        class="ch"
        :style="{ '--i': String(i) }"
        >{{ c }}</span
      >
    </div>

    <!-- ⑤ 底部：启动按钮 + 说明 -->
    <div class="foot">
      <button class="launch" type="button" @click="emit('launch')">
        <span class="ln-main">点击启动</span>
        <span class="ln-sub mono">CLICK TO LAUNCH</span>
        <span class="ln-arrow" aria-hidden="true">›</span>
      </button>
      <p class="hint mono">按下 Enter 或点击上方按钮进入 · 汇万千思路，写一纸文章</p>
    </div>

    <!-- ⑥ 跳过（直接进入软件，不播放动画） -->
    <button class="skip mono" type="button" @click="emit('skip')">跳过 ›</button>
  </div>
</template>

<style scoped>
.intro {
  position: fixed;
  inset: 0;
  z-index: 9000;
  overflow: hidden;
  display: grid;
  place-items: center;
  /* 覆盖层整体淡出（phase=ui 时触发），配合 App.vue 的操作层渐显 */
  transition: opacity 0.7s var(--motion);
}
.intro[data-phase='ui'] {
  opacity: 0;
  pointer-events: none;
}

/* ① 底色：交给 body（同一主题色）。paper 保持透明 → 待机的 WebGL 棱球
 *    能从大字后方透出（它就是后续放大成背景的那只球，不重新放置）。
 *    元素与 background 值保留，供自动化验收读取主题底色。 */
.paper {
  position: absolute;
  inset: 0;
  background: var(--theme-paper);
  opacity: 0;
  pointer-events: none;
}

/* ② 装饰层 */
.deco {
  position: absolute;
  inset: 0;
  transition: opacity 0.5s var(--motion);
}
.intro[data-phase='morph'] .deco,
.intro[data-phase='grow'] .deco,
.intro[data-phase='ui'] .deco {
  opacity: 0;
}
.grid {
  position: absolute;
  inset: -40%;
  background-image:
    linear-gradient(to right, color-mix(in srgb, var(--theme-accent) 13%, transparent) 1px, transparent 1px),
    linear-gradient(to bottom, color-mix(in srgb, var(--theme-accent) 13%, transparent) 1px, transparent 1px);
  background-size: 62px 62px;
  opacity: 0.5;
  animation: gridDrift 36s linear infinite;
  mask-image: radial-gradient(circle at 50% 50%, #000 0%, rgba(0, 0, 0, 0.35) 48%, transparent 72%);
  -webkit-mask-image: radial-gradient(circle at 50% 50%, #000 0%, rgba(0, 0, 0, 0.35) 48%, transparent 72%);
}
@keyframes gridDrift {
  from {
    transform: translate3d(0, 0, 0);
  }
  to {
    transform: translate3d(62px, 62px, 0);
  }
}
.glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  opacity: 0.5;
}
.g1 {
  width: 46vmax;
  height: 46vmax;
  left: 50%;
  top: 50%;
  margin: -23vmax 0 0 -23vmax;
  background: radial-gradient(circle, color-mix(in srgb, var(--theme-accent) 34%, transparent), transparent 66%);
  animation: breathe 7.5s ease-in-out infinite;
}
.g2 {
  width: 30vmax;
  height: 30vmax;
  left: 12%;
  bottom: 6%;
  background: radial-gradient(circle, color-mix(in srgb, var(--theme-accent-hover) 22%, transparent), transparent 68%);
  animation: float1 17s ease-in-out infinite;
}
.g3 {
  width: 26vmax;
  height: 26vmax;
  right: 8%;
  top: 10%;
  background: radial-gradient(circle, color-mix(in srgb, var(--theme-accent-strong) 24%, transparent), transparent 68%);
  animation: float2 21s ease-in-out infinite;
}
@keyframes breathe {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.42;
  }
  50% {
    transform: scale(1.14);
    opacity: 0.6;
  }
}
@keyframes float1 {
  0%,
  100% {
    transform: translate3d(0, 0, 0);
  }
  50% {
    transform: translate3d(6vmax, -4vmax, 0);
  }
}
@keyframes float2 {
  0%,
  100% {
    transform: translate3d(0, 0, 0);
  }
  50% {
    transform: translate3d(-5vmax, 5vmax, 0);
  }
}
/* 扫线：threeui 式的垂直扫描光带 */
.scan {
  position: absolute;
  left: 0;
  right: 0;
  height: 34%;
  background: linear-gradient(
    to bottom,
    transparent,
    color-mix(in srgb, var(--theme-accent) 9%, transparent) 42%,
    color-mix(in srgb, var(--theme-accent) 16%, transparent) 50%,
    color-mix(in srgb, var(--theme-accent) 9%, transparent) 58%,
    transparent
  );
  animation: scanMove 6.4s cubic-bezier(0.45, 0, 0.55, 1) infinite;
}
@keyframes scanMove {
  0% {
    top: -38%;
    opacity: 0;
  }
  12% {
    opacity: 1;
  }
  88% {
    opacity: 1;
  }
  100% {
    top: 104%;
    opacity: 0;
  }
}
.vignette {
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 50% 48%, transparent 34%, color-mix(in srgb, var(--theme-paper) 78%, transparent) 86%);
}

/* ③ 四角括线 */
.corner {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--theme-muted);
  font-size: 10.5px;
  letter-spacing: 0.18em;
  opacity: 0.78;
  transition: opacity 0.4s var(--motion);
}
/* 四角括线：点击后与其它装饰一起退场。
 * 原先只隐藏 morph 阶段 → grow 阶段又淡回来，产生一次多余闪烁；
 * 而且会与软件自身的顶栏在交叉淡入时重叠，留下残影。 */
.intro[data-phase='morph'] .corner,
.intro[data-phase='grow'] .corner,
.intro[data-phase='ui'] .corner {
  opacity: 0;
}
.corner i {
  display: block;
  width: 26px;
  height: 26px;
  border: 1px solid color-mix(in srgb, var(--theme-accent) 55%, transparent);
}
.corner.tl {
  left: 22px;
  top: 22px;
}
.corner.tl i {
  border-right: 0;
  border-bottom: 0;
}
.corner.tr {
  right: 22px;
  top: 22px;
  flex-direction: row-reverse;
}
.corner.tr i {
  border-left: 0;
  border-bottom: 0;
}
.corner.bl {
  left: 22px;
  bottom: 22px;
}
.corner.bl i {
  border-right: 0;
  border-top: 0;
}
.corner.br {
  right: 22px;
  bottom: 22px;
  flex-direction: row-reverse;
}
.corner.br i {
  border-left: 0;
  border-top: 0;
}

/* ④ 主视觉大字（大字后方即待机起就在自转的 WebGL 棱球，见 App.vue） */
.logo {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.04em;
  perspective: 1100px;
  perspective-origin: 50% 50%;
  z-index: 1;
}
.ch {
  display: block;
  font-size: clamp(58px, 12.5vw, 168px);
  font-weight: 800;
  line-height: 1.12;
  letter-spacing: 0.02em;
  color: var(--theme-ink);
  transform-style: preserve-3d;
  will-change: transform, opacity, filter;
  text-shadow:
    0 0 34px color-mix(in srgb, var(--theme-accent) 38%, transparent),
    0 0 90px color-mix(in srgb, var(--theme-accent) 18%, transparent);
  animation: chIn 0.9s var(--motion) backwards;
  animation-delay: calc(var(--i) * 0.11s);
  transition:
    transform 1s cubic-bezier(0.55, 0.06, 0.3, 1),
    opacity 0.68s var(--motion),
    filter 0.68s var(--motion);
  transition-delay: calc(var(--i) * 0.075s);
}
@keyframes chIn {
  from {
    opacity: 0;
    transform: translateY(22px) scale(0.94);
    filter: blur(12px);
  }
  to {
    opacity: 1;
    transform: none;
    filter: blur(0);
  }
}
/* 点击后：各自旋转数圈、缩向中心并虚化 —— 视觉上「旋进」成为棱球 */
.intro[data-phase='morph'] .ch,
.intro[data-phase='grow'] .ch,
.intro[data-phase='ui'] .ch {
  transform: rotateY(1080deg) rotateX(-360deg) scale(0.045);
  opacity: 0;
  filter: blur(10px);
}

/* ⑥ 底部启动控件 */
.foot {
  position: absolute;
  left: 50%;
  bottom: 12vh;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  z-index: 1;
  transition:
    opacity 0.36s var(--motion),
    transform 0.36s var(--motion);
}
.intro[data-phase='morph'] .foot,
.intro[data-phase='grow'] .foot,
.intro[data-phase='ui'] .foot {
  opacity: 0;
  transform: translateX(-50%) translateY(14px);
  pointer-events: none;
}
.launch {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 14px;
  padding: 13px 30px 13px 28px;
  border: 1px solid color-mix(in srgb, var(--theme-accent) 62%, transparent);
  border-radius: 4px;
  background: color-mix(in srgb, var(--theme-accent) 10%, transparent);
  color: var(--theme-ink);
  cursor: pointer;
  overflow: hidden;
  transition:
    background 0.25s var(--motion),
    border-color 0.25s var(--motion),
    transform 0.25s var(--motion),
    box-shadow 0.25s var(--motion);
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--theme-accent) 12%, transparent) inset,
    0 10px 34px color-mix(in srgb, var(--theme-accent) 16%, transparent);
  animation: riseIn 0.8s var(--motion) 0.5s backwards;
}
@keyframes riseIn {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
/* 掠过式高光（threeui 的扫光按钮） */
.launch::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  width: 42%;
  left: -60%;
  background: linear-gradient(
    100deg,
    transparent,
    color-mix(in srgb, var(--theme-accent-hover) 26%, transparent),
    transparent
  );
  animation: sweep 3.4s cubic-bezier(0.5, 0, 0.5, 1) infinite;
}
@keyframes sweep {
  0% {
    left: -60%;
  }
  55%,
  100% {
    left: 130%;
  }
}
.launch:hover {
  background: color-mix(in srgb, var(--theme-accent) 20%, transparent);
  border-color: var(--theme-accent);
  transform: translateY(-2px);
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--theme-accent) 26%, transparent) inset,
    0 14px 40px color-mix(in srgb, var(--theme-accent) 26%, transparent);
}
.launch:active {
  transform: translateY(0) scale(0.985);
}
.ln-main {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.24em;
}
.ln-sub {
  font-size: 10.5px;
  letter-spacing: 0.22em;
  color: color-mix(in srgb, var(--theme-ink) 62%, transparent);
}
.ln-arrow {
  font-size: 20px;
  line-height: 1;
  color: var(--theme-accent);
  transition: transform 0.25s var(--motion);
}
.launch:hover .ln-arrow {
  transform: translateX(5px);
}
.hint {
  margin: 0;
  font-size: 10.5px;
  letter-spacing: 0.16em;
  color: var(--theme-muted);
  opacity: 0.82;
  animation: riseIn 0.8s var(--motion) 0.68s backwards;
}

/* ⑦ 跳过 —— 注意 bottom 要避开右下角括线标签（原先两者都在 22px 处重叠） */
.skip {
  position: absolute;
  right: 22px;
  bottom: 60px;
  padding: 5px 12px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--theme-muted);
  font-size: 11px;
  letter-spacing: 0.16em;
  cursor: pointer;
  z-index: 2;
  transition: all 0.22s var(--motion);
}
.skip:hover {
  color: var(--theme-accent-hover);
  border-color: color-mix(in srgb, var(--theme-accent) 55%, transparent);
  background: color-mix(in srgb, var(--theme-accent) 10%, transparent);
}
.intro[data-phase='morph'] .skip,
.intro[data-phase='grow'] .skip,
.intro[data-phase='ui'] .skip {
  opacity: 0;
  pointer-events: none;
}

/* 窄屏：跳过按钮不与底部提示重叠 */
@media (max-width: 620px) {
  .corner.bl {
    display: none;
  }
  .foot {
    bottom: 15vh;
    width: 100%;
    padding: 0 18px;
  }
  .launch {
    width: 100%;
    justify-content: center;
  }
  .hint {
    text-align: center;
    line-height: 1.6;
  }
}

/* 无障碍：降低动效时停掉所有循环动画（App.vue 通常已直接跳过整个启动动画） */
@media (prefers-reduced-motion: reduce) {
  .grid,
  .glow,
  .scan,
  .launch::after,
  .ch {
    animation: none !important;
  }
}
</style>
