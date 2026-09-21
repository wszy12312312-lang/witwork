<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import {
  store,
  loadKbItems,
  openKbItem,
  createKbItem,
  saveKbItem,
  deleteKbItem,
  rollbackKbItem,
  retrieveKb,
  reindexKb,
  type KbItem,
  type KbVersion,
} from '../lib/store';

const emit = defineEmits<{ (e: 'close'): void }>();

const tab = ref<'browse' | 'retrieve'>('browse');
const showNew = ref(false);
const newTitle = ref('');
const newContent = ref('');

const detail = computed(() => store.kbCurrentItem as (KbItem & { versions?: KbVersion[] }) | null);
const editTitle = ref('');
const editContent = ref('');
const editReason = ref('');

const query = ref('');
const busy = ref(false);

function sectionTitle(key: string): string {
  return store.kbSections.find((s) => s.key === key)?.title || key;
}

async function pickSection(key: string) {
  store.kbCurrentItem = null;
  await loadKbItems(key);
}

async function submitNew() {
  if (!newTitle.value.trim()) return;
  await createKbItem(store.kbActiveSection, newTitle.value, newContent.value);
  newTitle.value = '';
  newContent.value = '';
  showNew.value = false;
}

async function openDetail(it: KbItem) {
  // 列表项不含 versions，需拉取完整条目（含版本历史）才能正确显示/回滚
  await openKbItem(it.id);
  const fresh = store.kbCurrentItem as KbItem | null;
  if (!fresh) return;
  editTitle.value = fresh.title;
  editContent.value = fresh.content || '';
  editReason.value = '';
}

async function saveDetail() {
  if (!detail.value) return;
  await saveKbItem(detail.value.id, {
    title: editTitle.value,
    content: editContent.value,
    reason: editReason.value.trim() || '编辑',
  });
}

async function doDelete() {
  if (!detail.value) return;
  await deleteKbItem(detail.value.id);
}

async function doRollback(v: KbVersion) {
  if (!detail.value) return;
  await rollbackKbItem(detail.value.id, v.id);
  if (store.kbCurrentItem) {
    editContent.value = (store.kbCurrentItem as KbItem).content || '';
    editTitle.value = (store.kbCurrentItem as KbItem).title;
  }
}

async function doRetrieve() {
  if (!query.value.trim()) return;
  busy.value = true;
  try {
    await retrieveKb(query.value);
  } finally {
    busy.value = false;
  }
}

async function doReindex() {
  busy.value = true;
  try {
    await reindexKb();
  } finally {
    busy.value = false;
  }
}

onMounted(() => {
  if (!store.kbItems.length) loadKbItems();
});
</script>

<template>
  <section class="kb">
    <header class="kb-head">
      <div class="kb-title">知识库</div>
      <button class="x" @click="emit('close')" title="关闭">✕</button>
    </header>

    <nav class="tabs">
      <button :class="{ on: tab === 'browse' }" @click="tab = 'browse'">条目</button>
      <button :class="{ on: tab === 'retrieve' }" @click="tab = 'retrieve'">检索</button>
    </nav>

    <div v-if="store.kbError" class="kb-err">⚠ {{ store.kbError }}</div>

    <!-- 浏览 -->
    <div v-if="tab === 'browse'" class="kb-body">
      <!-- 详情视图 -->
      <div v-if="detail" class="detail">
        <div class="det-bar">
          <button class="back" @click="store.kbCurrentItem = null">← 返回列表</button>
          <span class="det-sec">{{ sectionTitle(detail.section) }}</span>
        </div>
        <input class="det-title" v-model="editTitle" placeholder="条目标题" />
        <textarea class="det-body" v-model="editContent" placeholder="条目正文…"></textarea>
        <input class="det-reason" v-model="editReason" placeholder="修改说明（版本备注，可选）" />
        <div class="det-acts">
          <button class="save" @click="saveDetail">保存</button>
          <RareDeleteButton @confirm="doDelete" />
        </div>
        <div class="vers">
          <div class="vers-h">版本历史（点击回滚到第 N 版）</div>
          <div v-for="v in (detail.versions || [])" :key="v.id" class="ver-row">
            <button class="ver-btn" @click="doRollback(v)">↺ 第{{ v.id }}版</button>
            <span class="ver-reason">{{ v.reason || '' }}</span>
            <span class="ver-time">{{ (v.created_at || '').slice(0, 19) }}</span>
          </div>
          <div v-if="!(detail.versions || []).length" class="hint">暂无历史版本</div>
        </div>
      </div>

      <!-- 列表视图 -->
      <template v-else>
        <div class="sec-row">
          <button
            v-for="s in store.kbSections"
            :key="s.key"
            class="sec-chip"
            :class="{ on: s.key === store.kbActiveSection }"
            @click="pickSection(s.key)"
          >
            {{ s.title }}
          </button>
        </div>
        <button class="new-item" @click="showNew = !showNew">＋ 新建条目</button>
        <div v-if="showNew" class="new-form">
          <input class="nf-title" v-model="newTitle" placeholder="条目标题" />
          <textarea class="nf-body" v-model="newContent" placeholder="条目正文…"></textarea>
          <div class="nf-acts">
            <button class="save" @click="submitNew">入库</button>
            <button class="ghost" @click="showNew = false">取消</button>
          </div>
        </div>
        <div class="item-list">
          <div v-for="it in store.kbItems" :key="it.id" class="item" @click="openDetail(it)">
            <div class="it-title">{{ it.title }}</div>
            <div class="it-meta">
              <span class="it-src">{{ it.source_type }}</span>
              <span class="it-time">{{ (it.updated_at || '').slice(0, 10) }}</span>
            </div>
          </div>
          <div v-if="!store.kbItems.length" class="hint">该分区暂无条目</div>
        </div>
      </template>
    </div>

    <!-- 检索 -->
    <div v-else class="kb-body">
      <div class="ret-box">
        <input class="ret-q" v-model="query" placeholder="检索知识库（支持 2 字短词）" @keyup.enter="doRetrieve" />
        <button class="ret-go" :disabled="busy" @click="doRetrieve">检索</button>
      </div>
      <div class="hits">
        <div v-for="h in store.kbHits" :key="h.n" class="hit">
          <div class="hit-top">
            <span class="hit-n">[{{ h.n }}]</span>
            <span class="hit-title">{{ h.title }}</span>
            <span class="hit-sec">{{ h.section_title }}</span>
          </div>
          <div class="hit-snip">{{ h.snippet }}</div>
        </div>
        <div v-if="!store.kbHits.length" class="hint">输入关键词开始检索</div>
      </div>
      <div class="reindex">
        <button class="ri-btn" :disabled="busy" @click="doReindex">重建向量索引</button>
        <span v-if="store.kbReindex" class="ri-res">
          重嵌入 {{ store.kbReindex.reindexed }} · 跳过 {{ store.kbReindex.skipped }} · 维度 {{ store.kbReindex.dim }}
        </span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.kb {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.kb-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.kb-title {
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
  padding: 8px 14px 0;
}
.tabs button {
  font-size: 12.5px;
  padding: 5px 12px;
  border: 1px solid var(--theme-line);
  border-bottom: none;
  border-radius: 6px 6px 0 0;
  background: transparent;
  color: var(--theme-ink-soft);
  cursor: pointer;
}
.tabs button.on {
  background: var(--theme-field);
  color: var(--theme-accent-hover);
  border-color: var(--theme-accent);
}
.kb-err {
  color: var(--theme-error);
  font-size: 12px;
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
  padding: 6px 10px;
  margin: 8px 14px 0;
  border-radius: var(--radius-sm);
}
.kb-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.sec-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.sec-chip {
  font-size: 12px;
  padding: 4px 10px;
  border: 1px solid var(--theme-line);
  border-radius: 999px;
  background: transparent;
  color: var(--theme-ink-soft);
  cursor: pointer;
}
.sec-chip.on {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
  background: var(--theme-field);
}
.new-item {
  align-self: flex-start;
  font-size: 12px;
  padding: 5px 12px;
  border: 1px solid var(--theme-accent);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--theme-accent-hover);
  cursor: pointer;
}
.new-item:hover {
  background: var(--theme-field);
}
.new-form {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
}
.nf-title,
.det-title,
.ret-q,
.nf-body,
.det-body,
.det-reason {
  font-family: var(--font-sans);
  font-size: 13px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-paper);
  color: var(--theme-ink);
  padding: 6px 9px;
}
.nf-title:focus,
.det-title:focus,
.ret-q:focus,
.nf-body:focus,
.det-body:focus,
.det-reason:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.nf-body,
.det-body {
  min-height: 120px;
  resize: vertical;
  line-height: 1.7;
}
.nf-acts,
.det-acts {
  display: flex;
  gap: 8px;
}
.save,
.ret-go,
.ri-btn {
  font-size: 13px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border: 1px solid var(--theme-solid-bg);
  cursor: pointer;
}
.save:hover:not(:disabled),
.ret-go:hover:not(:disabled),
.ri-btn:hover:not(:disabled) {
  background: var(--theme-solid-hover);
}
.save:disabled,
.ret-go:disabled,
.ri-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.ghost,
.del {
  font-size: 13px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
}
.ghost {
  border: 1px solid var(--theme-line);
  color: var(--theme-ink-soft);
}
.del {
  border: 1px solid var(--theme-error);
  color: var(--theme-error);
}
.del:hover {
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
}
.item-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.item {
  padding: 9px 11px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-paper);
  cursor: pointer;
}
.item:hover {
  border-color: var(--theme-accent);
}
.it-title {
  font-size: 13.5px;
  color: var(--theme-ink);
  font-weight: 600;
}
.it-meta {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  font-size: 11px;
  color: var(--theme-muted);
}
.it-src {
  color: var(--theme-accent);
  font-family: var(--font-mono);
}
.detail {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.det-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}
.back {
  font-size: 12px;
  background: transparent;
  border: none;
  color: var(--theme-accent-hover);
  cursor: pointer;
}
.det-sec {
  font-size: 11.5px;
  color: var(--theme-muted);
}
.vers {
  margin-top: 6px;
  border-top: 1px dashed var(--theme-line);
  padding-top: 8px;
}
.vers-h {
  font-size: 12px;
  color: var(--theme-muted);
  margin-bottom: 6px;
}
.ver-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  font-size: 12px;
}
.ver-btn {
  font-size: 11.5px;
  padding: 3px 9px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--theme-ink-soft);
  cursor: pointer;
}
.ver-btn:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.ver-reason {
  color: var(--theme-ink-soft);
}
.ver-time {
  margin-left: auto;
  font-size: 10.5px;
  color: var(--theme-muted);
  font-family: var(--font-mono);
}
.ret-box {
  display: flex;
  gap: 8px;
}
.ret-q {
  flex: 1;
}
.hits {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hit {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 9px 11px;
  background: var(--theme-paper);
}
.hit-top {
  display: flex;
  gap: 6px;
  align-items: baseline;
  font-size: 13px;
}
.hit-n {
  color: var(--theme-accent);
  font-family: var(--font-mono);
}
.hit-title {
  font-weight: 600;
  color: var(--theme-ink);
}
.hit-sec {
  margin-left: auto;
  font-size: 11px;
  color: var(--theme-muted);
}
.hit-snip {
  margin-top: 4px;
  font-size: 12px;
  color: var(--theme-ink-soft);
  line-height: 1.6;
}
.reindex {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
}
.ri-res {
  font-size: 11px;
  color: var(--theme-muted);
  font-family: var(--font-mono);
}
.hint {
  font-size: 12px;
  color: var(--theme-muted);
}
</style>
