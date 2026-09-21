<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { store, loadRoles, createRole, instantiateRole } from '../lib/store';

const emit = defineEmits<{ (e: 'close'): void }>();

const newName = ref('');
const newCategory = ref('配角');
const newFields = ref('appearance,personality,catchphrase,status_current');
const instTid = ref<number | null>(null);
const instName = ref('');
const tip = ref('');

function parseFields(t: { fields_json?: string }): string[] {
  try {
    const v = t.fields_json ? JSON.parse(t.fields_json) : [];
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

const hasBook = computed(() => !!store.currentBookId);

async function doCreate() {
  const name = newName.value.trim();
  if (!name) {
    tip.value = '请填写模板名称';
    return;
  }
  const fields = newFields.value
    .split(/[，,\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const ok = await createRole(name, newCategory.value.trim() || '配角', fields);
  tip.value = ok ? '已创建模板' : store.rolesError || '创建失败';
  if (ok) {
    newName.value = '';
    setTimeout(() => (tip.value = ''), 1800);
  }
}

function startInst(t: number) {
  instTid.value = t;
  instName.value = '';
}
async function confirmInst(t: number) {
  const name = instName.value.trim();
  if (!name) {
    tip.value = '请填写角色名称';
    return;
  }
  const ok = await instantiateRole(t, name);
  tip.value = ok ? `已实例化为角色「${name}」` : store.rolesError || '实例化失败';
  if (ok) {
    instTid.value = null;
    setTimeout(() => (tip.value = ''), 1800);
  }
}

onMounted(async () => {
  await loadRoles();
});
</script>

<template>
  <section class="rl">
    <header class="rl-head">
      <div class="rl-title">角色模板库</div>
      <button class="x" @click="emit('close')" title="关闭">✕</button>
    </header>

    <div v-if="store.rolesError" class="rl-err">⚠ {{ store.rolesError }}</div>
    <div v-if="tip" class="rl-tip">{{ tip }}</div>

    <div class="rl-body">
      <!-- 模板列表 -->
      <div class="hint">内置 5 套模板，可基于模板一键实例化为当前作品的角色（副本）。</div>
      <div class="rel-list">
        <div v-for="t in store.roles" :key="t.id" class="rl-card">
          <div class="rl-top">
            <span class="rl-name">{{ t.name }}</span>
            <span class="rl-cat">{{ t.category }}</span>
            <span class="rl-badge" :class="t.built_in ? 'bi' : 'cu'">{{ t.built_in ? '内置' : '自定义' }}</span>
          </div>
          <div class="rl-fields">
            <span v-for="f in parseFields(t)" :key="f" class="chip">{{ f }}</span>
          </div>
          <div class="rl-acts">
            <button class="mini" :disabled="!hasBook" @click="startInst(t.id)">实例化为角色</button>
          </div>
          <div v-if="instTid === t.id" class="rl-inst">
            <input v-model="instName" class="inp" placeholder="角色名称" />
            <button class="mini solid" @click="confirmInst(t.id)">确认</button>
            <button class="mini" @click="instTid = null">取消</button>
          </div>
          <div v-if="!hasBook" class="rl-sub">打开作品后可实例化</div>
        </div>
        <div v-if="!store.roles.length" class="hint">加载中…</div>
      </div>

      <!-- 新建模板 -->
      <div class="rl-new">
        <div class="rl-new-title">新建模板</div>
        <label class="fld">
          <span>名称</span>
          <input v-model="newName" class="inp" placeholder="如：导师模板" />
        </label>
        <label class="fld">
          <span>分类</span>
          <input v-model="newCategory" class="inp" placeholder="如：导师" />
        </label>
        <label class="fld">
          <span>字段（逗号分隔）</span>
          <input v-model="newFields" class="inp" placeholder="appearance,personality,..." />
        </label>
        <button class="save" @click="doCreate">创建模板</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.rl {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.rl-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.rl-title {
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
.rl-err {
  color: var(--theme-error);
  font-size: 12px;
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
  padding: 6px 10px;
  margin: 8px 14px 0;
  border-radius: var(--radius-sm);
}
.rl-tip {
  font-size: 12px;
  color: var(--theme-success);
  padding: 4px 14px 0;
}
.rl-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.hint {
  font-size: 12px;
  color: var(--theme-muted);
}
.rel-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rl-card {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 9px 11px;
  background: var(--theme-field);
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.rl-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rl-name {
  font-weight: 600;
  font-size: 13.5px;
  color: var(--theme-ink);
}
.rl-cat {
  font-size: 11px;
  color: var(--theme-muted);
  border: 1px solid var(--theme-line);
  border-radius: 3px;
  padding: 1px 6px;
}
.rl-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  margin-left: auto;
}
.rl-badge.bi {
  color: var(--theme-accent-hover);
  background: color-mix(in srgb, var(--theme-accent) 14%, transparent);
}
.rl-badge.cu {
  color: var(--theme-muted);
  background: color-mix(in srgb, var(--theme-muted) 14%, transparent);
}
.rl-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.chip {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--theme-ink-soft);
  background: var(--theme-paper);
  border: 1px solid var(--theme-line);
  border-radius: 3px;
  padding: 1px 7px;
}
.rl-acts {
  display: flex;
  gap: 8px;
}
.rl-inst {
  display: flex;
  gap: 6px;
  align-items: center;
}
.rl-sub {
  font-size: 11px;
  color: var(--theme-muted);
}
.mini {
  font-size: 12px;
  padding: 4px 11px;
  border: 1px solid var(--theme-line);
  border-radius: 4px;
  background: transparent;
  color: var(--theme-ink-soft);
  cursor: pointer;
}
.mini:hover:not(:disabled) {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.mini:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.mini.solid {
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border-color: var(--theme-solid-bg);
}
.inp {
  font-size: 13px;
  padding: 6px 9px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
  flex: 1;
  min-width: 0;
}
.inp:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.rl-new {
  border: 1px dashed var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.rl-new-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--theme-ink);
}
.fld {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--theme-muted);
}
.save {
  font-size: 13px;
  padding: 7px 15px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border: 1px solid var(--theme-solid-bg);
  align-self: flex-start;
}
.save:hover {
  background: var(--theme-solid-hover);
}
</style>
