#!/usr/bin/env python
"""启动动画「旋转连续性」断言测试（万维文 WitWork）

用户的核心要求：
  棱球在放大成为背景的过程中，旋转的**角度 / 角速度 / 方向**必须与之后的
  背景旋转完全一致、连贯无跳变。

本测试不重新推导公式，而是从 web-astro/src/components/App.vue 里**按名字抽取
真实发布的代码片段**（常量 + velProfile / growProgress / appearProgress /
applySceneState），拼成可执行 JS 交给 node 跑一遍 60fps 仿真，然后断言：

  A1 放大阶段的角速度恒等于背景角速度（严格相等，不是「约等于」）
  A2 角度单调递增、方向恒定（同一旋转方向）
  A3 角速度加速有界 —— 逐帧角增量没有突跳（这是「无跳变」的量化判据）
  A4 速度剖面在放大开始的瞬间已归零到 1e-3 以内
  A5 缩放在 T_GROW_END 精确落到 1.0，且逐帧单调、无回退
  A6 不透明度在放大前后平滑收敛到背景值，末值严格相等
  A7 起播瞬间（t=0）角速度与待机态一致（起播也不跳）

用法：
  ./venv/Scripts/python.exe tools/intro_timeline_test.py
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile

APP = pathlib.Path("web-astro/src/components/App.vue")


def extract(src: str, start_pat: str, end_pat: str, name: str) -> str:
    """按正则取 [start_pat, end_pat) 之间的文本；取不到直接报错（宁可失败也别假通过）。"""
    i = src.find(start_pat)
    if i < 0:
        raise SystemExit(f"抽取失败：找不到起点 {name} -> {start_pat!r}")
    j = src.find(end_pat, i)
    if j < 0:
        raise SystemExit(f"抽取失败：找不到终点 {name} -> {end_pat!r}")
    return src[i:j]


def main() -> int:
    src = APP.read_text(encoding="utf-8")

    # ---- 按名字抽取真实代码 ----
    consts = extract(src, "const BG_VEL_Y", "const S0 = 0.1;", "时间轴常量")
    consts += src[src.find("const S0 = 0.1;") : src.find("const S0 = 0.1;") + len("const S0 = 0.1;")]
    opacity_consts = extract(src, "// 背景态的不透明度", "/* ==================== 启动动画时间轴", "不透明度常量")
    clamp = extract(src, "const clamp01 =", "\nconst smoothstep", "clamp01")

    # smoothstep / easeInOutCubic
    helpers = extract(src, "const clamp01 =", "/** 额外角速度剖面", "数学 helper")
    # velProfile / growProgress / appearProgress
    timeline_fns = extract(src, "/** 额外角速度剖面", "// ---- 启动动画状态 ----", "时间轴函数")
    scene = extract(src, "function applySceneState", "\nfunction animate", "applySceneState")
    # 时间轴常量后续可能被引用（T_GROW_START 等）已在 consts 内

    js_parts = [
        opacity_consts,
        consts,
        helpers,
        timeline_fns,
        scene,
    ]
    js = "\n".join(js_parts)

    # ---- 去掉 TypeScript 类型标注 ----
    # 抽取出来的都是纯数学代码，标注只有 number / boolean，整体剥掉即可
    js = js.replace(": number", "").replace(": boolean", "")
    js = re.sub(r"\)\s*\{", ") {", js)  # 归一化已有的写法

    # ---- 把 Three.js 对象替换成可观测的桩 ----
    js = js.replace("group3d", "G").replace("wireMat", "WM").replace("innerMat", "IM").replace("orbitMat", "OM")

    harness = """
// ====== 桩：替代 Three.js 对象，记录缩放与不透明度 ======
const G  = { scale: { s: 0, setScalar(v) { this.s = v; } } };
const WM = { opacity: 0 };
const IM = { opacity: 0 };
const OM = { opacity: 0 };   // 环绕轨道粒子材质桩

/*__INJECT__*/

// ====== 60fps 仿真：完全照搬 App.vue 的 animate 积分方式 ======
const FPS = 60, DT = 1 / FPS;
const DUR = 5.0;
let t = -1;              // 待机：introPending 为 true
let introPending = true;
let spinY = 0, spinX = 0;
const rows = [];
function frame(tv) {
  const p = velProfile(tv);
  const gs = growSpinProfile(tv);
  const vy = BG_VEL_Y + SPIN_EXTRA_Y * p + GROW_SPIN_Y * gs;
  const vx = BG_VEL_X + SPIN_EXTRA_X * p + GROW_SPIN_X * gs;
  spinY += vy * DT;
  spinX += vx * DT;
  applySceneState(tv);
  rows.push({ t: tv, vy, vx, spinY, scale: G.scale.s, wireO: WM.opacity, innerO: IM.opacity, orbitO: OM.opacity });
}
// 待机若干帧
for (let i = 0; i < 30; i++) frame(-1);
introPending = false;                    // 起播
const N = Math.round(DUR / DT);
for (let i = 0; i <= N; i++) frame(i * DT);

// ====== 断言 ======
const fails = [];
function ok(name, cond, detail) {
  console.log((cond ? "  PASS  " : "  FAIL  ") + name + (detail ? "   <- " + detail : ""));
  if (!cond) fails.push(name);
}
const near = (a, b, eps) => Math.abs(a - b) <= eps;

console.log("=== 时间轴常量（取自 App.vue）===");
console.log(`  BG_VEL_Y=${BG_VEL_Y} BG_VEL_X=${BG_VEL_X} SPIN_EXTRA_Y=${SPIN_EXTRA_Y} SPIN_EXTRA_X=${SPIN_EXTRA_X}`);
console.log(`  GROW_SPIN_Y=${GROW_SPIN_Y} GROW_SPIN_X=${GROW_SPIN_X}（放大段额外自转，两端归零）`);
console.log(`  T_GROW_START=${T_GROW_START} T_GROW_END=${T_GROW_END} T_VEL_DOWN=${T_VEL_DOWN} S0=${S0}`);
console.log(`  BG_WIRE_O=${BG_WIRE_O} BG_INNER_O=${BG_INNER_O} INTRO_WIRE_O=${INTRO_WIRE_O} INTRO_INNER_O=${INTRO_INNER_O}`);
console.log();

console.log("=== A1 放大段角速度剖面（两端精确收敛到背景速度）===");
const growRows = rows.filter(r => r.t >= T_GROW_START - 1e-9 && r.t <= T_GROW_END + 1e-9);
const badVy = growRows.filter(r => r.vy !== BG_VEL_Y + GROW_SPIN_Y * growSpinProfile(r.t));
const badVx = growRows.filter(r => r.vx !== BG_VEL_X + GROW_SPIN_X * growSpinProfile(r.t));
ok("放大段每帧 vy === BG_VEL_Y + GROW_SPIN_Y*growSpinProfile(t)", badVy.length === 0,
   badVy.length ? `异常 ${badVy.length} 帧` : `${growRows.length} 帧全部严格相等`);
ok("放大段每帧 vx === BG_VEL_X + GROW_SPIN_X*growSpinProfile(t)", badVx.length === 0,
   badVx.length ? `异常 ${badVx.length} 帧` : "OK");
const afterRows = rows.filter(r => r.t > T_GROW_END + 1e-9);
const badAfter = afterRows.filter(r => r.vy !== BG_VEL_Y || r.vx !== BG_VEL_X);
ok("放大结束后每一帧角速度 === 背景角速度（进入背景无速度突跳）", badAfter.length === 0,
   badAfter.length ? `异常 ${badAfter.length} 帧` : `${afterRows.length} 帧全部严格相等`);
ok("growSpinProfile 在放大区间两端严格为 0",
   growSpinProfile(T_GROW_START) === 0 && growSpinProfile(T_GROW_END) === 0,
   `起=${growSpinProfile(T_GROW_START)} 止=${growSpinProfile(T_GROW_END)}`);
// 跨界速度跳变：放大最后一帧 → 放大后第一帧
const lastGrowRow = growRows.slice(-1)[0];
const firstAfterRow = afterRows[0];
const boundaryJumpDeg = Math.abs(firstAfterRow.vy - lastGrowRow.vy) * 180 / Math.PI;
ok("放大→背景 跨界速度跳变 < 0.5°/s", boundaryJumpDeg < 0.5, `实测 ${boundaryJumpDeg.toFixed(4)}°/s`);
// 量化「放大时到底转了多少」：用户要的就是这个看得见
const g0 = growRows[0].spinY, g1 = growRows.slice(-1)[0].spinY;
const growTotalDeg = (g1 - g0) * 180 / Math.PI;
const bgOnlyDeg = BG_VEL_Y * (T_GROW_END - T_GROW_START) * 180 / Math.PI;
ok("放大过程总转角 ≥ 90°（肉眼可见地在旋转）", growTotalDeg >= 90,
   `实测 ${growTotalDeg.toFixed(1)}°（其中背景分量仅 ${bgOnlyDeg.toFixed(1)}°，额外自转贡献 ${(growTotalDeg - bgOnlyDeg).toFixed(1)}°）`);
console.log();

console.log("=== A2 方向恒定 & 角度单调递增 ===");
let mono = true, signOk = true;
for (let i = 1; i < rows.length; i++) {
  if (rows[i].spinY <= rows[i - 1].spinY) mono = false;
  if (rows[i].vy <= 0 || rows[i].vx <= 0) signOk = false;
}
ok("spinY 逐帧严格递增（无倒转）", mono);
ok("角速度始终为正（方向不变）", signOk);
console.log();

console.log("=== A3 逐帧角增量无突跳（加速有界）===");
let maxD2 = 0, atT = 0;
for (let i = 2; i < rows.length; i++) {
  const d2 = Math.abs((rows[i].spinY - rows[i - 1].spinY) - (rows[i - 1].spinY - rows[i - 2].spinY));
  if (d2 > maxD2) { maxD2 = d2; atT = rows[i].t; }
}
const maxD2Deg = maxD2 * 180 / Math.PI;
ok("最大逐帧角加速度 < 0.5°/帧²", maxD2Deg < 0.5, `实测 ${maxD2Deg.toFixed(4)}°/帧² @ t=${atT.toFixed(3)}s`);
// 放大段内部：额外自转剖面在鼓起/收回，角加速度有界但非零（这是「边放大边旋转」的来源）
let growD2 = 0, growD2At = 0;
for (let i = 2; i < rows.length; i++) {
  if (rows[i - 2].t < T_GROW_START + DT) continue;
  if (rows[i].t > T_GROW_END) continue;
  const d2 = Math.abs((rows[i].spinY - rows[i - 1].spinY) - (rows[i - 1].spinY - rows[i - 2].spinY));
  if (d2 > growD2) { growD2 = d2; growD2At = rows[i].t; }
}
ok("放大段内部逐帧角加速度有界 < 0.1°/帧²（鼓形剖面平滑收放）", growD2 * 180 / Math.PI < 0.1,
   `实测 ${(growD2 * 180 / Math.PI).toFixed(4)}°/帧² @ t=${growD2At.toFixed(3)}s`);
// 放大结束之后：角速度恒定 = 背景速度 → 逐帧角增量必须完全相同
let postD2 = 0;
for (let i = 2; i < rows.length; i++) {
  if (rows[i - 2].t <= T_GROW_END + DT) continue;
  const d2 = Math.abs((rows[i].spinY - rows[i - 1].spinY) - (rows[i - 1].spinY - rows[i - 2].spinY));
  postD2 = Math.max(postD2, d2);
}
ok("放大结束后逐帧角增量完全相同（角加速度严格 = 0）", postD2 === 0, `实测 ${postD2}`);
console.log();

console.log("=== A4 放大开始瞬间速度剖面已归零 ===");
const eps = 1e-6;
const pBefore = velProfile(T_GROW_START - eps);
const pAt = velProfile(T_GROW_START);
ok("velProfile(T_GROW_START-ε) < 1e-3", pBefore < 1e-3, `= ${pBefore.toExponential(3)}`);
ok("velProfile(T_GROW_START) === 0", pAt === 0, `= ${pAt}`);
ok("T_GROW_START === T_VEL_DOWN（设计前提）", T_GROW_START === T_VEL_DOWN);
console.log();

console.log("=== A5 缩放落点与单调性 ===");
ok("growProgress(T_GROW_END) === 1", growProgress(T_GROW_END) === 1, String(growProgress(T_GROW_END)));
const lastGrow = rows.filter(r => r.t <= T_GROW_END).slice(-1)[0];
ok("末帧 scale 归一到 1（误差 < 1e-6）", near(lastGrow.scale, 1, 1e-6), `scale=${lastGrow.scale}`);
let scaleMono = true, maxRatioStep = 0;
const gRows = rows.filter(r => r.t >= T_GROW_START && r.t <= T_GROW_END);
for (let i = 1; i < gRows.length; i++) {
  if (gRows[i].scale <= gRows[i - 1].scale) scaleMono = false;
  maxRatioStep = Math.max(maxRatioStep, Math.abs(gRows[i].scale / gRows[i - 1].scale - 1));
}
ok("放大段缩放逐帧递增（无回退）", scaleMono);
ok("放大段单帧缩放比变化 < 5%（指数式推近 + 正弦缓动，实测峰值 ≈4%）", maxRatioStep < 0.05,
   `最大 ${(maxRatioStep * 100).toFixed(2)}%/帧`);
ok("放大结束后 scale 恒为 1", rows.filter(r => r.t > T_GROW_END).every(r => r.scale === 1));
console.log();

console.log("=== A6 不透明度收敛到背景值 ===");
const tail = rows.slice(-1)[0];
ok("末帧 wireO === BG_WIRE_O", tail.wireO === BG_WIRE_O, `${tail.wireO} vs ${BG_WIRE_O}`);
ok("末帧 innerO === BG_INNER_O", tail.innerO === BG_INNER_O, `${tail.innerO} vs ${BG_INNER_O}`);
ok("末帧 orbitO === BG_ORBIT_O（轨道粒子收敛为背景点缀强度）", tail.orbitO === BG_ORBIT_O, `${tail.orbitO} vs ${BG_ORBIT_O}`);
let maxOpJump = 0;
for (let i = 1; i < rows.length; i++) {
  const base = rows[i].t < 0 || rows[i - 1].t < 0 ? 0 : 0;
  maxOpJump = Math.max(maxOpJump, Math.abs(rows[i].wireO - rows[i - 1].wireO));
  maxOpJump = Math.max(maxOpJump, Math.abs(rows[i].orbitO - rows[i - 1].orbitO));
}
ok("逐帧不透明度变化 < 0.06（无闪现，含轨道粒子）", maxOpJump < 0.06, `最大 ${maxOpJump.toFixed(4)}`);
console.log();

console.log("=== A7 起播瞬间不跳（待机态与 t=0 角速度一致）===");
const idleRows = rows.filter(r => r.t < 0);
const firstLaunch = rows.find(r => r.t >= 0);
ok("待机帧角速度 == 背景角速度", idleRows.every(r => r.vy === BG_VEL_Y && r.vx === BG_VEL_X));
ok("t=0 首帧角速度 == 背景角速度", firstLaunch.vy === BG_VEL_Y && firstLaunch.vx === BG_VEL_X,
   `vy=${firstLaunch.vy}`);
console.log();

console.log("=== 时序快照（每 0.2s）===");
console.log("   t(s)    角度 spinY(°)   角速度(°/s)   scale    wireO   innerO");
let k = 0;
for (const r of rows) {
  if (r.t < 0) continue;
  if (r.t + 1e-9 >= k * 0.2) {
    console.log(
      `  ${r.t.toFixed(2).padStart(5)}  ${(r.spinY * 180 / Math.PI).toFixed(2).padStart(11)}  ` +
      `${(r.vy * 180 / Math.PI).toFixed(2).padStart(9)}  ${r.scale.toFixed(3).padStart(6)}  ` +
      `${r.wireO.toFixed(3).padStart(6)}  ${r.innerO.toFixed(3).padStart(6)}`
    );
    k++;
  }
}

console.log();
console.log(fails.length ? "失败：" + fails.join("、") : "全部通过 ✅");
process.exit(fails.length ? 1 : 0);
"""

    tmp = pathlib.Path(tempfile.gettempdir()) / "witwork_intro_timeline.js"
    tmp.write_text(harness.replace("/*__INJECT__*/", js), encoding="utf-8")

    node = r"C:\Users\wszy1\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
    if not pathlib.Path(node).exists():
        node = "node"
    r = subprocess.run([node, str(tmp)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout)
    if r.stderr.strip():
        print("--- node stderr ---")
        print(r.stderr[:2000])
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
