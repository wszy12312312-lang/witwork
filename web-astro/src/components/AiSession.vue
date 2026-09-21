<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue';
import {
  store,
  openSession,
  createSessionForBook,
  deleteSession,
  setSessionProvider,
  sendMessage,
  stopStreaming,
  type SessionMessage,
  type Citation,
} from '../lib/store';

const emit = defineEmits<{ (e: 'close'): void }>();

const input = ref('');
const box = ref<HTMLElement | null>(null);

const enabledProviders = computed(() => store.providers.filter((p) => p.enabled));
const activeSession = computed(() => store.sessions.find((s) => s.id === store.currentSessionId) || null);

const canSend = computed(() => !!store.currentSessionId && !!input.value.trim() && !store.streaming);

async function onProviderChange(e: Event) {
  const pid = (e.target as HTMLSelectElement).value || null;
  store.draftProviderId = pid;
  if (store.currentSessionId) await setSessionProvider(store.currentSessionId, pid);
}

async function doSend() {
  const text = input.value.trim();
  if (!text || !canSend.value) return;
  input.value = '';
  await sendMessage(text);
}

async function doNew() {
  await createSessionForBook();
  await nextTick(() => scrollToEnd());
}

function isLive(m: SessionMessage): boolean {
  return !!(m as SessionMessage & { _live?: boolean })._live;
}

function scrollToEnd() {
  nextTick(() => {
    const el = box.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

watch(
  () => store.sessionMessages.map((m) => (m as SessionMessage & { _live?: boolean })._live ? m.content.length : -1).join(','),
  () => scrollToEnd()
);
watch(() => store.currentSessionId, () => scrollToEnd());
</script>

<template>
  <section class="ai">
    <header class="ai-head">
      <div class="ai-title">
        <span class="dot" :class="{ live: store.streaming }"></span>
        AI 协作会话
      </div>
      <button class="x" @click="emit('close')" title="关闭">✕</button>
    </header>

    <!-- provider 选择 -->
    <div class="ai-prov">
      <label class="pv-label">模型</label>
      <select class="pv-sel" :value="store.draftProviderId || ''" @change="onProviderChange">
        <option v-for="p in enabledProviders" :key="p.id" :value="p.id">
          {{ p.name || p.kind }} · {{ p.model || p.kind }}
        </option>
        <option v-if="!enabledProviders.length" value="" disabled>无可用模型</option>
      </select>
      <button v-if="!store.currentSessionId" class="new-sess" @click="doNew">＋ 新会话</button>
    </div>

    <!-- 会话列表 -->
    <div v-if="store.sessions.length" class="sess-row">
      <button
        v-for="s in store.sessions"
        :key="s.id"
        class="sess-chip"
        :class="{ on: s.id === store.currentSessionId }"
        @click="openSession(s.id)"
      >
        <span class="sc-title">{{ s.title }}</span>
        <span class="sc-del" @click.stop="deleteSession(s.id)" title="删除">✕</span>
      </button>
    </div>

    <!-- 未建会话 -->
    <div v-if="!store.currentSessionId" class="ai-empty">
      <p>还没有会话。</p>
      <button class="new-sess big" @click="doNew">＋ 新建协作会话</button>
      <p class="hint">AI 会结合知识库检索、人格与当前章节上下文作答，并给出引用卡。</p>
    </div>

    <!-- 消息流 -->
    <div v-else ref="box" class="ai-msgs">
      <template v-for="(m, i) in store.sessionMessages" :key="i">
        <div class="row" :class="m.role === 'user' ? 'u' : 'a'">
          <div class="bubble" :class="{ live: isLive(m) }">
            <!-- 引用卡 -->
            <div v-if="m.role === 'assistant' && (m.refs as Citation[] | null)?.length" class="refs">
              <div v-for="c in (m.refs as Citation[])" :key="c.n" class="ref" :title="c.snippet">
                <span class="rn">[{{ c.n }}]</span>
                <span class="rt">{{ c.title }}</span>
                <span class="rs">{{ c.section_title }}</span>
              </div>
            </div>
            <div v-if="m.role === 'assistant' && isLive(m) && !m.content" class="thinking">
              思考中<span class="cur">▍</span>
            </div>
            <pre v-else class="ctext">{{ m.content }}</pre>
            <div v-if="m.role === 'assistant' && m.token_count" class="tok">
              ≈{{ m.token_count }} tokens
            </div>
          </div>
        </div>
      </template>
      <div v-if="store.aiError" class="ai-err">⚠ {{ store.aiError }}</div>
    </div>

    <!-- 输入 -->
    <footer v-if="store.currentSessionId" class="ai-input">
      <textarea
        v-model="input"
        class="ai-ta"
        placeholder="问 AI 点什么，或让它接着写…（Enter 发送 / Shift+Enter 换行）"
        @keydown.enter.exact.prevent="doSend"
      ></textarea>
      <div class="ai-btns">
        <button v-if="store.streaming" class="stop" @click="stopStreaming">■ 停止</button>
        <button v-else class="send" :disabled="!canSend" @click="doSend">发送 ↵</button>
      </div>
    </footer>

    <div v-if="activeSession" class="ai-foot">
      当前会话：{{ activeSession.title }}
    </div>
  </section>
</template>

<style scoped>
.ai {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.ai-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.ai-title {
  font-weight: 700;
  font-size: 15px;
  color: var(--theme-ink);
  display: flex;
  align-items: center;
  gap: 8px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--theme-muted);
}
.dot.live {
  background: var(--theme-success);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--theme-success) 30%, transparent);
  animation: pulse 1s var(--motion) infinite;
}
@keyframes pulse {
  50% {
    opacity: 0.4;
  }
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
.ai-prov {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.pv-label {
  font-size: 12px;
  color: var(--theme-muted);
}
.pv-sel {
  flex: 1;
  font-size: 13px;
  padding: 5px 8px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
}
.pv-sel:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.new-sess {
  font-size: 12px;
  padding: 5px 10px;
  border: 1px solid var(--theme-accent);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--theme-accent-hover);
  cursor: pointer;
  white-space: nowrap;
}
.new-sess.big {
  font-size: 14px;
  padding: 8px 16px;
  margin-top: 8px;
}
.new-sess:hover {
  background: var(--theme-field);
}
.sess-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 8px 14px;
  border-bottom: 1px solid var(--theme-line);
  max-height: 96px;
  overflow: auto;
}
.sess-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 4px 8px;
  border: 1px solid var(--theme-line);
  border-radius: 999px;
  background: transparent;
  color: var(--theme-ink-soft);
  cursor: pointer;
}
.sess-chip.on {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
  background: var(--theme-field);
}
.sc-del {
  color: var(--theme-muted);
  font-size: 10px;
}
.sc-del:hover {
  color: var(--theme-error);
}
.ai-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 20px;
  color: var(--theme-muted);
  text-align: center;
}
.ai-empty .hint {
  font-size: 12px;
  max-width: 280px;
}
.ai-msgs {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.row {
  display: flex;
}
.row.u {
  justify-content: flex-end;
}
.row.a {
  justify-content: flex-start;
}
.bubble {
  max-width: 88%;
  padding: 10px 12px;
  border-radius: var(--radius);
  font-size: 13.5px;
  line-height: 1.7;
  white-space: normal;
}
.row.u .bubble {
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
  border-bottom-right-radius: 4px;
}
.row.a .bubble {
  background: var(--theme-field);
  color: var(--theme-ink);
  border: 1px solid var(--theme-line);
  border-bottom-left-radius: 4px;
}
.bubble.live {
  border-color: var(--theme-accent);
}
.ctext {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-sans);
}
.refs {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--theme-line);
}
.ref {
  display: flex;
  gap: 6px;
  align-items: baseline;
  font-size: 11.5px;
  color: var(--theme-muted);
  cursor: help;
}
.rn {
  color: var(--theme-accent);
  font-family: var(--font-mono);
}
.rt {
  color: var(--theme-ink-soft);
}
.rs {
  margin-left: auto;
  font-size: 10.5px;
}
.thinking {
  color: var(--theme-muted);
}
.cur {
  animation: blink 1s steps(1) infinite;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
.tok {
  margin-top: 6px;
  font-size: 10.5px;
  color: var(--theme-muted);
  font-family: var(--font-mono);
}
.ai-err {
  color: var(--theme-error);
  font-size: 12.5px;
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
  padding: 8px 10px;
  border-radius: var(--radius-sm);
}
.ai-input {
  border-top: 1px solid var(--theme-line);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ai-ta {
  resize: none;
  height: 64px;
  font-family: var(--font-sans);
  font-size: 13.5px;
  line-height: 1.6;
  padding: 8px 10px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
}
.ai-ta:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.ai-btns {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.send,
.stop {
  font-size: 13px;
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  border: 1px solid var(--theme-solid-bg);
}
.send {
  background: var(--theme-solid-bg);
  color: var(--theme-solid-fg);
}
.send:hover:not(:disabled) {
  background: var(--theme-solid-hover);
}
.send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.stop {
  background: transparent;
  color: var(--theme-error);
  border-color: var(--theme-error);
}
.stop:hover {
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
}
.ai-foot {
  font-size: 11px;
  color: var(--theme-muted);
  padding: 6px 14px;
  border-top: 1px solid var(--theme-line);
}
</style>
