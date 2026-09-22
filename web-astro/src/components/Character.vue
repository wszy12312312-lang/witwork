<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import {
  store,
  loadCharacters,
  openCharacter,
  createCharacter,
  saveCharacter,
  deleteCharacter,
  aliasesOf,
  addRelation,
  deleteRelation,
  scanAppearances,
  extractCandidates,
  applyPatch,
  rejectPatch,
} from '../lib/store';
import type { Character, Patch } from '../lib/api';
import RareDeleteButton from './RareDeleteButton.vue';

const emit = defineEmits<{ (e: 'close'): void }>();

type Tab = 'cards' | 'relations' | 'appearances' | 'extract';
const tab = ref<Tab>('cards');

// ---- 人物卡：编辑缓冲 ----
const eName = ref('');
const eAppearance = ref('');
const ePersonality = ref('');
const eCatchphrase = ref('');
const eStatus = ref('');
const eTaboo = ref('');
const eAliases = ref(''); // 逗号分隔

// 新增缓冲
const newName = ref('');
const newAppearance = ref('');

function loadBuf(c: Character | null) {
  if (!c) return;
  eName.value = c.name || '';
  eAppearance.value = c.appearance || '';
  ePersonality.value = c.personality || '';
  eCatchphrase.value = c.catchphrase || '';
  eStatus.value = c.status_current || '';
  eTaboo.value = c.taboo || '';
  eAliases.value = aliasesOf(c).join('，');
}

watch(
  () => store.currentCharacterId,
  () => {
    if (store.characterCurrent) loadBuf(store.characterCurrent);
  }
);

async function pickCard(c: Character) {
  // 列表项是完整行，但仍走 openCharacter 以连带加载出场/关系，避免「列表项当详情」类缺陷
  await openCharacter(c.id);
  loadBuf(store.characterCurrent);
  detailOpen.value = true;
}

// 编辑详情卡展开/收起：保存成功后自动收起，点头部可再展开
const detailOpen = ref(true);
const saveTip = ref('');
let tipTimer: ReturnType<typeof setTimeout> | null = null;

async function newCard() {
  const n = newName.value.trim();
  if (!n) return;
  await createCharacter(n, { appearance: newAppearance.value.trim() || null });
  newName.value = '';
  newAppearance.value = '';
}

async function saveCard() {
  if (!store.currentCharacterId) return;
  const aliases = eAliases.value
    .split(/[，,]/)
    .map((s) => s.trim())
    .filter(Boolean);
  await saveCharacter(store.currentCharacterId, {
    name: eName.value.trim(),
    appearance: eAppearance.value.trim() || null,
    personality: ePersonality.value.trim() || null,
    catchphrase: eCatchphrase.value.trim() || null,
    status_current: eStatus.value.trim() || null,
    taboo: eTaboo.value.trim() || null,
    aliases,
  });
  // 保存失败（charError 有值）不收起，让用户看到错误；成功则收起编辑卡并短暂提示
  if (store.charError) return;
  detailOpen.value = false;
  saveTip.value = '已保存 ✓';
  if (tipTimer) clearTimeout(tipTimer);
  tipTimer = setTimeout(() => (saveTip.value = ''), 2000);
}

async function delCard() {
  if (!store.currentCharacterId) return;
  await deleteCharacter(store.currentCharacterId);
}

// ---- 关系网 ----
const relFrom = ref<number | null>(null);
const relTo = ref<number | null>(null);
const relType = ref('');
const relNote = ref('');

function nameOf(id: number): string {
  const c = store.characters.find((x) => x.id === id);
  return c ? c.name : `#${id}`;
}

function relateCurrent() {
  relFrom.value = store.currentCharacterId;
}

async function addRel() {
  if (!relFrom.value || !relTo.value) return;
  if (relFrom.value === relTo.value) return;
  await addRelation(relFrom.value, relTo.value, relType.value.trim(), relNote.value.trim() || null);
  relType.value = '';
  relNote.value = '';
}

// ---- 出场 ----
const scanText = ref('');
const scanMsg = ref('');

// ---- 候选抽取 ----
const exText = ref('');

watch(tab, (t) => {
  if (t === 'appearances' && !scanText.value) scanText.value = store.currentChapter?.content || '';
  if (t === 'extract' && !exText.value) exText.value = store.currentChapter?.content || '';
});

async function doScan() {
  const n = await scanAppearances(scanText.value);
  scanMsg.value = n ? `已记录 ${n} 处出场` : '未检测到出场';
}

async function doExtract() {
  await extractCandidates(exText.value);
}

const patches = computed(() => store.patches as Patch[]);

function patchContent(p: Patch): string {
  try {
    const f = JSON.parse(p.fields_json || '{}');
    return f.content || '';
  } catch {
    return '';
  }
}

function quickRelateCurrent() {
  relateCurrent();
  tab.value = 'relations';
}

const hasBook = computed(() => !!store.currentBookId);
</script>

<template>
  <section class="ch">
    <header class="ch-head">
      <div class="ch-title">人物卡</div>
      <button class="x" @click="emit('close')" title="关闭">✕</button>
    </header>

    <nav class="tabs">
      <button class="tab" :class="{ on: tab === 'cards' }" @click="tab = 'cards'">人物卡</button>
      <button class="tab" :class="{ on: tab === 'relations' }" @click="tab = 'relations'">关系网</button>
      <button class="tab" :class="{ on: tab === 'appearances' }" @click="tab = 'appearances'">出场</button>
      <button class="tab" :class="{ on: tab === 'extract' }" @click="tab = 'extract'">候选抽取</button>
    </nav>

    <div v-if="!hasBook" class="ch-err">请先打开一个作品。</div>
    <div v-else-if="store.charError" class="ch-err">⚠ {{ store.charError }}</div>

    <div v-if="hasBook" class="ch-body">
      <!-- 人物卡 -->
      <div v-show="tab === 'cards'" class="pane">
        <div class="new">
          <input v-model="newName" class="inp" placeholder="新人物姓名" />
          <input v-model="newAppearance" class="inp grow" placeholder="外貌（可选）" />
          <button class="add" :disabled="!newName.trim()" @click="newCard">＋ 新建</button>
        </div>

        <div class="list">
          <div
            v-for="c in store.characters"
            :key="c.id"
            class="row"
            :class="{ on: c.id === store.currentCharacterId }"
            @click="pickCard(c)"
          >
            <b>{{ c.name }}</b>
            <span v-if="c.kb_item_id" class="tag">已同步知识库</span>
            <span class="muted">{{ (c.appearance || '').slice(0, 14) }}</span>
          </div>
          <div v-if="!store.characters.length" class="hint">还没有人物，先新建一个吧。</div>
        </div>

        <div v-if="store.characterCurrent" class="detail">
          <div class="detail-h" :title="detailOpen ? '点击收起' : '点击展开'" @click="detailOpen = !detailOpen">
            <span class="detail-tri">{{ detailOpen ? '▾' : '▸' }}</span>
            <span>编辑：{{ store.characterCurrent.name }}</span>
            <span v-if="saveTip" class="ok">{{ saveTip }}</span>
            <span class="detail-spacer"></span>
            <RareDeleteButton @confirm="delCard" @click.stop />
          </div>
          <template v-if="detailOpen">
          <label class="lbl">姓名</label>
          <input v-model="eName" class="inp" />
          <label class="lbl">别名（逗号分隔）</label>
          <input v-model="eAliases" class="inp" placeholder="如：阿明，小明" />
          <label class="lbl">外貌</label>
          <textarea v-model="eAppearance" class="ta" rows="2"></textarea>
          <label class="lbl">性格</label>
          <textarea v-model="ePersonality" class="ta" rows="2"></textarea>
          <label class="lbl">口癖</label>
          <input v-model="eCatchphrase" class="inp" placeholder="口头禅 / 惯用语" />
          <label class="lbl">当前状态</label>
          <input v-model="eStatus" class="inp" placeholder="如：重伤昏迷中" />
          <label class="lbl">禁忌</label>
          <input v-model="eTaboo" class="inp" placeholder="不可触碰的雷点" />
          <div class="acts">
            <button class="save" @click="saveCard">保存</button>
            <button class="rel" @click="quickRelateCurrent">＋ 加关系</button>
          </div>
          </template>
        </div>
      </div>

      <!-- 关系网 -->
      <div v-show="tab === 'relations'" class="pane">
        <div class="rel-form">
          <select v-model.number="relFrom" class="inp">
            <option :value="null" disabled>来源人物</option>
            <option v-for="c in store.characters" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
          <input v-model="relType" class="inp grow" placeholder="关系（如：师徒/宿敌）" />
          <select v-model.number="relTo" class="inp">
            <option :value="null" disabled>对象人物</option>
            <option v-for="c in store.characters" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
          <button class="add" :disabled="!relFrom || !relTo || relFrom === relTo" @click="addRel">＋ 添加</button>
        </div>
        <input v-model="relNote" class="inp note" placeholder="备注（可选）" />
        <div class="rel-list">
          <div v-for="r in store.relations" :key="r.id" class="rel-row">
            <span><b>{{ nameOf(r.from_id) }}</b> — {{ r.relation || '关系' }} → <b>{{ nameOf(r.to_id) }}</b></span>
            <button class="rm" @click="deleteRelation(r.id)">✕</button>
          </div>
          <div v-if="!store.relations.length" class="hint">还没有关系，添加一条吧。</div>
        </div>
      </div>

      <!-- 出场 -->
      <div v-show="tab === 'appearances'" class="pane">
        <div v-if="!store.currentCharacterId" class="hint">先在「人物卡」里选中一个人物，再扫描其出场。</div>
        <template v-else>
          <div class="ap-h">为「{{ store.characterCurrent?.name }}」扫描出场</div>
          <textarea v-model="scanText" class="ta big" placeholder="粘贴该人物出场的正文段落…"></textarea>
          <div class="acts">
            <button class="save" @click="doScan">扫描出场</button>
            <span v-if="scanMsg" class="ok">{{ scanMsg }}</span>
          </div>
          <div class="rel-list">
            <div v-for="a in store.appearances" :key="a.id" class="ap-row">
              <div class="ap-sum">第 {{ a.chapter_id }} 章 · {{ a.summary }}</div>
              <div class="ap-ex">{{ a.excerpt }}</div>
            </div>
            <div v-if="!store.appearances.length" class="hint">还没有出场记录。</div>
          </div>
        </template>
      </div>

      <!-- 候选抽取 -->
      <div v-show="tab === 'extract'" class="pane">
        <div class="hint">从正文 / 对话中识别可能的人物，产出待确认候选（归档进知识库 character 分区）。</div>
        <textarea v-model="exText" class="ta big" placeholder="粘贴正文或对话片段…"></textarea>
        <div class="acts">
          <button class="save" @click="doExtract">抽取候选</button>
        </div>
        <div class="rel-list">
          <div v-for="p in patches" :key="p.id" class="patch-row">
            <div class="patch-t">{{ p.title }} <span class="tag">{{ p.op }}</span></div>
            <div class="patch-r">{{ p.reason }}</div>
            <div class="patch-c">{{ patchContent(p) }}</div>
            <div class="acts">
              <button class="save sm" @click="applyPatch(p.id)">应用归档</button>
              <button class="rm sm" @click="rejectPatch(p.id)">忽略</button>
            </div>
          </div>
          <div v-if="!patches.length" class="hint">暂无候选。</div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.ch {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.ch-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.ch-title {
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
.ch-err {
  color: var(--theme-error);
  font-size: 12px;
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
  padding: 6px 10px;
  margin: 8px 14px 0;
  border-radius: var(--radius-sm);
}
.ch-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.pane {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.new {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.inp {
  font-size: 13px;
  padding: 6px 9px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
}
.inp.grow {
  flex: 1;
  min-width: 120px;
}
.inp.note {
  width: 100%;
}
.inp:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.add,
.save,
.rel,
.rm {
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
.rel,
.rm {
  background: transparent;
  border: 1px solid var(--theme-line);
  color: var(--theme-ink-soft);
}
.rel:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.rm:hover {
  border-color: var(--theme-error);
  color: var(--theme-error);
}
.list {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--theme-line);
  cursor: pointer;
  font-size: 13px;
  color: var(--theme-ink-soft);
}
.row:last-child {
  border-bottom: none;
}
.row:hover {
  background: var(--theme-field);
}
.row.on {
  background: var(--theme-field);
  color: var(--theme-ink);
}
.tag {
  font-size: 10.5px;
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid var(--theme-accent);
  color: var(--theme-accent-hover);
}
.muted {
  color: var(--theme-muted);
  font-size: 12px;
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
  gap: 6px;
  font-size: 13px;
  color: var(--theme-ink);
  margin-bottom: 2px;
  cursor: pointer;
  user-select: none;
}
.detail-tri {
  font-size: 11px;
  color: var(--theme-muted);
  width: 12px;
}
.detail-spacer {
  flex: 1;
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
.lbl {
  font-size: 11.5px;
  color: var(--theme-muted);
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
.acts {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.rel-form {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.rel-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rel-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12.5px;
  color: var(--theme-ink-soft);
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 7px 9px;
  background: var(--theme-field);
}
.rel-row b {
  color: var(--theme-ink);
}
.ap-h {
  font-size: 13px;
  color: var(--theme-ink);
  font-weight: 600;
}
.ap-row {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  background: var(--theme-field);
}
.ap-sum {
  font-size: 12px;
  color: var(--theme-accent-hover);
  margin-bottom: 3px;
}
.ap-ex {
  font-size: 12px;
  color: var(--theme-muted);
  white-space: pre-wrap;
  word-break: break-word;
}
.patch-row {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  background: var(--theme-field);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.patch-t {
  font-size: 13px;
  color: var(--theme-ink);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}
.patch-r {
  font-size: 11.5px;
  color: var(--theme-muted);
}
.patch-c {
  font-size: 12px;
  color: var(--theme-ink-soft);
  white-space: pre-wrap;
  word-break: break-word;
}
.ok {
  font-size: 12px;
  color: var(--theme-success);
}
.hint {
  font-size: 12px;
  color: var(--theme-muted);
}
.save.sm,
.rm.sm {
  font-size: 12px;
  padding: 3px 10px;
}
</style>
