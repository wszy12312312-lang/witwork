// 万维文 WitWork 后端 API 客户端。相对路径 /api 在开发与生产（FastAPI 托管）下一致。
export interface Book {
  id: number;
  title: string | null;
  status: string;
  author?: string | null;
  summary?: string | null;
  deleted_at?: string | null;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface Volume {
  id: number;
  book_id: number;
  title: string;
  sort_order: number;
  [key: string]: unknown;
}

export interface Chapter {
  id: number;
  book_id: number;
  volume_id: number | null;
  title: string;
  content: string;
  words: number;
  sort_order: number;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface BookDetail extends Book {
  volumes: Volume[];
  chapters: Chapter[];
}

/** 回收站里的一条卷（带所属作品名与「随之隐藏的章节数」） */
export interface TrashedVolume extends Volume {
  book_title?: string | null;
  chapters?: number;
  deleted_at?: string | null;
}

/** 回收站里的一条章节（带作品名/卷名） */
export interface TrashedChapter {
  id: number;
  book_id: number;
  volume_id: number | null;
  title: string;
  words: number;
  deleted_at?: string | null;
  book_title?: string | null;
  volume_title?: string | null;
}

/** GET /api/books/trash：统一回收站视图 */
export interface TrashAll {
  books: Book[];
  volumes: TrashedVolume[];
  chapters: TrashedChapter[];
}

/** SMTC 里的一个播放会话 */
export interface NowPlayingSession {
  appId: string;
  title: string;
  artist: string;
  album: string;
  status: string; // Playing | Paused | Stopped | ...
  playing: boolean;
  position: number;
  duration: number;
}

/** GET /api/song/now */
export interface NowPlaying {
  ok: boolean;
  error?: string;
  current?: NowPlayingSession | null;
  sessions?: NowPlayingSession[];
  count?: number;
  cover_version?: number; // 封面变化计数，用于前端 bust 图片缓存
}

export type SongAction = 'play' | 'pause' | 'toggle' | 'next' | 'prev';
export interface SongVolume {
  available: boolean;
  level: number; // 0-100
  muted: boolean;
  error?: string;
  installing?: boolean; // pycaw 缺失、后台自动安装中
  need_pycaw?: boolean; // 真正缺 pycaw（与「有 pycaw 但无播放会话」区分）
}

export interface HistoryStatus {
  can_undo: boolean;
  can_redo: boolean;
  undo_left: number;
  redo_left: number;
  depth: number;
}

export interface PreviewResult {
  html: string;
  paragraphs?: number;
  pages?: number;
  words?: number;
  [key: string]: unknown;
}

export interface TypesetChange {
  type: string;
  before: string;
  after: string;
}

export interface TypesetResult {
  changes: TypesetChange[];
  content?: string;
  [key: string]: unknown;
}

export interface Snapshot {
  id: number;
  chapter_id: number;
  kind: string;
  title: string;
  content: string;
  trigger?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

export interface SearchHit {
  chapter_id: number;
  chapter_title: string;
  line: number;
  col: number;
  snippet: string;
}

export interface SearchResult {
  hits: SearchHit[];
  total: number;
  truncated?: boolean;
}

export interface ReplacePreviewRow {
  chapter_id: number;
  chapter_title: string;
  count: number;
  before: string;
  after: string;
}

export interface ReplacePreview {
  total: number;
  results: ReplacePreviewRow[];
}

export interface ReplaceLog {
  id: number;
  undone: boolean;
  [key: string]: unknown;
}

// ---- Provider / 会话（AI 协作） ----
export interface Provider {
  id: string;
  kind: string;
  name?: string;
  model?: string | null;
  base_url?: string | null;
  api_key_ref?: string | null;
  context_window?: number;
  enabled: number; // 0 / 1
  is_local?: number;
  is_default?: boolean;
  [key: string]: unknown;
}

export interface Citation {
  n: number;
  section: string;
  section_title: string;
  title: string;
  snippet: string;
  [key: string]: unknown;
}

export interface SessionMessage {
  id: number;
  role: string; // 'user' | 'assistant'
  content: string;
  refs?: Citation[] | null;
  provider_snapshot?: { kind?: string; model?: string } | null;
  token_count?: number;
  created_at?: string;
  // 本地流式占位标记：助手消息生成中为真，done/error 后清除
  _live?: boolean;
  [key: string]: unknown;
}

export interface Session {
  id: number;
  book_id?: number | null;
  title: string;
  active_provider_id?: string | null;
  created_at?: string;
  messages?: SessionMessage[];
  [key: string]: unknown;
}

// SSE 事件：refs(一次) / delta(多次) / done / error
export interface StreamEvent {
  type: 'refs' | 'delta' | 'done' | 'error';
  data: unknown;
}

// ---- 知识库 ----
export interface KbSection {
  id: number;
  key: string;
  title: string;
  description?: string | null;
  built_in?: number;
  [key: string]: unknown;
}

export interface KbVersion {
  id: number;
  item_id: number;
  content: string;
  reason?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

export interface KbItem {
  id: number;
  section: string;
  title: string;
  content?: string;
  source_type?: string;
  source_ref?: string | null;
  current_version_id?: number | null;
  created_at?: string;
  updated_at?: string;
  versions?: KbVersion[];
  [key: string]: unknown;
}

export interface KbHit {
  n: number;
  item_id: number;
  section: string;
  section_title: string;
  title: string;
  snippet: string;
  score: number;
  [key: string]: unknown;
}

export interface KbRetrieveResult {
  hits: KbHit[];
}

export interface KbReindexResult {
  reindexed: number;
  skipped: number;
  mode: string;
  dim: number;
}

// ---- 人格 ----
export interface Persona {
  id: number;
  name: string;
  system_prompt?: string;
  tone?: string | null;
  focus?: string | null;
  temperature?: number;
  is_default?: number;
  active?: number;
  built_in?: number;
  // 后端以 *_json 列返回原始字符串；前端解析后填到下列数组便于编辑
  style_tags?: string[];
  methods?: string[];
  forbidden?: string[];
  style_tags_json?: string;
  methods_json?: string;
  forbidden_json?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface PersonaVersion {
  id: number;
  persona_id: number;
  snapshot_json?: string;
  note?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

// ---- 人物卡 ----
export interface Character {
  id: number;
  book_id: number | null;
  name: string;
  aliases_json?: string;
  aliases?: string[];
  appearance?: string | null;
  personality?: string | null;
  catchphrase?: string | null;
  status_current?: string | null;
  taboo?: string | null;
  kb_item_id?: number | null;
  template_id?: number | null;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface CharacterRelation {
  id: number;
  book_id: number | null;
  from_id: number;
  to_id: number;
  relation?: string;
  note?: string | null;
  [key: string]: unknown;
}

export interface CharacterAppearance {
  id: number;
  character_id: number;
  chapter_id: number | null;
  summary?: string | null;
  excerpt?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

// 结构化写回提议（抽取候选人物时返回）
export interface Patch {
  id: number;
  session_id?: number | null;
  target_type?: string;
  section?: string;
  title?: string;
  op?: string;
  fields_json?: string;
  reason?: string | null;
  status?: string;
  applied_at?: string | null;
  [key: string]: unknown;
}

// ---- 伏笔 ----
export type ForeshadowStatus = 'planned' | 'planted' | 'called' | 'resolved' | 'abandoned';
export type ForeshadowAction = 'create' | 'plant' | 'call' | 'resolve' | 'abandon' | 'reopen';

export interface Foreshadow {
  id: number;
  book_id: number | null;
  title: string;
  content?: string | null;
  importance?: number;
  keywords?: string | null;
  status?: ForeshadowStatus;
  planted_chapter_id?: number | null;
  resolved_chapter_id?: number | null;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface ForeshadowEvent {
  id: number;
  foreshadowing_id: number;
  action: string;
  chapter_id?: number | null;
  note?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

export interface ForeshadowScanMatch {
  id: number;
  title: string;
  status: string;
  matched: string[];
}

export interface ForeshadowInjection {
  text: string;
}

// ---- 词条 ----
export interface Entry {
  id: number;
  book_id: number | null;
  name: string;
  category?: string | null;
  aliases_json?: string;
  aliases?: string[];
  description?: string | null;
  first_chapter_id?: number | null;
  kb_item_id?: number | null;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface EntryCandidate {
  word: string;
  count: number;
}

export interface EntryNormalizeResult {
  [chapterId: string]: number;
}

// ---- 爽点节奏 ----
export type BeatKind = 'payoff' | 'reversal' | 'hook' | 'pressure' | 'warmth' | 'climax' | 'info';
export const BEAT_KIND_LABEL: Record<BeatKind, string> = {
  payoff: '回报',
  reversal: '反转',
  hook: '钩子',
  pressure: '压力',
  warmth: '温情',
  climax: '高潮',
  info: '信息',
};
export const BEAT_KINDS: BeatKind[] = ['payoff', 'reversal', 'hook', 'pressure', 'warmth', 'climax', 'info'];

export interface BeatMark {
  id: number;
  book_id: number | null;
  chapter_id: number;
  kind: BeatKind;
  strength: number; // 1-5
  offset?: number; // 正文字符位置
  text?: string | null;
  source?: string; // manual | ai
  created_at?: string;
  [key: string]: unknown;
}

export interface BeatTemplate {
  id: number;
  name: string;
  rule_json?: string;
  built_in?: number;
  created_at?: string;
  [key: string]: unknown;
}

export interface BeatPerChapter {
  chapter_id: number;
  title?: string | null;
  words?: number;
  count: number;
  avg_strength: number;
  kinds: string[];
}

export interface BeatMetrics {
  per_chapter: BeatPerChapter[];
  intervals: Record<string, number[]>;
  flat_runs: Array<{ end_chapter?: string; length: number }>;
  deviation: { template: string; misses: number } | null;
  total_marks: number;
}

export interface BeatSuggestion {
  chapter?: string;
  position_words: number;
  kind: BeatKind;
  reason: string;
}

// ---- 写作统计 ----
export interface DailyStat {
  date: string;
  book_id: number | null;
  words_added: number;
  words_deleted: number;
  net: number;
  minutes: number;
  [key: string]: unknown;
}

export interface TodayStat {
  date: string;
  net: number;
  added: number;
  deleted: number;
  minutes: number;
  goal: number;
  streak: number;
}

export interface WritingGoal {
  id?: number;
  book_id: number | null;
  daily_words: number;
  [key: string]: unknown;
}

export interface UpdatePlan {
  id: number;
  book_id: number | null;
  time_of_day: string; // "HH:MM"
  days: string; // "1,2,3,4,5,6,7"
  enabled: number; // 0/1
  [key: string]: unknown;
}

export interface Notification {
  id: number;
  book_id: number | null;
  kind?: string;
  title?: string;
  body?: string;
  read?: number;
  created_at?: string;
  [key: string]: unknown;
}

// ---- 兼容工具 ----
export interface WordFreqItem {
  word: string;
  count: number;
}
export interface AiTastePara {
  index: number;
  score: number;
  chars: number;
  sent_cv: number;
  bigram_repeat: number;
  transitions: number;
  entropy: number;
  text: string;
}
export interface AiTasteResult {
  score: number;
  paragraphs: AiTastePara[];
  signals: string[];
}
export interface ComplianceHit {
  word: string;
  count: number;
  pos: number;
  context: string;
}
export interface ComplianceResult {
  hits: ComplianceHit[];
  total: number;
  word_count: number;
}
export interface ServiceProbe {
  url: string;
  available: boolean;
  hint: string;
}
export interface ServicesResult {
  sd_webui: ServiceProbe;
  comfyui: ServiceProbe;
  tts: ServiceProbe;
}

// ---- 备份 ----
export interface BackupItem {
  name: string;
  size: number;
  created_at: string;
  tag?: string | null;
  [key: string]: unknown;
}

// ---- 导出 ----
export interface ExportResult {
  name: string;
  download_url: string;
  mime: string;
  [key: string]: unknown;
}

// ---- 角色模板库 ----
export interface RoleTemplate {
  id: number;
  name: string;
  category: string;
  fields_json: string;
  is_global: number;
  built_in: number;
  [key: string]: unknown;
}

// ---- 框架共创 ----
export type FrameworkPhase =
  | 'brief'
  | 'worldview'
  | 'faction'
  | 'plotline'
  | 'character'
  | 'outline'
  | 'confirmed';

export interface FrameworkState {
  phase: FrameworkPhase;
  phase_label: string;
  required: string[];
  data: Record<string, string>;
  needs_review: FrameworkPhase[];
  history: { phase: FrameworkPhase; conclusion: string; note?: string | null }[];
  confirmed: boolean;
}

export interface OutlineResult {
  chapters: { id: number; title: string }[];
  planned_foreshadows: string[];
  count: number;
}

const BASE = '/api';

async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { headers: { Accept: 'application/json' } });
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return (await r.json()) as T;
}

async function send<T>(path: string, method: string, body?: unknown, isJson = true): Promise<T> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(body);
  }
  const r = await fetch(`${BASE}${path}`, init);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  if (!isJson) return undefined as unknown as T;
  const text = await r.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  health: () => getJSON<{ status?: string }>('/health'),

  // 作品列表。includeTrashed=true 时后端返回含已删除项。
  books: (includeTrashed = false) =>
    getJSON<Book[]>(`/books?include_trashed=${includeTrashed ? 'true' : 'false'}`),
  // 作品详情（含 volumes / chapters）
  book: (id: number) => getJSON<BookDetail>(`/books/${id}`),
  createBook: (payload: Partial<Book>) => send<Book>('/books', 'POST', payload),
  updateBook: (id: number, payload: Record<string, unknown>) => send<Book>(`/books/${id}`, 'PUT', payload),
  // 软删除（移入回收站）
  trash: (id: number) => send<{ ok: boolean }>(`/books/${id}`, 'DELETE'),
  // 从回收站恢复
  restore: (id: number) => send<{ ok: boolean }>(`/books/${id}/restore`, 'POST'),
  createVolume: (bookId: number, payload: { title?: string; sort_order?: number }) =>
    send<Volume>(`/books/${bookId}/volumes`, 'POST', payload),
  // 注意路径是 /books/volumes/{id}（后端路由如此），早先写成 /volumes/{id} 会 404
  updateVolume: (volumeId: number, payload: Record<string, unknown>) =>
    send<Volume>(`/books/volumes/${volumeId}`, 'PUT', payload),
  // 删除单卷（软删进回收站；卷下章节随之隐藏，可整体恢复）
  deleteVolume: (volumeId: number) =>
    send<{ ok: boolean; volume_id: number; chapters: number }>(`/books/volumes/${volumeId}`, 'DELETE'),
  restoreVolume: (volumeId: number) =>
    send<{ ok: boolean; volume_id: number; chapters: number }>(`/books/volumes/${volumeId}/restore`, 'POST'),
  // 回收站统一视图（作品 / 卷 / 章节）
  trashAll: () => getJSON<TrashAll>('/books/trash'),

  // 章节
  createChapter: (payload: { book_id: number; volume_id?: number | null; title?: string; content?: string; sort_order?: number }) =>
    send<Chapter>('/chapters', 'POST', payload),
  chapter: (id: number) => getJSON<Chapter>(`/chapters/${id}`),
  updateChapter: (id: number, payload: Record<string, unknown>) => send<Chapter>(`/chapters/${id}`, 'PUT', payload),
  deleteChapter: (id: number) => send<{ ok: boolean }>(`/chapters/${id}`, 'DELETE'),
  restoreChapter: (id: number) => send<Chapter>(`/chapters/${id}/restore`, 'POST'),

  // 当前播放歌曲（Windows SMTC；不支持时返回 ok:false）
  songNow: (force = false) => getJSON<NowPlaying>(`/song/now?force=${force ? 'true' : 'false'}`),
  songStatus: () => getJSON<{ available: boolean; count: number; error: string }>('/song/status'),
  songRefresh: () => send<NowPlaying>('/song/refresh', 'POST'),
  // 传输控制（play/pause/toggle/next/prev）+ 封面 + 音量
  songControl: (action: SongAction) => send<{ ok: boolean; error?: string }>('/song/control', 'POST', { action }),
  // 封面走 /api 前缀（此前漏掉 /api 导致 img 404，部件永远显示音符占位）
  songCoverUrl: (version: number) => `/api/song/cover?v=${version}`,
  // 音量读取必须带上当前播放 App 的 appId（此前漏传导致永远「未找到音频会话」）
  songVolume: (appId = '') => getJSON<SongVolume>(`/song/volume?app_id=${encodeURIComponent(appId)}`),
  songVolumeSet: (appId: string, level: number) => send<SongVolume>('/song/volume', 'POST', { app_id: appId, level }),

  // 快照
  listSnapshots: (chapterId: number) => getJSON<Snapshot[]>(`/chapters/${chapterId}/snapshots`),
  createSnapshot: (chapterId: number, payload: { title?: string; kind?: string }) =>
    send<Snapshot>(`/chapters/${chapterId}/snapshots`, 'POST', payload),
  restoreSnapshot: (snapshotId: number) => send<Chapter>(`/snapshots/${snapshotId}/restore`, 'POST'),
  diffSnapshot: (chapterId: number, snapshotId: number) =>
    getJSON<{ diff: unknown }>(`/chapters/${chapterId}/diff?snapshot_id=${snapshotId}`),

  // 编辑历史 / 撤销栈
  historyPush: (cid: number, content: string, label: string) =>
    send<HistoryStatus>(`/chapters/${cid}/history/push`, 'POST', { content, label }),
  historyUndo: (cid: number) => send<{ content: string; status: HistoryStatus }>(`/chapters/${cid}/history/undo`, 'POST'),
  historyRedo: (cid: number) => send<{ content: string; status: HistoryStatus }>(`/chapters/${cid}/history/redo`, 'POST'),
  historyStatus: (cid: number) => getJSON<HistoryStatus>(`/chapters/${cid}/history/status`),

  // 手机预览与排版
  typesetPreview: (cid: number, content: string, options: Record<string, unknown> = {}) =>
    send<PreviewResult>(`/typeset/chapters/${cid}/preview`, 'POST', { content, options }),
  typesetNormalize: (cid: number, content: string, options: Record<string, unknown> = {}, dryRun = true) =>
    send<TypesetResult>(`/typeset/chapters/${cid}/normalize`, 'POST', { content, options, dry_run: dryRun }),

  // 全文搜索与替换
  searchBook: (bookId: number, query: string, opts: Record<string, unknown> = {}) =>
    send<SearchResult>(`/books/${bookId}/search`, 'POST', { query, ...opts }),
  replaceBook: (bookId: number, query: string, replacement: string, opts: Record<string, unknown> = {}) =>
    send<ReplacePreview>(`/books/${bookId}/replace`, 'POST', { query, replacement, ...opts }),
  listReplaceLogs: (bookId: number) => getJSON<ReplaceLog[]>(`/books/${bookId}/replace-logs`),
  undoReplace: (rid: number) => send<unknown>(`/replace-logs/${rid}/undo`, 'POST'),

  // ---- Provider / 模型管理 ----
  providers: () => getJSON<Provider[]>('/providers'),
  createProvider: (fields: Record<string, unknown>) => send<Provider>('/providers', 'POST', fields),
  updateProvider: (pid: string, fields: Record<string, unknown>) => send<Provider>(`/providers/${pid}`, 'PUT', fields),
  deleteProvider: (pid: string) => send<{ ok: boolean }>(`/providers/${pid}`, 'DELETE'),
  setDefaultProvider: (pid: string) => send<{ ok: boolean; default_provider_id: string }>('/providers/default', 'POST', { id: pid }),
  testProvider: (pid: string) => getJSON<{ ok: boolean; error: string; models: string[]; capabilities: Record<string, unknown> }>(`/providers/test/${pid}`),
  discoverModels: (baseUrl?: string) => getJSON<{ ok: boolean; error: string; models: string[]; base_url: string }>(`/providers/discover${baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : ''}`),

  // ---- 会话（AI 协作） ----
  listSessions: (bookId: number) => getJSON<Session[]>(`/sessions?book_id=${bookId}`),
  createSession: (bookId: number, title: string, providerId?: string | null) =>
    send<Session>('/sessions', 'POST', { book_id: bookId, title, provider_id: providerId ?? null }),
  getSession: (sid: number) => getJSON<Session>(`/sessions/${sid}`),
  deleteSession: (sid: number) => send<{ ok: boolean }>(`/sessions/${sid}`, 'DELETE'),
  setSessionProvider: (sid: number, providerId: string | null) =>
    send<Session>(`/sessions/${sid}/provider`, 'PATCH', { provider_id: providerId }),

  // SSE 流式：读取 text/event-stream，逐事件回调。可被 signal 中止（停止生成）。
  sendMessageStream: (
    sid: number,
    content: string,
    providerId: string | null | undefined,
    onEvent: (ev: StreamEvent) => void,
    signal?: AbortSignal
  ): Promise<void> =>
    new Promise<void>((resolve, reject) => {
      const body = JSON.stringify({ content, provider_id: providerId ?? null, params: {} });
      fetch(`${BASE}/sessions/${sid}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal,
      })
        .then((r) => {
          if (!r.ok || !r.body) {
            reject(new Error(`/sessions/${sid}/messages → ${r.status}`));
            return;
          }
          const reader = r.body.getReader();
          const decoder = new TextDecoder();
          let buf = '';
          const pump = (): Promise<void> =>
            reader.read().then(({ done, value }) => {
              if (done) {
                // 处理末尾可能残留的缓冲
                flushBuffer();
                resolve();
                return;
              }
              buf += decoder.decode(value, { stream: true });
              flushBuffer();
              return pump();
            });
          const flushBuffer = () => {
            const parts = buf.split('\n\n');
            buf = parts.pop() ?? '';
            for (const p of parts) {
              const line = p.trim();
              if (!line.startsWith('data:')) continue;
              const json = line.slice(5).trim();
              if (!json) continue;
              try {
                onEvent(JSON.parse(json) as StreamEvent);
              } catch {
                /* 忽略坏帧 */
              }
            }
          };
          pump().catch((e) => reject(e));
        })
        .catch((e) => reject(e));
    }),

  // SSE 流式：AI 正文操作（改写/续写/扩写/缩写/创作/通读全书）。可被 signal 中止。
  aiOpsStream: (
    payload: {
      operation: string;
      book_id: number | null;
      chapter_id: number | null;
      text: string;
      instruction?: string;
      scope?: string;
      provider_id?: string | null;
    },
    onEvent: (ev: StreamEvent) => void,
    signal?: AbortSignal
  ): Promise<void> =>
    new Promise<void>((resolve, reject) => {
      const body = JSON.stringify({
        operation: payload.operation,
        book_id: payload.book_id,
        chapter_id: payload.chapter_id,
        text: payload.text,
        instruction: payload.instruction ?? '',
        scope: payload.scope ?? 'chapter',
        provider_id: payload.provider_id ?? null,
        params: {},
      });
      fetch(`${BASE}/ai/ops/operate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal,
      })
        .then((r) => {
          if (!r.ok || !r.body) {
            reject(new Error(`/ai/ops/operate → ${r.status}`));
            return;
          }
          const reader = r.body.getReader();
          const decoder = new TextDecoder();
          let buf = '';
          const pump = (): Promise<void> =>
            reader.read().then(({ done, value }) => {
              if (done) {
                flushBuffer();
                resolve();
                return;
              }
              buf += decoder.decode(value, { stream: true });
              flushBuffer();
              return pump();
            });
          const flushBuffer = () => {
            const parts = buf.split('\n\n');
            buf = parts.pop() ?? '';
            for (const p of parts) {
              const line = p.trim();
              if (!line.startsWith('data:')) continue;
              const json = line.slice(5).trim();
              if (!json) continue;
              try {
                onEvent(JSON.parse(json) as StreamEvent);
              } catch {
                /* 忽略坏帧 */
              }
            }
          };
          pump().catch((e) => reject(e));
        })
        .catch((e) => reject(e));
    }),

  // ---- 知识库 ----
  kbSections: () => getJSON<KbSection[]>('/kb/sections'),
  createKbSection: (key: string, title: string, description?: string) =>
    send<KbSection>('/kb/sections', 'POST', { key, title, description }),
  kbItems: (section?: string) =>
    getJSON<KbItem[]>(`/kb/items${section ? `?section=${encodeURIComponent(section)}` : ''}`),
  createKbItem: (section: string, title: string, content: string) =>
    send<KbItem>('/kb/items', 'POST', { section, title, content }),
  kbItem: (id: number) => getJSON<KbItem>(`/kb/items/${id}`),
  saveKbItem: (id: number, payload: { title?: string; content?: string; reason?: string }) =>
    send<KbItem>(`/kb/items/${id}`, 'PUT', payload),
  deleteKbItem: (id: number) => send<{ ok: boolean }>(`/kb/items/${id}`, 'DELETE'),
  rollbackKbItem: (id: number, versionId: number) =>
    send<KbItem>(`/kb/items/${id}/rollback`, 'POST', { version_id: versionId }),
  kbRetrieve: (query: string, sections?: string[], topK?: number) =>
    send<KbRetrieveResult>('/kb/retrieve', 'POST', { query, sections, top_k: topK }),
  kbReindex: (section?: string) => send<KbReindexResult>('/kb/reindex', 'POST', section ? { section } : {}),

  // ---- 人格 ----
  personas: () => getJSON<Persona[]>('/personas'),
  createPersona: (p: Partial<Persona>) => send<Persona>('/personas', 'POST', p),
  persona: (id: number) => getJSON<Persona>(`/personas/${id}`),
  savePersona: (id: number, p: Partial<Persona>) => send<Persona>(`/personas/${id}`, 'PUT', p),
  deletePersona: (id: number) => send<{ ok: boolean }>(`/personas/${id}`, 'DELETE'),
  activatePersona: (id: number) => send<Persona>(`/personas/${id}/activate`, 'POST'),
  personaVersions: (id: number) => getJSON<PersonaVersion[]>(`/personas/${id}/versions`),
  adjustPersona: (sessionId: number, statement: string) =>
    send<unknown>('/personas/adjust', 'POST', { session_id: sessionId, statement }),

  // ---- 框架共创（挂在 /sessions 前缀） ----
  frameworkState: (sid: number) => getJSON<FrameworkState>(`/sessions/${sid}/framework`),
  advanceFramework: (sid: number, conclusion: string, note?: string | null) =>
    send<FrameworkState>(`/sessions/${sid}/framework/advance`, 'POST', { conclusion, note: note ?? null }),
  retreatFramework: (sid: number) => send<FrameworkState>(`/sessions/${sid}/framework/retreat`, 'POST'),
  generateOutline: (sid: number, bookId: number) =>
    send<OutlineResult>(`/sessions/${sid}/framework/outline`, 'POST', { book_id: bookId }),

  // ---- 人物卡 ----
  characters: (bookId?: number) =>
    getJSON<Character[]>(`/characters${bookId ? `?book_id=${bookId}` : ''}`),
  createCharacter: (bookId: number | null, name: string, fields?: Record<string, unknown>) =>
    send<Character>('/characters', 'POST', { book_id: bookId, name, fields: fields || {} }),
  character: (id: number) => getJSON<Character>(`/characters/${id}`),
  saveCharacter: (id: number, payload: Record<string, unknown>) => send<Character>(`/characters/${id}`, 'PUT', payload),
  deleteCharacter: (id: number) => send<{ ok: boolean }>(`/characters/${id}`, 'DELETE'),
  characterRelations: (bookId?: number) =>
    getJSON<CharacterRelation[]>(`/characters/relations${bookId ? `?book_id=${bookId}` : ''}`),
  addRelation: (bookId: number | null, fromId: number, toId: number, relation: string, note?: string | null) =>
    send<CharacterRelation>('/characters/relations', 'POST', {
      book_id: bookId,
      from_id: fromId,
      to_id: toId,
      relation,
      note: note ?? null,
    }),
  deleteRelation: (rid: number) => send<{ ok: boolean }>(`/characters/relations/${rid}`, 'DELETE'),
  extractCandidates: (bookId: number | null, text: string, sessionId?: number | null) =>
    send<{ patches: Patch[] }>('/characters/extract', 'POST', {
      book_id: bookId,
      text,
      session_id: sessionId ?? null,
    }),
  scanAppearances: (bookId: number | null, chapterId: number | null, text: string) =>
    send<{ records: CharacterAppearance[] }>('/characters/scan-appearances', 'POST', {
      book_id: bookId,
      chapter_id: chapterId,
      text,
    }),
  characterAppearances: (cid: number) => getJSON<CharacterAppearance[]>(`/characters/${cid}/appearances`),

  // ---- 结构化写回提议 ----
  applyPatch: (pid: number) => send<unknown>(`/patches/${pid}/apply`, 'POST'),
  rejectPatch: (pid: number) => send<unknown>(`/patches/${pid}/reject`, 'POST'),

  // ---- 伏笔 ----
  foreshadows: (bookId?: number, status?: string) => {
    const q: string[] = [];
    if (bookId != null) q.push(`book_id=${bookId}`);
    if (status) q.push(`status=${status}`);
    return getJSON<Foreshadow[]>(`/foreshadow${q.length ? `?${q.join('&')}` : ''}`);
  },
  createForeshadow: (bookId: number | null, title: string, content?: string | null, importance?: number, keywords?: string | null) =>
    send<Foreshadow>('/foreshadow', 'POST', {
      book_id: bookId,
      title,
      content: content ?? null,
      importance: importance ?? 3,
      keywords: keywords ?? null,
    }),
  foreshadow: (id: number) => getJSON<Foreshadow>(`/foreshadow/${id}`),
  saveForeshadow: (id: number, payload: Record<string, unknown>) => send<Foreshadow>(`/foreshadow/${id}`, 'PUT', payload),
  deleteForeshadow: (id: number) => send<{ ok: boolean }>(`/foreshadow/${id}`, 'DELETE'),
  foreshadowAction: (id: number, action: ForeshadowAction, chapterId?: number | null, note?: string | null) =>
    send<Foreshadow>(`/foreshadow/${id}/action`, 'POST', { action, chapter_id: chapterId ?? null, note: note ?? null }),
  foreshadowEvents: (id: number) => getJSON<ForeshadowEvent[]>(`/foreshadow/${id}/events`),
  foreshadowInjection: (bookId?: number) =>
    getJSON<ForeshadowInjection>(`/foreshadow/injection${bookId != null ? `?book_id=${bookId}` : ''}`),
  scanForeshadow: (bookId: number | null, text: string) =>
    send<{ matches: ForeshadowScanMatch[] }>('/foreshadow/scan', 'POST', { book_id: bookId, text }),
  unresolvedForeshadow: (bookId?: number, minImportance = 4) =>
    getJSON<Foreshadow[]>(`/foreshadow/unresolved${bookId != null ? `?book_id=${bookId}&min_importance=${minImportance}` : `?min_importance=${minImportance}`}`),

  // ---- 词条 ----
  entries: (bookId?: number, category?: string) => {
    const q: string[] = [];
    if (bookId != null) q.push(`book_id=${bookId}`);
    if (category) q.push(`category=${encodeURIComponent(category)}`);
    return getJSON<Entry[]>(`/entries${q.length ? `?${q.join('&')}` : ''}`);
  },
  createEntry: (bookId: number | null, name: string, category?: string | null, aliases?: string[], description?: string | null, firstChapterId?: number | null) =>
    send<Entry>('/entries', 'POST', {
      book_id: bookId,
      name,
      category: category ?? null,
      aliases: aliases ?? [],
      description: description ?? null,
      first_chapter_id: firstChapterId ?? null,
    }),
  entry: (id: number) => getJSON<Entry>(`/entries/${id}`),
  saveEntry: (id: number, payload: Record<string, unknown>) => send<Entry>(`/entries/${id}`, 'PUT', payload),
  deleteEntry: (id: number) => send<{ ok: boolean }>(`/entries/${id}`, 'DELETE'),
  extractEntries: (bookId: number | null, texts?: string[], chapterIds?: number[], topN = 30, minCount = 2) =>
    send<{ candidates: EntryCandidate[] }>('/entries/extract', 'POST', {
      book_id: bookId,
      texts: texts ?? null,
      chapter_ids: chapterIds ?? null,
      top_n: topN,
      min_count: minCount,
    }),
  normalizeEntries: (bookId: number | null, chapterIds?: number[]) =>
    send<{ replaced: EntryNormalizeResult }>('/entries/normalize', 'POST', { book_id: bookId, chapter_ids: chapterIds ?? null }),

  // ---- 爽点节奏 ----
  beats: (bookId?: number, chapterId?: number) => {
    const q: string[] = [];
    if (bookId != null) q.push(`book_id=${bookId}`);
    if (chapterId != null) q.push(`chapter_id=${chapterId}`);
    return getJSON<BeatMark[]>(`/beats${q.length ? `?${q.join('&')}` : ''}`);
  },
  addBeat: (payload: { book_id: number | null; chapter_id: number; kind: BeatKind; strength?: number; offset?: number; text?: string | null; source?: string }) =>
    send<BeatMark>('/beats', 'POST', payload),
  deleteBeat: (id: number) => send<{ ok: boolean }>(`/beats/${id}`, 'DELETE'),
  beatTemplates: () => getJSON<BeatTemplate[]>('/beats/templates'),
  beatMetrics: (bookId?: number, templateId?: number, flatThreshold = 3000) => {
    const q: string[] = [];
    if (bookId != null) q.push(`book_id=${bookId}`);
    if (templateId != null) q.push(`template_id=${templateId}`);
    q.push(`flat_threshold=${flatThreshold}`);
    return getJSON<BeatMetrics>(`/beats/metrics?${q.join('&')}`);
  },
  beatSuggest: (bookId?: number, templateId?: number, flatThreshold = 3000) => {
    const q: string[] = [];
    if (bookId != null) q.push(`book_id=${bookId}`);
    if (templateId != null) q.push(`template_id=${templateId}`);
    q.push(`flat_threshold=${flatThreshold}`);
    return getJSON<{ suggestions: BeatSuggestion[] }>(`/beats/suggest?${q.join('&')}`);
  },

  // ---- 写作统计 ----
  statsToday: (bookId?: number) => getJSON<TodayStat>(`/stats/today${bookId != null ? `?book_id=${bookId}` : ''}`),
  statsDaily: (date?: string, bookId?: number) => {
    const q: string[] = [];
    if (date) q.push(`date=${date}`);
    if (bookId != null) q.push(`book_id=${bookId}`);
    return getJSON<DailyStat>(`/stats/daily${q.length ? `?${q.join('&')}` : ''}`);
  },
  statsHeatmap: (bookId?: number, days = 180) => getJSON<DailyStat[]>(`/stats/heatmap?days=${days}${bookId != null ? `&book_id=${bookId}` : ''}`),
  statsStreak: (bookId?: number) => getJSON<{ days: number }>(`/stats/streak${bookId != null ? `?book_id=${bookId}` : ''}`),
  statsGoal: (bookId?: number) => getJSON<WritingGoal>(`/stats/goals${bookId != null ? `?book_id=${bookId}` : ''}`),
  setStatGoal: (bookId: number | null, dailyWords: number) =>
    send<WritingGoal>('/stats/goals', 'PUT', { book_id: bookId, daily_words: dailyWords }),
  statsPlans: (bookId?: number) => getJSON<UpdatePlan[]>(`/stats/update-plans${bookId != null ? `?book_id=${bookId}` : ''}`),
  addStatPlan: (bookId: number | null, timeOfDay = '20:00', days = '1,2,3,4,5,6,7', enabled = 1) =>
    send<UpdatePlan>('/stats/update-plans', 'POST', { book_id: bookId, time_of_day: timeOfDay, days, enabled }),
  deleteStatPlan: (pid: number) => send<{ ok: boolean }>(`/stats/update-plans/${pid}`, 'DELETE'),
  statsNotifications: (unread = false, bookId?: number) => {
    const q: string[] = [];
    if (unread) q.push('unread=true');
    if (bookId != null) q.push(`book_id=${bookId}`);
    return getJSON<Notification[]>(`/stats/notifications${q.length ? `?${q.join('&')}` : ''}`);
  },
  readNotification: (id?: number) => send<{ ok: boolean }>('/stats/notifications/read', 'POST', { id: id ?? null }),

  // ---- 兼容工具 ----
  toolWordFreq: (body: { text?: string; chapter_ids?: number[]; top_n?: number }) =>
    send<{ words: WordFreqItem[] }>('/tools/word-freq', 'POST', body),
  toolAiTaste: (body: { text?: string; chapter_ids?: number[] }) =>
    send<AiTasteResult>('/tools/ai-taste', 'POST', body),
  toolCompliance: (body: { text?: string; chapter_ids?: number[]; custom?: string[] }) =>
    send<ComplianceResult>('/tools/compliance', 'POST', body),
  toolServices: () => getJSON<ServicesResult>('/tools/services'),

  // ---- 设置 ----
  getSettings: () => getJSON<{ config: Record<string, unknown>; keys: string[] }>('/settings'),
  putSettings: (partial: Record<string, unknown>) =>
    send<Record<string, unknown>>('/settings', 'PUT', partial),

  // ---- 备份 ----
  backupList: () => getJSON<BackupItem[]>('/backup/list'),
  backupCreate: (tag?: string) => send<BackupItem>('/backup/create', 'POST', { tag: tag || null }),
  backupRestore: (name: string) => send<{ ok: boolean }>('/backup/restore', 'POST', { name }),
  backupDrill: (name: string) => send<{ ok: boolean; checked?: number }>('/backup/drill', 'POST', { name }),
  backupDelete: (name: string) => send<{ ok: boolean }>('/backup/delete', 'DELETE', { name }),

  // ---- 导出 ----
  exportDocx: (bookId: number) => send<ExportResult>('/export/docx', 'POST', { book_id: bookId }),
  exportMd: (bookId: number) => send<ExportResult>('/export/md', 'POST', { book_id: bookId }),
  exportEpub: (bookId: number) => send<ExportResult>('/export/epub', 'POST', { book_id: bookId }),
  exportFramework: (bookId: number, fmt: 'md' | 'json' = 'md') =>
    send<ExportResult>('/export/framework', 'POST', { book_id: bookId, fmt }),

  // ---- 角色模板库 ----
  getRoles: () => getJSON<RoleTemplate[]>('/roles'),
  createRole: (name: string, category: string, fields: string[]) =>
    send<RoleTemplate>('/roles', 'POST', { name, category, fields, is_global: 0 }),
  instantiateRole: (tid: number, bookId: number, name: string) =>
    send<unknown>('/roles/' + tid + '/instantiate', 'POST', { book_id: bookId, name }),
};
