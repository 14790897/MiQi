import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Button } from '../../components/ui/Button';
import { Textarea } from '../../components/ui/Textarea';
import { Tooltip } from '../../components/ui/Tooltip';
import { ContextMenu, type ContextMenuAction } from '../../components/ContextMenu';
import { cn } from '../../lib/utils';
import {
  Send,
  Square,
  Wrench,
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
  Pencil,
  BookOpen,
  GitCompare,
  Undo2,
  ListChecks,
  Settings,
  ExternalLink,
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
  type: 'image' | 'text';
  dataUrl?: string;
  content?: string;
  size: number;
  extracting?: boolean;
  dataBase64?: string;
  _tmpId?: number;
}

// ── Binary-to-base64 helper (async, non-blocking) ────────────────
function arrayBufferToBase64(buffer: ArrayBuffer): Promise<string> {
  return new Promise((resolve, reject) => {
    const blob = new Blob([buffer]);
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      const comma = dataUrl.indexOf(',');
      resolve(comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl);
    };
    reader.onerror = () => reject(new Error('base64 encode failed'));
    reader.readAsDataURL(blob);
  });
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
  action?: 'open-provider-settings';
  actionLabel?: string;
  /** When true the message is collapsed by default (user can click to expand) */
  collapsed?: boolean;
  /** Short label shown when collapsed (e.g. "exec" or "write_file → /path/to/file") */
  summary?: string;
  timestamp: number;
}

function isMissingProviderConfigMessage(message: string) {
  const normalized = message.toLowerCase();
  return normalized.includes('no api key configured');
}

function isProviderConfigurationProblem(message: string) {
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

const OFFICE_FILE_RE = /\.(docx|xlsx|pptx|ppt)$/i;

function relativeTimeLabel(timestamp?: number | string | null, now = Date.now()): string {
  if (timestamp === undefined || timestamp === null) return '尚未更新';
  const value = typeof timestamp === 'number' ? timestamp : Date.parse(timestamp);
  if (!Number.isFinite(value)) return '尚未更新';

  const diff = now - value;
  if (diff < 60_000) return '刚刚更新';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前更新`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前更新`;
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
    files.length > 0
      ? files.map((file) => `- ${file.name} (${file.op})`)
      : ['- 暂无文件'];

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
      /(?:create_docx|create_xlsx|create_pptx|docx_write|xlsx_write|pptx_write)\s*\(\s*["'](.+?)["']\s*\)/i,
      'write',
    ],
    [/(?:edit_docx|append_xlsx)\s*\(\s*["'](.+?)["']\s*\)/i, 'edit'],
    // Office tool success: "Created: file.xlsx (3 sheet(s))"
    [/^(?:Created|Appended):\s+(.+?\.\w{1,6})(?:\s*\(.*\))?$/i, 'write'],
    // Generic fallback: any mention of a path-like string after a colon
    [/(?:file|path)[:\s]+([^\s,]+\.[a-zA-Z]{1,6})/i, 'read'],
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

const DEFAULT_SESSION = 'desktop:default';

function messageContentToString(content: unknown): string {
  return typeof content === 'string' ? content : JSON.stringify(content);
}

function isAssistantTextMessage(msg: any): boolean {
  return msg?.role === 'assistant' && !!msg.content && String(msg.content).trim().length > 0;
}

function isToolActivityMessage(msg: any): boolean {
  return (
    msg?.role === 'tool' ||
    (msg?.role === 'assistant' && Array.isArray(msg.tool_calls) && msg.tool_calls.length > 0)
  );
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

    turnBuffer.forEach((msg, index) => {
      if (
        isAssistantTextMessage(msg) &&
        isToolActivityMessage(msg) &&
        index !== lastAssistantTextIndex
      ) {
        result.push({ ...msg, content: '' });
        return;
      }
      if (isAssistantTextMessage(msg) && index !== lastAssistantTextIndex) return;
      result.push(msg);
    });
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

export function sessionMsgsToUi(rawMsgs: any[]): Message[] {
  const result: Message[] = [];
  for (const m of collapseAssistantMessagesWithinTurns(rawMsgs)) {
    const ts = m.timestamp ? new Date(m.timestamp).getTime() : Date.now();

    if (m.role === 'user' || m.role === 'assistant') {
      // For assistant messages with tool_calls, emit a progress indicator first
      if (m.role === 'assistant' && m.tool_calls?.length) {
        const hintText =
          m._tool_hint_text ||
          m.tool_calls
            .map((tc: any) => {
              const fn = tc.function?.name || tc.name || '?';
              const args = tc.function?.arguments || tc.arguments || '';
              const argStr = typeof args === 'string' ? args : JSON.stringify(args);
              return `${fn}(${argStr.slice(0, 80)})`;
            })
            .join(', ');
        // Short summary: just tool names, or parse file path from _tool_hint_text
        const summaryParts = m.tool_calls.map((tc: any) => {
          const fn = tc.function?.name || tc.name || '?';
          return fn;
        });
        const summary = summaryParts.join(', ');
        result.push({
          role: 'progress',
          content: hintText,
          summary,
          toolHint: true,
          collapsed: true,
          timestamp: ts,
        });
      }

      // Skip assistant messages that have no text content (only tool_calls)
      const hasContent = m.content && String(m.content).trim().length > 0;
      if (m.role === 'user' || hasContent) {
        result.push({
          role: m.role as 'user' | 'assistant',
          content: messageContentToString(m.content),
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
        const preview = content.length > 120 ? content.slice(0, 120) + '…' : content;
        result.push({
          role: 'progress',
          content: `${toolName}: ${preview}`,
          summary: toolName,
          toolHint: true,
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
    if (msg.collapsed && merged.length > 0 && merged[merged.length - 1].collapsed) {
      const prev = merged[merged.length - 1];
      // Append content and summary
      prev.content += '\n' + msg.content;
      prev.summary = prev.summary!.includes(',')
        ? prev.summary // already a group, keep it
        : `${prev.summary}, ${msg.summary}`; // merge two single items
      // Use the later timestamp
      prev.timestamp = msg.timestamp;
    } else {
      merged.push({ ...msg });
    }
  }

  // When a group has multiple items, rewrite summary to show count
  for (const msg of merged) {
    if (msg.collapsed && msg.summary && msg.summary.includes(',')) {
      const names = msg.summary.split(', ').filter(Boolean);
      // Deduplicate tool names
      const unique = [...new Set(names)];
      msg.summary = `${unique.length} tool calls: ${unique.join(', ')}`;
    }
  }

  return merged;
}

function removeTransientTurnMessagesSinceLastUser(messages: Message[]): Message[] {
  const lastUserIndex = (() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === 'user') return i;
    }
    return -1;
  })();

  return messages.reduce((acc, message, index) => {
    if (index <= lastUserIndex) {
      acc.push(message);
      return acc;
    }
    if (message.role === 'assistant') return acc;
    if (message.role !== 'progress' || message.toolHint) {
      // Retained toolHint progress should render collapsed after final
      if (message.role === 'progress' && message.toolHint && !message.collapsed) {
        acc.push({ ...message, collapsed: true });
      } else {
        acc.push(message);
      }
    }
    return acc;
  }, [] as Message[]);
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
  'docx_write',
  'xlsx_write',
  'pptx_write',
  'edit_docx',
  'append_xlsx',
];
const _FILE_READ_TOOLS = ['read_file'];

/** Extract a file path from a JSON-stringified tool args object.
 *  Checks common keys: path, file_path, filename. */
function _extractPathFromArgs(argsStr: string): string | null {
  try {
    const args = JSON.parse(argsStr);
    return (args.path as string) || (args.file_path as string) || (args.filename as string) || null;
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
    const key = path.replace(/\\/g, '/');
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

/* ─── Main component ─────────────────────────────────────────────── */
export function ChatConsole({
  sessionKey = DEFAULT_SESSION,
  loadTrigger,
  onNewSession,
  onChatFinished,
  onOpenProviderSettings,
}: {
  sessionKey?: string;
  /** Increment to force a session history reload (e.g. after bridge becomes ready) */
  loadTrigger?: number;
  onNewSession?: (newKey: string) => void;
  onChatFinished?: () => void;
  onOpenProviderSettings?: () => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionUpdatedAt, setSessionUpdatedAt] = useState<string | null>(null);
  const [clockTick, setClockTick] = useState(() => Date.now());
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [downloadingPaperId, setDownloadingPaperId] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [panelWidth, setPanelWidth] = useState(280);
  const panelResizing = useRef(false);

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
          setActivePluginCount((plugins ?? []).filter((plugin) => plugin.status === 'active').length);
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
  const [previewFile, setPreviewFile] = useState<{ path: string; content: string } | null>(null);
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
  const unsubsRef = useRef<Array<() => void>>([]);
  const finalCleanupTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shareFeedbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentSessionRef = useRef(sessionKey);
  // Track the active thread ID for new-protocol thread-aware conversations
  const currentThreadIdRef = useRef<string | null>(null);

  // ── Thread tabs for multi-agent support ──
  interface ThreadTab {
    threadId: string;
    agentType: string;
    label: string;
  }
  const [threads, setThreads] = useState<ThreadTab[]>([
    { threadId: 'main', agentType: 'main', label: 'Main' },
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
    setTrackedFiles((prev) => {
      const existing = prev.find((f) => f.path === path);
      if (existing) {
        // Upgrade: read < edit < write
        const rank: Record<TrackedFile['op'], number> = { read: 0, edit: 1, write: 2, delete: 3 };
        const nextOp = rank[op] > rank[existing.op] ? op : existing.op;
        return prev.map((f) =>
          f.path === path
            ? { ...f, op: nextOp, lastSeen: Date.now(), truncated: f.truncated && truncated }
            : f
        );
      }
      return [...prev, { path, name: basename(path), op, lastSeen: Date.now(), truncated }];
    });
  }, []);

  useEffect(() => {
    // Tear down any in-flight stream listeners from a previous session
    // before updating the ref.  This makes the per-handler session_key
    // guard a defence-in-depth measure rather than the sole mechanism.
    cleanupListeners();
    currentSessionRef.current = sessionKey;
    currentThreadIdRef.current = null; // Reset on session change
    setHistoryLoaded(false);
    setMessages([]);
    setSessionUpdatedAt(null);
    // NOTE: do NOT clear trackedFiles here — clearing before the async
    // load completes causes a flash of "No files yet" on every session
    // switch.  If the bridge is not ready yet, sendSafe returns null and
    // we would permanently lose the display.  Instead we replace atomically
    // inside load() after the bridge responds.
    justOpened.current = true;
    userScrolledUp.current = false; // reset for new session
    const load = async () => {
      try {
        const detail = await window.miqi.sessions.get(sessionKey);
        if (currentSessionRef.current !== sessionKey) return;
        const rawMsgs: any[] = (detail as any)?.messages ?? [];
        const uiMsgs = sessionMsgsToUi(rawMsgs);
        setMessages(uiMsgs);
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
      const ext = file.name.split('.').pop()?.toLowerCase() || '';
      const isImage = file.type.startsWith('image/');
      const isPdf = file.type === 'application/pdf' || ext === 'pdf';
      const isOffice = !isImage && !isPdf && (
        file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' || ext === 'docx'
        || file.type === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' || ext === 'xlsx'
        || file.type === 'application/vnd.openxmlformats-officedocument.presentationml.presentation' || ext === 'pptx'
      );
      const isBinary = isPdf || isOffice;

      if (isBinary) {
        const tmpId = Math.random();
        setAttachments((prev) => [...prev, { name: file.name, type: 'text', size: file.size, extracting: true, _tmpId: tmpId }]);
        const reader = new FileReader();
        reader.onload = async () => {
          const buffer = reader.result as ArrayBuffer;
          // Client-side only encodes to base64; backend saves to workspace
          // and mirrors into the WSL sandbox.  The agent then uses read_file
          // or exec tools (pdfplumber / python-docx / openpyxl) to extract text.
          let dataBase64: string | undefined;
          try {
            dataBase64 = await arrayBufferToBase64(buffer);
          } catch {
            dataBase64 = undefined;
          }
          setAttachments((prev) => prev.map((a: any) =>
            a._tmpId === tmpId
              ? { name: file.name, type: 'text', content: '', size: file.size, dataBase64 }
              : a
          ));
        };
        reader.onerror = () => {
          // Clear the stuck extracting attachment so Send stays usable
          setAttachments((prev) => prev.filter((a: any) => a._tmpId !== tmpId));
        };
        reader.readAsArrayBuffer(file);
        return;
      }
      const reader = new FileReader();
      reader.onload = () => setAttachments((prev) => [...prev, isImage
        ? { name: file.name, type: 'image', dataUrl: reader.result as string, size: file.size }
        : { name: file.name, type: 'text', content: reader.result as string, size: file.size }
      ]);
      if (isImage) reader.readAsDataURL(file);
      else reader.readAsText(file);
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
    setMessages((prev) => [
      ...prev,
      { role: 'progress', content: '已停止。', timestamp: Date.now() },
    ]);
  }, [cleanupListeners, currentReqId]);

  const handleNewSession = useCallback(async () => {
    if (streaming) return;
    const newKey = `desktop:${Date.now()}`;
    currentThreadIdRef.current = null;
    cleanupListeners();
    onNewSession?.(newKey);
  }, [streaming, cleanupListeners, onNewSession]);

  const handleDeleteSession = useCallback(async () => {
    const key = currentSessionRef.current;
    if (!key) return;
    if (!window.confirm('Delete this conversation? This cannot be undone.')) return;
    try {
      await window.miqi.sessions.delete(key);
    } catch {
      /* ignore */
    }
    handleNewSession();
  }, [handleNewSession]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text && attachments.length === 0) return;

    try {
      const result = await window.miqi.providers.list();
      const hasConfiguredProvider = result.providers.some((provider) => provider.configured);
      if (!hasConfiguredProvider) {
        setMessages((prev) => [...prev, createProviderConfigMessage()]);
        return;
      }
    } catch {
      // If provider status cannot be read, keep the original send path so the
      // bridge can surface the underlying runtime error.
    }

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

    let content = text;
    // Collect binary attachments to pass through IPC (backend saves before agent runs)
    const binaryAtts: Array<{name: string, data_base64: string}> = [];
    for (const att of attachments) {
      if (att.dataBase64) {
        binaryAtts.push({ name: att.name, data_base64: att.dataBase64 });
        const ext = att.name.split('.').pop()?.toLowerCase() || '';
        const isPdf = ext === 'pdf';
        const label = isPdf ? 'PDF' : ext.toUpperCase();
        const wsPath = `uploads/${att.name}`;
        if (isPdf) {
          content += `\n\n[${label}: ${att.name}] saved to workspace ${wsPath}\nYou can read it with the read_file tool, or install PDF tools to extract text:\n  exec("pip install pdfplumber && python3 -c \\"import pdfplumber; pdf=pdfplumber.open('${wsPath}'); print('\\\\n'.join(p.extract_text() or '' for p in pdf.pages))\\"")`;
        } else {
          content += `\n\n[${label}: ${att.name}] saved to workspace ${wsPath}\nUse read_file to inspect, or install appropriate tools (python-docx for .docx, openpyxl for .xlsx, python-pptx for .pptx) to extract text content.`;
        }
      } else if (att.content)
        content += `\n\n[Attachment: ${att.name}]\n\`\`\`\n${att.content}\n\`\`\``;
      else if (att.type === 'image' && att.dataUrl) content += `\n\n[Image: ${att.name}]`;
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
    setStreaming(true);
    cleanupListeners();

    let fullContent = '';
    let displayed = '';
    let animId: number | null = null;
    let finalDone = false;
    let streamErrorHandled = false;

    // Reveal the assistant reply with a typewriter animation. The bubble is
    // created lazily — only once the first chunk of content is available — so
    // we never render an empty assistant bubble (which previously flashed as a
    // blank message box before the first animation frame filled it in; see
    // issue #109). If the reply has no text, no bubble is shown at all.
    const revealNext = () => {
      if (displayed.length >= fullContent.length) {
        if (finalDone) {
          setStreaming(false);
          scheduleFinalCleanup();
        }
        return;
      }
      displayed += fullContent.slice(displayed.length, displayed.length + 4);
      const snap = displayed;
      const ts = userMsg.timestamp + 1;
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last?.role === 'assistant' && last.timestamp === ts)
          return [...prev.slice(0, -1), { ...last, content: snap }];
        // First chunk: insert the assistant bubble prefilled with content,
        // never as an empty placeholder.
        return [...prev, { role: 'assistant', content: snap, timestamp: ts }];
      });
      animId = requestAnimationFrame(revealNext);
    };

    // Track last progress event time for watchdog
    let lastEventAt = Date.now();
    const NO_PROGRESS_WARN_MS = 25_000; // 25s — show "still waiting" warning
    const NO_PROGRESS_STRONG_MS = 60_000; // 60s — stronger warning
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
      if (finalDone) {
        if (watchdogTimer) {
          clearInterval(watchdogTimer);
          watchdogTimer = null;
        }
        return;
      }
      const elapsed = Date.now() - lastEventAt;
      if (elapsed >= NO_PROGRESS_STRONG_MS) {
        appendWatchdogMsg(
          '⚠️ No response from backend for 60s. You can abort and check runtime logs.'
        );
      } else if (elapsed >= NO_PROGRESS_WARN_MS) {
        appendWatchdogMsg('⏳ Still waiting for backend response…');
      }
    }, 5_000); // check every 5s

    const sendCleanup = () => {
      if (watchdogTimer) {
        clearInterval(watchdogTimer);
        watchdogTimer = null;
      }
      // NOTE: cleanupListeners() is deliberately NOT called here.
      // The typewriter completing does not mean the turn is over —
      // another final may still arrive (e.g. tool-call then final-text).
      // Listeners are torn down only on abort / error / new-session.
    };

    const scheduleFinalCleanup = () => {
      if (finalCleanupTimerRef.current) return;
      finalCleanupTimerRef.current = setTimeout(() => {
        finalCleanupTimerRef.current = null;
        sendCleanup();
        if (onChatFinished) onChatFinished();
      }, 100);
    };

    const unsubProgress = window.miqi.chat.onProgress((data: ChatProgress) => {
      if (data.session_key && data.session_key !== currentSessionRef.current) return;
      lastEventAt = Date.now();
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

        setMessages((prev) => [
          ...prev,
          {
            role: msgRole,
            content: extracted.role === 'warning' ? `⚠️ ${extracted.message}` : extracted.message,
            toolHint: data.tool_hint || toolName === 'paper_search',
            toolCallId: data.tool_call_id,
            toolName,
            toolData,
            timestamp: Date.now(),
          },
        ]);
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
      if (data.session_key && data.session_key !== currentSessionRef.current) return;
      clearFinalCleanupTimer();
      if (animId !== null) {
        cancelAnimationFrame(animId);
        animId = null;
      }
      fullContent = data.content;
      displayed = '';
      finalDone = true;
      setCurrentReqId(null);
      if (data.tool_calls?.length) {
        // Track file operations from tool_calls for Task Assets panel.
        // Office tools (create_docx, etc.) don't always produce progress
        // hints that match parseToolHint patterns, so we extract file
        // paths directly from the final tool call list.
        for (const tc of (data.tool_calls ?? []) as any[]) {
          const fn = tc?.function || tc?.tool?.function || {};
          const toolName: string = fn?.name || '';
          if (!toolName) continue;
          const filePath: string = _extractPathFromArgs(fn?.arguments || '{}') || '';
          if (!filePath) continue;
          if (_FILE_WRITE_TOOLS.includes(toolName)) {
            trackFile(filePath, 'write', false);
          } else if (_FILE_READ_TOOLS.includes(toolName)) {
            trackFile(filePath, 'read', false);
          }
        }

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
      if (data.session_key && data.session_key !== currentSessionRef.current) return;
      streamErrorHandled = true;
      if (animId !== null) cancelAnimationFrame(animId);
      const message = sanitizeUiMessage(data.message);
      setMessages((prev) => [
        ...prev,
        isProviderConfigurationProblem(message)
          ? createProviderConfigMessage(message)
          : { role: 'error', content: message, timestamp: Date.now() },
      ]);
      setStreaming(false);
      sendCleanup();
      cleanupListeners();
    });

    const unsubAborted = window.miqi.chat.onAborted((_data: ChatAborted) => {
      if (_data.session_key && _data.session_key !== currentSessionRef.current) return;
      if (animId !== null) cancelAnimationFrame(animId);
      setStreaming(false);
      setCurrentReqId(null);
      setMessages((prev) => [
        ...prev,
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
      await window.miqi.chat.send(content, key, threadId ?? undefined, binaryAtts.length > 0 ? binaryAtts : undefined);
    } catch (e: any) {
      if (animId !== null) cancelAnimationFrame(animId);
      if (streamErrorHandled) {
        setStreaming(false);
        sendCleanup();
        cleanupListeners();
        return;
      }
      const errMsg = sanitizeUiMessage(e?.message ?? String(e ?? 'Unknown error'));
      if (isProviderConfigurationProblem(errMsg)) {
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
  }, [input, attachments, streaming, cleanupListeners, onChatFinished]);

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

  const handlePreview = useCallback(async (path: string) => {
    // Open all files with the system default application — no in-app preview modal.
    const result = await window.miqi.files.openExternal(path);
    if (!result?.opened) {
      setPreviewFile({ path, content: `(Could not open file: ${path})` });
    }
  }, []);

  const closePreview = () => setPreviewFile(null);

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

  const handleCopy = (text: string, idx: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

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

  /* session display name — use the first user message as title */
  const sessionTitle = useMemo(() => {
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
  }, [messages, sessionKey]);

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
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="image/*,text/*,.md,.txt,.py,.ts,.js,.json,.csv,.yaml,.yml,.toml,.pdf,.docx,.xlsx,.pptx"
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
          className="text-sm font-bold whitespace-nowrap shrink-0"
          style={{ color: 'var(--text)' }}
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
          <div
            className="flex items-center gap-1.5 pl-2 ml-1 border-l"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div
              className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0"
              style={{ background: 'var(--avatar-dark)' }}
            >
              A
            </div>
            <span className="text-xs whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
              Admin
            </span>
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
                    handleNewSession();
                  } catch { /* ignore */ }
                },
              },
              {
                label: '删除对话',
                danger: true,
                onSelect: async () => {
                  if (!window.confirm('删除此对话？操作不可恢复。')) return;
                  try {
                    await window.miqi.sessions.delete(sessionKey);
                    handleNewSession();
                  } catch (e) {
                    console.error('Delete failed:', e);
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
              <h2
                className="text-[16px] font-semibold truncate leading-[1.35]"
                style={{ color: 'var(--text)' }}
              >
                {sessionTitle}
              </h2>
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
            <div className="max-w-[760px] mx-auto px-6 py-5 flex flex-col gap-8">
              {!historyLoaded ? (
                <div className="flex items-center justify-center min-h-[300px]">
                  <Loader2
                    size={16}
                    className="animate-spin"
                    style={{ color: 'var(--text-faint)' }}
                  />
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
                    <p className="text-[15px] font-medium" style={{ color: 'var(--text-muted)' }}>
                      从文件、问题或修改请求开始
                    </p>
                    <p className="text-xs" style={{ color: 'var(--text-faint)' }}>
                      发起一段对话即可开始
                    </p>
                  </div>
                </div>
              ) : (
                messages.map((msg, i) => (
                  <MessageBubble
                    key={`${msg.timestamp}-${i}`}
                    msg={msg}
                    execOutputs={execOutputs}
                    isLast={i === messages.length - 1}
                    onCopy={(text) => handleCopy(text, i)}
                    isCopied={copiedIdx === i}
                    onRetry={() => handleRetry(msg)}
                    onOpenProviderSettings={onOpenProviderSettings}
                    onDownloadPaper={handleDownloadPaper}
                    downloadingPaperId={downloadingPaperId}
                  />
                ))
              )}
              {streaming && (
                <div
                  className="flex items-center gap-2 text-xs px-1"
                  style={{ color: 'var(--text-muted)' }}
                  data-testid="thinking-indicator"
                >
                  <Loader2 size={12} className="animate-spin" />
                  Thinking…
                </div>
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
                  {attachments.map((att, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs max-w-[200px]"
                      style={{
                        background: 'var(--surface-muted)',
                        border: '1px solid var(--border-subtle)',
                        color: 'var(--text-muted)',
                      }}
                    >
                      {att.type === 'image' ? (
                        <Image size={12} className="shrink-0" style={{ color: 'var(--info)' }} />
                      ) : att.extracting ? (
                        <Loader2 size={12} className="shrink-0 animate-spin" style={{ color: 'var(--warning)' }} />
                      ) : att.content ? (
                        <CheckCircle size={12} className="shrink-0" style={{ color: '#22c55e' }} />
                      ) : (
                        <FileText
                          size={12}
                          className="shrink-0"
                          style={{ color: 'var(--text-faint)' }}
                        />
                      )}
                      <span className="truncate">{att.name}</span>
                      <button
                        onClick={() => removeAttachment(i)}
                        className="shrink-0 hover:text-[var(--danger)]"
                      >
                        <X size={11} />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div
                className="flex items-end gap-2 rounded-xl px-4 py-3.5 focus-within:ring-2 transition-all"
                data-testid="chat-input-container"
                style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  outline: 'none',
                  boxShadow: '0 -4px 20px rgba(0,0,0,0.06), 0 2px 8px rgba(0,0,0,0.04)',
                }}
              >
                <button
                  onClick={handleAttachClick}
                  className="shrink-0 p-1 rounded hover:bg-[var(--surface-muted)] transition-colors"
                  title="Attach file or image"
                  aria-label="Attach file or image"
                >
                  <Paperclip size={15} style={{ color: 'var(--text-faint)' }} />
                </button>
                <Textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => {
                    setInput(e.target.value);
                    adjustTextareaHeight();
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder="输入消息或拖入文件..."
                  rows={1}
                  allowResize={true}
                  className="flex-1 border-0 bg-transparent p-0! leading-6! focus:ring-0 focus:border-0 min-h-0 text-sm"
                  disabled={streaming}
                  style={{ color: 'var(--text)' }}
                />
                {streaming ? (
                  <button
                    onClick={handleAbort}
                    className="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center transition-colors hover:bg-[var(--surface-muted)]"
                  >
                    <Square size={14} style={{ color: 'var(--text-muted)' }} />
                  </button>
                ) : (
                  <button
                    onClick={handleSend}
                    disabled={!input.trim() && attachments.length === 0 || attachments.some(a => a.extracting)}
                    className="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center transition-colors disabled:opacity-30"
                    style={{ background: 'var(--accent)' }}
                  >
                    <Send size={13} style={{ color: '#fff' }} />
                  </button>
                )}
              </div>
            </div>
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
              <div className="flex items-center gap-1.5">
                <LayoutGrid size={13} style={{ color: 'var(--text-muted)' }} />
                <span className="text-xs font-semibold" style={{ color: 'var(--text)' }} data-testid="task-assets-title">
                  任务资产
                </span>
              </div>
              <span className="text-xs font-medium" style={{ color: 'var(--text-faint)' }}>
                {trackedFiles.length}
              </span>
            </div>

            {trackedFiles.length === 0 ? (
              <div className="flex flex-col items-center justify-center flex-1 px-4 py-8 text-center gap-4">
                <FileText size={28} style={{ color: 'var(--text-faint)', opacity: 0.35 }} />
                <div className="flex flex-col items-center gap-1">
                  <p className="text-[13px] font-medium" style={{ color: 'var(--text-muted)' }} data-testid="task-assets-empty">
                    暂无文件
                  </p>
                  <p className="text-[11px]" style={{ color: 'var(--text-faint)' }}>
                    Agent 操作会显示在这里
                  </p>
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
                    <span className="text-xs font-semibold" style={{ color: 'var(--text)' }}>
                      修改建议
                    </span>
                  </div>
                  <span className="text-[10px]" style={{ color: 'var(--text-faint)' }}>
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
                        <span
                          className="text-[11px] truncate flex-1"
                          style={{ color: 'var(--text)' }}
                          title={f.path}
                        >
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
                          className="p-1 rounded transition-colors shrink-0"
                          style={{ color: 'var(--text-faint)' }}
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
                  merging || trackedFiles.length === 0
                    ? 'cursor-not-allowed'
                    : 'hover:opacity-90',
                )}
                style={{
                  background:
                    merging || trackedFiles.length === 0 ? 'var(--surface-muted)' : 'var(--accent)',
                  color: merging || trackedFiles.length === 0 ? 'var(--text-faint)' : 'var(--accent-text)',
                  opacity: merging || trackedFiles.length === 0 ? 0.5 : 1,
                }}
              >
                {merging ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <GitMerge size={13} />
                )}
                {merging ? '合并中...' : '合并所有更改'}
              </button>
              {trackedFiles.length === 0 && (
                <div className="flex items-center justify-center mt-2 py-1.5">
                  <span className="text-xs" style={{ color: 'var(--text-faint)' }}>
                    跟踪文件变更后将在此显示合并选项
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── File Preview Modal ── */}
      {previewFile && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.5)' }}
          onClick={closePreview}
        >
          <div
            className="flex flex-col rounded-xl shadow-2xl overflow-hidden"
            style={{
              width: 680,
              maxHeight: '80vh',
              background: 'var(--surface-elevated)',
              border: '1px solid var(--border)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="flex items-center justify-between px-4 py-3 border-b shrink-0"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <FileText size={14} style={{ color: 'var(--info)' }} className="shrink-0" />
                <span
                  className="text-[11px] font-mono break-all leading-relaxed"
                  style={{ color: 'var(--text-muted)' }}
                  title={previewFile.path}
                >
                  {previewFile.path}
                </span>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => window.miqi.files.openExternal(previewFile.path)}
                  className="flex items-center gap-1 px-2 py-1 rounded text-[11px] text-[var(--accent)] hover:bg-[var(--accent-soft)] transition-colors"
                  title="Open with system default application"
                >
                  <ExternalLink size={12} />
                  <span>系统应用打开</span>
                </button>
                <button
                  onClick={closePreview}
                  className="p-1 rounded hover:bg-[var(--surface-muted)] transition-colors"
                >
                  <X size={14} style={{ color: 'var(--text-faint)' }} />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto p-4">
              <pre
                className="text-xs font-mono leading-relaxed whitespace-pre-wrap break-all"
                style={{ color: 'var(--text-muted)' }}
              >
                {previewFile.content}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* ── Diff Modal ── */}
      {diffFile && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.6)' }}
          onClick={closeDiff}
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
            <div
              className="flex items-center justify-between px-4 py-3 border-b shrink-0"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <div className="flex items-center gap-2 min-w-0">
                <GitCompare size={14} style={{ color: 'var(--warning)' }} className="shrink-0" />
                <span
                  className="text-sm font-medium truncate"
                  style={{ color: 'var(--text)' }}
                  title={diffFile.path}
                >
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
                    title="Revert to HEAD (undo changes)"
                  >
                    <Undo2 size={12} className={reverting ? 'animate-spin' : ''} />
                    {reverting ? 'Reverting...' : 'Revert'}
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
                  <Loader2
                    size={24}
                    className="animate-spin"
                    style={{ color: 'var(--text-faint)' }}
                  />
                  <span className="ml-2 text-sm" style={{ color: 'var(--text-faint)' }}>
                    Loading diff...
                  </span>
                </div>
              ) : diffFile.diff ? (
                <DiffView diff={diffFile.diff} />
              ) : diffFile.original_content !== null && diffFile.current_content !== null ? (
                /* No snapshot diff but we have both versions — show side by side */
                <div className="flex h-full" style={{ minHeight: 400 }}>
                  <div
                    className="flex-1 p-4 overflow-auto border-r"
                    style={{ borderColor: 'var(--border-subtle)' }}
                  >
                    <div
                      className="text-[10px] font-semibold uppercase tracking-wider mb-2"
                      style={{ color: 'var(--text-faint)' }}
                    >
                      Original
                    </div>
                    <pre
                      className="text-xs font-mono leading-relaxed whitespace-pre-wrap break-all"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      {diffFile.original_content || '(empty)'}
                    </pre>
                  </div>
                  <div className="flex-1 p-4 overflow-auto">
                    <div
                      className="text-[10px] font-semibold uppercase tracking-wider mb-2"
                      style={{ color: 'var(--text-faint)' }}
                    >
                      Current
                    </div>
                    <pre
                      className="text-xs font-mono leading-relaxed whitespace-pre-wrap break-all"
                      style={{ color: 'var(--text)' }}
                    >
                      {diffFile.current_content || '(empty)'}
                    </pre>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center h-48">
                  <span className="text-sm" style={{ color: 'var(--text-faint)' }}>
                    {diffFile.original_content === null && diffFile.current_content === null
                      ? 'No snapshot available — file was not modified in this session'
                      : 'No changes detected'}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Sub-components ──────────────────────────────────────────────── */

/** Renders a unified diff string with syntax-highlighted +/- lines. */
function DiffView({ diff }: { diff: string }) {
  const lines = diff.split('\n');
  // Detect if this is a new file diff (starts with --- /dev/null)
  const isNewFile = lines.some((l) => l.startsWith('--- /dev/null'));
  return (
    <div
      className="overflow-x-auto text-xs font-mono leading-5"
      style={{ background: 'var(--surface)' }}
    >
      {lines.map((line, i) => {
        let bg = 'transparent';
        let color = 'var(--text-muted)';
        let prefix = ' ';

        if (line.startsWith('+++ b/')) {
          // New file: show +++ as green
          bg = 'rgba(34,197,94,0.08)';
          color = '#4ade80';
        } else if (line.startsWith('--- /dev/null')) {
          // New file: show --- /dev/null as gray (context for empty original)
          color = 'var(--text-faint)';
        } else if (line.startsWith('---')) {
          color = 'var(--text-faint)';
        } else if (line.startsWith('@@')) {
          bg = isNewFile ? 'rgba(34,197,94,0.08)' : 'rgba(96,165,250,0.08)';
          color = isNewFile ? '#4ade80' : 'var(--info)';
        } else if (line.startsWith('+')) {
          bg = 'rgba(34,197,94,0.10)';
          color = '#4ade80';
          prefix = '+';
        } else if (line.startsWith('-')) {
          bg = 'rgba(239,68,68,0.10)';
          color = '#f87171';
          prefix = '-';
        }

        return (
          <div
            key={i}
            style={{
              background: bg,
              color,
              paddingLeft: 12,
              paddingRight: 12,
              whiteSpace: 'pre',
              minWidth: '100%',
              display: 'block',
            }}
          >
            {line || '\u00a0'}
          </div>
        );
      })}
    </div>
  );
}

function SectionLabel({ label, sectionKey }: { label: string; sectionKey: string }) {
  const testId = `section-label-${sectionKey}`;
  return (
    <div
      className="px-4 pt-3 pb-1.5 text-[10px] font-semibold uppercase tracking-widest"
      style={{ color: 'var(--text-faint)' }}
      data-testid={testId}
    >
      {label}
    </div>
  );
}

function TrackedFileCard({
  file,
  onPreview,
  onDiff,
}: {
  file: TrackedFile;
  onPreview: () => void;
  onDiff?: () => void;
}) {
  const opColor: Record<TrackedFile['op'], string> = {
    read: 'var(--info)',
    edit: 'var(--warning)',
    write: 'var(--accent)',
    delete: 'var(--danger)',
  };
  const OpIcon = file.op === 'read' ? BookOpen : file.op === 'delete' ? X : Pencil;
  const displayPath = file.path.replace(/\\/g, '/');
  const isOfficeFile = OFFICE_FILE_RE.test(file.path);

  return (
    <div
      className="rounded-lg p-2.5"
      style={{
        border: '1px solid var(--border-subtle)',
        background: 'var(--surface)',
      }}
    >
      <div className="flex items-start gap-2 mb-1">
        <FileText size={14} className="shrink-0 mt-0.5" style={{ color: opColor[file.op] }} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap mb-0.5">
            <span
              className="text-[12px] font-medium truncate"
              style={{ color: 'var(--text)' }}
              title={displayPath}
            >
              {file.name.length > 30 ? file.name.slice(0, 28) + '…' : file.name}
            </span>
            <span
              className="text-[9px] px-1.5 py-0.5 rounded font-semibold shrink-0"
              style={{
                background: `color-mix(in srgb, ${opColor[file.op]} 15%, transparent)`,
                color: opColor[file.op],
              }}
            >
              {file.op.toUpperCase()}
            </span>
            {isOfficeFile && (
              <span
                className="text-[9px] px-1.5 py-0.5 rounded font-semibold shrink-0"
                style={{
                  background: 'var(--surface-muted)',
                  color: 'var(--text-faint)',
                }}
              >
                OFFICE
              </span>
            )}
          </div>
        </div>
      </div>
      {file.truncated ? (
        <div
          className="w-full flex items-center justify-center gap-1 py-1 rounded-md text-[11px]"
          style={{
            border: '1px solid var(--border-subtle)',
            color: 'var(--text-faint)',
            background: 'var(--surface-muted)',
          }}
          title="Path was truncated in progress message"
        >
          <span className="text-[10px]">Path incomplete</span>
        </div>
      ) : (
        <div className="flex gap-1.5">
          {onDiff && (file.op === 'write' || file.op === 'edit') && (
            <button
              onClick={onDiff}
              disabled={isOfficeFile}
              className="flex-1 flex items-center justify-center gap-1 py-1 rounded-md text-[11px] transition-colors"
              style={{
                border: '1px solid var(--border)',
                color: isOfficeFile ? 'var(--text-faint)' : 'var(--warning)',
                opacity: isOfficeFile ? 0.55 : 1,
              }}
              title={
                isOfficeFile ? 'Diff is not available for Office binary files' : 'Compare diff'
              }
            >
              <GitCompare size={10} />
              Diff
            </button>
          )}
          <button
            onClick={onPreview}
            className="flex-1 flex items-center justify-center gap-1 py-1 rounded-md text-[11px] transition-colors"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-muted)',
            }}
            title={isOfficeFile ? '不支持预览 Office 文件' : '预览文件'}
            data-testid="file-preview-btn"
          >
            <Eye size={10} />
            Preview
          </button>
        </div>
      )}
    </div>
  );
}

function MessageBubble({
  msg,
  execOutputs,
  isLast,
  onCopy,
  isCopied,
  onRetry,
  onOpenProviderSettings,
  onDownloadPaper,
  downloadingPaperId,
}: {
  msg: Message;
  execOutputs: Record<string, { stdout: string; stderr: string; running: boolean }>;
  isLast: boolean;
  onCopy: (text: string) => void;
  isCopied: boolean;
  onRetry?: () => void;
  onOpenProviderSettings?: () => void;
  onDownloadPaper?: (paper: PaperItem) => void;
  downloadingPaperId?: string | null;
}) {
  const [expanded, setExpanded] = useState(false);

  if (msg.role === 'progress') {
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
    return (
      <div
        className={cn(
          'flex items-center gap-2 text-xs py-1 px-1',
          msg.collapsed && 'cursor-pointer'
        )}
        style={{ color: msg.toolHint ? 'var(--info)' : 'var(--text-muted)' }}
        onClick={msg.collapsed ? () => setExpanded((v) => !v) : undefined}
      >
        {msg.toolHint ? (
          <Wrench size={12} />
        ) : isLast ? (
          <Loader2 size={12} className="animate-spin" />
        ) : (
          <CheckCircle size={12} />
        )}
        {msg.collapsed &&
          (isCollapsed ? (
            <ChevronRight size={10} className="shrink-0" style={{ color: 'var(--text-faint)' }} />
          ) : (
            <ChevronDown size={10} className="shrink-0" style={{ color: 'var(--text-faint)' }} />
          ))}
        {isCollapsed ? (
          <span>{msg.summary || msg.content}</span>
        ) : (
          <span className="whitespace-pre-wrap break-all">{msg.content}</span>
        )}
        {/* Inline exec output (Phase 7.4) */}
        {msg.toolCallId && execOutputs[msg.toolCallId] && (
          <div className="ml-5 mt-1 p-2 bg-black/80 text-green-400 text-[11px] font-mono rounded max-h-48 overflow-y-auto border border-gray-700">
            <pre className="whitespace-pre-wrap">
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
          className="text-sm rounded-2xl px-4 py-3 prose prose-sm max-w-none break-words"
          style={{
            background: 'var(--surface-muted)',
            color: 'var(--text)',
            border: '1px solid var(--border-subtle)',
            maxWidth: '82%',
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
                  <FileText size={12} className="shrink-0" style={{ color: 'var(--text-faint)' }} />
                  <span>{att.name}</span>
                </div>
              ))}
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
              {msg.role === 'assistant' && msg.content === '' ? (
                <span className="inline-block w-2 h-4 bg-[var(--accent)] animate-pulse rounded-sm" />
              ) : msg.role === 'assistant' ? (
                <MarkdownContent content={msg.content} />
              ) : (
                renderContent(msg.content)
              )}
            </div>

            {/* copy button */}
            {!isUser && msg.content !== '' && (
              <button
                onClick={() => onCopy(msg.content)}
                className="self-start opacity-0 group-hover:opacity-100 transition-opacity p-0.5"
                style={{ color: 'var(--text-faint)' }}
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

function AgentAvatar() {
  return (
    <div
      className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-xs font-bold text-white mt-0.5"
      style={{ background: 'var(--accent)' }}
    >
      A
    </div>
  );
}

function UserAvatar() {
  return (
    <div
      className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-xs font-bold text-white mt-0.5"
      style={{ background: 'var(--avatar-dark)' }}
    >
      U
    </div>
  );
}

/** Strip <think>...</think> reasoning blocks before rendering.
 *  Handles both complete blocks and cross-message orphans
 *  (tags split across streaming chunks). */
function stripThinkBlocks(text: string): string {
  // let result = text.replace(/<think>[\s\S]*?<\/think>/gi, '')  // complete blocks
  let result = text.replace(/<\/?think>/gi, ''); // orphan tags
  return result.trim();
}

function MarkdownContent({ content }: { content: string }) {
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  const displayContent = stripThinkBlocks(content);

  const handleCopyCode = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedCode(code);
    setTimeout(() => setCopiedCode(null), 2000);
  };

  const components = useMemo(
    () => ({
      p: ({ children }: any) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
      h1: ({ children }: any) => (
        <h1 className="text-base font-bold mt-3 mb-1.5 first:mt-0">{children}</h1>
      ),
      h2: ({ children }: any) => (
        <h2 className="text-sm font-bold mt-3 mb-1 first:mt-0">{children}</h2>
      ),
      h3: ({ children }: any) => (
        <h3 className="text-sm font-semibold mt-2 mb-0.5 first:mt-0">{children}</h3>
      ),
      ul: ({ children }: any) => <ul className="list-disc pl-5 my-1.5 space-y-0.5">{children}</ul>,
      ol: ({ children }: any) => (
        <ol className="list-decimal pl-5 my-1.5 space-y-0.5">{children}</ol>
      ),
      li: ({ children }: any) => <li className="leading-relaxed">{children}</li>,
      blockquote: ({ children }: any) => (
        <blockquote
          className="border-l-2 pl-3 my-2 italic"
          style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}
        >
          {children}
        </blockquote>
      ),
      strong: ({ children }: any) => <strong className="font-semibold">{children}</strong>,
      em: ({ children }: any) => <em className="italic">{children}</em>,
      hr: () => <hr className="my-3" style={{ borderColor: 'var(--border-subtle)' }} />,
      a: ({ href, children }: any) => (
        <a
          href={href}
          className="underline cursor-pointer"
          style={{ color: 'var(--accent)' }}
          onClick={(e) => {
            e.preventDefault();
            if (href) window.open(href, '_blank');
          }}
        >
          {children}
        </a>
      ),
      table: ({ children }: any) => (
        <div className="overflow-x-auto my-2">
          <table className="text-xs w-full border-collapse">{children}</table>
        </div>
      ),
      th: ({ children }: any) => (
        <th
          className="border px-2 py-1.5 text-left font-medium"
          style={{ borderColor: 'var(--border)', background: 'var(--surface-muted)' }}
        >
          {children}
        </th>
      ),
      td: ({ children }: any) => (
        <td className="border px-2 py-1.5" style={{ borderColor: 'var(--border-subtle)' }}>
          {children}
        </td>
      ),
      pre: ({ children }: any) => (
        <pre
          className="relative group my-2 rounded-lg overflow-x-auto"
          style={{ background: 'rgba(0,0,0,0.06)' }}
        >
          {children}
        </pre>
      ),
      code: ({ className, children, ...props }: any) => {
        const codeStr = String(children);
        const isBlock = codeStr.endsWith('\n');
        if (isBlock) {
          const code = codeStr.replace(/\n$/, '');
          return (
            <code className={cn('block text-xs font-mono p-3', className)} {...props}>
              <button
                onClick={() => handleCopyCode(code)}
                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity rounded px-1.5 py-0.5 text-[10px] leading-none"
                style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-muted)',
                }}
              >
                {copiedCode === code ? 'Copied' : 'Copy'}
              </button>
              {code}
            </code>
          );
        }
        return (
          <code
            className="text-xs font-mono px-1.5 py-0.5 rounded"
            style={{ background: 'rgba(0,0,0,0.08)' }}
            {...props}
          >
            {children}
          </code>
        );
      },
    }),
    [copiedCode]
  );

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {displayContent}
    </ReactMarkdown>
  );
}

function renderContent(text: string) {
  const parts = text.split(/(```[\s\S]*?```)/g);
  return parts.map((part, i) => {
    if (part.startsWith('```') && part.endsWith('```')) {
      const inner = part.slice(3, -3);
      const langEnd = inner.indexOf('\n');
      const code = langEnd > 0 ? inner.slice(langEnd + 1) : inner;
      return (
        <pre
          key={i}
          className="my-2 text-xs rounded-lg px-3 py-2 overflow-x-auto"
          style={{ background: 'rgba(0,0,0,0.06)' }}
        >
          <code>{code}</code>
        </pre>
      );
    }
    const segments = part.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
    return (
      <span key={i}>
        {segments.map((seg, j) => {
          if (seg.startsWith('**') && seg.endsWith('**'))
            return <strong key={j}>{seg.slice(2, -2)}</strong>;
          if (seg.startsWith('`') && seg.endsWith('`'))
            return (
              <code
                key={j}
                className="text-xs font-mono px-1 rounded"
                style={{ background: 'rgba(0,0,0,0.08)' }}
              >
                {seg.slice(1, -1)}
              </code>
            );
          return (
            <span key={j}>
              {seg.split('\n').map((line, k, arr) => (
                <span key={k}>
                  {line}
                  {k < arr.length - 1 && <br />}
                </span>
              ))}
            </span>
          );
        })}
      </span>
    );
  });
}
