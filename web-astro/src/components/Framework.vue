<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { store, loadFramework, advanceFramework, retreatFramework, generateOutline, type FrameworkPhase } from '../lib/store';

const emit = defineEmits<{ (e: 'close'): void }>();

const PHASES: FrameworkPhase[] = ['brief', 'worldview', 'faction', 'plotline', 'character', 'outline', 'confirmed'];
const LABEL: Record<FrameworkPhase, string> = {
  brief: '一句话框架',
  worldview: '世界观',
  faction: '势力',
  plotline: '情节线',
  character: '人物',
  outline: '大纲',
  confirmed: '已确认',
};

const conclusion = ref('');
const fw = computed(() => store.framework as { phase: FrameworkPhase; phase_label: string; required: string[]; data: Record<string, string>; needs_review: FrameworkPhase[]; confirmed: boolean } | null);

function pidx(p: FrameworkPhase): number {
  return PHASES.indexOf(p);
}

// 阶段切换后清空输入框
watch(
  () => fw.value?.phase,
  () => {
    conclusion.value = '';
  }
);
watch(
  () => store.currentSessionId,
  () => loadFramework()
);

const showOutline = computed(() => fw.value && (fw.value.phase === 'outline' || fw.value.phase === 'confirmed'));

const summaryPhases = computed(() => PHASES.filter((p) => p !== 'confirmed'));

async function doAdvance() {
  if (!conclusion.value.trim()) return;
  await advanceFramework(conclusion.value);
}
async function doRetreat() {
  await retreatFramework();
}
async function doOutline() {
  await generateOutline();
}

onMounted(() => {
  if (!store.framework && store.currentSessionId) loadFramework();
});
</script>

<template>
  <section class="fw">
    <header class="fw-head">
      <div class="fw-title">框架共创</div>
      <button class="x" @click="emit('close')" title="关闭">✕</button>
    </header>

    <div v-if="store.frameworkError" class="fw-err">⚠ {{ store.frameworkError }}</div>

    <div v-if="!store.currentSessionId" class="fw-empty">
      <p>尚未开启 AI 会话。</p>
      <p class="hint">框架共创基于一次协作会话推进，请先在「AI 协作」中新建会话。</p>
    </div>

    <div v-else-if="fw" class="fw-body">
      <!-- 阶段进度 -->
      <div class="steps">
        <span
          v-for="(p, i) in PHASES"
          :key="p"
          class="step"
          :class="{
            on: p === fw.phase,
            done: pidx(p) < pidx(fw.phase),
            review: fw.needs_review.includes(p),
          }"
        >
          <i class="num">{{ i + 1 }}</i>{{ LABEL[p] }}
        </span>
      </div>

      <!-- 当前阶段 -->
      <div class="cur">
        <div class="cur-h">
          当前阶段：<b>{{ fw.phase_label }}</b>
          <span v-if="fw.confirmed" class="badge ok">✓ 已确认</span>
        </div>

        <div v-if="fw.required.length" class="req">
          <div class="req-h">本阶段引导问题</div>
          <div v-for="q in fw.required" :key="q" class="req-q">· {{ q }}</div>
        </div>

        <label class="lbl">本阶段结论（三段式：①结论 ②待确认 ③下一步）</label>
        <textarea
          v-model="conclusion"
          class="concl"
          placeholder="把这一阶段的思考沉淀成结论，推进后写回知识库对应分区…"
        ></textarea>

        <div class="acts">
          <button class="adv" :disabled="!conclusion.trim()" @click="doAdvance">推进 →</button>
          <button class="ret" :disabled="pidx(fw.phase) === 0" @click="doRetreat">← 回退</button>
          <button v-if="showOutline" class="ol" @click="doOutline">生成章节骨架</button>
        </div>
        <div v-if="!store.currentBookId && showOutline" class="hint">生成章节骨架需先打开一个作品</div>
      </div>

      <!-- 已沉淀框架 -->
      <div class="summary">
        <div class="sum-h">已沉淀框架</div>
        <div v-for="p in summaryPhases" :key="p" v-show="fw.data[p]" class="sum-row">
          <span class="sum-ph" :class="{ review: fw.needs_review.includes(p) }">{{ LABEL[p] }}</span>
          <span class="sum-tx">{{ fw.data[p] }}</span>
        </div>
        <div v-if="!summaryPhases.some((p) => fw.data[p])" class="hint">还没有沉淀内容，从「一句话框架」开始推进吧。</div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.fw {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.fw-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.fw-title {
  font-weight: 700;
  font-size: 15px;
  color: var(--theme-ink);
}
.x {
  border: none;
  background: transparent;
  color: var(--theme-muted);
  font-size: 14px;
  cursor: pointer;
}
.x:hover {
  color: var(--theme-ink);
}
.fw-err {
  color: var(--theme-error);
  font-size: 12px;
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
  padding: 6px 10px;
  margin: 8px 14px 0;
  border-radius: var(--radius-sm);
}
.fw-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 20px;
  color: var(--theme-muted);
  text-align: center;
}
.fw-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.steps {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.step {
  font-size: 11.5px;
  padding: 4px 9px;
  border: 1px solid var(--theme-line);
  border-radius: 999px;
  background: transparent;
  color: var(--theme-muted);
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.step .num {
  font-style: normal;
  font-family: var(--font-mono);
  font-size: 10px;
  opacity: 0.7;
}
.step.done {
  color: var(--theme-ink-soft);
  border-color: var(--theme-line);
}
.step.on {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
  background: var(--theme-field);
}
.step.review {
  border-color: var(--theme-error);
  color: var(--theme-error);
}
.cur {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 12px;
  background: var(--theme-field);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cur-h {
  font-size: 14px;
  color: var(--theme-ink);
}
.badge.ok {
  margin-left: 8px;
  font-size: 10.5px;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid var(--theme-success);
  color: var(--theme-success);
}
.req {
  border-left: 2px solid var(--theme-accent);
  padding-left: 10px;
}
.req-h {
  font-size: 11.5px;
  color: var(--theme-muted);
  margin-bottom: 4px;
}
.req-q {
  font-size: 12.5px;
  color: var(--theme-ink-soft);
  line-height: 1.7;
}
.lbl {
  font-size: 12px;
  color: var(--theme-muted);
}
.concl {
  font-family: var(--font-sans);
  font-size: 13px;
  line-height: 1.7;
  min-height: 120px;
  resize: vertical;
  padding: 8px 10px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-paper);
  color: var(--theme-ink);
}
.concl:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.acts {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.adv,
.ol {
  font-size: 13px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border: 1px solid var(--theme-solid-bg);
  cursor: pointer;
}
.adv:hover:not(:disabled),
.ol:hover {
  background: var(--theme-solid-hover);
}
.adv:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.ret {
  font-size: 13px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: 1px solid var(--theme-line);
  color: var(--theme-ink-soft);
  cursor: pointer;
}
.ret:hover:not(:disabled) {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.ret:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.summary {
  border-top: 1px dashed var(--theme-line);
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sum-h {
  font-size: 12px;
  color: var(--theme-muted);
}
.sum-row {
  display: flex;
  gap: 8px;
  font-size: 12.5px;
  align-items: baseline;
}
.sum-ph {
  flex: 0 0 auto;
  color: var(--theme-accent);
  font-weight: 600;
}
.sum-ph.review {
  color: var(--theme-error);
}
.sum-tx {
  color: var(--theme-ink-soft);
  white-space: pre-wrap;
  word-break: break-word;
}
.hint {
  font-size: 12px;
  color: var(--theme-muted);
}
</style>
