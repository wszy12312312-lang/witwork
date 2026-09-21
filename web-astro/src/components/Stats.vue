<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import {
  store,
  refreshStats,
  loadStatsHeatmap,
  setStatGoal,
  addStatPlan,
  deleteStatPlan,
  readNotification,
} from '../lib/store';
import RareCounter from './RareCounter.vue';
import RareDeleteButton from './RareDeleteButton.vue';

const emit = defineEmits<{ (e: 'close'): void }>();

type Tab = 'today' | 'heatmap' | 'goal' | 'plans';
const tab = ref<Tab>('today');

const hasBook = computed(() => !!store.currentBookId);
const today = computed(() => store.statsToday);

const goalPct = computed(() => {
  if (!today.value || !today.value.goal) return 0;
  return Math.min(100, Math.round((today.value.net / today.value.goal) * 100));
});

// 热力图
const heatWindow = ref(84); // 最近 N 天
const netTotal = computed(() => store.statsHeatmap.reduce((a, d) => a + (d.net || 0), 0));
const activeDays = computed(() => store.statsHeatmap.filter((d) => (d.net || 0) > 0).length);

function heatColor(net: number): string {
  if (net <= 0) return 'color-mix(in srgb, var(--theme-line) 60%, transparent)';
  if (net <= 300) return 'color-mix(in srgb, var(--theme-accent) 28%, transparent)';
  if (net <= 1000) return 'color-mix(in srgb, var(--theme-accent) 50%, transparent)';
  if (net <= 2500) return 'color-mix(in srgb, var(--theme-accent) 74%, transparent)';
  return 'var(--theme-accent)';
}

// 更新计划
const planTime = ref('20:00');
const planDays = ref('1,2,3,4,5,6,7');
const WEEK = ['一', '二', '三', '四', '五', '六', '日'];

function daysLabel(days: string): string {
  const set = (days || '').split(',').map((s) => s.trim()).filter(Boolean);
  if (set.length === 7) return '每天';
  return set.map((d) => WEEK[Number(d) - 1] || d).join('、');
}

async function doAddPlan() {
  await addStatPlan(planTime.value.trim() || '20:00', planDays.value.trim() || '1,2,3,4,5,6,7');
}

// 目标
const goalInput = ref(2000);
function syncGoalInput() {
  goalInput.value = store.statsGoal?.daily_words || 2000;
}
async function saveGoal() {
  const v = Math.max(100, Math.round(goalInput.value) || 2000);
  await setStatGoal(v);
}

async function reloadHeatmap() {
  await loadStatsHeatmap(heatWindow.value);
}

onMounted(async () => {
  await refreshStats();
  syncGoalInput();
});
</script>

<template>
  <section class="st">
    <header class="st-head">
      <div class="st-title">写作统计</div>
      <button class="x" @click="emit('close')" title="关闭">✕</button>
    </header>

    <nav class="tabs">
      <button class="tab" :class="{ on: tab === 'today' }" @click="tab = 'today'">今日</button>
      <button class="tab" :class="{ on: tab === 'heatmap' }" @click="tab = 'heatmap'">热力图</button>
      <button class="tab" :class="{ on: tab === 'goal' }" @click="tab = 'goal'">目标</button>
      <button class="tab" :class="{ on: tab === 'plans' }" @click="tab = 'plans'">
        计划 <span class="badge">{{ store.statsPlans.length }}</span>
      </button>
    </nav>

    <div v-if="!hasBook" class="st-err">请先打开一个作品。</div>
    <div v-else-if="store.statsError" class="st-err">⚠ {{ store.statsError }}</div>

    <div v-if="hasBook" class="st-body">
      <!-- 今日 -->
      <div v-show="tab === 'today'" class="pane">
        <div class="cards">
          <div class="card">
            <div class="cv"><RareCounter :value="today?.net ?? 0" /></div>
            <div class="cl">今日净增</div>
          </div>
          <div class="card">
            <div class="cv"><RareCounter :value="today?.streak ?? 0" /></div>
            <div class="cl">连续天数</div>
          </div>
          <div class="card">
            <div class="cv"><RareCounter :value="today?.minutes ?? 0" /></div>
            <div class="cl">写作分钟</div>
          </div>
        </div>

        <div class="goalbar" v-if="today">
          <div class="gb-h">
            <span>目标 {{ today.goal }} 字</span>
            <span>{{ today.net }} / {{ today.goal }}（{{ goalPct }}%）</span>
          </div>
          <div class="gb-track">
            <div class="gb-fill" :style="{ width: goalPct + '%' }"></div>
          </div>
        </div>

        <div class="sub">通知</div>
        <div class="rel-list">
          <div v-for="n in store.statsNotifications" :key="n.id" class="ntf" :class="{ unread: !(n.read) }">
            <div class="ntf-body">
              <div class="ntf-t">{{ n.title || '提醒' }}</div>
              <div class="ntf-c">{{ n.body }}</div>
            </div>
            <button v-if="!n.read" class="act sm" @click="readNotification(n.id)">已读</button>
          </div>
          <div v-if="!store.statsNotifications.length" class="hint">暂无通知。</div>
        </div>
      </div>

      <!-- 热力图 -->
      <div v-show="tab === 'heatmap'" class="pane">
        <div class="new">
          <label class="str">窗口</label>
          <select v-model.number="heatWindow" class="sel" @change="reloadHeatmap">
            <option :value="42">近 6 周</option>
            <option :value="84">近 12 周</option>
            <option :value="180">近半年</option>
          </select>
          <span class="hint">活跃 <RareCounter :value="activeDays" :separator="''" /> 天 · 累计 <RareCounter :value="netTotal" /> 字</span>
        </div>
        <div class="heat">
          <div
            v-for="d in store.statsHeatmap"
            :key="d.date"
            class="cell"
            :style="{ background: heatColor(d.net || 0) }"
            :title="`${d.date}：${d.net || 0} 字`"
          ></div>
          <div v-if="!store.statsHeatmap.length" class="hint">暂无数据。</div>
        </div>
        <div class="legend">
          <span class="lg">少</span>
          <span class="cell" :style="{ background: heatColor(100) }"></span>
          <span class="cell" :style="{ background: heatColor(500) }"></span>
          <span class="cell" :style="{ background: heatColor(1500) }"></span>
          <span class="cell" :style="{ background: heatColor(3000) }"></span>
          <span class="lg">多</span>
        </div>
      </div>

      <!-- 目标 -->
      <div v-show="tab === 'goal'" class="pane">
        <div class="hint">设置每日字数目标，今日进度会据此计算完成度。</div>
        <label class="lbl">每日目标（字）</label>
        <input v-model.number="goalInput" class="inp" type="number" min="100" step="100" />
        <div class="acts">
          <button class="save" @click="saveGoal">保存目标</button>
        </div>
        <div class="hint" v-if="store.statsGoal">当前目标：{{ store.statsGoal.daily_words }} 字/天</div>
      </div>

      <!-- 计划 -->
      <div v-show="tab === 'plans'" class="pane">
        <div class="hint">更新提醒计划：到点或断更时提醒你回来写。</div>
        <div class="new">
          <input v-model="planTime" class="inp w90" type="time" />
          <input v-model="planDays" class="inp w160" placeholder="1,2,3,4,5,6,7" />
          <button class="save" @click="doAddPlan">＋ 添加</button>
        </div>
        <div class="hint">星期：1=一 2=二 3=三 4=四 5=五 6=六 7=日（逗号分隔）</div>
        <div class="rel-list">
          <div v-for="p in store.statsPlans" :key="p.id" class="plan-row">
            <span class="pt">{{ p.time_of_day }}</span>
            <span class="pd">{{ daysLabel(p.days) }}</span>
            <span class="pen" :class="{ off: !p.enabled }">{{ p.enabled ? '启用' : '停用' }}</span>
            <RareDeleteButton @confirm="deleteStatPlan(p.id)" />
          </div>
          <div v-if="!store.statsPlans.length" class="hint">还没有计划。</div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.st {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.st-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--theme-line);
}
.st-title {
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
.badge {
  font-family: var(--font-mono);
  font-size: 10px;
  background: var(--theme-field);
  border: 1px solid var(--theme-line);
  border-radius: 8px;
  padding: 0 5px;
  margin-left: 2px;
}
.st-err {
  color: var(--theme-error);
  font-size: 12px;
  background: color-mix(in srgb, var(--theme-error) 12%, transparent);
  padding: 6px 10px;
  margin: 8px 14px 0;
  border-radius: var(--radius-sm);
}
.st-body {
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
.cards {
  display: flex;
  gap: 8px;
}
.card {
  flex: 1;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 10px;
  background: var(--theme-field);
  text-align: center;
}
.cv {
  font-size: 20px;
  font-weight: 700;
  color: var(--theme-accent);
  font-family: var(--font-mono);
}
.cl {
  font-size: 11px;
  color: var(--theme-muted);
  margin-top: 2px;
}
.goalbar {
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 10px;
  background: var(--theme-field);
}
.gb-h {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--theme-ink-soft);
  margin-bottom: 6px;
}
.gb-track {
  height: 8px;
  border-radius: 4px;
  background: var(--theme-line);
  overflow: hidden;
}
.gb-fill {
  height: 100%;
  background: var(--theme-accent);
  border-radius: 4px;
  transition: width 0.3s var(--motion);
}
.sub {
  font-size: 12px;
  color: var(--theme-muted);
  margin-top: 2px;
}
.rel-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ntf {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  background: var(--theme-field);
}
.ntf.unread {
  border-color: color-mix(in srgb, var(--theme-accent) 50%, var(--theme-line));
}
.ntf-body {
  flex: 1;
  min-width: 0;
}
.ntf-t {
  font-size: 13px;
  color: var(--theme-ink);
}
.ntf-c {
  font-size: 12px;
  color: var(--theme-ink-soft);
}
.act {
  background: transparent;
  border: 1px solid var(--theme-line);
  color: var(--theme-ink-soft);
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.act:hover {
  border-color: var(--theme-accent);
  color: var(--theme-accent-hover);
}
.act.sm {
  font-size: 12px;
  padding: 3px 10px;
}
.new {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.sel {
  font-size: 13px;
  padding: 6px 8px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
}
.str {
  font-size: 11.5px;
  color: var(--theme-muted);
}
.inp {
  font-size: 13px;
  padding: 6px 9px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  background: var(--theme-field);
  color: var(--theme-ink);
}
.inp.w90 {
  width: 110px;
}
.inp.w160 {
  width: 170px;
}
.inp:focus,
.sel:focus {
  outline: none;
  border-color: var(--theme-accent);
}
.heat {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
}
.cell {
  width: 13px;
  height: 13px;
  border-radius: 3px;
  border: 1px solid color-mix(in srgb, var(--theme-line) 70%, transparent);
}
.legend {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--theme-muted);
}
.lg {
  color: var(--theme-muted);
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
.save:hover {
  background: var(--theme-solid-hover);
}
.lbl {
  font-size: 11.5px;
  color: var(--theme-muted);
}
.plan-row {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--theme-line);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  background: var(--theme-field);
  font-size: 13px;
  color: var(--theme-ink-soft);
}
.pt {
  font-family: var(--font-mono);
  color: var(--theme-ink);
}
.pd {
  flex: 1;
}
.pen {
  font-size: 11px;
  color: var(--theme-success);
}
.pen.off {
  color: var(--theme-muted);
}
.del {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: 1px solid var(--theme-error);
  color: var(--theme-error);
  cursor: pointer;
}
.hint {
  font-size: 12px;
  color: var(--theme-muted);
}
</style>
