/**
 * AI 写作抽屉的「现场缓存 + 历史记录」。
 *
 * - awCache：当前抽屉的操作/方向/生成结果/字数设置。抽屉是 v-if 卸载的，
 *   组件卸载即丢状态 → 把这些放在模块级 reactive 里，关抽屉、切别的功能面板
 *   都不会丢；再镜像到 localStorage，软件重启后也能恢复。
 * - awHistory：每次生成完成记录一条（操作 + 当时方向 + 生成内容 + 章节），
 *   可在抽屉里载入后再次编辑方向重新生成、或再次应用。
 */
import { reactive, ref, watch } from 'vue';

export type AwOp =
  | 'rewrite'
  | 'continue'
  | 'expand'
  | 'shrink'
  | 'create'
  | 'review'
  | 'gen_outline'
  | 'gen_from_outline';

export interface AwHistoryEntry {
  id: number;
  ts: number;
  op: AwOp;
  opLabel: string;
  /** 生成时填的方向（可能为空） */
  instruction: string;
  result: string;
  bookId: number | null;
  chapterId: number | null;
  chapterTitle: string;
}

const CACHE_KEY = 'inkrealm.aw.cache.v1';
const HIST_KEY = 'inkrealm.aw.history.v1';
const HIST_MAX = 40;

function loadJSON<T>(key: string, fallback: T): T {
  try {
    const s = localStorage.getItem(key);
    return s ? (JSON.parse(s) as T) : fallback;
  } catch {
    return fallback;
  }
}

function saveJSON(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* 存储满等异常静默，不影响使用 */
  }
}

export const awCache = reactive({
  op: 'rewrite' as AwOp,
  instruction: '',
  result: '',
  done: false,
  targetWords: 0,
  customWords: 0,
});

// 启动时从 localStorage 恢复上次现场
Object.assign(awCache, loadJSON<Partial<typeof awCache>>(CACHE_KEY, {}));

export const awHistory = ref<AwHistoryEntry[]>(loadJSON<AwHistoryEntry[]>(HIST_KEY, []));

// 防抖持久化
let cacheTimer: ReturnType<typeof setTimeout> | null = null;
watch(
  awCache,
  () => {
    if (cacheTimer) clearTimeout(cacheTimer);
    cacheTimer = setTimeout(() => saveJSON(CACHE_KEY, { ...awCache }), 250);
  },
  { deep: true }
);

let histTimer: ReturnType<typeof setTimeout> | null = null;
function persistHistory() {
  if (histTimer) clearTimeout(histTimer);
  histTimer = setTimeout(() => saveJSON(HIST_KEY, awHistory.value), 250);
}

let seq = 0;

/** 生成完成：记录一条历史（最新的在前，超出上限裁掉） */
export function pushAwHistory(e: Omit<AwHistoryEntry, 'id' | 'ts'>) {
  if (!e.result || !e.result.trim()) return;
  awHistory.value.unshift({ ...e, id: Date.now() * 1000 + (seq++ % 1000), ts: Date.now() });
  if (awHistory.value.length > HIST_MAX) awHistory.value.length = HIST_MAX;
  persistHistory();
}

export function removeAwHistory(id: number) {
  awHistory.value = awHistory.value.filter((x) => x.id !== id);
  persistHistory();
}

export function clearAwHistory() {
  awHistory.value = [];
  persistHistory();
}
