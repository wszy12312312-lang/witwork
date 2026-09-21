<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount, computed } from 'vue';
import {
  store,
  loadSettings,
  saveSettings,
  loadBackups,
  createBackup,
  restoreBackup,
  drillBackup,
  deleteBackup,
  exportBook,
  bootstrap,
  reindexKb,
  loadProviders,
  setProviderDefault,
} from '../lib/store';
import { api, type Provider } from '../lib/api';

const emit = defineEmits<{ (e: 'close'): void }>();

type Tab = 'pref' | 'backup' | 'export' | 'model';
const tab = ref<Tab>('pref');

const form = reactive({
  theme: 'dark',
  editor_font_size: 18,
  editor_line_height: 1.8,
  editor_page_width: 720,
  ai_panel_side: 'left',
  layout_scheme: 'A',
  embedding: 'hash',
  autosave_delay_ms: 1500,
  auto_typeset: false,
  punctuation_normalize: true,
  phone_chars_per_page: 350,
  break_days_warn: 3,
  // ---- 表层 UI / 功能面板 ----
  topbar_alpha: 78,
  hud_enabled: false,
  hud_texture: true,
  hud_widgets: 'time,today,countdown,song,focus',
  song_autodetect: true,
  editor_ruled_lines: false,
});

// 功能面板部件开关
const WIDGET_DEFS = [
  { k: 'time', label: '时间日期' },
  { k: 'today', label: '今日事项' },
  { k: 'countdown', label: '日程倒计时' },
  { k: 'song', label: '歌曲信息' },
  { k: 'focus', label: '专注计时' },
];
const widgetSet = computed(
  () => new Set((form.hud_widgets || '').split(',').map((s) => s.trim()).filter(Boolean))
);
function toggleWidget(k: string, on: boolean) {
  const s = new Set(widgetSet.value);
  if (on) s.add(k);
  else s.delete(k);
  form.hud_widgets = WIDGET_DEFS.map((d) => d.k).filter((x) => s.has(x)).join(',');
}

function syncFormFromStore() {
  const c = store.settings || {};
  const num = (k: string, d: number) => (c[k] == null ? d : Number(c[k]));
  form.theme = (c['theme'] as string) || 'dark';
  form.editor_font_size = num('editor_font_size', 18);
  form.editor_line_height = num('editor_line_height', 1.8);
  form.editor_page_width = num('editor_page_width', 720);
  form.ai_panel_side = (c['ai_panel_side'] as string) || 'left';
  form.layout_scheme = (c['layout_scheme'] as string) || 'A';
  form.embedding = (c['embedding'] as string) || 'hash';
  embeddingAtLoad.value = form.embedding;
  needReindex.value = false;
  form.autosave_delay_ms = num('autosave_delay_ms', 1500);
  form.auto_typeset = Boolean(c['auto_typeset'] ?? false);
  form.punctuation_normalize = Boolean(c['punctuation_normalize'] ?? true);
  form.phone_chars_per_page = num('phone_chars_per_page', 350);
  form.break_days_warn = num('break_days_warn', 3);
  form.topbar_alpha = num('topbar_alpha', 78);
  form.hud_enabled = Boolean(c['hud_enabled'] ?? false);
  form.hud_texture = Boolean(c['hud_texture'] ?? true);
  form.hud_widgets = (c['hud_widgets'] as string) || 'time,today,countdown,song,focus';
  form.song_autodetect = c['song_autodetect'] === undefined ? true : Boolean(c['song_autodetect']);
  form.editor_ruled_lines = Boolean(c['editor_ruled_lines'] ?? false);
}

const saving = ref(false);
const savedTip = ref('');

// ---- 外观项的「即时生效」 ----
// 界面统一不透明度：拖动过程中直接改 store（本地即时生效，不发请求），
// 松手 / 停止拖动后再落库。App.vue 会把该值同时注入 --topbar/--panel/--field/--drawer-alpha。
let alphaTimer: ReturnType<typeof setTimeout> | null = null;
function clampAlpha(v: number) {
  const n = Number(v);
  return Number.isFinite(n) ? Math.min(100, Math.max(0, Math.round(n))) : 78;
}
function onAlphaInput() {
  form.topbar_alpha = clampAlpha(form.topbar_alpha);
  store.topbarAlpha = form.topbar_alpha; // 即时预览
  if (alphaTimer) clearTimeout(alphaTimer);
  alphaTimer = setTimeout(persistAlpha, 450);
}
function persistAlpha() {
  if (alphaTimer) {
    clearTimeout(alphaTimer);
    alphaTimer = null;
  }
  store.settingsError = '';
  void saveSettings({ topbar_alpha: form.topbar_alpha });
}
// 主题切换：下拉一改就立即保存并应用（无需再点保存）
async function onThemeChange() {
  const ok = await saveSettings({ theme: form.theme });
  if (ok) {
    savedTip.value = '主题已应用';
    setTimeout(() => (savedTip.value = ''), 1600);
  }
}
onBeforeUnmount(() => {
  if (alphaTimer) clearTimeout(alphaTimer);
});
// 换了嵌入模型后必须全量重索引，否则旧维度向量与新查询不匹配 → 检索静默失效
const embeddingAtLoad = ref('hash');
const needReindex = ref(false);
const reindexing = ref(false);
const reindexTip = ref('');

async function savePref() {
  saving.value = true;
  savedTip.value = '';
  const embeddingChanged = form.embedding !== embeddingAtLoad.value;
  const ok = await saveSettings({ ...form });
  saving.value = false;
  if (!ok) {
    savedTip.value = '保存失败：' + (store.settingsError || '');
    return;
  }
  savedTip.value = '已保存并应用';
  setTimeout(() => (savedTip.value = ''), 2000);
  if (embeddingChanged) {
    embeddingAtLoad.value = form.embedding;
    needReindex.value = true;
    reindexTip.value = '';
  }
}

async function doReindex() {
  reindexing.value = true;
  reindexTip.value = '';
  try {
    await reindexKb();
    needReindex.value = false;
    reindexTip.value = '索引已重建';
  } catch (e) {
    reindexTip.value = (e as Error)?.message || '重建失败';
  } finally {
    reindexing.value = false;
  }
}

// ---- 备份 ----
const backupTag = ref('');
const busy = ref('');
const confirming = ref<{ name: string; kind: 'restore' | 'delete' } | null>(null);

async function doCreate() {
  busy.value = 'create';
  await createBackup(backupTag.value.trim() || undefined);
  backupTag.value = '';
  busy.value = '';
}
async function confirmAction() {
  if (!confirming.value) return;
  const { name, kind } = confirming.value;
  busy.value = name;
  const ok = kind === 'restore' ? await restoreBackup(name) : await deleteBackup(name);
  confirming.value = null;
  busy.value = '';
  if (ok && kind === 'restore') {
    // 恢复会替换数据库，重新拉一次全量状态
    await bootstrap();
    savedTip.value = '已从备份恢复';
    setTimeout(() => (savedTip.value = ''), 2500);
  }
}

// ---- 导出 ----
const exportBookId = ref<number | null>(null);
const exporting = ref('');
const exportError = ref('');
const exportBooks = computed(() => store.books);

async function doExport(kind: 'docx' | 'md' | 'epub' | 'framework') {
  const id = exportBookId.value;
  if (id == null || exporting.value) return;
  exporting.value = kind;
  exportError.value = '';
  try {
    await exportBook(id, kind);
  } catch (e) {
    exportError.value = (e as Error)?.message || '导出失败';
  } finally {
    exporting.value = '';
  }
}

onMounted(async () => {
  await loadSettings();
  syncFormFromStore();
  loadManualSong();
  await loadBackups();
  if (!exportBookId.value && store.currentBookId) exportBookId.value = store.currentBookId;
  await loadProviders();
});

// 手动歌曲：关闭自动检测后在此填写（与功能面板共用 localStorage 键，面板只读展示）
const LS_SONG = 'inkrealm.dock.song';
const manualSong = reactive({ title: '', artist: '' });
function loadManualSong() {
  try {
    const o = JSON.parse(localStorage.getItem(LS_SONG) || '{}');
    manualSong.title = o.title || '';
    manualSong.artist = o.artist || '';
  } catch { /* ignore */ }
}
function saveManualSong() {
  try {
    localStorage.setItem(LS_SONG, JSON.stringify({ title: manualSong.title, artist: manualSong.artist }));
  } catch { /* ignore */ }
}
async function onSongAutoChange() {
  // 立即生效：功能面板会依此切换自动/手动
  await saveSettings({ song_autodetect: form.song_autodetect });
}

// ---- 模型（Provider）管理 ----
const KIND_LABELS: Record<string, string> = {
  mock: '演示', ollama: 'Ollama', openai: 'OpenAI 兼容', anthropic: 'Claude', llamacpp: 'llama.cpp',
};
const modelBusy = ref('');
const modelMsg = ref('');

// 列表增删改查
const editingId = ref<string | null>(null);
const showForm = ref(false);
const formP = reactive({
  id: '',
  kind: 'ollama',
  name: '',
  base_url: 'http://127.0.0.1:11434',
  api_key_ref: '',
  model: '',
  context_window: 32768,
  is_local: 1,
  enabled: 1,
});
function openAdd() {
  editingId.value = null;
  formP.id = '';
  formP.kind = 'ollama';
  formP.name = '';
  formP.base_url = 'http://127.0.0.1:11434';
  formP.api_key_ref = '';
  formP.model = '';
  formP.context_window = 32768;
  formP.is_local = 1;
  formP.enabled = 1;
  showForm.value = true;
  modelMsg.value = '';
}
function openEdit(p: Provider) {
  editingId.value = p.id;
  formP.id = p.id;
  formP.kind = p.kind || 'ollama';
  formP.name = (p.name as string) || '';
  formP.base_url = (p.base_url as string) || '';
  formP.api_key_ref = (p.api_key_ref as string) || '';
  formP.model = (p.model as string) || '';
  formP.context_window = p.context_window || 32768;
  formP.is_local = p.is_local ? 1 : 0;
  formP.enabled = p.enabled ? 1 : 0;
  showForm.value = true;
  modelMsg.value = '';
}
async function saveForm() {
  modelBusy.value = 'save';
  modelMsg.value = '';
  try {
    const payload: Record<string, unknown> = {
      kind: formP.kind,
      name: (formP.name || '').trim() || formP.model || formP.id,
      base_url: formP.base_url ? formP.base_url.trim() : null,
      api_key_ref: formP.api_key_ref ? formP.api_key_ref.trim() : null,
      model: formP.model ? formP.model.trim() : null,
      context_window: Number(formP.context_window) || 8000,
      is_local: formP.is_local ? 1 : 0,
      enabled: formP.enabled ? 1 : 0,
    };
    if (editingId.value) {
      await api.updateProvider(editingId.value, payload);
    } else {
      await api.createProvider({ id: formP.id ? formP.id.trim() : undefined, ...payload });
    }
    await loadProviders();
    showForm.value = false;
    modelMsg.value = '已保存';
    setTimeout(() => (modelMsg.value = ''), 1800);
  } catch (e) {
    modelMsg.value = '保存失败：' + ((e as Error)?.message || String(e));
  } finally {
    modelBusy.value = '';
  }
}
const confirmDel = ref<Provider | null>(null);
async function confirmDelAction() {
  if (!confirmDel.value) return;
  modelBusy.value = 'del';
  try {
    await api.deleteProvider(confirmDel.value.id);
    await loadProviders();
    modelMsg.value = '已删除';
    setTimeout(() => (modelMsg.value = ''), 1800);
  } catch (e) {
    modelMsg.value = '删除失败：' + ((e as Error)?.message || String(e));
  } finally {
    modelBusy.value = '';
    confirmDel.value = null;
  }
}
async function toggleEnabled(p: Provider, on: boolean) {
  try {
    await api.updateProvider(p.id, { enabled: on ? 1 : 0 });
    await loadProviders();
  } catch (e) {
    modelMsg.value = '更新失败：' + ((e as Error)?.message || String(e));
  }
}
async function doSetDefault(p: Provider) {
  modelBusy.value = 'default';
  try {
    await setProviderDefault(p.id);
    modelMsg.value = `已设为默认：${p.name || p.model || p.id}`;
    setTimeout(() => (modelMsg.value = ''), 1800);
  } catch (e) {
    modelMsg.value = '设置失败：' + ((e as Error)?.message || String(e));
  } finally {
    modelBusy.value = '';
  }
}
const testingId = ref<string | null>(null);
const testResults = reactive<Record<string, { ok: boolean; error: string }>>({});
async function doTest(p: Provider) {
  testingId.value = p.id;
  delete testResults[p.id];
  try {
    const r = await api.testProvider(p.id);
    testResults[p.id] = { ok: !!r.ok, error: r.error || (r.ok ? '' : '连接失败') };
  } catch (e) {
    testResults[p.id] = { ok: false, error: (e as Error)?.message || String(e) };
  } finally {
    testingId.value = null;
  }
}
// 探测本地 Ollama 已装模型，一键选用
const discovering = ref(false);
const discoverErr = ref('');
const discoveredModels = ref<string[]>([]);
async function discover() {
  discovering.value = true;
  discoverErr.value = '';
  discoveredModels.value = [];
  try {
    const r = await api.discoverModels();
    if (r.ok) discoveredModels.value = r.models;
    else discoverErr.value = r.error || '未发现已安装模型';
  } catch (e) {
    discoverErr.value = (e as Error)?.message || '探测失败';
  } finally {
    discovering.value = false;
  }
}
function useDiscoveredModel(m: string) {
  openAdd();
  formP.kind = 'ollama';
  formP.name = m;
  formP.model = m;
  formP.base_url = 'http://127.0.0.1:11434';
  formP.is_local = 1;
  formP.enabled = 1;
  discoveredModels.value = [];
}
</script>

<template>
  <div class="set-overlay" @click.self="emit('close')">
    <div class="set-drawer">
      <header class="set-head">
        <div class="set-title">设置</div>
        <button class="x" @click="emit('close')" title="关闭">✕</button>
      </header>

      <nav class="tabs">
        <button class="tab" :class="{ on: tab === 'pref' }" @click="tab = 'pref'">偏好</button>
        <button class="tab" :class="{ on: tab === 'model' }" @click="tab = 'model'">模型</button>
        <button class="tab" :class="{ on: tab === 'backup' }" @click="tab = 'backup'">备份</button>
        <button class="tab" :class="{ on: tab === 'export' }" @click="tab = 'export'">导出</button>
      </nav>

      <div v-if="store.settingsError" class="set-err">⚠ {{ store.settingsError }}</div>

      <div class="set-body">
        <!-- 偏好 -->
        <div v-show="tab === 'pref'" class="pane">
          <div class="grid">
            <label class="fld">
              <span>主题</span>
              <select v-model="form.theme">
                <option value="dark">暗色</option>
                <option value="light">亮色</option>
                <option value="sepia">茶色</option>
              </select>
            </label>
            <label class="fld">
              <span>AI 面板位置</span>
              <select v-model="form.ai_panel_side">
                <option value="left">左侧</option>
                <option value="right">右侧</option>
              </select>
            </label>
            <label class="fld">
              <span>布局方案</span>
              <select v-model="form.layout_scheme">
                <option value="A">A</option>
                <option value="B">B</option>
              </select>
            </label>
            <label class="fld">
              <span>歌曲自动检测（Windows SMTC）</span>
              <select v-model="form.song_autodetect" @change="onSongAutoChange">
                <option :value="true">开启（读系统当前播放）</option>
                <option :value="false">关闭（手动填写）</option>
              </select>
            </label>
            <label class="fld">
              <span>编辑器字号</span>
              <input v-model.number="form.editor_font_size" type="number" min="12" max="32" />
            </label>
            <label class="fld">
              <span>行距</span>
              <input v-model.number="form.editor_line_height" type="number" step="0.1" min="1.2" max="2.4" />
            </label>
            <label class="fld">
              <span>页宽 (px)</span>
              <input v-model.number="form.editor_page_width" type="number" min="480" max="1000" />
            </label>
            <label class="fld">
              <span>自动保存延迟 (ms)</span>
              <input v-model.number="form.autosave_delay_ms" type="number" min="300" max="5000" step="100" />
            </label>
            <label class="fld">
              <span>手机每页字数</span>
              <input v-model.number="form.phone_chars_per_page" type="number" min="150" max="800" />
            </label>
            <label class="fld">
              <span>断更提醒 (天)</span>
              <input v-model.number="form.break_days_warn" type="number" min="1" max="30" />
            </label>
            <label class="fld wide">
              <span>界面整体不透明度 {{ form.topbar_alpha }}%（顶栏与各面板统一生效，拖动即时预览）</span>
              <input
                v-model.number="form.topbar_alpha"
                type="range"
                min="0"
                max="100"
                step="1"
                @input="onAlphaInput"
                @change="persistAlpha"
              />
            </label>
            <label class="fld check">
              <input v-model="form.auto_typeset" type="checkbox" />
              <span>保存时自动排版</span>
            </label>
            <label class="fld check">
              <input v-model="form.punctuation_normalize" type="checkbox" />
              <span>标点归一化</span>
            </label>
            <label class="fld check">
              <input v-model="form.editor_ruled_lines" type="checkbox" />
              <span>写作区信纸横线</span>
            </label>
          </div>
          <div class="sub">功能面板</div>
          <div class="grid">
            <label class="fld">
              <span>功能面板</span>
              <select v-model="form.hud_enabled">
                <option :value="false">关闭</option>
                <option :value="true">开启</option>
              </select>
            </label>
            <label class="fld check">
              <input v-model="form.hud_texture" type="checkbox" />
              <span>质感（扫线）</span>
            </label>
          </div>
          <div class="wgrid">
            <label v-for="w in WIDGET_DEFS" :key="w.k" class="fld check">
              <input
                type="checkbox"
                :checked="widgetSet.has(w.k)"
                @change="toggleWidget(w.k, ($event.target as HTMLInputElement).checked)"
              />
              <span>{{ w.label }}</span>
            </label>
          </div>
          <!-- 手动歌曲：关闭自动检测后在此填写，功能面板只读展示 -->
          <div v-if="!form.song_autodetect" class="manual-song">
            <div class="sub">手动歌曲（功能面板展示）</div>
            <div class="row">
              <input v-model="manualSong.title" class="in" placeholder="曲名" @change="saveManualSong" />
              <input v-model="manualSong.artist" class="in" placeholder="艺术家" @change="saveManualSong" />
            </div>
          </div>
          <div class="acts">
            <button class="save" :disabled="saving" @click="savePref">{{ saving ? '保存中…' : '保存偏好' }}</button>
            <span v-if="savedTip" class="tip">{{ savedTip }}</span>
          </div>
          <div v-if="needReindex" class="reindex">
            <div class="ri-txt">
              ⚠ 嵌入模型已切换为「{{ form.embedding }}」。旧向量维度与新查询不匹配，知识库检索会静默失效——需全量重建索引。
            </div>
            <div class="ri-acts">
              <button class="save" :disabled="reindexing" @click="doReindex">
                {{ reindexing ? '重建中…' : '立即重建索引' }}
              </button>
              <span v-if="reindexTip" class="tip">{{ reindexTip }}</span>
            </div>
          </div>
        </div>

        <!-- 模型（Provider）管理 -->
        <div v-show="tab === 'model'" class="pane">
          <div class="acts">
            <button class="save" :disabled="!!modelBusy" @click="openAdd">+ 新增模型</button>
            <button class="mini" :disabled="discovering" @click="discover">{{ discovering ? '探测中…' : '探测本地 Ollama' }}</button>
            <span v-if="modelMsg" class="tip">{{ modelMsg }}</span>
          </div>

          <!-- 探测结果 -->
          <div v-if="discoveredModels.length" class="disc">
            <div class="disc-t">本地 Ollama 已安装：点击「选用」自动填入新增表单</div>
            <div v-for="m in discoveredModels" :key="m" class="disc-row">
              <span class="disc-name">{{ m }}</span>
              <button class="mini" @click="useDiscoveredModel(m)">选用</button>
            </div>
          </div>
          <div v-if="discoverErr" class="set-err">⚠ {{ discoverErr }}</div>

          <!-- 模型列表 -->
          <div class="rel-list">
            <div v-for="p in store.providers" :key="p.id" class="pr-row" :class="{ def: p.is_default }">
              <div class="pr-main">
                <div class="pr-top">
                  <span class="pr-name">{{ p.name || p.model || p.id }}</span>
                  <span v-if="p.is_default" class="pr-star" title="默认模型">★ 默认</span>
                  <span class="pr-kind">{{ KIND_LABELS[p.kind] || p.kind }}</span>
                  <label class="pr-en">
                    <input type="checkbox" :checked="!!p.enabled" @change="toggleEnabled(p, ($event.target as HTMLInputElement).checked)" />
                    <span>启用</span>
                  </label>
                </div>
                <div class="pr-sub">
                  <span class="pr-model">{{ p.model || '—' }}</span>
                  <span v-if="p.base_url" class="pr-url">{{ p.base_url }}</span>
                  <span v-if="p.context_window" class="pr-cw">窗口 {{ p.context_window }}</span>
                </div>
                <div v-if="testResults[p.id]" class="pr-test" :class="{ bad: !testResults[p.id].ok }">
                  {{ testResults[p.id].ok ? '✓ 连接正常' : '✗ ' + testResults[p.id].error }}
                </div>
              </div>
              <div class="pr-acts">
                <button v-if="!p.is_default" class="mini" :disabled="!!modelBusy" @click="doSetDefault(p)">设为默认</button>
                <button class="mini" :disabled="!!testingId" @click="doTest(p)">{{ testingId === p.id ? '测试…' : '测试' }}</button>
                <button class="mini" @click="openEdit(p)">编辑</button>
                <button class="mini danger" :disabled="!!modelBusy" @click="confirmDel = p">删除</button>
              </div>
            </div>
            <div v-if="!store.providers.length" class="hint">暂无模型，点击「新增模型」或「探测本地 Ollama」。</div>
          </div>

          <!-- 新增/编辑表单 -->
          <div v-if="showForm" class="mform">
            <div class="mform-t">{{ editingId ? '编辑模型' : '新增模型' }}</div>
            <div class="grid">
              <label class="fld">
                <span>类型</span>
                <select v-model="formP.kind">
                  <option value="ollama">Ollama（本地）</option>
                  <option value="openai">OpenAI 兼容</option>
                  <option value="anthropic">Claude (Anthropic)</option>
                  <option value="llamacpp">llama.cpp</option>
                  <option value="mock">演示 (mock)</option>
                </select>
              </label>
              <label class="fld">
                <span>显示名称</span>
                <input v-model.trim="formP.name" placeholder="如 本地写作大模型" />
              </label>
              <label v-if="!editingId" class="fld">
                <span>ID（可选，留空按名称生成）</span>
                <input v-model.trim="formP.id" placeholder="如 qwen3-14b" />
              </label>
              <label class="fld">
                <span>Base URL</span>
                <input v-model.trim="formP.base_url" placeholder="http://127.0.0.1:11434" />
              </label>
              <label class="fld">
                <span>API Key 引用（可选）</span>
                <input v-model.trim="formP.api_key_ref" placeholder="环境变量名或引用" />
              </label>
              <label class="fld">
                <span>模型名</span>
                <input v-model.trim="formP.model" placeholder="如 qwen3:14b" />
              </label>
              <label class="fld">
                <span>上下文窗口 (tokens)</span>
                <input v-model.number="formP.context_window" type="number" min="1024" max="2000000" step="1024" />
              </label>
              <label class="fld check">
                <input v-model="formP.is_local" type="checkbox" :true-value="1" :false-value="0" />
                <span>本地模型</span>
              </label>
              <label class="fld check">
                <input v-model="formP.enabled" type="checkbox" :true-value="1" :false-value="0" />
                <span>启用</span>
              </label>
            </div>
            <div class="acts">
              <button class="save" :disabled="!!modelBusy" @click="saveForm">{{ modelBusy === 'save' ? '保存中…' : '保存' }}</button>
              <button class="ghost" @click="showForm = false">取消</button>
            </div>
          </div>
        </div>

        <!-- 备份 -->
        <div v-show="tab === 'backup'" class="pane">
          <div class="acts">
            <input v-model="backupTag" class="inp" placeholder="标签（可选）" />
            <button class="save" :disabled="busy === 'create'" @click="doCreate">
              {{ busy === 'create' ? '创建中…' : '创建备份' }}
            </button>
          </div>
          <div class="rel-list">
            <div v-for="b in store.backups" :key="b.name" class="bk-row">
              <div class="bk-meta">
                <span class="bk-name">{{ b.name }}</span>
                <span class="bk-sub">{{ b.tag || '—' }} · {{ (b.size / 1024).toFixed(1) }} KB · {{ b.created_at }}</span>
              </div>
              <div class="bk-acts">
                <button class="mini" @click="confirming = { name: b.name, kind: 'restore' }">恢复</button>
                <button class="mini" @click="drillBackup(b.name)">演练</button>
                <button class="mini danger" @click="confirming = { name: b.name, kind: 'delete' }">删除</button>
              </div>
            </div>
            <div v-if="!store.backups.length" class="hint">暂无备份，点击「创建备份」打包数据库与配置。</div>
          </div>
        </div>

        <!-- 导出 -->
        <div v-show="tab === 'export'" class="pane">
          <div class="hint">选择作品后导出。Markdown / EPUB 导出正文与卷章；设定导出世界观/人物/框架。</div>
          <label class="fld">
            <span>作品</span>
            <select v-model.number="exportBookId">
              <option :value="null" disabled>请选择作品</option>
              <option v-for="b in exportBooks" :key="b.id" :value="b.id">{{ b.title || '未命名' }}</option>
            </select>
          </label>
          <div class="acts">
            <button class="save" :disabled="!exportBookId || !!exporting" @click="doExport('docx')">导出 Word</button>
            <button class="save" :disabled="!exportBookId || !!exporting" @click="doExport('md')">导出 Markdown</button>
            <button class="save" :disabled="!exportBookId || !!exporting" @click="doExport('epub')">导出 EPUB</button>
            <button class="save" :disabled="!exportBookId || !!exporting" @click="doExport('framework')">导出设定(MD)</button>
          </div>
          <div v-if="exporting" class="hint">正在生成（{{ exporting }}）…</div>
          <div v-if="exportError" class="set-err">⚠ {{ exportError }}</div>
        </div>
      </div>

      <!-- 确认弹窗 -->
      <div v-if="confirming" class="confirm" @click.self="confirming = null">
        <div class="confirm-box">
          <div class="confirm-txt">
            {{ confirming.kind === 'restore' ? '确定恢复此备份？将覆盖当前数据库与配置（不可撤销）。' : '确定删除此备份？' }}
          </div>
          <div class="confirm-acts">
            <button class="ghost" @click="confirming = null">取消</button>
            <button class="solid" :class="{ danger: confirming.kind === 'delete' }" @click="confirmAction">
              {{ confirming.kind === 'restore' ? '恢复' : '删除' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 模型删除确认 -->
      <div v-if="confirmDel" class="confirm" @click.self="confirmDel = null">
        <div class="confirm-box">
          <div class="confirm-txt">
            确定删除模型「{{ confirmDel.name || confirmDel.model || confirmDel.id }}」？删除默认模型会自动清除默认标记。
          </div>
          <div class="confirm-acts">
            <button class="ghost" @click="confirmDel = null">取消</button>
            <button class="solid danger" :disabled="modelBusy === 'del'" @click="confirmDelAction">删除</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.set-overlay {
  position: fixed;
  inset: 0;
  z-index: 40;
  background: color-mix(in srgb, var(--theme-ink) 35%, transparent);
}
.set-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(480px, 92%);
  display: flex;
  flex-direction: column;
  background: var(--theme-paper);
  border-left: 1px solid var(--theme-line);
  border-radius: 0;
  box-shadow: var(--shadow-panel);
  overflow: hidden;
  z-index: 41;
}
.set-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--theme-line);
}
.set-title {
  font-weight: 700;
  font-size: 16px;
  color: var(--theme-ink);
}
.x {
  border: none;
  background: transparent;
  color: var(--theme-muted);
  font-size: 16px;
  cursor: pointer;
}
.x:hover {
  color: var(--theme-ink);
}
.tabs {
  display: flex;
  gap: 4px;
  padding: 10px 16px 0;
}
.tab {
  font-size: 13px;
  padding: 6px 14px;
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
.set-err {
  color: var(--theme-error);
  font-size: 12px;
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
  padding: 6px 10px;
  margin: 10px 16px 0;
  border-radius: var(--radius-sm);
}
.set-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 14px 18px;
}
.pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.fld {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 12.5px;
  color: var(--theme-ink-soft);
}
.fld > span {
  color: var(--theme-muted);
}
.fld select,
.fld input {
  font-size: 13px;
  padding: 6px 9px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
}
.fld select:focus,
.fld input:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.fld.check {
  flex-direction: row;
  align-items: center;
  gap: 8px;
}
.fld.check input {
  width: 16px;
  height: 16px;
}
.fld.wide {
  grid-column: 1 / -1;
}
.fld input[type='range'] {
  padding: 0;
  accent-color: var(--theme-accent);
}
.wgrid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 10px;
  background: var(--theme-field);
}
.sub {
  font-size: 11.5px;
  letter-spacing: 0.06em;
  color: var(--theme-muted);
  margin-top: 2px;
}
.manual-song {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.manual-song .row {
  display: flex;
  gap: 6px;
}
.manual-song .in {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  padding: 5px 8px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
}
.manual-song .in:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.acts {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.save {
  font-size: 13px;
  padding: 7px 15px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border: 1px solid var(--theme-solid-bg);
}
.save:hover:not(:disabled) {
  background: var(--theme-solid-hover);
}
.save:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.tip {
  font-size: 12px;
  color: var(--theme-success);
}
.reindex {
  border: 1px solid color-mix(in srgb, var(--theme-error) 45%, var(--theme-line));
  background: color-mix(in srgb, var(--theme-error) 10%, transparent);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ri-txt {
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--theme-ink);
}
.ri-acts {
  display: flex;
  gap: 10px;
  align-items: center;
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
.inp:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.rel-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bk-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 8px 11px;
  background: var(--theme-field);
}
.bk-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.bk-name {
  font-weight: 600;
  font-size: 13px;
  color: var(--theme-ink);
  font-family: var(--font-mono);
}
.bk-sub {
  font-size: 11px;
  color: var(--theme-muted);
}
.bk-acts {
  display: flex;
  gap: 6px;
}
.mini {
  font-size: 12px;
  padding: 4px 10px;
  border: 1px solid var(--theme-line);
  border-radius: 4px;
  background: transparent;
  color: var(--theme-ink-soft);
  cursor: pointer;
}
.mini:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.mini.danger {
  color: var(--theme-error);
  border-color: color-mix(in srgb, var(--theme-error) 50%, var(--theme-line));
}
.hint {
  font-size: 12px;
  color: var(--theme-muted);
}
.confirm {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--theme-scrim);
}
.confirm-box {
  width: min(360px, 90%);
  background: var(--theme-paper);
  border: 1px solid var(--theme-line);
  border-radius: var(--radius);
  padding: 18px;
  box-shadow: var(--shadow-panel);
}
.confirm-txt {
  font-size: 13.5px;
  color: var(--theme-ink);
  line-height: 1.6;
}
.confirm-acts {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
}
.ghost {
  font-size: 13px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--theme-ink-soft);
  border: 1px solid var(--theme-line);
  cursor: pointer;
}
/* ---- 模型管理 ---- */
.disc {
  display: flex;
  flex-direction: column;
  gap: 6px;
  border: 1px solid color-mix(in srgb, var(--theme-accent) 45%, var(--theme-line));
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  background: var(--theme-field);
}
.disc-t {
  font-size: 12px;
  color: var(--theme-muted);
}
.disc-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.disc-name {
  font-size: 13px;
  font-family: var(--font-mono);
  color: var(--theme-ink);
}
.pr-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 9px 11px;
  background: var(--theme-field);
}
.pr-row.def {
  border-color: color-mix(in srgb, var(--theme-accent) 55%, var(--theme-line));
  background: color-mix(in srgb, var(--theme-accent) 8%, var(--theme-field));
}
.pr-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}
.pr-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.pr-name {
  font-weight: 600;
  font-size: 13.5px;
  color: var(--theme-ink);
}
.pr-star {
  font-size: 11px;
  color: var(--theme-solid-fg);
  background: var(--theme-accent);
  border-radius: 3px;
  padding: 1px 6px;
}
.pr-kind {
  font-size: 11px;
  color: var(--theme-muted);
  border: 1px solid var(--theme-line);
  border-radius: 3px;
  padding: 1px 6px;
}
.pr-en {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  color: var(--theme-muted);
  margin-left: auto;
}
.pr-en input {
  width: 14px;
  height: 14px;
}
.pr-sub {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 11.5px;
  color: var(--theme-muted);
}
.pr-model {
  font-family: var(--font-mono);
  color: var(--theme-ink-soft);
}
.pr-test {
  font-size: 11.5px;
  color: var(--theme-success);
}
.pr-test.bad {
  color: var(--theme-error);
}
.pr-acts {
  display: flex;
  flex-direction: column;
  gap: 5px;
  align-items: stretch;
}
.mform {
  display: flex;
  flex-direction: column;
  gap: 10px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 12px;
  background: var(--theme-paper);
}
.mform-t {
  font-size: 13px;
  font-weight: 600;
  color: var(--theme-ink);
}
.solid {
  font-size: 13px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border: 1px solid var(--theme-solid-bg);
  cursor: pointer;
}
.solid.danger {
  background: var(--theme-error);
  border-color: var(--theme-error);
  color: #2a0f0a;
}
@media (max-width: 560px) {
  .grid {
    grid-template-columns: 1fr;
  }
  .wgrid {
    grid-template-columns: 1fr;
  }
}
/* 抽屉/弹层的主题外观位于全局样式表 tokens.css。
 * ⚠️ 切勿在此用 `:global([data-theme=...]) .child`：Vue 的 scoped 编译会把后代选择器
 * 整段丢掉，只留 `[data-theme=...]`，于是规则直接命中 <html>（曾导致 pointer-events:none
 * 让全站不可点击、字体被压到 12.5px、文字全变橙金、整页多出扫线混合）。 */
</style>
