<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import {
  store,
  openForeshadow,
  createForeshadow,
  saveForeshadow,
  deleteForeshadow,
  foreshadowAction,
  scanForeshadow,
} from '../lib/store';
import type { Foreshadow, ForeshadowAction } from '../lib/api';
import RareDeleteButton from './RareDeleteButton.vue';

const emit = defineEmits<{ (e: 'close'): void }>();

type Tab = 'board' | 'inject' | 'scan';
const tab = ref<Tab>('board');

const STATUS_LABEL: Record<string, string> = {
  planned: '计划中',
  planted: '已埋设',
  called: '已调用',
  resolved: '已回收',
  abandoned: '已废弃',
};
const ACTION_LABEL: Record<ForeshadowAction, string> = {
  create: '新建',
  plant: '埋设',
  call: '调用',
  resolve: '回收',
  abandon: '废弃',
  reopen: '复活',
};

// 新建缓冲
const nTitle = ref('');
const nContent = ref('');
const nImportance = ref(3);
const nKeywords = ref('');

// 编辑缓冲
const eTitle = ref('');
const eContent = ref('');
const eImportance = ref(3);
const eKeywords = ref('');
const actNote = ref('');

// 扫描
const scanText = ref('');

const hasBook = computed(() => !!store.currentBookId);
const cur = computed(() => store.foreshadowCurrent as Foreshadow | null);

const sorted = computed(() =>
  [...store.foreshadows].sort((a, b) => (Number(b.importance) || 0) - (Number(a.importance) || 0))
);

const byStatus = computed(() => {
  const m: Record<string, Foreshadow[]> = {};
  for (const f of store.foreshadows) {
    const s = f.status || 'planned';
    (m[s] ||= []).push(f);
  }
  return m;
});

function loadBuf(f: Foreshadow | null) {
  if (!f) return;
  eTitle.value = f.title || '';
  eContent.value = f.content || '';
  eImportance.value = Number(f.importance) || 3;
  eKeywords.value = f.keywords || '';
  actNote.value = '';
}

watch(
  () => store.currentForeshadowId,
  () => loadBuf(cur.value)
);

async function pick(f: Foreshadow) {
  await openForeshadow(f.id);
  loadBuf(cur.value);
}

async function newFs() {
  const t = nTitle.value.trim();
  if (!t) return;
  await createForeshadow(t, nContent.value.trim() || null, Number(nImportance.value) || 3, nKeywords.value.trim() || null);
  nTitle.value = '';
  nContent.value = '';
  nKeywords.value = '';
  nImportance.value = 3;
}

async function saveFs() {
  if (!store.currentForeshadowId) return;
  await saveForeshadow(store.currentForeshadowId, {
    title: eTitle.value.trim(),
    content: eContent.value.trim() || null,
    importance: Number(eImportance.value) || 3,
    keywords: eKeywords.value.trim() || null,
  });
}

async function delFs() {
  if (!store.currentForeshadowId) return;
  await deleteForeshadow(store.currentForeshadowId);
}

async function doAction(act: ForeshadowAction) {
  if (!store.currentForeshadowId) return;
  await foreshadowAction(store.currentForeshadowId, act, store.currentChapterId, actNote.value.trim() || null);
}

async function doScan() {
  await scanForeshadow(scanText.value);
}

async function resolveFromScan(id: number) {
  await foreshadowAction(id, 'resolve', store.currentChapterId, '扫描命中自动回收');
  await scanForeshadow(scanText.value);
}
</script>

<template>
  <section class="fs">
    <header class="fs-head">
      <div class="fs-title">伏笔</div>
      <button class="x" @click="emit('close')" title="关闭">✕</button>
    </header>

    <nav class="tabs">
      <button class="tab" :class="{ on: tab === 'board' }" @click="tab = 'board'">看板</button>
      <button class="tab" :class="{ on: tab === 'inject' }" @click="tab = 'inject'">写作注入</button>
      <button class="tab" :class="{ on: tab === 'scan' }" @click="tab = 'scan'">回收扫描</button>
    </nav>

    <div v-if="!hasBook" class="fs-err">请先打开一个作品。</div>
    <div v-else-if="store.foresightError" class="fs-err">⚠ {{ store.foresightError }}</div>

    <div v-if="hasBook" class="fs-body">
      <!-- 看板 -->
      <div v-show="tab === 'board'" class="pane">
        <div class="new">
          <input v-model="nTitle" class="inp" placeholder="伏笔标题" />
          <input v-model.number="nImportance" class="inp w60" type="number" min="1" max="5" title="重要度 1-5" />
          <button class="add" :disabled="!nTitle.trim()" @click="newFs">＋ 新建</button>
        </div>
        <input v-model="nKeywords" class="inp full" placeholder="关键词（逗号分隔，用于回收扫描）" />
        <textarea v-model="nContent" class="ta" rows="2" placeholder="伏笔内容 / 设定（可选）"></textarea>

        <div class="board">
          <div v-for="(list, s) in byStatus" :key="s" class="grp">
            <div class="grp-h"><span class="st" :class="s">{{ STATUS_LABEL[s] || s }}</span> <span class="cnt">{{ list.length }}</span></div>
            <div
              v-for="f in list"
              :key="f.id"
              class="row"
              :class="{ on: f.id === store.currentForeshadowId }"
              @click="pick(f)"
            >
              <b>{{ f.title }}</b>
              <span class="imp">★{{ f.importance }}</span>
              <span v-if="f.keywords" class="kw">{{ f.keywords }}</span>
            </div>
          </div>
          <div v-if="!sorted.length" class="hint">还没有伏笔，先新建一个吧。</div>
        </div>

        <div v-if="cur" class="detail">
          <div class="detail-h">
            <span>编辑：{{ cur.title }}</span>
            <RareDeleteButton @confirm="delFs" />
          </div>
          <label class="lbl">标题</label>
          <input v-model="eTitle" class="inp" />
          <label class="lbl">关键词（逗号分隔）</label>
          <input v-model="eKeywords" class="inp" placeholder="如：玉佩，旧伤" />
          <label class="lbl">重要度（1-5）</label>
          <input v-model.number="eImportance" class="inp w60" type="number" min="1" max="5" />
          <label class="lbl">内容 / 设定</label>
          <textarea v-model="eContent" class="ta" rows="3"></textarea>

          <div class="acts">
            <button class="save" @click="saveFs">保存</button>
          </div>

          <div class="life">
            <div class="life-h">生命周期动作</div>
            <div class="acts">
              <button class="act" :disabled="cur.status === 'planted'" @click="doAction('plant')">{{ ACTION_LABEL.plant }}</button>
              <button class="act" :disabled="cur.status === 'called'" @click="doAction('call')">{{ ACTION_LABEL.call }}</button>
              <button class="act" :disabled="cur.status === 'resolved'" @click="doAction('resolve')">{{ ACTION_LABEL.resolve }}</button>
              <button class="act" :disabled="cur.status === 'abandoned'" @click="doAction('abandon')">{{ ACTION_LABEL.abandon }}</button>
              <button class="act" @click="doAction('reopen')">{{ ACTION_LABEL.reopen }}</button>
            </div>
            <input v-model="actNote" class="inp full" placeholder="动作备注（可选）" />
          </div>

          <div class="ev">
            <div class="life-h">事件时间线</div>
            <div v-for="ev in store.foreshadowEvents" :key="ev.id" class="ev-row">
              <span class="ev-act">{{ ACTION_LABEL[ev.action as ForeshadowAction] || ev.action }}</span>
              <span class="ev-meta">第 {{ ev.chapter_id }} 章</span>
              <span v-if="ev.note" class="ev-note">{{ ev.note }}</span>
            </div>
            <div v-if="!store.foreshadowEvents.length" class="hint">暂无事件。</div>
          </div>
        </div>
      </div>

      <!-- 写作注入 -->
      <div v-show="tab === 'inject'" class="pane">
        <div class="hint">写作时自动注入「计划中 / 已埋设」的伏笔清单（按重要度降序），供 AI 参考。</div>
        <pre class="inject">{{ store.foreshadowInjection || '（暂无待注入伏笔）' }}</pre>
      </div>

      <!-- 回收扫描 -->
      <div v-show="tab === 'scan'" class="pane">
        <div class="hint">把正文粘贴进来，扫描已埋设 / 已调用伏笔的关键词命中，提示可标记回收。</div>
        <textarea v-model="scanText" class="ta big" placeholder="粘贴正文段落…"></textarea>
        <div class="acts">
          <button class="save" @click="doScan">扫描命中</button>
        </div>
        <div class="rel-list">
          <div v-for="m in store.foreshadowScan" :key="m.id" class="scan-row">
            <div><b>{{ m.title }}</b> <span class="st" :class="m.status">{{ STATUS_LABEL[m.status] || m.status }}</span></div>
            <div class="muted">命中：{{ m.matched.join('、') }}</div>
            <button class="act sm" @click="resolveFromScan(m.id)">标记回收</button>
          </div>
          <div v-if="!store.foreshadowScan.length" class="hint">没有命中。</div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.fs {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.fs-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.fs-title {
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
.fs-err {
  color: var(--theme-error);
  font-size: 12px;
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
  padding: 6px 10px;
  margin: 8px 14px 0;
  border-radius: var(--radius-sm);
}
.fs-body {
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
.inp.w60 {
  width: 64px;
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
.act:hover:not(:disabled) {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.act:disabled {
  opacity: 0.35;
  cursor: not-allowed;
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
.ta.big {
  min-height: 120px;
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
.imp {
  color: var(--theme-accent);
  font-size: 11px;
}
.kw {
  color: var(--theme-muted);
  font-size: 11px;
  margin-left: auto;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 45%;
}
.st {
  font-size: 10.5px;
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid var(--theme-line);
  color: var(--theme-muted);
}
.st.planned {
  border-color: var(--theme-line);
  color: var(--theme-muted);
}
.st.planted {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.st.called {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.st.resolved {
  border-color: var(--theme-success);
  color: var(--theme-success);
}
.st.abandoned {
  border-color: var(--theme-error);
  color: var(--theme-error);
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
.life,
.ev {
  border-top: 1px dashed var(--theme-line);
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.life-h {
  font-size: 12px;
  color: var(--theme-muted);
}
.ev-row {
  display: flex;
  gap: 8px;
  align-items: baseline;
  font-size: 12px;
  color: var(--theme-ink-soft);
}
.ev-act {
  color: var(--theme-accent);
  font-weight: 600;
}
.ev-meta {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--theme-muted);
}
.ev-note {
  color: var(--theme-muted);
}
.inject {
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--theme-field);
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 10px;
  color: var(--theme-ink-soft);
  margin: 0;
}
.rel-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.scan-row {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  background: var(--theme-field);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.muted {
  color: var(--theme-muted);
  font-size: 12px;
}
.act.sm {
  font-size: 12px;
  padding: 3px 10px;
  align-self: flex-start;
}
.hint {
  font-size: 12px;
  color: var(--theme-muted);
}
</style>
