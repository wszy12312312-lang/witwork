<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import {
  store,
  openPersona,
  createPersona,
  savePersona,
  deletePersona,
  activatePersona,
  adjustPersona,
  type Persona,
  type PersonaVersion,
} from '../lib/store';
import RareDeleteButton from './RareDeleteButton.vue';

const emit = defineEmits<{ (e: 'close'): void }>();

const showNew = ref(false);
const cur = computed(() => store.personaCurrent as Persona | null);

const eName = ref('');
const ePrompt = ref('');
const eTone = ref('');
const eFocus = ref('');
const eTemp = ref(0.8);
const eStyle = ref('');
const eMethods = ref('');
const eForbidden = ref('');

const adjustText = ref('');

function arrOf(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw as string[];
  if (typeof raw === 'string' && raw) {
    try {
      const v = JSON.parse(raw);
      return Array.isArray(v) ? v : [];
    } catch {
      return [];
    }
  }
  return [];
}
function csv(s: string): string[] {
  return s
    .split(/[,，]/)
    .map((x) => x.trim())
    .filter(Boolean);
}
function join(a?: string[]): string {
  return (a || []).join('，');
}

function tagsOf(p: Persona): string {
  return join(arrOf(p.style_tags ?? p.style_tags_json));
}
function methodsOf(p: Persona): string {
  return join(arrOf(p.methods ?? p.methods_json));
}
function forbiddenOf(p: Persona): string {
  return join(arrOf(p.forbidden ?? p.forbidden_json));
}

async function submitNew() {
  if (!eName.value.trim()) return;
  await createPersona({
    name: eName.value.trim(),
    system_prompt: ePrompt.value,
    tone: eTone.value || null,
    focus: eFocus.value || null,
    temperature: Number(eTemp.value) || 0.8,
    style_tags: csv(eStyle.value),
    methods: csv(eMethods.value),
    forbidden: csv(eForbidden.value),
  });
  eName.value = '';
  ePrompt.value = '';
  eTone.value = '';
  eFocus.value = '';
  eTemp.value = 0.8;
  eStyle.value = '';
  eMethods.value = '';
  eForbidden.value = '';
  showNew.value = false;
}

async function openDetail(p: Persona) {
  store.personaVersions = [];
  await openPersona(p.id);
  const fresh = store.personaCurrent;
  if (!fresh) return;
  eName.value = fresh.name;
  ePrompt.value = fresh.system_prompt || '';
  eTone.value = fresh.tone || '';
  eFocus.value = fresh.focus || '';
  eTemp.value = typeof fresh.temperature === 'number' ? fresh.temperature : 0.8;
  eStyle.value = tagsOf(fresh);
  eMethods.value = methodsOf(fresh);
  eForbidden.value = forbiddenOf(fresh);
}

async function saveDetail() {
  if (!cur.value) return;
  await savePersona(cur.value.id, {
    name: eName.value.trim(),
    system_prompt: ePrompt.value,
    tone: eTone.value || null,
    focus: eFocus.value || null,
    temperature: Number(eTemp.value) || 0.8,
    style_tags: csv(eStyle.value),
    methods: csv(eMethods.value),
    forbidden: csv(eForbidden.value),
  });
}

async function doDelete() {
  if (!cur.value) return;
  await deletePersona(cur.value.id);
}

async function doAdjust() {
  if (!adjustText.value.trim()) return;
  await adjustPersona(adjustText.value.trim());
  adjustText.value = '';
}

function snapshotNote(v: PersonaVersion): string {
  try {
    const s = v.snapshot_json ? JSON.parse(v.snapshot_json) : null;
    return s?.name ? `→ ${s.name}` : v.note || '';
  } catch {
    return v.note || '';
  }
}

onMounted(() => {
  if (!store.personas.length) store.loadPersonas();
});
</script>

<template>
  <section class="ps">
    <header class="ps-head">
      <div class="ps-title">人格</div>
      <button class="x" @click="emit('close')" title="关闭">✕</button>
    </header>

    <div v-if="store.personaError" class="ps-err">⚠ {{ store.personaError }}</div>

    <!-- 详情/编辑 -->
    <div v-if="cur" class="ps-body">
      <div class="det-bar">
        <button class="back" @click="store.personaCurrent = null">← 返回列表</button>
        <span v-if="cur.active" class="badge on">使用中</span>
        <span v-if="cur.built_in" class="badge">内置</span>
      </div>
      <input class="fld" v-model="eName" placeholder="人格名称" />
      <textarea class="fld area" v-model="ePrompt" placeholder="系统提示词（system prompt）"></textarea>
      <div class="grid2">
        <input class="fld" v-model="eTone" placeholder="语气（如：克制、专业）" />
        <input class="fld" v-model="eFocus" placeholder="侧重（如：一致性优先）" />
      </div>
      <label class="temp">
        温度 temperature：<span class="mono">{{ eTemp }}</span>
        <input type="range" min="0" max="1.5" step="0.1" v-model.number="eTemp" />
      </label>
      <input class="fld" v-model="eStyle" placeholder="风格标签（逗号分隔）" />
      <input class="fld" v-model="eMethods" placeholder="创作方法（逗号分隔，如：三幕、雪花）" />
      <input class="fld" v-model="eForbidden" placeholder="禁忌（逗号分隔）" />
      <div class="det-acts">
        <button class="save" @click="saveDetail">保存</button>
        <button v-if="!cur.active" class="use" @click="activatePersona(cur.id)">设为当前</button>
        <RareDeleteButton @confirm="doDelete" />
      </div>

      <div class="vers">
        <div class="vers-h">版本历史（快照）</div>
        <div v-for="v in store.personaVersions" :key="v.id" class="ver-row">
          <span class="ver-id">#{{ v.id }}</span>
          <span class="ver-note">{{ snapshotNote(v) || v.note || '' }}</span>
          <span class="ver-time">{{ (v.created_at || '').slice(0, 19) }}</span>
        </div>
        <div v-if="!store.personaVersions.length" class="hint">暂无历史版本</div>
      </div>
    </div>

    <!-- 列表 -->
    <div v-else class="ps-body">
      <button class="new-item" @click="showNew = !showNew">＋ 新建人格</button>
      <div v-if="showNew" class="new-form">
        <input class="fld" v-model="eName" placeholder="人格名称" />
        <textarea class="fld area" v-model="ePrompt" placeholder="系统提示词"></textarea>
        <div class="grid2">
          <input class="fld" v-model="eTone" placeholder="语气" />
          <input class="fld" v-model="eFocus" placeholder="侧重" />
        </div>
        <label class="temp">
          温度：<span class="mono">{{ eTemp }}</span>
          <input type="range" min="0" max="1.5" step="0.1" v-model.number="eTemp" />
        </label>
        <input class="fld" v-model="eStyle" placeholder="风格标签（逗号分隔）" />
        <input class="fld" v-model="eMethods" placeholder="创作方法（逗号分隔）" />
        <input class="fld" v-model="eForbidden" placeholder="禁忌（逗号分隔）" />
        <div class="nf-acts">
          <button class="save" @click="submitNew">创建</button>
          <button class="ghost" @click="showNew = false">取消</button>
        </div>
      </div>

      <div class="list">
        <div v-for="p in store.personas" :key="p.id" class="item" @click="openDetail(p)">
          <div class="it-top">
            <span class="it-name">{{ p.name }}</span>
            <span v-if="p.active" class="badge on">使用中</span>
            <span v-if="p.built_in" class="badge">内置</span>
          </div>
          <div class="it-tags">{{ tagsOf(p) || '（无风格标签）' }}</div>
        </div>
        <div v-if="!store.personas.length" class="hint">还没有人格，点上方新建</div>
      </div>
    </div>

    <!-- 自然语言调整（需 AI 会话） -->
    <div class="adjust">
      <div class="adj-h">自然语言调整（实时覆盖到当前 AI 会话）</div>
      <div class="adj-box">
        <input
          class="adj-q"
          v-model="adjustText"
          :disabled="!store.currentSessionId"
          placeholder="如：更口语一点、少点形容词"
          @keyup.enter="doAdjust"
        />
        <button class="adj-go" :disabled="!store.currentSessionId || !adjustText.trim()" @click="doAdjust">应用</button>
      </div>
      <div v-if="!store.currentSessionId" class="hint">需先在「AI 协作」中开启一个会话</div>
    </div>
  </section>
</template>

<style scoped>
.ps {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.ps-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.ps-title {
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
.ps-err {
  color: var(--theme-error);
  font-size: 12px;
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
  padding: 6px 10px;
  margin: 8px 14px 0;
  border-radius: var(--radius-sm);
}
.ps-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 14px;
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
.badge {
  font-size: 10.5px;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid var(--theme-line);
  color: var(--theme-muted);
}
.badge.on {
  border-color: var(--theme-success);
  color: var(--theme-success);
}
.fld {
  font-family: var(--font-sans);
  font-size: 13px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-paper);
  color: var(--theme-ink);
  padding: 6px 9px;
}
.fld:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.area {
  min-height: 90px;
  resize: vertical;
  line-height: 1.6;
}
.grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.temp {
  font-size: 12px;
  color: var(--theme-ink-soft);
  display: flex;
  align-items: center;
  gap: 8px;
}
.temp .mono {
  font-family: var(--font-mono);
  color: var(--theme-accent);
}
.temp input[type='range'] {
  flex: 1;
}
.det-acts,
.nf-acts {
  display: flex;
  gap: 8px;
}
.save,
.use,
.adj-go {
  font-size: 13px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border: 1px solid var(--theme-solid-bg);
  cursor: pointer;
}
.save:hover,
.use:hover,
.adj-go:hover:not(:disabled) {
  background: var(--theme-solid-hover);
}
.use {
  background: transparent;
  color: var(--theme-accent-hover);
  border-color: var(--theme-accent);
}
.del,
.ghost {
  font-size: 13px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
}
.del {
  border: 1px solid var(--theme-error);
  color: var(--theme-error);
}
.del:hover {
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
}
.ghost {
  border: 1px solid var(--theme-line);
  color: var(--theme-ink-soft);
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
.ver-id {
  font-family: var(--font-mono);
  color: var(--theme-accent);
}
.ver-note {
  color: var(--theme-ink-soft);
}
.ver-time {
  margin-left: auto;
  font-size: 10.5px;
  color: var(--theme-muted);
  font-family: var(--font-mono);
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
.list {
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
.it-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.it-name {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--theme-ink);
}
.it-tags {
  margin-top: 3px;
  font-size: 11.5px;
  color: var(--theme-muted);
}
.adjust {
  border-top: 1px solid var(--theme-line);
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--theme-field);
}
.adj-h {
  font-size: 12px;
  color: var(--theme-muted);
}
.adj-box {
  display: flex;
  gap: 8px;
}
.adj-q {
  flex: 1;
  font-family: var(--font-sans);
  font-size: 13px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-paper);
  color: var(--theme-ink);
  padding: 6px 9px;
}
.adj-q:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.adj-q:disabled {
  opacity: 0.6;
}
.adj-go:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.hint {
  font-size: 12px;
  color: var(--theme-muted);
}
</style>
