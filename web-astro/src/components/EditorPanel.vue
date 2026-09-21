<script setup lang="ts">
import { ref, watch, computed, onMounted, onBeforeUnmount } from 'vue';
import {
  store,
  saveChapter,
  makeSnapshot,
  pushHistory,
  undoHistory,
  redoHistory,
  loadHistoryStatus,
  loadPreview,
  runTypeset,
  applyTypeset,
} from '../lib/store';
import FindReplace from './FindReplace.vue';
import PhonePreview from './PhonePreview.vue';
import SnapshotPanel from './SnapshotPanel.vue';
import AiSession from './AiSession.vue';
import AiWrite from './AiWrite.vue';
import Knowledge from './Knowledge.vue';
import Persona from './Persona.vue';
import Framework from './Framework.vue';
import Character from './Character.vue';
import Foreshadow from './Foreshadow.vue';
import Entry from './Entry.vue';
import Beat from './Beat.vue';
import Stats from './Stats.vue';
import Tools from './Tools.vue';
import Roles from './Roles.vue';
import RareCounter from './RareCounter.vue';
import { vMagnetRail } from '../lib/rare';

const title = ref('');
const content = ref('');
let timer: ReturnType<typeof setTimeout> | null = null;
let histTimer: ReturnType<typeof setTimeout> | null = null;
let previewTimer: ReturnType<typeof setTimeout> | null = null;
const showFind = ref(false);
// 视图模式：编辑 / 预览 / 分屏（两者同时）
const viewMode = ref<'edit' | 'preview' | 'split'>('edit');
const showPreview = computed(() => viewMode.value !== 'edit');
const showEditor = computed(() => viewMode.value !== 'preview');
const showSnapshots = ref(false);
const showAi = ref(false);
const showAiWrite = ref(false);
const showKb = ref(false);
const showPersona = ref(false);
const showFramework = ref(false);
const showCharacter = ref(false);
const showForeshadow = ref(false);
const showEntry = ref(false);
const showBeat = ref(false);
const showStats = ref(false);
const showTools = ref(false);
const showRoles = ref(false);
const cursorIndex = ref(-1);
const selStart = ref(0);
const selEnd = ref(0);

watch(
  () => store.currentChapterId,
  async (id) => {
    if (id && store.currentChapter) {
      title.value = store.currentChapter.title || '';
      content.value = store.currentChapter.content || '';
      await loadHistoryStatus();
      if (showPreview.value) refreshPreview();
    }
  }
);

const words = computed(() => (content.value || '').replace(/\s/g, '').length);
const canUndo = computed(() => !!store.historyStatus?.can_undo);
const canRedo = computed(() => !!store.historyStatus?.can_redo);

function onInput() {
  store.saveStatus = 'unsaved';
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => commit(), 1500);
  if (histTimer) clearTimeout(histTimer);
  histTimer = setTimeout(() => pushHistory(content.value, '编辑'), 1500);
  if (showPreview.value) {
    if (previewTimer) clearTimeout(previewTimer);
    previewTimer = setTimeout(() => refreshPreview(), 200);
  }
}

function onCursor(e: Event) {
  const target = e.target as HTMLTextAreaElement;
  const start = target.selectionStart || 0;
  const end = target.selectionEnd || 0;
  const before = content.value.slice(0, start);
  cursorIndex.value = Math.max(0, before.split('\n').filter((s) => s.trim()).length - 1);
  store.editorCursor = start;
  selStart.value = start;
  selEnd.value = end;
}

async function applyAiText(payload: {
  mode: 'replace' | 'insert' | 'whole';
  text: string;
  selStart?: number;
  selEnd?: number;
  pos?: number;
}) {
  if (!store.currentChapterId) return;
  const full = content.value;
  let next = full;
  if (payload.mode === 'replace') {
    const s = payload.selStart ?? 0;
    const e = payload.selEnd ?? full.length;
    next = full.slice(0, s) + payload.text + full.slice(e);
  } else if (payload.mode === 'insert') {
    const p = payload.pos ?? selStart.value;
    next = full.slice(0, p) + payload.text + full.slice(p);
  } else if (payload.mode === 'whole') {
    next = payload.text;
  }
  // 先留历史，保证可撤销
  await pushHistory(full, 'AI 操作前');
  content.value = next;
  await saveChapter({ title: title.value, content: next });
  if (showPreview.value) await refreshPreview();
}

async function refreshPreview() {
  await loadPreview(content.value);
}

async function setView(mode: 'edit' | 'preview' | 'split') {
  viewMode.value = mode;
  // 切到含预览的模式时总是重取，否则会停留在旧内容的预览
  if (mode !== 'edit' && store.currentChapterId) await refreshPreview();
}

async function doTypeset() {
  typesetTip.value = '';
  if (!store.currentChapterId) {
    typesetTip.value = '请先打开一个章节';
    return;
  }
  try {
    const r = await runTypeset(content.value);
    if (r && r.length) {
      viewMode.value = 'edit';
      typesetTip.value = `发现 ${r.length} 处可排版（见下方建议，可应用或忽略）`;
    } else {
      typesetTip.value = '未发现需要排版的地方 ✓';
      setTimeout(() => (typesetTip.value = ''), 2500);
    }
  } catch (e) {
    typesetTip.value = '排版失败：' + ((e as Error)?.message || '未知错误');
  }
}

async function doApplyTypeset() {
  const n = store.typesetChanges.length;
  try {
    const nc = await applyTypeset(content.value);
    if (nc == null) {
      typesetTip.value = '应用排版失败，请重试';
      return;
    }
    content.value = nc;
    await saveChapter({ title: title.value, content: content.value });
    typesetTip.value = `已应用 ${n} 处排版并保存 ✓`;
    setTimeout(() => (typesetTip.value = ''), 2500);
  } catch (e) {
    typesetTip.value = '应用排版失败：' + ((e as Error)?.message || '未知错误');
  }
}

async function commit() {
  if (!store.currentChapterId) return;
  await saveChapter({ title: title.value, content: content.value });
}

async function flush() {
  if (timer) clearTimeout(timer);
  await commit();
}

async function doUndo() {
  const prev = await undoHistory();
  if (prev === null || prev === undefined) return;
  content.value = prev;
  await saveChapter({ title: title.value, content: content.value });
}

async function doRedo() {
  const next = await redoHistory();
  if (next === null || next === undefined) return;
  content.value = next;
  await saveChapter({ title: title.value, content: content.value });
}

function onKey(e: KeyboardEvent) {
  if (!(e.ctrlKey || e.metaKey)) return;
  const k = e.key.toLowerCase();
  if (k === 's') {
    e.preventDefault();
    flush();
  } else if (k === 'f') {
    e.preventDefault();
    showFind.value = !showFind.value;
  } else if (k === 'z' && !e.shiftKey) {
    e.preventDefault();
    doUndo();
  } else if ((k === 'z' && e.shiftKey) || k === 'y') {
    e.preventDefault();
    doRedo();
  }
}

onMounted(() => window.addEventListener('keydown', onKey));
onBeforeUnmount(() => window.removeEventListener('keydown', onKey));
</script>

<template>
  <main class="panel editor">
    <div v-if="!store.currentChapter" class="empty">从左侧选择或新建一个章节开始写作</div>
    <template v-else>
      <div class="editor-bar" v-magnet-rail="{ selector: 'button', strength: 6, scale: 1.08 }">
        <button class="tb" :disabled="!canUndo" @click="doUndo" title="撤回 (Ctrl+Z)">⟲ 撤回</button>
        <button class="tb" :disabled="!canRedo" @click="doRedo" title="重做 (Ctrl+Shift+Z)">⟳ 重做</button>
        <button class="tb" :class="{ on: showFind }" @click="showFind = !showFind">查找替换</button>
        <button class="tb" @click="doTypeset">一键排版</button>
        <button class="tb" :class="{ on: showSnapshots }" @click="showSnapshots = !showSnapshots">章节快照</button>
        <button class="tb" :class="{ on: showAi }" @click="showAi = !showAi">AI 协作</button>
        <button class="tb" :class="{ on: showAiWrite }" @click="showAiWrite = !showAiWrite">AI 写作</button>
        <button class="tb" :class="{ on: showKb }" @click="showKb = !showKb">知识库</button>
        <button class="tb" :class="{ on: showPersona }" @click="showPersona = !showPersona">人格</button>
        <button class="tb" :class="{ on: showFramework }" @click="showFramework = !showFramework">框架</button>
        <button class="tb" :class="{ on: showCharacter }" @click="showCharacter = !showCharacter">人物</button>
        <button class="tb" :class="{ on: showForeshadow }" @click="showForeshadow = !showForeshadow">伏笔</button>
        <button class="tb" :class="{ on: showEntry }" @click="showEntry = !showEntry">词条</button>
        <button class="tb" :class="{ on: showBeat }" @click="showBeat = !showBeat">爽点</button>
        <button class="tb" :class="{ on: showStats }" @click="showStats = !showStats">统计</button>
        <button class="tb" :class="{ on: showTools }" @click="showTools = !showTools">工具</button>
        <button class="tb" :class="{ on: showRoles }" @click="showRoles = !showRoles">角色库</button>
        <span class="kb-sub mono">栈 {{ store.historyStatus.depth }}（可撤 {{ store.historyStatus.undo_left }}）</span>
      </div>

      <FindReplace v-if="showFind" />

      <div v-if="store.typesetChanges.length" class="typeset">
        <div class="kb-sub">排版建议 {{ store.typesetChanges.length }} 处（可整段接受或忽略）</div>
        <div class="ts-list">
          <div v-for="(c, i) in store.typesetChanges" :key="i" class="ts-row">
            <span class="ts-type">{{ c.type }}</span>
            <span class="ts-before">{{ c.before }}</span>
            <span class="ts-after">{{ c.after }}</span>
          </div>
        </div>
        <div class="kb-actions">
          <button class="tb" @click="doApplyTypeset">应用排版</button>
          <button class="tb" @click="store.typesetChanges = []">忽略</button>
        </div>
      </div>

      <div class="editor-main" :class="'vm-' + viewMode">
        <div v-show="showEditor" class="editor-left">
          <input class="chap-title" v-model="title" @input="onInput" placeholder="章节标题" />
          <textarea
            class="chap-body"
            v-model="content"
            @input="onInput"
            @keyup="onCursor"
            @click="onCursor"
            @select="onCursor"
            placeholder="开始写作…"
          ></textarea>
        </div>
        <div v-if="showPreview && store.preview" class="editor-right">
          <PhonePreview
            :html="store.preview.html"
            :pages="store.preview.pages || 0"
            :words="store.preview.words || 0"
            :title="title"
            :cursor-index="cursorIndex"
          />
        </div>
        <!-- 视图切换浮在编辑区右上角：不受工具栏换行影响，任何窗口尺寸都可见 -->
        <div class="view-switch" role="group" aria-label="视图切换">
          <button class="vs" :class="{ on: viewMode === 'edit' }" @click="setView('edit')" title="仅编辑">编辑</button>
          <button class="vs" :class="{ on: viewMode === 'preview' }" @click="setView('preview')" title="仅预览">预览</button>
          <button class="vs" :class="{ on: viewMode === 'split' }" @click="setView('split')" title="编辑与预览同时显示">分屏</button>
        </div>
      </div>

      <div class="editor-foot">
        <span class="wc">字数：<RareCounter :value="words" /></span>
        <button class="solid-button" @click="flush">立即保存</button>
        <button class="ghost-button" @click="makeSnapshot">手动快照</button>
        <span class="hint">自动保存 1.5s · Ctrl+S 保存 · Ctrl+F 查找</span>
      </div>
    </template>

    <!-- 章节快照抽屉 -->
    <transition name="drawer">
      <div class="snap-overlay" v-if="showSnapshots" @click.self="showSnapshots = false">
        <aside class="snap-aside">
          <SnapshotPanel />
        </aside>
      </div>
    </transition>

    <!-- AI 协作抽屉 -->
    <transition name="drawer">
      <div class="ai-overlay" v-if="showAi" @click.self="showAi = false">
        <aside class="ai-aside">
          <AiSession @close="showAi = false" />
        </aside>
      </div>
    </transition>

    <!-- AI 写作抽屉（直接对正文做改写/续写/扩写/缩写/创作/通读全书）-->
    <transition name="drawer">
      <div class="aw-overlay" v-if="showAiWrite" @click.self="showAiWrite = false">
        <aside class="aw-aside">
          <AiWrite
            :book-id="store.currentBookId"
            :chapter-id="store.currentChapterId"
            :full-text="content"
            :sel-start="selStart"
            :sel-end="selEnd"
            :chapter-title="title"
            @close="showAiWrite = false"
            @apply-text="applyAiText"
          />
        </aside>
      </div>
    </transition>

    <!-- 知识库抽屉 -->
    <transition name="drawer">
      <div class="kb-overlay" v-if="showKb" @click.self="showKb = false">
        <aside class="kb-aside">
          <Knowledge @close="showKb = false" />
        </aside>
      </div>
    </transition>

    <!-- 人格抽屉 -->
    <transition name="drawer">
      <div class="ps-overlay" v-if="showPersona" @click.self="showPersona = false">
        <aside class="ps-aside">
          <Persona @close="showPersona = false" />
        </aside>
      </div>
    </transition>

    <!-- 框架抽屉 -->
    <transition name="drawer">
      <div class="fw-overlay" v-if="showFramework" @click.self="showFramework = false">
        <aside class="fw-aside">
          <Framework @close="showFramework = false" />
        </aside>
      </div>
    </transition>

    <!-- 人物抽屉 -->
    <transition name="drawer">
      <div class="ch-overlay" v-if="showCharacter" @click.self="showCharacter = false">
        <aside class="ch-aside">
          <Character @close="showCharacter = false" />
        </aside>
      </div>
    </transition>

    <!-- 伏笔抽屉 -->
    <transition name="drawer">
      <div class="fs-overlay" v-if="showForeshadow" @click.self="showForeshadow = false">
        <aside class="fs-aside">
          <Foreshadow @close="showForeshadow = false" />
        </aside>
      </div>
    </transition>

    <!-- 词条抽屉 -->
    <transition name="drawer">
      <div class="en-overlay" v-if="showEntry" @click.self="showEntry = false">
        <aside class="en-aside">
          <Entry @close="showEntry = false" />
        </aside>
      </div>
    </transition>

    <!-- 爽点节奏抽屉 -->
    <transition name="drawer">
      <div class="bt-overlay" v-if="showBeat" @click.self="showBeat = false">
        <aside class="bt-aside">
          <Beat @close="showBeat = false" />
        </aside>
      </div>
    </transition>

    <!-- 写作统计抽屉 -->
    <transition name="drawer">
      <div class="st-overlay" v-if="showStats" @click.self="showStats = false">
        <aside class="st-aside">
          <Stats @close="showStats = false" />
        </aside>
      </div>
    </transition>

    <!-- 工具箱抽屉 -->
    <transition name="drawer">
      <div class="tl-overlay" v-if="showTools" @click.self="showTools = false">
        <aside class="tl-aside">
          <Tools @close="showTools = false" />
        </aside>
      </div>
    </transition>

    <!-- 角色模板库抽屉 -->
    <transition name="drawer">
      <div class="rl-overlay" v-if="showRoles" @click.self="showRoles = false">
        <aside class="rl-aside">
          <Roles @close="showRoles = false" />
        </aside>
      </div>
    </transition>
  </main>
</template>

<style scoped>
.editor {
  background: color-mix(in srgb, var(--theme-panel) var(--panel-alpha), transparent);
  border: 1px solid var(--theme-line);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  min-height: 0;
  position: relative;
  overflow: hidden;
}
.snap-overlay {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: flex;
  justify-content: flex-end;
  background: var(--theme-scrim);
}
.snap-aside {
  width: min(420px, 86%);
  height: 100%;
  background: color-mix(in srgb, var(--theme-paper) var(--drawer-alpha), transparent);
  border-left: 1px solid var(--theme-line);
  box-shadow: -12px 0 30px rgba(8, 10, 8, 0.25);
  display: flex;
  flex-direction: column;
}
.ai-overlay {
  position: absolute;
  inset: 0;
  z-index: 6;
  display: flex;
  justify-content: flex-end;
  background: var(--theme-scrim);
}
.ai-aside {
  width: min(440px, 90%);
  height: 100%;
  background: color-mix(in srgb, var(--theme-paper) var(--drawer-alpha), transparent);
  border-left: 1px solid var(--theme-line);
  box-shadow: -12px 0 30px rgba(8, 10, 8, 0.25);
  display: flex;
  flex-direction: column;
}
.aw-overlay {
  position: absolute;
  inset: 0;
  z-index: 12;
  display: flex;
  justify-content: flex-end;
  background: var(--theme-scrim);
}
.aw-aside {
  width: min(460px, 92%);
  height: 100%;
  background: color-mix(in srgb, var(--theme-paper) var(--drawer-alpha), transparent);
  border-left: 1px solid var(--theme-line);
  box-shadow: -12px 0 30px rgba(8, 10, 8, 0.25);
  display: flex;
  flex-direction: column;
}
.kb-overlay {
  position: absolute;
  inset: 0;
  z-index: 7;
  display: flex;
  justify-content: flex-end;
  background: var(--theme-scrim);
}
.kb-aside {
  width: min(460px, 92%);
  height: 100%;
  background: color-mix(in srgb, var(--theme-paper) var(--drawer-alpha), transparent);
  border-left: 1px solid var(--theme-line);
  box-shadow: -12px 0 30px rgba(8, 10, 8, 0.25);
  display: flex;
  flex-direction: column;
}
.ps-overlay {
  position: absolute;
  inset: 0;
  z-index: 8;
  display: flex;
  justify-content: flex-end;
  background: var(--theme-scrim);
}
.ps-aside {
  width: min(460px, 92%);
  height: 100%;
  background: color-mix(in srgb, var(--theme-paper) var(--drawer-alpha), transparent);
  border-left: 1px solid var(--theme-line);
  box-shadow: -12px 0 30px rgba(8, 10, 8, 0.25);
  display: flex;
  flex-direction: column;
}
.fw-overlay {
  position: absolute;
  inset: 0;
  z-index: 9;
  display: flex;
  justify-content: flex-end;
  background: var(--theme-scrim);
}
.fw-aside {
  width: min(460px, 92%);
  height: 100%;
  background: color-mix(in srgb, var(--theme-paper) var(--drawer-alpha), transparent);
  border-left: 1px solid var(--theme-line);
  box-shadow: -12px 0 30px rgba(8, 10, 8, 0.25);
  display: flex;
  flex-direction: column;
}
.ch-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  justify-content: flex-end;
  background: var(--theme-scrim);
}
.ch-aside {
  width: min(460px, 92%);
  height: 100%;
  background: color-mix(in srgb, var(--theme-paper) var(--drawer-alpha), transparent);
  border-left: 1px solid var(--theme-line);
  box-shadow: -12px 0 30px rgba(8, 10, 8, 0.25);
  display: flex;
  flex-direction: column;
}
.fs-overlay {
  position: absolute;
  inset: 0;
  z-index: 11;
  display: flex;
  justify-content: flex-end;
  background: var(--theme-scrim);
}
.fs-aside {
  width: min(460px, 92%);
  height: 100%;
  background: color-mix(in srgb, var(--theme-paper) var(--drawer-alpha), transparent);
  border-left: 1px solid var(--theme-line);
  box-shadow: -12px 0 30px rgba(8, 10, 8, 0.25);
  display: flex;
  flex-direction: column;
}
.en-overlay {
  position: absolute;
  inset: 0;
  z-index: 12;
  display: flex;
  justify-content: flex-end;
  background: var(--theme-scrim);
}
.en-aside {
  width: min(460px, 92%);
  height: 100%;
  background: color-mix(in srgb, var(--theme-paper) var(--drawer-alpha), transparent);
  border-left: 1px solid var(--theme-line);
  box-shadow: -12px 0 30px rgba(8, 10, 8, 0.25);
  display: flex;
  flex-direction: column;
}
.bt-overlay {
  position: absolute;
  inset: 0;
  z-index: 13;
  display: flex;
  justify-content: flex-end;
  background: var(--theme-scrim);
}
.bt-aside {
  width: min(480px, 94%);
  height: 100%;
  background: color-mix(in srgb, var(--theme-paper) var(--drawer-alpha), transparent);
  border-left: 1px solid var(--theme-line);
  box-shadow: -12px 0 30px rgba(8, 10, 8, 0.25);
  display: flex;
  flex-direction: column;
}
.st-overlay {
  position: absolute;
  inset: 0;
  z-index: 14;
  display: flex;
  justify-content: flex-end;
  background: var(--theme-scrim);
}
.st-aside {
  width: min(480px, 94%);
  height: 100%;
  background: color-mix(in srgb, var(--theme-paper) var(--drawer-alpha), transparent);
  border-left: 1px solid var(--theme-line);
  box-shadow: -12px 0 30px rgba(8, 10, 8, 0.25);
  display: flex;
  flex-direction: column;
}
.tl-overlay {
  position: absolute;
  inset: 0;
  z-index: 15;
  display: flex;
  justify-content: flex-end;
  background: var(--theme-scrim);
}
.tl-aside {
  width: min(480px, 94%);
  height: 100%;
  background: color-mix(in srgb, var(--theme-paper) var(--drawer-alpha), transparent);
  border-left: 1px solid var(--theme-line);
  box-shadow: -12px 0 30px rgba(8, 10, 8, 0.25);
  display: flex;
  flex-direction: column;
}
.rl-overlay {
  position: absolute;
  inset: 0;
  z-index: 16;
  display: flex;
  justify-content: flex-end;
  background: var(--theme-scrim);
}
.rl-aside {
  width: min(480px, 94%);
  height: 100%;
  background: color-mix(in srgb, var(--theme-paper) var(--drawer-alpha), transparent);
  border-left: 1px solid var(--theme-line);
  box-shadow: -12px 0 30px rgba(8, 10, 8, 0.25);
  display: flex;
  flex-direction: column;
}
/* GitHub 风格抽屉：遮罩淡入淡出，右侧面板自身从右缘滑入/滑出 */
.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 0.28s var(--motion);
}
.drawer-enter-active > aside,
.drawer-leave-active > aside {
  transition: transform 0.32s var(--motion);
}
.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}
.drawer-enter-from > aside,
.drawer-leave-to > aside {
  transform: translateX(100%);
}
.empty {
  color: var(--theme-muted);
  font-size: 14px;
  padding: 40px;
  text-align: center;
}
.editor-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid var(--theme-line);
  flex-wrap: wrap;
}
.tb {
  font-size: 12px;
  padding: 5px 11px;
  border: 1px solid var(--theme-line);
  border-radius: 4px;
  background: transparent;
  color: var(--theme-ink-soft);
  transition: all 0.2s var(--motion);
}
.tb:hover:not(:disabled) {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.tb:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.tb.on {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
  background: var(--theme-field);
}
.vs {
  font-size: 12px;
  padding: 5px 12px;
  border: none;
  background: transparent;
  color: var(--theme-muted);
  cursor: pointer;
  transition: all 0.2s var(--motion);
}
.vs + .vs {
  border-left: 1px solid var(--theme-line);
}
.vs:hover {
  color: var(--theme-accent-hover);
}
.vs.on {
  background: var(--theme-field);
  color: var(--theme-accent-hover);
}
.kb-sub {
  font-size: 12px;
  color: var(--theme-muted);
  font-family: var(--font-mono);
  margin-left: auto;
}
.typeset {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  margin: 8px 14px;
  padding: 10px;
  background: var(--theme-field);
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 0;
}
/* 建议过多时可向下滑动查看（标题与操作按钮常驻，不随列表滚走） */
.ts-list {
  /* 同样需要按 --ui-scale 补偿，避免放大后超出可视区 */
  max-height: calc(34vh / var(--ui-scale, 1));
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-right: 2px;
}
.ts-row {
  font-size: 12px;
  display: flex;
  gap: 8px;
  align-items: baseline;
}
.ts-type {
  font-family: var(--font-mono);
  color: var(--theme-accent);
}
.ts-before {
  color: var(--theme-error);
  text-decoration: line-through;
}
.ts-after {
  color: var(--theme-success);
}
.kb-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
.editor-main {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 12px;
  padding: 12px 14px;
  min-height: 0;
  position: relative; /* 视图切换浮层的定位基准 */
}
/* 浮在编辑区右上角：绝对定位，窗口缩放/工具栏换行都不会把它挤掉 */
.view-switch {
  position: absolute;
  top: 14px;
  right: 20px;
  z-index: 4;
  display: flex;
  border: 1px solid var(--theme-line);
  border-radius: 4px;
  overflow: hidden;
  background: color-mix(in srgb, var(--theme-paper) var(--panel-alpha), transparent);
  box-shadow: 0 2px 10px rgba(8, 10, 8, 0.14);
}
/* 三态视图：分屏=双列；编辑/预览=单列 */
.editor-main.vm-edit,
.editor-main.vm-preview {
  grid-template-columns: 1fr;
}
.editor-left {
  display: flex;
  flex-direction: column;
  min-height: 0;
  gap: 8px;
}
.chap-title {
  font-size: 18px;
  font-weight: 700;
  /* 右侧留出空间，避免被右上角的视图切换浮层遮住标题文字 */
  padding: 8px 190px 8px 10px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--theme-field) var(--field-alpha), transparent);
  color: var(--theme-ink);
}
.chap-title:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.chap-body {
  flex: 1;
  min-height: 0;
  resize: none;
  font-family: var(--font-sans);
  font-size: var(--editor-font-size, 16px);
  line-height: var(--editor-line-height, 1.9);
  padding: 14px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--theme-field) var(--field-alpha), transparent);
  color: var(--theme-ink);
}
.chap-body:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.editor-right {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 6px;
  min-height: 0;
}
.editor-foot {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 10px 14px;
  border-top: 1px solid var(--theme-line);
  font-size: 13px;
  color: var(--theme-ink-soft);
}
.editor-foot .hint {
  color: var(--theme-muted);
  font-size: 12px;
}
.solid-button,
.ghost-button {
  font-size: 13px;
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.2s var(--motion);
}
.solid-button {
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border: 1px solid var(--theme-solid-bg);
}
.solid-button:hover {
  background: var(--theme-solid-hover);
}
.ghost-button {
  background: transparent;
  color: var(--theme-ink-soft);
  border: 1px solid var(--theme-line);
}
.ghost-button:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
@media (max-width: 900px) {
  .editor-main {
    grid-template-columns: 1fr;
  }
  .editor-right {
    height: 320px;
  }
}
</style>
