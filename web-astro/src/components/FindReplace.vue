<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { store, doSearch, doReplace, loadReplaceLogs, undoReplace } from '../lib/store';

const q = ref('');
const rep = ref('');
const useRegex = ref(false);
const caseSensitive = ref(false);
const scope = ref<'book' | 'volume' | 'chapter'>('book');
const preview = ref<typeof store.replacePreview>(null);
const msg = ref('');

onMounted(() => {
  q.value = store.searchQuery || '';
});

async function find() {
  const r = await doSearch(q.value, {
    use_regex: useRegex.value,
    case_sensitive: caseSensitive.value,
    scope: scope.value,
  });
  msg.value = `命中 ${r?.total ?? 0} 处${r?.truncated ? '（已截断）' : ''}`;
}

async function previewReplace() {
  const r = await doReplace(rep.value, true, {
    use_regex: useRegex.value,
    case_sensitive: caseSensitive.value,
    scope: scope.value,
  });
  preview.value = r;
  msg.value = `预览：共 ${r?.total ?? 0} 处将替换`;
}

async function applyReplace() {
  const r = await doReplace(rep.value, false, {
    use_regex: useRegex.value,
    case_sensitive: caseSensitive.value,
    scope: scope.value,
  });
  preview.value = null;
  msg.value = `已替换 ${r?.total ?? 0} 处（已建快照，可撤销）`;
  await loadReplaceLogs();
  await find();
}

async function undoLast() {
  const logs = store.replaceLogs || [];
  const last = logs.find((l) => !(l as { undone: boolean }).undone);
  if (!last) return;
  await undoReplace((last as { id: number }).id);
  msg.value = '已撤销上次替换';
  await find();
}
</script>

<template>
  <div class="find">
    <div class="find-row">
      <input v-model="q" class="inp" placeholder="查找" @keyup.enter="find" />
      <input v-model="rep" class="inp" placeholder="替换为" />
      <button class="tb" @click="find">查找</button>
      <button class="tb" @click="previewReplace">预览</button>
      <button class="tb" @click="applyReplace">全部替换</button>
      <button class="tb" @click="undoLast">撤销替换</button>
    </div>
    <div class="find-row find-opts">
      <label><input type="checkbox" v-model="useRegex" /> 正则</label>
      <label><input type="checkbox" v-model="caseSensitive" /> 区分大小写</label>
      <select v-model="scope" class="inp">
        <option value="book">全书</option>
        <option value="volume">当前卷</option>
        <option value="chapter">当前章</option>
      </select>
      <span class="kb-sub">{{ msg }}</span>
    </div>

    <div v-if="preview && preview.results && preview.results.length" class="find-preview">
      <div v-for="r in preview.results" :key="r.chapter_id" class="fp">
        <div class="kb-sub">{{ r.chapter_title }} · {{ r.count }} 处</div>
        <div class="fp-before">- {{ r.before }}</div>
        <div class="fp-after">+ {{ r.after }}</div>
      </div>
    </div>

    <div class="find-hits">
      <div v-for="(h, i) in store.searchHits" :key="i" class="fh">
        <span class="kb-sub">{{ h.chapter_title }} L{{ h.line }}:{{ h.col }}</span>
        <div class="fh-snippet">{{ h.snippet }}</div>
      </div>
      <div v-if="!store.searchHits.length" class="kb-empty">无命中</div>
    </div>
  </div>
</template>

<style scoped>
.find {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 10px;
  background: var(--theme-field);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.find-row {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}
.inp {
  font-size: 13px;
  padding: 4px 8px;
  border: 1px solid var(--theme-line);
  border-radius: 4px;
  background: var(--theme-paper);
  color: var(--theme-ink);
  min-width: 90px;
}
.inp:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.tb {
  font-size: 12px;
  padding: 4px 10px;
  border: 1px solid var(--theme-line);
  border-radius: 4px;
  background: transparent;
  color: var(--theme-ink-soft);
  transition: all 0.2s var(--motion);
}
.tb:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.find-opts label {
  font-size: 12px;
  color: var(--theme-ink-soft);
  display: inline-flex;
  gap: 4px;
  align-items: center;
}
.kb-sub {
  font-size: 12px;
  color: var(--theme-muted);
  font-family: var(--font-mono);
}
.find-preview {
  border-top: 1px solid var(--theme-line);
  padding-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.fp-before {
  font-size: 12px;
  color: var(--theme-error);
}
.fp-after {
  font-size: 12px;
  color: var(--theme-success);
}
.find-hits {
  border-top: 1px solid var(--theme-line);
  padding-top: 6px;
  max-height: 140px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.fh {
  font-size: 12px;
}
.fh-snippet {
  color: var(--theme-ink-soft);
  padding: 2px 0;
}
.kb-empty {
  color: var(--theme-muted);
  font-size: 12px;
}
</style>
