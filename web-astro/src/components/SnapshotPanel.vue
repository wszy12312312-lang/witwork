<script setup lang="ts">
import { ref } from 'vue';
import { store, makeSnapshot, restoreSnapshot, diffSnapshot } from '../lib/store';

interface DiffLine {
  type: 'eq' | 'del' | 'add';
  text: string;
}

const diffFor = ref<{ id: number; title: string; lines: DiffLine[] } | null>(null);
const busyId = ref<number | null>(null);

function fmtTime(s?: string) {
  if (!s) return '';
  return s.replace('T', ' ').slice(0, 19);
}

async function doNew() {
  await makeSnapshot();
}

async function doRestore(sid: number) {
  if (!confirm('恢复到该快照？当前正文将被覆盖（建议先手动快照）。')) return;
  await restoreSnapshot(sid);
  diffFor.value = null;
}

async function viewDiff(sid: number, title: string) {
  busyId.value = sid;
  try {
    const lines = await diffSnapshot(sid);
    diffFor.value = { id: sid, title, lines: lines || [] };
  } finally {
    busyId.value = null;
  }
}

function closeDiff() {
  diffFor.value = null;
}
</script>

<template>
  <div class="snap-drawer">
    <div class="snap-head">
      <span class="eyebrow mono">章节快照</span>
      <button class="mini solid" @click="doNew">＋ 手动快照</button>
    </div>

    <div class="snap-list" v-if="store.snapshots.length">
      <div class="snap-row" v-for="s in store.snapshots" :key="s.id">
        <div class="snap-meta">
          <span class="snap-title">{{ s.title || ('快照 #' + s.id) }}</span>
          <span class="mono snap-time">{{ fmtTime(s.created_at) }}</span>
          <span class="snap-kind" v-if="s.kind">{{ s.kind }}</span>
        </div>
        <div class="snap-acts">
          <button class="mini" :disabled="busyId === s.id" @click="viewDiff(s.id, s.title || ('快照 #' + s.id))">差异</button>
          <button class="mini" @click="doRestore(s.id)">恢复</button>
        </div>
      </div>
    </div>
    <div class="snap-empty mono" v-else>暂无快照。编辑后会自动在 1.5s 触发自动快照（若启用）。</div>

    <!-- 差异视图 -->
    <div class="snap-diff" v-if="diffFor">
      <div class="diff-head">
        <span class="kb-sub">与《{{ diffFor.title }}》的差异（快照 → 当前正文）</span>
        <button class="mini" @click="closeDiff">关闭</button>
      </div>
      <div class="diff-body">
        <div
          v-for="(l, i) in diffFor.lines"
          :key="i"
          class="diff-line"
          :class="l.type"
        >
          <span class="mark">{{ l.type === 'del' ? '−' : l.type === 'add' ? '＋' : ' ' }}</span>
          <span class="txt">{{ l.text || ' ' }}</span>
        </div>
        <div class="diff-empty mono" v-if="!diffFor.lines.length">两份正文完全一致。</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.snap-drawer {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.snap-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.eyebrow {
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--theme-muted);
}
.snap-list {
  flex: 1;
  overflow: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.snap-row {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  background: var(--theme-field);
}
.snap-meta {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}
.snap-title {
  font-size: 13px;
  font-weight: 600;
}
.snap-time {
  font-size: 11px;
  color: var(--theme-muted);
}
.snap-kind {
  font-size: 11px;
  color: var(--theme-accent);
  border: 1px solid var(--theme-accent);
  border-radius: 4px;
  padding: 0 6px;
}
.snap-acts {
  display: flex;
  gap: 6px;
  margin-top: 6px;
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
.mini:hover:not(:disabled) {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.mini:disabled {
  opacity: 0.4;
}
.mini.solid {
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border-color: var(--theme-solid-bg);
}
.snap-empty {
  color: var(--theme-muted);
  font-size: 12px;
  padding: 16px;
}
.snap-diff {
  border-top: 1px solid var(--theme-line);
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}
.diff-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
}
.kb-sub {
  font-size: 12px;
  color: var(--theme-muted);
  font-family: var(--font-mono);
}
.diff-body {
  flex: 1;
  overflow: auto;
  padding: 6px 10px 12px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
}
.diff-line {
  display: flex;
  gap: 6px;
  white-space: pre-wrap;
  word-break: break-all;
}
.diff-line .mark {
  width: 12px;
  flex: none;
  opacity: 0.7;
}
.diff-line.del {
  background: color-mix(in srgb, var(--theme-error) 14%, transparent);
  color: var(--theme-ink);
}
.diff-line.add {
  background: color-mix(in srgb, var(--theme-success) 16%, transparent);
  color: var(--theme-ink);
}
.diff-empty {
  color: var(--theme-muted);
  padding: 12px;
}
</style>
