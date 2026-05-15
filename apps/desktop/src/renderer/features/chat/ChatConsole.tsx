import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '../../components/ui/Button'
import { Textarea } from '../../components/ui/Textarea'
import { ContextMenu, type ContextMenuAction } from '../../components/ContextMenu'
import { cn } from '../../lib/utils'
import {
  Send,
  Square,
  Wrench,
  Loader2,
  Copy,
  Check,
  Paperclip,
  X,
  FileText,
  Image,
  LayoutGrid,
  MoreHorizontal,
  Share2,
  Eye,
  GitMerge,
  ChevronDown,
  ChevronRight,
  Pencil,
  BookOpen,
  GitCompare,
  Undo2,
} from 'lucide-react'
import type {
  ChatProgress,
  ChatFinal,
  ChatError,
  ChatAborted,
} from '../../../shared/ipc'

interface Attachment {
  name: string
  type: 'image' | 'text'
  dataUrl?: string
  content?: string
  size: number
}

interface Message {
  role: 'user' | 'assistant' | 'progress' | 'error'
  content: string
  attachments?: Attachment[]
  toolHint?: boolean
  timestamp: number
}

/* ─── Tracked file from tool hints ───────────────────────────────── */
interface TrackedFile {
  path: string
  name: string
  op: 'read' | 'write' | 'edit' | 'delete'
  /** epoch ms of last operation */
  lastSeen: number
  /** path was truncated in the progress message (ends with ...) */
  truncated?: boolean
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
function parseToolHint(text: string): { path: string; op: TrackedFile['op']; truncated: boolean } | null {
  const patterns: Array<[RegExp, TrackedFile['op']]> = [
    // "Read: /abs/path/to/file.ts"  or  "Reading file src/foo.ts …"
    [/^(?:Read|Reading(?:\s+file)?)[:\s]+(.+?)(?:\s*….*)?$/i, 'read'],
    [/^(?:Write|Writing(?:\s+file)?)[:\s]+(.+?)(?:\s*….*)?$/i, 'write'],
    [/^(?:Edit|Editing(?:\s+file)?)[:\s]+(.+?)(?:\s*….*)?$/i, 'edit'],
    [/^(?:Delete|Deleting(?:\s+file)?)[:\s]+(.+?)(?:\s*….*)?$/i, 'delete'],
    // nanobot / miqi style: write_file("path"), read_file("path"), edit_file("path")
    [/(?:write|edit|delete|read)_file\s*\(\s*["'](.+?)["']\s*\)/i, 'write'],
    // Generic fallback: any mention of a path-like string after a colon
    [/(?:file|path)[:\s]+([^\s,]+\.[a-zA-Z]{1,6})/i, 'read'],
  ]
  for (const [re, op] of patterns) {
    const m = text.match(re)
    if (m) {
      let raw = m[1].trim().replace(/['"]/g, '')
      // Detect truncation (ends with ...)
      const truncated = raw.endsWith('...') || raw.endsWith('…')
      // Strip trailing ellipsis / quotes
      raw = raw.replace(/\.{3,}$/g, '').replace(/…$/g, '').trim()
      // Must look like a file path (contains '/' or '\' or has extension)
      if (raw && /[/\\.]/.test(raw)) {
        // For the _file() pattern, try to infer a more specific op from the verb
        let inferredOp = op
        if (re.source.includes('write')) inferredOp = 'write'
        else if (re.source.includes('edit')) inferredOp = 'edit'
        else if (re.source.includes('delete')) inferredOp = 'delete'
        else if (re.source.includes('read')) inferredOp = 'read'
        return { path: raw, op: inferredOp, truncated }
      }
    }
  }
  return null
}

function basename(path: string): string {
  return path.replace(/\\/g, '/').split('/').pop() ?? path
}

const DEFAULT_SESSION = 'desktop:default'

function sessionMsgsToUi(rawMsgs: any[]): Message[] {
  return rawMsgs
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .map((m) => ({
      role: m.role as 'user' | 'assistant',
      content:
        typeof m.content === 'string' ? m.content : JSON.stringify(m.content),
      timestamp: m.timestamp ? new Date(m.timestamp).getTime() : Date.now(),
    }))
}

/** Parse tracked files from raw session messages (includes progress entries with _tool_hint). */
function extractTrackedFilesFromMessages(rawMsgs: any[]): TrackedFile[] {
  const fileMap = new Map<string, TrackedFile>()
  const rank: Record<TrackedFile['op'], number> = { read: 0, edit: 1, write: 2, delete: 3 }

  for (const msg of rawMsgs) {
    // Prefer _tool_hint_text (full path, from persisted session) over content (may be truncated)
    const hintText = msg._tool_hint_text || msg.content
    if (msg._tool_hint && hintText) {
      const parsed = parseToolHint(hintText)
      if (parsed) {
        const key = parsed.path
        const existing = fileMap.get(key)
        if (!existing || rank[parsed.op] > rank[existing.op]) {
          fileMap.set(key, {
            path: key,
            name: basename(key),
            op: parsed.op,
            lastSeen: msg.timestamp ? new Date(msg.timestamp).getTime() : Date.now(),
            truncated: parsed.truncated,
          })
        }
      }
    }
  }
  return Array.from(fileMap.values())
}

/* ─── Main component ─────────────────────────────────────────────── */
export function ChatConsole({
  sessionKey = DEFAULT_SESSION,
  onNewSession,
  onChatFinished,
}: {
  sessionKey?: string
  onNewSession?: (newKey: string) => void
  onChatFinished?: () => void
}) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null)
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [panelOpen, setPanelOpen] = useState(true)
  /** files touched by the agent during this session */
  const [trackedFiles, setTrackedFiles] = useState<TrackedFile[]>([])
  /** preview modal */
  const [previewFile, setPreviewFile] = useState<{ path: string; content: string } | null>(null)
  /** diff modal */
  const [diffFile, setDiffFile] = useState<{
    path: string
    diff: string | null
    original_content: string | null
    current_content: string | null
    has_diff: boolean
  } | null>(null)
  const [diffLoading, setDiffLoading] = useState(false)
  const [reverting, setReverting] = useState(false)
  const [merging, setMerging] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const unsubsRef = useRef<Array<() => void>>([])
  const currentSessionRef = useRef(sessionKey)

  /** Upsert a file into trackedFiles */
  const trackFile = useCallback((path: string, op: TrackedFile['op'], truncated = false) => {
    setTrackedFiles((prev) => {
      const existing = prev.find((f) => f.path === path)
      if (existing) {
        // Upgrade: read < edit < write
        const rank: Record<TrackedFile['op'], number> = { read: 0, edit: 1, write: 2, delete: 3 }
        const nextOp = rank[op] > rank[existing.op] ? op : existing.op
        return prev.map((f) => f.path === path ? { ...f, op: nextOp, lastSeen: Date.now(), truncated: f.truncated && truncated } : f)
      }
      return [...prev, { path, name: basename(path), op, lastSeen: Date.now(), truncated }]
    })
  }, [])

  useEffect(() => {
    currentSessionRef.current = sessionKey
    setHistoryLoaded(false)
    setMessages([])
    setTrackedFiles([])
    const load = async () => {
      try {
        const detail = await window.miqi.sessions.get(sessionKey)
        if (currentSessionRef.current !== sessionKey) return
        const rawMsgs: any[] = (detail as any)?.messages ?? []
        const uiMsgs = sessionMsgsToUi(rawMsgs)
        setMessages(uiMsgs)
        // Restore tracked files from session history
        setTrackedFiles(extractTrackedFilesFromMessages(rawMsgs))
      } catch { /* session doesn't exist yet */ }
      setHistoryLoaded(true)
    }
    load()
  }, [sessionKey])

  useEffect(() => {
    if (scrollRef.current)
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages])

  const cleanupListeners = useCallback(() => {
    for (const unsub of unsubsRef.current) unsub()
    unsubsRef.current = []
  }, [])

  const handleAttachClick = () => fileInputRef.current?.click()

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    Array.from(e.target.files ?? []).forEach((file) => {
      const isImage = file.type.startsWith('image/')
      const reader = new FileReader()
      if (isImage) {
        reader.onload = () =>
          setAttachments((prev) => [
            ...prev,
            { name: file.name, type: 'image', dataUrl: reader.result as string, size: file.size },
          ])
        reader.readAsDataURL(file)
      } else {
        reader.onload = () =>
          setAttachments((prev) => [
            ...prev,
            { name: file.name, type: 'text', content: reader.result as string, size: file.size },
          ])
        reader.readAsText(file)
      }
    })
    e.target.value = ''
  }

  const removeAttachment = (idx: number) =>
    setAttachments((prev) => prev.filter((_, i) => i !== idx))

  const handleAbort = useCallback(async () => {
    cleanupListeners()
    await window.miqi.chat.abort()
    setStreaming(false)
    setMessages((prev) => [
      ...prev,
      { role: 'progress', content: 'Aborted.', timestamp: Date.now() },
    ])
  }, [cleanupListeners])

  const handleNewSession = useCallback(async () => {
    if (streaming) return
    const oldKey = currentSessionRef.current
    const newKey = `desktop:${Date.now()}`
    cleanupListeners()
    try { await window.miqi.chat.send('/new', oldKey) } catch { /* ignore */ }
    onNewSession?.(newKey)
  }, [streaming, cleanupListeners, onNewSession])

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if ((!text && attachments.length === 0) || streaming) return

    let content = text
    for (const att of attachments) {
      if (att.type === 'text' && att.content)
        content += `\n\n[Attachment: ${att.name}]\n\`\`\`\n${att.content}\n\`\`\``
      else if (att.type === 'image' && att.dataUrl)
        content += `\n\n[Image: ${att.name}]`
    }

    const userMsg: Message = {
      role: 'user',
      content: text || '(attachment)',
      attachments: [...attachments],
      timestamp: Date.now(),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setAttachments([])
    setStreaming(true)
    cleanupListeners()

    let fullContent = ''
    let displayed = ''
    let animId: number | null = null
    let finalDone = false

    const revealNext = () => {
      if (displayed.length < fullContent.length) {
        displayed += fullContent.slice(displayed.length, displayed.length + 4)
        const snap = displayed
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last?.role === 'assistant' && last.timestamp === userMsg.timestamp + 1)
            return [...prev.slice(0, -1), { ...last, content: snap }]
          return prev
        })
        animId = requestAnimationFrame(revealNext)
      } else if (finalDone) {
        setStreaming(false)
        cleanupListeners()
        if (onChatFinished) onChatFinished()
      }
    }

    const unsubProgress = window.miqi.chat.onProgress((data: ChatProgress) => {
      setMessages((prev) => [
        ...prev,
        { role: 'progress', content: data.text, toolHint: data.tool_hint, timestamp: Date.now() },
      ])
      // Parse file operations from tool hints
      if (data.tool_hint && data.text) {
        const parsed = parseToolHint(data.text)
        if (parsed) trackFile(parsed.path, parsed.op, parsed.truncated)
      }
    })

    const unsubFinal = window.miqi.chat.onFinal((data: ChatFinal) => {
      fullContent = data.content
      finalDone = true
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: '', timestamp: userMsg.timestamp + 1 },
      ])
      animId = requestAnimationFrame(revealNext)
    })

    const unsubError = window.miqi.chat.onError((data: ChatError) => {
      if (animId !== null) cancelAnimationFrame(animId)
      setMessages((prev) => [
        ...prev,
        { role: 'error', content: data.message, timestamp: Date.now() },
      ])
      setStreaming(false)
      cleanupListeners()
    })

    const unsubAborted = window.miqi.chat.onAborted((_data: ChatAborted) => {
      if (animId !== null) cancelAnimationFrame(animId)
      setStreaming(false)
      setMessages((prev) => [
        ...prev,
        { role: 'progress', content: 'Aborted.', timestamp: Date.now() },
      ])
      cleanupListeners()
    })

    unsubsRef.current = [unsubProgress, unsubFinal, unsubError, unsubAborted]

    try {
      await window.miqi.chat.send(content, currentSessionRef.current)
    } catch (e: any) {
      if (animId !== null) cancelAnimationFrame(animId)
      setMessages((prev) => [
        ...prev,
        { role: 'error', content: e.message ?? String(e), timestamp: Date.now() },
      ])
      setStreaming(false)
      cleanupListeners()
    }
  }, [input, attachments, streaming, cleanupListeners, onChatFinished])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handlePreview = useCallback(async (path: string) => {
    try {
      const result = await window.miqi.files.read(path)
      setPreviewFile({ path, content: result.content })
    } catch {
      setPreviewFile({ path, content: `(Could not read file: ${path})` })
    }
  }, [])

  const closePreview = () => setPreviewFile(null)

  const handleShowDiff = useCallback(async (path: string) => {
    setDiffLoading(true)
    try {
      const result = await window.miqi.files.diff(path)
      setDiffFile({
        path,
        diff: result.diff,
        original_content: result.original_content,
        current_content: result.current_content,
        has_diff: result.has_diff,
      })
    } catch {
      setDiffFile({ path, diff: null, original_content: null, current_content: null, has_diff: false })
    } finally {
      setDiffLoading(false)
    }
  }, [])

  const closeDiff = () => setDiffFile(null)

  const handleRevert = useCallback(async () => {
    if (!diffFile || reverting) return
    setReverting(true)
    try {
      const result = await window.miqi.files.revert(diffFile.path)
      if (result.reverted) {
        // Refresh the diff view
        await handleShowDiff(diffFile.path)
        // Update tracked files list (file is now back to HEAD)
        setTrackedFiles((prev) => prev.filter((f) => f.path !== diffFile.path))
        // Refresh preview if open
        if (previewFile?.path === diffFile.path) {
          const content = await window.miqi.files.read(diffFile.path)
          setPreviewFile({ path: diffFile.path, content: content.content })
        }
      }
    } catch {
      // Silently fail - revert button is best-effort
    } finally {
      setReverting(false)
    }
  }, [diffFile, reverting, handleShowDiff, previewFile])

  /** Revert ALL tracked (modified) files at once. */
  const handleMergeAll = useCallback(async () => {
    if (merging) return
    const toRevert = trackedFiles.filter((f) => f.op === 'write' || f.op === 'edit' || f.op === 'delete')
    if (toRevert.length === 0) return
    setMerging(true)
    try {
      await Promise.allSettled(
        toRevert.map((f) => window.miqi.files.revert(f.path)),
      )
      setTrackedFiles([])
    } finally {
      setMerging(false)
    }
  }, [merging, trackedFiles])

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const files = Array.from(e.dataTransfer.files)
    if (!files.length || !fileInputRef.current) return
    const dt = new DataTransfer()
    files.forEach((f) => dt.items.add(f))
    fileInputRef.current.files = dt.files
    fileInputRef.current.dispatchEvent(new Event('change', { bubbles: true }))
  }

  const handleCopy = (text: string, idx: number) => {
    navigator.clipboard.writeText(text)
    setCopiedIdx(idx)
    setTimeout(() => setCopiedIdx(null), 2000)
  }

  const handleRetry = useCallback(async (msg: Message) => {
    if (streaming) return
    cleanupListeners()
    const idx = messages.indexOf(msg)
    if (idx >= 0) setMessages((prev) => prev.slice(0, idx))
    setInput(msg.content)
    setAttachments(msg.attachments ?? [])
  }, [streaming, cleanupListeners, messages])

  /* session display name */
  const sessionTitle = sessionKey.replace(/^desktop:/, '').replace(/_/g, ' ') || 'New Task'

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
        accept="image/*,text/*,.md,.txt,.py,.ts,.js,.json,.csv,.yaml,.yml,.toml"
        className="hidden"
        onChange={handleFileChange}
      />

      {/* ── Task header bar ── */}
      <div
        className="flex items-center justify-between px-5 h-12 border-b shrink-0"
        style={{
          background: 'var(--surface-elevated)',
          borderColor: 'var(--border-subtle)',
        }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <h2
            className="text-sm font-semibold truncate"
            style={{ color: 'var(--text)' }}
          >
            {sessionTitle}
          </h2>
          <span className="tag-review shrink-0">REVIEW</span>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {/* toggle panel */}
          <button
            onClick={() => setPanelOpen((v) => !v)}
            className="p-1.5 rounded hover:bg-[var(--surface-muted)] transition-colors"
            title="Toggle assets panel"
          >
            <LayoutGrid size={14} style={{ color: 'var(--text-faint)' }} />
          </button>
          <button className="p-1.5 rounded hover:bg-[var(--surface-muted)] transition-colors">
            <MoreHorizontal size={14} style={{ color: 'var(--text-faint)' }} />
          </button>
          {/* <button
            onClick={handleNewSession}
            disabled={streaming}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
            style={{
              background: 'var(--accent)',
              color: '#fff',
            }}
          >
            <Share2 size={12} />
            Share Task
          </button> */}
        </div>
      </div>

      {/* ── Main area: chat + right panel ── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Chat area */}
        <div className="flex flex-col flex-1 overflow-hidden">
          {/* Messages */}
          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto"
            style={{ background: 'var(--background)' }}
          >
            <div className="max-w-[760px] mx-auto px-6 py-5 flex flex-col gap-5">
              {!historyLoaded ? (
                <div className="flex items-center justify-center min-h-[300px]">
                  <Loader2
                    size={16}
                    className="animate-spin"
                    style={{ color: 'var(--text-faint)' }}
                  />
                </div>
              ) : messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center gap-3">
                  <div
                    className="w-14 h-14 rounded-2xl flex items-center justify-center text-xl font-bold text-white"
                    style={{ background: 'var(--topbar-bg)' }}
                  >
                    A
                  </div>
                  <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                    Ask Agent to analyze or edit files...
                  </p>
                </div>
              ) : (
                messages.map((msg, i) => (
                  <MessageBubble
                    key={`${msg.timestamp}-${i}`}
                    msg={msg}
                    isLast={i === messages.length - 1}
                    onCopy={(text) => handleCopy(text, i)}
                    isCopied={copiedIdx === i}
                    onRetry={() => handleRetry(msg)}
                  />
                ))
              )}
              {streaming &&
                messages.length > 0 &&
                messages[messages.length - 1].role === 'progress' && (
                  <div
                    className="flex items-center gap-2 text-xs px-1"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    <Loader2 size={12} className="animate-spin" />
                    Thinking…
                  </div>
                )}
            </div>
          </div>

          {/* Composer */}
          <div
            className="shrink-0 px-5 pb-4 pt-3 border-t"
            style={{
              background: 'var(--surface-elevated)',
              borderColor: 'var(--border-subtle)',
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
                        <Image
                          size={12}
                          className="shrink-0"
                          style={{ color: 'var(--info)' }}
                        />
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
                className="flex items-end gap-2 rounded-xl px-4 py-3 focus-within:ring-2 transition-all"
                style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  outline: 'none',
                }}
              >
                <button
                  onClick={handleAttachClick}
                  className="shrink-0 p-1 rounded hover:bg-[var(--surface-muted)] transition-colors"
                  title="Attach file or image"
                >
                  <Paperclip size={15} style={{ color: 'var(--text-faint)' }} />
                </button>
                <Textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask Agent to analyze or edit files..."
                  rows={1}
                  className="flex-1 border-0 bg-transparent p-0! leading-6! focus:ring-0 focus:border-0 min-h-0 resize-none text-sm"
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
                    disabled={!input.trim() && attachments.length === 0}
                    className="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center transition-colors disabled:opacity-30"
                    style={{ background: 'var(--accent)' }}
                  >
                    <Send size={13} style={{ color: '#fff' }} />
                  </button>
                )}
              </div>
              <p
                className="text-center text-[10px] mt-1.5"
                style={{ color: 'var(--text-faint)' }}
              >
                SHIFT + ENTER FOR NEW LINE • CTRL + ENTER TO SEND
              </p>
            </div>
          </div>
        </div>

        {/* ── Right panel: Task Assets ── */}
        {panelOpen && (
          <div
            className="flex flex-col shrink-0 border-l overflow-y-auto"
            style={{
              width: 280,
              background: 'var(--panel-bg)',
              borderColor: 'var(--panel-border)',
            }}
          >
            <div
              className="flex items-center justify-between px-4 py-3 border-b shrink-0"
              style={{ borderColor: 'var(--panel-border)' }}
            >
              <div className="flex items-center gap-1.5">
                <LayoutGrid size={13} style={{ color: 'var(--text-muted)' }} />
                <span
                  className="text-xs font-semibold"
                  style={{ color: 'var(--text)' }}
                >
                  Task Assets
                </span>
              </div>
              <span
                className="text-xs font-medium"
                style={{ color: 'var(--text-faint)' }}
              >
                {trackedFiles.length}
              </span>
            </div>

            {trackedFiles.length === 0 ? (
              <div className="flex flex-col items-center justify-center flex-1 px-4 py-8 text-center gap-2">
                <FileText
                  size={24}
                  style={{ color: 'var(--text-faint)', opacity: 0.4 }}
                />
                <p
                  className="text-[11px]"
                  style={{ color: 'var(--text-faint)' }}
                >
                  No files yet.
                  <br />
                  Agent operations will appear here.
                </p>
              </div>
            ) : (
              <>
                {/* Written / Edited files → Active for Edit */}
                {trackedFiles.filter((f) => f.op === 'write' || f.op === 'edit')
                  .length > 0 && (
                  <>
                    <SectionLabel label="ACTIVE FOR EDIT" />
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
                    <SectionLabel label="REFERENCED CONTEXT" />
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
                    <SectionLabel label="DELETED" />
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
            {trackedFiles.filter((f) => f.op === 'write' || f.op === 'edit')
              .length > 0 && (
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
                    <span
                      className="text-xs font-semibold"
                      style={{ color: 'var(--text)' }}
                    >
                      Proposed Changes
                    </span>
                  </div>
                  <span
                    className="text-[10px]"
                    style={{ color: 'var(--text-faint)' }}
                  >
                    {
                      trackedFiles.filter(
                        (f) => f.op === 'write' || f.op === 'edit',
                      ).length
                    }{' '}
                    file(s)
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
                        <FileText
                          size={11}
                          style={{ color: 'var(--info)' }}
                          className="shrink-0"
                        />
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
                            background:
                              f.op === 'write'
                                ? 'var(--accent)'
                                : 'rgba(234,179,8,0.15)',
                            color:
                              f.op === 'write'
                                ? 'var(--accent-text)'
                                : 'var(--warning)',
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
                className="w-full py-2.5 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition-colors"
                style={{
                  background:
                    merging || trackedFiles.length === 0
                      ? 'var(--surface-muted)'
                      : 'var(--accent)',
                  color:
                    merging || trackedFiles.length === 0
                      ? 'var(--text-faint)'
                      : 'var(--accent-text)',
                }}
              >
                {merging ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <GitMerge size={13} />
                )}
                {merging ? 'MERGING...' : 'MERGE ALL CHANGES'}
              </button>
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
              <div className="flex items-center gap-2 min-w-0">
                <FileText
                  size={14}
                  style={{ color: 'var(--info)' }}
                  className="shrink-0"
                />
                <span
                  className="text-sm font-medium truncate"
                  style={{ color: 'var(--text)' }}
                  title={previewFile.path}
                >
                  {previewFile.path}
                </span>
              </div>
              <button
                onClick={closePreview}
                className="p-1 rounded hover:bg-[var(--surface-muted)] transition-colors shrink-0"
              >
                <X size={14} style={{ color: 'var(--text-faint)' }} />
              </button>
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
                <GitCompare
                  size={14}
                  style={{ color: 'var(--warning)' }}
                  className="shrink-0"
                />
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
                      background: reverting
                        ? 'var(--surface-muted)'
                        : 'rgba(239,68,68,0.15)',
                      color: reverting ? 'var(--text-faint)' : 'var(--danger)',
                      border: '1px solid var(--danger)',
                    }}
                    title="Revert to HEAD (undo changes)"
                  >
                    <Undo2
                      size={12}
                      className={reverting ? 'animate-spin' : ''}
                    />
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
                  <span
                    className="ml-2 text-sm"
                    style={{ color: 'var(--text-faint)' }}
                  >
                    Loading diff...
                  </span>
                </div>
              ) : diffFile.diff ? (
                <DiffView diff={diffFile.diff} />
              ) : diffFile.original_content !== null &&
                diffFile.current_content !== null ? (
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
                  <span
                    className="text-sm"
                    style={{ color: 'var(--text-faint)' }}
                  >
                    {diffFile.original_content === null &&
                    diffFile.current_content === null
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
  )
}

/* ─── Sub-components ──────────────────────────────────────────────── */

/** Renders a unified diff string with syntax-highlighted +/- lines. */
function DiffView({ diff }: { diff: string }) {
  const lines = diff.split('\n')
  return (
    <div className="overflow-x-auto text-xs font-mono leading-5" style={{ background: 'var(--surface)' }}>
      {lines.map((line, i) => {
        let bg = 'transparent'
        let color = 'var(--text-muted)'
        let prefix = ' '

        if (line.startsWith('+++') || line.startsWith('---')) {
          color = 'var(--text-faint)'
        } else if (line.startsWith('@@')) {
          bg = 'rgba(96,165,250,0.08)'
          color = 'var(--info)'
        } else if (line.startsWith('+')) {
          bg = 'rgba(34,197,94,0.10)'
          color = '#4ade80'
          prefix = '+'
        } else if (line.startsWith('-')) {
          bg = 'rgba(239,68,68,0.10)'
          color = '#f87171'
          prefix = '-'
        }

        return (
          <div
            key={i}
            style={{ background: bg, color, paddingLeft: 12, paddingRight: 12, whiteSpace: 'pre', minWidth: '100%', display: 'block' }}
          >
            {line || '\u00a0'}
          </div>
        )
      })}
    </div>
  )
}

function SectionLabel({ label }: { label: string }) {
  return (
    <div
      className="px-4 pt-3 pb-1.5 text-[10px] font-semibold uppercase tracking-widest"
      style={{ color: 'var(--text-faint)' }}
    >
      {label}
    </div>
  )
}

function TrackedFileCard({
  file,
  onPreview,
  onDiff,
}: {
  file: TrackedFile
  onPreview: () => void
  onDiff?: () => void
}) {
  const opColor: Record<TrackedFile['op'], string> = {
    read: 'var(--info)',
    edit: 'var(--warning)',
    write: 'var(--accent)',
    delete: 'var(--danger)',
  }
  const OpIcon = file.op === 'read' ? BookOpen : file.op === 'delete' ? X : Pencil

  return (
    <div
      className="rounded-lg p-2.5"
      style={{
        border: '1px solid var(--border-subtle)',
        background: 'var(--surface)',
      }}
    >
      <div className="flex items-start gap-2 mb-2">
        <FileText size={14} className="shrink-0 mt-0.5" style={{ color: opColor[file.op] }} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap mb-0.5">
            <span
              className="text-[11px] font-medium truncate"
              style={{ color: 'var(--text)' }}
              title={file.path}
            >
              {file.name.length > 20 ? file.name.slice(0, 18) + '…' : file.name}
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
          </div>
          <span
            className="text-[10px] font-mono truncate block"
            style={{ color: 'var(--text-faint)' }}
            title={file.path}
          >
            {file.path.replace(/\\/g, '/').length > 28
              ? '…' + file.path.replace(/\\/g, '/').slice(-26)
              : file.path.replace(/\\/g, '/')}
          </span>
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
              className="flex-1 flex items-center justify-center gap-1 py-1 rounded-md text-[11px] transition-colors"
              style={{
                border: '1px solid var(--border)',
                color: 'var(--warning)',
              }}
              title="Compare diff"
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
          >
            <Eye size={10} />
            Preview
          </button>
        </div>
      )}
    </div>
  )
}

function MessageBubble({ msg, isLast, onCopy, isCopied, onRetry }: {
  msg: Message
  isLast: boolean
  onCopy: (text: string) => void
  isCopied: boolean
  onRetry?: () => void
}) {
  if (msg.role === 'progress') {
    return (
      <div
        className={cn('flex items-center gap-2 text-xs py-1 px-1')}
        style={{ color: msg.toolHint ? 'var(--info)' : 'var(--text-muted)' }}
      >
        {msg.toolHint ? <Wrench size={12} /> : <Loader2 size={12} className="animate-spin" />}
        <span>{msg.content}</span>
      </div>
    )
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
          {msg.content}
        </div>
      </div>
    )
  }

  const isUser = msg.role === 'user'
  const hasCodeBlock = /```[\s\S]*?```/.test(msg.content)

  const contextItems: ContextMenuAction[] = isUser
    ? [
        { label: 'Copy text', onSelect: () => onCopy(msg.content) },
        { label: 'Retry', onSelect: () => onRetry?.() },
      ]
    : [
        { label: 'Copy text', onSelect: () => onCopy(msg.content) },
        ...(hasCodeBlock ? [{ label: 'Copy code', onSelect: () => {
          const codeMatch = msg.content.match(/```[\s\S]*?```/g)
          if (codeMatch) {
            const code = codeMatch.map(b => b.replace(/```\w*\n?/g, '').replace(/```$/g, '')).join('\n\n')
            navigator.clipboard.writeText(code).catch(() => {})
          }
        } }] : []),
      ]

  return (
    <ContextMenu items={contextItems}>
      {({ onContextMenu }) => (
        <div
          className={cn('flex items-start gap-3', isUser && 'justify-end')}
          onContextMenu={onContextMenu}
        >
          {!isUser && <AgentAvatar />}

          <div className={cn('group flex flex-col gap-1.5', isUser ? 'items-end max-w-[70%]' : 'max-w-[82%]')}>
            {/* image attachments */}
            {msg.attachments?.filter(a => a.type === 'image').map((att, i) => (
              <img
                key={i}
                src={att.dataUrl}
                alt={att.name}
                className="rounded-xl max-w-[280px] max-h-[200px] object-cover"
                style={{ border: '1px solid var(--border-subtle)' }}
              />
            ))}
            {/* text attachments */}
            {msg.attachments?.filter(a => a.type === 'text').map((att, i) => (
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
              {msg.role === 'assistant' && msg.content === ''
                ? <span className="inline-block w-2 h-4 bg-[var(--accent)] animate-pulse rounded-sm" />
                : msg.role === 'assistant'
                  ? <MarkdownContent content={msg.content} />
                  : renderContent(msg.content)}
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
  )
}

function AgentAvatar() {
  return (
    <div
      className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-xs font-bold text-white mt-0.5"
      style={{ background: 'var(--topbar-bg)' }}
    >
      A
    </div>
  )
}

function UserAvatar() {
  return (
    <div
      className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-xs font-bold text-white mt-0.5"
      style={{ background: 'var(--topbar-bg)' }}
    >
      U
    </div>
  )
}

function MarkdownContent({ content }: { content: string }) {
  const [copiedCode, setCopiedCode] = useState<string | null>(null)

  const handleCopyCode = (code: string) => {
    navigator.clipboard.writeText(code)
    setCopiedCode(code)
    setTimeout(() => setCopiedCode(null), 2000)
  }

  const components = useMemo(
    () => ({
      p: ({ children }: any) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
      h1: ({ children }: any) => <h1 className="text-base font-bold mt-3 mb-1.5 first:mt-0">{children}</h1>,
      h2: ({ children }: any) => <h2 className="text-sm font-bold mt-3 mb-1 first:mt-0">{children}</h2>,
      h3: ({ children }: any) => <h3 className="text-sm font-semibold mt-2 mb-0.5 first:mt-0">{children}</h3>,
      ul: ({ children }: any) => <ul className="list-disc pl-5 my-1.5 space-y-0.5">{children}</ul>,
      ol: ({ children }: any) => <ol className="list-decimal pl-5 my-1.5 space-y-0.5">{children}</ol>,
      li: ({ children }: any) => <li className="leading-relaxed">{children}</li>,
      blockquote: ({ children }: any) => (
        <blockquote className="border-l-2 pl-3 my-2 italic" style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}>
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
          onClick={(e) => { e.preventDefault(); if (href) window.open(href, '_blank') }}
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
        <th className="border px-2 py-1.5 text-left font-medium" style={{ borderColor: 'var(--border)', background: 'var(--surface-muted)' }}>
          {children}
        </th>
      ),
      td: ({ children }: any) => (
        <td className="border px-2 py-1.5" style={{ borderColor: 'var(--border-subtle)' }}>
          {children}
        </td>
      ),
      pre: ({ children }: any) => (
        <pre className="relative group my-2 rounded-lg overflow-x-auto" style={{ background: 'rgba(0,0,0,0.06)' }}>
          {children}
        </pre>
      ),
      code: ({ className, children, ...props }: any) => {
        const codeStr = String(children)
        const isBlock = codeStr.endsWith('\n')
        if (isBlock) {
          const code = codeStr.replace(/\n$/, '')
          return (
            <code className={cn('block text-xs font-mono p-3', className)} {...props}>
              <button
                onClick={() => handleCopyCode(code)}
                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity rounded px-1.5 py-0.5 text-[10px] leading-none"
                style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}
              >
                {copiedCode === code ? 'Copied' : 'Copy'}
              </button>
              {code}
            </code>
          )
        }
        return (
          <code className="text-xs font-mono px-1.5 py-0.5 rounded" style={{ background: 'rgba(0,0,0,0.08)' }} {...props}>
            {children}
          </code>
        )
      },
    }),
    [copiedCode],
  )

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {content}
    </ReactMarkdown>
  )
}

function renderContent(text: string) {
  const parts = text.split(/(```[\s\S]*?```)/g)
  return parts.map((part, i) => {
    if (part.startsWith('```') && part.endsWith('```')) {
      const inner = part.slice(3, -3)
      const langEnd = inner.indexOf('\n')
      const code = langEnd > 0 ? inner.slice(langEnd + 1) : inner
      return (
        <pre key={i} className="my-2 text-xs rounded-lg px-3 py-2 overflow-x-auto" style={{ background: 'rgba(0,0,0,0.06)' }}>
          <code>{code}</code>
        </pre>
      )
    }
    const segments = part.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
    return (
      <span key={i}>
        {segments.map((seg, j) => {
          if (seg.startsWith('**') && seg.endsWith('**'))
            return <strong key={j}>{seg.slice(2, -2)}</strong>
          if (seg.startsWith('`') && seg.endsWith('`'))
            return <code key={j} className="text-xs font-mono px-1 rounded" style={{ background: 'rgba(0,0,0,0.08)' }}>{seg.slice(1, -1)}</code>
          return (
            <span key={j}>
              {seg.split('\n').map((line, k, arr) => (
                <span key={k}>{line}{k < arr.length - 1 && <br />}</span>
              ))}
            </span>
          )
        })}
      </span>
    )
  })
}
