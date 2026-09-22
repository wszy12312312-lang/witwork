<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount, nextTick } from 'vue';
import { store, aiOperate, stopAiOperate } from '../lib/store';
import { awCache, awHistory, pushAwHistory, removeAwHistory, clearAwHistory, type AwHistoryEntry } from '../lib/aiWriteCache';
import SpeechButton from './SpeechButton.vue';
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

// 状态存于模块级 awCache（见 lib/aiWriteCache.ts）：关抽屉 / 切别的功能面板都不丢，
// 软件重启后也能从 localStorage 恢复；这里初始化后双向镜像
const op = ref<Op>(props.initialOp || awCache.op || 'rewrite');
const instruction = ref(props.initialInstruction || awCache.instruction);
const result = ref(awCache.result);
const done = ref(awCache.done);
const targetWords = ref(awCache.targetWords);
// 自定义字数：>0 时优先于预设档位（创作 / 按大纲写 / 续写）
const customWords = ref(awCache.customWords);
const effWords = computed(() => (customWords.value > 0 ? customWords.value : targetWords.value));
const showHistory = ref(false);
const dirTa = ref<HTMLTextAreaElement | null>(null);
// 本次生成接到的知识库条数（refs 事件），0 表示没有检到或未开启接地
const kbRefs = ref(0);

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

// ---- 生成动画流程：方向文字「飞入」思考等待，首字到达后输出区展开呈现 ----
const flying = ref(false);
const flyText = computed(() => {
  const t = instruction.value.trim();
  return t ? (t.length > 26 ? t.slice(0, 26) + '…' : t) : curOp.value.label;
});

async function run() {
  if (store.streaming) return;
  if (runDisabled.value) return;
  result.value = '';
  done.value = false;
  kbRefs.value = 0;
  finalElapsedMs.value = 0;
  resultChars.value = 0;
  stage.value = 'prepare';
  startTicker();
  // 输入区文字以动画飞向「思考等待中」面板（0.6s，与等待面板的浮现重叠、衔接自然）
  flying.value = true;
  window.setTimeout(() => (flying.value = false), 680);

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
      params: { target_words: effWords.value || 0 },
    },
    (ev) => {
      if (ev.type === 'delta') {
        result.value += (ev.data as string) || '';
      } else if (ev.type === 'status') {
        const d = ev.data as { stage?: string } | null;
        if (d?.stage) stage.value = d.stage as Stage;
      } else if (ev.type === 'refs') {
        kbRefs.value = (ev.data as unknown[] | null)?.length ?? 0;
      } else if (ev.type === 'error') {
        result.value = '⚠ ' + (ev.data as string);
      } else if (ev.type === 'done') {
        done.value = true;
        const d = ev.data as { elapsed_ms?: number; chars?: number } | null;
        finalElapsedMs.value = d?.elapsed_ms ?? elapsedMs.value;
        resultChars.value = d?.chars ?? result.value.length;
        // 写入历史：操作 + 当时方向 + 生成内容 + 章节，之后可载入复用
        pushAwHistory({
          op: op.value,
          opLabel: curOp.value.label,
          instruction: instruction.value,
          result: result.value,
          bookId: props.bookId,
          chapterId: props.chapterId,
          chapterTitle: props.chapterTitle,
        });
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

/** 输出区关闭：停止生成（若在跑）并清空输出，恢复空状态。 */
function clearResult() {
  if (store.streaming) stopAiOperate();
  result.value = '';
  done.value = false;
  kbRefs.value = 0;
  finalElapsedMs.value = 0;
  resultChars.value = 0;
  stopTicker();
  stage.value = 'idle';
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

// 本地状态 → 模块级缓存（关抽屉 / 切面板不丢，localStorage 持久化在缓存模块里做）
watch(
  [op, instruction, result, done, targetWords, customWords],
  () => {
    awCache.op = op.value;
    awCache.instruction = instruction.value;
    awCache.result = result.value;
    awCache.done = done.value;
    awCache.targetWords = targetWords.value;
    awCache.customWords = customWords.value;
  }
);

// 语音输入：识别文本插入方向框光标处
function onDirSpeech(text: string) {
  const ta = dirTa.value;
  const s = ta && typeof ta.selectionStart === 'number' ? ta.selectionStart : instruction.value.length;
  instruction.value = instruction.value.slice(0, s) + text + instruction.value.slice(s);
  nextTick(() => {
    if (!ta) return;
    const np = s + text.length;
    ta.focus();
    ta.setSelectionRange(np, np);
  });
}

// 历史记录：载入一条（操作 + 方向 + 内容），可改方向重新生成或直接再应用
function loadEntry(h: AwHistoryEntry) {
  op.value = h.op;
  instruction.value = h.instruction;
  result.value = h.result;
  done.value = true;
  targetWords.value = 0;
  customWords.value = 0;
  showHistory.value = false;
}

function fmtTime(ts: number): string {
  const d = Date.now() - ts;
  if (d < 60_000) return '刚刚';
  if (d < 3_600_000) return `${Math.floor(d / 60_000)} 分钟前`;
  if (d < 86_400_000) return `${Math.floor(d / 3_600_000)} 小时前`;
  const dt = new Date(ts);
  return `${dt.getMonth() + 1}/${dt.getDate()} ${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`;
}

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

    <!-- 生成历史：全部功能共用一份，新→旧；操作 + 当时方向 + 内容，可载入后再编辑/再生成/再应用 -->
    <div class="aw-hist">
      <button class="aw-hist-toggle" @click="showHistory = !showHistory">
        🕘 历史记录<span v-if="awHistory.length">（{{ awHistory.length }}）</span>
        <span class="tri">{{ showHistory ? '▾' : '▸' }}</span>
      </button>
      <button v-if="showHistory && awHistory.length" class="aw-hist-clear" @click="clearAwHistory">清空</button>
    </div>
    <div v-if="showHistory" class="aw-hist-list">
      <div
        v-for="(h, hi) in awHistory"
        :key="h.id"
        class="aw-hist-item"
        :style="{ animationDelay: hi * 36 + 'ms' }"
        title="点击载入：可改方向重新生成，或直接再次应用"
        @click="loadEntry(h)"
      >
        <div class="aw-hist-meta">
          <span class="aw-hist-op">{{ h.opLabel }}</span>
          <span v-if="h.chapterTitle" class="aw-hist-chap">{{ h.chapterTitle }}</span>
          <span v-if="h.instruction" class="aw-hist-dir">方向：{{ h.instruction }}</span>
          <span class="aw-hist-time">{{ fmtTime(h.ts) }}</span>
        </div>
        <div class="aw-hist-snip">{{ h.result.slice(0, 80) }}{{ h.result.length > 80 ? '…' : '' }}</div>
        <button class="aw-hist-del" title="删除这条" @click.stop="removeAwHistory(h.id)">✕</button>
      </div>
      <div v-if="!awHistory.length" class="aw-hist-empty">还没有历史。生成一次就会记在这里。</div>
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
      <div class="aw-dir-wrap">
        <textarea
          ref="dirTa"
          v-model="instruction"
          class="aw-ta"
          :class="{ thinking: store.streaming && !result }"
          :placeholder="curOp.need === 'book' ? '你的创作方向（可选，如：写一段雨夜追杀，节奏紧张）' : '你的方向（可选，如：更口语化 / 加强紧张感 / 缩短一半）'"
          :disabled="store.streaming"
        ></textarea>
        <SpeechButton class="aw-mic" title="语音输入方向" @result="onDirSpeech" />
        <!-- 生成瞬间：方向文字原位起飞，飞向下方的「思考等待中」面板 -->
        <span v-if="flying" class="aw-fly" aria-hidden="true">{{ flyText }}</span>
      </div>
    </div>

    <div v-if="showLength" class="aw-len">
      <span class="ln-label">篇幅</span>
      <button
        v-for="l in LENGTHS"
        :key="l.v"
        class="ln-btn"
        :class="{ on: customWords <= 0 && targetWords === l.v }"
        :disabled="store.streaming"
        @click="targetWords = l.v; customWords = 0"
      >{{ l.label }}</button>
      <input
        v-model.number="customWords"
        class="ln-custom"
        type="number"
        min="0"
        step="100"
        placeholder="自定义字数"
        title="自定义目标字数，填了优先于上面的档位"
        :disabled="store.streaming"
      />
    </div>

    <div class="aw-btns">
      <button v-if="store.streaming" class="stop" @click="stopAiOperate">■ 停止</button>
      <button v-else class="run" :disabled="runDisabled" :title="runHint" @click="run">生成 ✦</button>
      <span v-if="runHint && !store.streaming" class="run-hint">{{ runHint }}</span>
    </div>

    <!-- 生成历史已移至「模型」选择块下方（统一一份，新→旧） -->

    <!-- threeui 风格等待面板：只要还在生成就常驻，首字之后自动切换为「输出中」 -->
    <transition name="aw-fade">
      <div v-if="store.streaming" class="aw-wait">
        <AiWaiting
          :stage="stage"
          :elapsed-ms="elapsedMs"
          :has-text="!!result"
          :op-label="curOp.label"
          @stop="stopAiOperate"
        />
      </div>
    </transition>

    <div v-if="store.aiError" class="aw-err">
      <span>⚠ {{ store.aiError }}</span>
      <button class="retry" @click="run">重试</button>
    </div>

    <!-- 输出区：首字到达时从等待状态平滑展开；右上角 ✕ 清空恢复空态 -->
    <transition name="aw-rise">
      <div class="aw-result" v-if="result">
        <div class="aw-result-head">
          <span class="aw-result-cap">输出</span>
          <button
            class="aw-result-close"
            title="清空输出内容并恢复空状态"
            @click="clearResult"
          >✕ 清空</button>
        </div>
        <pre class="aw-text" :class="{ typing: store.streaming }">{{ stripFences(result) }}</pre>
        <div class="aw-meta mono" v-if="done && !store.streaming">
          耗时 {{ (finalElapsedMs / 1000).toFixed(1) }}s · 约 {{ resultChars }} 字<template v-if="kbRefs > 0"> · 已接知识库 {{ kbRefs }} 条设定</template>
        </div>
        <div class="aw-result-btns" v-if="done && !store.streaming && op !== 'review'">
          <button class="apply" @click="apply">{{ applyLabel }}</button>
          <button class="cp" @click="copyRes">复制</button>
        </div>
        <div class="aw-result-btns" v-else-if="done && !store.streaming && op === 'review'">
          <button class="cp" @click="copyRes">复制全部意见</button>
        </div>
      </div>
    </transition>
  </section>
</template>

<style scoped>
.aw {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  /* 内容超出时可整体向下滚动（历史展开 / 输出很长时不再被截断） */
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
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
  transition: transform var(--dur-base) var(--spring), border-color 0.25s var(--motion),
    color 0.25s var(--motion), background 0.25s var(--motion);
}
.op:active {
  transform: scale(0.94);
  transition-duration: var(--dur-fast);
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
.aw-dir-wrap {
  position: relative;
}
.aw-mic {
  position: absolute;
  right: 8px;
  bottom: 8px;
}
.aw-hist {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.aw-hist-toggle {
  font-size: 12.5px;
  border: none;
  background: transparent;
  color: var(--theme-ink-soft);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
}
.aw-hist-toggle:hover {
  color: var(--theme-accent-hover);
}
.aw-hist-toggle .tri {
  font-size: 10px;
  color: var(--theme-muted);
}
.aw-hist-clear {
  font-size: 11.5px;
  padding: 2px 9px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--theme-muted);
  cursor: pointer;
}
.aw-hist-clear:hover {
  border-color: var(--theme-error);
  color: var(--theme-error);
}
.aw-hist-list {
  max-height: 200px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.aw-hist-item {
  position: relative;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  padding: 7px 30px 7px 9px;
  cursor: pointer;
  /* threeui 列表项入场：依次上浮（延迟由行内 animationDelay 控制） */
  animation: awItemIn 0.46s var(--spring) both;
  transition: transform var(--dur-base) var(--spring), border-color 0.25s var(--motion);
}
.aw-hist-item:hover {
  border-color: var(--theme-accent);
  transform: translateX(2px);
}
.aw-hist-item:active {
  transform: scale(0.99);
  transition-duration: var(--dur-fast);
}
@keyframes awItemIn {
  from {
    opacity: 0;
    transform: translate3d(0, 10px, 0) scale(0.98);
  }
}
.aw-hist-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 3px;
}
.aw-hist-op {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid var(--theme-accent);
  color: var(--theme-accent-hover);
  white-space: nowrap;
}
.aw-hist-dir {
  font-size: 11.5px;
  color: var(--theme-ink-soft);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1;
}
.aw-hist-chap {
  font-size: 11px;
  color: var(--theme-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 92px;
}
.aw-hist-time {
  font-size: 11px;
  color: var(--theme-muted);
  white-space: nowrap;
}
.aw-hist-snip {
  font-size: 12px;
  color: var(--theme-muted);
  white-space: pre-wrap;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.aw-hist-del {
  position: absolute;
  right: 6px;
  top: 6px;
  border: none;
  background: transparent;
  color: var(--theme-muted);
  font-size: 11px;
  cursor: pointer;
}
.aw-hist-del:hover {
  color: var(--theme-error);
}
.aw-hist-empty {
  font-size: 12px;
  color: var(--theme-muted);
}
.aw-ta {
  resize: none;
  height: 56px;
  width: 100%;
  font-family: var(--font-sans);
  font-size: 13px;
  line-height: 1.6;
  /* 右下角留出语音图标的位置（图标融入框角，不压正文） */
  padding: 8px 38px 8px 10px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
  transition: color 0.3s var(--motion);
}
.aw-ta:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.aw-ta:disabled {
  opacity: 0.6;
}
/* 思考等待中：方向文字已被「带走」，原位淡出 */
.aw-ta.thinking {
  color: transparent;
}
.aw-ta.thinking::placeholder {
  color: transparent;
}
/* 方向文字起飞：threeui 语言 —— 弹簧缓动 + 位移缩放 + 失焦模糊，
   收束到下方的「思考等待中」面板，落点不再生硬 */
.aw-fly {
  position: absolute;
  left: 12px;
  bottom: 12px;
  max-width: calc(100% - 64px);
  font-size: 13px;
  line-height: 1.6;
  color: var(--theme-accent-hover);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
  transform-origin: 20% 100%;
  animation: awFly 0.72s var(--spring) forwards;
}
@keyframes awFly {
  0% {
    opacity: 0;
    transform: translate3d(0, 0, 0) scale(1);
    filter: blur(0);
  }
  20% {
    opacity: 1;
    transform: translate3d(0, 12px, 0) scale(0.97);
  }
  100% {
    opacity: 0;
    transform: translate3d(0, 172px, 0) scale(0.36);
    filter: blur(2.6px);
  }
}
/* 等待面板进场 / 退场：threeui 弹簧 */
.aw-fade-enter-active {
  transition: opacity 0.34s var(--spring), transform 0.4s var(--spring);
}
.aw-fade-enter-from {
  opacity: 0;
  transform: translate3d(0, -12px, 0) scale(0.97);
}
.aw-fade-leave-active {
  transition: opacity 0.28s var(--expo-out), transform 0.28s var(--expo-out);
}
.aw-fade-leave-to {
  opacity: 0;
  transform: translate3d(0, -8px, 0) scale(0.98);
}
/* 输出区进场：从等待态「化开」—— 上浮 + 微缩放 + 由模糊转清晰 */
.aw-rise-enter-active {
  transition: opacity 0.5s var(--expo-out), transform 0.62s var(--spring), filter 0.5s var(--expo-out);
}
.aw-rise-enter-from {
  opacity: 0;
  transform: translate3d(0, 24px, 0) scale(0.985);
  filter: blur(4px);
}
/* 重新生成时旧输出淡出，避免在等待面板出现前「啪」一下消失 */
.aw-rise-leave-active {
  transition: opacity 0.26s var(--expo-out), transform 0.26s var(--expo-out);
}
.aw-rise-leave-to {
  opacity: 0;
  transform: translate3d(0, -10px, 0) scale(0.99);
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
.ln-custom {
  width: 108px;
  font-size: 12px;
  padding: 3px 8px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
}
.ln-custom:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.ln-custom:disabled {
  opacity: 0.5;
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
  /* threeui：弹簧回弹 + 按下微缩 */
  transition: transform var(--dur-base) var(--spring), background 0.25s var(--motion),
    border-color 0.25s var(--motion), color 0.25s var(--motion), box-shadow 0.25s var(--motion);
}
.run:active:not(:disabled),
.stop:active {
  transform: scale(0.95);
  transition-duration: var(--dur-fast);
}
.run {
  position: relative;
  overflow: hidden;
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border: 1px solid var(--theme-solid-bg);
}
/* threeui 扫光：hover 时一道高光掠过 */
.run::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    100deg,
    transparent 28%,
    color-mix(in srgb, var(--theme-solid-fg) 26%, transparent) 50%,
    transparent 72%
  );
  transform: translateX(-130%);
  pointer-events: none;
}
.run:hover:not(:disabled)::after {
  animation: awSheen 0.95s var(--expo-out);
}
.run:hover:not(:disabled) {
  box-shadow: 0 6px 20px color-mix(in srgb, var(--theme-ink) 18%, transparent);
}
@keyframes awSheen {
  to {
    transform: translateX(130%);
  }
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
  /* 1 0 auto：内容短时铺满剩余空间，内容长时撑开、由 .aw 整体滚动 */
  flex: 1 0 auto;
  min-height: 200px;
  display: flex;
  flex-direction: column;
  padding: 10px 14px 14px;
  gap: 8px;
}
.aw-result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.aw-result-cap {
  font-size: 12px;
  color: var(--theme-muted);
  letter-spacing: 1px;
}
.aw-result-close {
  font-size: 11.5px;
  padding: 2px 10px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--theme-muted);
  cursor: pointer;
  transition: all 0.15s var(--motion);
}
.aw-result-close:hover {
  border-color: var(--theme-error);
  color: var(--theme-error);
}
.aw-text {
  /* 由外层 .aw 统一滚动，避免「输出区内部滚 + 面板滚」的双滚动条 */
  flex: none;
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
  transition: transform var(--dur-base) var(--spring), background 0.25s var(--motion);
}
.apply:hover {
  background: var(--theme-solid-hover);
}
.apply:active {
  transform: scale(0.95);
  transition-duration: var(--dur-fast);
}
.cp {
  font-size: 13px;
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--theme-line);
  background: transparent;
  color: var(--theme-ink-soft);
  cursor: pointer;
  transition: transform var(--dur-base) var(--spring), border-color 0.25s var(--motion),
    color 0.25s var(--motion);
}
.cp:active {
  transform: scale(0.95);
  transition-duration: var(--dur-fast);
}
.cp:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
</style>
