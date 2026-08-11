import { useState, useEffect, useRef, useCallback, useMemo, type ComponentProps } from 'react';
import { AgentAvatar, UserAvatar } from './components/Avatars';
import { MarkdownContent } from './components/MarkdownContent';
import { ThinkBlock } from './components/ThinkBlock';
import { DiffView } from './components/DiffView';
import { renderContent } from './components/renderContent';
import { TrackedFileCard } from './components/TrackedFileCard';
import { ErrorBoundary } from '../../components/ErrorBoundary';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Button } from '../../components/ui/Button';
import { Textarea } from '../../components/ui/Textarea';
import { Tooltip } from '../../components/ui/Tooltip';
import { ContextMenu, type ContextMenuAction } from '../../components/ContextMenu';
import { cn } from '../../lib/utils';
import { Modal } from '../../components/shared';
import { formatRelativeTime } from '../../lib/formatTime';
import {
  ExecutionPolicySelector,
  type ExecutionPolicy,
} from '../../components/ExecutionPolicySelector';
import {
  Send,
  Square,
  Loader2,
  Copy,
  Check,
  CheckCircle,
  Paperclip,
  X,
  FileText,
  Image,
  LayoutGrid,
  MoreHorizontal,
  Plus,
  Eye,
  GitMerge,
  ChevronDown,
  ChevronRight,
  ArrowDown,
  Pencil,
  BookOpen,
  GitCompare,
  Undo2,
  ListChecks,
  Settings,
  ExternalLink,
  FileSpreadsheet,
  FileBarChart,
  FolderOpen,
  Folder,
  FolderCheck,
  AlertCircle,
  FileType,
  Loader,
} from 'lucide-react';
import type {
  ChatProgress,
  ChatFinal,
  ChatError,
  ChatAborted,
  ChatSubagentResult,
} from '../../../shared/ipc';
import { extractProgressMessage, type ProgressPayload } from './progressUtils';
import { sanitizeUiMessage } from '../../lib/sanitizeUiMessage';
import PaperSearchResult, {
  tryParsePaperSearchResult,
  type PaperSearchPayload,
  type PaperItem,
} from './PaperSearchResult';

interface Attachment {
  name: string;
  type: 'image' | 'text' | 'document';
  dataUrl?: string;
  content?: string;
  size: number;
  dataBase64?: string;
  mimeType?: string;
  /** Parse status: pending → parsing → done | error */
  status?: 'pending' | 'parsing' | 'done' | 'error';
  /** Server-parsed text content, shown inline after send */
  parsedContent?: string;
  /** Parse error message if status === 'error' */
  parseError?: string;
}

const DOCUMENT_SUFFIXES_RE =
  /\.(docx|doc|pptx|ppt|xlsx|xls|pdf|odt|odp|ods|md|markdown|mdown|html|htm|csv|json|xml|yaml|yml|env|log|sql|ini|toml|htaccess|sh|bash|txt|text|rtf)$/i;

function getDocCategory(name: string): { label: string; color: string; bg: string } {
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  const map: Record<string, { label: string; color: string; bg: string }> = {
    pdf: { label: 'PDF', color: '#ef4444', bg: 'rgba(239,68,68,0.12)' },
    docx: { label: 'DOC', color: '#3b82f6', bg: 'rgba(59,130,246,0.12)' },
    doc: { label: 'DOC', color: '#3b82f6', bg: 'rgba(59,130,246,0.12)' },
    pptx: { label: 'PPT', color: '#f97316', bg: 'rgba(249,115,22,0.12)' },
    ppt: { label: 'PPT', color: '#f97316', bg: 'rgba(249,115,22,0.12)' },
    xlsx: { label: 'XLS', color: '#22c55e', bg: 'rgba(34,197,94,0.12)' },
    xls: { label: 'XLS', color: '#22c55e', bg: 'rgba(34,197,94,0.12)' },
    md: { label: 'MD', color: '#a855f7', bg: 'rgba(168,85,247,0.12)' },
    markdown: { label: 'MD', color: '#a855f7', bg: 'rgba(168,85,247,0.12)' },
    mdown: { label: 'MD', color: '#a855f7', bg: 'rgba(168,85,247,0.12)' },
    html: { label: 'HTML', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
    htm: { label: 'HTML', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
    csv: { label: 'CSV', color: '#10b981', bg: 'rgba(16,185,129,0.12)' },
    json: { label: 'JSON', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
    xml: { label: 'XML', color: '#6366f1', bg: 'rgba(99,102,241,0.12)' },
    yaml: { label: 'YAML', color: '#06b6d4', bg: 'rgba(6,182,212,0.12)' },
    yml: { label: 'YAML', color: '#06b6d4', bg: 'rgba(6,182,212,0.12)' },
    env: { label: 'ENV', color: '#84cc16', bg: 'rgba(132,204,22,0.12)' },
    log: { label: 'LOG', color: '#64748b', bg: 'rgba(100,116,139,0.12)' },
    sql: { label: 'SQL', color: '#0ea5e9', bg: 'rgba(14,165,233,0.12)' },
    ini: { label: 'INI', color: '#8b5cf6', bg: 'rgba(139,92,246,0.12)' },
    toml: { label: 'TOML', color: '#e11d48', bg: 'rgba(225,29,72,0.12)' },
    htaccess: { label: 'HTA', color: '#d946ef', bg: 'rgba(217,70,239,0.12)' },
    sh: { label: 'SH', color: '#14b8a6', bg: 'rgba(20,184,166,0.12)' },
    bash: { label: 'SH', color: '#14b8a6', bg: 'rgba(20,184,166,0.12)' },
    txt: { label: 'TXT', color: '#6b7280', bg: 'rgba(107,114,128,0.12)' },
    text: { label: 'TXT', color: '#6b7280', bg: 'rgba(107,114,128,0.12)' },
    rtf: { label: 'RTF', color: '#ec4899', bg: 'rgba(236,72,153,0.12)' },
    odt: { label: 'DOC', color: '#3b82f6', bg: 'rgba(59,130,246,0.12)' },
    odp: { label: 'PPT', color: '#f97316', bg: 'rgba(249,115,22,0.12)' },
    ods: { label: 'XLS', color: '#22c55e', bg: 'rgba(34,197,94,0.12)' },
  };
  return (
    map[ext] ?? {
      label: ext.toUpperCase() || 'FILE',
      color: 'var(--text-faint)',
      bg: 'var(--surface-muted)',
    }
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Parse embedded document content from message body so the UI shows
 * coloured chips instead of raw injection text.  Handles three formats:
 *   1. Client-side preview:  [File: name]\n```\n...\n```
 *   2. Binary/scanned placeholder: [name: binary file, ...] / [name: scanned PDF ...]
 *   3. Server-side parsed:   --- Document: name ---\n...\n--- End of name ---
 *
 * The LLM still receives the full content; only the display is cleaned.
 */
const FILE_BLOCK_RES = [
  /\[File: ([^\]]+)\]\n```\n[\s\S]*?\n```/g,
  /\[([^\]:]+):\s*(?:binary file|scanned PDF)[^\]]*\]/g,
  /--- Document: ([^\n]+) ---\n[\s\S]*?\n--- End of \1 ---/g,
  /--- ([^\n]+) ---\n[\s\S]*?\n--- End of \1 ---/g, // legacy: client-side inject before fix
  /\[Uploaded: ([^\]]+?)\s+[—\-]\s+use\s+pdf_read[^\]]*\]/g, // backend fallback when parse returns empty
];

interface FileChip {
  name: string;
  category: ReturnType<typeof getDocCategory>;
}

function extractFileChips(content: string): { cleanContent: string; chips: FileChip[] } {
  const chips: FileChip[] = [];
  let clean = content;
  for (const re of FILE_BLOCK_RES) {
    clean = clean.replace(re, (_full: string, name: string) => {
      if (!chips.some((c) => c.name === name)) {
        chips.push({ name, category: getDocCategory(name) });
      }
      return '';
    });
  }
  return { cleanContent: clean.trim(), chips };
}

interface Message {
  role: 'user' | 'assistant' | 'progress' | 'error' | 'subagent';
  content: string;
  attachments?: Attachment[];
  toolHint?: boolean;
  toolCallId?: string;
  /** Tool name for specialized rendering (e.g. 'paper_search') */
  toolName?: string;
  /** Parsed tool data for card rendering */
  toolData?: unknown;
  /** Original tool-call arguments (e.g. web_fetch's url) — real references */
  toolArgs?: unknown;
  action?: 'open-provider-settings';
  actionLabel?: string;
  /** When true the message is collapsed by default (user can click to expand) */
  collapsed?: boolean;
  /** Short label shown when collapsed (e.g. "exec" or "write_file → /path/to/file") */
  summary?: string;
  /** True when this row is a restored tool result (its content is the raw
   *  tool OUTPUT, not a live hint line). Rendered with a terminal-style
   *  expandable box instead of activity parsing. */
  toolOutput?: boolean;
  /** Model chain-of-thought (DeepSeek-R1 / Kimi thinking models). Rendered as
   *  a collapsible thinking block above the message content. Issue #539. */
  reasoning?: string;
  /** Marks the live reasoning bubble during streaming so it can be replaced
   *  by the final assistant message once the turn completes. Issue #539. */
  isLiveReasoning?: boolean;
  /** Seconds elapsed from send to final for the "用时 X 秒" label. */
  reasoningElapsedS?: number;
  timestamp: number;
}

interface MessageSource {
  tool: string;
  url: string;
}

const TOOL_LABELS: Record<string, string> = {
  web_fetch: '网页抓取',
  web_search: '网页搜索',
  paper_search: '论文搜索',
  paper_get: '论文详情',
  create_docx: '创建 Word 文档',
  create_xlsx: '创建 Excel 表格',
  create_pptx: '创建 PPT',
  create_pdf: '创建 PDF',
  docx_write: '编辑 Word 文档',
  xlsx_write: '编辑 Excel 表格',
  pptx_write: '编辑 PPT',
  pdf_write: '编辑 PDF',
  edit_docx: '编辑 Word 文档',
  append_xlsx: '追加 Excel 数据',
  exec: '执行命令',
  read_file: '读取文件',
  write_file: '写入文件',
  edit_file: '编辑文件',
  delete_file: '删除文件',
  apply_patch: '应用补丁',
  paper_download: '下载论文',
  skill_manage: '管理技能',
};

/** Hostname (no www.) for a URL — used for the favicon + primary label. */
function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

/** Extract reference URLs from a tool/progress message.
 *  Priority: the URL the tool actually touched (toolArgs) > structured
 *  paper_search cards > links found in result text (fallback). */
function extractMessageSources(msg: Message): MessageSource[] {
  const sources: MessageSource[] = [];
  const skip = [
    'api.semanticscholar.org',
    '/graph/v1/',
    'developer.mozilla.org/en-US/docs/Web/HTTP',
    // Search-engine invocation / redirect URLs (the tool's own query, not a result page)
    'bing.com/search',
    'duckduckgo.com/?q=',
    'duckduckgo.com/html',
    'search.brave.com',
    'google.com/search',
    'so.com/s?q=',      // 360 搜索调用
    'so.com/link?',     // 360 搜索结果跳转链接
    'sogou.com/web?query=',
    'user.guancha.cn/main/search',
    'beian.miit.gov.cn',
    // RSS 聚合噪音：命名空间、图片 CDN、Google News 转发链（base64 文章 ID）
    'purl.org',
    'www.w3.org/2005/Atom',
    'www.w3.org/2000/svg',
    'search.yahoo.com/mrss',
    'lh3.googleusercontent.com',
    'ichef.bbci.co.uk',
    's.rfi.fr/media',
    'news.google.com',          // 聚合页 + 转发链，无直接文章
    'rsshub.app',               // RSSHub 聚合源
    'feeds.',                   // feeds.bbci.co.uk 等 RSS 源域名
    'www.81.cn',                // 军网栏目页（被抓的聚合列表）
  ];
  // 图片/静态资源 + RSS 文件（*.xml / /rss）不是文章来源。纯域名首页保留
  // ——用户要求工具行能看到具体 URL（#539 反馈）。
  const noiseRe = /\.(jpe?g|png|gif|webp|svg|ico|css|js|xml)([?#]|$)/i;
  const rssPathRe = /\/rss[?/]|\.rss([?#]|$)/i;
  const isNoise = (u: string) =>
    noiseRe.test(u) || rssPathRe.test(u) || skip.some((s) => u.includes(s));
  const clean = (raw: string): string =>
    raw.split('{')[0].replace(/[.,;:!?。，；：、）\]]+$/, '');
  // Deduplicate across all branches + cap: duplicate URLs produce duplicate
  // React keys and one checkUrl request each (CodeRabbit #564 review).
  const seen = new Set<string>();
  const push = (tool: string, url: string) => {
    if (!url || seen.has(url) || sources.length >= 20) return;
    if (isNoise(url)) return;
    seen.add(url);
    sources.push({ tool, url });
  };

  // 1. The exact URL the tool fetched/searched — most trustworthy.
  //    toolArgs may be a single object or an array (merged tool-result group).
  const argsList = Array.isArray(msg.toolArgs) ? msg.toolArgs : [msg.toolArgs];
  for (const argsRaw of argsList) {
    if (!argsRaw || typeof argsRaw !== 'object') continue;
    const args = argsRaw as Record<string, unknown>;
    for (const key of ['url', 'link', 'href', 'query']) {
      const v = args[key];
      if (typeof v === 'string' && /^https?:\/\//i.test(v) && !skip.some((s) => v.includes(s))) {
        push(msg.toolName || 'tool', clean(v));
      }
    }
  }

  // 2. paper_search card data.
  if (msg.toolName === 'paper_search' && msg.toolData) {
    const items = (msg.toolData as { items?: { url?: string; arxiv_id?: string }[] }).items ?? [];
    for (const it of items) {
      const url = it.url || (it.arxiv_id ? `https://arxiv.org/abs/${it.arxiv_id}` : '');
      if (url) push('paper_search', clean(url));
    }
    return sources;
  }
  if (msg.toolName === 'paper_search') return sources; // failed search: no refs

  // 3. Fallback: links inside the result text (deduped, noise filtered).
  const content = String(msg.content ?? '');
  for (const m of content.matchAll(/https?:\/\/[^\s"'<>)\]]+/g)) {
    push(msg.toolName || 'tool', clean(m[0]));
  }
  return sources;
}

/** Parse web_search output ("N. title\n   url\n   body") into structured
 *  result cards for the chain row (deep-search style). */
interface WebSearchItem {
  title: string;
  url: string;
  snippet?: string;
}

function parseWebSearchResults(content: string): WebSearchItem[] {
  const items: WebSearchItem[] = [];
  const entryRe = /^\d+\.\s+(.+)$/gm;
  let m: RegExpExecArray | null;
  while ((m = entryRe.exec(content)) !== null) {
    const title = m[1].trim();
    const rest = content.slice(m.index + m[0].length).split(/\n(?=\d+\.\s)/)[0];
    const lines = rest
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean);
    const url = lines.find((l) => /^https?:\/\//i.test(l)) ?? '';
    const snippet = lines.find((l) => !/^https?:\/\//i.test(l)) ?? '';
    if (title && url) items.push({ title, url, snippet });
  }
  return items;
}

function isMissingProviderConfigMessage(message: string) {
  const normalized = message.toLowerCase();
  return normalized.includes('no api key configured');
}

function isProviderConfigurationProblem(message: string, code?: string) {
  if (code === 'NO_API_KEY') return true;
  const normalized = message.toLowerCase();
  return (
    isMissingProviderConfigMessage(message) ||
    normalized.includes('模型服务认证失败') ||
    normalized.includes('authentication') ||
    normalized.includes('invalid api key') ||
    normalized.includes('api key') ||
    normalized.includes('api base') ||
    normalized.includes('当前模型配置')
  );
}

function createProviderConfigMessage(content?: string): Message {
  return {
    role: 'error',
    content: content || '尚未配置模型服务。请先配置 Provider/API Key 后再发送消息。',
    action: 'open-provider-settings',
    actionLabel: '去配置模型',
    timestamp: Date.now(),
  };
}

/* ─── Tracked file from tool hints ───────────────────────────────── */
interface TrackedFile {
  path: string;
  name: string;
  op: 'read' | 'write' | 'edit' | 'delete';
  /** epoch ms of last operation */
  lastSeen: number;
  /** path was truncated in the progress message (ends with ...) */
  truncated?: boolean;
}

const OFFICE_FILE_RE = /\.(docx|xlsx|pptx|ppt|xls|doc|odt|odp|ods)$/i;
const PDF_FILE_RE = /\.pdf$/i;
const TEXT_SUFFIXES_RE =
  /\.(md|markdown|mdown|txt|text|csv|json|yaml|yml|xml|log|env|sql|ini|toml|htaccess|sh|bash|rtf)$/i;
const OFFICE_FILE_RE_LEGACY = /\.(docx|xlsx|pptx|ppt)$/i;

/** Extract text from a PDF buffer by parsing BT/ET text blocks.
 *  Fast client-side extraction — handles text-based PDFs (not scanned). */
function extractPdfText(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer),
    limit = Math.min(bytes.length, 2_000_000);
  let raw = '';
  for (let i = 0; i < limit; i++) raw += String.fromCharCode(bytes[i]);
  const results: string[] = [];
  let pos = 0;
  while (pos < raw.length) {
    const bt = raw.indexOf('BT', pos);
    if (bt === -1) break;
    const et = raw.indexOf('ET', bt + 2);
    if (et === -1) break;
    const block = raw.slice(bt + 2, et);
    for (const m of block.matchAll(/\(([^)]*)\)\s*Tj/g)) if (m[1].trim()) results.push(m[1]);
    for (const m of block.matchAll(/\[([^\]]*)\]\s*TJ/g))
      for (const im of m[1].matchAll(/\(([^)]*)\)/g)) if (im[1].trim()) results.push(im[1]);
    pos = et + 2;
  }
  return results.join(' ') || '';
}

function getMimeTypeFromName(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase();
  const mimeMap: Record<string, string> = {
    pdf: 'application/pdf',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    doc: 'application/msword',
    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    ppt: 'application/vnd.ms-powerpoint',
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    xls: 'application/vnd.ms-excel',
    odt: 'application/vnd.oasis.opendocument.text',
    odp: 'application/vnd.oasis.opendocument.presentation',
    ods: 'application/vnd.oasis.opendocument.spreadsheet',
  };
  return ext ? mimeMap[ext] || 'application/octet-stream' : 'application/octet-stream';
}

function getDocIcon(name: string) {
  const ext = name.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'pdf':
      return FileText;
    case 'xlsx':
    case 'xls':
    case 'csv':
    case 'ods':
      return FileSpreadsheet;
    case 'pptx':
    case 'ppt':
    case 'odp':
      return FileBarChart;
    default:
      return FileType;
  }
}

function relativeTimeLabel(timestamp?: number | string | null, now = Date.now()): string {
  if (timestamp === undefined || timestamp === null) return '尚未更新';
  const value = typeof timestamp === 'number' ? timestamp : Date.parse(timestamp);
  if (!Number.isFinite(value)) return '尚未更新';
  const diff = now - value;
  // For < 2 days, delegate to the shared relative formatter + "更新" suffix
  if (diff < 2 * 86_400_000) {
    return `${formatRelativeTime(timestamp, { suffix: '更新', now })}`;
  }
  // For older entries, keep the "X天前更新" format
  return `${Math.floor(diff / 86_400_000)} 天前更新`;
}

export function buildTaskHeaderMeta(
  updatedAt: number | string | null | undefined,
  fileCount: number,
  activePluginCount: number,
  now = Date.now()
): string {
  const fileLabel = `${fileCount} 个文件`;
  const pluginLabel = `${activePluginCount} 个启用插件`;
  return `${relativeTimeLabel(updatedAt, now)} · ${fileLabel} · ${pluginLabel}`;
}

export function buildTaskShareText({
  title,
  meta,
  messages,
  files,
}: {
  title: string;
  meta: string;
  messages: Message[];
  files: TrackedFile[];
}): string {
  const visibleMessages = messages
    .filter((message) => message.role === 'user' || message.role === 'assistant')
    .slice(-8);
  const messageLines =
    visibleMessages.length > 0
      ? visibleMessages.map((message) => {
          const role = message.role === 'user' ? '用户' : 'MiQi';
          const content = message.content.trim().replace(/\s+/g, ' ');
          return `- ${role}: ${content || '(空消息)'}`;
        })
      : ['- 暂无对话内容'];
  const fileLines =
    files.length > 0 ? files.map((file) => `- ${file.name} (${file.op})`) : ['- 暂无文件'];

  return [
    `# ${title}`,
    '',
    meta,
    '',
    '## 最近对话',
    ...messageLines,
    '',
    '## 相关文件',
    ...fileLines,
  ].join('\n');
}

export function buildTaskReproContext({
  sessionKey,
  title,
  meta,
  messages,
  files,
}: {
  sessionKey: string;
  title: string;
  meta: string;
  messages: Message[];
  files: TrackedFile[];
}): string {
  const visibleMessages = messages
    .filter((message) => message.role === 'user' || message.role === 'assistant')
    .slice(-12);
  const messageLines =
    visibleMessages.length > 0
      ? visibleMessages.map((message) => {
          const role = message.role === 'user' ? '用户' : 'MiQi';
          const content = message.content.trim().replace(/\s+/g, ' ');
          return `- ${role}: ${content || '(空消息)'}`;
        })
      : ['- 暂无对话内容'];
  const fileLines =
    files.length > 0
      ? files.map((file) => `- [${file.op}] ${file.path || file.name}`)
      : ['- 暂无文件'];

  return [
    '# MiQi 任务复现上下文',
    '',
    `- 会话: ${sessionKey}`,
    `- 标题: ${title}`,
    `- 状态: ${meta}`,
    '',
    '## 最近对话',
    ...messageLines,
    '',
    '## 相关文件',
    ...fileLines,
  ].join('\n');
}

export function getTaskShareDownloadName(title: string, timestamp = Date.now()): string {
  const safeTitle =
    title
      .trim()
      .replace(/[\\/:*?"<>|\u0000-\u001f]+/g, '-')
      .replace(/\s+/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 48) || 'miqi-task';
  const stamp = new Date(timestamp).toISOString().replace(/[:.]/g, '-');
  return `${safeTitle}-${stamp}.md`;
}

/**
 * Extract the thread rows from a `threads.list` result, defensively, so the
 * resume path tolerates either backend page shape. The backend `Page.to_dict()`
 * (thread_protocol.py:94) envelopes rows under `data`; the legacy TS
 * `ThreadListResult` type declared them under `items`. Read both so a
 * field-name mismatch between the running backend and this helper can't
 * silently empty the list and force every session to mint a fresh thread.
 *
 * Pure + exported so the whole `threads.list → extractThreadListRows →
 * pickThreadToResume` wiring is unit-tested with backend-shaped payloads
 * without mounting the React component (see chatConsoleThreadResume.test.ts).
 */
export function extractThreadListRows(listResult: unknown): unknown[] {
  if (Array.isArray(listResult)) return listResult;
  const obj = listResult as Record<string, unknown> | null | undefined;
  const rows = obj?.data ?? obj?.items;
  return Array.isArray(rows) ? rows : [];
}

/**
 * Pick the best non-archived, non-ephemeral stored thread id from a
 * `thread/list` result, for resuming an existing conversation when
 * (re)entering a session (Issue #490).
 *
 * Selection rule (chosen over a plain most-recent sort to survive legacy
 * fragmented sessions): prefer the thread holding the MOST persisted turns
 * (`turnCount`, surfaced by backend `_thread_list`), ties broken by the
 * largest `updatedAt` (fallback `createdAt`). Rationale — a fragmented
 * session has several thread_ids; the most-recently-touched one may be
 * nearly empty (e.g. a thread that only captured the user repeatedly
 * asking "what did we do before"), while the thread with the most turns
 * holds the real conversation the user expects to recall. On a clean
 * single-thread session both heuristics agree. Returns `null` when there
 * is no resumable thread. `items` are the loose rows from the
 * `ThreadView.to_dict` camelCase shape: `id`, `turnCount`, `updatedAt`,
 * `createdAt`, `archived`, `ephemeral`.
 *
 * Pure + exported so the resume-selection rule is unit-tested without
 * mounting the React component. The load `useEffect` calls this on the
 * `threads.list` result and stores the returned id in
 * `currentThreadIdRef` so subsequent `chat.send` reuses it instead of
 * minting a fresh thread_id that would orphan prior history.
 */
export function pickThreadToResume(items: unknown): string | null {
  const rows = (Array.isArray(items) ? items : []) as Array<Record<string, unknown>>;
  const candidates = rows
    .filter(
      (t) =>
        !!t &&
        !t.archived &&
        !t.ephemeral &&
        typeof t.id === 'string' &&
        (t.id as string).length > 0
    )
    .map((t) => ({
      id: t.id as string,
      turns: Number(t.turnCount ?? 0) || 0,
      ts: Number(t.updatedAt ?? t.createdAt ?? 0) || 0,
    }))
    .sort((a, b) => b.turns - a.turns || b.ts - a.ts);
  return candidates.length > 0 ? candidates[0].id : null;
}

/** Extract file path + operation from a tool-hint progress text.
 *  Nanobot tool hints look like:
 *    "Read: /abs/path/to/file.ts"
 *    "Write: src/components/Foo.tsx"
 *    "Edit: README.md"
 *    "Delete: tmp/foo.log"
 *    "Reading file src/foo.ts …"
 *    "Writing file /path/to/bar.py"
 */
function parseToolHint(
  text: string
): { path: string; op: TrackedFile['op']; truncated: boolean } | null {
  const patterns: Array<[RegExp, TrackedFile['op']]> = [
    // "Read: /abs/path/to/file.ts"  or  "Reading file src/foo.ts …"
    [/^(?:Read|Reading(?:\s+file)?)[:\s]+(.+?)(?:\s*….*)?$/i, 'read'],
    [/^(?:Write|Writing(?:\s+file)?)[:\s]+(.+?)(?:\s*….*)?$/i, 'write'],
    [/^(?:Edit|Editing(?:\s+file)?)[:\s]+(.+?)(?:\s*….*)?$/i, 'edit'],
    [/^(?:Delete|Deleting(?:\s+file)?)[:\s]+(.+?)(?:\s*….*)?$/i, 'delete'],
    // nanobot / miqi style: write_file("path"), read_file("path"), edit_file("path")
    [/(?:write|edit|delete|read)_file\s*\(\s*["'](.+?)["']\s*\)/i, 'write'],
    // Office creation tools create files in the workspace.
    [
      /(?:create_docx|create_xlsx|create_pptx|create_pdf|pdf_write|docx_write|xlsx_write|pptx_write)\s*\(\s*["'](.+?)["']\s*\)/i,
      'write',
    ],
    [/(?:edit_docx|append_xlsx)\s*\(\s*["'](.+?)["']\s*\)/i, 'edit'],
    // Office tool success: "Created: file.xlsx (3 sheet(s))"
    [/^(?:Created|Appended):\s+(.+?\.\w{1,6})(?:\s*\(.*\))?$/i, 'write'],
    // Generic fallback: only match clear file-path patterns like
    // "Saved to: file.pdf", "Output: path/to/file.pdf" or "Downloading: file.pdf"
    // where the prefix is a known verb and the path has a directory separator or
    // a known extension.  This avoids false positives from arbitrary curl output.
    [
      /(?:Saving|Saved|Writing|Written|Downloading|Downloaded|Output|Result)(?:\s+to)?[:\s]\s*(.+?\.[a-zA-Z]{1,6})/i,
      'write',
    ],
    // Also match the natural language "file/path: something.ext"
    [/(?:file|path)[:\s]+((?:\S+\/)?\S+\.[a-zA-Z]{1,6})/i, 'read'],
  ];
  for (const [re, op] of patterns) {
    const m = text.match(re);
    if (m) {
      let raw = m[1].trim().replace(/['"]/g, '');
      // Detect truncation (ends with ...)
      const truncated = raw.endsWith('...') || raw.endsWith('…');
      // Strip trailing ellipsis / quotes
      raw = raw
        .replace(/\.{3,}$/g, '')
        .replace(/…$/g, '')
        .trim();
      // Must look like a file path (contains '/' or '\' or has extension)
      if (raw && /[/\\.]/.test(raw)) {
        // For the _file() pattern, try to infer a more specific op from the verb
        let inferredOp = op;
        if (re.source.includes('write')) inferredOp = 'write';
        else if (re.source.includes('edit')) inferredOp = 'edit';
        else if (re.source.includes('delete')) inferredOp = 'delete';
        else if (re.source.includes('read')) inferredOp = 'read';
        else if (re.source.includes('create_') || re.source.includes('_write'))
          inferredOp = 'write';
        return { path: raw, op: inferredOp, truncated };
      }
    }
  }
  return null;
}

function basename(path: string): string {
  return path.replace(/\\/g, '/').split('/').pop() ?? path;
}

/** Normalise a sandbox-internal path to a workspace-relative path.
 *  Strips /home/miqi/workspace/ prefix so the path resolves correctly on the
 *  host filesystem.  Leaves relative paths and non-sandbox absolute paths
 *  unchanged — the IPC handlers resolve them against the workspace root. */
function normalizeSandboxPath(p: string): string {
  if (p === '/home/miqi/workspace') return '.';
  if (p.startsWith('/home/miqi/workspace/')) return p.slice('/home/miqi/workspace/'.length);
  return p;
}

const DEFAULT_SESSION = 'desktop:default';

function messageContentToString(content: unknown): string {
  return typeof content === 'string' ? content : JSON.stringify(content);
}

interface ToolActivity {
  name: string;
  duration?: string;
}

function toolDisplayName(name: string): string {
  return TOOL_LABELS[name] ?? name;
}

/** Per-tool emoji for the chain icons — colorful, tool-call style (社区标准
 *  🔧 表示工具，⚡ 强调执行；文件/文档/网络类用对应物象 emoji）。 */
const TOOL_ICON_EMOJI: Record<string, string> = {
  exec: '⚡',
  read_file: '📄',
  list_dir: '📂',
  write_file: '✍️',
  edit_file: '✍️',
  delete_file: '🗑️',
  apply_patch: '🔧',
  create_docx: '📝',
  docx_write: '📝',
  create_xlsx: '📊',
  xlsx_write: '📊',
  create_pptx: '📽️',
  pptx_write: '📽️',
  create_pdf: '📕',
  pdf_write: '📕',
  web_search: '🔍',
  web_fetch: '🌐',
  paper_search: '🔍',
  paper_get: '📑',
  paper_download: '📥',
  cron: '⏰',
  memory: '💾',
  message: '💬',
  session_search: '🔎',
  skill_manage: '🧰',
  spawn: '👥',
  task_begin: '🚩',
  task_end: '🏁',
  trace_search: '🧭',
};

function toolIconEmoji(name: string): string {
  if (TOOL_ICON_EMOJI[name]) return TOOL_ICON_EMOJI[name];
  // MCP 网关工具（mcp__xxx__yyy）统一用插头图标。
  if (name.startsWith('mcp') || name.includes('gateway')) return '🔌';
  return '🔧';
}

function formatToolDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

function parseToolDuration(duration?: string): number {
  const m = duration?.match(/^(\d+(?:\.\d+)?)(ms|s)$/);
  if (!m) return 0;
  return m[2] === 's' ? Number(m[1]) * 1000 : Number(m[1]);
}

function parseToolActivity(content: string): ToolActivity[] {
  return content
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const name = line.match(/^[A-Za-z_][\w.-]*/)?.[0] ?? line.slice(0, 28);
      const ms = line.match(/\((\d+)\s*ms\)/i)?.[1];
      const sec = line.match(/\((\d+(?:\.\d+)?)\s*s\)/i)?.[1];
      return {
        name,
        duration: ms
          ? formatToolDuration(Number(ms))
          : sec
            ? `${sec}s`
            : undefined,
      };
    });
}

/** One line per unique tool, keeping the LATEST duration seen for each
 *  (a later occurrence overwrites an earlier one; a missing duration
 *  keeps any earlier value rather than erasing it). */
function groupToolActivities(activities: ToolActivity[]): ToolActivity[] {
  const byName = new Map<string, string | undefined>();
  for (const act of activities) {
    if (!act.name) continue;
    if (act.duration) byName.set(act.name, act.duration);
    else if (!byName.has(act.name)) byName.set(act.name, undefined);
  }
  return [...byName.entries()].map(([name, duration]) => ({
    name,
    duration,
  }));
}

function summarizeToolActivities(activities: ToolActivity[], fallback?: string): string {
  const calls = activities.filter((a) => a.duration);
  const totalMs = calls.reduce((sum, a) => sum + parseToolDuration(a.duration), 0);
  const suffix = totalMs > 0 ? ` · ${formatToolDuration(totalMs)}` : '';
  if (calls.length === 1) return `${toolDisplayName(calls[0].name)}${suffix}`;
  if (calls.length > 1) return `已完成 ${calls.length} 项工具调用${suffix}`;
  return fallback || '工具调用';
}

/** Extract the call's concrete target (exec command, file path) from tool
 *  args so the chain row reads "执行命令 · python x.py" instead of just the
 *  tool name. Values follow HINT_VALUE_KEYS; long ones are truncated. */
function toolCallDetail(args: unknown): string | undefined {
  const list = Array.isArray(args) ? args : args !== undefined ? [args] : [];
  for (const item of list) {
    if (!item || typeof item !== 'object') continue;
    const obj = item as Record<string, unknown>;
    for (const key of HINT_VALUE_KEYS) {
      const v = obj[key];
      if (typeof v === 'string' && v.trim()) {
        return v.length > 60 ? `${v.slice(0, 60)}…` : v;
      }
    }
  }
  return undefined;
}

/** Tool-chain row label: tool name · concrete target · duration. */
function toolChainLabel(
  activities: ToolActivity[],
  args: unknown,
  fallback?: string,
): string {
  const detail = toolCallDetail(args);
  if (activities.length === 1) {
    const act = activities[0];
    return `${toolDisplayName(act.name)}${detail ? ` · ${detail}` : ''}${
      act.duration ? ` · ${act.duration}` : ''
    }`;
  }
  return `${summarizeToolActivities(activities, fallback)}${detail ? ` · ${detail}` : ''}`;
}

function isAssistantTextMessage(msg: any): boolean {
  // Reasoning-only assistant turns (thinking models may emit
  // reasoning_content with empty content) must still count as text so the
  // collapse logic keeps cross-turn reasoning merges intact (#539).
  const visible = msg?.content ?? msg?.reasoning_content ?? '';
  return msg?.role === 'assistant' && String(visible).trim().length > 0;
}

/**
 * An assistant message that IS tool-related (its content is about tool calls,
 * or it carries tool_calls). We keep it separate from true *text* so the
 * collapse logic can strip intermediate tool-only assistant records.
 */
function isAssistantToolCallMessage(msg: any): boolean {
  return msg?.role === 'assistant' && Array.isArray(msg.tool_calls) && msg.tool_calls.length > 0;
}

/** Merge reasoning segments without duplicating chunks already present. */
function mergeReasoningParts(parts: string[]): string {
  const seen = new Set<string>();
  const merged: string[] = [];
  for (const part of parts) {
    for (const chunk of String(part).split('\n\n---\n\n')) {
      const trimmed = chunk.trim();
      if (!trimmed || seen.has(trimmed)) continue;
      seen.add(trimmed);
      merged.push(trimmed);
    }
  }
  return merged.join('\n\n---\n\n');
}

function collapseAssistantMessagesWithinTurns(rawMsgs: any[]): any[] {
  const result: any[] = [];
  let turnBuffer: any[] = [];

  const flushTurn = () => {
    if (turnBuffer.length === 0) return;

    const lastAssistantTextIndex = (() => {
      for (let i = turnBuffer.length - 1; i >= 0; i -= 1) {
        if (isAssistantTextMessage(turnBuffer[i])) return i;
      }
      return -1;
    })();

    // Reasoning is rendered as a standalone timeline block BEFORE the tool
    // calls, so the final answer never reorders it above the tools. #539
    const reasoningParts: string[] = [];
    let firstReasoningTs: number | null = null;
    const emitted: any[] = [];

    turnBuffer.forEach((msg, index) => {
      if (msg.role === 'assistant' && msg.reasoning_content) {
        reasoningParts.push(String(msg.reasoning_content));
        if (firstReasoningTs === null) firstReasoningTs = msg.timestamp ?? null;
      }
      if (
        isAssistantTextMessage(msg) &&
        isAssistantToolCallMessage(msg) &&
        index !== lastAssistantTextIndex
      ) {
        emitted.push({ ...msg, content: '', reasoning_content: undefined });
        return;
      }
      if (isAssistantTextMessage(msg) && index !== lastAssistantTextIndex) {
        return;
      }
      if (msg.role === 'assistant' && msg.reasoning_content) {
        const { reasoning_content, ...rest } = msg;
        emitted.push(rest);
        return;
      }
      emitted.push(msg);
    });

    if (reasoningParts.length > 0) {
      result.push({
        role: 'progress',
        content: mergeReasoningParts(reasoningParts),
        reasoning: mergeReasoningParts(reasoningParts),
        timestamp: firstReasoningTs ?? Date.now(),
      });
    }
    result.push(...emitted);

    turnBuffer = [];
  };

  for (const msg of rawMsgs) {
    if (msg?.role === 'user') {
      flushTurn();
      result.push(msg);
      continue;
    }
    turnBuffer.push(msg);
  }
  flushTurn();

  return result;
}

/** Arg keys whose value is the call's target and safe to show in a hint
 *  (file paths, the exec command). Other args only get their name shown —
 *  values like paper titles or URLs are long strings that would leak
 *  into the hint instead of a concise call summary (issue #532). */
const HINT_VALUE_KEYS = ['path', 'file_path', 'filename', 'outPath', 'command', 'url', 'query'];

export function sessionMsgsToUi(rawMsgs: any[]): Message[] {
  const result: Message[] = [];
  for (const m of collapseAssistantMessagesWithinTurns(rawMsgs)) {
    const ts = m.timestamp ? new Date(m.timestamp).getTime() : Date.now();

    if (m.role === 'progress') {
      result.push({
        role: 'progress',
        content: String(m.content ?? ''),
        reasoning: m.reasoning ? String(m.reasoning) : undefined,
        reasoningElapsedS: m.reasoningElapsedS,
        timestamp: ts,
      });
      continue;
    }

    if (m.role === 'user' || m.role === 'assistant') {
      // Skip assistant messages that have no text content (only tool_calls).
      // Reasoning-only assistant turns (thinking models that emit no reply
      // text) still render a folded thinking block, so admit them too. #539.
      // Note: the old per-tool-call hint row is gone — restored tool results
      // (role 'tool', below) already carry the full "执行命令 · cp …" label,
      // so emitting both made every tool appear twice (#539 用户要求).
      const reasoningContent =
        typeof m.reasoning_content === 'string' && m.reasoning_content.trim().length > 0
          ? m.reasoning_content
          : undefined;
      const hasContent = m.content && String(m.content).trim().length > 0;
      if (m.role === 'user' || hasContent || reasoningContent) {
        result.push({
          role: m.role as 'user' | 'assistant',
          content: messageContentToString(m.content),
          reasoning: reasoningContent,
          timestamp: ts,
        });
      }
    } else if (m.role === 'subagent') {
      // Subagent result messages — render with the subagent style
      result.push({
        role: 'subagent',
        content: messageContentToString(m.content),
        timestamp: ts,
      });
    } else if (m.role === 'tool') {
      // Tool result messages → show as collapsed progress with toolHint
      const toolName = m.name || 'tool';
      const content = typeof m.content === 'string' ? m.content : JSON.stringify(m.content);
      const toolArgs = (m as { arguments?: unknown }).arguments;

      // Detect paper_search results → render as cards (not collapsed)
      if (toolName === 'paper_search') {
        const paperData = tryParsePaperSearchResult(content);
        if (paperData && paperData.items?.length) {
          result.push({
            role: 'progress',
            content: content,
            summary: `📄 Found ${paperData.items.length} papers${paperData.query ? ` for "${paperData.query}"` : ''}`,
            toolHint: true,
            toolName: 'paper_search',
            toolData: paperData,
            collapsed: false,
            timestamp: ts,
          });
        } else {
          // Search returned empty or errored — still show normally
          const preview = content.length > 120 ? content.slice(0, 120) + '…' : content;
          result.push({
            role: 'progress',
            content: `paper_search: ${preview}`,
            summary: 'paper_search',
            toolHint: true,
            collapsed: true,
            timestamp: ts,
          });
        }
      } else {
        // Restored tool result: keep the full output for inspection, but the
        // collapsed row must read like the live chain ("执行命令 · cp …"),
        // never parse the OUTPUT text as activity lines (#539 恢复视图).
        const detail = toolCallDetail(toolArgs);
        result.push({
          role: 'progress',
          content: content,
          summary: `${toolDisplayName(toolName)}${detail ? ` · ${detail}` : ''}`,
          toolHint: true,
          toolArgs,
          toolName,
          toolOutput: true,
          collapsed: true,
          timestamp: ts,
        });
      }
    }
    // Ignore other roles (system, etc.)
  }

  // Merge consecutive collapsed progress messages into a single group
  const merged: Message[] = [];
  for (const msg of result) {
    // Restored tool-output rows must stay individual chain steps (each has its
    // own step number + command detail) — never merge them into one blob.
    const merges = !msg.toolOutput;
    if (
      merges &&
      msg.collapsed &&
      merged.length > 0 &&
      !merged[merged.length - 1].toolOutput &&
      merged[merged.length - 1].collapsed
    ) {
      const prev = merged[merged.length - 1];
      // Append content and summary
      prev.content += '\n' + msg.content;
      prev.summary = prev.summary!.includes(',')
        ? prev.summary // already a group, keep it
        : `${prev.summary}, ${msg.summary}`; // merge two single items
      // Use the later timestamp
      prev.timestamp = msg.timestamp;
      // A group containing raw tool output must keep the terminal-style
      // expandable rendering (#539 恢复视图).
      if (msg.toolOutput) prev.toolOutput = true;
      // Keep every tool call's arguments in the group — "查看来源" needs the
      // exact URL each web_fetch/web_search actually touched, not just the first.
      const prevArgs = Array.isArray(prev.toolArgs)
        ? prev.toolArgs
        : prev.toolArgs !== undefined
          ? [prev.toolArgs]
          : [];
      if (msg.toolArgs !== undefined) prevArgs.push(msg.toolArgs);
      if (prevArgs.length > 0) prev.toolArgs = prevArgs;
    } else {
      merged.push({ ...msg });
    }
  }

  // When a group has multiple items, rewrite summary to show a Chinese count
  // (live rows carry details like "执行命令 · cp …", so keep it short).
  for (const msg of merged) {
    if (msg.collapsed && msg.summary && msg.summary.includes(',')) {
      const names = msg.summary.split(', ').filter(Boolean);
      const unique = [...new Set(names)];
      if (unique.length > 1) {
        const first = unique[0].split(' · ')[0] || unique[0];
        msg.summary = `${unique.length} 项工具调用 · ${first} 等`;
      }
    }
  }

  // Restored thinking blocks have no elapsed time — derive it from the turn
  // span (first reasoning record → last message of the turn) so the header
  // always reads "已深度思考 · X 秒" (#539 用户要求).
  const withElapsed = dedupeReasoningBlocks(merged);
  for (let i = 0; i < withElapsed.length; i += 1) {
    const m = withElapsed[i];
    if (m.role !== 'progress' || !m.reasoning || m.reasoningElapsedS !== undefined) continue;
    let endTs = m.timestamp;
    for (let j = i + 1; j < withElapsed.length; j += 1) {
      if (withElapsed[j].role === 'user') break;
      if (withElapsed[j].timestamp > endTs) endTs = withElapsed[j].timestamp;
    }
    const secs = Math.round((endTs - m.timestamp) / 1000);
    if (secs > 0) m.reasoningElapsedS = secs;
  }
  return withElapsed;
}

function removeTransientTurnMessagesSinceLastUser(messages: Message[]): Message[] {
  const lastUserIndex = (() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === 'user') return i;
    }
    return -1;
  })();

  const cleaned = messages.reduce((acc, message, index) => {
    if (index <= lastUserIndex) {
      acc.push(message);
      return acc;
    }
    if (message.role === 'assistant') return acc;
    if (message.role !== 'progress') {
      acc.push(message);
      return acc;
    }
    // Thinking blocks stay in place; tool rows collapse after the final.
    if (message.reasoning) {
      acc.push(message);
      return acc;
    }
    if (message.toolHint) acc.push(message);
    return acc;
  }, [] as Message[]);

  return dedupeReasoningBlocks(cleaned);
}

type ChatGroup =
  | { kind: 'msg'; msg: Message }
  | { kind: 'chain'; rows: Message[]; done: boolean };

/** Group consecutive tool rows into a single chain so the final rendering can
 *  collapse them into one「工具调用 · N」block (live rows stay expanded while
 *  the turn runs; the group is marked done once a non-tool message follows). */
function groupChatMessages(messages: Message[]): ChatGroup[] {
  const out: ChatGroup[] = [];
  let chain: Message[] | null = null;
  let chainDone = false;
  const flush = () => {
    if (chain) {
      out.push({ kind: 'chain', rows: chain, done: chainDone });
      chain = null;
      chainDone = false;
    }
  };
  for (const m of messages) {
    const isToolRow = m.role === 'progress' && !!m.toolHint;
    if (isToolRow) {
      if (!chain) chain = [];
      chain.push(m);
      continue;
    }
    if (chain) chainDone = true;
    flush();
    out.push({ kind: 'msg', msg: m });
  }
  flush();
  return out;
}

/** Merge adjacent thinking blocks so a turn can never show duplicate headers. */
function dedupeReasoningBlocks(messages: Message[]): Message[] {
  const out: Message[] = [];
  let pending: Message | null = null;
  for (const m of messages) {
    if (m.role === 'progress' && m.reasoning) {
      if (pending) {
        pending.content = `${pending.content}\n${m.content}`;
        pending.reasoning = pending.content;
        pending.reasoningElapsedS = m.reasoningElapsedS ?? pending.reasoningElapsedS;
        pending.timestamp = m.timestamp;
        pending.isLiveReasoning = pending.isLiveReasoning || m.isLiveReasoning;
        continue;
      }
      pending = { ...m };
      out.push(pending);
      continue;
    }
    pending = null;
    out.push(m);
  }
  return out;
}

/** Promote an existing thinking block, or insert one after the user message.
 *  Updating in place guarantees a turn never renders two thinking headers. */
export function insertStandaloneReasoning(
  messages: Message[],
  reasoning: string,
  elapsedSeconds?: number,
): Message[] {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role === 'user') break;
    if (messages[i].role === 'progress' && messages[i].reasoning) {
      const next = [...messages];
      next[i] = {
        ...next[i],
        isLiveReasoning: false,
        content: reasoning,
        reasoning,
        reasoningElapsedS: elapsedSeconds,
      };
      return next;
    }
  }
  const block: Message = {
    role: 'progress',
    content: reasoning,
    reasoning,
    reasoningElapsedS: elapsedSeconds,
    timestamp: Date.now(),
  };
  let insertAt = messages.length;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role === 'user') {
      insertAt = i + 1;
      break;
    }
  }
  return [...messages.slice(0, insertAt), block, ...messages.slice(insertAt)];
}

/** Append a streaming reasoning chunk to the last live thinking bubble. */
export function appendReasoningDelta(
  messages: Message[],
  delta: string,
  ts = Date.now(),
): Message[] {
  let idx = -1;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].isLiveReasoning) {
      idx = i;
      break;
    }
  }
  if (idx >= 0) {
    const next = [...messages];
    const appended = next[idx].content + delta;
    next[idx] = { ...next[idx], content: appended, reasoning: appended };
    return next;
  }
  return [
    ...messages,
    {
      role: 'progress',
      content: delta,
      reasoning: delta,
      isLiveReasoning: true,
      timestamp: ts,
    },
  ];
}

/** File-operation tool names shared between progress-hint parsing and
 *  onFinal tool_call tracking. Keep in sync with the backends that
 *  produce file paths. */
const _FILE_WRITE_TOOLS = [
  'write_file',
  'edit_file',
  'delete_file',
  'apply_patch',
  'create_docx',
  'create_xlsx',
  'create_pptx',
  'create_pdf',
  'pdf_write',
  'docx_write',
  'xlsx_write',
  'pptx_write',
  'edit_docx',
  'append_xlsx',
  'skill_manage',
  'paper_download',
  'exec',
];
const _FILE_READ_TOOLS = ['read_file', 'pdf_read'];

/** Extract a file path from a JSON-stringified tool args object.
 *  Checks common keys: path, file_path, filename, outPath.
 *  For skill_manage, derives the SKILL.md path from the skill name.
 *  For exec, parses the command string for curl -o/-O, wget -O, or > redirect. */
function _extractPathFromArgs(argsStr: string): string | null {
  try {
    const args = JSON.parse(argsStr);

    // skill_manage: derive from name
    if (args.name && (args.action === 'create' || args.action === 'patch')) {
      return `skills/${args.name}/SKILL.md`;
    }

    // Direct path parameters
    const directPath =
      (args.path as string) ||
      (args.file_path as string) ||
      (args.filename as string) ||
      (args.outPath as string) ||
      (args.out_path as string) ||
      (args.output as string);
    if (directPath) return directPath;

    // exec: parse command string for output filenames
    const cmd: string = (args.command as string) || '';
    if (cmd) {
      // Match: -o <file>  (curl/wget explicit output path)
      let m1 = cmd.match(/(?:^|\s)-o\s+(\S+\.\w+)/);
      if (m1) return m1[1].replace(/^["']|["']$/g, '');
      // Match: --output <file>
      m1 = cmd.match(/--output\s+(\S+\.\w+)/);
      if (m1) return m1[1].replace(/^["']|["']$/g, '');
      // Match: -O  (boolean flag — derive filename from last URL basename)
      // Must match O at argument boundary: -O, -LO, -fsSLO, etc.
      if (/(?:^|\s)[a-zA-Z]*O(?:\s+|$)/.test(cmd)) {
        const urls = cmd
          .split(/\s+/)
          .filter((t) => t.startsWith('http://') || t.startsWith('https://'));
        if (urls.length) {
          const name = urls[urls.length - 1].split('/').pop() || '';
          if (name) return name;
        }
      }
      // Match: > <file>  or  >><file>  (shell redirect)
      const m2 = cmd.match(/(?:^|\s)>{1,2}\s*(\S+\.\w+)/);
      if (m2) return m2[1].replace(/^["']|["']$/g, '');
    }

    return null;
  } catch {
    return null;
  }
}

/** Parse tracked files from raw session messages.
 *  Handles three formats:
 *  1. _tool_hint metadata (from progress events, persisted by some backends)
 *  2. tool_calls array on assistant messages (raw provider format)
 *  3. name field on tool result messages (raw provider format)
 */
function extractTrackedFilesFromMessages(rawMsgs: any[]): TrackedFile[] {
  const fileMap = new Map<string, TrackedFile>();
  const rank: Record<TrackedFile['op'], number> = { read: 0, edit: 1, write: 2, delete: 3 };

  const upsert = (path: string, op: TrackedFile['op'], timestamp?: string) => {
    const key = normalizeSandboxPath(path).replace(/\\/g, '/');
    const existing = fileMap.get(key);
    if (!existing || rank[op] > rank[existing.op]) {
      fileMap.set(key, {
        path: key,
        name: basename(key),
        op,
        lastSeen: timestamp ? new Date(timestamp).getTime() : Date.now(),
        truncated: false,
      });
    }
  };

  for (const msg of rawMsgs) {
    // Format 1: _tool_hint metadata (persisted progress events)
    const hintText = msg._tool_hint_text || msg.content;
    if (msg._tool_hint && hintText) {
      const parsed = parseToolHint(hintText);
      if (parsed) {
        upsert(parsed.path, parsed.op, msg.timestamp);
      }
    }

    // Format 2: assistant messages with tool_calls array
    if (Array.isArray(msg.tool_calls)) {
      for (const tc of msg.tool_calls) {
        const fn = tc?.function || tc?.tool?.function || {};
        const toolName: string = fn?.name || '';
        if (!toolName) continue;
        const argsStr: string = fn?.arguments || '{}';
        const filePath = _extractPathFromArgs(argsStr);
        if (!filePath) continue;
        if (_FILE_WRITE_TOOLS.includes(toolName)) {
          upsert(filePath, toolName === 'delete_file' ? 'delete' : 'write', msg.timestamp);
        } else if (_FILE_READ_TOOLS.includes(toolName)) {
          upsert(filePath, 'read', msg.timestamp);
        }
      }
    }

    // Format 3: tool result messages with name field
    if (msg.role === 'tool' && msg.name) {
      const toolName: string = msg.name;
      // Try to extract path from content (often contains the file path)
      const contentPath = parseToolHint(String(msg.content || ''));
      if (contentPath) {
        upsert(contentPath.path, contentPath.op, msg.timestamp);
      } else if (_FILE_WRITE_TOOLS.includes(toolName)) {
        // Tool result without parsable content — try to infer from tool name
        // (best-effort; actual path is in the paired assistant tool_calls message)
      }
    }
  }
  return Array.from(fileMap.values());
}

// ── Cross-session in-flight event cache (#378) ──────────────────
// When the user switches sessions mid-stream, the per-send listeners
// silently bail (data.session_key !== currentSessionRef.current).
// This cache captures those events so the session-load effect can
// replay them when the user switches back, avoiding the permanent
// loss of the assistant reply.
//
// Kept module-level so the caches survive a ChatConsole unmount — App.tsx no
// longer keys the component by sessionKey, but route/layout changes can still
// unmount it, and component-scoped refs would drop the events of a dead
// instance.  Both caches are bounded to a fixed number of sessions so a
// long-lived desktop process visiting many sessions does not accumulate
// unbounded event/message payloads.
interface InFlightEvent {
  type: 'progress' | 'final' | 'error' | 'aborted';
  data: unknown;
  timestamp: number;
}
interface InFlightSnapshot {
  events: InFlightEvent[];
  userMsgTimestamp: number;
}
/** Map that drops the oldest key once it exceeds `maxSize` entries. */
function boundedMap<K, V>(maxSize: number): Map<K, V> {
  const map = new Map<K, V>();
  const originalSet = map.set.bind(map);
  map.set = ((key: K, value: V) => {
    // Call the bound original set, NOT map.set (which is now this wrapper) —
    // otherwise every call recurses into itself until the stack overflows.
    originalSet(key, value);
    if (map.size > maxSize) {
      const oldest = map.keys().next().value;
      if (oldest !== undefined) map.delete(oldest);
    }
    return map;
  }) as typeof originalSet;
  return map;
}
const MODULE_CACHE_MAX_SESSIONS = 20;
const moduleInFlightCache = boundedMap<string, InFlightSnapshot>(MODULE_CACHE_MAX_SESSIONS);

// Per-session snapshot of the last-rendered messages.  While on a session,
// its thinking/reply events take the LIVE path (rendered into `messages`)
// and never enter moduleInFlightCache — so switching away and wiping the
// component state would lose them.  On switch we snapshot the current
// session's messages here so switching back restores them instantly
// (module-level, survives the component staying mounted across switches).
const moduleMessagesSnapshot = boundedMap<string, Message[]>(MODULE_CACHE_MAX_SESSIONS);

// Typewriter reveal state per session.  `revealNext` runs in the handleSend
// closure, whose local vars (fullContent/displayed/animId) would die with the
// closure's RAF chain if we stopped it on switch-away.  Holding the state at
// module level lets the animation pause across a switch (by skipping
// setMessages) and RESUME when the user returns — the reply's remaining text
// keeps revealing instead of freezing mid-typewriter.
interface RevealState {
  fullContent: string;
  displayed: string;
  animId: number | null;
  finalDone: boolean;
}
const revealBySession = boundedMap<string, RevealState>(MODULE_CACHE_MAX_SESSIONS);

// Sessions whose final reply has already been rendered by load() (merged from
// history / cached final).  When such a session's old send listener then
// receives the same final via the live path, it must NOT append a duplicate —
// the reply is already on screen.  Cleared when a new send starts.
const finalHandledSessions = new Set<string>();

// Whether each session currently has a turn in flight (streaming).  Set true
// in handleSend, cleared on final/error/aborted.  The switch-back effect uses
// this as the authoritative "is this session still generating?" signal — the
// heuristic alternatives (cached progress events / snapshot thinking text /
// active typewriter) all miss the early-thinking phase, where the only
// evidence is the indicator itself (snapshot holds just the user bubble).
const streamingBySession = new Set<string>();

/** Convert cached in-flight events into UI messages for immediate display.
 *  Pure — no side effects.  Used to render the thinking/reply synchronously
 *  on session switch so there is no blank-window gap while sessions.get()
 *  resolves.  Exec inline output and doc_progress attachment status are
 *  handled by the load() replay (they update execOutputs/attachments). */
function cachedEventsToMessages(events: InFlightEvent[]): Message[] {
  const out: Message[] = [];
  for (const ev of events) {
    if (ev.type === 'progress') {
      const pd = ev.data as ChatProgress;
      if (pd?.text && !pd?.stream) {
        out.push({
          role: 'progress',
          content: pd.text,
          toolHint: pd?.tool_hint === true,
          toolCallId: pd?.tool_call_id,
          collapsed: pd?.tool_hint === true,
          timestamp: Date.now(),
        });
      }
    } else if (ev.type === 'final') {
      const fd = ev.data as ChatFinal;
      if (fd?.content) {
        out.push({ role: 'assistant', content: fd.content, timestamp: Date.now() });
      }
    } else if (ev.type === 'error') {
      const ed = ev.data as any;
      out.push({ role: 'error', content: ed?.message || 'Unknown error', timestamp: Date.now() });
    } else if (ev.type === 'aborted') {
      out.push({ role: 'progress', content: '已停止。', timestamp: Date.now() });
    }
  }
  return out;
}

/** Split cached events into thinking (progress/error/subagent) vs the final
 *  reply.  Used by load() to merge with history in the correct visual order
 *  (thinking ABOVE the reply). */
function splitCachedMessages(events: InFlightEvent[]): {
  thinking: Message[];
  finalReply: string | null;
} {
  const thinking: Message[] = [];
  let finalReply: string | null = null;
  for (const ev of events) {
    if (ev.type === 'progress') {
      const pd = ev.data as ChatProgress;
      if (pd?.text && !pd?.stream) {
        thinking.push({
          role: 'progress',
          content: pd.text,
          toolHint: pd?.tool_hint === true,
          toolCallId: pd?.tool_call_id,
          collapsed: pd?.tool_hint === true,
          timestamp: Date.now(),
        });
      }
    } else if (ev.type === 'error') {
      const ed = ev.data as any;
      thinking.push({
        role: 'error',
        content: ed?.message || 'Unknown error',
        timestamp: Date.now(),
      });
    } else if (ev.type === 'aborted') {
      thinking.push({ role: 'progress', content: '已停止。', timestamp: Date.now() });
    } else if (ev.type === 'final') {
      const fd = ev.data as ChatFinal;
      if (fd?.content) finalReply = fd.content;
    }
  }
  return { thinking, finalReply };
}

/* ─── Main component ─────────────────────────────────────────────── */
export function ChatConsole({
  sessionKey = DEFAULT_SESSION,
  loadTrigger,
  workspace,
  newSessionTrigger,
  onNewSession,
  pendingWorkspace,
  onChatFinished,
  renameVersion,
  onRename,
  onOpenProviderSettings,
  onOpenApprovals,
  onWorkspaceLoaded,
}: {
  sessionKey?: string;
  /** Increment to force a session history reload (e.g. after bridge becomes ready) */
  loadTrigger?: number;
  /** Current workspace path (shown in the inline selector before conversation starts). */
  workspace?: string | null;
  /** Increment to trigger workspace picker → new session flow */
  newSessionTrigger?: number;
  onNewSession?: (newKey: string, workspace?: string | null) => void;
  pendingWorkspace?: { current: { sessionKey: string; workspace: string } | null };
  onChatFinished?: () => void;
  /** Increment to force a title reload after the session is renamed from
   *  the sidebar, so the active header stays in sync. */
  renameVersion?: number;
  /** Called after a successful header inline rename, so the parent can
   *  refresh the sidebar (which reads titles from the backend). */
  onRename?: () => void;
  onOpenProviderSettings?: () => void;
  onOpenApprovals?: () => void;
  onWorkspaceLoaded?: (workspace: string | null) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  // Tracks the latest messages for the session-switch snapshot.  Kept in
  // sync below; the switch effect snapshots the session we're leaving into
  // moduleMessagesSnapshot so switching back restores it instantly.
  const messagesRef = useRef<Message[]>([]);
  messagesRef.current = messages;
  const [sessionUpdatedAt, setSessionUpdatedAt] = useState<string | null>(null);
  const [customTitle, setCustomTitle] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState(false);
  const [clockTick, setClockTick] = useState(() => Date.now());
  const [input, setInput] = useState('');
  const [executionPolicy, setExecutionPolicy] = useState<ExecutionPolicy>('edit');
  const [streaming, setStreaming] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [downloadingPaperId, setDownloadingPaperId] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [panelWidth, setPanelWidth] = useState(280);
  const panelResizing = useRef(false);
  const [workspacePickerOpen, setWorkspacePickerOpen] = useState(false);
  const [recentWorkspaces, setRecentWorkspaces] = useState<string[]>([]);

  useEffect(() => {
    const timer = window.setInterval(() => setClockTick(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false; // prevent overlapping polls when bridge is slow (#311)
    const loadActivePlugins = async () => {
      if (inFlight) return; // skip if previous request still pending
      try {
        inFlight = true;
        const result = await window.miqi.plugins.list();
        const plugins = (result as unknown as { plugins?: Array<{ status?: string }> })?.plugins;
        if (!cancelled) {
          setActivePluginCount(
            (plugins ?? []).filter((plugin) => plugin.status === 'active').length
          );
        }
      } catch {
        if (!cancelled) setActivePluginCount(0);
      } finally {
        inFlight = false;
      }
    };

    loadActivePlugins();
    const timer = window.setInterval(loadActivePlugins, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  // Task Assets panel resize
  const handlePanelResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    panelResizing.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!panelResizing.current) return;
      // panel is on the right, so new width = window width - mouse x
      const newWidth = window.innerWidth - e.clientX;
      setPanelWidth(Math.max(200, Math.min(500, newWidth)));
    };
    const handleMouseUp = () => {
      if (panelResizing.current) {
        panelResizing.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      // cleanup if unmounted during drag
      panelResizing.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, []);
  /** Current in-flight request ID (for abort) */
  const [currentReqId, setCurrentReqId] = useState<string | null>(null);
  /** files touched by the agent during this session */
  const [trackedFiles, setTrackedFiles] = useState<TrackedFile[]>([]);
  /** preview modal */
  const [previewFile, setPreviewFile] = useState<{
    path: string;
    content: string;
    dataBase64?: string;
  } | null>(null);

  // When preview is open, lock the entire page body so no clicks fall through
  // to elements behind the modal (sidebar, chat area, etc.)
  useEffect(() => {
    if (previewFile) {
      const prev = document.body.style.pointerEvents;
      document.body.style.pointerEvents = 'none';
      return () => {
        document.body.style.pointerEvents = prev;
      };
    }
  }, [previewFile]);

  // Destroy all IPC listeners on unmount to prevent memory leaks and
  // state-updates on an unmounted component (#378 fix, round 2).  Also cancel
  // the active send's watchdog interval + typewriter frame so an in-flight
  // send can't keep calling setMessages after unmount.
  useEffect(() => {
    return () => {
      activeSendCleanupRef.current?.();
      cleanupListeners();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** diff modal */
  const [diffFile, setDiffFile] = useState<{
    path: string;
    diff: string | null;
    original_content: string | null;
    current_content: string | null;
    has_diff: boolean;
    is_new_file?: boolean;
  } | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [reverting, setReverting] = useState(false);
  // Inline exec output: tool_call_id → accumulated stdout/stderr
  const [execOutputs, setExecOutputs] = useState<
    Record<string, { stdout: string; stderr: string; running: boolean }>
  >({});
  // When false, suppress the bordered inline terminal box for exec outputs.
  // Stored under desktop.ui.inlineExecOutput (opaque desktop-owned settings).
  // Defaults to false to avoid empty-box artifacts when sandbox policy strips
  // stdout/stderr (see issue surfaced after #339).
  const [inlineExecOutput, setInlineExecOutput] = useState(false);
  useEffect(() => {
    window.miqi.config
      ?.get()
      ?.then((cfg: any) => {
        if (cfg?.desktop?.ui?.inlineExecOutput === true) setInlineExecOutput(true);
      })
      .catch(() => {});
  }, []);

  // Refetch when window regains focus, so toggling the setting in the
  // Settings page takes effect without a full app reload.
  useEffect(() => {
    const refetch = () => {
      window.miqi.config
        ?.get()
        ?.then((cfg: any) => setInlineExecOutput(cfg?.desktop?.ui?.inlineExecOutput === true))
        .catch(() => {});
    };
    window.addEventListener('focus', refetch);
    document.addEventListener('visibilitychange', refetch);
    return () => {
      window.removeEventListener('focus', refetch);
      document.removeEventListener('visibilitychange', refetch);
    };
  }, []);
  const [merging, setMerging] = useState(false);
  const [activePluginCount, setActivePluginCount] = useState(0);
  const [shareStatus, setShareStatus] = useState<'idle' | 'copied' | 'exported' | 'context'>(
    'idle'
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const userScrolledUp = useRef(false);
  const justOpened = useRef(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const toolArgsByCallId = useRef<Map<string, unknown>>(new Map());
  /** web_search tool outputs (by tool_call_id) for click-to-expand result
   *  cards on the live tool row (#539). State, not ref — cards must re-render
   *  when the end event lands. */
  const [searchResultsByCallId, setSearchResultsByCallId] = useState<Record<string, string>>({});
  const previewJustClosed = useRef(false);
  const unsubsRef = useRef<Array<() => void>>([]);
  const finalCleanupTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const liveReasoningTsRef = useRef<number | null>(null);
  // Throttle live-reasoning re-renders: reasoning deltas arrive in a fast
  // stream and each setMessages forces a full messages rebuild + markdown
  // re-render in ThinkBlock.  Buffer deltas and flush on a short timer so the
  // UI updates a few times a second instead of per-chunk (fixes "thinking
  // displays slowly" under heavy reasoning streams).
  const reasoningBufRef = useRef('');
  const reasoningTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flushReasoningRef = useRef<((ts: number) => void) | null>(null);
  // Flush any buffered reasoning deltas into the message list immediately.
  // Used by abort/error/final so the tail of the thinking text is never lost.
  flushReasoningRef.current = (ts: number) => {
    if (reasoningTimerRef.current) {
      clearTimeout(reasoningTimerRef.current);
      reasoningTimerRef.current = null;
    }
    const buffered = reasoningBufRef.current;
    reasoningBufRef.current = '';
    if (buffered) {
      setMessages((prev) => appendReasoningDelta(prev, buffered, ts));
    }
  };
  const shareFeedbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentSessionRef = useRef(sessionKey);
  // Track the active thread ID for new-protocol thread-aware conversations
  const currentThreadIdRef = useRef<string | null>(null);

  const inFlightCacheRef = useRef(moduleInFlightCache);
  const fullContentRef = useRef('');
  // Active send's cleanup (watchdog interval + typewriter RAF), so the
  // unmount effect can cancel in-flight work even when a send is ongoing.
  const activeSendCleanupRef = useRef<(() => void) | null>(null);

  // ── Thread tabs for multi-agent support ──
  interface ThreadTab {
    threadId: string;
    agentType: string;
    label: string;
  }
  const [threads, setThreads] = useState<ThreadTab[]>([
    { threadId: 'main', agentType: 'main', label: '主线程' },
  ]);
  const [activeThreadId, setActiveThreadId] = useState('main');

  useEffect(() => {
    const unsub = window.miqi.agents?.onSpawned((data) => {
      setThreads((prev) => {
        if (prev.find((t) => t.threadId === data.sub_thread_id)) return prev;
        return [
          ...prev,
          {
            threadId: data.sub_thread_id,
            agentType: data.agent_type,
            label: data.task_label || data.agent_type,
          },
        ];
      });
    });
    return () => {
      if (unsub) unsub();
    };
  }, []);

  useEffect(() => {
    const unsub = window.miqi.agents?.onCompleted((data) => {
      setThreads((prev) =>
        prev.map((t) =>
          t.threadId === data.sub_thread_id ? { ...t, label: `${t.label.replace(/ ✓$/, '')} ✓` } : t
        )
      );
    });
    return () => {
      if (unsub) unsub();
    };
  }, []);

  // ── Plan sidebar state ──
  interface PlanStep {
    id: string;
    description: string;
    status: 'pending' | 'in_progress' | 'completed' | 'skipped';
    depends_on: string[];
  }
  const [plan, setPlan] = useState<{ title: string; steps: PlanStep[] } | null>(null);
  const [planOpen, setPlanOpen] = useState(false);

  useEffect(() => {
    const unsub = window.miqi.plan?.onUpdated((data) => {
      if (data.plan) {
        setPlan(data.plan);
        setPlanOpen(true);
      }
    });
    return () => {
      if (unsub) unsub();
    };
  }, []);

  /** Upsert a file into trackedFiles */
  const trackFile = useCallback((path: string, op: TrackedFile['op'], truncated = false) => {
    // Normalise sandbox-internal paths before storing so Preview works
    const normPath = normalizeSandboxPath(path);
    // Strip surrounding quotes, trailing ellipsis, and leading ./ for dedup
    const clean = normPath
      .replace(/^["']|["']$/g, '')
      .replace(/\.{3,}$/, '')
      .replace(/[…]$/, '')
      .replace(/^\.\//, '')
      .trim();
    setTrackedFiles((prev) => {
      // Fuzzy match: compare cleaned base name, then exact path
      const existing = prev.find((f) => {
        const fc = f.path
          .replace(/^["']|["']$/g, '')
          .replace(/\.{3,}$/, '')
          .replace(/[…]$/, '')
          .replace(/^\.\//, '')
          .trim();
        // Basename-only matching should only kick in when one side is a bare
        // filename (no directory), e.g. a tool hint reporting just "foo.pdf"
        // that needs to match an existing "papers/foo.pdf" entry. Two paths
        // that both carry (different) directories must not be merged just
        // because they share a filename.
        const eitherIsBareFilename = !clean.includes('/') || !fc.includes('/');
        return (
          f.path === normPath ||
          fc === clean ||
          (eitherIsBareFilename && basename(f.path) === basename(clean))
        );
      });
      if (existing) {
        // Upgrade: read < edit < write
        const rank: Record<TrackedFile['op'], number> = { read: 0, edit: 1, write: 2, delete: 3 };
        const nextOp = rank[op] > rank[existing.op] ? op : existing.op;
        return prev.map((f) =>
          f.path === existing.path
            ? { ...f, op: nextOp, lastSeen: Date.now(), truncated: f.truncated && truncated }
            : f
        );
      }
      return [
        ...prev,
        { path: normPath, name: basename(normPath), op, lastSeen: Date.now(), truncated },
      ];
    });
  }, []);

  useEffect(() => {
    // True only on an actual sessionKey change.  loadTrigger can bump alone
    // (e.g. bridge became ready) to reload the SAME session — in that case we
    // must NOT wipe the user's typed input / attachments / streaming state,
    // which this PR's new explicit resets would otherwise do on every reload.
    const _sessionChanged = currentSessionRef.current !== sessionKey;
    // Snapshot the session we're leaving so switching back restores the
    // live-rendered thinking/reply instantly.  While on a session its events
    // take the LIVE path (in `messages`), never moduleInFlightCache — so
    // without this snapshot they'd be lost when setMessages([]) runs below.
    if (_sessionChanged && currentSessionRef.current) {
      moduleMessagesSnapshot.set(currentSessionRef.current, messagesRef.current);
    }
    // Update the ref FIRST so the per-handler session_key guard on the
    // CURRENT listeners (from the previous session's handleSend) sees the
    // new session.  Crucially, do NOT call cleanupListeners() here — the
    // old listeners must survive the session switch so they can route
    // orphan events into inFlightCacheRef.  They are torn down naturally
    // by the next handleSend() or by the unmount cleanup effect (#378).
    currentSessionRef.current = sessionKey;
    currentThreadIdRef.current = null; // Reset on session change
    toolArgsByCallId.current.clear(); // drop tool-call args from the previous session
    if (_sessionChanged) {
      setHistoryLoaded(false);
      // ── Instant restore ─────────────────────────────────────────
      // sessions.get() is async, so clearing messages here and waiting would
      // leave a blank window until it resolves.  Restore the snapshot of this
      // session (from when we last left it) or its cached in-flight events
      // NOW so the thinking/reply appears immediately, no blank flash.
      const _targetCache = inFlightCacheRef.current.get(sessionKey);
      const _snapshot = moduleMessagesSnapshot.get(sessionKey);
      // A turn is "live" if (a) cached progress events arrived while we were
      // away with no terminal event yet, OR (b) the snapshot still shows
      // in-progress thinking.  (b) matters because progress events that
      // arrived BEFORE the switch-away took the live path (rendered into
      // messages + snapshot) and never entered the cache — the cache alone
      // would wrongly report "no live turn" and kill the thinking indicator.
      const _cacheLiveTurn =
        !!_targetCache &&
        _targetCache.events.some((e) => e.type === 'progress') &&
        !_targetCache.events.some((e) => e.type === 'final' || e.type === 'error' || e.type === 'aborted');
      let _snapLiveTurn = false;
      if (_snapshot && _snapshot.length > 0) {
        const _snapLastUser = (() => {
          for (let _i = _snapshot.length - 1; _i >= 0; _i -= 1) {
            if (_snapshot[_i].role === 'user') return _i;
          }
          return -1;
        })();
        const _after = _snapshot.slice(_snapLastUser + 1);
        const _hasThinking = _after.some((_m) => _m.role === 'progress' || _m.role === 'subagent');
        const _hasFinalReply = _after.some((_m) => _m.role === 'assistant' && String(_m.content ?? '').trim().length > 0);
        // A turn is also live if the typewriter is still revealing a reply
        // (the assistant bubble holds partial text).  Many backends emit no
        // progress events — the "thinking" the user sees is the half-typed
        // assistant reply.  Check revealBySession: if this session still has
        // a running typewriter (final not done), keep streaming on.
        const _reveal = revealBySession.get(sessionKey);
        // Typewriter is active while it still has text to reveal, regardless
        // of whether finalDone is set (finalDone just means content arrived).
        const _typewriterActive =
          !!_reveal && _reveal.displayed.length < _reveal.fullContent.length;
        _snapLiveTurn = (_hasThinking && !_hasFinalReply) || _typewriterActive;
      }
      // Authoritative "is this session still generating?" — handleSend adds the
      // key, final/error/aborted removes it.  This survives every phase of a
      // turn, including early thinking where the snapshot holds only the user
      // bubble and no progress text / typewriter exists yet — the exact phase
      // where the heuristics below (cache progress, snapshot thinking, active
      // typewriter) all report false and the thinking indicator wrongly dies.
      const _hasLiveTurn =
        streamingBySession.has(sessionKey) || _cacheLiveTurn || _snapLiveTurn;
      if (_snapshot && _snapshot.length > 0) {
        // Exact last-rendered view — best fidelity.
        setMessages(_snapshot);
        setHistoryLoaded(true);
      } else if (_targetCache && _targetCache.events.length > 0) {
        setMessages(cachedEventsToMessages(_targetCache.events));
        setHistoryLoaded(true);
      } else {
        setMessages([]);
      }
      setSessionUpdatedAt(null);
      // The component survives session switches (App.tsx no longer keys it by
      // sessionKey), so state that used to be wiped by remount must be reset
      // here explicitly — otherwise a previous session's attachments, inline
      // exec output, or streaming flag leak into the newly opened session.
      setAttachments([]);
      setExecOutputs({});
      // A turn is still live only if progress events were cached while we were
      // away AND no terminal event (final/error/aborted) arrived yet — a cached
      // final means the backend already finished and the persisted history
      // renders the reply, so the spinner must stay off.  Unconditionally
      // setting streaming false here made the spinner vanish on switch-back
      // until the reply bubble appeared.
      if (_hasLiveTurn) {
        setStreaming(true);
      } else {
        setStreaming(false);
      }
      setCurrentReqId(null);
      setInput('');
      setThreads([{ threadId: 'main', agentType: 'main', label: '主线程' }]);
      setActiveThreadId('main');
      setPlan(null);
      setPlanOpen(false);
      fullContentRef.current = '';
      // #612 session-rename state must reset per session too (the component no
      // longer remounts on sessionKey change, so without this a rename dialog
      // or custom title from the previous session would leak into this one).
      setCustomTitle(null);
      setEditingTitle(false);
      // NOTE: do NOT clear trackedFiles here — clearing before the async
      // load completes causes a flash of "No files yet" on every session
      // switch.  If the bridge is not ready yet, sendSafe returns null and
      // we would permanently lose the display.  Instead we replace atomically
      // inside load() after the bridge responds.
      justOpened.current = true;
      userScrolledUp.current = false; // reset for new session
    }
    const load = async () => {
      // ── Retry with exponential backoff ──────────────────────────
      // On startup the bridge may not be running yet → sendSafe
      // returns null.  Even when running, transient IPC failures
      // can occur.  Retry so that a slow bridge start or a one-off
      // error doesn't leave the session permanently blank (#480).
      const MAX_RETRIES = 10;
      const BASE_DELAY_MS = 500;
      const MAX_DELAY_MS = 10_000;

      let detail: unknown = null;
      let lastErr: unknown = null;

      for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
        if (currentSessionRef.current !== sessionKey) return;

        try {
          const pw = pendingWorkspace?.current;
          // Only consume if it belongs to this session — prevents
          // cross-session races and retry-drop on transient failures.
          if (pw && pw.sessionKey === sessionKey) {
            pendingWorkspace.current = null;
            detail = await window.miqi.sessions.get(sessionKey, { workspace: pw.workspace } as any);
          } else {
            detail = await window.miqi.sessions.get(sessionKey);
          }
        } catch (err) {
          lastErr = err;
        }

        if (detail != null) break; // got data — stop retrying

        if (attempt < MAX_RETRIES - 1) {
          const delay = Math.min(BASE_DELAY_MS * Math.pow(2, attempt), MAX_DELAY_MS);
          console.warn(
            `[ChatConsole] Load attempt ${attempt + 1}/${MAX_RETRIES} returned null, retrying in ${delay}ms…`
          );
          await new Promise((r) => setTimeout(r, delay));
        }
      }

      if (currentSessionRef.current !== sessionKey) return;

      if (detail == null) {
        console.warn(
          '[ChatConsole] Failed to load session data after retries, last error:',
          lastErr
        );
        setHistoryLoaded(true);
        return;
      }

      try {
        const rawMsgs: any[] = (detail as any)?.messages ?? [];
        const wsFromSession = (detail as any)?.workspace ?? null;
        onWorkspaceLoaded?.(wsFromSession);
        const uiMsgs = sessionMsgsToUi(rawMsgs);

        // ── Merge snapshot + cached in-flight events with history ──
        // sessions.get() is the authoritative, deduped source — build merged
        // FROM it (uiMsgs) so the persisted full reply is never duplicated.
        // The snapshot carries live-rendered THINKING (progress/error/subagent,
        // never persisted) that sessions.get lacks; insert it right after the
        // last user message so the thinking the user saw before switching away
        // stays visible above the reply.
        //
        // If this session's typewriter is still active (a reply is being
        // revealed), KEEP the snapshot's assistant bubble — instant restore
        // showed it, and rebuilding from history would drop the half-typed
        // reply or shift it, making the thinking/reply appear to jump.  The
        // module-level typewriter resumes and completes it.
        var cached = inFlightCacheRef.current.get(sessionKey);
        const _snap = moduleMessagesSnapshot.get(sessionKey);
        // The typewriter "needs to keep working" whenever it has content to
        // present — i.e. fullContent is non-empty.  Don't key on `displayed <
        // fullContent`: the RAF chain keeps advancing `displayed` even while
        // the UI is skipped, so by the time the user switches back `displayed`
        // may already equal fullContent while the on-screen bubble is still
        // half-typed.  In that case the revealNext completion branch syncs the
        // full text to the bubble — but ONLY if we keep the RAF running (or at
        // least don't cancel it below).
        const _revealState = revealBySession.get(sessionKey);
        const _typewriterHasContent = !!_revealState && _revealState.fullContent.length > 0;
        const _revealActive = _typewriterHasContent && _revealState!.displayed.length < _revealState!.fullContent.length;
        var merged = uiMsgs.slice();
        if (_typewriterHasContent && _snap && _snap.length > 0) {
          // Keep the snapshot (which holds the partial reply the typewriter is
          // completing) so the user doesn't see a jump — BUT the snapshot may
          // predate the persisted full reply (sessions.get already has it).
          // Merge: start from uiMsgs (authoritative full history) and carry the
          // snapshot's in-progress thinking/subagent lines above the reply.
          // A bare snapshot-only merge would DROP the persisted full reply,
          // leaving the bubble blank until a restart.
          const _snapNonReply: Message[] = [];
          const _snapLastUser = (() => {
            for (let _i = _snap.length - 1; _i >= 0; _i -= 1) {
              if (_snap[_i].role === 'user') return _i;
            }
            return -1;
          })();
          for (const _sm of _snap.slice(_snapLastUser + 1)) {
            if (_sm.role === 'progress' || _sm.role === 'error' || _sm.role === 'subagent') {
              _snapNonReply.push(_sm);
            }
          }
          if (_snapNonReply.length > 0) {
            const insIdx = (() => {
              for (let _i = merged.length - 1; _i >= 0; _i -= 1) {
                if (merged[_i].role === 'user') return _i + 1;
              }
              return merged.length;
            })();
            merged.splice(insIdx, 0, ..._snapNonReply);
          }
        }

        if (_snap && _snap.length > 0) {
          const _snapThinking: Message[] = [];
          const lastUserIdx = (() => {
            for (let _i = _snap.length - 1; _i >= 0; _i -= 1) {
              if (_snap[_i].role === 'user') return _i;
            }
            return -1;
          })();
          for (const _sm of _snap.slice(lastUserIdx + 1)) {
            if (_sm.role === 'progress' || _sm.role === 'error' || _sm.role === 'subagent') {
              _snapThinking.push(_sm);
            }
          }
          if (_snapThinking.length > 0 && !_revealActive) {
            const insIdx = (() => {
              for (let _i = merged.length - 1; _i >= 0; _i -= 1) {
                if (merged[_i].role === 'user') return _i + 1;
              }
              return merged.length;
            })();
            merged.splice(insIdx, 0, ..._snapThinking);
          }
        }

        // Thinking carried by the snapshot (live-rendered, never persisted)
        // is already inside `merged`.  Cached events add post-switch progress.
        if (cached && cached.events.length > 0) {
          const _split = splitCachedMessages(cached.events);
          const _finalContent = _split.finalReply ?? '';
          // If the final was persisted, sessions.get already renders it —
          // don't append a duplicate from cache.  When the typewriter is
          // active (_revealActive) the partial reply is on screen and the
          // typewriter will complete it — also skip the cached final so we
          // don't stack a partial bubble + a full duplicate.
          const _alreadyPersisted =
            _revealActive ||
            (_finalContent !== '' &&
              merged.some((_m) => _m.role === 'assistant' && String(_m.content ?? '') === _finalContent.trim()));
          if (!_alreadyPersisted) {
            // Append cached thinking that isn't already represented in merged
            // (same toolCallId OR same content prefix — plain thinking lines
            // carry no toolCallId, so fall back to content comparison).
            for (const _ctm of _split.thinking) {
              const _dup = merged.some(
                (_m) =>
                  _m.role === 'progress' &&
                  ((_m.toolCallId != null && _m.toolCallId === _ctm.toolCallId) ||
                    (_m.content.startsWith(_ctm.content) || _ctm.content.startsWith(_m.content)))
              );
              if (!_dup) merged.push(_ctm);
            }
            if (_split.finalReply) {
              merged.push({ role: 'assistant', content: _split.finalReply, timestamp: Date.now() });
            }
          }
          // Exec inline output → merge into execOutputs for the session
          for (var _ec = 0; _ec < cached.events.length; _ec += 1) {
            const _eev = cached.events[_ec];
            if (_eev.type === 'progress') {
              const _epd = _eev.data as ChatProgress;
              if (_epd?.stream && _epd?.delta && _epd?.tool_call_id) {
                setExecOutputs(function (_prev) {
                  var _cur = _prev[_epd.tool_call_id!] || { stdout: '', stderr: '', running: true };
                  var _out = _cur.stdout;
                  var _err = _cur.stderr;
                  if (_epd.stream === 'stdout') {
                    _out += (_epd.delta || '');
                  } else {
                    _err += (_epd.delta || '');
                  }
                  return { ..._prev, [_epd.tool_call_id!]: { stdout: _out, stderr: _err, running: true } };
                });
              } else if (_epd?.type === 'doc_progress' && _epd?.file) {
                // Apply attachment status directly to `merged` — a nested
                // setMessages updater would be overwritten by the plain
                // setMessages(merged) below, silently dropping the restore.
                merged = merged.map(function (_m) {
                  if (_m.role === 'user' && _m.attachments) {
                    var _upd = _m.attachments.map(function (_a) {
                      if (_a.name !== _epd.file || _a.type !== 'document') return _a;
                      var _st: Attachment['status'] = _epd.stage === 'ready' || _epd.stage === 'done' ? 'done' : _epd.stage === 'error' ? 'error' : 'parsing';
                      return { ..._a, status: _st, parseError: _st === 'error' ? (_epd.message ?? '') : _a.parseError };
                    });
                    return { ..._m, attachments: _upd };
                  }
                  return _m;
                });
              }
            }
          }
          inFlightCacheRef.current.delete(sessionKey);
        }
        // A cached final (or persisted history) now renders the full reply —
        // mark the session so the old send listener's live onFinal doesn't
        // append a duplicate when it fires for the same reply.
        if (cached && cached.events.some((e) => e.type === 'final')) {
          finalHandledSessions.add(sessionKey);
        }
        // If a cached final was merged, the FULL reply is already rendered in
        // `merged` — stop this session's typewriter so the revealNext RAF loop
        // (which pauses across switches) doesn't keep revealing over it and
        // duplicate the bubble.  Determine "full reply already rendered" by
        // whether the LAST assistant message equals the typewriter's full
        // content; if merged only holds a half-typed reply, keep the RAF so
        // revealNext completes it.
        const _revealNow = revealBySession.get(sessionKey);
        const _lastAsstContent = (() => {
          for (let _i = merged.length - 1; _i >= 0; _i -= 1) {
            if (merged[_i].role === 'assistant') return String(merged[_i].content ?? '');
          }
          return '';
        })();
        const _mergedHasFullReply =
          !!_revealNow &&
          _revealNow.fullContent.length > 0 &&
          _lastAsstContent === _revealNow.fullContent;
        if (_revealNow && (_mergedHasFullReply || (!_typewriterHasContent && (_revealNow.finalDone || _revealNow.displayed.length > 0)))) {
          if (_revealNow.animId !== null) {
            cancelAnimationFrame(_revealNow.animId);
            _revealNow.animId = null;
          }
          if (_revealNow.finalDone || _mergedHasFullReply) {
            setStreaming(false);
          }
        }
        setMessages(merged);
        // Snapshot is now reconciled into `merged` — clear it so a later
        // load() (loadTrigger refresh) doesn't re-append stale transient
        // progress on top of history.
        moduleMessagesSnapshot.delete(sessionKey);
        setSessionUpdatedAt((detail as any)?.updated_at ?? null);
        // Restore tracked files from dedicated tracked_files.json
        let tfList: any[] = [];
        try {
          const tfResult = await window.miqi.sessions.getTrackedFiles(sessionKey);
          if (currentSessionRef.current !== sessionKey) return;
          tfList = (tfResult as any)?.tracked_files ?? [];
        } catch {
          // backend failure is non-fatal — fall through to message extraction
        }
        // Also extract tracked files from session messages (fallback when
        // tracked_files.json is empty — agent tools don't persist there).
        const fromMessages = extractTrackedFilesFromMessages(rawMsgs);
        // Merge: backend data takes priority, messages fill gaps
        const mergedMap = new Map<string, TrackedFile>();
        for (const f of fromMessages) mergedMap.set(f.path, f);
        for (const f of tfList as any[]) {
          const normPath = (f.path as string).replace(/\\/g, '/');
          mergedMap.set(normPath, {
            path: normPath,
            name: f.name,
            op: f.op,
            lastSeen: f.lastSeen,
          });
        }
        setTrackedFiles(Array.from(mergedMap.values()));

        // ── Issue #490: resume this session's most-recent active thread ──
        // currentThreadIdRef is reset to null on every sessionKey/remount
        // (line above) and is never persisted, so without this the next
        // send would call thread/start → mint a fresh random thread_id,
        // orphaning the prior thread's SQLite history and making the model
        // "forget" earlier turns even though the UI still shows them.
        //
        // Look up stored threads for this session and reuse the most
        // recently updated one so chat.send continues accumulating into
        // the SAME (session_id, thread_id). A brand-new session has no
        // stored threads → ref stays null → first send still creates one.
        // This keeps thread isolation intact (B/C content is never pulled
        // into A); only A's own history is reloaded.
        // Guard with a short timeout (Promise.race, same shape as the
        // thread/start guard below) so a slow/hung backend can't block the
        // surrounding flow from reaching setHistoryLoaded(true). This is a
        // best-effort optimization; on timeout or rejection we fall through to
        // the existing first-send thread/start path (ref stays null) — the
        // session still loads, just without thread reuse. 10s is far shorter
        // than thread/start's 30s (which budgets sandbox first-init) because
        // threads/list is a cheap SQLite read, not a sandbox spawn.
        let resumeTimer: ReturnType<typeof setTimeout> | null = null;
        try {
          const listRes = await Promise.race([
            window.miqi.threads.list({
              session_key: currentSessionRef.current,
            }),
            new Promise<never>((_, reject) => {
              resumeTimer = setTimeout(() => reject(new Error('thread/list timeout')), 10_000);
            }),
          ]);
          if (resumeTimer) clearTimeout(resumeTimer);
          if (currentSessionRef.current !== sessionKey) return; // switched away
          // backend `Page.to_dict()` (thread_protocol.py:94) envelopes rows
          // under `data`; read via extractThreadListRows so resume matches
          // the real backend shape (and is unit-tested end-to-end).
          const listRows = extractThreadListRows(listRes);
          const resumeId = pickThreadToResume(listRows);
          if (resumeId) {
            currentThreadIdRef.current = resumeId;
          }
        } catch (err) {
          // Non-fatal: timeout or rejection → ref stays null → first send
          // still uses the thread/start path. Don't block rendering.
          if (resumeTimer) clearTimeout(resumeTimer);
          console.warn('[ChatConsole] Failed to resume thread:', err);
        }
      } catch (err) {
        console.warn('[ChatConsole] Failed to load session data:', err);
      }
      setHistoryLoaded(true);
    };
    load();
    // loadTrigger lets the parent force a reload (e.g. after bridge becomes ready)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionKey, loadTrigger]);

  // Scroll to bottom: (a) unconditionally after opening a session,
  // (b) during streaming only if the user hasn't manually scrolled up.
  useEffect(() => {
    if (!historyLoaded) return;
    const el = scrollRef.current;
    if (!el) return;
    if (justOpened.current) {
      justOpened.current = false;
      el.scrollTop = el.scrollHeight + el.clientHeight; // clamped to max
      userScrolledUp.current = false;
    } else if (!userScrolledUp.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [historyLoaded, messages]);

  // Detect manual scroll-up / scroll-back-to-bottom
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (distFromBottom < 40) {
        userScrolledUp.current = false;
      } else if (distFromBottom > 80) {
        userScrolledUp.current = true;
      }
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  // Persistent listener for subagent results — must NOT be cleaned up
  // when the main chat completes, because subagents finish asynchronously.
  useEffect(() => {
    const unsub = window.miqi.chat.onSubagentResult((data: ChatSubagentResult) => {
      if (data.session_key && data.session_key !== currentSessionRef.current) return;
      const statusIcon = data.status === 'ok' ? '✅' : '❌';
      const label = data.label || data.task_id;
      const content = `${statusIcon} Subagent "${label}" ${data.status === 'ok' ? 'completed' : 'failed'}:\n\n${data.result}`;
      setMessages((prev) => [...prev, { role: 'subagent', content, timestamp: Date.now() }]);
    });
    return () => {
      unsub();
    };
  }, []);

  const clearFinalCleanupTimer = useCallback(() => {
    if (finalCleanupTimerRef.current) {
      clearTimeout(finalCleanupTimerRef.current);
      finalCleanupTimerRef.current = null;
    }
  }, []);

  const showShareFeedback = useCallback((status: 'copied' | 'exported' | 'context') => {
    if (shareFeedbackTimerRef.current) {
      clearTimeout(shareFeedbackTimerRef.current);
    }
    setShareStatus(status);
    shareFeedbackTimerRef.current = setTimeout(() => {
      setShareStatus('idle');
      shareFeedbackTimerRef.current = null;
    }, 2000);
  }, []);

  const cleanupListeners = useCallback(() => {
    clearFinalCleanupTimer();
    if (shareFeedbackTimerRef.current) {
      clearTimeout(shareFeedbackTimerRef.current);
      shareFeedbackTimerRef.current = null;
    }
    for (const unsub of unsubsRef.current) unsub();
    unsubsRef.current = [];
  }, [clearFinalCleanupTimer]);

  const handleAttachClick = () => fileInputRef.current?.click();

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    Array.from(e.target.files ?? []).forEach((file) => {
      const isImage = file.type.startsWith('image/');
      const isDocument = DOCUMENT_SUFFIXES_RE.test(file.name);
      const isTextLike = TEXT_SUFFIXES_RE.test(file.name) || file.type.startsWith('text/');

      if (isTextLike && !isDocument) {
        // Plain text files — read directly as text
        const reader = new FileReader();
        reader.onload = () =>
          setAttachments((prev) => [
            ...prev,
            { name: file.name, type: 'text', content: reader.result as string, size: file.size },
          ]);
        reader.readAsText(file);
      } else if (isTextLike && isDocument) {
        // Markdown/text files detected as documents — read as text AND as base64 for server fallback
        const reader = new FileReader();
        reader.onload = () => {
          const base64 = (reader.result as string).split(',')[1];
          const textContent = new TextDecoder().decode(
            Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))
          );
          setAttachments((prev) => [
            ...prev,
            {
              name: file.name,
              type: 'document',
              dataBase64: base64,
              content: textContent,
              dataUrl: reader.result as string,
              size: file.size,
              mimeType: file.type || getMimeTypeFromName(file.name),
              status: 'pending' as const,
            },
          ]);
        };
        reader.readAsDataURL(file);
      } else if (isDocument) {
        const reader = new FileReader();
        reader.onload = () => {
          const base64 = (reader.result as string).split(',')[1];
          const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
          // PDF/MD/text parse instantly client-side → done; Office/RTF needs server → pending
          const isServerParsed = /^(docx|doc|pptx|ppt|xlsx|xls|odt|odp|ods|rtf)$/i.test(ext);
          const parseStatus: Attachment['status'] = isServerParsed ? 'pending' : 'done';

          setAttachments((prev) => [
            ...prev,
            {
              name: file.name,
              type: 'document',
              dataUrl: reader.result as string,
              dataBase64: base64,
              size: file.size,
              mimeType: file.type || getMimeTypeFromName(file.name),
              status: parseStatus,
            },
          ]);
        };
        reader.readAsDataURL(file);
      } else if (isImage) {
        const reader = new FileReader();
        reader.onload = () =>
          setAttachments((prev) => [
            ...prev,
            { name: file.name, type: 'image', dataUrl: reader.result as string, size: file.size },
          ]);
        reader.readAsDataURL(file);
      } else {
        const reader = new FileReader();
        reader.onload = () =>
          setAttachments((prev) => [
            ...prev,
            { name: file.name, type: 'text', content: reader.result as string, size: file.size },
          ]);
        reader.readAsText(file);
      }
    });
    e.target.value = '';
  };

  const removeAttachment = (idx: number) =>
    setAttachments((prev) => prev.filter((_, i) => i !== idx));

  const handleAbort = useCallback(async () => {
    cleanupListeners();
    try {
      await window.miqi.chat.abort(currentSessionRef.current);
    } catch {
      /* ignore */
    }
    setStreaming(false);
    setCurrentReqId(null);
    flushReasoningRef.current?.(Date.now());
    liveReasoningTsRef.current = null;
    setMessages((prev) => [
      ...prev.filter((m) => !m.isLiveReasoning),
      { role: 'progress', content: '已停止。', timestamp: Date.now() },
    ]);
  }, [cleanupListeners, currentReqId]);

  // Respond to new-session trigger from App/Sidebar — create directly, no picker.
  // NOTE: this intentionally does NOT gate on `streaming`. Switching sessions
  // mid-stream is an expected workflow (covered by session-streaming-isolation
  // E2E); the new ChatConsole unmount aborts the in-flight render, and backend
  // isolation guarantees the stream never leaks into the new session.
  useEffect(() => {
    if (newSessionTrigger && newSessionTrigger > 0) {
      createSession(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newSessionTrigger]);

  // Opens the workspace picker modal — called by the inline "更换" button
  const handleOpenWorkspacePicker = useCallback(async () => {
    const workspaces = await window.miqi.sessions.listRecentWorkspaces()
      .then(r => r?.workspaces ?? [])
      .catch(() => [] as string[]);
    setRecentWorkspaces(workspaces);
    setWorkspacePickerOpen(true);
  }, []);

  const createSession = useCallback((workspace?: string | null) => {
    // Do NOT call setWorkspacePickerOpen(false) here — onNewSession
    // changes sessionKey which unmounts this ChatConsole instance via
    // the key={sessionKey} in App. The Dialog portal is cleaned up
    // by React unmount, and the new instance mounts with the default
    // workspacePickerOpen=false state. Calling setState here races
    // with the unmount (the state update is never flushed).
    const newKey = `desktop:${Date.now()}`;
    currentThreadIdRef.current = null;
    cleanupListeners();
    onNewSession?.(newKey, workspace ?? null);
  }, [cleanupListeners, onNewSession]);

  const handleDeleteSession = useCallback(async () => {
    const key = currentSessionRef.current;
    if (!key) return;
    if (!window.confirm('确定删除此对话？此操作不可撤销。')) return;
    try {
      await window.miqi.sessions.delete(key);
    } catch {
      /* ignore */
    }
    createSession(null);
  }, [createSession]);

  /** Payload for programmatic sends (e.g. regenerate) — bypasses input state */
  const retryPayloadRef = useRef<{ text: string; attachments: Attachment[]; retry?: boolean } | null>(null);
  const handleSendRef = useRef<() => void>(() => {});

  const handleSend = useCallback(async () => {
    const payload = retryPayloadRef.current;
    const text = (payload?.text ?? input).trim();
    const atts = payload?.attachments ?? attachments;
    if (!text && atts.length === 0) {
      retryPayloadRef.current = null;
      return;
    }
    // Retry/regenerate: nudge the model to answer differently — the stored
    // user message stays clean, only the outbound content gets the hint.
    const retryHint = payload?.retry
      ? '\n\n[系统提示：这是重试请求。请换一个角度重新回答，不要复述之前的答案。]'
      : '';

    try {
      const result = await window.miqi.providers.list();
      const hasConfiguredProvider = result.providers.some((provider) => provider.configured);
      if (!hasConfiguredProvider) {
        retryPayloadRef.current = null;
        setMessages((prev) => [...prev, createProviderConfigMessage()]);
        return;
      }
    } catch {
      // If provider status cannot be read, keep the original send path so the
      // bridge can surface the underlying runtime error.
    }
    // All early-return guards passed — the retry payload is now consumed.
    retryPayloadRef.current = null;

    // The component survives session switches, so a turn's closure can
    // outlive the session it belongs to.  Capture the session this send
    // targets NOW — the `sessionKey` prop closure may be stale (not in the
    // useCallback deps) and the session-switch effect mutates
    // currentSessionRef.  The watchdog below must not warn into another
    // session after the user switched away.
    const sendSessionKey = currentSessionRef.current;

    // If a reveal animation is still running from the previous response,
    // cancel it and abort the in-flight request so we can start fresh.
    if (streaming) {
      cleanupListeners();
      setStreaming(false);
      try {
        await window.miqi.chat.abort();
      } catch {
        /* ignore */
      }
    }

    // Generate a client-side req_id so we can abort this specific request
    const reqId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    setCurrentReqId(reqId);

    let content = text + retryHint;

    // Build message content with embedded document text
    for (const att of atts) {
      if (att.type === 'text' && att.content) {
        content += `\n\n[File: ${att.name}]\n\`\`\`\n${att.content}\n\`\`\``;
      } else if (att.type === 'image' && att.dataUrl) {
        content += `\n\n[Image: ${att.name}]`;
      } else if (att.type === 'document' && att.dataBase64) {
        // Decode and extract text client-side
        try {
          const raw = Uint8Array.from(atob(att.dataBase64), (c) => c.charCodeAt(0));
          let extracted = '';
          const ext = att.name.split('.').pop()?.toLowerCase() ?? '';

          if (ext === 'pdf') {
            extracted = extractPdfText(raw.buffer);
          } else if (
            ext === 'md' ||
            ext === 'markdown' ||
            ext === 'mdown' ||
            ext === 'txt' ||
            ext === 'text' ||
            ext === 'html' ||
            ext === 'htm' ||
            ext === 'csv' ||
            ext === 'json' ||
            ext === 'yaml' ||
            ext === 'yml' ||
            ext === 'xml' ||
            ext === 'env' ||
            ext === 'log' ||
            ext === 'sql' ||
            ext === 'ini' ||
            ext === 'toml' ||
            ext === 'htaccess' ||
            ext === 'sh' ||
            ext === 'bash'
          ) {
            extracted = new TextDecoder().decode(raw);
          }

          if (extracted && extracted.trim()) {
            content += `\n\n--- Document: ${att.name} ---\n${extracted.slice(0, 50000)}\n--- End of ${att.name} ---`;
          } else if (ext === 'pdf') {
            content += `\n\n[${att.name}: scanned PDF — OCR will be attempted by the server]`;
          } else {
            content += `\n\n[${att.name}: binary file, server will parse]`;
          }
        } catch {
          content += `\n\n[${att.name}: ${formatFileSize(att.size)} — parsing on server]`;
        }
      }
    }

    const userMsg: Message = {
      role: 'user',
      content: text || '(attachment)',
      attachments: [...attachments],
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    userScrolledUp.current = false; // user sent a message — resume auto-scroll
    setInput('');
    // Reset textarea height after sending
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }, 0);
    setAttachments([]);
    // Save a snapshot before clearing — chat.send needs it later
    const sentAttachments = [...attachments];
    setStreaming(true);
    streamingBySession.add(sendSessionKey); // turn in flight — survives switch
    cleanupListeners();
    finalHandledSessions.delete(sendSessionKey); // new turn — allow live final

    // Typewriter state is held at module level (revealBySession) so it
    // survives a session switch-away — the animation pauses (skips setMessages
    // while away) and RESUMES when the user returns.
    const _reveal = revealBySession.get(sendSessionKey) ?? {
      fullContent: '',
      displayed: '',
      animId: null,
      finalDone: false,
    };
    revealBySession.set(sendSessionKey, _reveal);
    let fullContent = _reveal.fullContent;
    let displayed = _reveal.displayed;
    let animId = _reveal.animId;
    let finalDone = _reveal.finalDone;
    let streamErrorHandled = false;
    fullContentRef.current = fullContent;
    // Timestamp when the turn started so we can compute "用时 X 秒".
    const turnStartMs = Date.now();

    // Reveal the assistant reply with a typewriter animation. The bubble is
    // created lazily — only once the first chunk of content is available — so
    // we never render an empty assistant bubble (which previously flashed as a
    // blank message box before the first animation frame filled it in; see
    // issue #109). If the reply has no text, no bubble is shown at all.
    const persistReveal = () => {
      _reveal.fullContent = fullContent;
      _reveal.displayed = displayed;
      _reveal.animId = animId;
      _reveal.finalDone = finalDone;
    };
    const revealNext = () => {
      // The component survives session switches, so this typewriter loop can
      // outlive the session it belongs to.  Keep the RAF chain RUNNING across
      // a switch-away — only skip the setMessages when we're not on the send's
      // own session.  If we stopped the chain on switch-away (animId = null;
      // return), nothing would ever restart it when the user switches back,
      // so a half-typed reply would never finish revealing.  The user sees
      // the remaining content continue the moment they return.
      if (currentSessionRef.current === sendSessionKey) {
        if (displayed.length >= fullContent.length) {
          // Reveal finished.  If the UI's assistant bubble is still partial
          // (the RAF chain advanced `displayed` in memory while we were away,
          // skipping setMessages), sync it to the full text in one update so
          // the remaining content appears immediately on switch-back.  If the
          // bubble doesn't exist yet (load() rebuilt the list without it),
          // create it prefilled with the full reply.
          const ts = userMsg.timestamp + 1;
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === 'assistant' && last.timestamp === ts && last.content !== fullContent) {
              return [...prev.slice(0, -1), { ...last, content: fullContent }];
            }
            if (last?.role === 'assistant' && last.content !== fullContent) {
              return [...prev.slice(0, -1), { ...last, content: fullContent }];
            }
            if (!last || last.role !== 'assistant') {
              return [...prev, { role: 'assistant', content: fullContent, timestamp: ts }];
            }
            return prev;
          });
          if (finalDone) {
            setStreaming(false);
            scheduleFinalCleanup();
          }
          animId = null;
          persistReveal();
          return;
        }
        displayed += fullContent.slice(displayed.length, displayed.length + 4);
        persistReveal();
        const snap = displayed;
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          // Update the LAST assistant bubble regardless of timestamp.  After a
          // switch-back, load() may have rendered the persisted full reply with
          // a different timestamp than this typewriter's ts — matching on ts
          // would MISS it and append a duplicate bubble.  If the last message
          // is already this exact content, no-op; if it's an assistant (the
          // reply being revealed), replace its content with the latest chunk.
          if (last?.role === 'assistant') {
            if (last.content === snap) return prev;
            return [...prev.slice(0, -1), { ...last, content: snap }];
          }
          // First chunk: insert the assistant bubble prefilled with content,
          // never as an empty placeholder.
          return [...prev, { role: 'assistant', content: snap, timestamp: Date.now() }];
        });
      }
      // Always reschedule — even while away — so the animation resumes the
      // moment the user returns to this session.
      animId = requestAnimationFrame(revealNext);
      persistReveal();
    };

    // Track last progress event time for watchdog
    let lastEventAt = Date.now();
    // 思考过程实时可见后，普通等待不再提示（用户要求 #539）：只在真正
    // 卡死（60s 无任何事件）时给出强警告，避免噪音。
    const NO_PROGRESS_STRONG_MS = 60_000; // 60s — "really stuck" warning
    let warnMsgId: number | null = null; // timestamp of the last warning message
    let watchdogTimer: ReturnType<typeof setInterval> | null = null;

    // Helper: append watchdog message (idempotent — deduplicates via warnMsgId ref)
    const appendWatchdogMsg = (content: string) => {
      if (warnMsgId !== null) return; // already shown
      warnMsgId = Date.now();
      setMessages((prev) => [...prev, { role: 'error' as const, content, timestamp: warnMsgId! }]);
    };

    // Start watchdog timer
    watchdogTimer = setInterval(() => {
      // sendCleanup() clears watchdogTimer; if the interval fires after
      // that but before the OS dequeues it, bail immediately (#454).
      if (!watchdogTimer) return;
      if (finalDone) {
        clearInterval(watchdogTimer);
        watchdogTimer = null;
        return;
      }
      // The component now survives session switches (App.tsx removed
      // key={sessionKey}), so this turn's watchdog can outlive the session
      // it belongs to.  Never append warnings into a different session —
      // the user switched away; the warning belongs to this turn's own
      // session, which is handled when they switch back.
      if (currentSessionRef.current !== sendSessionKey) return;
      const elapsed = Date.now() - lastEventAt;
      if (elapsed >= NO_PROGRESS_STRONG_MS) {
        appendWatchdogMsg('⚠️ 后端 60s 无响应，可中止并检查运行日志。');
      }
    }, 5_000); // check every 5s

    const sendCleanup = () => {
      if (watchdogTimer) {
        clearInterval(watchdogTimer);
        watchdogTimer = null;
      }
      // Also stop the typewriter frame — otherwise an unmount while a send is
      // in flight leaves the RAF loop scheduling on an unmounted component.
      if (animId !== null) {
        cancelAnimationFrame(animId);
        animId = null;
      }
      activeSendCleanupRef.current = null;
      // NOTE: cleanupListeners() is deliberately NOT called here.
      // The typewriter completing does not mean the turn is over —
      // another final may still arrive (e.g. tool-call then final-text).
      // Listeners are torn down only on abort / error / new-session.
    };
    activeSendCleanupRef.current = sendCleanup;

    const scheduleFinalCleanup = () => {
      if (finalCleanupTimerRef.current) return;
      finalCleanupTimerRef.current = setTimeout(() => {
        finalCleanupTimerRef.current = null;
        sendCleanup();
        if (onChatFinished) onChatFinished();
      }, 100);
    };

    const unsubProgress = window.miqi.chat.onProgress((data: ChatProgress) => {
      // session_key is optional (back-compat); a missing one belongs to this
      // send's own session (sendSessionKey).  Without the fallback, a
      // session_key-less event arriving after a switch-away would be applied
      // to whatever session is now active — leaking A's stream into B.
      const _owner = data.session_key ?? sendSessionKey;
      if (_owner !== currentSessionRef.current) {
        var buf = inFlightCacheRef.current.get(_owner);
        if (!buf) { buf = { events: [], userMsgTimestamp: 0 }; inFlightCacheRef.current.set(_owner, buf); }
        buf.events.push({ type: 'progress', data, timestamp: Date.now() });
        return;
      }
      lastEventAt = Date.now();

      // ── Document progress events ───────────────────────────────
      if (data.type === 'doc_progress' && data.file) {
        setAttachments((prev) =>
          prev.map((a) => {
            if (a.name !== data.file || a.type !== 'document') return a;
            const stage = data.stage ?? 'parsing';
            const status =
              stage === 'ready' || stage === 'done'
                ? 'done'
                : stage === 'error'
                  ? 'error'
                  : 'parsing';
            return {
              ...a,
              status,
              parseError: status === 'error' ? (data.message ?? '') : a.parseError,
            };
          })
        );
        return;
      }

      // ── Live reasoning stream (thinking models) ──────────────────────
      // Append every delta to the LAST live thinking bubble in the message
      // list. The scan is deliberately state-driven (not a closure-local
      // timestamp) so StrictMode re-invocation or an effect re-creation can
      // never spawn a second "思考中…" block.
      //
      // Throttled: reasoning deltas arrive in a fast stream; appending each
      // one triggers a full messages rebuild + markdown re-render in
      // ThinkBlock, which makes thinking display slowly.  Buffer and flush on
      // a short timer.
      if (data.stream === 'reasoning' && typeof data.delta === 'string') {
        const ts = Date.now();
        liveReasoningTsRef.current = ts;
        reasoningBufRef.current += data.delta;
        if (!reasoningTimerRef.current) {
          reasoningTimerRef.current = setTimeout(() => {
            reasoningTimerRef.current = null;
            const buffered = reasoningBufRef.current;
            reasoningBufRef.current = '';
            if (buffered) {
              setMessages((prev) => appendReasoningDelta(prev, buffered, ts));
            }
          }, 60); // ~16 fps effective — smooth without per-chunk re-render
        }
        return;
      }

      // Handle stream deltas from exec (Phase 7 inline tool progress)
      if (data.stream && data.delta && data.tool_call_id) {
        const stream = data.stream;
        const delta = data.delta;
        const toolCallId = data.tool_call_id;
        setExecOutputs((prev) => {
          const current = prev[toolCallId] || { stdout: '', stderr: '', running: true };
          const streamKey = stream === 'stdout' ? 'stdout' : 'stderr';
          return {
            ...prev,
            [toolCallId]: {
              ...current,
              [streamKey]: current[streamKey] + delta,
            },
          };
        });
        return;
      }

      // Try structured extraction first, then fall back to raw text
      const extracted = extractProgressMessage(data as ProgressPayload);

      if (extracted) {
        const msgRole =
          extracted.role === 'error'
            ? ('error' as const)
            : extracted.role === 'warning'
              ? ('progress' as const) // warnings render as progress with warning style
              : ('progress' as const);
        // Detect paper_search result from backend events
        let toolName: string | undefined;
        let toolData: unknown;
        // Path A: item/toolResult notification (from turn_event_adapter)
        if (!toolData && data.tool_hint && data.text && !data.stream) {
          const parsed = tryParsePaperSearchResult(data.text);
          if (parsed?.items?.length) {
            toolName = 'paper_search';
            toolData = parsed;
          }
        }
        // Path B: toolExecution/outputDelta from PaperSearchTool itself
        if (!toolData && data.delta && typeof data.delta === 'string') {
          try {
            const inner = JSON.parse(data.delta);
            if (inner?.type === 'paper_search_result' && inner.payload) {
              toolName = 'paper_search';
              toolData = inner.payload;
            }
          } catch {
            /* not JSON, ignore */
          }
        }

        const toolMsg: Message = {
          role: msgRole,
          content: extracted.role === 'warning' ? `⚠️ ${extracted.message}` : extracted.message,
          toolHint: data.tool_hint || toolName === 'paper_search',
          toolCallId: data.tool_call_id,
          toolName,
          toolData,
          toolArgs: data.tool_args
            ? data.tool_args
            : data.tool_call_id
              ? toolArgsByCallId.current.get(data.tool_call_id)
              : undefined,
          timestamp: Date.now(),
        };
        setMessages((prev) => {
          // Tool begin/end events share a tool_call_id: update the existing
          // row instead of stacking a second block, keeping one chain node
          // per tool call.
          if (toolMsg.toolHint && toolMsg.toolCallId) {
            for (let i = prev.length - 1; i >= 0; i -= 1) {
              const m = prev[i];
              if (m.role === 'progress' && m.toolHint && m.toolCallId === toolMsg.toolCallId) {
                const next = [...prev];
                next[i] = {
                  ...m,
                  content: toolMsg.content,
                  toolName: toolMsg.toolName ?? m.toolName,
                  toolData: toolMsg.toolData ?? m.toolData,
                  toolArgs: toolMsg.toolArgs ?? m.toolArgs,
                };
                return next;
              }
            }
          }
          return [...prev, toolMsg];
        });
        // End event carries the tool result — stash web_search output so the
        // row can expand into result cards on click (#539).
        const endCallId = data.tool_call_id;
        const endOutput = data.tool_output;
        if (endOutput && endCallId) {
          setSearchResultsByCallId((prev) => ({
            ...prev,
            [endCallId]: endOutput,
          }));
        }
      } else if (data.tool_hint || data.stream) {
        // tool_hint without text still deserves a line (old behavior for exec hints)
        // but skip completely empty/stream-only events
        return;
      }
      // Otherwise skip — no displayable content

      // Parse file operations from tool hints
      if (data.tool_hint && data.text) {
        const parsed = parseToolHint(data.text);
        if (parsed) trackFile(parsed.path, parsed.op, parsed.truncated);
      }
    });

    const unsubFinal = window.miqi.chat.onFinal((data: ChatFinal) => {
      const _owner = data.session_key ?? sendSessionKey;
      if (_owner !== currentSessionRef.current) {
        var buf = inFlightCacheRef.current.get(_owner);
        if (!buf) { buf = { events: [], userMsgTimestamp: 0 }; inFlightCacheRef.current.set(_owner, buf); }
        buf.events.push({ type: 'final', data, timestamp: Date.now() });
        return;
      }
      clearFinalCleanupTimer();
      if (animId !== null) {
        cancelAnimationFrame(animId);
        animId = null;
      }
      fullContent = data.content;
      displayed = '';
      finalDone = true;
      persistReveal();
      streamingBySession.delete(_owner);
      setCurrentReqId(null);
      // If load() already rendered this final (merged from history/cache), the
      // reply is on screen — don't append a duplicate via the live path.  Just
      // stop streaming; the bubble is already complete.
      if (finalHandledSessions.has(_owner)) {
        finalHandledSessions.delete(_owner);
        setStreaming(false);
        streamingBySession.delete(_owner);
        scheduleFinalCleanup();
        return;
      }
      // Final answer arrived — drop the watchdog "waiting" hint; it must only
      // be visible while the backend is actually working (#539 用户要求).
      if (warnMsgId !== null) {
        const watchdogId = warnMsgId;
        warnMsgId = null;
        setMessages((prev) =>
          prev.filter((m) => !(m.role === 'error' && m.timestamp === watchdogId))
        );
      }
      // Keep the thinking block at its original position in the timeline
      // (before tool calls). A live bubble is finalized in place; otherwise
      // the block is inserted right after the user message. The assistant
      // bubble never re-renders reasoning, so there is no layout jump.
      const hadLiveReasoning = liveReasoningTsRef.current !== null;
      const finalReasoningElapsedS =
        data.reasoning || hadLiveReasoning
          ? Math.round((Date.now() - turnStartMs) / 1000)
          : undefined;
      if (hadLiveReasoning) {
        setMessages((prev) => {
          const liveText = [...prev].reverse().find((m) => m.isLiveReasoning)?.content ?? '';
          const resolved = data.reasoning || liveText;
          return prev.map((m) =>
            m.isLiveReasoning
              ? {
                  ...m,
                  isLiveReasoning: false,
                  content: resolved || m.content,
                  reasoning: resolved || m.content,
                  reasoningElapsedS: finalReasoningElapsedS,
                }
              : m
          );
        });
        flushReasoningRef.current?.(Date.now());
        liveReasoningTsRef.current = null;
      } else if (data.reasoning) {
        const reasoning = data.reasoning;
        const elapsed = finalReasoningElapsedS;
        setMessages((prev) => insertStandaloneReasoning(prev, reasoning, elapsed));
      }
      if (data.tool_calls?.length) {
        // Track file operations from tool_calls for Task Assets panel.
        // Office tools (create_docx, etc.) don't always produce progress
        // hints that match parseToolHint patterns, so we extract file
        // paths directly from the final tool call list.
        for (const tc of (data.tool_calls ?? []) as any[]) {
          const fn = tc?.function || tc?.tool?.function || {};
          const toolName: string = fn?.name || '';
          if (!toolName) continue;
          // Remember call args so the matching tool result can show the exact
          // URL the tool touched (web_fetch etc.) in "查看来源".
          const callId: string = tc?.id || '';
          if (callId && fn?.arguments) {
            try {
              toolArgsByCallId.current.set(callId, JSON.parse(fn.arguments));
            } catch {
              toolArgsByCallId.current.set(callId, fn.arguments);
            }
          }
          const filePath: string = _extractPathFromArgs(fn?.arguments || '{}') || '';
          if (!filePath) continue;
          if (_FILE_WRITE_TOOLS.includes(toolName)) {
            trackFile(filePath, 'write', false);
          } else if (_FILE_READ_TOOLS.includes(toolName)) {
            trackFile(filePath, 'read', false);
          }
        }

        // Reload tracked files from the backend — _persist_tracked_file saves the
        // correct session-relative path (e.g. sessions/<key>/files/report.pdf) while
        // _extractPathFromArgs only sees the bare filename from AI tool call args.
        // Merge backend data on top: it wins when keys collide.
        window.miqi.sessions.getTrackedFiles(currentSessionRef.current!).then(
          (tfResult: any) => {
            const tfList: any[] = tfResult?.tracked_files ?? [];
            if (tfList.length) {
              setTrackedFiles((prev) => {
                const m = new Map(prev.map((f) => [f.path, f]));
                for (const f of tfList) {
                  const np = (f.path as string).replace(/\\/g, '/');
                  m.set(np, { path: np, name: basename(np), op: f.op, lastSeen: Date.now() });
                }
                return Array.from(m.values());
              });
            }
          },
          () => {
            /* non-fatal */
          }
        );

        setMessages((prev) => {
          const cleaned = removeTransientTurnMessagesSinceLastUser(prev);
          // Only append collapsed tool-call group if streaming didn't
          // already render toolHint progress for this turn (avoids dupes).
          const hasToolHints = cleaned.some((m) => m.role === 'progress' && m.toolHint);
          if (hasToolHints) return cleaned;
          const toolMessages = sessionMsgsToUi([
            {
              role: 'assistant',
              content: '',
              tool_calls: data.tool_calls,
              timestamp: new Date().toISOString(),
            },
          ]);
          return [...cleaned, ...toolMessages];
        });
      } else {
        setMessages((prev) => removeTransientTurnMessagesSinceLastUser(prev));
      }
      // Do NOT push an empty assistant bubble here — revealNext creates the
      // bubble lazily once the first chunk is available, so we never flash a
      // blank message box. Handle the empty-reply case (no text at all)
      // immediately instead of waiting on an animation that has nothing to show.
      if (!fullContent) {
        setStreaming(false);
        scheduleFinalCleanup();
        return;
      }
      setStreaming(true);
      animId = requestAnimationFrame(revealNext);
    });

    const unsubError = window.miqi.chat.onError((data: ChatError) => {
      const _owner = data.session_key ?? sendSessionKey;
      if (_owner !== currentSessionRef.current) {
        var buf = inFlightCacheRef.current.get(_owner);
        if (!buf) { buf = { events: [], userMsgTimestamp: 0 }; inFlightCacheRef.current.set(_owner, buf); }
        buf.events.push({ type: 'error', data, timestamp: Date.now() });
        return;
      }
      streamErrorHandled = true;
      if (animId !== null) cancelAnimationFrame(animId);
      const message = sanitizeUiMessage(data.message);
      flushReasoningRef.current?.(Date.now());
      liveReasoningTsRef.current = null;
      setMessages((prev) => [
        ...prev.filter((m) => !m.isLiveReasoning),
        isProviderConfigurationProblem(message, data.code)
          ? createProviderConfigMessage(message)
          : { role: 'error', content: message, timestamp: Date.now() },
      ]);
      setStreaming(false);
      streamingBySession.delete(sendSessionKey);
      sendCleanup();
      cleanupListeners();
    });

    const unsubAborted = window.miqi.chat.onAborted((_data: ChatAborted) => {
      const _owner = _data.session_key ?? sendSessionKey;
      if (_owner !== currentSessionRef.current) {
        var buf = inFlightCacheRef.current.get(_owner);
        if (!buf) { buf = { events: [], userMsgTimestamp: 0 }; inFlightCacheRef.current.set(_owner, buf); }
        buf.events.push({ type: 'aborted', data: _data, timestamp: Date.now() });
        return;
      }
      if (animId !== null) cancelAnimationFrame(animId);
      setStreaming(false);
      streamingBySession.delete(sendSessionKey);
      setCurrentReqId(null);
      flushReasoningRef.current?.(Date.now());
      liveReasoningTsRef.current = null;
      setMessages((prev) => [
        ...prev.filter((m) => !m.isLiveReasoning),
        { role: 'progress', content: '已停止。', timestamp: Date.now() },
      ]);
      sendCleanup();
    });

    unsubsRef.current = [unsubProgress, unsubFinal, unsubError, unsubAborted];

    try {
      // On first message for a new conversation, create a thread with
      // a title derived from the user's first prompt.
      let threadId = currentThreadIdRef.current;
      if (threadId == null) {
        try {
          const title = (text || '新会话').trim().slice(0, 60);
          // Non-blocking: start thread with a timeout so chat.send
          // isn't delayed by a slow bridge restart.  Falls through to
          // chat.send without thread_id on failure.
          // 30s timeout gives sandbox first-init (WSL apt-get 60-120s)
          // a better chance without holding up the UI forever (#311).
          const threadResult = await Promise.race([
            window.miqi.threads.start({
              title,
              session_key: currentSessionRef.current,
            }),
            new Promise<never>((_, reject) =>
              setTimeout(() => reject(new Error('thread/start timeout')), 30_000)
            ),
          ]);
          // Extract thread id from the result
          const thread = (threadResult as any)?.thread;
          if (thread) {
            threadId = thread.id || thread.threadId;
            if (threadId) {
              currentThreadIdRef.current = threadId;
            }
          }
        } catch {
          // If thread/start fails, fall through to chat.send without thread_id
        }
      }

      const key =
        activeThreadId === 'main' ? currentSessionRef.current : `desktop:${activeThreadId}`;
      const chatAttachments = sentAttachments
        .filter((a) => a.type === 'document' && a.dataBase64)
        .map((a) => ({ name: a.name, data_base64: a.dataBase64, mime_type: a.mimeType }));

      // Mark all doc attachments as parsing
      if (sentAttachments.some((a) => a.type === 'document')) {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === 'user' && last.attachments) {
            const updated = last.attachments.map((a) =>
              a.type === 'document' ? { ...a, status: 'parsing' as const } : a
            );
            return [...prev.slice(0, -1), { ...last, attachments: updated }];
          }
          return prev;
        });
      }

      // Fire send — server parses synchronously in _chat_send_handler
      const sendPromise = window.miqi.chat.send(
        content,
        key,
        threadId ?? undefined,
        executionPolicy,
        chatAttachments.length > 0 ? chatAttachments : undefined,
        workspace ?? undefined
      );

      // Mark as done after a tick — server parsing is synchronous, already complete
      if (sentAttachments.some((a) => a.type === 'document')) {
        setTimeout(() => {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === 'user' && last.attachments) {
              const updated = last.attachments.map((a) =>
                a.type === 'document' && a.status === 'parsing'
                  ? { ...a, status: 'done' as const }
                  : a
              );
              return [...prev.slice(0, -1), { ...last, attachments: updated }];
            }
            return prev;
          });
        }, 100);
      }

      await sendPromise;
    } catch (e: any) {
      if (animId !== null) cancelAnimationFrame(animId);
      if (streamErrorHandled) {
        setStreaming(false);
        sendCleanup();
        cleanupListeners();
        return;
      }
      const errMsg = sanitizeUiMessage(e?.message ?? String(e ?? '未知错误'));
      if (isProviderConfigurationProblem(errMsg, e?.code)) {
        setMessages((prev) => [...prev, createProviderConfigMessage(errMsg)]);
      } else if (e?.code) {
        setMessages((prev) => [
          ...prev,
          { role: 'error' as const, content: errMsg, timestamp: Date.now() },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          { role: 'error' as const, content: errMsg, timestamp: Date.now() },
        ]);
      }
      setStreaming(false);
      sendCleanup();
      cleanupListeners();
    }
  }, [input, attachments, streaming, cleanupListeners, onChatFinished, executionPolicy, workspace]);

  // Keep handleSendRef fresh for programmatic sends (regenerate)
  useEffect(() => {
    handleSendRef.current = () => handleSend();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handleSend]);

  // ── Download paper via chat ─────────────────────────────────────
  const handleDownloadPaper = useCallback(
    (paper: PaperItem) => {
      const title = (paper.title || 'this paper').trim();
      const pid = paper.arxiv_id || paper.id || paper.doi || title;
      const instruction = `请下载论文《${title}》的 PDF 文件。paperId: ${pid}`;
      setDownloadingPaperId(paper.id || null);
      // Set input and trigger send on next tick so React state propagates
      setInput(instruction);
      setTimeout(() => {
        const text = instruction.trim();
        if (!text) return;
        // Direct send: bypasses the input-state read in handleSend since
        // we just set it. We inline the send logic here for simplicity.
        window.miqi.chat
          .send(text, sessionKey)
          .then(() => {
            setDownloadingPaperId(null);
          })
          .catch(() => {
            setDownloadingPaperId(null);
          });
      }, 0);
    },
    [sessionKey]
  );

  /** Auto-resize textarea to fit content */
  const adjustTextareaHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  /** Normalise a sandbox-internal path to a host path that can be opened.
   *  Strips /home/miqi/workspace/ prefix so the path resolves correctly on the
   *  host filesystem.  Leaves relative paths and non-sandbox absolute paths
   *  unchanged — they are handled by the IPC handlers. */
  const normalizePath = useCallback((p: string): string => {
    return normalizeSandboxPath(p);
  }, []);

  const handlePreview = useCallback(async (rawPath: string) => {
    const path = normalizePath(rawPath);

    // For document files (PDF, Word, Excel, Markdown, etc.):
    // try in-app parsing first — more reliable than system-open which
    // depends on OS file associations.  Fall back to system default
    // application only when parsing is unavailable.
    const isDocFile = DOCUMENT_SUFFIXES_RE.test(path);
    if (isDocFile) {
      // Collect candidate paths: the tracked path, then try common subdirs
      // (paper_search saves to workspace/papers/, office tools to workspace/ root)
      const candidates = [path];
      const nameOnly = path.replace(/\\/g, '/').split('/').pop()!;
      if (nameOnly !== path) candidates.push(nameOnly);
      if (!path.startsWith('papers/')) candidates.push(`papers/${nameOnly}`);

      for (const candidate of candidates) {
        try {
          const result = await window.miqi.documents.parse(candidate, currentSessionRef.current, {
            preview: true,
          });
          if (result?.text) {
            setPreviewFile({ path: candidate, content: result.text });
            return;
          }
        } catch {
          continue; // try next candidate
        }
      }
    }
    // Open with system default application as fallback
    const result = await window.miqi.files.openExternal(path);
    if (!result?.opened) {
      setPreviewFile({ path, content: `(Could not open file: ${path})` });
    }
  }, []);

  const closePreview = useCallback((e?: React.MouseEvent) => {
    e?.stopPropagation();
    e?.preventDefault();
    previewJustClosed.current = true;
    setPreviewFile(null);
    setTimeout(() => {
      previewJustClosed.current = false;
    }, 300);
  }, []);

  const handleShowDiff = useCallback(async (path: string) => {
    setDiffLoading(true);
    try {
      const result = await window.miqi.files.diff(path, currentSessionRef.current);
      setDiffFile({
        path,
        diff: result.diff,
        original_content: result.original_content,
        current_content: result.current_content,
        has_diff: result.has_diff,
        is_new_file: (result as any).is_new_file,
      });
    } catch {
      setDiffFile({
        path,
        diff: null,
        original_content: null,
        current_content: null,
        has_diff: false,
      });
    } finally {
      setDiffLoading(false);
    }
  }, []);

  const closeDiff = () => setDiffFile(null);

  const handleRevert = useCallback(async () => {
    if (!diffFile || reverting) return;
    setReverting(true);
    try {
      const result = await window.miqi.files.revert(diffFile.path, currentSessionRef.current);
      if (result.reverted) {
        // Refresh the diff view
        await handleShowDiff(diffFile.path);
        // Update tracked files list (file is now back to HEAD)
        setTrackedFiles((prev) => prev.filter((f) => f.path !== diffFile.path));
        // Refresh preview if open
        if (previewFile?.path === diffFile.path) {
          const content = await window.miqi.files.read(diffFile.path, currentSessionRef.current);
          setPreviewFile({
            path: diffFile.path,
            content: content.content ?? '当前文件不是文本内容，无法在聊天预览中显示。',
          });
        }
      }
    } catch {
      // Silently fail - revert button is best-effort
    } finally {
      setReverting(false);
    }
  }, [diffFile, reverting, handleShowDiff, previewFile]);

  /** Accept ALL tracked file changes at once — keep files, discard snapshots. */
  const handleMergeAll = useCallback(async () => {
    if (merging) return;
    const toAccept = trackedFiles.filter(
      (f) => f.op === 'write' || f.op === 'edit' || f.op === 'delete'
    );
    if (toAccept.length === 0) return;
    setMerging(true);
    try {
      await Promise.allSettled(
        toAccept.map((f) => window.miqi.files.accept(f.path, currentSessionRef.current))
      );
      // Reset accepted files to 'read' so they stay visible in Referenced Context
      const acceptedPaths = new Set(toAccept.map((f) => f.path));
      setTrackedFiles((prev) =>
        prev.map((f) => (acceptedPaths.has(f.path) ? { ...f, op: 'read' as const } : f))
      );
    } finally {
      setMerging(false);
    }
  }, [merging, trackedFiles]);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    if (!files.length || !fileInputRef.current) return;
    const dt = new DataTransfer();
    files.forEach((f) => dt.items.add(f));
    fileInputRef.current.files = dt.files;
    fileInputRef.current.dispatchEvent(new Event('change', { bubbles: true }));
  };

  // Handle clipboard paste for files and images (Ctrl+V)
  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.kind !== 'file') continue;
      const file = item.getAsFile();
      if (!file) continue;
      const isDocument = DOCUMENT_SUFFIXES_RE.test(file.name);
      if (isDocument) {
        const reader = new FileReader();
        reader.onload = () => {
          const base64 = (reader.result as string).split(',')[1];
          const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
          const isServerParsed = /^(docx|doc|pptx|ppt|xlsx|xls|odt|odp|ods|rtf)$/i.test(ext);
          const parseStatus: Attachment['status'] = isServerParsed ? 'pending' : 'done';
          setAttachments((prev) => [
            ...prev,
            {
              name: file.name,
              type: 'document',
              dataBase64: base64,
              size: file.size,
              mimeType: file.type || getMimeTypeFromName(file.name),
              status: parseStatus,
            },
          ]);
        };
        reader.readAsDataURL(file);
      } else if (file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = () =>
          setAttachments((prev) => [
            ...prev,
            {
              name: file.name || 'pasted-image.png',
              type: 'image',
              dataUrl: reader.result as string,
              size: file.size,
            },
          ]);
        reader.readAsDataURL(file);
      }
    }
  }, []);

  const handleCopy = (text: string, idx: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  // Associate each assistant answer with the tool URLs that preceded it in
  // the same turn. Memoized — extractMessageSources scans full tool outputs,
  // which would otherwise re-run on every animation frame while streaming.
  const sourcesByMsg = useMemo(() => {
    const map = new Map<Message, MessageSource[]>();
    let pending: MessageSource[] = [];
    let seen = new Set<string>();
    const MAX_SOURCES = 20;
    const merge = (next: MessageSource[]) => {
      for (const s of next) {
        if (seen.has(s.url) || pending.length >= MAX_SOURCES) continue;
        seen.add(s.url);
        pending.push(s);
      }
    };
    for (const m of messages) {
      if (m.role === 'progress') {
        // Tool rows also carry their own references (web_search/web_fetch
        // results) so the chain can show clickable sources inline. Cross-row
        // dedupe: the same RSS link must not repeat on every fetched row.
        const own = extractMessageSources(m).filter((s) => {
          if (seen.has(s.url)) return false;
          seen.add(s.url);
          return true;
        });
        if (own.length > 0) map.set(m, own);
        merge(own);
      } else if (m.role === 'user') {
        pending = [];
        seen = new Set();
      } else if (m.role === 'assistant') {
        map.set(m, pending);
        pending = [];
        seen = new Set();
      }
    }
    return map;
  }, [messages]);

  // Number tool rows within each user turn so they render as a workflow
  // chain (1, 2, 3…) instead of anonymous stacked blocks.
  const toolStepByMsg = useMemo(() => {
    const map = new Map<Message, number>();
    let step = 0;
    for (const m of messages) {
      if (m.role === 'user') {
        step = 0;
      } else if (m.role === 'progress' && m.toolHint) {
        step += 1;
        map.set(m, step);
      }
    }
    return map;
  }, [messages]);

  // Tool rows grouped into collapsible「工具调用 · N」chains for rendering.
  const chatGroups = useMemo(() => groupChatMessages(messages), [messages]);

  /** Retry a user message: rewind to it, resend automatically with a
   *  "answer differently" hint so the model doesn't repeat itself. */
  const handleRetry = useCallback(
    async (msg: Message) => {
      if (streaming) return;
      cleanupListeners();
      const idx = messages.indexOf(msg);
      if (idx >= 0) setMessages((prev) => prev.slice(0, idx));
      setInput(msg.content);
      setAttachments(msg.attachments ?? []);
    },
    [streaming, cleanupListeners, messages]
  );

  const handleRegenerate = useCallback(
    async (assistantMsg: Message) => {
      if (streaming) return;
      const idx = messages.indexOf(assistantMsg);
      if (idx < 0) return;
      let userIdx = -1;
      for (let i = idx - 1; i >= 0; i--) {
        if (messages[i].role === 'user') {
          userIdx = i;
          break;
        }
      }
      if (userIdx < 0) return;
      const userMsg = messages[userIdx];
      retryPayloadRef.current = {
        text: userMsg.content,
        attachments: userMsg.attachments ?? [],
        retry: true,
      };
      setMessages((prev) => prev.slice(0, userIdx)); // handleSend re-appends the user message
      setInput(userMsg.content);
      setAttachments(userMsg.attachments ?? []);
      requestAnimationFrame(() => handleSendRef.current());
    },
    [streaming, messages]
  );

  /* session display name — persisted custom title wins, else first user
     message, else timestamp fallback */
  const sessionTitle = useMemo(() => {
    if (customTitle) return customTitle;
    const firstUserMsg = messages.find((m) => m.role === 'user');
    if (firstUserMsg) {
      return firstUserMsg.content.trim().slice(0, 60);
    }
    // Fallback: format timestamp from session key
    const raw = sessionKey.replace(/^desktop:/, '');
    const ts = parseInt(raw, 10);
    if (!isNaN(ts) && raw.length >= 13) {
      return new Intl.DateTimeFormat('zh-CN', {
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      }).format(new Date(ts));
    }
    return raw.replace(/_/g, ' ') || '新任务';
  }, [customTitle, messages, sessionKey]);

  /* ── session title inline rename (from sidebar rename or header edit) ── */
  const lastRenameVersion = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (renameVersion === lastRenameVersion.current) return;
    lastRenameVersion.current = renameVersion;
    let cancelled = false;
    (async () => {
      try {
        const detail = await window.miqi.sessions.get(sessionKey);
        if (cancelled) return;
        const metaTitle = (detail as any)?.metadata?.title;
        setCustomTitle(typeof metaTitle === 'string' && metaTitle.trim() ? metaTitle : null);
      } catch {
        if (!cancelled) setCustomTitle(null);
      }
    })();
    return () => { cancelled = true; };
  }, [renameVersion, sessionKey]);

  const titleInputRef = useRef<HTMLInputElement>(null);
  const titleSubmitLock = useRef(false);
  useEffect(() => {
    if (editingTitle) {
      titleSubmitLock.current = false; // re-arm for the new edit session
      titleInputRef.current?.focus();
      titleInputRef.current?.select();
    }
  }, [editingTitle]);
  const handleTitleConfirm = useCallback(
    async (value: string) => {
      // Enter unmounts the input, which can fire a trailing blur → guard
      // against confirming the same edit twice.
      if (titleSubmitLock.current) return;
      titleSubmitLock.current = true;
      const trimmed = value.trim();
      if (trimmed) {
        try {
          await window.miqi.sessions.rename(sessionKey, trimmed.slice(0, 100));
          setCustomTitle(trimmed.slice(0, 100));
          onRename?.();
        } catch { /* ignore */ }
      }
      setEditingTitle(false);
    },
    [sessionKey, onRename]
  );

  const taskHeaderInfo = useMemo(() => {
    const latestMessageAt = messages.reduce<number | null>((latest, message) => {
      if (!Number.isFinite(message.timestamp)) return latest;
      return latest === null || message.timestamp > latest ? message.timestamp : latest;
    }, null);
    const updatedAt = latestMessageAt ?? sessionUpdatedAt;
    return {
      updatedLabel: relativeTimeLabel(updatedAt, clockTick),
      fileLabel: `${trackedFiles.length} 个文件`,
      pluginLabel: `${activePluginCount} 个启用插件`,
      meta: buildTaskHeaderMeta(updatedAt, trackedFiles.length, activePluginCount, clockTick),
    };
  }, [activePluginCount, clockTick, messages, sessionUpdatedAt, trackedFiles.length]);

  const getTaskShareSummary = useCallback(
    () =>
      buildTaskShareText({
        title: sessionTitle,
        meta: taskHeaderInfo.meta,
        messages,
        files: trackedFiles,
      }),
    [messages, sessionTitle, taskHeaderInfo.meta, trackedFiles]
  );

  const handleCopyTaskSummary = useCallback(async () => {
    await navigator.clipboard.writeText(getTaskShareSummary());
    showShareFeedback('copied');
  }, [getTaskShareSummary, showShareFeedback]);

  const handleExportTaskMarkdown = useCallback(() => {
    const text = getTaskShareSummary();
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = getTaskShareDownloadName(sessionTitle);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    showShareFeedback('exported');
  }, [getTaskShareSummary, sessionTitle, showShareFeedback]);

  const handleCopyReproContext = useCallback(async () => {
    const text = buildTaskShareText({
      title: sessionTitle,
      meta: taskHeaderInfo.meta,
      messages,
      files: trackedFiles,
    });
    const context = buildTaskReproContext({
      sessionKey,
      title: sessionTitle,
      meta: taskHeaderInfo.meta,
      messages,
      files: trackedFiles,
    });
    await navigator.clipboard.writeText(context || text);
    showShareFeedback('context');
  }, [messages, sessionKey, sessionTitle, showShareFeedback, taskHeaderInfo.meta, trackedFiles]);

  const shareMenuItems = useMemo<ContextMenuAction[]>(
    () => [
      { label: '复制摘要', shortcut: '推荐', onSelect: handleCopyTaskSummary },
      { label: '导出 Markdown', onSelect: handleExportTaskMarkdown },
      {
        label: '复制上下文',
        shortcut: `${messages.filter((message) => message.role === 'user' || message.role === 'assistant').length} 条`,
        divider: true,
        onSelect: handleCopyReproContext,
      },
    ],
    [handleCopyReproContext, handleCopyTaskSummary, handleExportTaskMarkdown, messages]
  );

  const shareButtonLabel =
    shareStatus === 'copied'
      ? '已复制摘要'
      : shareStatus === 'exported'
        ? '已导出'
        : shareStatus === 'context'
          ? '已复制上下文'
          : '分享任务';

  const shareButtonTone = shareStatus === 'idle' ? 'var(--text)' : 'var(--success)';
  const shareButtonBackground = 'var(--surface-muted)';
  const shareButtonBorder = 'var(--border-subtle)';

  return (
    <div
      className="flex flex-col h-full"
      style={previewFile ? { pointerEvents: 'none' } : undefined}
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
      onPaste={handlePaste}
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="image/*,text/*,.md,.markdown,.mdown,.txt,.text,.py,.ts,.js,.json,.csv,.yaml,.yml,.toml,.xml,.env,.log,.sql,.ini,.htaccess,.sh,.bash,.rtf,.pdf,.docx,.pptx,.xlsx,.doc,.ppt,.xls,.odt,.odp,.ods,.html,.htm"
        className="hidden"
        onChange={handleFileChange}
      />

      {/* ── Thread tabs ── */}
      {threads.length > 1 && (
        <div className="flex gap-1 px-2 pt-1 overflow-x-auto border-b border-[var(--border)] shrink-0">
          {threads.map((t) => (
            <button
              key={t.threadId}
              onClick={() => setActiveThreadId(t.threadId)}
              className={cn(
                'px-3 py-1.5 text-xs rounded-t whitespace-nowrap transition-colors',
                activeThreadId === t.threadId
                  ? 'bg-[var(--surface)] text-[var(--text)] border-t border-x border-[var(--border)]'
                  : 'text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-hover)]'
              )}
            >
              {t.label}
              {t.threadId !== 'main' && (
                <button
                  className="ml-1.5 text-[var(--text-muted)] hover:text-[var(--danger)]"
                  onClick={(e) => {
                    e.stopPropagation();
                    setThreads((prev) => prev.filter((th) => th.threadId !== t.threadId));
                    if (activeThreadId === t.threadId) setActiveThreadId('main');
                  }}
                >
                  ×
                </button>
              )}
            </button>
          ))}
        </div>
      )}

      {/* ── Top header bar: Logo | Search | Badges | User ── */}
      <div
        className="flex items-center gap-3 px-5 h-10 border-b shrink-0"
        style={{
          background: 'var(--surface-elevated)',
          borderColor: 'var(--border-subtle)',
        }}
      >
        {/* Left: Logo */}
        <span
          className="text-sm font-bold whitespace-nowrap shrink-0 text-text"
          data-testid="app-title"
        >
          MiQi Desktop
        </span>

        {/* Center: Search */}
        <div
          className="flex-1 max-w-[400px] mx-auto flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs"
          style={{
            background: 'var(--surface-muted)',
            border: '1px solid var(--border-subtle)',
            color: 'var(--text-faint)',
          }}
        >
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <span className="select-none">搜索或输入命令...</span>
        </div>

        {/* Right: Badges + user + actions */}
        <div className="flex items-center gap-2 shrink-0">
          {/* User avatar + name */}
          <div className="flex items-center gap-1.5 pl-2 ml-1 border-l border-border-subtle">
            <div
              className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0"
              style={{ background: 'var(--avatar-dark)' }}
            >
              A
            </div>
            <span className="text-xs whitespace-nowrap text-text-muted">Admin</span>
          </div>

          {/* More menu */}
          <ContextMenu
            items={[
              {
                label: '分享对话',
                onSelect: () => {
                  const text = buildTaskShareText({
                    title: sessionTitle || sessionKey,
                    meta: sessionKey,
                    messages,
                    files: trackedFiles,
                  });
                  navigator.clipboard.writeText(text);
                  showShareFeedback('copied');
                },
              },
              {
                label: '导出对话',
                onSelect: () => {
                  const text = buildTaskShareText({
                    title: sessionTitle || sessionKey,
                    meta: sessionKey,
                    messages,
                    files: trackedFiles,
                  });
                  const link = document.createElement('a');
                  link.download = getTaskShareDownloadName(sessionTitle || sessionKey);
                  link.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
                  link.click();
                  URL.revokeObjectURL(link.href);
                  showShareFeedback('exported');
                },
              },
              {
                label: '归档',
                divider: true,
                onSelect: async () => {
                  try {
                    await window.miqi.sessions.archive(sessionKey);
                    createSession(null);
                  } catch {
                    /* ignore */
                  }
                },
              },
              {
                label: '删除对话',
                danger: true,
                onSelect: async () => {
                  if (!window.confirm('删除此对话？操作不可恢复。')) return;
                  try {
                    await window.miqi.sessions.delete(sessionKey);
                    createSession(null);
                  } catch (e) {
                    console.error('删除失败:', e);
                  }
                },
              },
            ]}
          >
            {({ onContextMenu }) => (
              <Tooltip content="更多对话操作">
                <button
                  className="p-1.5 rounded hover:bg-[var(--surface-muted)] transition-colors"
                  onClick={onContextMenu}
                  aria-label="更多对话操作"
                  title="更多对话操作"
                >
                  <MoreHorizontal size={14} style={{ color: 'var(--text-faint)' }} />
                </button>
              </Tooltip>
            )}
          </ContextMenu>
        </div>
      </div>

      {/* ── Main area: chat + right panel ── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Chat area */}
        <div className="flex flex-col flex-1 overflow-hidden">
          {/* ── Sub header: task title + status (inside chat area) ── */}
          <div
            className="flex items-center gap-3 px-5 min-h-12 border-b shrink-0"
            style={{
              background: 'var(--surface)',
              borderColor: 'var(--border-subtle)',
            }}
          >
            <div className="min-w-0 flex-1 flex items-center gap-2.5">
              {editingTitle ? (
                <input
                  ref={titleInputRef}
                  defaultValue={sessionTitle}
                  maxLength={100}
                  className="text-[16px] font-semibold leading-[1.35] text-text bg-transparent border border-[var(--accent)] rounded px-1.5 py-0.5 min-w-0 focus:outline-none"
                  data-testid="title-inline-input"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleTitleConfirm((e.target as HTMLInputElement).value);
                    if (e.key === 'Escape') {
                      // Cancel: guard so the trailing blur from unmounting the
                      // input doesn't commit the abandoned edit.
                      titleSubmitLock.current = true;
                      setEditingTitle(false);
                    }
                  }}
                  onBlur={(e) => handleTitleConfirm(e.target.value)}
                />
              ) : (
                <h2
                  role="button"
                  tabIndex={0}
                  className="text-[16px] font-semibold truncate leading-[1.35] text-text cursor-pointer hover:text-[var(--accent)] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] rounded"
                  data-testid="chat-title"
                  title="\u70b9\u51fb\u91cd\u547d\u540d"
                  onClick={() => setEditingTitle(true)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setEditingTitle(true);
                    }
                  }}
                >
                  {sessionTitle}
                </h2>
              )}
              <span className="tag-inprogress shrink-0">{'\u8fdb\u884c\u4e2d'}</span>
              <div
                className="flex min-w-0 items-center gap-1.5 shrink-0 text-[12px] leading-none whitespace-nowrap"
                aria-label={taskHeaderInfo.meta}
                style={{ color: 'var(--text-faint)' }}
              >
                <span>{taskHeaderInfo.updatedLabel}</span>
                <span aria-hidden="true">·</span>
                <span>{taskHeaderInfo.fileLabel}</span>
                <span aria-hidden="true">·</span>
                <span>{taskHeaderInfo.pluginLabel}</span>
              </div>
            </div>
            <div
              className="flex shrink-0 items-stretch overflow-hidden rounded-md shadow-[0_1px_0_rgba(18,18,18,0.05)]"
              style={{
                background: shareButtonBackground,
                border: `1px solid ${shareButtonBorder}`,
              }}
            >
              <button
                onClick={handleCopyTaskSummary}
                className="flex h-7 min-w-[96px] items-center justify-center gap-1.5 px-3 text-xs font-semibold transition-colors whitespace-nowrap hover:brightness-95"
                style={{
                  color: shareButtonTone,
                  cursor: 'pointer',
                }}
                title="复制任务摘要"
                aria-label="复制任务摘要"
              >
                {shareStatus === 'idle' ? <Send size={12} /> : <Check size={12} />}
                {shareButtonLabel}
              </button>
              <ContextMenu items={shareMenuItems} minWidth={180}>
                {({ onContextMenu }) => (
                  <Tooltip content="复制摘要、导出 Markdown 或复制上下文">
                    <button
                      onClick={onContextMenu}
                      className="flex h-7 w-7 items-center justify-center transition-colors hover:brightness-95"
                      style={{
                        borderLeft: `1px solid ${shareButtonBorder}`,
                        color: shareStatus === 'idle' ? 'var(--text-muted)' : 'var(--success)',
                      }}
                      title="更多分享方式"
                      aria-label="更多分享方式"
                      aria-haspopup="menu"
                    >
                      <ChevronDown size={12} />
                    </button>
                  </Tooltip>
                )}
              </ContextMenu>
            </div>
            <Tooltip content="显示或隐藏文件面板">
              <button
                onClick={() => setPanelOpen((v) => !v)}
                className="p-1.5 rounded hover:bg-[var(--surface-muted)] transition-colors shrink-0 ml-1"
                title="显示或隐藏文件面板"
                aria-label="显示或隐藏文件面板"
                data-testid="toggle-assets-panel-btn"
              >
                <LayoutGrid size={14} style={{ color: 'var(--text-faint)' }} />
              </button>
            </Tooltip>
          </div>
          {/* Messages */}
          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto"
            style={{ background: 'var(--background)' }}
          >
            <div className="max-w-[760px] mx-auto px-6 py-5 flex flex-col gap-2">
              {!historyLoaded ? (
                <div className="flex items-center justify-center min-h-[300px]">
                  <Loader2 size={16} className="animate-spin text-text-faint" />
                </div>
              ) : messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center gap-4">
                  <div
                    className="w-16 h-16 rounded-2xl flex items-center justify-center text-2xl font-bold text-white shadow-lg"
                    style={{ background: 'var(--avatar-dark)' }}
                  >
                    A
                  </div>
                  <div className="flex flex-col items-center gap-1">
                    <p className="text-[15px] font-medium text-text-muted">
                      从文件、问题或修改请求开始
                    </p>
                    <p className="text-xs text-text-faint">发起一段对话即可开始</p>
                  </div>
                </div>
              ) : (
                chatGroups.map((group, i) =>
                  group.kind === 'chain' ? (
                    <ToolChainGroup
                      key={`chain-${group.rows[0]?.timestamp ?? i}-${i}`}
                      rows={group.rows}
                      done={group.done}
                      sourcesByMsg={sourcesByMsg}
                        searchResultsByCallId={searchResultsByCallId}
                        execOutputs={execOutputs}
                        inlineExecOutput={inlineExecOutput}
                        onCopy={(text) => handleCopy(text, i)}
                        isCopied={copiedIdx === i}
                        onRetry={undefined}
                        onRegenerate={undefined}
                        onOpenProviderSettings={onOpenProviderSettings}
                        onDownloadPaper={handleDownloadPaper}
                        downloadingPaperId={downloadingPaperId}
                      />
                    ) : (
                      <div key={`${group.msg.timestamp}-${i}`}>
                        <MessageBubble
                          msg={group.msg}
                          execOutputs={execOutputs}
                          inlineExecOutput={inlineExecOutput}
                          sources={sourcesByMsg.get(group.msg) ?? []}
                          toolStepIndex={toolStepByMsg.get(group.msg)}
                          isLast={i === chatGroups.length - 1}
                          searchResults={
                            group.msg.toolCallId
                              ? searchResultsByCallId[group.msg.toolCallId]
                              : undefined
                          }
                          onCopy={(text) => handleCopy(text, i)}
                          isCopied={copiedIdx === i}
                          onRetry={() => handleRetry(group.msg)}
                          onRegenerate={() => handleRegenerate(group.msg)}
                          onOpenProviderSettings={onOpenProviderSettings}
                          onDownloadPaper={handleDownloadPaper}
                          downloadingPaperId={downloadingPaperId}
                        />
                      </div>
                    )
                  )
              )}
            </div>
          </div>

          {/* Composer */}
          <div
            className="shrink-0 px-5 pb-4 pt-3"
            style={{
              background: 'var(--background)',
            }}
          >
            <div className="max-w-[760px] mx-auto">
              {attachments.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-2">
                  {attachments.map((att, i) => {
                    const isDoc = att.type === 'document';
                    const cat = isDoc ? getDocCategory(att.name) : null;
                    const isPending = isDoc && (!att.status || att.status === 'pending');
                    const isParsing = isDoc && att.status === 'parsing';
                    const isDone = isDoc && att.status === 'done';
                    const isError = isDoc && att.status === 'error';

                    return (
                      <div
                        key={i}
                        className="flex items-center gap-2 rounded-lg pl-2 pr-1.5 py-1.5 text-xs group max-w-[240px] cursor-pointer hover:brightness-95 transition-all"
                        style={{
                          background: isDoc && cat ? cat.bg : 'var(--surface-muted)',
                          border: `1px solid ${isDoc && cat ? cat.color + '40' : 'var(--border-subtle)'}`,
                        }}
                        onClick={async (e) => {
                          // Ignore clicks that arrive right after closing preview
                          // (the close button click can fall through to the chip behind)
                          if (previewJustClosed.current) return;
                          if (!isDoc || !att.dataBase64) return;
                          const ext = att.name.split('.').pop()?.toLowerCase() ?? '';
                          let previewText = '';

                          // Client-side extraction only (fast, no server round-trip)
                          try {
                            const raw = Uint8Array.from(atob(att.dataBase64), (c) =>
                              c.charCodeAt(0)
                            );
                            if (ext === 'pdf') {
                              previewText = extractPdfText(raw.buffer);
                            } else if (
                              /^(md|markdown|mdown|txt|text|csv|json|ya?ml|xml|py|ts|js|log|html|htm|env|sql|ini|toml|htaccess|sh|bash)$/i.test(
                                ext
                              )
                            ) {
                              previewText = new TextDecoder().decode(raw);
                            } else {
                              previewText = '(Office 文件 —— 发送后服务端解析)';
                            }
                          } catch {
                            previewText = '(无法预览)';
                          }
                          if (!previewText || !previewText.trim()) {
                            previewText = '(扫描件或二进制文件，无文本内容)';
                          }
                          setPreviewFile({
                            path: att.name,
                            content: previewText.slice(0, 50000),
                            dataBase64: att.dataBase64,
                          });
                        }}
                      >
                        {/* File type badge */}
                        {isDoc && cat ? (
                          <span
                            className="shrink-0 rounded font-bold text-[10px] px-1.5 py-0.5 leading-none"
                            style={{ background: cat.color, color: '#fff' }}
                          >
                            {cat.label}
                          </span>
                        ) : att.type === 'image' ? (
                          <Image size={14} className="shrink-0" style={{ color: 'var(--info)' }} />
                        ) : (
                          <FileText size={14} className="shrink-0 text-text-faint" />
                        )}

                        {/* Name + size */}
                        <div className="flex flex-col min-w-0 leading-tight">
                          <span className="truncate font-medium text-text">
                            {att.name.length > 28
                              ? att.name.slice(0, 25) + '…' + att.name.slice(-4)
                              : att.name}
                          </span>
                          <span className="text-[10px] text-text-muted">
                            {formatFileSize(att.size)}
                            {isDoc && isParsing && ' · 解析中…'}
                            {isDoc && isDone && ' · 已就绪'}
                            {isDoc && isError && ' · 解析失败'}
                          </span>
                        </div>

                        {/* Status icon — only after send */}
                        {isDoc && isParsing && (
                          <Loader2
                            size={13}
                            className="shrink-0 animate-spin"
                            style={{ color: cat?.color ?? 'var(--text-faint)' }}
                          />
                        )}
                        {isDoc && isDone && (
                          <CheckCircle
                            size={13}
                            className="shrink-0"
                            style={{ color: '#22c55e' }}
                          />
                        )}
                        {isDoc && isError && (
                          <AlertCircle
                            size={13}
                            className="shrink-0"
                            style={{ color: '#ef4444' }}
                          />
                        )}

                        {/* Remove */}
                        <button
                          onClick={() => removeAttachment(i)}
                          className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-[rgba(0,0,0,0.1)] rounded p-0.5"
                        >
                          <X size={11} style={{ color: 'var(--text-faint)' }} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}

              <div
                className="flex flex-col rounded-3xl px-7 py-3.5 transition-all"
                data-testid="chat-input-container"
                style={{
                  background: 'color-mix(in srgb, var(--surface) 85%, transparent)',
                  backdropFilter: 'blur(16px)',
                  WebkitBackdropFilter: 'blur(16px)',
                  border: '1px solid color-mix(in srgb, var(--border) 60%, transparent)',
                  outline: 'none',
                  boxShadow: '0 -4px 20px rgba(0,0,0,0.06), 0 2px 8px rgba(0,0,0,0.04)',
                }}
              >
                {/* Textarea on top — grows up to 1/3 of viewport (DeepSeek style) */}
                <Textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => {
                    setInput(e.target.value);
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder="请输入消息或拖入文件..."
                  rows={1}
                  allowResize={true}
                  className="w-full border-0 bg-transparent p-0! leading-7! focus:ring-0 focus:border-0 min-h-[52px] max-h-[25vh] text-[15px]"
                  disabled={streaming}
                  style={{ color: 'var(--text)', fieldSizing: 'content' }}
                />
                {/* Icon row at the bottom — no text, like DeepSeek */}
                <div className="flex items-center gap-3 pt-1.5 mt-0.5 border-t border-[var(--border-subtle)]">
                  <ExecutionPolicySelector
                    policy={executionPolicy}
                    onChange={setExecutionPolicy}
                    disabled={streaming}
                    onOpenApprovals={onOpenApprovals}
                  />
                  {/* AI disclaimer — centered in the mode row, fades when typing */}
                  <div className="flex-1 flex items-center justify-center">
                    <span
                      className="text-size-2xs leading-relaxed tracking-wide text-[var(--text-faint)] italic select-none transition-opacity duration-300"
                      style={{ opacity: !input.trim() && attachments.length === 0 ? 1 : 0 }}
                    >
                      AI 也会犯错误，对于重要答案请谨慎验证
                    </span>
                  </div>
                  <button
                    onClick={handleAttachClick}
                    className="shrink-0 p-1.5 rounded hover:bg-[var(--surface-muted)] transition-colors"
                    title="附件或图片"
                    aria-label="附件或图片"
                  >
                    <Paperclip size={15} style={{ color: 'var(--text-faint)' }} />
                  </button>
                  {streaming ? (
                    <button
                      onClick={handleAbort}
                      title="停止生成"
                      aria-label="停止生成"
                      className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center transition-all duration-200 hover:bg-[var(--surface-muted)] active:scale-95"
                    >
                      <Square size={12} style={{ color: 'var(--text-muted)' }} fill="currentColor" />
                    </button>
                  ) : (
                    <button
                      onClick={handleSend}
                      disabled={!input.trim() && attachments.length === 0}
                      title="发送"
                      aria-label="发送"
                      className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center transition-all duration-200 hover:brightness-110 hover:-translate-y-px active:scale-95 disabled:opacity-30 disabled:hover:brightness-100 disabled:hover:translate-y-0 disabled:shadow-none"
                      style={{
                        background:
                          'linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 65%, #000))',
                        boxShadow:
                          '0 2px 10px color-mix(in srgb, var(--accent) 35%, transparent)',
                      }}
                    >
                      <Send size={14} style={{ color: '#fff' }} />
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Inline workspace selector — only before the conversation starts */}
            {historyLoaded && messages.length === 0 && (
              <div className="flex items-center justify-center mt-2" data-testid="inline-workspace-selector">
                <div
                  className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs border shadow-sm"
                  style={{
                    background: 'var(--surface)',
                    borderColor: 'var(--border-subtle)',
                    color: 'var(--text-muted)',
                  }}
                >
                  <Folder size={12} className="shrink-0" />
                  <span className="truncate max-w-[280px]" title={workspace || undefined} data-testid="inline-workspace-path">
                    {workspace ? `工作目录：${workspace}` : '默认工作目录'}
                  </span>
                  <button
                    type="button"
                    onClick={handleOpenWorkspacePicker}
                    disabled={streaming}
                    className="ml-0.5 text-[var(--accent)] hover:underline disabled:opacity-40 disabled:hover:no-underline"
                    title="更换工作目录"
                    data-testid="inline-workspace-change-btn"
                  >
                    更换
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Plan Sidebar ── */}
        {planOpen && plan && (
          <div className="w-72 border-l border-[var(--border)] bg-[var(--surface)] flex flex-col shrink-0">
            <div className="flex items-center justify-between p-2 border-b border-[var(--border)]">
              <span className="text-sm font-semibold truncate">{plan.title}</span>
              <button
                onClick={() => setPlanOpen(false)}
                className="text-[var(--text-muted)] hover:text-[var(--text)]"
              >
                <X size={14} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {plan.steps.map((step) => (
                <div key={step.id} className="flex items-start gap-2 text-xs py-1">
                  <span
                    className={cn(
                      'mt-0.5 w-4 h-4 rounded-full flex items-center justify-center text-[10px] shrink-0',
                      step.status === 'completed' && 'bg-green-500 text-white',
                      step.status === 'in_progress' && 'bg-blue-500 text-white animate-pulse',
                      step.status === 'pending' && 'bg-gray-300 text-gray-600',
                      step.status === 'skipped' && 'bg-gray-200 text-gray-400'
                    )}
                  >
                    {step.status === 'completed' ? '✓' : step.status === 'in_progress' ? '●' : '○'}
                  </span>
                  <span
                    className={cn(
                      step.status === 'skipped' && 'line-through text-[var(--text-muted)]',
                      step.status === 'in_progress' && 'font-medium'
                    )}
                  >
                    {step.description}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Right panel: Task Assets ── */}
        {panelOpen && (
          <div
            data-testid="task-assets-panel"
            className="flex flex-col shrink-0 border-l overflow-y-auto relative"
            style={{
              width: panelWidth,
              background: 'var(--panel-bg)',
              borderColor: 'var(--panel-border)',
            }}
          >
            {/* Resize handle — left edge */}
            <div
              onMouseDown={handlePanelResizeStart}
              className="absolute top-0 left-0 w-1.5 h-full cursor-col-resize hover:bg-[var(--accent)]/30 transition-colors z-10"
              style={{ marginLeft: -2 }}
            />
            <div
              className="flex items-center justify-between px-4 py-3 border-b shrink-0"
              style={{ borderColor: 'var(--panel-border)' }}
            >
              <div className="flex items-center gap-1.5 text-text-muted">
                <LayoutGrid size={13} />
                <span className="text-xs font-semibold text-text" data-testid="task-assets-title">
                  任务资产
                </span>
              </div>
              <span className="text-xs font-medium text-text-faint">{trackedFiles.length}</span>
            </div>

            {trackedFiles.length === 0 ? (
              <div className="flex flex-col items-center justify-center flex-1 px-4 py-8 text-center gap-4">
                <FileText size={28} style={{ color: 'var(--text-faint)', opacity: 0.35 }} />
                <div className="flex flex-col items-center gap-1">
                  <p
                    className="text-[13px] font-medium text-text-muted"
                    data-testid="task-assets-empty"
                  >
                    暂无文件
                  </p>
                  <p className="text-[11px] text-text-faint">Agent 操作会显示在这里</p>
                </div>
              </div>
            ) : (
              <>
                {/* Written / Edited files → Active for Edit */}
                {trackedFiles.filter((f) => f.op === 'write' || f.op === 'edit').length > 0 && (
                  <>
                    <SectionLabel label="编辑中" sectionKey="active-for-edit" />
                    <div className="px-3 pb-3 flex flex-col gap-2">
                      {trackedFiles
                        .filter((f) => f.op === 'write' || f.op === 'edit')
                        .map((f) => (
                          <TrackedFileCard
                            key={f.path}
                            file={f}
                            onPreview={() => handlePreview(f.path)}
                            onDiff={() => handleShowDiff(f.path)}
                          />
                        ))}
                    </div>
                  </>
                )}

                {/* Read files → Referenced Context */}
                {trackedFiles.filter((f) => f.op === 'read').length > 0 && (
                  <>
                    <SectionLabel label="引用上下文" sectionKey="referenced-context" />
                    <div className="px-3 pb-3 flex flex-col gap-2">
                      {trackedFiles
                        .filter((f) => f.op === 'read')
                        .map((f) => (
                          <TrackedFileCard
                            key={f.path}
                            file={f}
                            onPreview={() => handlePreview(f.path)}
                          />
                        ))}
                    </div>
                  </>
                )}

                {/* Deleted files */}
                {trackedFiles.filter((f) => f.op === 'delete').length > 0 && (
                  <>
                    <SectionLabel label="已删除" sectionKey="deleted" />
                    <div className="px-3 pb-3 flex flex-col gap-2">
                      {trackedFiles
                        .filter((f) => f.op === 'delete')
                        .map((f) => (
                          <TrackedFileCard
                            key={f.path}
                            file={f}
                            onPreview={() => handlePreview(f.path)}
                          />
                        ))}
                    </div>
                  </>
                )}
              </>
            )}

            {/* Proposed changes summary */}
            <div className="flex-1" />
            {trackedFiles.filter((f) => f.op === 'write' || f.op === 'edit').length > 0 && (
              <div
                className="border-t mx-3 mt-2 pt-3 pb-3"
                style={{ borderColor: 'var(--panel-border)' }}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-1.5">
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ background: 'var(--warning)' }}
                    />
                    <span className="text-xs font-semibold text-text">修改建议</span>
                  </div>
                  <span className="text-[10px] text-text-faint">
                    {trackedFiles.filter((f) => f.op === 'write' || f.op === 'edit').length} 个文件
                  </span>
                </div>
                <div className="flex flex-col gap-1.5 mb-3">
                  {trackedFiles
                    .filter((f) => f.op === 'write' || f.op === 'edit')
                    .slice(0, 3)
                    .map((f) => (
                      <div
                        key={f.path}
                        className="flex items-center gap-1.5 rounded-lg px-2.5 py-2"
                        style={{
                          background: 'var(--surface-muted)',
                          border: '1px solid var(--border-subtle)',
                        }}
                      >
                        <FileText size={11} style={{ color: 'var(--info)' }} className="shrink-0" />
                        <span className="text-[11px] truncate flex-1 text-text" title={f.path}>
                          {f.name}
                        </span>
                        <span
                          className="text-[9px] px-1.5 py-0.5 rounded font-medium shrink-0"
                          style={{
                            background: f.op === 'write' ? 'var(--accent)' : 'rgba(234,179,8,0.15)',
                            color: f.op === 'write' ? 'var(--accent-text)' : 'var(--warning)',
                          }}
                        >
                          {f.op.toUpperCase()}
                        </span>
                        <button
                          onClick={() => handleShowDiff(f.path)}
                          className="p-1 rounded transition-colors shrink-0 text-text-faint"
                          title="Compare diff"
                        >
                          <GitCompare size={11} />
                        </button>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Merge all */}
            <div className="px-3 pb-4 shrink-0">
              <button
                onClick={handleMergeAll}
                disabled={merging || trackedFiles.length === 0}
                className={cn(
                  'w-full py-2 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition duration-200',
                  merging || trackedFiles.length === 0 ? 'cursor-not-allowed' : 'hover:opacity-90'
                )}
                style={{
                  background:
                    merging || trackedFiles.length === 0 ? 'var(--surface-muted)' : 'var(--accent)',
                  color:
                    merging || trackedFiles.length === 0
                      ? 'var(--text-faint)'
                      : 'var(--accent-text)',
                  opacity: merging || trackedFiles.length === 0 ? 0.5 : 1,
                }}
              >
                {merging ? <Loader2 size={13} className="animate-spin" /> : <GitMerge size={13} />}
                {merging ? '合并中...' : '合并所有更改'}
              </button>
              {trackedFiles.length === 0 && (
                <div className="flex items-center justify-center mt-2 py-1.5">
                  <span className="text-xs text-text-faint">跟踪文件变更后将在此显示合并选项</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── File Preview Modal ── */}
      {previewFile && (
        <Modal
          open={!!previewFile}
          onOpenChange={(o) => {
            if (!o) closePreview();
          }}
          hideClose
        >
          <div
            className="flex flex-col rounded-xl shadow-2xl overflow-hidden"
            style={{
              width: 780,
              maxHeight: '85vh',
              background: 'var(--surface-elevated)',
              border: '1px solid var(--border)',
              pointerEvents: 'auto',
            }}
            onClick={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b shrink-0 border-border-subtle">
              <div className="flex items-center gap-2 min-w-0 flex-1">
                {PDF_FILE_RE.test(previewFile.path) ? (
                  <FileText size={14} style={{ color: '#ef4444' }} className="shrink-0" />
                ) : /\.(xlsx|xls|csv|ods)$/i.test(previewFile.path) ? (
                  <FileSpreadsheet size={14} style={{ color: '#22c55e' }} className="shrink-0" />
                ) : /\.(pptx|ppt|odp)$/i.test(previewFile.path) ? (
                  <FileBarChart size={14} style={{ color: '#f97316' }} className="shrink-0" />
                ) : (
                  <FileType size={14} style={{ color: 'var(--info)' }} className="shrink-0" />
                )}
                <span
                  className="text-[11px] font-mono break-all leading-relaxed text-text-muted"
                  title={previewFile.path}
                >
                  {previewFile.path}
                </span>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={async () => {
                    if (previewFile.dataBase64) {
                      const tmp = `_open_${Date.now()}_${previewFile.path}`;
                      try {
                        await window.miqi.files.write(tmp, '', undefined, previewFile.dataBase64);
                        await window.miqi.files.openExternal(tmp);
                      } catch {
                        /* fallback */
                      }
                    } else {
                      window.miqi.files.openExternal(previewFile.path);
                    }
                  }}
                  className="flex items-center gap-1 px-2 py-1 rounded text-[11px] text-[var(--accent)] hover:bg-[var(--accent-soft)] transition-colors"
                  title="用系统默认应用打开"
                >
                  <ExternalLink size={12} />
                  <span>系统应用打开</span>
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    closePreview(e);
                  }}
                  className="p-1 rounded hover:bg-[var(--surface-muted)] transition-colors"
                >
                  <X size={14} style={{ color: 'var(--text-faint)' }} />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto p-4">
              <pre className="text-xs font-mono leading-relaxed whitespace-pre-wrap break-all text-text-muted">
                {previewFile.content}
              </pre>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Diff Modal ── */}
      {diffFile && (
        <Modal
          open={!!diffFile}
          onOpenChange={(o) => {
            if (!o) closeDiff();
          }}
          hideClose
        >
          <div
            className="flex flex-col rounded-xl shadow-2xl overflow-hidden"
            style={{
              width: 900,
              maxHeight: '85vh',
              background: 'var(--surface-elevated)',
              border: '1px solid var(--border)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b shrink-0 border-border-subtle">
              <div className="flex items-center gap-2 min-w-0">
                <GitCompare size={14} style={{ color: 'var(--warning)' }} className="shrink-0" />
                <span className="text-sm font-medium truncate text-text" title={diffFile.path}>
                  {diffFile.path.split(/[/\\]/).pop()}
                </span>
                {!diffLoading && diffFile.has_diff && (
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0"
                    style={{
                      background: 'rgba(234,179,8,0.15)',
                      color: 'var(--warning)',
                    }}
                  >
                    MODIFIED
                  </span>
                )}
                {!diffLoading && diffFile.has_diff && (diffFile as any).is_new_file && (
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0"
                    style={{
                      background: 'rgba(34,197,94,0.15)',
                      color: '#4ade80',
                    }}
                  >
                    NEW FILE
                  </span>
                )}
                {!diffLoading && !diffFile.has_diff && (
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0"
                    style={{
                      background: 'var(--surface-muted)',
                      color: 'var(--text-faint)',
                    }}
                  >
                    NO CHANGES
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                {!diffLoading && diffFile.has_diff && (
                  <button
                    onClick={handleRevert}
                    disabled={reverting}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
                    style={{
                      background: reverting ? 'var(--surface-muted)' : 'rgba(239,68,68,0.15)',
                      color: reverting ? 'var(--text-faint)' : 'var(--danger)',
                      border: '1px solid var(--danger)',
                    }}
                    title="还原到 HEAD（撤销所有改动）"
                  >
                    <Undo2 size={12} className={reverting ? 'animate-spin' : ''} />
                    {reverting ? '正在还原…' : '还原'}
                  </button>
                )}
                <button
                  onClick={closeDiff}
                  className="p-1 rounded hover:bg-[var(--surface-muted)] transition-colors shrink-0"
                >
                  <X size={14} style={{ color: 'var(--text-faint)' }} />
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto">
              {diffLoading ? (
                <div className="flex items-center justify-center h-48">
                  <Loader2 size={24} className="animate-spin text-text-faint" />
                  <span className="ml-2 text-sm text-text-faint">Loading diff...</span>
                </div>
              ) : diffFile.diff ? (
                <DiffView diff={diffFile.diff} />
              ) : diffFile.original_content !== null && diffFile.current_content !== null ? (
                /* No snapshot diff but we have both versions — show side by side */
                <div className="flex h-full" style={{ minHeight: 400 }}>
                  <div className="flex-1 p-4 overflow-auto border-r border-border-subtle">
                    <div className="text-[10px] font-semibold uppercase tracking-wider mb-2 text-text-faint">
                      Original
                    </div>
                    <pre className="text-xs font-mono leading-relaxed whitespace-pre-wrap break-all text-text-muted">
                      {diffFile.original_content || '(empty)'}
                    </pre>
                  </div>
                  <div className="flex-1 p-4 overflow-auto">
                    <div className="text-[10px] font-semibold uppercase tracking-wider mb-2 text-text-faint">
                      Current
                    </div>
                    <pre className="text-xs font-mono leading-relaxed whitespace-pre-wrap break-all text-text">
                      {diffFile.current_content || '(empty)'}
                    </pre>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center h-48">
                  <span className="text-sm text-text-faint">
                    {diffFile.original_content === null && diffFile.current_content === null
                      ? '无快照可用 — 此文件未在本会话中修改'
                      : '未检测到变更'}
                  </span>
                </div>
              )}
            </div>
          </div>
        </Modal>
      )}

      {/* ── Workspace Picker Modal ── */}
      <Modal
        open={workspacePickerOpen}
        onOpenChange={(o) => { if (!o) setWorkspacePickerOpen(false); }}
        hideClose
      >
        <div
          className="flex flex-col rounded-xl shadow-2xl"
          style={{
            width: 420,
            maxHeight: '70vh',
            background: 'var(--surface-elevated)',
            border: '1px solid var(--border)',
            pointerEvents: 'auto',
          }}
          onClick={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
          data-testid="workspace-picker-modal"
        >
          <div className="flex items-center justify-between px-4 py-3 border-b shrink-0 border-border-subtle">
            <div className="flex items-center gap-2">
              <Folder size={16} style={{ color: 'var(--accent)' }} />
              <span className="text-sm font-medium text-[var(--text)]">选择工作目录</span>
            </div>
            <button
              onClick={() => setWorkspacePickerOpen(false)}
              className="p-1 rounded hover:bg-[var(--surface-muted)] transition-colors"
            >
              <X size={14} style={{ color: 'var(--text-faint)' }} />
            </button>
          </div>

          <div className="flex-1 overflow-auto p-3 flex flex-col gap-2">
            {/* Recent workspaces */}
            {recentWorkspaces.length > 0 && (
              <>
                <div className="text-[10px] font-semibold uppercase tracking-wider text-text-faint px-1 pt-1 pb-0.5" data-testid="workspace-picker-recent-label">
                  最近使用
                </div>
                {recentWorkspaces.map((ws, idx) => (
                  <button
                    key={ws}
                    onClick={() => createSession(ws)}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-colors hover:bg-[var(--surface-muted)] w-full"
                    data-testid={`workspace-picker-recent-${idx}`}
                  >
                    <FolderCheck size={14} style={{ color: 'var(--text-muted)' }} className="shrink-0" />
                    <span
                      className="text-xs text-[var(--text)] truncate"
                      title={ws}
                    >
                      {ws}
                    </span>
                  </button>
                ))}
                <div className="border-t border-border-subtle my-1" />
              </>
            )}

            {/* Browse button */}
            <button
              onClick={async () => {
                setWorkspacePickerOpen(false);
                try {
                  const dir = await window.miqi.dialog.openDirectory();
                  createSession(dir ?? null);
                } catch {
                  createSession(null);
                }
              }}
              className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-left transition-colors hover:bg-[var(--surface-muted)] w-full"
              data-testid="workspace-picker-browse"
            >
              <FolderOpen size={14} style={{ color: 'var(--accent)' }} className="shrink-0" />
              <span className="text-xs text-[var(--accent)]">浏览...</span>
            </button>

            {/* Default workspace */}
            <button
              onClick={() => createSession(null)}
              className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-left transition-colors hover:bg-[var(--surface-muted)] w-full"
              data-testid="workspace-picker-default"
            >
              <Folder size={14} style={{ color: 'var(--text-muted)' }} className="shrink-0" />
              <span className="text-xs text-[var(--text-muted)]">使用默认工作目录</span>
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

/* ─── Sub-components ──────────────────────────────────────────────── */

/** Renders a unified diff string with syntax-highlighted +/- lines. */

function SectionLabel({ label, sectionKey }: { label: string; sectionKey: string }) {
  const testId = `section-label-${sectionKey}`;
  return (
    <div
      className="px-4 pt-3 pb-1.5 text-[10px] font-semibold uppercase tracking-widest text-text-faint"
      data-testid={testId}
    >
      {label}
    </div>
  );
}

/** Tool-chain group: while the turn runs the numbered steps stay visible;
 *  once the final answer arrives the whole chain collapses into one
 *  「工具调用 · N」block (click to re-expand). #539 用户要求。 */
function ToolChainGroup({
  rows,
  done,
  sourcesByMsg,
  searchResultsByCallId,
  ...bubbleProps
}: {
  rows: Message[];
  done: boolean;
  sourcesByMsg: Map<Message, MessageSource[]>;
  searchResultsByCallId: Record<string, string>;
} & Omit<
  ComponentProps<typeof MessageBubble>,
  'msg' | 'sources' | 'toolStepIndex' | 'isLastToolRow' | 'isLast'
>) {
  const [open, setOpen] = useState(true);
  const autoCollapsedRef = useRef(false);
  // Auto-fold once, when the turn completes (a later manual expand is kept).
  useEffect(() => {
    if (done && !autoCollapsedRef.current) {
      autoCollapsedRef.current = true;
      const t = setTimeout(() => setOpen(false), 1500);
      return () => clearTimeout(t);
    }
  }, [done]);

  const label = `工具调用 · ${rows.length}`;
  return (
    <div className="my-0.5 flex min-w-0">
      <div className="flex w-4 flex-col items-center self-stretch">
        <span className="text-[13px] leading-none">🔧</span>
        <span className="mt-0.5 w-[2px] flex-1 min-h-2 rounded-full" style={{ background: 'var(--border-subtle)' }} />
      </div>
      <div className="min-w-0 flex-1 pl-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1.5 py-0.5 text-xs cursor-pointer select-none transition-opacity hover:opacity-75"
          style={{ color: 'var(--info)' }}
          aria-expanded={open}
        >
          <span>{label}</span>
          <ChevronDown
            size={11}
            className="shrink-0 transition-transform opacity-60"
            style={{ transform: open ? 'none' : 'rotate(-90deg)' }}
          />
        </button>
        {open && (
          <div className="mt-0.5 flex flex-col">
            {rows.map((row, i) => (
              <MessageBubble
                key={`${row.timestamp}-${i}`}
                msg={row}
                sources={sourcesByMsg.get(row) ?? []}
                toolStepIndex={i + 1}
                isLastToolRow={i === rows.length - 1}
                isLast={false}
                searchResults={
                  row.toolCallId ? searchResultsByCallId[row.toolCallId] : undefined
                }
                {...bubbleProps}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MessageBubble({
  msg,
  execOutputs,
  inlineExecOutput,
  isLast,
  onCopy,
  isCopied,
  onRetry,
  onOpenProviderSettings,
  onDownloadPaper,
  downloadingPaperId,
  sources,
  toolStepIndex,
  isLastToolRow,
  searchResults,
}: {
  msg: Message;
  execOutputs: Record<string, { stdout: string; stderr: string; running: boolean }>;
  inlineExecOutput: boolean;
  isLast: boolean;
  onCopy: (text: string) => void;
  isCopied: boolean;
  onRetry?: () => void;
  onRegenerate?: () => void;
  onOpenProviderSettings?: () => void;
  onDownloadPaper?: (paper: PaperItem) => void;
  downloadingPaperId?: string | null;
  /** Reference URLs collected from the tool calls preceding this answer */
  sources?: MessageSource[];
  /** Workflow step number when this progress row is a tool call. */
  toolStepIndex?: number;
  /** True when this is the last tool row of the turn — hides the ↓ arrow. */
  isLastToolRow?: boolean;
  /** web_search result text for this row (click-to-expand cards). */
  searchResults?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  if (msg.role === 'progress') {
    // Thinking blocks live in the timeline as their own quiet block, both
    // while streaming and after the turn finishes. Issue #539.
    if (msg.reasoning) {
      return (
        <ThinkBlock
          reasoning={msg.reasoning}
          defaultOpen={msg.isLiveReasoning}
          elapsedSeconds={msg.reasoningElapsedS}
          live={msg.isLiveReasoning}
        />
      );
    }
    // ── Paper search result: render formatted cards ──────────────
    if (msg.toolName === 'paper_search' && msg.toolData) {
      return (
        <PaperSearchResult
          data={msg.toolData as PaperSearchPayload}
          onDownloadPaper={onDownloadPaper || (() => {})}
          downloadingId={downloadingPaperId || null}
        />
      );
    }

    const isCollapsed = msg.collapsed && !expanded;
    const activities = groupToolActivities(parseToolActivity(msg.content));
    // Restored tool results carry raw OUTPUT in content — never parse that
    // into pseudo-activities; the summary already reads "执行命令 · cp …".
    const toolLabel = msg.toolOutput
      ? msg.summary || '工具调用'
      : toolChainLabel(activities, msg.toolArgs, msg.summary);
    const isToolRow = !!msg.toolHint;
    if (isToolRow) {
      const iconName = msg.toolName || activities[0]?.name || '';
      const isSearch = msg.toolName === 'web_search';
      // web_search output renders as clickable result cards. Live rows read
      // the stashed end-event output; restored rows parse the stored content.
      // Both stack under the label row with the left rule running through
      // (用户要求：URL 往下堆叠、竖线贯穿、点击搜索行直接出结果卡片).
      const results =
        isSearch && !isCollapsed
          ? parseWebSearchResults(searchResults ?? msg.content)
          : [];
      const canExpandSearch = isSearch && results.length > 0;
      return (
        <div className="flex items-start gap-2 py-0.5">
          <div className="flex w-4 flex-col items-center self-stretch">
            <span className="text-[13px] leading-none">{toolIconEmoji(iconName)}</span>
            {toolStepIndex ? (
              <span className="mt-0.5 text-[9px] leading-none tabular-nums" style={{ color: 'var(--info)' }}>
                {String(toolStepIndex).padStart(2, '0')}
              </span>
            ) : null}
            <span className="mt-0.5 w-[2px] flex-1 min-h-2 rounded-full" style={{ background: 'var(--border-subtle)' }} />
            {!isLastToolRow && (
              <ArrowDown size={10} className="shrink-0" style={{ color: 'var(--info)', opacity: 0.55 }} />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <button
              type="button"
              onClick={canExpandSearch ? () => setSearchOpen((v) => !v) : undefined}
              className={cn(
                'block min-w-0 text-left text-[11px] leading-4 break-all transition-opacity',
                canExpandSearch && 'cursor-pointer select-none hover:opacity-80'
              )}
              style={{ color: 'var(--info)' }}
              aria-expanded={canExpandSearch ? searchOpen : undefined}
            >
              {toolLabel}
              {canExpandSearch && (
                <ChevronDown
                  size={11}
                  className="ml-1 inline-block shrink-0 align-middle transition-transform opacity-60"
                  style={{ transform: searchOpen ? 'none' : 'rotate(-90deg)' }}
                />
              )}
            </button>
            {searchOpen && results.length > 0 && (
              <div className="mt-1 flex flex-col gap-1.5">
                {results.map((r) => (
                  <a
                    key={r.url}
                    href={r.url}
                    target="_blank"
                    rel="noreferrer"
                    title={r.url}
                    className="block rounded-lg border p-2 transition-colors hover:border-[var(--info)]"
                    style={{ borderColor: 'var(--border-subtle)' }}
                  >
                    <div className="flex items-center gap-1.5 text-[11px]" style={{ color: 'var(--info)' }}>
                      <img
                        src={`https://${hostOf(r.url)}/favicon.ico`}
                        alt=""
                        loading="lazy"
                        className="h-3 w-3 rounded-[3px]"
                        onError={(e) => {
                          (e.currentTarget as HTMLImageElement).style.display = 'none';
                        }}
                      />
                      <span className="truncate font-medium">{hostOf(r.url)}</span>
                    </div>
                    <div className="mt-0.5 truncate text-xs font-medium">{r.title}</div>
                    {r.snippet && (
                      <div className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                        {r.snippet}
                      </div>
                    )}
                  </a>
                ))}
              </div>
            )}
            {sources && sources.length > 0 && (
              <div className="mt-1 flex flex-col gap-1">
                {sources.map((s) => (
                  <a
                    key={s.url}
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    title={s.url}
                    className="flex min-w-0 items-center gap-1.5 text-[11px] leading-4 transition-opacity hover:opacity-80"
                    style={{ color: 'var(--info)' }}
                  >
                    <img
                      src={`https://${hostOf(s.url)}/favicon.ico`}
                      alt=""
                      loading="lazy"
                      className="h-3 w-3 shrink-0 rounded-[3px]"
                      onError={(e) => {
                        (e.currentTarget as HTMLImageElement).style.display = 'none';
                      }}
                    />
                    <span className="shrink-0 font-medium">{hostOf(s.url)}</span>
                    <span className="truncate opacity-70">{s.url.replace(/^https?:\/\//, '')}</span>
                  </a>
                ))}
              </div>
            )}
            {inlineExecOutput && msg.toolCallId && execOutputs[msg.toolCallId] && (
              <div className="mt-1 p-2 bg-black/80 text-green-400 text-[11px] font-mono rounded max-h-48 overflow-y-auto border border-gray-700">
                <pre
                  className="whitespace-pre-wrap"
                  style={{ background: 'transparent', border: 'none', borderRadius: 0, padding: 0, margin: 0 }}
                >
                  {execOutputs[msg.toolCallId].stdout}
                  {execOutputs[msg.toolCallId].stderr ? (
                    <span className="text-red-400">{execOutputs[msg.toolCallId].stderr}</span>
                  ) : null}
                </pre>
                {execOutputs[msg.toolCallId].running && (
                  <span className="inline-block w-1.5 h-3 bg-green-400 animate-pulse ml-0.5 align-middle" />
                )}
              </div>
            )}
            {!isCollapsed && msg.toolOutput && results.length === 0 && (
              <div className="mt-1 max-h-48 overflow-y-auto rounded border border-gray-700 bg-black/80 p-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-all" style={{ color: '#d1d5db' }}>
                {msg.content}
              </div>
            )}
          </div>
        </div>
      );
    }
    return (
      <div className="min-w-0 text-xs">
        <button
          type="button"
          onClick={msg.collapsed ? () => setExpanded((v) => !v) : undefined}
          className={cn(
            'inline-flex max-w-full items-center gap-1 px-1 py-0.5 text-[11px] transition-opacity',
            msg.collapsed && 'cursor-pointer select-none',
            isToolRow ? 'hover:opacity-80' : 'hover:opacity-75'
          )}
          style={
            isToolRow
              ? { color: 'var(--info)' }
              : { color: 'var(--text-muted)' }
          }
        >
          {isToolRow ? (
            <span className="text-[12px] leading-none">{toolIconEmoji(activities[0]?.name ?? '')}</span>
          ) : isLast ? (
            <Loader2 size={11} className="shrink-0 animate-spin opacity-70" />
          ) : (
            <CheckCircle size={11} className="shrink-0 opacity-70" />
          )}
          <span className="truncate">{toolLabel}</span>
          {msg.collapsed &&
            (isCollapsed ? (
              <ChevronRight size={11} className="shrink-0 opacity-60" />
            ) : (
              <ChevronDown size={11} className="shrink-0 opacity-60" />
            ))}
        </button>
        {!isCollapsed && !msg.toolOutput && activities.length > 0 && (
          <div className="mt-0.5 flex flex-col gap-0.5 pl-0.5">
            {activities.map((act, i) => (
              <span key={i} className="text-[11px]" style={{ color: 'var(--info)' }}>
                {toolDisplayName(act.name)}
                {act.duration ? ` · ${act.duration}` : ''}
              </span>
            ))}
          </div>
        )}
        {/* Inline exec output (Phase 7.4) — gated by ui.inlineExecOutput setting */}
        {inlineExecOutput && msg.toolCallId && execOutputs[msg.toolCallId] && (
          <div className="ml-5 mt-1 p-2 bg-black/80 text-green-400 text-[11px] font-mono rounded max-h-48 overflow-y-auto border border-gray-700">
            <pre
              className="whitespace-pre-wrap"
              style={{ background: 'transparent', border: 'none', borderRadius: 0, padding: 0, margin: 0 }}
            >
              {execOutputs[msg.toolCallId].stdout}
              {execOutputs[msg.toolCallId].stderr ? (
                <span className="text-red-400">{execOutputs[msg.toolCallId].stderr}</span>
              ) : null}
            </pre>
            {execOutputs[msg.toolCallId].running && (
              <span className="inline-block w-1.5 h-3 bg-green-400 animate-pulse ml-0.5 align-middle" />
            )}
          </div>
        )}
      </div>
    );
  }
  if (msg.role === 'error') {
    return (
      <div className="flex items-start gap-3">
        <AgentAvatar />
        <div
          className="text-sm rounded-2xl px-4 py-3"
          style={{
            background: 'var(--danger-bg)',
            color: 'var(--danger)',
            border: '1px solid var(--danger)',
          }}
        >
          <div className="whitespace-pre-wrap break-words">{msg.content}</div>
          {msg.action === 'open-provider-settings' && onOpenProviderSettings && (
            <button
              type="button"
              onClick={onOpenProviderSettings}
              className="mt-3 inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors"
              style={{
                background: 'var(--danger)',
                color: 'var(--danger-bg)',
              }}
            >
              <Settings size={13} />
              {msg.actionLabel ?? '配置 Provider'}
            </button>
          )}
        </div>
      </div>
    );
  }

  if (msg.role === 'subagent') {
    return (
      <div className="flex items-start gap-3">
        <GitMerge size={18} style={{ color: 'var(--accent)', marginTop: 6 }} />
        <div
          className="text-sm rounded-2xl px-4 py-3 prose prose-sm max-w-none break-words overflow-x-auto"
          style={{
            background: 'var(--surface-muted)',
            color: 'var(--text)',
            border: '1px solid var(--border-subtle)',
            maxWidth: '82%',
            minWidth: 0,
          }}
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
        </div>
      </div>
    );
  }

  const isUser = msg.role === 'user';
  const hasCodeBlock = /```[\s\S]*?```/.test(msg.content);

  const contextItems: ContextMenuAction[] = isUser
    ? [
        { label: '复制文本', onSelect: () => onCopy(msg.content) },
        { label: '重试', onSelect: () => onRetry?.() },
      ]
    : [
        { label: '复制文本', onSelect: () => onCopy(msg.content) },
        ...(hasCodeBlock
          ? [
              {
                label: '复制代码',
                onSelect: () => {
                  const codeMatch = msg.content.match(/```[\s\S]*?```/g);
                  if (codeMatch) {
                    const code = codeMatch
                      .map((b) => b.replace(/```\w*\n?/g, '').replace(/```$/g, ''))
                      .join('\n\n');
                    navigator.clipboard.writeText(code).catch(() => {});
                  }
                },
              },
            ]
          : []),
      ];

  return (
    <ContextMenu items={contextItems}>
      {({ onContextMenu }) => (
        <div
          className={cn('flex items-start gap-3', isUser && 'justify-end')}
          onContextMenu={onContextMenu}
          data-testid={isUser ? 'chat-message-user' : 'chat-message-assistant'}
        >
          {!isUser && <AgentAvatar />}

          <div
            className={cn(
              'group flex flex-col gap-1.5',
              isUser ? 'items-end max-w-[70%]' : 'max-w-[82%]'
            )}
          >
            {/* image attachments */}
            {msg.attachments
              ?.filter((a) => a.type === 'image')
              .map((att, i) => (
                <img
                  key={i}
                  src={att.dataUrl}
                  alt={att.name}
                  className="rounded-xl max-w-[280px] max-h-[200px] object-cover"
                  style={{ border: '1px solid var(--border-subtle)' }}
                />
              ))}
            {/* text attachments */}
            {msg.attachments
              ?.filter((a) => a.type === 'text')
              .map((att, i) => (
                <div
                  key={i}
                  className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs"
                  style={{
                    background: 'var(--surface-muted)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-muted)',
                  }}
                >
                  <FileText size={12} className="shrink-0 text-text-faint" />
                  <span>{att.name}</span>
                </div>
              ))}
            {/* document attachments */}
            {msg.attachments
              ?.filter((a) => a.type === 'document')
              .map((att, i) => {
                const cat = getDocCategory(att.name);
                const isDone = !att.status || att.status === 'done';
                const isParsing = att.status === 'parsing';
                return (
                  <div
                    key={i}
                    className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs transition-all duration-500"
                    style={{
                      background: isDone && cat ? cat.bg : 'var(--surface-muted)',
                      border: `1px solid ${isDone && cat ? cat.color + '40' : 'var(--border-subtle)'}`,
                      color: isDone && cat ? cat.color : 'var(--text-muted)',
                      opacity: isDone ? 1 : 0.7,
                    }}
                  >
                    <span
                      className="shrink-0 rounded font-bold text-[10px] px-1 py-0.5 leading-none text-white"
                      style={{ background: isDone && cat ? cat.color : 'var(--text-faint)' }}
                    >
                      {cat ? cat.label : 'FILE'}
                    </span>
                    <span>
                      {att.name} ({formatFileSize(att.size)})
                    </span>
                    {isParsing && (
                      <Loader2 size={11} className="shrink-0 animate-spin text-text-muted" />
                    )}
                    {isDone && (
                      <CheckCircle size={11} className="shrink-0" style={{ color: '#22c55e' }} />
                    )}
                  </div>
                );
              })}
            {/* Always clean injected document text from content — shown as chips only when attachments are missing */}
            {isUser &&
              (() => {
                const { cleanContent, chips } = extractFileChips(msg.content);
                // Always store cleaned content so the bubble renders without injected text
                (msg as any).__cleanContent = cleanContent;
                // Only show historical chips when there are no real attachments (avoids duplicates)
                if (chips.length === 0 || (msg.attachments && msg.attachments.length > 0))
                  return null;
                return chips.map((chip, i) => (
                  <div
                    key={`hist-${i}`}
                    className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs"
                    style={{
                      background: chip.category.bg,
                      border: `1px solid ${chip.category.color}40`,
                      color: chip.category.color,
                    }}
                  >
                    <span
                      className="shrink-0 rounded font-bold text-[10px] px-1 py-0.5 leading-none text-white"
                      style={{ background: chip.category.color }}
                    >
                      {chip.category.label}
                    </span>
                    <span>{chip.name}</span>
                    <CheckCircle size={11} className="shrink-0" style={{ color: '#22c55e' }} />
                  </div>
                ));
              })()}

            {/* Main bubble */}
            <div
              className="text-sm leading-relaxed rounded-2xl px-4 py-3"
              style={
                isUser
                  ? { background: 'var(--bubble-user-bg)', color: 'var(--bubble-user-text)' }
                  : {
                      background: 'var(--bubble-ai-bg)',
                      color: 'var(--bubble-ai-text)',
                      border: '1px solid var(--bubble-ai-border)',
                    }
              }
            >
              <ErrorBoundary
                fallback={(error, reset) => (
                  <div
                    className="text-xs p-2 rounded"
                    style={{ color: 'var(--danger)', background: 'var(--danger-bg)' }}
                  >
                    ⚠ 消息渲染失败
                    <button
                      onClick={reset}
                      className="ml-2 underline"
                      style={{ color: 'var(--accent)' }}
                    >
                      重试
                    </button>
                  </div>
                )}
              >
                {msg.role === 'assistant' && msg.content === '' && !msg.reasoning ? (
                  <span className="inline-block w-2 h-4 bg-[var(--accent)] animate-pulse rounded-sm" />
                ) : msg.role === 'assistant' ? (
                  <MarkdownContent content={msg.content} />
                ) : (
                  renderContent((msg as any).__cleanContent ?? msg.content)
                )}
              </ErrorBoundary>
            </div>

            {/* copy button */}
            {!isUser && msg.content !== '' && (
              <button
                onClick={() => onCopy(msg.content)}
                className="self-start opacity-0 group-hover:opacity-100 transition-opacity p-0.5 text-text-faint"
              >
                {isCopied ? <Check size={12} /> : <Copy size={12} />}
              </button>
            )}
          </div>

          {isUser && <UserAvatar />}
        </div>
      )}
    </ContextMenu>
  );
}

/** Strip <think>...</think> reasoning blocks before rendering.
 *  Handles both complete blocks and cross-message orphans
 *  (tags split across streaming chunks). */
