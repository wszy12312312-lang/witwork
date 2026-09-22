// 全局响应式状态 + 动作（万维文 WitWork）。从旧 web/src/store.js 移植为 TypeScript。
// 当前先落地「编辑器 + 目录树 + 回收站 + 搜索替换」所需的字段与动作，
// 其余模块（AI 会话 / 知识库 / 人物 / 伏笔 / 统计 / 设置 …）后续按模块增量补充。
import { reactive } from 'vue';
import { api, type Book, type BookDetail, type Chapter, type Volume, type HistoryStatus, type PreviewResult, type TypesetChange, type Snapshot, type SearchHit, type SearchResult, type ReplacePreview, type ReplaceLog, type Provider, type Citation, type Session, type SessionMessage, type StreamEvent, type KbSection, type KbItem, type KbVersion, type KbHit, type KbReindexResult, type Persona, type PersonaVersion, type FrameworkState, type OutlineResult, type FrameworkPhase, type Character, type CharacterRelation, type CharacterAppearance, type Patch, type Foreshadow, type ForeshadowEvent, type ForeshadowAction, type ForeshadowScanMatch, type ForeshadowInjection, type Entry, type EntryCandidate, type EntryNormalizeResult, type BeatMark, type BeatTemplate, type BeatMetrics, type BeatSuggestion, type BeatKind, type DailyStat, type TodayStat, type WritingGoal, type UpdatePlan, type Notification, type WordFreqItem, type AiTasteResult, type ComplianceResult, type ServicesResult, type BackupItem, type ExportResult, type RoleTemplate, type TrashAll, type TrashedVolume, type TrashedChapter, type NowPlaying, type SongVolume, type SongAction } from './api';

// 组件习惯从 store 导入这些类型；此处统一再导出，避免「导入不存在成员」的类型不一致。
export type {
  SessionMessage, Citation, FrameworkPhase, KbItem, KbVersion, Persona, PersonaVersion,
} from './api';

export const store = reactive({
  // 连接状态
  connected: false,
  error: null as string | null,

  // 作品 / 章节
  books: [] as Book[],
  trashed: [] as Book[],
  // 回收站（作品 / 卷 / 章节三类，来自 GET /api/books/trash）
  trashedVolumes: [] as TrashedVolume[],
  trashedChapters: [] as TrashedChapter[],
  currentBookId: null as number | null,
  currentBook: null as BookDetail | null, // 详情：含 volumes / chapters
  currentChapterId: null as number | null,
  currentChapter: null as Chapter | null,
  saveStatus: 'saved' as 'saved' | 'saving' | 'unsaved',

  // 快照
  snapshots: [] as Snapshot[],

  // 撤销栈
  historyStatus: { can_undo: false, can_redo: false, undo_left: 0, redo_left: 0, depth: 0 } as HistoryStatus,

  // 手机预览 / 排版
  preview: null as PreviewResult | null,
  typesetChanges: [] as TypesetChange[],

  // 搜索替换
  searchQuery: '',
  searchHits: [] as SearchHit[],
  replaceWith: '',
  replacePreview: null as ReplacePreview | null,
  replaceLogs: [] as ReplaceLog[],

  // 占位：后续模块字段
  providers: [] as Provider[],
  sessions: [] as Session[],
  currentSessionId: null as number | null,
  sessionMessages: [] as SessionMessage[],
  streaming: false,
  aiError: '',
  draftProviderId: null as string | null,
  kbSections: [] as KbSection[],
  kbItems: [] as KbItem[],
  kbCurrentItem: null as KbItem | null,
  kbHits: [] as KbHit[],
  kbReindex: null as KbReindexResult | null,
  kbActiveSection: '' as string,
  kbQuery: '',
  kbError: '',
  patches: [] as unknown[],
  personas: [] as Persona[],
  personaCurrent: null as Persona | null,
  personaVersions: [] as PersonaVersion[],
  personaError: '',
  framework: null as FrameworkState | null,
  frameworkError: '',
  currentCharacterId: null as number | null,
  characterCurrent: null as Character | null,
  characters: [] as Character[],
  relations: [] as CharacterRelation[],
  appearances: [] as CharacterAppearance[],
  charError: '',
  currentForeshadowId: null as number | null,
  foreshadowCurrent: null as Foreshadow | null,
  foreshadowEvents: [] as ForeshadowEvent[],
  foreshadows: [] as Foreshadow[],
  foresightError: '',
  foreshadowInjection: '',
  foreshadowScan: [] as ForeshadowScanMatch[],
  entries: [] as Entry[],
  currentEntryId: null as number | null,
  entryCurrent: null as Entry | null,
  entryCandidates: [] as EntryCandidate[],
  entryNormalize: null as EntryNormalizeResult | null,
  entryError: '',
  beatMarks: [] as BeatMark[],
  beatTemplates: [] as BeatTemplate[],
  beatMetrics: null as BeatMetrics | null,
  beatSuggestions: [] as BeatSuggestion[],
  beatTemplateId: null as number | null,
  beatError: '',
  editorCursor: 0 as number, // 编辑器正文字符偏移（标注爽点用）
  statsToday: null as TodayStat | null,
  statsHeatmap: [] as DailyStat[],
  statsGoal: null as WritingGoal | null,
  statsPlans: [] as UpdatePlan[],
  statsNotifications: [] as Notification[],
  statsError: '',
  toolsWords: [] as WordFreqItem[],
  toolsTaste: null as AiTasteResult | null,
  toolsCompliance: null as ComplianceResult | null,
  toolsServices: null as ServicesResult | null,
  toolsError: '',
  settings: null as Record<string, unknown> | null,
  theme: 'dark',
  editorFontSize: 18,
  editorLineHeight: 1.8,
  editorPageWidth: 720,
  editorRuledLines: false,
  backups: [] as BackupItem[],
  settingsError: '',
  roles: [] as RoleTemplate[],
  rolesError: '',
  layoutScheme: 'A',
  aiPanelSide: 'left',
  aiOpen: false,
  // ---- 表层 UI / 功能面板 ----
  topbarAlpha: 78, // 界面统一不透明度（0-100）：顶栏 + 面板 + 内嵌区 + 抽屉一起变（历史键名 topbar_alpha 保留兼容）
  hudEnabled: false, // 功能面板开关
  hudTexture: true, // 面板质感（扫线）
  hudWidgets: 'time,today,countdown,song,focus', // 功能面板启用的部件
  songAutodetect: true, // 歌曲部件：用系统 SMTC 自动检测当前播放
  song: null as NowPlaying | null, // 最近一次 SMTC 检测结果
  songError: '',
  songCoverVersion: 0, // 封面变化计数（用于 bust 图片缓存）
  songVolume: null as SongVolume | null, // 当前播放 App 的音量状态
});

// ---- 连接 / 列表 ----
export async function bootstrap() {
  try {
    await api.health();
    store.connected = true;
  } catch {
    store.connected = false;
  }
  await loadProviders();
  await loadKbSections();
  await loadBooks();
  await loadTrash();
  await loadSettings();
  await loadBackups();
}

export async function loadBooks() {
  try {
    store.books = await api.books(false);
    store.error = null;
  } catch (e) {
    store.error = (e as Error)?.message || '加载作品失败';
    throw e;
  }
}

export async function loadTrash() {
  try {
    const all: TrashAll = await api.trashAll();
    store.trashed = all.books || [];
    store.trashedVolumes = all.volumes || [];
    store.trashedChapters = all.chapters || [];
  } catch {
    /* 新接口不可用时退回只列作品，回收站加载失败不阻断主流程 */
    try {
      store.trashed = await api.books(true);
    } catch {
      /* ignore */
    }
  }
}

// ---- 作品 ----
export async function openBook(bookId: number) {
  store.currentBookId = bookId;
  store.currentBook = await api.book(bookId);
  await loadSessions();
  await loadCharactersForBook();
  await loadConsistencyForBook();
  await loadEntries();
}

export async function openNewBook(title: string) {
  const t = (title || '未命名作品').trim() || '未命名作品';
  const b = await api.createBook({ title: t });
  // 落地即可写：自动建默认卷与首章，并直接打开首章
  const vol = await api.createVolume(b.id, { title: '正文卷' });
  const ch = await api.createChapter({ book_id: b.id, volume_id: vol.id, title: '第1章' });
  await loadBooks();
  await openBook(b.id);
  await openChapter(ch.id);
}

export async function openNewVolume(bookId: number, title: string) {
  const t = (title || '正文卷').trim() || '正文卷';
  await api.createVolume(bookId, { title: t });
  await openBook(bookId);
}

// ---- 章节 ----
export async function openChapter(chapterId: number) {
  try {
    store.currentChapterId = chapterId;
    store.currentChapter = await api.chapter(chapterId);
  } catch (e) {
    // 章节（或其所属作品）已被删除：后端会 404。清空编辑区回到空态，
    // 而不是把上一章的内容继续挂在界面上。
    console.warn('openChapter 失败，章节不可见：', e);
    store.currentChapterId = null;
    store.currentChapter = null;
    store.snapshots = [];
    store.saveStatus = 'saved';
    return;
  }
  store.currentChapterId = chapterId;
  store.saveStatus = 'saved';
  await loadSnapshots(chapterId);
  await loadHistoryStatus();
  store.typesetChanges = [];
  store.preview = null;
}

export async function openNewChapter(volumeId: number | null) {
  const bookId = store.currentBookId;
  if (!bookId) return;
  const ch = await api.createChapter({ book_id: bookId, volume_id: volumeId || null, title: '未命名章节' });
  await openBook(bookId);
  await openChapter(ch.id);
}

export async function saveChapter(payload: Partial<Chapter>) {
  if (!store.currentChapterId) return;
  store.saveStatus = 'saving';
  store.currentChapter = await api.updateChapter(store.currentChapterId, payload);
  store.saveStatus = 'saved';
  if (store.currentBook) {
    const ch = store.currentBook.chapters.find((c) => c.id === store.currentChapterId);
    if (ch) {
      ch.title = store.currentChapter.title;
      ch.words = store.currentChapter.words;
    }
  }
}

// ---- 快照 ----
export async function loadSnapshots(chapterId: number) {
  store.snapshots = await api.listSnapshots(chapterId);
}

export async function makeSnapshot() {
  if (!store.currentChapterId) return;
  await api.createSnapshot(store.currentChapterId, { title: '手动快照 ' + new Date().toLocaleString() });
  await loadSnapshots(store.currentChapterId);
}

export async function restoreSnapshot(sid: number) {
  if (!store.currentChapterId) return;
  await api.restoreSnapshot(sid);
  store.currentChapter = await api.chapter(store.currentChapterId);
  await loadSnapshots(store.currentChapterId);
}

export async function diffSnapshot(sid: number): Promise<{ type: string; text: string }[] | null> {
  if (!store.currentChapterId) return null;
  const r = await api.diffSnapshot(store.currentChapterId, sid);
  return (r as { diff?: { type: string; text: string }[] }).diff || null;
}

// ---- 回收站 ----
export async function trashBook(id: number) {
  await api.trash(id);
  await loadBooks();
  // 兜底清理：只要当前编辑区指向的作品已不在可见列表（无论删除的是哪本书、
  // 状态是否一致），一律复位编辑区。否则会出现"作品都删了，原文还挂在编辑器"。
  if (store.currentBookId !== null && !store.books.some((b) => b.id === store.currentBookId)) {
    store.currentBookId = null;
    store.currentBook = null;
    store.currentChapterId = null;
    store.currentChapter = null;
    store.snapshots = [];
  }
  await loadTrash();
}

export async function restoreBook(id: number) {
  await api.restore(id);
  await loadBooks();
  await loadTrash();
}

// ---- 单章 / 单卷删除（软删 → 回收站，可恢复） ----
// 删当前打开的章节/卷时，要把编辑区一并复位，否则界面会停在已删除的内容上。
export async function deleteChapter(id: number) {
  await api.deleteChapter(id);
  if (store.currentChapterId === id) {
    store.currentChapterId = null;
    store.currentChapter = null;
    store.snapshots = [];
  }
  if (store.currentBookId) await openBook(store.currentBookId);
  await loadTrash();
}

export async function restoreChapter(id: number) {
  await api.restoreChapter(id);
  if (store.currentBookId) await openBook(store.currentBookId);
  await loadTrash();
}

export async function deleteVolume(volumeId: number) {
  await api.deleteVolume(volumeId);
  // 该卷下的章节会一起隐藏：若当前正在编辑其中之一，则清空编辑区
  if (store.currentChapter?.volume_id === volumeId) {
    store.currentChapterId = null;
    store.currentChapter = null;
    store.snapshots = [];
  }
  if (store.currentBookId) await openBook(store.currentBookId);
  await loadTrash();
}

export async function restoreVolume(volumeId: number) {
  await api.restoreVolume(volumeId);
  if (store.currentBookId) await openBook(store.currentBookId);
  await loadTrash();
}

// ---- 当前播放歌曲（Windows SMTC） ----
export async function refreshSong(force = false) {
  if (!store.songAutodetect) {
    store.song = null;
    store.songError = '';
    return;
  }
  try {
    store.song = await api.songNow(force);
    store.songError = store.song?.ok ? '' : (store.song?.error || '');
    if (store.song?.ok) store.songCoverVersion = store.song.cover_version ?? 0;
  } catch (e) {
    store.songError = (e as Error)?.message || '歌曲检测失败';
  }
}

// 传输控制（play/pause/toggle/next/prev）
export async function songControl(action: SongAction): Promise<{ ok: boolean; error?: string }> {
  try {
    const r = await api.songControl(action);
    // 控制后立即使状态与封面刷新一次
    void refreshSong(true);
    if (action === 'next' || action === 'prev') loadSongVolume();
    return r;
  } catch (e) {
    return { ok: false, error: (e as Error)?.message || '传输控制失败' };
  }
}

// 读取当前播放 App 的音量
export async function loadSongVolume() {
  if (!store.songAutodetect || !store.song?.ok) return;
  const appId = store.song.current?.appId || '';
  try {
    store.songVolume = await api.songVolume(appId);
  } catch {
    store.songVolume = { available: false, level: 0, muted: false };
  }
}

// 设置当前播放 App 的音量（0-100）
export async function setSongVolume(level: number) {
  const appId = store.song?.current?.appId || '';
  try {
    store.songVolume = await api.songVolumeSet(appId, level);
  } catch (e) {
    store.songError = (e as Error)?.message || '音量设置失败';
  }
}

// ---- 撤销栈 ----
export async function pushHistory(content: string, label: string) {
  if (!store.currentChapterId) return;
  store.historyStatus = await api.historyPush(store.currentChapterId, content, label);
}

export async function undoHistory(): Promise<string | null> {
  if (!store.currentChapterId) return null;
  const r = await api.historyUndo(store.currentChapterId);
  if (r.status) store.historyStatus = r.status;
  return r.content;
}

export async function redoHistory(): Promise<string | null> {
  if (!store.currentChapterId) return null;
  const r = await api.historyRedo(store.currentChapterId);
  if (r.status) store.historyStatus = r.status;
  return r.content;
}

export async function loadHistoryStatus() {
  if (!store.currentChapterId) return;
  store.historyStatus = await api.historyStatus(store.currentChapterId);
}

// ---- 手机预览 / 排版 ----
export async function loadPreview(content: string) {
  if (!store.currentChapterId) return;
  store.preview = await api.typesetPreview(store.currentChapterId, content);
}

export async function runTypeset(content: string): Promise<TypesetChange[] | null> {
  if (!store.currentChapterId) return null;
  const r = await api.typesetNormalize(store.currentChapterId, content, {}, true);
  store.typesetChanges = r.changes || [];
  return store.typesetChanges;
}

export async function applyTypeset(content: string): Promise<string | null> {
  if (!store.currentChapterId) return null;
  const r = await api.typesetNormalize(store.currentChapterId, content, {}, false);
  store.typesetChanges = [];
  return r.content ?? null;
}

// ---- 全文搜索与替换 ----
export async function doSearch(q: string, opts: Record<string, unknown> = {}): Promise<SearchResult | null> {
  if (!store.currentBookId) return null;
  store.searchQuery = q;
  const r = await api.searchBook(store.currentBookId, q, opts);
  store.searchHits = r.hits || [];
  return r;
}

export async function doReplace(replacement: string, dryRun: boolean, opts: Record<string, unknown> = {}): Promise<ReplacePreview | null> {
  if (!store.currentBookId) return null;
  store.replaceWith = replacement;
  const r = await api.replaceBook(store.currentBookId, store.searchQuery, replacement, { ...opts, dry_run: !!dryRun });
  store.replacePreview = r;
  return r;
}

export async function loadReplaceLogs() {
  if (!store.currentBookId) return;
  store.replaceLogs = await api.listReplaceLogs(store.currentBookId);
}

export async function undoReplace(rid: number) {
  await api.undoReplace(rid);
  await loadReplaceLogs();
}

// ---- Provider / AI 会话 ----
export async function loadProviders() {
  try {
    store.providers = await api.providers();
    if (!store.draftProviderId) {
      // 兜底优先真实模型：mock 是离线演示占位，常排在最前，直接取第一个会
      // 让没设默认模型的用户点「生成」得到「演示模式」占位回复。
      const enabled = store.providers.filter((p) => p.enabled);
      const real = enabled.filter((p) => p.kind !== 'mock');
      const def = enabled.find((p) => p.is_default) || real[0] || enabled[0];
      store.draftProviderId = def ? def.id : null;
    }
  } catch {
    store.providers = [];
  }
}

// 选择要使用的模型：用户设的默认 > 真实模型 > 任意启用项（最后才落到 mock 演示占位）。
// 会话创建、打开会话、生成兜底统一走它，避免各处口径不一致导致「静默用上 mock」。
export function pickProviderId(): string | null {
  const enabled = store.providers.filter((p) => p.enabled);
  const def = enabled.find((p) => p.is_default);
  const real = enabled.filter((p) => p.kind !== 'mock');
  return (def || real[0] || enabled[0])?.id ?? null;
}

export async function setProviderDefault(pid: string) {
  const r = await api.setDefaultProvider(pid);
  await loadProviders();
  if (r && r.default_provider_id) store.draftProviderId = r.default_provider_id;
  return r;
}

export async function reloadProviders() {
  return loadProviders();
}

export async function loadSessions() {
  if (!store.currentBookId) {
    store.sessions = [];
    store.currentSessionId = null;
    store.sessionMessages = [];
    return;
  }
  try {
    store.sessions = await api.listSessions(store.currentBookId);
    if (store.currentSessionId && !store.sessions.some((s) => s.id === store.currentSessionId)) {
      store.currentSessionId = null;
      store.sessionMessages = [];
    }
  } catch {
    store.sessions = [];
  }
}

export async function openSession(sid: number) {
  store.currentSessionId = sid;
  store.aiError = '';
  try {
    const s = await api.getSession(sid);
    const idx = store.sessions.findIndex((x) => x.id === sid);
    if (idx >= 0) store.sessions[idx] = s;
    else store.sessions = [...store.sessions, s];
    store.sessionMessages = (s.messages || []) as SessionMessage[];
    const active = (s.active_provider_id as string | null) || pickProviderId();
    store.draftProviderId = active;
  } catch (e) {
    store.aiError = (e as Error)?.message || '打开会话失败';
  }
}

export async function createSessionForBook(title?: string) {
  // 未选中作品时不能直接 return —— 以前这里静默退出，界面毫无反馈，
  // 加上错误条只在「已有会话」分支渲染，空态下任何报错都看不见，
  // 表现就是「点了『新建会话』没反应」。
  if (!store.currentBookId) {
    if (!store.books.length) {
      try {
        await loadBooks();
      } catch {
        /* 交给下面的提示 */
      }
    }
    const first = store.books[0];
    if (first) {
      // 有作品只是没选中：自动选用第一个可见作品，别让用户卡住
      store.currentBookId = first.id;
    } else {
      store.aiError = '还没有作品：请先在左侧新建一个作品，再开始 AI 协作会话';
      return;
    }
  }
  const pid = store.draftProviderId || pickProviderId();
  store.aiError = '';
  try {
    const s = await api.createSession(store.currentBookId, title?.trim() || '新会话', pid);
    await loadSessions();
    await openSession(s.id);
  } catch (e) {
    store.aiError = (e as Error)?.message || '新建会话失败';
  }
}

export async function deleteSession(sid: number) {
  try {
    await api.deleteSession(sid);
  } catch {
    /* ignore */
  }
  if (store.currentSessionId === sid) {
    store.currentSessionId = null;
    store.sessionMessages = [];
  }
  await loadSessions();
}

export async function setSessionProvider(sid: number, pid: string | null) {
  if (!sid) return;
  try {
    await api.setSessionProvider(sid, pid);
    const idx = store.sessions.findIndex((x) => x.id === sid);
    if (idx >= 0) store.sessions[idx] = { ...store.sessions[idx], active_provider_id: pid };
  } catch (e) {
    store.aiError = (e as Error)?.message || '切换模型失败';
  }
  store.draftProviderId = pid;
}

// 流式生成（SSE）。维护本地消息列表：先追加 user，再追加一个 _live 的 assistant 占位，
// 事件到来时增量填充 refs/delta，done/error 收尾；结束后从后端拉取持久化的干净消息。
let currentAbort: AbortController | null = null;
let aiOpsAbort: AbortController | null = null;

export async function sendMessage(content: string) {
  const sid = store.currentSessionId;
  if (!sid || !content.trim() || store.streaming) return;
  store.streaming = true;
  store.aiError = '';
  store.sessionMessages = [
    ...store.sessionMessages,
    { role: 'user', content, refs: null, token_count: 0 } as SessionMessage,
    { role: 'assistant', content: '', refs: [], _live: true } as SessionMessage,
  ];
  const pid = store.draftProviderId ?? null;
  const ac = new AbortController();
  currentAbort = ac;
  try {
    await api.sendMessageStream(
      sid,
      content,
      pid,
      (ev: StreamEvent) => {
        const msgs = store.sessionMessages as SessionMessage[];
        const last = msgs[msgs.length - 1];
        if (!last) return;
        if (ev.type === 'refs') {
          (last as SessionMessage & { refs: Citation[] }).refs = (ev.data as Citation[]) || [];
        } else if (ev.type === 'delta') {
          last.content += (ev.data as string) || '';
        } else if (ev.type === 'done') {
          (last as SessionMessage & { _live?: boolean })._live = false;
          const d = ev.data as { tokens?: number };
          if (d?.tokens != null) last.token_count = d.tokens;
        } else if (ev.type === 'error') {
          store.aiError = (ev.data as string) || '生成出错';
          (last as SessionMessage & { _live?: boolean })._live = false;
        }
      },
      ac.signal
    );
  } catch (e) {
    const err = e as Error;
    if (err?.name !== 'AbortError') {
      store.aiError = err?.message || '生成失败';
      const msgs = store.sessionMessages as SessionMessage[];
      const last = msgs[msgs.length - 1];
      if (last && (last as SessionMessage & { _live?: boolean })._live) {
        (last as SessionMessage & { _live?: boolean })._live = false;
      }
    }
  } finally {
    store.streaming = false;
    currentAbort = null;
    // 拉取后端持久化的干净消息（含 refs / 真实 id），覆盖本地占位
    if (store.currentSessionId) {
      try {
        await openSession(store.currentSessionId);
      } catch {
        /* ignore */
      }
    }
  }
}

export function stopStreaming() {
  if (currentAbort) currentAbort.abort();
}

// ---- AI 正文操作（改写/续写/扩写/缩写/创作/通读全书）----
export async function aiOperate(
  payload: {
    operation: string;
    book_id: number | null;
    chapter_id: number | null;
    text: string;
    instruction?: string;
    scope?: string;
    provider_id?: string | null;
    /** 附加生成参数（如 target_words 目标字数），透传到后端 */
    params?: Record<string, unknown> | null;
  },
  onEvent: (ev: StreamEvent) => void
): Promise<void> {
  if (store.streaming) return;
  store.streaming = true;
  store.aiError = '';
  const ac = new AbortController();
  aiOpsAbort = ac;
  try {
    await api.aiOpsStream(payload, onEvent, ac.signal);
  } catch (e) {
    const err = e as Error;
    if (err?.name !== 'AbortError') {
      store.aiError = err?.message || '生成失败';
    }
  } finally {
    store.streaming = false;
    aiOpsAbort = null;
  }
}

export function stopAiOperate() {
  if (aiOpsAbort) aiOpsAbort.abort();
}

// ---- 知识库 ----
export async function loadKbSections() {
  try {
    store.kbSections = await api.kbSections();
    if (!store.kbActiveSection && store.kbSections.length) {
      store.kbActiveSection = store.kbSections[0].key;
    }
  } catch {
    store.kbSections = [];
  }
}

export async function loadKbItems(section?: string) {
  const sec = section ?? store.kbActiveSection;
  store.kbActiveSection = sec;
  try {
    store.kbItems = await api.kbItems(sec || undefined);
  } catch {
    store.kbItems = [];
  }
}

export async function openKbItem(id: number) {
  try {
    store.kbCurrentItem = await api.kbItem(id);
  } catch (e) {
    store.kbError = (e as Error)?.message || '打开条目失败';
  }
}

export async function createKbItem(section: string, title: string, content: string) {
  try {
    await api.createKbItem(section, title.trim(), content);
    await loadKbItems(section);
  } catch (e) {
    store.kbError = (e as Error)?.message || '新建条目失败';
  }
}

export async function saveKbItem(id: number, payload: { title?: string; content?: string; reason?: string }) {
  try {
    await api.saveKbItem(id, payload);
    await openKbItem(id);
    await loadKbItems(store.kbActiveSection);
  } catch (e) {
    store.kbError = (e as Error)?.message || '保存失败';
  }
}

export async function deleteKbItem(id: number) {
  try {
    await api.deleteKbItem(id);
  } catch {
    /* ignore */
  }
  store.kbCurrentItem = null;
  await loadKbItems(store.kbActiveSection);
}

export async function rollbackKbItem(id: number, versionId: number) {
  try {
    await api.rollbackKbItem(id, versionId);
    await openKbItem(id);
    await loadKbItems(store.kbActiveSection);
  } catch (e) {
    store.kbError = (e as Error)?.message || '回滚失败';
  }
}

export async function retrieveKb(query: string, sections?: string[]) {
  store.kbQuery = query;
  try {
    const r = await api.kbRetrieve(query, sections);
    store.kbHits = r.hits || [];
  } catch (e) {
    store.kbError = (e as Error)?.message || '检索失败';
    store.kbHits = [];
  }
}

export async function reindexKb(section?: string) {
  try {
    store.kbReindex = await api.kbReindex(section);
  } catch (e) {
    store.kbError = (e as Error)?.message || '重建索引失败';
  }
}

// ---- 人格 ----
export async function loadPersonas() {
  try {
    store.personas = await api.personas();
  } catch {
    store.personas = [];
  }
}

export async function openPersona(id: number) {
  try {
    store.personaCurrent = await api.persona(id);
    store.personaVersions = await api.personaVersions(id);
  } catch (e) {
    store.personaError = (e as Error)?.message || '打开人格失败';
  }
}

export async function createPersona(p: Partial<Persona>) {
  try {
    await api.createPersona(p);
    await loadPersonas();
  } catch (e) {
    store.personaError = (e as Error)?.message || '新建人格失败';
  }
}

export async function savePersona(id: number, p: Partial<Persona>) {
  try {
    await api.savePersona(id, p);
    await openPersona(id);
    await loadPersonas();
  } catch (e) {
    store.personaError = (e as Error)?.message || '保存失败';
  }
}

export async function deletePersona(id: number) {
  try {
    await api.deletePersona(id);
  } catch {
    /* ignore */
  }
  store.personaCurrent = null;
  await loadPersonas();
}

export async function activatePersona(id: number) {
  try {
    await api.activatePersona(id);
    await loadPersonas();
  } catch (e) {
    store.personaError = (e as Error)?.message || '激活失败';
  }
}

export async function adjustPersona(statement: string) {
  if (!store.currentSessionId) {
    store.personaError = '需先开启一个 AI 会话才能用自然语言调整人格';
    return;
  }
  store.personaError = '';
  try {
    await api.adjustPersona(store.currentSessionId, statement);
    await loadPersonas();
    if (store.personaCurrent) await openPersona(store.personaCurrent.id);
  } catch (e) {
    store.personaError = (e as Error)?.message || '调整失败';
  }
}

// ---- 框架共创 ----
export async function loadFramework() {
  store.frameworkError = '';
  if (!store.currentSessionId) {
    store.framework = null;
    return;
  }
  try {
    store.framework = await api.frameworkState(store.currentSessionId);
  } catch (e) {
    store.framework = null;
    store.frameworkError = (e as Error)?.message || '加载框架状态失败';
  }
}

export async function advanceFramework(conclusion: string, note?: string | null) {
  if (!store.currentSessionId) {
    store.frameworkError = '需先开启一个 AI 会话';
    return;
  }
  if (!conclusion.trim()) return;
  try {
    store.framework = await api.advanceFramework(store.currentSessionId, conclusion.trim(), note ?? null);
  } catch (e) {
    store.frameworkError = (e as Error)?.message || '推进失败';
  }
}

export async function retreatFramework() {
  if (!store.currentSessionId) return;
  try {
    store.framework = await api.retreatFramework(store.currentSessionId);
  } catch (e) {
    store.frameworkError = (e as Error)?.message || '回退失败';
  }
}

export async function generateOutline() {
  if (!store.currentSessionId) {
    store.frameworkError = '需先开启一个 AI 会话';
    return;
  }
  if (!store.currentBookId) {
    store.frameworkError = '需先打开一个作品才能生成章节骨架';
    return;
  }
  try {
    const r: OutlineResult = await api.generateOutline(store.currentSessionId, store.currentBookId);
    // 重新拉取状态（outline 阶段已写 _outline_created）
    await loadFramework();
    if (r.count) await loadBooks();
  } catch (e) {
    store.frameworkError = (e as Error)?.message || '生成章节骨架失败';
  }
}

// ---- 人物卡 ----
export function aliasesOf(c: Character | null): string[] {
  if (!c) return [];
  if (Array.isArray(c.aliases)) return c.aliases;
  try {
    return JSON.parse(c.aliases_json || '[]') as string[];
  } catch {
    return [];
  }
}

export async function loadCharacters() {
  store.charError = '';
  try {
    store.characters = await api.characters(store.currentBookId ?? undefined);
  } catch (e) {
    store.charError = (e as Error)?.message || '加载人物失败';
  }
}

export async function openCharacter(id: number) {
  store.charError = '';
  try {
    store.currentCharacterId = id;
    store.characterCurrent = await api.character(id);
    await loadAppearances(id);
    await loadRelations();
  } catch (e) {
    store.charError = (e as Error)?.message || '打开人物失败';
  }
}

export async function createCharacter(name: string, fields?: Record<string, unknown>) {
  store.charError = '';
  try {
    await api.createCharacter(store.currentBookId, name.trim(), fields);
    await loadCharacters();
  } catch (e) {
    store.charError = (e as Error)?.message || '新建人物失败';
  }
}

export async function saveCharacter(id: number, payload: Record<string, unknown>) {
  store.charError = '';
  try {
    await api.saveCharacter(id, payload);
    await openCharacter(id);
    await loadCharacters();
  } catch (e) {
    store.charError = (e as Error)?.message || '保存失败';
  }
}

export async function deleteCharacter(id: number) {
  try {
    await api.deleteCharacter(id);
  } catch {
    /* ignore */
  }
  if (store.currentCharacterId === id) {
    store.currentCharacterId = null;
    store.characterCurrent = null;
  }
  await loadCharacters();
}

export async function loadRelations() {
  try {
    store.relations = await api.characterRelations(store.currentBookId ?? undefined);
  } catch {
    store.relations = [];
  }
}

export async function addRelation(fromId: number, toId: number, relation: string, note?: string | null) {
  store.charError = '';
  try {
    await api.addRelation(store.currentBookId, fromId, toId, relation, note ?? null);
    await loadRelations();
  } catch (e) {
    store.charError = (e as Error)?.message || '添加关系失败';
  }
}

export async function deleteRelation(rid: number) {
  try {
    await api.deleteRelation(rid);
  } catch {
    /* ignore */
  }
  await loadRelations();
}

export async function loadAppearances(cid: number) {
  try {
    store.appearances = await api.characterAppearances(cid);
  } catch {
    store.appearances = [];
  }
}

export async function scanAppearances(text: string): Promise<number> {
  if (!store.currentCharacterId) return 0;
  store.charError = '';
  try {
    const r = await api.scanAppearances(store.currentBookId, store.currentChapterId, text);
    await loadAppearances(store.currentCharacterId);
    return (r.records || []).length;
  } catch (e) {
    store.charError = (e as Error)?.message || '扫描出场失败';
    return 0;
  }
}

export async function extractCandidates(text: string): Promise<Patch[]> {
  store.charError = '';
  try {
    const r = await api.extractCandidates(store.currentBookId, text, store.currentSessionId);
    store.patches = r.patches || [];
    return r.patches || [];
  } catch (e) {
    store.charError = (e as Error)?.message || '抽取候选失败';
    return [];
  }
}

export async function applyPatch(pid: number) {
  store.charError = '';
  try {
    await api.applyPatch(pid);
  } catch (e) {
    store.charError = (e as Error)?.message || '应用失败';
  }
  store.patches = (store.patches as Patch[]).filter((p) => (p as Patch).id !== pid);
  await loadCharacters();
}

export async function rejectPatch(pid: number) {
  try {
    await api.rejectPatch(pid);
  } catch {
    /* ignore */
  }
  store.patches = (store.patches as Patch[]).filter((p) => (p as Patch).id !== pid);
}

// 打开作品时连带加载人物（关系随后按需）
export async function loadCharactersForBook() {
  if (!store.currentBookId) {
    store.characters = [];
    store.relations = [];
    return;
  }
  await loadCharacters();
  await loadRelations();
}

// ---- 伏笔 ----
export async function loadForeshadows() {
  store.foresightError = '';
  try {
    store.foreshadows = await api.foreshadows(store.currentBookId ?? undefined);
  } catch (e) {
    store.foresightError = (e as Error)?.message || '加载伏笔失败';
  }
}

export async function openForeshadow(id: number) {
  store.foresightError = '';
  try {
    store.currentForeshadowId = id;
    store.foreshadowCurrent = await api.foreshadow(id);
    store.foreshadowEvents = await api.foreshadowEvents(id);
  } catch (e) {
    store.foresightError = (e as Error)?.message || '打开伏笔失败';
  }
}

export async function createForeshadow(title: string, content?: string | null, importance?: number, keywords?: string | null) {
  store.foresightError = '';
  try {
    await api.createForeshadow(store.currentBookId, title.trim(), content, importance, keywords);
    await loadForeshadows();
  } catch (e) {
    store.foresightError = (e as Error)?.message || '新建伏笔失败';
  }
}

export async function saveForeshadow(id: number, payload: Record<string, unknown>) {
  store.foresightError = '';
  try {
    await api.saveForeshadow(id, payload);
    await openForeshadow(id);
    await loadForeshadows();
  } catch (e) {
    store.foresightError = (e as Error)?.message || '保存失败';
  }
}

export async function deleteForeshadow(id: number) {
  try {
    await api.deleteForeshadow(id);
  } catch {
    /* ignore */
  }
  if (store.currentForeshadowId === id) {
    store.currentForeshadowId = null;
    store.foreshadowCurrent = null;
    store.foreshadowEvents = [];
  }
  await loadForeshadows();
}

export async function foreshadowAction(id: number, action: ForeshadowAction, chapterId?: number | null, note?: string | null) {
  store.foresightError = '';
  try {
    await api.foreshadowAction(id, action, chapterId ?? null, note ?? null);
    await openForeshadow(id);
    await loadForeshadows();
  } catch (e) {
    store.foresightError = (e as Error)?.message || '操作失败';
  }
}

export async function loadForeshadowInjection() {
  try {
    const r = await api.foreshadowInjection(store.currentBookId ?? undefined);
    store.foreshadowInjection = r.text || '';
  } catch {
    store.foreshadowInjection = '';
  }
}

export async function scanForeshadow(text: string) {
  store.foresightError = '';
  try {
    const r = await api.scanForeshadow(store.currentBookId, text);
    store.foreshadowScan = r.matches || [];
  } catch (e) {
    store.foresightError = (e as Error)?.message || '扫描失败';
    store.foreshadowScan = [];
  }
}

// 打开作品时连带加载伏笔
export async function loadConsistencyForBook() {
  if (!store.currentBookId) {
    store.foreshadows = [];
    return;
  }
  await loadForeshadows();
  await loadForeshadowInjection();
}

// ---- 词条 ----
export function aliasesOfEntry(e: Entry | null): string[] {
  if (!e) return [];
  if (Array.isArray(e.aliases)) return e.aliases;
  try {
    return JSON.parse(e.aliases_json || '[]') as string[];
  } catch {
    return [];
  }
}

export async function loadEntries() {
  store.entryError = '';
  try {
    store.entries = await api.entries(store.currentBookId ?? undefined);
  } catch (e) {
    store.entryError = (e as Error)?.message || '加载词条失败';
  }
}

export async function openEntry(id: number) {
  store.entryError = '';
  try {
    store.currentEntryId = id;
    store.entryCurrent = await api.entry(id);
  } catch (e) {
    store.entryError = (e as Error)?.message || '打开词条失败';
  }
}

export async function createEntry(name: string, category?: string | null, aliases?: string[], description?: string | null) {
  store.entryError = '';
  try {
    await api.createEntry(store.currentBookId, name.trim(), category, aliases, description);
    await loadEntries();
  } catch (e) {
    store.entryError = (e as Error)?.message || '新建词条失败';
  }
}

export async function saveEntry(id: number, payload: Record<string, unknown>) {
  store.entryError = '';
  try {
    await api.saveEntry(id, payload);
    await openEntry(id);
    await loadEntries();
  } catch (e) {
    store.entryError = (e as Error)?.message || '保存失败';
  }
}

export async function deleteEntry(id: number) {
  try {
    await api.deleteEntry(id);
  } catch {
    /* ignore */
  }
  if (store.currentEntryId === id) {
    store.currentEntryId = null;
    store.entryCurrent = null;
  }
  await loadEntries();
}

export async function extractEntries(texts?: string[], topN = 30, minCount = 2) {
  store.entryError = '';
  try {
    const r = await api.extractEntries(store.currentBookId, texts, undefined, topN, minCount);
    store.entryCandidates = r.candidates || [];
  } catch (e) {
    store.entryError = (e as Error)?.message || '抽取候选失败';
  }
}

export async function normalizeEntries(chapterIds?: number[]) {
  store.entryError = '';
  try {
    const r = await api.normalizeEntries(store.currentBookId, chapterIds);
    store.entryNormalize = r.replaced || null;
  } catch (e) {
    store.entryError = (e as Error)?.message || '归一化失败';
  }
}

// ---- 爽点节奏 ----
export async function loadBeatMarks() {
  store.beatError = '';
  try {
    store.beatMarks = await api.beats(store.currentBookId ?? undefined);
  } catch (e) {
    store.beatError = (e as Error)?.message || '加载爽点标注失败';
  }
}

export async function loadBeatTemplates() {
  try {
    store.beatTemplates = await api.beatTemplates();
    if (store.beatTemplateId == null && store.beatTemplates.length) {
      const builtin = store.beatTemplates.find((t) => t.built_in);
      store.beatTemplateId = builtin ? builtin.id : store.beatTemplates[0].id;
    }
  } catch {
    store.beatTemplates = [];
  }
}

export async function loadBeatMetrics(templateId?: number | null) {
  if (templateId != null) store.beatTemplateId = templateId;
  if (!store.currentBookId) return;
  store.beatError = '';
  try {
    store.beatMetrics = await api.beatMetrics(store.currentBookId, store.beatTemplateId ?? undefined);
  } catch (e) {
    store.beatError = (e as Error)?.message || '加载节奏指标失败';
  }
}

export async function loadBeatSuggest(templateId?: number | null) {
  if (templateId != null) store.beatTemplateId = templateId;
  if (!store.currentBookId) return;
  store.beatError = '';
  try {
    const r = await api.beatSuggest(store.currentBookId, store.beatTemplateId ?? undefined);
    store.beatSuggestions = r.suggestions || [];
  } catch (e) {
    store.beatError = (e as Error)?.message || '加载建议失败';
  }
}

// 打开爽点抽屉时一次性加载：标注 + 模板 + 指标 + 建议
export async function refreshBeat() {
  if (!store.currentBookId) return;
  await loadBeatTemplates();
  await loadBeatMarks();
  await loadBeatMetrics();
  await loadBeatSuggest();
}

export async function addBeat(chapterId: number, kind: BeatKind, strength: number, offset = 0, text?: string | null) {
  store.beatError = '';
  try {
    await api.addBeat({
      book_id: store.currentBookId,
      chapter_id: chapterId,
      kind,
      strength,
      offset,
      text: text ?? null,
      source: 'manual',
    });
    await loadBeatMarks();
    await loadBeatMetrics();
  } catch (e) {
    store.beatError = (e as Error)?.message || '添加爽点失败';
  }
}

export async function deleteBeat(id: number) {
  try {
    await api.deleteBeat(id);
  } catch {
    /* ignore */
  }
  await loadBeatMarks();
  await loadBeatMetrics();
}

// ---- 写作统计 ----
export async function loadStatsToday() {
  if (!store.currentBookId) return;
  store.statsError = '';
  try {
    store.statsToday = await api.statsToday(store.currentBookId);
  } catch (e) {
    store.statsError = (e as Error)?.message || '加载今日统计失败';
  }
}

export async function loadStatsHeatmap(days = 180) {
  if (!store.currentBookId) return;
  store.statsError = '';
  try {
    store.statsHeatmap = await api.statsHeatmap(store.currentBookId, days);
  } catch (e) {
    store.statsError = (e as Error)?.message || '加载热力图失败';
  }
}

export async function loadStatGoal() {
  if (!store.currentBookId) return;
  try {
    store.statsGoal = await api.statsGoal(store.currentBookId);
  } catch {
    store.statsGoal = null;
  }
}

export async function setStatGoal(dailyWords: number) {
  if (!store.currentBookId) return;
  store.statsError = '';
  try {
    store.statsGoal = await api.setStatGoal(store.currentBookId, dailyWords);
    await loadStatsToday();
  } catch (e) {
    store.statsError = (e as Error)?.message || '设置目标失败';
  }
}

export async function loadStatPlans() {
  if (!store.currentBookId) return;
  try {
    store.statsPlans = await api.statsPlans(store.currentBookId);
  } catch {
    store.statsPlans = [];
  }
}

export async function addStatPlan(timeOfDay = '20:00', days = '1,2,3,4,5,6,7', enabled = 1) {
  if (!store.currentBookId) return;
  store.statsError = '';
  try {
    await api.addStatPlan(store.currentBookId, timeOfDay, days, enabled);
    await loadStatPlans();
  } catch (e) {
    store.statsError = (e as Error)?.message || '添加计划失败';
  }
}

export async function deleteStatPlan(pid: number) {
  try {
    await api.deleteStatPlan(pid);
  } catch {
    /* ignore */
  }
  await loadStatPlans();
}

export async function loadNotifications() {
  if (!store.currentBookId) return;
  try {
    store.statsNotifications = await api.statsNotifications(false, store.currentBookId);
  } catch {
    store.statsNotifications = [];
  }
}

export async function readNotification(id?: number) {
  try {
    await api.readNotification(id);
  } catch {
    /* ignore */
  }
  await loadNotifications();
}

// 打开统计抽屉时一次性加载
export async function refreshStats() {
  if (!store.currentBookId) return;
  await loadStatsToday();
  await loadStatsHeatmap();
  await loadStatGoal();
  await loadStatPlans();
  await loadNotifications();
}

// ---- 兼容工具 ----
function currentText(): string {
  return store.currentChapter?.content || '';
}

export async function runWordFreq(topN = 50) {
  if (!store.currentChapter) {
    store.toolsError = '请先打开一个章节';
    return;
  }
  store.toolsError = '';
  try {
    const r = await api.toolWordFreq({ text: currentText(), top_n: topN });
    store.toolsWords = r.words || [];
  } catch (e) {
    store.toolsError = (e as Error)?.message || '高频词分析失败';
  }
}

export async function runAiTaste() {
  if (!store.currentChapter) {
    store.toolsError = '请先打开一个章节';
    return;
  }
  store.toolsError = '';
  try {
    store.toolsTaste = await api.toolAiTaste({ text: currentText() });
  } catch (e) {
    store.toolsError = (e as Error)?.message || 'AI 味分析失败';
  }
}

export async function runCompliance(custom?: string[]) {
  if (!store.currentChapter) {
    store.toolsError = '请先打开一个章节';
    return;
  }
  store.toolsError = '';
  try {
    store.toolsCompliance = await api.toolCompliance({ text: currentText(), custom: custom || [] });
  } catch (e) {
    store.toolsError = (e as Error)?.message || '合规自检失败';
  }
}

export async function loadServices() {
  store.toolsError = '';
  try {
    store.toolsServices = await api.toolServices();
  } catch (e) {
    store.toolsError = (e as Error)?.message || '服务探测失败';
  }
}

// ---- 设置 ----
const SETTINGS_KEYS_NUM = new Set([
  'editor_font_size',
  'editor_line_height',
  'editor_page_width',
  'retrieval_top_k',
  'autosave_delay_ms',
  'phone_chars_per_page',
  'break_days_warn',
  'topbar_alpha',
]);

function applySettings() {
  const c = store.settings || {};
  // 历史配置可能残留已废弃的莱茵主题（rhine/rhine-light），统一兜底为 dark
  const rawTheme = (c['theme'] as string) || 'dark';
  store.theme = ['dark', 'light', 'sepia'].includes(rawTheme) ? rawTheme : 'dark';
  store.editorFontSize = Number(c['editor_font_size'] ?? 18);
  store.editorLineHeight = Number(c['editor_line_height'] ?? 1.8);
  store.editorPageWidth = Number(c['editor_page_width'] ?? 720);
  store.editorRuledLines = Boolean(c['editor_ruled_lines'] ?? false);
  store.layoutScheme = (c['layout_scheme'] as string) || 'A';
  store.aiPanelSide = (c['ai_panel_side'] as string) || 'left';
  store.topbarAlpha = clampNum(c['topbar_alpha'], 78, 0, 100);
  store.hudEnabled = Boolean(c['hud_enabled'] ?? false);
  store.hudTexture = Boolean(c['hud_texture'] ?? true);
  store.hudWidgets = (c['hud_widgets'] as string) || 'time,today,countdown,song,focus';
  store.songAutodetect = c['song_autodetect'] === undefined ? true : Boolean(c['song_autodetect']);
}

function clampNum(v: unknown, d: number, lo: number, hi: number): number {
  const n = Number(v);
  if (!Number.isFinite(n)) return d;
  return Math.min(hi, Math.max(lo, n));
}

// 功能面板生效条件：仅由 hud_enabled 控制
export function hudActive(): boolean {
  return store.hudEnabled;
}

// 实际写入 <html> 的 data-theme（不再区分莱茵明暗）
export function effectiveTheme(): string {
  return store.theme || 'dark';
}

export async function loadSettings() {
  store.settingsError = '';
  try {
    const r = await api.getSettings();
    store.settings = r.config;
    applySettings();
  } catch (e) {
    store.settingsError = (e as Error)?.message || '加载设置失败';
  }
}

export async function saveSettings(partial: Record<string, unknown>) {
  store.settingsError = '';
  try {
    const merged = await api.putSettings(partial);
    store.settings = merged;
    applySettings();
    return true;
  } catch (e) {
    store.settingsError = (e as Error)?.message || '保存设置失败';
    return false;
  }
}

// ---- 备份 ----
export async function loadBackups() {
  try {
    store.backups = await api.backupList();
  } catch {
    /* 备份加载失败不阻断 */
  }
}

export async function createBackup(tag?: string) {
  try {
    await api.backupCreate(tag);
    await loadBackups();
    return true;
  } catch (e) {
    store.settingsError = (e as Error)?.message || '创建备份失败';
    return false;
  }
}

export async function restoreBackup(name: string) {
  try {
    await api.backupRestore(name);
    return true;
  } catch (e) {
    store.settingsError = (e as Error)?.message || '恢复备份失败';
    return false;
  }
}

export async function drillBackup(name: string) {
  try {
    await api.backupDrill(name);
    return true;
  } catch (e) {
    store.settingsError = (e as Error)?.message || '演练失败';
    return false;
  }
}

export async function deleteBackup(name: string) {
  try {
    await api.backupDelete(name);
    await loadBackups();
    return true;
  } catch (e) {
    store.settingsError = (e as Error)?.message || '删除备份失败';
    return false;
  }
}

// ---- 导出 ----
export async function exportBook(bookId: number, kind: 'docx' | 'md' | 'epub' | 'framework') {
  let r: ExportResult;
  if (kind === 'docx') r = await api.exportDocx(bookId);
  else if (kind === 'md') r = await api.exportMd(bookId);
  else if (kind === 'epub') r = await api.exportEpub(bookId);
  else r = await api.exportFramework(bookId, 'md');
  if (r.download_url) {
    const a = document.createElement('a');
    a.href = r.download_url;
    a.download = r.name || '';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  return r;
}

// ---- 角色模板库 ----
export async function loadRoles() {
  store.rolesError = '';
  try {
    store.roles = await api.getRoles();
  } catch (e) {
    store.rolesError = (e as Error)?.message || '加载角色模板失败';
  }
}

export async function createRole(name: string, category: string, fields: string[]) {
  store.rolesError = '';
  try {
    await api.createRole(name, category, fields);
    await loadRoles();
    return true;
  } catch (e) {
    store.rolesError = (e as Error)?.message || '创建模板失败';
    return false;
  }
}

export async function instantiateRole(tid: number, name: string) {
  store.rolesError = '';
  if (!store.currentBookId) {
    store.rolesError = '请先打开一个作品';
    return false;
  }
  try {
    await api.instantiateRole(tid, store.currentBookId, name);
    await loadCharactersForBook();
    return true;
  } catch (e) {
    store.rolesError = (e as Error)?.message || '实例化失败';
    return false;
  }
}
