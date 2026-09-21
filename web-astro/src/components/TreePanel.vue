<script setup lang="ts">
import { reactive, ref, computed } from 'vue';
import { api } from '../lib/api';
import {
  store,
  openBook,
  openChapter,
  openNewBook,
  openNewVolume,
  openNewChapter,
  trashBook,
  restoreBook,
  deleteChapter,
  restoreChapter,
  deleteVolume,
  restoreVolume,
  saveSettings,
} from '../lib/store';
import RareDeleteButton from './RareDeleteButton.vue';
import RhineDock from './RhineDock.vue';

const ui = reactive<{ newBook: boolean; newVol: Record<number, boolean> }>({ newBook: false, newVol: {} });
const newBook = ref('');
const newVol = reactive<Record<number, string>>({});

function chaptersOf(volId: number | null) {
  if (!store.currentBook) return [];
  return store.currentBook.chapters.filter((c) => (c.volume_id || null) === volId);
}

async function doNewBook() {
  const t = newBook.value.trim();
  if (!t) return;
  newBook.value = '';
  ui.newBook = false;
  await openNewBook(t);
}

async function doNewVol(bookId: number) {
  const t = (newVol[bookId] || '').trim();
  if (!t) return;
  await openNewVolume(bookId, t);
  newVol[bookId] = '';
  ui.newVol[bookId] = false;
}

async function doTrash(id: number) {
  await trashBook(id);
}

// ---- 单章 / 单卷删除（软删进回收站，可恢复） ----
// 交互确认由 RareDeleteButton 原位完成（点垃圾桶 → ✓/✕），这里只负责落库。
async function doDelChapter(ch: { id: number }) {
  await deleteChapter(ch.id);
}
async function doDelVolume(v: { id: number }) {
  await deleteVolume(v.id);
}

const showTrash = ref(false);
const trashEmpty = computed(
  () => !store.trashed.length && !store.trashedVolumes.length && !store.trashedChapters.length
);

const hudOn = computed(() => store.hudEnabled);
async function closeHud() {
  await saveSettings({ hud_enabled: false });
}

// 作品行点击：已展开则收起，否则展开（不再只能展开）
function toggleBook(b: { id: number }) {
  if (store.currentBookId === b.id) {
    store.currentBookId = null;
  } else {
    openBook(b.id);
  }
}

// ---- 拖动排序（卷与章节） ----
// HTML5 原生拖拽：卷在卷列表内排序；章在同卷（或根级）内排序。
// 排完把新 sort_order 逐个 PUT 落库，再 openBook 刷新（后端按 sort_order,id 排序返回）。
const dragInfo = ref<{ kind: 'vol' | 'ch'; id: number; volumeId: number | null } | null>(null);
const dropKey = ref('');
function onDragStart(e: DragEvent, kind: 'vol' | 'ch', id: number, volumeId: number | null) {
  dragInfo.value = { kind, id, volumeId };
  dropKey.value = '';
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(id));
  }
}
function onDragOver(e: DragEvent, kind: 'vol' | 'ch', id: number) {
  if (!dragInfo.value || dragInfo.value.kind !== kind) return;
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
  dropKey.value = kind + ':' + id;
}
function onDragLeave(kind: 'vol' | 'ch', id: number) {
  if (dropKey.value === kind + ':' + id) dropKey.value = '';
}
function onDragEnd() {
  dragInfo.value = null;
  dropKey.value = '';
}
async function onDrop(e: DragEvent, kind: 'vol' | 'ch', volumeId: number | null, targetId: number) {
  e.preventDefault();
  e.stopPropagation();
  const info = dragInfo.value;
  onDragEnd();
  if (!info || info.kind !== kind || info.id === targetId) return;
  const book = store.currentBook;
  if (!book) return;
  if (kind === 'vol') {
    const list = [...book.volumes];
    const from = list.findIndex((v) => v.id === info.id);
    const to = list.findIndex((v) => v.id === targetId);
    if (from < 0 || to < 0) return;
    const [moved] = list.splice(from, 1);
    list.splice(to, 0, moved);
    book.volumes = list;
    await Promise.all(list.map((v, i) => api.updateVolume(v.id, { sort_order: i })));
  } else {
    if ((info.volumeId || null) !== (volumeId || null)) return; // 只允许同层排序
    const list = book.chapters.filter((c) => (c.volume_id || null) === (volumeId || null));
    const from = list.findIndex((c) => c.id === info.id);
    const to = list.findIndex((c) => c.id === targetId);
    if (from < 0 || to < 0) return;
    const [moved] = list.splice(from, 1);
    list.splice(to, 0, moved);
    // 本地先生效（编辑器里当前打开的章不受影响）
    const byId = new Map(book.chapters.map((c) => [c.id, c]));
    list.forEach((c, i) => {
      const t = byId.get(c.id);
      if (t) t.sort_order = i;
    });
    await Promise.all(list.map((c, i) => api.updateChapter(c.id, { sort_order: i })));
  }
  await openBook(book.id);
}
const dragClass = (kind: 'vol' | 'ch', id: number) => ({
  dragging: dragInfo.value?.kind === kind && dragInfo.value.id === id,
  over: dropKey.value === kind + ':' + id,
});
</script>

<template>
  <aside class="panel tree">
    <RhineDock v-if="hudOn" @close="closeHud" />
    <div class="panel-head" :class="{ compact: hudOn }">
      <span class="eyebrow mono">{{ showTrash ? '回收站' : '作品' }}</span>
      <button class="ghost-button" @click="showTrash = !showTrash">
        {{ showTrash ? '返回作品' : '回收站' }}
      </button>
    </div>

    <!-- 回收站视图：作品 / 卷 / 章节 三类，均可原位恢复 -->
    <ul class="list" v-if="showTrash">
      <template v-if="store.trashed.length">
        <li class="trash-sec mono">作品</li>
        <li v-for="b in store.trashed" :key="'b' + b.id" class="trash-row">
          <span class="name">{{ b.title || '未命名' }}</span>
          <span class="meta mono">已删除</span>
          <button class="mini solid" @click="restoreBook(b.id)">恢复</button>
        </li>
      </template>

      <template v-if="store.trashedVolumes.length">
        <li class="trash-sec mono">卷</li>
        <li v-for="v in store.trashedVolumes" :key="'v' + v.id" class="trash-row">
          <span class="name">📖 {{ v.title }}</span>
          <span class="meta mono">{{ v.book_title || '—' }} · 含 {{ v.chapters ?? 0 }} 章</span>
          <button class="mini solid" @click="restoreVolume(v.id)">恢复</button>
        </li>
      </template>

      <template v-if="store.trashedChapters.length">
        <li class="trash-sec mono">章节</li>
        <li v-for="c in store.trashedChapters" :key="'c' + c.id" class="trash-row">
          <span class="name">{{ c.title }}</span>
          <span class="meta mono">
            {{ c.book_title || '—' }}{{ c.volume_title ? ' · ' + c.volume_title : '' }}
          </span>
          <button class="mini solid" @click="restoreChapter(c.id)">恢复</button>
        </li>
      </template>

      <li v-if="trashEmpty" class="empty mono">回收站为空</li>
    </ul>

    <!-- 作品树视图 -->
    <template v-else>
      <div class="tree-new" v-if="ui.newBook">
        <input v-model="newBook" placeholder="作品名" @keyup.enter="doNewBook" />
        <button class="mini solid" @click="doNewBook">建</button>
      </div>
      <ul class="list book-list">
        <li v-for="b in store.books" :key="b.id" class="book-item">
          <div class="book-row" :class="{ active: b.id === store.currentBookId }" @click="toggleBook(b)">
            <span class="caret" :class="{ open: b.id === store.currentBookId }">▸</span>
            <span class="name">{{ b.title || '未命名' }}</span>
            <RareDeleteButton title="删除作品（进回收站）" @confirm="doTrash(b.id)" />
          </div>

          <div v-if="b.id === store.currentBookId && store.currentBook" class="book-children">
            <div
              class="vol"
              v-for="v in store.currentBook.volumes"
              :key="v.id"
            >
              <div
                class="vol-row"
                draggable="true"
                :class="dragClass('vol', v.id)"
                title="拖动可调整卷的顺序"
                @dragstart="onDragStart($event, 'vol', v.id, null)"
                @dragover="onDragOver($event, 'vol', v.id)"
                @dragleave="onDragLeave('vol', v.id)"
                @drop="onDrop($event, 'vol', null, v.id)"
                @dragend="onDragEnd"
              >
                <span class="caret">▾</span>
                <span class="name">📖 {{ v.title }}</span>
                <button class="mini" @click="openNewChapter(v.id)">＋章</button>
                <RareDeleteButton size="sm" title="删除本卷（含其章节）" @confirm="doDelVolume(v)" />
              </div>
              <div
                class="ch"
                v-for="ch in chaptersOf(v.id)"
                :key="ch.id"
                :class="{ active: ch.id === store.currentChapterId, ...dragClass('ch', ch.id) }"
                draggable="true"
                title="拖动可调整章节顺序"
                @click="openChapter(ch.id)"
                @dragstart="onDragStart($event, 'ch', ch.id, v.id)"
                @dragover="onDragOver($event, 'ch', ch.id)"
                @dragleave="onDragLeave('ch', ch.id)"
                @drop="onDrop($event, 'ch', v.id, ch.id)"
                @dragend="onDragEnd"
              >
                <span class="dot">·</span>
                <span class="ch-title">{{ ch.title }}</span>
                <em class="mono">{{ ch.words }}</em>
                <span class="row-del" @click.stop>
                  <RareDeleteButton size="sm" title="删除本章" @confirm="doDelChapter(ch)" />
                </span>
              </div>
              <div class="tree-new" v-if="ui.newVol[v.id]">
                <input
                  :value="newVol[v.id]"
                  @input="newVol[v.id] = ($event.target as HTMLInputElement).value"
                  placeholder="卷名"
                  @keyup.enter="doNewVol(b.id)"
                />
                <button class="mini solid" @click="doNewVol(b.id)">建</button>
              </div>
              <button class="mini add-vol" v-if="!ui.newVol[v.id]" @click="ui.newVol[v.id] = true">＋卷</button>
            </div>

            <!-- 根级（不属于任何卷）章节：同样可拖动排序 -->
            <div
              class="ch"
              v-for="ch in chaptersOf(null)"
              :key="ch.id"
              :class="{ active: ch.id === store.currentChapterId, ...dragClass('ch', ch.id) }"
              draggable="true"
              title="拖动可调整章节顺序"
              @click="openChapter(ch.id)"
              @dragstart="onDragStart($event, 'ch', ch.id, null)"
              @dragover="onDragOver($event, 'ch', ch.id)"
              @dragleave="onDragLeave('ch', ch.id)"
              @drop="onDrop($event, 'ch', null, ch.id)"
              @dragend="onDragEnd"
            >
              <span class="dot">·</span>
              <span class="ch-title">{{ ch.title }}</span>
              <em class="mono">{{ ch.words }}</em>
              <span class="row-del" @click.stop>
                <RareDeleteButton size="sm" title="删除本章" @confirm="doDelChapter(ch)" />
              </span>
            </div>

            <!-- 常驻新增：即使卷/章删光了也能一键补章（补在根级，可再拖进卷） -->
            <button class="mini add-ch" @click="openNewChapter(null)">＋ 新增章节</button>
          </div>
        </li>
        <li v-if="!store.books.length" class="empty mono">暂无作品</li>
      </ul>
      <button class="add-book" @click="ui.newBook = !ui.newBook">＋ 新建作品</button>
    </template>
  </aside>
</template>

<style scoped>
.tree {
  background: color-mix(in srgb, var(--theme-panel) var(--panel-alpha), transparent);
  border: 1px solid var(--theme-line);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.panel-head.compact {
  padding: 8px 12px;
}
.eyebrow {
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--theme-muted);
}
.ghost-button {
  font-size: 12px;
  padding: 3px 10px;
  border: 1px solid var(--theme-line);
  border-radius: 4px;
  background: transparent;
  color: var(--theme-ink-soft);
  transition: all 0.2s var(--motion);
}
.ghost-button:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.list {
  list-style: none;
  margin: 0;
  padding: 8px;
  overflow: auto;
  flex: 1;
}
.book-item {
  margin-bottom: 2px;
}
.book-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 9px 10px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.2s var(--motion);
}
.book-row:hover {
  background: var(--theme-field);
}
.book-row.active {
  border-color: var(--theme-accent);
  background: var(--theme-field);
}
.caret {
  color: var(--theme-muted);
  font-size: 11px;
  transition: transform 0.18s var(--motion);
}
.caret.open {
  transform: rotate(90deg);
}
.name {
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.book-children {
  padding: 2px 0 6px 14px;
}
.vol {
  margin: 2px 0;
}
.vol-row {
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
}
.ch {
  padding: 5px 8px 5px 22px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  color: var(--theme-ink-soft);
  transition: background 0.2s var(--motion);
  display: flex;
  gap: 6px;
  align-items: center;
}
.ch:hover {
  background: var(--theme-field);
}
.ch.active {
  background: var(--theme-field);
  border-left: 2px solid var(--theme-accent);
}
.ch .dot {
  color: var(--theme-muted);
  flex: none;
}
.ch-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ch em {
  font-style: normal;
  font-size: 11px;
  color: var(--theme-muted);
  flex: none;
}
/* 删除按钮平时收起，悬停章节行（或按钮已聚焦/已弹开）才出现，避免目录树变吵 */
.row-del {
  flex: none;
  display: inline-flex;
  opacity: 0;
  transition: opacity 0.18s var(--motion);
}
.ch:hover .row-del,
.row-del:focus-within {
  opacity: 1;
}
.tree-new {
  display: flex;
  gap: 6px;
  padding: 4px 8px;
}
.tree-new input {
  flex: 1;
  font-size: 13px;
  padding: 4px 8px;
  border: 1px solid var(--theme-line);
  border-radius: 4px;
  background: var(--theme-field);
  color: var(--theme-ink);
}
.tree-new input:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.mini {
  font-size: 12px;
  padding: 2px 8px;
  border: 1px solid var(--theme-line);
  border-radius: 4px;
  background: transparent;
  color: var(--theme-ink-soft);
  transition: all 0.2s var(--motion);
}
.mini:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.mini.solid {
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border-color: var(--theme-solid-bg);
}
.mini.solid:hover {
  background: var(--theme-solid-hover);
}
.add-vol {
  margin: 2px 0 4px 22px;
}
/* 常驻新增章节按钮：虚线边框引导，与「新建作品」同视觉语言 */
.add-ch {
  margin: 6px 0 4px 22px;
  border-style: dashed;
  color: var(--theme-muted);
}
.add-ch:hover {
  color: var(--theme-accent-hover);
}
/* 拖动排序视觉反馈：拖起半透明、落点高亮 */
.vol-row {
  cursor: grab;
}
.vol-row:active {
  cursor: grabbing;
}
.dragging {
  opacity: 0.4;
}
.over {
  outline: 1px dashed var(--theme-accent);
  outline-offset: -1px;
  background: color-mix(in srgb, var(--theme-accent) 10%, transparent);
}
.trash-sec {
  font-size: 10.5px;
  letter-spacing: 0.12em;
  color: var(--theme-muted);
  padding: 10px 10px 2px;
  border-bottom: 1px dashed color-mix(in srgb, var(--theme-line) 70%, transparent);
  margin-bottom: 4px;
}
.trash-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 8px;
  align-items: center;
  padding: 9px 10px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
}
.trash-row:hover {
  background: var(--theme-field);
}
.meta {
  font-size: 11px;
  color: var(--theme-muted);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.empty {
  color: var(--theme-muted);
  font-size: 13px;
  padding: 12px;
}
.add-book {
  margin: 8px;
  padding: 9px;
  border: 1px dashed var(--theme-line);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--theme-ink-soft);
  font-size: 13px;
  transition: all 0.2s var(--motion);
}
.add-book:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
</style>
