<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import {
  store,
  refreshBeat,
  addBeat,
  deleteBeat,
  loadBeatMetrics,
  loadBeatSuggest,
} from '../lib/store';
import { BEAT_KINDS, BEAT_KIND_LABEL } from '../lib/api';
import type { BeatKind } from '../lib/api';

const emit = defineEmits<{ (e: 'close'): void }>();

type Tab = 'marks' | 'rhythm' | 'suggest';
const tab = ref<Tab>('marks');

const hasBook = computed(() => !!store.currentBookId);

// 章节下拉
const chapters = computed(() =>
  [...(store.currentBook?.chapters || [])].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
);
const chapterTitle = (id: number) =>
  chapters.value.find((c) => c.id === id)?.title || `第 ${id} 章`;

// 新增标注表单
const addChapter = ref<number>(store.currentChapterId || 0);
const addKind = ref<BeatKind>('payoff');
const addStrength = ref(3);
const addText = ref('');

const canAdd = computed(() => !!addChapter.value);

function strengthStars(n: number): string {
  return '★'.repeat(Math.max(0, Math.min(5, n))) + '☆'.repeat(Math.max(0, 5 - Math.max(0, Math.min(5, n))));
}

// 标注按章节分组
const byChapter = computed(() => {
  const m: Record<number, typeof store.beatMarks> = {};
  for (const b of store.beatMarks) {
    (m[b.chapter_id] ||= []).push(b);
  }
  // 章节顺序
  const ordered: { chapterId: number; title: string; list: typeof store.beatMarks }[] = [];
  for (const c of chapters.value) {
    if (m[c.id]) ordered.push({ chapterId: c.id, title: c.title, list: m[c.id] });
  }
  // 不在当前作品章节里的（防脏数据）
  for (const cid of Object.keys(m)) {
    const id = Number(cid);
    if (!chapters.value.some((c) => c.id === id)) {
      ordered.push({ chapterId: id, title: chapterTitle(id), list: m[id] });
    }
  }
  return ordered;
});

const totalMarks = computed(() => store.beatMarks.length);

async function doAdd() {
  if (!addChapter.value) return;
  const offset = addChapter.value === store.currentChapterId ? store.editorCursor : 0;
  await addBeat(addChapter.value, addKind.value, addStrength.value, offset, addText.value.trim() || null);
  addText.value = '';
}

// 节奏指标
const flatRuns = computed(() => store.beatMetrics?.flat_runs || []);
const deviation = computed(() => store.beatMetrics?.deviation || null);

function intervalsText(): string {
  const iv = store.beatMetrics?.intervals || {};
  const parts: string[] = [];
  for (const k of BEAT_KINDS) {
    if (iv[k] && iv[k].length) {
      parts.push(`${BEAT_KIND_LABEL[k]}：间隔 ${iv[k].join('/')} 章`);
    }
  }
  return parts.length ? parts.join('；') : '暂无间隔数据';
}

// 模板选择
const tplId = computed({
  get: () => store.beatTemplateId,
  set: (v: number | null) => {
    if (v != null) {
      loadBeatMetrics(v);
      loadBeatSuggest(v);
    }
  },
});

async function refreshMetrics() {
  await loadBeatMetrics();
  await loadBeatSuggest();
}

function kindChipColor(k: string): string {
  // 用暖色档案色系区分
  const map: Record<string, string> = {
    payoff: 'var(--theme-accent)',
    reversal: '#c98a3a',
    hook: '#8a6db0',
    pressure: '#b05b4a',
    warmth: '#4a8a6d',
    climax: '#a8405b',
    info: 'var(--theme-muted)',
  };
  return map[k] || 'var(--theme-muted)';
}

watch(
  () => store.currentChapterId,
  (id) => {
    if (id && !addChapter.value) addChapter.value = id;
  }
);

onMounted(async () => {
  if (store.currentChapterId) addChapter.value = store.currentChapterId;
  await refreshBeat();
});
</script>

<template>
  <section class="bt">
    <header class="bt-head">
      <div class="bt-title">爽点节奏</div>
      <button class="x" @click="emit('close')" title="关闭">✕</button>
    </header>

    <nav class="tabs">
      <button class="tab" :class="{ on: tab === 'marks' }" @click="tab = 'marks'">
        标注 <span class="badge">{{ totalMarks }}</span>
      </button>
      <button class="tab" :class="{ on: tab === 'rhythm' }" @click="tab = 'rhythm'">节奏</button>
      <button class="tab" :class="{ on: tab === 'suggest' }" @click="tab = 'suggest'">
        建议 <span class="badge">{{ store.beatSuggestions.length }}</span>
      </button>
    </nav>

    <div v-if="!hasBook" class="bt-err">请先打开一个作品。</div>
    <div v-else-if="store.beatError" class="bt-err">⚠ {{ store.beatError }}</div>

    <div v-if="hasBook" class="bt-body">
      <!-- 标注 -->
      <div v-show="tab === 'marks'" class="pane">
        <div class="new">
          <select v-model.number="addChapter" class="sel">
            <option v-for="c in chapters" :key="c.id" :value="c.id">{{ c.title }}</option>
          </select>
          <select v-model="addKind" class="sel w90">
            <option v-for="k in BEAT_KINDS" :key="k" :value="k">{{ BEAT_KIND_LABEL[k] }}</option>
          </select>
        </div>
        <div class="new">
          <label class="str">强度</label>
          <input v-model.number="addStrength" class="rng" type="range" min="1" max="5" step="1" />
          <span class="stars">{{ strengthStars(addStrength) }}</span>
        </div>
        <input v-model="addText" class="inp full" placeholder="备注（可选，如：此处揭露身世）" />
        <div class="acts">
          <button class="save" :disabled="!canAdd" @click="doAdd">＋ 标注爽点</button>
          <span v-if="addChapter === store.currentChapterId" class="hint">将在当前光标处标记</span>
        </div>

        <div class="board">
          <div v-for="g in byChapter" :key="g.chapterId" class="grp">
            <div class="grp-h">{{ g.title }} <span class="cnt">{{ g.list.length }}</span></div>
            <div v-for="b in g.list" :key="b.id" class="mrow">
              <span class="chip" :style="{ background: kindChipColor(b.kind), borderColor: kindChipColor(b.kind) }">{{ BEAT_KIND_LABEL[b.kind] }}</span>
              <span class="stars sm">{{ strengthStars(b.strength) }}</span>
              <span class="mtxt">{{ b.text || '（无备注）' }}</span>
              <button class="del" @click="deleteBeat(b.id)">删</button>
            </div>
          </div>
          <div v-if="!totalMarks" class="hint">还没有爽点标注，选好章节与类型后点击「标注」。也可在正文里把光标停在想标记的位置再标注。</div>
        </div>
      </div>

      <!-- 节奏 -->
      <div v-show="tab === 'rhythm'" class="pane">
        <div class="new">
          <label class="str">对照模板</label>
          <select v-model.number="tplId" class="sel">
            <option v-for="t in store.beatTemplates" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
          <button class="act sm" @click="refreshMetrics">刷新</button>
        </div>

        <div v-if="deviation" class="warn">
          与模板「{{ deviation.template }}」偏离 <b>{{ deviation.misses }}</b> 处（高重要节点缺爽点）。
        </div>
        <div v-else class="hint">未选模板或未偏离。</div>

        <div class="hint">逐章爽点统计（数量 / 平均强度 / 类型）：</div>
        <div class="tbl">
          <div class="tr th">
            <span class="c1">章节</span>
            <span class="c2">数量</span>
            <span class="c3">均强</span>
            <span class="c4">类型</span>
          </div>
          <div v-for="pc in store.beatMetrics?.per_chapter" :key="pc.chapter_id" class="tr">
            <span class="c1">{{ pc.title || ('第 ' + pc.chapter_id + ' 章') }}</span>
            <span class="c2">{{ pc.count }}</span>
            <span class="c3">{{ pc.avg_strength || '—' }}</span>
            <span class="c4">
              <span v-for="k in pc.kinds" :key="k" class="ktag" :style="{ color: kindChipColor(k) }">{{ BEAT_KIND_LABEL[k] }}</span>
              <span v-if="!pc.kinds.length" class="muted">无</span>
            </span>
          </div>
        </div>

        <div v-if="flatRuns.length" class="flat">
          <div class="hint">连续平淡段（建议插入爽点）：</div>
          <div v-for="(r, i) in flatRuns" :key="i" class="flat-row">
            {{ r.end_chapter || '结尾' }} 之前连续 {{ r.length }} 字无爽点
          </div>
        </div>
        <div v-else class="hint">未检测到连续平淡段。</div>

        <div class="hint">类型间隔：{{ intervalsText() }}</div>
      </div>

      <!-- 建议 -->
      <div v-show="tab === 'suggest'" class="pane">
        <div class="hint">基于模板节奏与平淡段给出的插入建议。</div>
        <div class="rel-list">
          <div v-for="(s, i) in store.beatSuggestions" :key="i" class="sug-row">
            <span class="chip" :style="{ background: kindChipColor(s.kind), borderColor: kindChipColor(s.kind) }">{{ BEAT_KIND_LABEL[s.kind] }}</span>
            <div class="sug-body">
              <div class="sug-ch">{{ s.chapter || '全书' }}<span v-if="s.position_words" class="pos">（约第 {{ s.position_words }} 字）</span></div>
              <div class="sug-reason">{{ s.reason }}</div>
            </div>
          </div>
          <div v-if="!store.beatSuggestions.length" class="hint">暂无明显节奏问题，保持得不错。</div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.bt {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.bt-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.bt-title {
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
.tabs {
  display: flex;
  gap: 4px;
  padding: 8px 12px 0;
  flex-wrap: wrap;
}
.tab {
  font-size: 12px;
  padding: 5px 11px;
  border: 1px solid var(--theme-line);
  border-radius: 4px;
  background: transparent;
  color: var(--theme-muted);
  cursor: pointer;
  transition: all 0.2s var(--motion);
}
.tab.on {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
  background: var(--theme-field);
}
.badge {
  font-family: var(--font-mono);
  font-size: 10px;
  background: var(--theme-field);
  border: 1px solid var(--theme-line);
  border-radius: 8px;
  padding: 0 5px;
  margin-left: 2px;
}
.bt-err {
  color: var(--theme-error);
  font-size: 12px;
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
  padding: 6px 10px;
  margin: 8px 14px 0;
  border-radius: var(--radius-sm);
}
.bt-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.pane {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.new {
  display: flex;
  gap: 8px;
  align-items: center;
}
.sel {
  font-size: 13px;
  padding: 6px 8px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
}
.sel.w90 {
  width: 96px;
}
.str {
  font-size: 11.5px;
  color: var(--theme-muted);
}
.rng {
  flex: 1;
  accent-color: var(--theme-accent);
}
.inp {
  font-size: 13px;
  padding: 6px 9px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
}
.inp.full {
  width: 100%;
}
.inp:focus,
.sel:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.acts {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.save,
.act {
  font-size: 13px;
  padding: 6px 13px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.2s var(--motion);
}
.save {
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border: 1px solid var(--theme-solid-bg);
}
.save:hover {
  background: var(--theme-solid-hover);
}
.save:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.act {
  background: transparent;
  border: 1px solid var(--theme-line);
  color: var(--theme-ink-soft);
}
.act:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.act.sm {
  font-size: 12px;
  padding: 3px 10px;
}
.stars {
  font-size: 12px;
  color: var(--theme-accent);
  font-family: var(--font-mono);
  letter-spacing: 1px;
}
.stars.sm {
  font-size: 10px;
}
.board {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.grp {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.grp-h {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 9px;
  background: var(--theme-field);
  font-size: 12px;
  color: var(--theme-muted);
}
.cnt {
  font-family: var(--font-mono);
}
.mrow {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 9px;
  border-top: 1px solid var(--theme-line);
  font-size: 13px;
  color: var(--theme-ink-soft);
}
.chip {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 10px;
  border: 1px solid;
  color: #fff;
  white-space: nowrap;
}
.mtxt {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.del {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: 1px solid var(--theme-error);
  color: var(--theme-error);
  cursor: pointer;
}
.warn {
  font-size: 12.5px;
  color: var(--theme-error);
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--theme-error) 40%, transparent);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
}
.tbl {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.tr {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 9px;
  font-size: 12.5px;
  border-top: 1px solid var(--theme-line);
  color: var(--theme-ink-soft);
}
.tr.th {
  background: var(--theme-field);
  color: var(--theme-muted);
  border-top: none;
}
.tr .c1 {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tr .c2,
.tr .c3 {
  width: 40px;
  text-align: center;
  font-family: var(--font-mono);
}
.tr .c4 {
  width: 120px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.ktag {
  font-size: 11px;
}
.muted {
  color: var(--theme-muted);
}
.flat {
  border: 1px solid color-mix(in srgb, var(--theme-error) 35%, var(--theme-line));
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  background: color-mix(in srgb, var(--theme-error) 8%, transparent);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.flat-row {
  font-size: 12.5px;
  color: var(--theme-ink-soft);
}
.rel-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sug-row {
  display: flex;
  gap: 8px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  background: var(--theme-field);
}
.sug-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.sug-ch {
  font-size: 13px;
  color: var(--theme-ink);
}
.pos {
  color: var(--theme-muted);
  font-size: 11px;
  font-family: var(--font-mono);
}
.sug-reason {
  font-size: 12px;
  color: var(--theme-ink-soft);
}
.hint {
  font-size: 12px;
  color: var(--theme-muted);
}
</style>
