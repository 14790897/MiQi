import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '../../components/ui/Button'
import { Textarea } from '../../components/ui/Textarea'
import { cn } from '../../lib/utils'
import {
  Send,
  Square,
  User,
  Bot,
  Wrench,
  Loader2,
  Copy,
  Check,
  Paperclip,
  X,
  FileText,
  Image,
  Plus,
} from 'lucide-react'
import type { ChatProgress, ChatFinal, ChatError, ChatAborted } from '../../../shared/ipc'

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

const DEFAULT_SESSION = 'desktop:default'

function sessionMsgsToUi(rawMsgs: any[]): Message[] {
  return rawMsgs
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .map((m) => ({
      role: m.role as 'user' | 'assistant',
      content: typeof m.content === 'string' ? m.content : JSON.stringify(m.content),
      timestamp: m.timestamp ? new Date(m.timestamp).getTime() : Date.now(),
    }))
}

export function ChatConsole({ sessionKey = DEFAULT_SESSION, onNewSession, onChatFinished }: {
  sessionKey?: string
  onNewSession?: () => void
  onChatFinished?: () => void
}) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null)
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const unsubsRef = useRef<Array<() => void>>([])
  const currentSessionRef = useRef(sessionKey)

  // Load session history on mount or when sessionKey changes
  useEffect(() => {
    currentSessionRef.current = sessionKey
    setHistoryLoaded(false)
    setMessages([])
    const load = async () => {
      try {
        const detail = await window.miqi.sessions.get(sessionKey)
        if (currentSessionRef.current !== sessionKey) return
        const uiMsgs = sessionMsgsToUi((detail as any)?.messages ?? [])
        setMessages(uiMsgs)
      } catch { /* session doesn't exist yet */ }
      setHistoryLoaded(true)
    }
    load()
  }, [sessionKey])

  // Auto-scroll
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
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
        reader.onload = () => setAttachments((prev) => [...prev, { name: file.name, type: 'image', dataUrl: reader.result as string, size: file.size }])
        reader.readAsDataURL(file)
      } else {
        reader.onload = () => setAttachments((prev) => [...prev, { name: file.name, type: 'text', content: reader.result as string, size: file.size }])
        reader.readAsText(file)
      }
    })
    e.target.value = ''
  }

  const removeAttachment = (idx: number) => setAttachments((prev) => prev.filter((_, i) => i !== idx))

  const handleAbort = useCallback(async () => {
    cleanupListeners()
    await window.miqi.chat.abort()
    setStreaming(false)
    setMessages((prev) => [...prev, { role: 'progress', content: '已中止。', timestamp: Date.now() }])
  }, [cleanupListeners])

  const handleNewSession = useCallback(async () => {
    if (streaming) return
    setMessages([])
    cleanupListeners()
    try { await window.miqi.chat.send('/new') } catch { /* ignore */ }
    if (onNewSession) onNewSession()
  }, [streaming, cleanupListeners, onNewSession])

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if ((!text && attachments.length === 0) || streaming) return

    let content = text
    for (const att of attachments) {
      if (att.type === 'text' && att.content) content += `\n\n[附件: ${att.name}]\n\`\`\`\n${att.content}\n\`\`\``
      else if (att.type === 'image' && att.dataUrl) content += `\n\n[图片附件: ${att.name}]`
    }

    const userMsg: Message = { role: 'user', content: text || '(附件)', attachments: [...attachments], timestamp: Date.now() }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setAttachments([])
    setStreaming(true)
    cleanupListeners()

    // Typewriter animation state
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
      setMessages((prev) => [...prev, { role: 'progress', content: data.text, toolHint: data.tool_hint, timestamp: Date.now() }])
    })

    const unsubFinal = window.miqi.chat.onFinal((data: ChatFinal) => {
      fullContent = data.content
      finalDone = true
      setMessages((prev) => [...prev, { role: 'assistant', content: '', timestamp: userMsg.timestamp + 1 }])
      animId = requestAnimationFrame(revealNext)
    })

    const unsubError = window.miqi.chat.onError((data: ChatError) => {
      if (animId !== null) cancelAnimationFrame(animId)
      setMessages((prev) => [...prev, { role: 'error', content: data.message, timestamp: Date.now() }])
      setStreaming(false)
      cleanupListeners()
    })

    const unsubAborted = window.miqi.chat.onAborted((_data: ChatAborted) => {
      if (animId !== null) cancelAnimationFrame(animId)
      setStreaming(false)
      setMessages((prev) => [...prev, { role: 'progress', content: '已中止。', timestamp: Date.now() }])
      cleanupListeners()
    })

    unsubsRef.current = [unsubProgress, unsubFinal, unsubError, unsubAborted]

    try {
      await window.miqi.chat.send(content)
    } catch (e: any) {
      if (animId !== null) cancelAnimationFrame(animId)
      setMessages((prev) => [...prev, { role: 'error', content: e.message ?? String(e), timestamp: Date.now() }])
      setStreaming(false)
      cleanupListeners()
    }
  }, [input, attachments, streaming, cleanupListeners, onChatFinished])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

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

  return (
    <div className="flex flex-col h-full" onDrop={handleDrop} onDragOver={(e) => e.preventDefault()}>
      <input ref={fileInputRef} type="file" multiple accept="image/*,text/*,.md,.txt,.py,.ts,.js,.json,.csv,.yaml,.yml,.toml" className="hidden" onChange={handleFileChange} />

      {/* Toolbar */}
      <div className="shrink-0 flex items-center justify-between px-6 py-2 border-b border-[var(--border-subtle)]">
        <span className="text-xs text-[var(--text-faint)] font-mono">{sessionKey}</span>
        <Button size="sm" variant="ghost" onClick={handleNewSession} disabled={streaming} className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]" title="新建会话">
          <Plus size={13} />
          新建会话
        </Button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="max-w-[820px] mx-auto px-6 py-4 flex flex-col gap-4">
          {!historyLoaded ? (
            <div className="flex items-center justify-center min-h-[300px]">
              <Loader2 size={16} className="animate-spin text-[var(--text-faint)]" />
            </div>
          ) : messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center gap-3">
              <div className="w-12 h-12 rounded-full bg-[var(--accent-soft)] flex items-center justify-center">
                <Bot size={24} className="text-[var(--accent)]" />
              </div>
              <p className="text-sm text-[var(--text-muted)]">发送消息开始与 MiQi 对话。</p>
            </div>
          ) : (
            messages.map((msg, i) => (
              <MessageBubble
                key={`${msg.timestamp}-${i}`}
                msg={msg}
                isLast={i === messages.length - 1}
                onCopy={(text) => handleCopy(text, i)}
                isCopied={copiedIdx === i}
              />
            ))
          )}
          {streaming && messages.length > 0 && messages[messages.length - 1].role === 'progress' && (
            <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] px-1">
              <Loader2 size={12} className="animate-spin" />
              思考中…
            </div>
          )}
        </div>
      </div>

      {/* Composer */}
      <div className="shrink-0 px-6 pb-4 pt-2">
        <div className="max-w-[820px] mx-auto">
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {attachments.map((att, i) => (
                <div key={i} className="flex items-center gap-1.5 bg-[var(--surface-muted)] border border-[var(--border-subtle)] rounded-lg px-2 py-1 text-xs text-[var(--text-muted)] max-w-[200px]">
                  {att.type === 'image' ? <Image size={12} className="shrink-0 text-[var(--info)]" /> : <FileText size={12} className="shrink-0 text-[var(--text-faint)]" />}
                  <span className="truncate">{att.name}</span>
                  <button onClick={() => removeAttachment(i)} className="shrink-0 hover:text-[var(--danger)]">
                    <X size={11} />
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="flex items-end gap-2 bg-[var(--surface)] border border-[var(--border)] rounded-xl px-4 py-3 focus-within:border-[var(--accent)] focus-within:ring-2 focus-within:ring-[var(--accent)]/20 transition-all">
            <Button size="icon" variant="ghost" onClick={handleAttachClick} className="shrink-0 text-[var(--text-faint)] hover:text-[var(--text-muted)]" title="附加文件或图片">
              <Paperclip size={16} />
            </Button>
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息…"
              rows={1}
              className="flex-1 border-0 bg-transparent p-0 focus:ring-0 focus:border-0 min-h-0 resize-none"
              disabled={streaming}
            />
            {streaming ? (
              <Button size="icon" variant="ghost" onClick={handleAbort} className="shrink-0">
                <Square size={16} />
              </Button>
            ) : (
              <Button size="icon" onClick={handleSend} disabled={!input.trim() && attachments.length === 0} className="shrink-0">
                <Send size={16} />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function MessageBubble({ msg, isLast, onCopy, isCopied }: {
  msg: Message
  isLast: boolean
  onCopy: (text: string) => void
  isCopied: boolean
}) {
  if (msg.role === 'progress') {
    return (
      <div className={cn('flex items-center gap-2 text-xs py-1 px-1', msg.toolHint ? 'text-[var(--info)]' : 'text-[var(--text-muted)]')}>
        {msg.toolHint ? <Wrench size={12} /> : <Loader2 size={12} className="animate-spin" />}
        <span>{msg.content}</span>
      </div>
    )
  }
  if (msg.role === 'error') {
    return (
      <div className="flex items-start gap-3 px-1">
        <div className="w-7 h-7 rounded-full bg-[var(--danger)]/15 flex items-center justify-center shrink-0 mt-0.5">
          <Bot size={14} className="text-[var(--danger)]" />
        </div>
        <div className="text-sm text-[var(--danger)] bg-[var(--danger)]/5 rounded-lg px-3 py-2">{msg.content}</div>
      </div>
    )
  }
  const isUser = msg.role === 'user'
  return (
    <div className={cn('flex items-start gap-3', isUser && 'justify-end')}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-[var(--accent-soft)] flex items-center justify-center shrink-0 mt-0.5">
          <Bot size={14} className="text-[var(--accent)]" />
        </div>
      )}
      <div className={cn('group flex flex-col gap-1 max-w-[75%]', isUser && 'items-end')}>
        {msg.attachments?.filter(a => a.type === 'image').map((att, i) => (
          <img key={i} src={att.dataUrl} alt={att.name}
            className="rounded-lg max-w-[300px] max-h-[200px] object-cover border border-[var(--border-subtle)]" />
        ))}
        {msg.attachments?.filter(a => a.type === 'text').map((att, i) => (
          <div key={i} className="flex items-center gap-1.5 bg-[var(--surface-muted)] border border-[var(--border-subtle)] rounded-lg px-2.5 py-1.5 text-xs text-[var(--text-muted)]">
            <FileText size={12} className="shrink-0 text-[var(--text-faint)]" />
            <span>{att.name}</span>
          </div>
        ))}
        <div className={cn(
          'text-sm leading-relaxed rounded-xl px-4 py-2.5',
          isUser ? 'bg-[var(--accent-soft)] text-[var(--text)]' : 'bg-[var(--surface)] border border-[var(--border-subtle)] text-[var(--text)]',
        )}>
          {msg.role === 'assistant' && msg.content === ''
            ? <span className="inline-block w-2 h-4 bg-[var(--accent)] animate-pulse rounded-sm" />
            : msg.role === 'assistant'
              ? <MarkdownContent content={msg.content} />
              : renderContent(msg.content)}
        </div>
        {!isUser && msg.content !== '' && (
          <button
            onClick={() => onCopy(msg.content)}
            className="self-start opacity-0 group-hover:opacity-100 transition-opacity text-[var(--text-faint)] hover:text-[var(--text-muted)] p-0.5"
          >
            {isCopied ? <Check size={12} /> : <Copy size={12} />}
          </button>
        )}
      </div>
      {isUser && (
        <div className="w-7 h-7 rounded-full bg-[var(--surface-muted)] flex items-center justify-center shrink-0 mt-0.5">
          <User size={14} className="text-[var(--text-muted)]" />
        </div>
      )}
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

  const components = useMemo(() => ({
    p: ({ children }: any) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
    h1: ({ children }: any) => <h1 className="text-base font-bold mt-3 mb-1.5 first:mt-0">{children}</h1>,
    h2: ({ children }: any) => <h2 className="text-sm font-bold mt-3 mb-1 first:mt-0">{children}</h2>,
    h3: ({ children }: any) => <h3 className="text-sm font-semibold mt-2 mb-0.5 first:mt-0">{children}</h3>,
    ul: ({ children }: any) => <ul className="list-disc pl-5 my-1.5 space-y-0.5">{children}</ul>,
    ol: ({ children }: any) => <ol className="list-decimal pl-5 my-1.5 space-y-0.5">{children}</ol>,
    li: ({ children }: any) => <li className="leading-relaxed">{children}</li>,
    blockquote: ({ children }: any) => (
      <blockquote className="border-l-2 border-[var(--border)] pl-3 my-2 text-[var(--text-muted)] italic">{children}</blockquote>
    ),
    strong: ({ children }: any) => <strong className="font-semibold">{children}</strong>,
    em: ({ children }: any) => <em className="italic">{children}</em>,
    hr: () => <hr className="border-[var(--border-subtle)] my-3" />,
    a: ({ href, children }: any) => (
      <a
        href={href}
        className="text-[var(--accent)] underline hover:text-[var(--accent-hover)] cursor-pointer"
        onClick={(e) => { e.preventDefault(); if (href) window.open(href, '_blank') }}
      >{children}</a>
    ),
    table: ({ children }: any) => (
      <div className="overflow-x-auto my-2">
        <table className="text-xs w-full border-collapse">{children}</table>
      </div>
    ),
    th: ({ children }: any) => (
      <th className="border border-[var(--border)] px-2 py-1.5 bg-[var(--surface-muted)] text-left font-medium">{children}</th>
    ),
    td: ({ children }: any) => (
      <td className="border border-[var(--border-subtle)] px-2 py-1.5">{children}</td>
    ),
    pre: ({ children }: any) => (
      <pre className="relative group my-2 bg-[var(--surface-muted)] rounded-lg overflow-x-auto">
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
              className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-[var(--surface)] border border-[var(--border)] rounded px-1.5 py-0.5 text-[10px] text-[var(--text-muted)] hover:text-[var(--text)] leading-none"
            >
              {copiedCode === code ? '已复制' : '复制'}
            </button>
            {code}
          </code>
        )
      }
      return <code className="text-xs font-mono bg-[var(--surface-muted)] px-1.5 py-0.5 rounded" {...props}>{children}</code>
    },
  }), [copiedCode])

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {content}
    </ReactMarkdown>
  )
}

function renderContent(text: string) {
  // Legacy: kept for user messages (plain text with basic formatting)
  const parts = text.split(/(```[\s\S]*?```)/g)
  return parts.map((part, i) => {
    if (part.startsWith('```') && part.endsWith('```')) {
      const inner = part.slice(3, -3)
      const langEnd = inner.indexOf('\n')
      const code = langEnd > 0 ? inner.slice(langEnd + 1) : inner
      return (
        <pre key={i} className="my-2 text-xs bg-[var(--surface-muted)] rounded-lg px-3 py-2 overflow-x-auto">
          <code>{code}</code>
        </pre>
      )
    }
    const segments = part.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
    return (
      <span key={i}>
        {segments.map((seg, j) => {
          if (seg.startsWith('**') && seg.endsWith('**')) return <strong key={j}>{seg.slice(2, -2)}</strong>
          if (seg.startsWith('`') && seg.endsWith('`')) return <code key={j} className="text-xs bg-[var(--surface-muted)] px-1 rounded">{seg.slice(1, -1)}</code>
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
