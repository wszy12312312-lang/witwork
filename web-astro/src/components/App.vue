<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch, computed } from 'vue';
import * as THREE from 'three';
import { store, bootstrap, effectiveTheme, saveSettings } from '../lib/store';
import TreePanel from './TreePanel.vue';
import EditorPanel from './EditorPanel.vue';
import Settings from './Settings.vue';
import AiSession from './AiSession.vue';
import RareBell from './RareBell.vue';
import { vMagnetRail } from '../lib/rare';

let renderer: THREE.WebGLRenderer | null = null;
let raf = 0;
let resizeObserver: ResizeObserver | null = null;

// 档案体半径与取景留白（>1 表示图案四周留白，避免贴边/被裁切）
const ARCHIVE_RADIUS = 2.15;
const ARCHIVE_SCALE = 3; // 档案体放大 3 倍（用户要求）
const FIT_MARGIN = 1.45;
const MAX_WIDEN = 1.3; // 极端竖屏最多拉远到 1.3 倍，避免图案大小跳变

const showSettings = ref(false);

// 布局：A=标准（目录 320px） / B=紧凑（目录 240px，编辑器更宽）；AI 侧栏按 aiPanelSide 停靠左/右
const workbenchStyle = computed(() => {
  const tree = store.layoutScheme === 'B' ? '240px' : '320px';
  if (store.aiOpen) {
    return store.aiPanelSide === 'left'
      ? { gridTemplateColumns: `380px ${tree} 1fr` }
      : { gridTemplateColumns: `${tree} 1fr 380px` };
  }
  return { gridTemplateColumns: `${tree} 1fr` };
});

// 主题写到 <html>，使 body 与后代都能取到 [data-theme] 覆盖的调色板。
// 注意：不能用 immediate，否则 Astro 静态构建的 SSR 阶段会执行到 document（服务端未定义）→ ReferenceError。
function applyTheme(t: string) {
  if (typeof document === 'undefined') return;
  document.documentElement.setAttribute('data-theme', t || 'dark');
}
const themeAttr = computed(() => effectiveTheme());
watch(() => store.theme, () => applyTheme(effectiveTheme()));

// HUD 功能面板开关（不再与莱茵终端主题耦合，仅由 hud_enabled 控制）
const hudOn = computed(() => store.hudEnabled);
async function setHud(on: boolean) {
  await saveSettings({ hud_enabled: on });
}

// 暖色「三维档案终端」背景：缓慢自转的线框档案体，杏金描边。
function initScene() {
  const stage = document.getElementById('stage');
  if (!stage) return;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.set(0, 0, 6.2);

  renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.domElement.style.cssText = 'width:100%;height:100%;display:block';
  stage.appendChild(renderer.domElement);

  const group = new THREE.Group();
  // 几何放大 ARCHIVE_SCALE 倍；相机距离仍按基准 ARCHIVE_RADIUS 计算，
  // 因此图案在画面中确实变大 3 倍（会超出边界，作为背景装饰）。
  const geo = new THREE.IcosahedronGeometry(ARCHIVE_RADIUS * ARCHIVE_SCALE, 1);
  const wire = new THREE.LineSegments(
    new THREE.WireframeGeometry(geo),
    new THREE.LineBasicMaterial({ color: 0xa67d48, transparent: true, opacity: 0.5 })
  );
  const inner = new THREE.Mesh(
    geo,
    new THREE.MeshBasicMaterial({ color: 0xcbb397, wireframe: true, transparent: true, opacity: 0.12 })
  );
  group.add(wire, inner);
  scene.add(group);

  // 视口自适应：档案体始终居中。
  // 关键：常见比例（横屏/方形）下相机距离完全固定 → 图案大小稳定、不会随窗口"变大变小"；
  // 仅极端竖屏才小幅拉远避免左右裁切，并限制最大幅度（MAX_WIDEN）避免缩放跳变。
  const fitCamera = (w: number, h: number) => {
    const aspect = w / h || 1;
    camera.aspect = aspect;
    const halfFov = (camera.fov * Math.PI) / 360;
    const fit = (ARCHIVE_RADIUS * FIT_MARGIN) / Math.tan(halfFov);
    const widen = aspect >= 1 ? 1 : Math.min(1 / aspect, MAX_WIDEN);
    camera.position.set(0, 0, fit * widen);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
  };

  const resize = () => {
    const w = stage.clientWidth || window.innerWidth;
    const h = stage.clientHeight || window.innerHeight;
    if (!w || !h) return;
    renderer!.setSize(w, h, false);
    fitCamera(w, h);
  };
  resize();
  window.addEventListener('resize', resize);
  // 用 ResizeObserver 兜住布局变化（侧栏开合、布局 A/B 切换等）导致的尺寸变化
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(stage);
  }

  const animate = () => {
    raf = requestAnimationFrame(animate);
    group.rotation.y += 0.0016;
    group.rotation.x += 0.0006;
    renderer!.render(scene, camera);
  };
  animate();
}

onMounted(async () => {
  applyTheme(effectiveTheme());
  // 3D 背景失败绝不能拖垮整个应用：initScene 若抛错（如无 WebGL / 显卡驱动异常），
  // 以前会中断 onMounted，导致 bootstrap 不执行 → 主题、HUD、数据全不加载（近似空白页）。
  // 另外支持 ?nofx=1 主动跳过 3D（低配设备 / 自动化截图）。
  const noFx = typeof location !== 'undefined' && /[?&]nofx=1/.test(location.search);
  if (!noFx) {
    try {
      initScene();
    } catch (e) {
      console.warn('[WitWork] 3D 背景初始化失败，已降级为纯色背景：', e);
    }
  }
  try {
    await bootstrap();
  } catch {
    /* 连接失败已在 store.connected 标记 */
  }
});

onBeforeUnmount(() => {
  cancelAnimationFrame(raf);
  resizeObserver?.disconnect();
  resizeObserver = null;
  renderer?.dispose();
});
</script>

<template>
  <div
    class="shell"
    :data-theme="themeAttr"
    :style="{
      '--editor-font-size': store.editorFontSize + 'px',
      '--editor-line-height': String(store.editorLineHeight),
      '--editor-page-width': store.editorPageWidth + 'px',
      '--topbar-alpha': store.topbarAlpha + '%',
    }"
  >
    <header class="topbar">
      <div class="brand mono" title="万维文 AI 写作：汇万千思路，写一纸文章。">万维文 · WITWORK</div>
      <div class="top-actions" v-magnet-rail="{ selector: 'button', strength: 5, scale: 1.06 }">
        <RareBell />
        <button class="tb" :class="{ on: hudOn }" title="功能面板" @click="setHud(!hudOn)">终端</button>
        <button class="tb" :class="{ on: store.aiOpen }" @click="store.aiOpen = !store.aiOpen">AI 助手</button>
        <button class="tb" @click="showSettings = true">设置</button>
        <div class="status" :class="{ on: store.connected }">
          <span class="dot"></span>
          <span>{{ store.connected ? '后端已连接' : '后端未连接（请先启动 FastAPI:127.0.0.1:8723）' }}</span>
        </div>
      </div>
    </header>

    <section class="work-grid" :style="workbenchStyle">
      <TreePanel />
      <EditorPanel />
      <aside v-if="store.aiOpen" class="ai-dock" :style="{ order: store.aiPanelSide === 'left' ? -1 : 1 }">
        <AiSession @close="store.aiOpen = false" />
      </aside>
    </section>

    <p v-if="store.error" class="err mono">{{ store.error }}</p>

    <Transition name="drawer">
      <Settings v-if="showSettings" @close="showSettings = false" />
    </Transition>
  </div>
</template>

<style scoped>
.shell {
  position: fixed;
  top: 0;
  left: 0;
  /* 整体放大：width/height 反向除以 --ui-scale，使 scale 后仍精确铺满视口 */
  width: calc(100% / var(--ui-scale, 1));
  height: calc(100% / var(--ui-scale, 1));
  transform: scale(var(--ui-scale, 1));
  transform-origin: top left;
  display: flex;
  flex-direction: column;
  z-index: 2;
}
.topbar {
  position: relative;
  /* 抬到各抽屉(z5-16)之上，使铃铛下拉不被面板遮住；仍低于设置抽屉(z40) */
  z-index: 25;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 22px;
  border-bottom: 1px solid color-mix(in srgb, var(--theme-line) 80%, transparent);
  /* 顶栏操作层：可变透明度（--topbar-alpha 由设置 topbar_alpha 驱动，所有预设通用）+ 背景模糊 */
  background: color-mix(in srgb, var(--theme-paper) var(--topbar-alpha, 78%), transparent);
  backdrop-filter: blur(12px) saturate(1.15);
  -webkit-backdrop-filter: blur(12px) saturate(1.15);
}
.tb.terminal {
  font-family: var(--font-mono);
  letter-spacing: 0.06em;
}
.tb.terminal.on {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
  background: color-mix(in srgb, var(--theme-accent) 14%, transparent);
}
.brand {
  font-size: 15px;
  letter-spacing: 0.16em;
}
.top-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}
.tb {
  font-size: 12px;
  padding: 5px 12px;
  border: 1px solid var(--theme-line);
  border-radius: 4px;
  background: transparent;
  color: var(--theme-ink-soft);
  cursor: pointer;
  transition: all 0.2s var(--motion);
}
.tb:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
  background: var(--theme-field);
}
.tb.on {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
  background: var(--theme-field);
}
.ai-dock {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--theme-panel) var(--panel-alpha), transparent);
  overflow: hidden;
}
.status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--theme-muted);
  font-family: var(--font-mono);
}
.status .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--theme-error);
  transition: background 0.3s var(--motion);
}
.status.on .dot {
  background: var(--theme-success);
}
/* 注意：类名不能叫 .workbench（历史上会与全屏 absolute 浮层撞车）。改名 work-grid。 */
.work-grid {
  flex: 1;
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
  padding: 18px 22px;
  min-height: 0;
}
.err {
  color: var(--theme-error);
  padding: 0 22px 16px;
  font-size: 12px;
  font-family: var(--font-mono);
}
/* GitHub 风格抽屉：遮罩淡入淡出，面板自身从右侧滑入 */
.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 0.26s var(--motion);
}
.drawer-enter-active .set-drawer,
.drawer-leave-active .set-drawer {
  transition: transform 0.3s var(--motion);
}
.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}
.drawer-enter-from .set-drawer,
.drawer-leave-to .set-drawer {
  transform: translateX(100%);
}
@media (max-width: 760px) {
  .work-grid {
    grid-template-columns: 1fr;
  }
}
</style>
