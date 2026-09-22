<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch, computed } from 'vue';
import * as THREE from 'three';
import { store, bootstrap, effectiveTheme, cacheTheme, saveSettings } from '../lib/store';
import TreePanel from './TreePanel.vue';
import EditorPanel from './EditorPanel.vue';
import Settings from './Settings.vue';
import AiSession from './AiSession.vue';
import RareBell from './RareBell.vue';
import Intro from './Intro.vue';
import { vMagnetRail } from '../lib/rare';

let renderer: THREE.WebGLRenderer | null = null;
let raf = 0;
let resizeObserver: ResizeObserver | null = null;
let onResize: (() => void) | null = null;

// 3D 场景引用：启动动画与软件背景**共用同一个 group / 材质**，
// 这样「放大中的棱球」和「背景棱球」本来就是同一个对象，天然不会跳变。
let scene3d: THREE.Scene | null = null;
let camera3d: THREE.PerspectiveCamera | null = null;
let group3d: THREE.Group | null = null;
let wireMat: THREE.LineBasicMaterial | null = null;
let innerMat: THREE.MeshBasicMaterial | null = null;
// 环绕轨道粒子：共用一份材质（便于统一控制不透明度），两圈粒子环绕棱球公转
let orbitMat: THREE.PointsMaterial | null = null;
let orbitRings: THREE.Object3D[] = [];

// 档案体半径与取景留白（>1 表示图案四周留白，避免贴边/被裁切）
const ARCHIVE_RADIUS = 2.15;
const ARCHIVE_SCALE = 3; // 档案体放大 3 倍（用户要求）
const FIT_MARGIN = 1.45;
const MAX_WIDEN = 1.3; // 极端竖屏最多拉远到 1.3 倍，避免图案大小跳变

// 背景态的不透明度：线框棱球停在 BG_WIRE_O；内部小球在放大阶段被移除，背景态不含内层 → 0
const BG_WIRE_O = 0.5;
const BG_INNER_O = 0;
// 环绕轨道粒子的不透明度：待机/坍缩时更亮（衬托大字后方的球），放大后收束为背景点缀
const BG_ORBIT_O = 0.5;
const INTRO_ORBIT_O = 1;
// 待机/坍缩阶段的棱球不透明度：**待机即此值**（球从一开始就在大字后方可见），
// 全程没有淡入——同一只球直接放大成背景，不存在「重新放置一只新球」。
const INTRO_WIRE_O = 0.92;
const INTRO_INNER_O = 0.24;

/* ==================== 启动动画时间轴 ====================
 * 旋转连续性（需求核心）：全场景只有一组自转角累加器 spinX / spinY，
 * 任何阶段都不重置、不做取模；
 *   角速度 = 背景基准速度
 *          + velProfile(t)      × 点击额外速度
 *          + growSpinProfile(t) × 放大额外速度
 * 两条额外速度剖面都在各自区间的两端**取值为 0、斜率也为 0**：
 *   · velProfile 在 t = T_VEL_DOWN 平滑归零，而 T_GROW_START === T_VEL_DOWN；
 *   · growSpinProfile 在放大区间的起点与终点都归零。
 * 因此「放大开始」「放大结束进入背景」两个瞬间，角速度都严格等于背景角速度，
 * 方向也完全一致 → 角度 / 速度 / 方向全程连贯无跳变。
 */
// 背景转速提高（用户反馈「字后面的球转得太慢」）：0.096 → 0.3 rad/s（≈17°/s）。
const BG_VEL_Y = 0.3; // rad/s 背景基准自转（≈17°/s，约 21s 一圈）
const BG_VEL_X = 0.11; // rad/s
const SPIN_EXTRA_Y = 4.4; // rad/s 点击瞬间叠加的高速自转
const SPIN_EXTRA_X = 1.5;
// 放大阶段的额外自转（用户反馈「放大时旋转不明显」）：鼓形剖面，两端严格归零。
// 峰值叠加在背景之上（合计 ≈1.9 rad/s ≈109°/s），1.54s 的放大过程因此多转 ≈88°，
// 落位瞬间又恰好收回背景速度 —— 既看得见「边放大边旋转」，又不产生速度突跳。
const GROW_SPIN_Y = 1.6; // rad/s
const GROW_SPIN_X = 0.6; // rad/s
// 环绕轨道粒子的公转角速度（相对棱球自身，两圈反向 → 观感像轨道）
const ORBIT_VEL_A = 0.95; // rad/s 内圈
const ORBIT_VEL_B = -0.62; // rad/s 外圈（反向）

const T_VEL_UP = 0.34; // 0 → 高速
const T_VEL_HOLD = 0.8; // 维持高速
const T_VEL_DOWN = 1.06; // 平滑回落，结束时恰好等于背景速度
const T_GROW_START = 1.06; // 开始放大（此刻角速度已 == 背景速度）
const T_GROW_END = 2.6; // 放大到位，棱球成为背景
const T_UI = 2.6; // 操作层开始渐显
const T_DONE = 3.36; // 覆盖层移除

// 棱球起始缩放：S0 时其视觉直径 ≈ 视口高度的 20.7%（竖屏由相机拉远补偿）。
// 待机时这只球就在「万维文」大字后方以该尺寸缓慢自转，点击后同一只球直接放大成背景。
const S0 = 0.1;

// 测试钩子开关（?introdebug=1）：暴露每帧的旋转/缩放状态，供自动化量化验收
const introDebug =
  typeof location !== 'undefined' && /[?&]introdebug=1/.test(location.search);

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
const smoothstep = (a: number, b: number, x: number) => {
  const t = clamp01((x - a) / (b - a));
  return t * t * (3 - 2 * t);
};
const easeInOutSine = (t: number) => -(Math.cos(Math.PI * t) - 1) / 2;

/** 额外角速度剖面：加速 → 保持 → 平滑归零（归零后角速度恒等于背景速度）。 */
function velProfile(t: number): number {
  if (t < 0) return 0;
  if (t < T_VEL_UP) return smoothstep(0, T_VEL_UP, t);
  if (t < T_VEL_HOLD) return 1;
  if (t < T_VEL_DOWN) return 1 - smoothstep(T_VEL_HOLD, T_VEL_DOWN, t);
  return 0;
}

/** 放大进度：指数式放大 → 观感是「匀速推近」，末段缓出，落点精确为 1。
 *  缓动用正弦型（而非三次型）：峰值速率只有平均值的 1.57 倍，
 *  实测逐帧缩放比变化峰值 ~4%（三次型是 7.6%，中段偏陡、观感略「冲」）。 */
function growProgress(t: number): number {
  return easeInOutSine(clamp01((t - T_GROW_START) / (T_GROW_END - T_GROW_START)));
}

/** 放大阶段的额外自转剖面：区间两端严格为 0、且斜率为 0（growProgress 用的是
 *  正弦缓动，其导数在 0/1 处本就为 0）→ 放大开始与结束两个瞬间的角速度
 *  都精确等于背景角速度，进出放大段都不跳；中段鼓起，让「边放大边旋转」看得见。 */
function growSpinProfile(t: number): number {
  if (t <= T_GROW_START || t >= T_GROW_END) return 0;
  return Math.sin(Math.PI * growProgress(t));
}

// ---- 启动动画状态 ----
type Phase = 'idle' | 'morph' | 'grow' | 'ui' | 'done';
const introPhase = ref<Phase>('idle');
const introEnabled = ref(true); // 覆盖层是否渲染
const uiVisible = ref(false); // 操作层是否已浮现
let introT = -1; // 启动动画已进行秒数；-1 = 未启动 / 已跳过 → 场景直接呈现背景态
let introPending = false; // 覆盖层已就位、等待用户点击（此时棱球已摆好起点，起播零归位）
let booted = false; // bootstrap 是否结束（操作层等它就绪后再浮现，避免空壳一闪）
let phaseGrow = false;
let phaseUi = false;
let phaseDone = false;
let spinX = 0;
let spinY = 0;
let lastFrame = 0;

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
  // 镜像到 localStorage：下次启动的 head 内联脚本据此在首屏就定好主题，
  // 启动动画的底色因此与「上次关闭前保存的主题」一致（需求 5）。
  cacheTheme(t || 'dark');
  const m = document.querySelector('meta[name="theme-color"]');
  if (m) {
    m.setAttribute('content', t === 'light' ? '#f7f5f2' : t === 'sepia' ? '#efe6d3' : '#14130f');
  }
}
const themeAttr = computed(() => effectiveTheme());
watch(() => store.theme, () => applyTheme(effectiveTheme()));

// HUD 功能面板开关（不再与莱茵终端主题耦合，仅由 hud_enabled 控制）
const hudOn = computed(() => store.hudEnabled);
async function setHud(on: boolean) {
  await saveSettings({ hud_enabled: on });
}

// 暖色「三维档案终端」背景：缓慢自转的线框档案体，杏金描边。
/** 圆形柔边点精灵：默认 Points 是方块，用它让轨道粒子是圆点。 */
function makeDotTexture(): THREE.Texture {
  const S = 64;
  const cv = document.createElement('canvas');
  cv.width = cv.height = S;
  const ctx = cv.getContext('2d');
  if (ctx) {
    const g = ctx.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
    g.addColorStop(0, 'rgba(255,255,255,1)');
    g.addColorStop(0.45, 'rgba(255,255,255,0.75)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, S, S);
  }
  const tex = new THREE.Texture(cv);
  tex.needsUpdate = true;
  return tex;
}

function initScene(withOrbit: boolean): boolean {
  const stage = document.getElementById('stage');
  if (!stage) return false;
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
    new THREE.LineBasicMaterial({ color: 0xa67d48, transparent: true, opacity: BG_WIRE_O })
  );
  const inner = new THREE.Mesh(
    geo,
    new THREE.MeshBasicMaterial({ color: 0xcbb397, wireframe: true, transparent: true, opacity: BG_INNER_O })
  );
  group.add(wire, inner);
  scene.add(group);

  // ---- 环绕轨道粒子 ----
  // 两圈轻微倾斜、反向公转的粒子环，绕在棱球外圈。
  // 放进 group 内 → 与棱球一同缩放/自转，永远是「围着球转的轨道」。
  if (withOrbit) {
    const baseR = ARCHIVE_RADIUS * ARCHIVE_SCALE;
    const orb = new THREE.PointsMaterial({
      color: 0xc9a468,
      transparent: true,
      opacity: BG_ORBIT_O,
      map: makeDotTexture(),
      // 关掉距离衰减：粒子按屏幕像素计大小，待机时球只有 S0=0.1，
      // 若按世界单位缩放，待机阶段粒子会小到看不见。
      sizeAttenuation: false,
      size: 3.4,
      depthWrite: false,
    });
    const defs = [
      { n: 300, r: baseR * 1.22, tilt: 0.42, thick: 0.06, vel: ORBIT_VEL_A },
      { n: 200, r: baseR * 1.52, tilt: -0.26, thick: 0.1, vel: ORBIT_VEL_B },
    ];
    for (const d of defs) {
      const pos = new Float32Array(d.n * 3);
      for (let i = 0; i < d.n; i++) {
        const a = (i / d.n) * Math.PI * 2;
        // 环半径带一点随机抖动 + 环面法向厚度，避免看起来像一条完美细线
        const rr = d.r * (1 + (Math.random() - 0.5) * d.thick * 2);
        pos[i * 3] = Math.cos(a) * rr;
        pos[i * 3 + 1] = (Math.random() - 0.5) * baseR * d.thick;
        pos[i * 3 + 2] = Math.sin(a) * rr;
      }
      const g2 = new THREE.BufferGeometry();
      g2.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      const pts = new THREE.Points(g2, orb);
      pts.rotation.x = d.tilt;
      group.add(pts);
      orbitRings.push(pts);
    }
    orbitMat = orb;
  }

  scene3d = scene;
  camera3d = camera;
  group3d = group;
  wireMat = wire.material as THREE.LineBasicMaterial;
  innerMat = inner.material as THREE.MeshBasicMaterial;

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
  onResize = resize;
  window.addEventListener('resize', resize);
  // 用 ResizeObserver 兜住布局变化（侧栏开合、布局 A/B 切换等）导致的尺寸变化
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(stage);
  }

  lastFrame = 0;
  animate();
  return true;
}

/** 把 group 摆到「待机态」：棱球在大字后方以 S0 缓慢自转、清晰可见——
 *  它就是后续放大成背景的那只球（不重新放置、不淡入，点击起播零跳变）。 */
function prepareIntroScene() {
  if (!group3d || !wireMat || !innerMat) return;
  group3d.scale.setScalar(S0);
  wireMat.opacity = INTRO_WIRE_O;
  innerMat.opacity = INTRO_INNER_O;
  if (orbitMat) orbitMat.opacity = INTRO_ORBIT_O;
}

/** 依据时间轴更新棱球的缩放与不透明度（旋转由主循环积分，不在这里碰）。 */
function applySceneState(t: number) {
  if (!group3d || !wireMat || !innerMat) return;
  if (t < 0) {
    if (introPending) {
      // 待机：棱球在大字后方以 S0 可见自转（透过透明覆盖层露出），
      // 点击起播时无需任何归位/淡入动作 → 不存在跳变风险。
      group3d.scale.setScalar(S0);
      wireMat.opacity = INTRO_WIRE_O;
      innerMat.opacity = INTRO_INNER_O;
      if (orbitMat) orbitMat.opacity = INTRO_ORBIT_O;
      return;
    }
    // 未启用动画 / 已跳过 → 直接呈现背景态
    group3d.scale.setScalar(1);
    wireMat.opacity = BG_WIRE_O;
    innerMat.opacity = BG_INNER_O;
    if (orbitMat) orbitMat.opacity = BG_ORBIT_O;
    return;
  }
  const settle = smoothstep(T_GROW_START, T_GROW_END, t);
  // 指数式放大：从 S0 精确增长到 1
  group3d.scale.setScalar(S0 * Math.pow(1 / S0, growProgress(t)));
  // 待机时已可见（INTRO_*），全程只随放大收束回背景态——同一只球，无淡入无重放
  wireMat.opacity = INTRO_WIRE_O * (1 - settle) + BG_WIRE_O * settle;
  // 内部小球（inner）：放大（grow）开始后 0.45s 内平滑淡出，
  // 只保留放大的线框棱球成为背景（需求：球体放大时去掉里面的小球）。
  const innerFade = smoothstep(T_GROW_START, T_GROW_START + 0.45, t);
  innerMat.opacity = INTRO_INNER_O * (1 - innerFade);
  // 轨道粒子：与棱球一样从待机可见度平滑收束到背景点缀强度
  if (orbitMat) orbitMat.opacity = INTRO_ORBIT_O * (1 - settle) + BG_ORBIT_O * settle;
}

function animate(now?: number) {
  raf = requestAnimationFrame(animate);
  const ms = typeof now === 'number' ? now : performance.now();
  const dt = lastFrame ? Math.min(0.05, (ms - lastFrame) / 1000) : 1 / 60;
  lastFrame = ms;

  // ---- 时间轴推进：由渲染循环驱动，与画面严格同步 ----
  if (introT >= 0) {
    introT += dt;
    if (!phaseGrow && introT >= T_GROW_START) {
      phaseGrow = true;
      introPhase.value = 'grow';
    }
    // 操作层等「背景就位」且「数据已就绪」后再浮现（数据最迟多等 2s，绝不无限期拖住）
    if (!phaseUi && introT >= T_UI && (booted || introT >= T_UI + 2)) {
      phaseUi = true;
      introPhase.value = 'ui';
      uiVisible.value = true;
    }
    if (!phaseDone && phaseUi && introT >= T_DONE) {
      phaseDone = true;
      introPhase.value = 'done';
      introEnabled.value = false; // 卸载覆盖层
    }
  }

  // ---- 自转：单一累加器，任何阶段都不重置 → 角度连续 ----
  const p = velProfile(introT);
  const gs = growSpinProfile(introT);
  const velY = BG_VEL_Y + SPIN_EXTRA_Y * p + GROW_SPIN_Y * gs;
  const velX = BG_VEL_X + SPIN_EXTRA_X * p + GROW_SPIN_X * gs;
  spinY += velY * dt;
  spinX += velX * dt;
  if (group3d) group3d.rotation.set(spinX, spinY, 0);

  // ---- 轨道粒子：绕棱球公转（在 group 内部，随球一起缩放/自转）----
  if (orbitRings.length) {
    orbitRings[0].rotation.y += ORBIT_VEL_A * dt;
    if (orbitRings[1]) orbitRings[1].rotation.y += ORBIT_VEL_B * dt;
  }

  applySceneState(introT);
  // 测试钩子（仅 ?introdebug=1 时开启）：把启动动画的实时状态暴露出来，
  // 供 tools/intro_shots.mjs 在真实浏览器里量化「旋转角度/角速度/方向连续性」。
  if (introDebug) {
    (window as unknown as Record<string, unknown>)['__witworkIntro'] = {
      t: introT,
      phase: introPhase.value,
      spinX,
      spinY,
      scale: group3d ? group3d.scale.x : 1,
      wireO: wireMat ? wireMat.opacity : 0,
      innerO: innerMat ? innerMat.opacity : 0,
      orbitO: orbitMat ? orbitMat.opacity : 0,
      velY,
      velX,
    };
  }
  if (renderer && scene3d && camera3d) renderer.render(scene3d, camera3d);
}

/** 点击启动：进入「大字旋转坍缩 → 棱球浮现」阶段。 */
function startLaunch() {
  if (!introEnabled.value || introT >= 0) return; // 防止重复触发
  introPending = false;
  introT = 0;
  introPhase.value = 'morph';
  if (group3d && wireMat && innerMat) applySceneState(0); // 立刻归位到动画起点
}

/** 跳过启动动画：直接进入「背景就位 + 操作层渐显」，覆盖层随即淡出。 */
function skipIntro() {
  if (!introEnabled.value || phaseDone) return;
  introPending = false;
  introT = T_UI;
  phaseGrow = true;
  phaseUi = true;
  introPhase.value = 'ui';
  uiVisible.value = true;
}

onMounted(async () => {
  applyTheme(effectiveTheme());

  // 是否播放启动动画：
  //  - ?nofx=1 或 ?intro=0：交给自动化截图/低配设备直接进软件
  //  - prefers-reduced-motion：尊重系统「减少动态效果」
  //  - 3D 初始化失败：没有棱球可放大，跳过动画避免半截效果
  //  - ?intro=auto：无人值守自动起播（演示录屏 / 自动化截图采样各阶段用）
  const noFx = typeof location !== 'undefined' && /[?&]nofx=1/.test(location.search);
  const introOff = typeof location !== 'undefined' && /[?&]intro=0/.test(location.search);
  const introAuto = typeof location !== 'undefined' && /[?&]intro=auto/.test(location.search);
  const reduceMotion =
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  let sceneReady = false;
  if (!noFx) {
    // 3D 背景失败绝不能拖垮整个应用：initScene 若抛错（如无 WebGL / 显卡驱动异常），
    // 以前会中断 onMounted，导致 bootstrap 不执行 → 主题、HUD、数据全不加载（近似空白页）。
    try {
      // 减少动态效果：不播启动动画，也不加环绕粒子（只保留静态线框背景）
      sceneReady = initScene(!reduceMotion);
    } catch (e) {
      console.warn('[WitWork] 3D 背景初始化失败，已降级为纯色背景：', e);
    }
  }

  const play = sceneReady && !noFx && !introOff && !reduceMotion;
  introEnabled.value = play;
  introPhase.value = play ? 'idle' : 'done';
  uiVisible.value = !play; // 不播动画时立即显示操作层
  introPending = play; // 待机期间棱球已摆好起点，点击即起播、无归位跳变
  if (play) prepareIntroScene();
  else applySceneState(-1);

  if (play && introAuto) {
    // 自动起播：留 260ms 让首屏大字入场动画走完，便于采样到完整时序
    setTimeout(() => startLaunch(), 260);
  }

  try {
    await bootstrap();
  } catch {
    /* 连接失败已在 store.connected 标记 */
  }
  booted = true;
});

onBeforeUnmount(() => {
  cancelAnimationFrame(raf);
  if (onResize) window.removeEventListener('resize', onResize);
  resizeObserver?.disconnect();
  resizeObserver = null;
  renderer?.dispose();
});
</script>

<template>
  <!-- 启动动画覆盖层：与 .shell 同级（body 直系子节点），因此不受 .shell 的
       transform: scale() 影响，可用全局 fixed + z-index 盖在一切之上。 -->
  <Intro
    v-if="introEnabled"
    :phase="introPhase"
    @launch="startLaunch"
    @skip="skipIntro"
  />

  <div
    class="shell"
    :class="{ 'shell-on': uiVisible }"
    :data-theme="themeAttr"
    :style="{
      '--editor-font-size': store.editorFontSize + 'px',
      '--editor-line-height': String(store.editorLineHeight),
      '--editor-page-width': store.editorPageWidth + 'px',
      // 统一不透明度：一个滑块同时驱动顶栏、面板、内嵌区、抽屉（设置 topbar_alpha）
      '--topbar-alpha': store.topbarAlpha + '%',
      '--panel-alpha': store.topbarAlpha + '%',
      '--field-alpha': store.topbarAlpha + '%',
      '--drawer-alpha': store.topbarAlpha + '%',
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
  /* --intro-y：启动动画结束后的操作层「轻轻上浮到位」 */
  transform: scale(var(--ui-scale, 1)) translateY(var(--intro-y, 0px));
  transform-origin: top left;
  display: flex;
  flex-direction: column;
  z-index: 2;
  /* 启动动画期间操作层先隐藏，等背景棱球就位后再渐显浮现（需求 4）。 */
  --intro-y: 12px;
  opacity: 0;
  pointer-events: none;
  transition:
    opacity 0.68s var(--motion),
    transform 0.68s var(--motion);
}
.shell.shell-on {
  opacity: 1;
  --intro-y: 0px;
  pointer-events: auto;
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
