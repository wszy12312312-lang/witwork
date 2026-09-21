<script setup lang="ts">
import { computed, nextTick, ref, watch, onMounted, onBeforeUnmount } from 'vue';

import { store, saveSettings } from '../lib/store';

// iPhone 18（2026）屏幕规格：6.3 英寸，物理 2622×1206 @3x，比例 19.5:9，458 PPI
// → CSS 逻辑分辨率 402×874。预览按此真实尺寸排版，再等比缩放以适应面板。
const SCREEN_W = 402;
const SCREEN_H = 874;

const props = defineProps<{
  html: string;
  pages?: number;
  words?: number;
  title?: string;
  cursorIndex?: number;
}>();

const THEMES = [
  { key: 'dark', name: '夜间', bg: '#1b1d22', fg: '#d8dbe0' },
  { key: 'sepia', name: '米黄', bg: '#f6efdc', fg: '#3d3529' },
  { key: 'paper', name: '纯白', bg: '#ffffff', fg: '#222222' },
  { key: 'green', name: '护眼', bg: '#dcecd9', fg: '#2f3e2f' },
  { key: 'parch', name: '羊皮', bg: '#e8dcc0', fg: '#4a3b28' },
];
// 预览字体（中文小说常用书体，均为系统字体，无需联网）
const FONT_FAMILIES = [
  { key: 'default', name: '默认', stack: '' },
  { key: 'song', name: '宋体', stack: '"Songti SC", "SimSun", "STSong", serif' },
  { key: 'hei', name: '黑体', stack: '"PingFang SC", "Microsoft YaHei", "Heiti SC", sans-serif' },
  { key: 'kai', name: '楷体', stack: '"Kaiti SC", "KaiTi", "STKaiti", serif' },
  { key: 'fangsong', name: '仿宋', stack: '"FangSong", "STFangsong", "Fangsong SC", serif' },
  { key: 'mono', name: '等宽', stack: 'var(--font-mono)' },
];

// 外观设置来自 app 设置（config），改动即时写回，刷新不丢
const theme = ref(String((store.settings as any)?.preview_theme ?? 'dark'));
const fontFamily = ref(String((store.settings as any)?.preview_font_family ?? 'default'));
const indent = ref(Number((store.settings as any)?.preview_indent ?? 2));
const paraGap = ref(Number((store.settings as any)?.preview_para_gap ?? 8));
// 字号只读（统一跟随 app 编辑器字号）；行距可改，写回 config.editor_line_height
const fontSize = computed(() => store.editorFontSize || 16);
const lineHeight = ref(Number((store.settings as any)?.editor_line_height ?? store.editorLineHeight ?? 1.8));

// 任何外观改动都同步回设置（偏好页可见，刷新保留）
async function syncPrefs(patch: Record<string, unknown>) {
  const cur: Record<string, unknown> = store.settings ? { ...store.settings } : {};
  const merged = { ...cur, ...patch };
  (store as any).settings = merged;
  await saveSettings(patch);
}
watch(theme, (v) => syncPrefs({ preview_theme: v }));
watch(fontFamily, (v) => syncPrefs({ preview_font_family: v }));
watch(indent, (v) => syncPrefs({ preview_indent: v }));
watch(paraGap, (v) => syncPrefs({ preview_para_gap: v }));
watch(lineHeight, (v) => syncPrefs({ editor_line_height: v }));

const themeObj = computed(() => THEMES.find((t) => t.key === theme.value) || THEMES[0]);
const fontStack = computed(
  () => FONT_FAMILIES.find((f) => f.key === fontFamily.value)?.stack || ''
);
const body = ref<HTMLElement | null>(null);

// 等比缩放：以 .phone-viewport 的可用空间为基准，宽高用同一个 scale（绝不变形/拉长）
const viewport = ref<HTMLElement | null>(null);
const scale = ref(1);
let ro: ResizeObserver | null = null;

function updateScale() {
  const el = viewport.value;
  if (!el) return;
  const availW = el.clientWidth || SCREEN_W;
  const availH = el.clientHeight || SCREEN_H;
  const s = Math.min(availW / SCREEN_W, availH / SCREEN_H, 1);
  scale.value = s > 0 ? s : 1;
}

onMounted(() => {
  updateScale();
  window.addEventListener('resize', updateScale);
  if (typeof ResizeObserver !== 'undefined' && viewport.value) {
    ro = new ResizeObserver(updateScale);
    ro.observe(viewport.value);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateScale);
  ro?.disconnect();
  ro = null;
});

watch(
  () => props.cursorIndex,
  async (i) => {
    if (i >= 0) {
      await nextTick();
      const el = body.value;
      if (!el) return;
      const p = el.querySelector(`.pv-p[data-i="${i}"]`);
      if (p) p.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }
);
</script>

<template>
  <div class="phone-wrap">
    <div class="phone-ctrl">
      <select v-model="theme" class="inp">
        <option v-for="t in THEMES" :key="t.key" :value="t.key">{{ t.name }}</option>
      </select>
      <select v-model="fontFamily" class="inp" title="字体">
        <option v-for="f in FONT_FAMILIES" :key="f.key" :value="f.key">{{ f.name }}</option>
      </select>
      <input v-model.number="lineHeight" class="inp" type="number" step="0.1" min="1.2" max="2.6" title="行距" />
      <input v-model.number="indent" class="inp" type="number" min="0" max="4" title="段首缩进(字符)" />
      <input v-model.number="paraGap" class="inp" type="number" min="0" max="24" title="段间距(px)" />
    </div>

    <div class="phone-spec mono">iPhone 18 · 6.3″ · {{ SCREEN_W }}×{{ SCREEN_H }} · 缩放 {{ (scale * 100).toFixed(0) }}%</div>

    <div class="phone-viewport" ref="viewport">
      <div
        class="phone-stage"
        :style="{ width: SCREEN_W * scale + 'px', height: SCREEN_H * scale + 'px' }"
      >
        <div
          class="phone"
          :style="{
            width: SCREEN_W + 'px',
            height: SCREEN_H + 'px',
            transform: `scale(${scale})`,
            fontFamily: fontStack,
            background: themeObj.bg,
            color: themeObj.fg,
          }"
        >
        <div class="phone-island"></div>
        <div class="phone-status">{{ title }}</div>
        <div
          class="phone-body"
          ref="body"
          :style="{
            fontSize: fontSize + 'px',
            lineHeight: lineHeight,
            '--pv-indent': indent + 'em',
            '--pv-gap': paraGap + 'px',
          }"
        >
          <div v-html="html"></div>
        </div>
        <div class="phone-foot">{{ words }} 字 · {{ pages }} 页</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.phone-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
}
.phone-ctrl {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.inp {
  font-size: 12px;
  padding: 3px 6px;
  border: 1px solid var(--theme-line);
  border-radius: 4px;
  background: var(--theme-field);
  color: var(--theme-ink);
}
.phone-spec {
  font-size: 11px;
  color: var(--theme-muted);
  text-align: center;
}
/* 关键：viewport 必须 flex:1 + min-height:0，
 * 否则在 flex 列容器里会被压缩，内部手机被 overflow 裁掉底部（看起来又扁又缺一截）。
 * 它提供确定的高度基准，scale 才能算出完整等比缩放。 */
.phone-viewport {
  flex: 1;
  min-height: 0;
  display: flex;
  justify-content: center;
  align-items: flex-start;
}
.phone-stage {
  position: relative;
  margin: 0 auto;
  overflow: hidden;
}
.phone {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: top left;
  border-radius: 44px; /* iPhone 机身圆角 */
  padding: 40px 18px 14px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 10px 30px rgba(8, 10, 8, 0.25);
}
.phone-island {
  position: absolute;
  top: 11px;
  left: 50%;
  transform: translateX(-50%);
  width: 96px;
  height: 26px;
  border-radius: 13px;
  background: rgba(0, 0, 0, 0.86);
}
.phone-status {
  flex: none;
  font-size: 12px;
  opacity: 0.6;
  text-align: center;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(128, 128, 128, 0.25);
  margin-bottom: 10px;
}
.phone-body {
  flex: 1;
  /* flex 子项默认 min-height:auto，内容会把它撑高而不滚动，
   * 超出部分被机身 overflow:hidden 裁掉 → 表现为"无法向下滑动"。必须置 0。 */
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain; /* 滚到边界不穿透到外层 */
}
.phone-body :deep(p) {
  margin: 0 0 var(--pv-gap, 8px);
  text-indent: var(--pv-indent, 2em);
}
.phone-foot {
  flex: none;
  font-size: 11px;
  opacity: 0.6;
  text-align: center;
  padding-top: 8px;
  border-top: 1px solid rgba(128, 128, 128, 0.25);
  margin-top: 10px;
}
</style>
