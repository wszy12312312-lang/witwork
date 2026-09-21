<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import {
  store,
  runWordFreq,
  runAiTaste,
  runCompliance,
  loadServices,
} from '../lib/store';

const emit = defineEmits<{ (e: 'close'): void }>();

type Tab = 'freq' | 'taste' | 'compliance' | 'services';
const tab = ref<Tab>('freq');

const hasBook = computed(() => !!store.currentBookId);
const hasChapter = computed(() => !!store.currentChapter);

const complianceCustom = ref('');
const tasteLevel = computed(() => {
  const s = store.toolsTaste?.score ?? 0;
  if (s >= 70) return { label: '高度 AI 味', color: 'var(--theme-error)' };
  if (s >= 40) return { label: '偏机械', color: '#c98a3a' };
  if (s >= 20) return { label: '略规整', color: 'var(--theme-accent)' };
  return { label: '自然', color: 'var(--theme-success)' };
});

onMounted(async () => {
  await loadServices();
});
</script>

<template>
  <section class="tl">
    <header class="tl-head">
      <div class="tl-title">工具箱</div>
      <button class="x" @click="emit('close')" title="关闭">✕</button>
    </header>

    <nav class="tabs">
      <button class="tab" :class="{ on: tab === 'freq' }" @click="tab = 'freq'">高频词</button>
      <button class="tab" :class="{ on: tab === 'taste' }" @click="tab = 'taste'">AI 味</button>
      <button class="tab" :class="{ on: tab === 'compliance' }" @click="tab = 'compliance'">合规</button>
      <button class="tab" :class="{ on: tab === 'services' }" @click="tab = 'services'">外部服务</button>
    </nav>

    <div v-if="!hasBook" class="tl-err">请先打开一个作品。</div>
    <div v-else-if="store.toolsError" class="tl-err">⚠ {{ store.toolsError }}</div>

    <div v-if="hasBook" class="tl-body">
      <!-- 高频词 -->
      <div v-show="tab === 'freq'" class="pane">
        <div class="hint">基于当前章节正文，提取 2-4 字高频词（剔除停用字与短词），辅助发现口头禅。</div>
        <div class="acts">
          <button class="save" :disabled="!hasChapter" @click="runWordFreq(50)">分析当前章节</button>
        </div>
        <div v-if="!hasChapter" class="hint">打开一个章节后即可分析。</div>
        <div class="rel-list">
          <div v-for="w in store.toolsWords" :key="w.word" class="wf-row">
            <span class="wf">{{ w.word }}</span>
            <span class="wc">×{{ w.count }}</span>
          </div>
          <div v-if="hasChapter && !store.toolsWords.length" class="hint">点击「分析当前章节」查看高频词。</div>
        </div>
      </div>

      <!-- AI 味 -->
      <div v-show="tab === 'taste'" class="pane">
        <div class="hint">逐段打分（句长越均匀、重复 n-gram 越多、AI 过渡词越密 → 越像 AI 生成）。</div>
        <div class="acts">
          <button class="save" :disabled="!hasChapter" @click="runAiTaste">分析当前章节</button>
        </div>
        <div v-if="store.toolsTaste" class="score-box">
          <div class="score-num" :style="{ color: tasteLevel.color }">{{ store.toolsTaste.score }}</div>
          <div class="score-lv" :style="{ color: tasteLevel.color }">{{ tasteLevel.label }}</div>
        </div>
        <div v-if="store.toolsTaste" class="rel-list">
          <div v-for="p in store.toolsTaste.paragraphs" :key="p.index" class="taste-row">
            <span class="ts" :style="{ color: p.score >= 40 ? 'var(--theme-error)' : p.score >= 20 ? '#c98a3a' : 'var(--theme-success)' }">{{ p.score }}</span>
            <span class="tt">{{ p.text }}…</span>
          </div>
        </div>
        <div v-if="!hasChapter" class="hint">打开一个章节后即可分析。</div>
      </div>

      <!-- 合规 -->
      <div v-show="tab === 'compliance'" class="pane">
        <div class="hint">扫描当前章节是否命中内置合规词库（可附加自定义词，逗号分隔）。</div>
        <input v-model="complianceCustom" class="inp full" placeholder="自定义词（可选，逗号分隔）" />
        <div class="acts">
          <button class="save" :disabled="!hasChapter" @click="runCompliance(complianceCustom.split(/[，,]/).map((s) => s.trim()).filter(Boolean))">扫描当前章节</button>
        </div>
        <div v-if="!hasChapter" class="hint">打开一个章节后即可扫描。</div>
        <div v-if="store.toolsCompliance" class="comp-sum">
          命中 <b>{{ store.toolsCompliance.total }}</b> 处（词库 {{ store.toolsCompliance.word_count }} 条）
        </div>
        <div class="rel-list">
          <div v-for="h in store.toolsCompliance?.hits" :key="h.word" class="comp-row">
            <span class="cw">{{ h.word }}</span>
            <span class="cc">×{{ h.count }}</span>
            <span class="cx">…{{ h.context }}…</span>
          </div>
          <div v-if="hasChapter && store.toolsCompliance && !store.toolsCompliance.hits.length" class="hint">未发现命中合规词。</div>
        </div>
      </div>

      <!-- 外部服务 -->
      <div v-show="tab === 'services'" class="pane">
        <div class="hint">探测本机可选服务；未启动则置灰并给安装提示。</div>
        <div class="rel-list" v-if="store.toolsServices">
          <div v-for="(s, key) in store.toolsServices" :key="key" class="svc-row">
            <span class="svc-name">{{ key === 'sd_webui' ? 'SD WebUI' : key === 'comfyui' ? 'ComfyUI' : 'TTS' }}</span>
            <span class="svc-dot" :class="s.available ? 'on' : 'off'"></span>
            <span class="svc-hint">{{ s.hint }}</span>
          </div>
        </div>
        <div v-else class="hint">探测中…</div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.tl {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.tl-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.tl-title {
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
.tl-err {
  color: var(--theme-error);
  font-size: 12px;
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
  padding: 6px 10px;
  margin: 8px 14px 0;
  border-radius: var(--radius-sm);
}
.tl-body {
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
.inp {
  font-size: 13px;
  padding: 6px 9px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
}
.inp.full {
  width: 100%;
}
.inp:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.acts {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.save {
  font-size: 13px;
  padding: 6px 13px;
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
.score-box {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.score-num {
  font-size: 28px;
  font-weight: 700;
  font-family: var(--font-mono);
}
.score-lv {
  font-size: 13px;
}
.rel-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.wf-row {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 5px 9px;
  background: var(--theme-field);
  font-size: 13px;
}
.wf {
  color: var(--theme-ink);
  font-weight: 600;
}
.wc {
  color: var(--theme-muted);
  font-family: var(--font-mono);
  font-size: 11px;
  margin-left: auto;
}
.taste-row {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 5px 9px;
  background: var(--theme-field);
  font-size: 12.5px;
}
.ts {
  font-family: var(--font-mono);
  font-weight: 700;
  width: 28px;
  text-align: center;
}
.tt {
  color: var(--theme-ink-soft);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.comp-sum {
  font-size: 12.5px;
  color: var(--theme-ink-soft);
}
.comp-row {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 5px 9px;
  background: var(--theme-field);
  font-size: 12.5px;
}
.cw {
  color: var(--theme-error);
  font-weight: 600;
}
.cc {
  color: var(--theme-muted);
  font-family: var(--font-mono);
  font-size: 11px;
}
.cx {
  color: var(--theme-ink-soft);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-left: auto;
  max-width: 60%;
}
.svc-row {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  background: var(--theme-field);
  font-size: 12.5px;
}
.svc-name {
  color: var(--theme-ink);
  font-weight: 600;
}
.svc-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
}
.svc-dot.on {
  background: var(--theme-success);
}
.svc-dot.off {
  background: var(--theme-muted);
}
.svc-hint {
  color: var(--theme-ink-soft);
}
.hint {
  font-size: 12px;
  color: var(--theme-muted);
}
</style>
