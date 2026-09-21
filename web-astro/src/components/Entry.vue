<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import {
  store,
  openEntry,
  createEntry,
  saveEntry,
  deleteEntry,
  extractEntries,
  normalizeEntries,
  aliasesOfEntry,
} from '../lib/store';
import RareDeleteButton from './RareDeleteButton.vue';
import type { Entry } from '../lib/api';

const emit = defineEmits<{ (e: 'close'): void }>();

type Tab = 'lib' | 'extract' | 'normalize';
const tab = ref<Tab>('lib');

// 编辑缓冲
const eName = ref('');
const eCategory = ref('');
const eAliases = ref('');
const eDescription = ref('');

// 新建
const nName = ref('');
const nCategory = ref('');
const nAliases = ref('');
const nDescription = ref('');

const hasBook = computed(() => !!store.currentBookId);
const cur = computed(() => store.entryCurrent as Entry | null);

const sorted = computed(() => [...store.entries].sort((a, b) => (a.id || 0) - (b.id || 0)));

const byCategory = computed(() => {
  const m: Record<string, Entry[]> = {};
  for (const e of store.entries) {
    const c = e.category || '未分类';
    (m[c] ||= []).push(e);
  }
  return m;
});

function loadBuf(e: Entry | null) {
  if (!e) return;
  eName.value = e.name || '';
  eCategory.value = e.category || '';
  eAliases.value = aliasesOfEntry(e).join('，');
  eDescription.value = e.description || '';
}

watch(
  () => store.currentEntryId,
  () => loadBuf(cur.value)
);

async function pick(e: Entry) {
  await openEntry(e.id);
  loadBuf(cur.value);
}

async function newEntry() {
  const t = nName.value.trim();
  if (!t) return;
  const aliases = nAliases.value.split(/[，,]/).map((s) => s.trim()).filter(Boolean);
  await createEntry(t, nCategory.value.trim() || null, aliases, nDescription.value.trim() || null);
  nName.value = '';
  nAliases.value = '';
  nDescription.value = '';
}

async function saveEn() {
  if (!store.currentEntryId) return;
  const aliases = eAliases.value.split(/[，,]/).map((s) => s.trim()).filter(Boolean);
  await saveEntry(store.currentEntryId, {
    name: eName.value.trim(),
    category: eCategory.value.trim() || null,
    aliases,
    description: eDescription.value.trim() || null,
  });
}

async function delEn() {
  if (!store.currentEntryId) return;
  await deleteEntry(store.currentEntryId);
}

async function doExtract() {
  const texts = store.currentChapter?.content ? [store.currentChapter.content] : undefined;
  await extractEntries(texts);
}

async function addFromCandidate(word: string) {
  await createEntry(word);
  await extractEntries(store.currentChapter?.content ? [store.currentChapter.content] : undefined);
}

async function doNormalize() {
  await normalizeEntries();
}

const normalizeTotal = computed(() => {
  const r = store.entryNormalize;
  if (!r) return 0;
  return Object.values(r).reduce((a, b) => a + (b || 0), 0);
});
</script>

<template>
  <section class="en">
    <header class="en-head">
      <div class="en-title">词条</div>
      <button class="x" @click="emit('close')" title="关闭">✕</button>
    </header>

    <nav class="tabs">
      <button class="tab" :class="{ on: tab === 'lib' }" @click="tab = 'lib'">词条库</button>
      <button class="tab" :class="{ on: tab === 'extract' }" @click="tab = 'extract'">抽取候选</button>
      <button class="tab" :class="{ on: tab === 'normalize' }" @click="tab = 'normalize'">异写归一</button>
    </nav>

    <div v-if="!hasBook" class="en-err">请先打开一个作品。</div>
    <div v-else-if="store.entryError" class="en-err">⚠ {{ store.entryError }}</div>

    <div v-if="hasBook" class="en-body">
      <!-- 词条库 -->
      <div v-show="tab === 'lib'" class="pane">
        <div class="new">
          <input v-model="nName" class="inp" placeholder="词条名" />
          <input v-model="nCategory" class="inp w100" placeholder="分类（可选）" />
          <button class="add" :disabled="!nName.trim()" @click="newEntry">＋ 新建</button>
        </div>
        <input v-model="nAliases" class="inp full" placeholder="异写别名（逗号分隔）" />
        <textarea v-model="nDescription" class="ta" rows="2" placeholder="释义 / 设定（可选）"></textarea>

        <div class="board">
          <div v-for="(list, c) in byCategory" :key="c" class="grp">
            <div class="grp-h">{{ c }} <span class="cnt">{{ list.length }}</span></div>
            <div
              v-for="e in list"
              :key="e.id"
              class="row"
              :class="{ on: e.id === store.currentEntryId }"
              @click="pick(e)"
            >
              <b>{{ e.name }}</b>
              <span v-if="aliasesOfEntry(e).length" class="kw">＝{{ aliasesOfEntry(e).join('，') }}</span>
            </div>
          </div>
          <div v-if="!sorted.length" class="hint">还没有词条，先新建一个吧。</div>
        </div>

        <div v-if="cur" class="detail">
          <div class="detail-h">
            <span>编辑：{{ cur.name }}</span>
            <RareDeleteButton @confirm="delEn" />
          </div>
          <label class="lbl">词条名</label>
          <input v-model="eName" class="inp" />
          <label class="lbl">分类</label>
          <input v-model="eCategory" class="inp" />
          <label class="lbl">异写别名（逗号分隔）</label>
          <input v-model="eAliases" class="inp" placeholder="如：小公爷，世子" />
          <label class="lbl">释义 / 设定</label>
          <textarea v-model="eDescription" class="ta" rows="3"></textarea>
          <div class="acts">
            <button class="save" @click="saveEn">保存</button>
          </div>
        </div>
      </div>

      <!-- 抽取候选 -->
      <div v-show="tab === 'extract'" class="pane">
        <div class="hint">对当前章节正文做新词发现（2-4 字 CJK n-gram 词频，剔除停用字与已有词条），列出候选词条。</div>
        <div class="acts">
          <button class="save" :disabled="!store.currentChapter" @click="doExtract">抽取当前章节候选</button>
        </div>
        <div v-if="!store.currentChapter" class="hint">打开一个章节后即可抽取其正文。</div>
        <div class="rel-list">
          <div v-for="c in store.entryCandidates" :key="c.word" class="cand-row">
            <span class="cw">{{ c.word }}</span>
            <span class="cc">×{{ c.count }}</span>
            <button class="act sm" @click="addFromCandidate(c.word)">＋ 收录</button>
          </div>
          <div v-if="!store.entryCandidates.length" class="hint">暂无候选。</div>
        </div>
      </div>

      <!-- 异写归一 -->
      <div v-show="tab === 'normalize'" class="pane">
        <div class="hint">把正文中出现的异写别名统一替换为规范词形（词条别名→词条名），返回各章替换次数。</div>
        <div class="acts">
          <button class="save" @click="doNormalize">归一化全书异写</button>
        </div>
        <div v-if="store.entryNormalize" class="norm">
          <div class="norm-h">共替换 {{ normalizeTotal }} 处</div>
          <div v-for="(n, cid) in store.entryNormalize" :key="cid" class="norm-row">
            第 {{ cid }} 章：{{ n }} 处
          </div>
        </div>
        <div v-else class="hint">尚未运行。</div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.en {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.en-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.en-title {
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
.en-err {
  color: var(--theme-error);
  font-size: 12px;
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
  padding: 6px 10px;
  margin: 8px 14px 0;
  border-radius: var(--radius-sm);
}
.en-body {
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
}
.inp {
  font-size: 13px;
  padding: 6px 9px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
}
.inp.w100 {
  width: 110px;
}
.inp.full {
  width: 100%;
}
.inp:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.add,
.save,
.act,
.del {
  font-size: 13px;
  padding: 6px 13px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.2s var(--motion);
}
.add,
.save {
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border: 1px solid var(--theme-solid-bg);
}
.add:hover:not(:disabled),
.save:hover {
  background: var(--theme-solid-hover);
}
.add:disabled {
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
.del {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: 1px solid var(--theme-error);
  color: var(--theme-error);
  cursor: pointer;
}
.ta {
  font-family: var(--font-sans);
  font-size: 13px;
  line-height: 1.6;
  padding: 7px 9px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-paper);
  color: var(--theme-ink);
  resize: vertical;
}
.ta:focus {
  outline: none;
  border-color: var(--theme-accent);
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
.row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 9px;
  border-top: 1px solid var(--theme-line);
  cursor: pointer;
  font-size: 13px;
  color: var(--theme-ink-soft);
}
.row:hover {
  background: var(--theme-field);
}
.row.on {
  background: var(--theme-field);
  color: var(--theme-ink);
}
.kw {
  color: var(--theme-muted);
  font-size: 11px;
  margin-left: auto;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 50%;
}
.detail {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 12px;
  background: var(--theme-field);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.detail-h {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: var(--theme-ink);
}
.lbl {
  font-size: 11.5px;
  color: var(--theme-muted);
}
.acts {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.rel-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cand-row {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 6px 9px;
  background: var(--theme-field);
  font-size: 13px;
  color: var(--theme-ink-soft);
}
.cw {
  color: var(--theme-ink);
  font-weight: 600;
}
.cc {
  color: var(--theme-muted);
  font-family: var(--font-mono);
  font-size: 11px;
}
.act.sm {
  font-size: 12px;
  padding: 3px 10px;
  margin-left: auto;
}
.norm {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 10px;
  background: var(--theme-field);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.norm-h {
  font-size: 13px;
  color: var(--theme-ink);
}
.norm-row {
  font-size: 12px;
  color: var(--theme-ink-soft);
}
.hint {
  font-size: 12px;
  color: var(--theme-muted);
}
</style>
