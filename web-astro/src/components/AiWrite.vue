<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount, nextTick } from 'vue';
import { store, aiOperate, stopAiOperate } from '../lib/store';
import AiWaiting from './AiWaiting.vue';

const props = defineProps<{
  bookId: number | null;
  chapterId: number | null;
  fullText: string;
  selStart: number;
  selEnd: number;
  chapterTitle: string;
  initialOp?: 'rewrite' | 'continue' | 'expand' | 'shrink' | 'create' | 'review' | 'gen_outline' | 'gen_from_outline' | null;
  outlineText?: string;
  /** 右键预设方向改写：预填的方向文案（非空即代表从右键预设打开） */
  initialInstruction?: string;
  /** 右键预设方向改写：打开即按预填方向自动生成 */
  autoRun?: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'apply-text', payload: { mode: 'replace' | 'insert' | 'whole'; text: string; selStart?: number; selEnd?: number; pos?: number }): void;
  (e: 'apply-outline', payload: { text: string }): void;
}>();

type Op = 'rewrite' | 'continue' | 'expand' | 'shrink' | 'create' | 'review' | 'gen_outline' | 'gen_from_outline';
type Stage = 'idle' | 'prepare' | 'connect' | 'generating';

const OPS: { key: Op; label: string; need: 'sel' | 'none' | 'book'; desc: string }[] = [
  { key: 'rewrite', label: '改写', need: 'sel', desc: '按方向改写选中文字（无选区则改整章）' },
  { key: 'continue', label: '续写', need: 'none', desc: '顺着文风接在后面写' },
  { key: 'expand', label: '扩写', need: 'sel', desc: '补充细节、心理、环境（无选区则扩整章）' },
  { key: 'shrink', label: '缩写', need: 'sel', desc: '压缩冗余、保留核心（无选区则缩整章）' },
  { key: 'create', label: '创作', need: 'book', desc: '按方向写全新段落，参考全书风格' },
  { key: 'review', label: '通读全书', need: 'book', desc: '读完整部作品，给出修改意见' },
  { key: 'gen_outline', label: '想法转大纲', need: 'none', desc: '把你的想法变成一章可写的大纲' },
  { key: 'gen_from_outline', label: '按大纲写', need: 'none', desc: '按本章大纲生成完整正文（替换整章）' },
];

// 支持「目标篇幅」的操作：给模型明确的字数指令，避免写得过短或注水
const LENGTH_OPS: Op[] = ['continue', 'create', 'gen_from_outline'];
const LENGTHS = [
  { v: 0, label: '自动' },
  { v: 500, label: '约 500 字' },
  { v: 1000, label: '约 1000 字' },
  { v: 2000, label: '约 2000 字' },
];

const op = ref<Op>(props.initialOp || 'rewrite');
const instruction = ref('');
const result = ref('');
const done = ref(false);
const targetWords = ref(0);

// ---- 生成过程反馈：阶段 + 计时 ----
const stage = ref<Stage>('idle');
const elapsedMs = ref(0);
const finalElapsedMs = ref(0);
const resultChars = ref(0);
let ticker: number | null = null;
let t0 = 0;

function startTicker() {
  stopTicker();
  t0 = performance.now();
  elapsedMs.value = 0;
  ticker = window.setInterval(() => {
    elapsedMs.value = performance.now() - t0;
  }, 100);
}
function stopTicker() {
  if (ticker !== null) {
    window.clearInterval(ticker);
    ticker = null;
  }
}
onBeforeUnmount(stopTicker);

const enabledProviders = computed(() => store.providers.filter((p) => p.enabled));
const hasSel = computed(() => props.selStart !== props.selEnd && props.selEnd > props.selStart);
const selLen = computed(() => (hasSel.value ? props.selEnd - props.selStart : 0));

const curOp = computed(() => OPS.find((o) => o.key === op.value)!);
const showLength = computed(() => LENGTH_OPS.includes(op.value));
const runDisabled = computed(() => !props.chapterId || !enabledProviders.value.length);
const runHint = computed(() => {
  if (!props.chapterId) return '请先打开一个章节';
  if (!enabledProviders.value.length) return '无可用模型，请到设置中添加';
  return '';
});
const applyLabel = computed(() => {
  if (op.value === 'gen_outline') return '写入大纲';
  if (op.value === 'gen_from_outline') return '替换整章';
  if (op.value === 'review') return '';
  if (op.value === 'continue') return '插入到此处';
  if (op.value === 'create') return '插入到光标';
  if (hasSel.value) return '替换选中';
  return '替换整章';
});

function stripFences(t: string): string {
  const m = t.match(/^```[^\n]*\n([\s\S]*?)\n```$/);
  return m ? m[1] : t.replace(/^```[^\n]*\n?/g, '').replace(/```$/g, '');
}

function selectOp(o: Op) {
  op.value = o;
}

async function run() {
  if (store.streaming) return;
  if (runDisabled.value) return;
  result.value = '';
  done.value = false;
  finalElapsedMs.value = 0;
  resultChars.value = 0;
  stage.value = 'prepare';
  startTicker();

  const o = op.value;
  let text = '';
  let scope = 'chapter';
  if (o === 'review' || o === 'create') {
    scope = 'book';
  } else if (o === 'gen_from_outline') {
    text = props.outlineText || '';
  } else if (o === 'gen_outline') {
    text = ''; // 想法写在 instruction
  } else if (hasSel.value) {
    text = props.fullText.slice(props.selStart, props.selEnd);
  } else {
    text = props.fullText; // 整章
  }

  await aiOperate(
    {
      operation: o,
      book_id: props.bookId,
      chapter_id: props.chapterId,
      text,
      instruction: instruction.value,
      scope,
      provider_id: store.draftProviderId ?? null,
      params: { target_words: targetWords.value || 0 },
    },
    (ev) => {
      if (ev.type === 'delta') {
        result.value += (ev.data as string) || '';
      } else if (ev.type === 'status') {
        const d = ev.data as { stage?: string } | null;
        if (d?.stage) stage.value = d.stage as Stage;
      } else if (ev.type === 'error') {
        result.value = '⚠ ' + (ev.data as string);
      } else if (ev.type === 'done') {
        done.value = true;
        const d = ev.data as { elapsed_ms?: number; chars?: number } | null;
        finalElapsedMs.value = d?.elapsed_ms ?? elapsedMs.value;
        resultChars.value = d?.chars ?? result.value.length;
      }
    }
  );

  stopTicker();
  stage.value = 'idle';
  done.value = true;
}

function apply() {
  const text = stripFences(result.value);
  if (!text.trim()) return;
  if (op.value === 'review') return;
  if (op.value === 'gen_outline') {
    emit('apply-outline', { text });
    return;
  }
  if (op.value === 'gen_from_outline') {
    emit('apply-text', { mode: 'whole', text });
    return;
  }
  if (op.value === 'continue') {
    const pos = hasSel.value ? props.selEnd : props.fullText.length;
    emit('apply-text', { mode: 'insert', text, pos });
  } else if (op.value === 'create') {
    emit('apply-text', { mode: 'insert', text, pos: props.selStart });
  } else if (hasSel.value) {
    emit('apply-text', { mode: 'replace', text, selStart: props.selStart, selEnd: props.selEnd });
  } else {
    emit('apply-text', { mode: 'whole', text });
  }
}

async function copyRes() {
  try {
    await navigator.clipboard.writeText(stripFences(result.value));
  } catch {
    /* ignore */
  }
}

// 【修复】抽屉已打开时再触发右键菜单，initialOp 会变化
// 但组件不会重新挂载，若不同步就会导致「点了扩写没反应」。
watch(
  () => props.initialOp,
  (o) => {
    if (o) op.value = o;
  }
);

// 右键预设方向改写：预填方向；若 autoRun，则打开即自动生成（一点即改）
if (props.initialInstruction && props.autoRun) {
  instruction.value = props.initialInstruction;
  nextTick(run);
}
watch(
  () => [props.initialOp, props.initialInstruction, props.autoRun] as const,
  ([o, instr, ar]) => {
    if (o) op.value = o;
    if (instr) instruction.value = instr;
    if (ar && instr) nextTick(run);
  }
);

watch(
  () => store.streaming,
  (s) => {
    if (s) done.value = false;
    else {
      // 被停止或异常结束：收掉计时器与阶段态
      stopTicker();
      stage.value = 'idle';
    }
  }
);
</script>

<template>
  <section class="aw">
    <header class="aw-head">
      <div class="aw-title">
        <span class="dot" :class="{ live: store.streaming }"></span>
        AI 写作操作
      </div>
      <button class="x" @click="emit('close')" title="关闭">✕</button>
    </header>

    <div class="aw-prov">
      <label class="pv-label">模型</label>
      <select class="pv-sel" :value="store.draftProviderId || ''" @change="(e) => (store.draftProviderId = (e.target as HTMLSelectElement).value || null)">
        <option v-for="p in enabledProviders" :key="p.id" :value="p.id">
          {{ p.name || p.kind }} · {{ p.model || p.kind }}
        </option>
        <option v-if="!enabledProviders.length" value="" disabled>无可用模型</option>
      </select>
    </div>

    <div class="aw-ops">
      <button
        v-for="o in OPS"
        :key="o.key"
        class="op"
        :class="{ on: op === o.key }"
        :title="o.desc"
        @click="selectOp(o.key)"
      >
        {{ o.label }}
      </button>
    </div>

    <div class="aw-sel mono">
      <template v-if="op === 'gen_outline'">在下方填写你的想法，AI 据此生成本章大纲</template>
      <template v-else-if="op === 'gen_from_outline'">将按下方「本章大纲」生成完整正文（替换整章）</template>
      <template v-else-if="op === 'review' || op === 'create'">将读取全书正文作为上下文</template>
      <template v-else-if="hasSel">已选 {{ selLen }} 字（{{ op === 'continue' ? '续写于选区之后' : '将作用于选区' }}）</template>
      <template v-else>未选区 · 将作用于整章</template>
    </div>

    <div class="aw-dir">
      <textarea
        v-model="instruction"
        class="aw-ta"
        :placeholder="curOp.need === 'book' ? '你的创作方向（可选，如：写一段雨夜追杀，节奏紧张）' : '你的方向（可选，如：更口语化 / 加强紧张感 / 缩短一半）'"
        :disabled="store.streaming"
      ></textarea>
    </div>

    <div v-if="showLength" class="aw-len">
      <span class="ln-label">篇幅</span>
      <button
        v-for="l in LENGTHS"
        :key="l.v"
        class="ln-btn"
        :class="{ on: targetWords === l.v }"
        :disabled="store.streaming"
        @click="targetWords = l.v"
      >{{ l.label }}</button>
    </div>

    <div class="aw-btns">
      <button v-if="store.streaming" class="stop" @click="stopAiOperate">■ 停止</button>
      <button v-else class="run" :disabled="runDisabled" :title="runHint" @click="run">生成 ✦</button>
      <span v-if="runHint && !store.streaming" class="run-hint">{{ runHint }}</span>
    </div>

    <!-- threeui 风格等待面板：只要还在生成就常驻，首字之后自动切换为「输出中」 -->
    <div v-if="store.streaming" class="aw-wait">
      <AiWaiting
        :stage="stage"
        :elapsed-ms="elapsedMs"
        :has-text="!!result"
        :op-label="curOp.label"
        @stop="stopAiOperate"
      />
    </div>

    <div v-if="store.aiError" class="aw-err">
      <span>⚠ {{ store.aiError }}</span>
      <button class="retry" @click="run">重试</button>
    </div>

    <div class="aw-result" v-if="result">
      <pre class="aw-text" :class="{ typing: store.streaming }">{{ stripFences(result) }}</pre>
      <div class="aw-meta mono" v-if="done && !store.streaming">
        耗时 {{ (finalElapsedMs / 1000).toFixed(1) }}s · 约 {{ resultChars }} 字
      </div>
      <div class="aw-result-btns" v-if="done && !store.streaming && op !== 'review'">
        <button class="apply" @click="apply">{{ applyLabel }}</button>
        <button class="cp" @click="copyRes">复制</button>
      </div>
      <div class="aw-result-btns" v-else-if="done && !store.streaming && op === 'review'">
        <button class="cp" @click="copyRes">复制全部意见</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.aw {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.aw-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.aw-title {
  font-weight: 700;
  font-size: 15px;
  color: var(--theme-ink);
  display: flex;
  align-items: center;
  gap: 8px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--theme-muted);
}
.dot.live {
  background: var(--theme-success);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--theme-success) 30%, transparent);
  animation: pulse 1s var(--motion) infinite;
}
@keyframes pulse {
  50% {
    opacity: 0.4;
  }
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
.aw-prov {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.pv-label {
  font-size: 12px;
  color: var(--theme-muted);
}
.pv-sel {
  flex: 1;
  font-size: 13px;
  padding: 5px 8px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
}
.pv-sel:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.aw-ops {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.op {
  font-size: 13px;
  padding: 6px 12px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--theme-ink-soft);
  cursor: pointer;
}
.op:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.op.on {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
  background: var(--theme-field);
}
.aw-sel {
  font-size: 11.5px;
  color: var(--theme-muted);
  padding: 6px 14px 0;
}
.aw-dir {
  padding: 8px 14px;
}
.aw-ta {
  resize: none;
  height: 56px;
  width: 100%;
  font-family: var(--font-sans);
  font-size: 13px;
  line-height: 1.6;
  padding: 8px 10px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
}
.aw-ta:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.aw-ta:disabled {
  opacity: 0.6;
}
.aw-len {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 14px 8px;
  flex-wrap: wrap;
}
.ln-label {
  font-size: 12px;
  color: var(--theme-muted);
  margin-right: 2px;
}
.ln-btn {
  font-size: 12px;
  padding: 3px 10px;
  border: 1px solid var(--theme-line);
  border-radius: 999px;
  background: transparent;
  color: var(--theme-ink-soft);
}
.ln-btn:hover:not(:disabled) {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.ln-btn.on {
  border-color: var(--theme-accent);
  background: var(--theme-field);
  color: var(--theme-accent-hover);
}
.ln-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.aw-btns {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 0 14px 10px;
  border-bottom: 1px solid var(--theme-line);
}
.run-hint {
  font-size: 11.5px;
  color: var(--theme-muted);
  margin-right: auto;
}
.run,
.stop {
  font-size: 13px;
  padding: 7px 18px;
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.run {
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border: 1px solid var(--theme-solid-bg);
}
.run:hover:not(:disabled) {
  background: var(--theme-solid-hover);
}
.run:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.stop {
  background: transparent;
  color: var(--theme-error);
  border: 1px solid var(--theme-error);
}
.stop:hover {
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
}
.aw-wait {
  padding: 10px 14px 2px;
}
.aw-err {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--theme-error);
  font-size: 12.5px;
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
  padding: 8px 10px;
  margin: 8px 14px;
  border-radius: var(--radius-sm);
}
.aw-err span {
  flex: 1;
  min-width: 0;
}
.retry {
  flex: none;
  font-size: 12px;
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--theme-error);
  background: transparent;
  color: var(--theme-error);
}
.retry:hover {
  background: color-mix(in srgb, var(--theme-error) 16%, transparent);
}
.aw-result {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 10px 14px 14px;
  gap: 8px;
}
.aw-text {
  flex: 1;
  min-height: 0;
  overflow: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-sans);
  font-size: 13.5px;
  line-height: 1.75;
  padding: 10px 12px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
}
/* 流式输出中：末尾一道光标，明确「还在写」 */
.aw-text.typing {
  border-color: color-mix(in srgb, var(--theme-accent) 55%, var(--theme-line));
}
.aw-text.typing::after {
  content: '';
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: text-bottom;
  background: var(--theme-accent);
  animation: caret 1s steps(1, end) infinite;
}
@keyframes caret {
  50% {
    opacity: 0;
  }
}
.aw-meta {
  font-size: 11.5px;
  color: var(--theme-muted);
}
.aw-result-btns {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
.apply {
  font-size: 13px;
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border: 1px solid var(--theme-solid-bg);
  cursor: pointer;
}
.apply:hover {
  background: var(--theme-solid-hover);
}
.cp {
  font-size: 13px;
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--theme-line);
  background: transparent;
  color: var(--theme-ink-soft);
  cursor: pointer;
}
.cp:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
</style>
