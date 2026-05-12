import { useState, useRef, useEffect, useCallback } from 'react'
import { Button } from '../../components/ui/Button'
import { Textarea } from '../../components/ui/Textarea'
import { ScrollArea } from '../../components/ui/ScrollArea'
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
} from 'lucide-react'
import type { ChatProgress, ChatFinal, ChatError, ChatAborted } from '../../../shared/ipc'

interface Message {
  role: 'user' | 'assistant' | 'progress' | 'error'
  content: string
  toolHint?: boolean
  timestamp: number
}

export function ChatConsole() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-scroll
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  // Store active listeners in a ref so abort can clean them up
  const unsubsRef = useRef<Array<() => void>>([])

  const cleanupListeners = useCallback(() => {
    for (const unsub of unsubsRef.current) {
      unsub()
    }
    unsubsRef.current = []
  }, [])

  const handleAbort = useCallback(async () => {
    // Clean up event listeners immediately so no more events arrive
    cleanupListeners()
    await window.miqi.chat.abort()
    setStreaming(false)
    setMessages((prev) => [...prev, {
      role: 'progress',
      content: 'Chat aborted by user.',
      timestamp: Date.now(),
    }])
  }, [cleanupListeners])

  const handleSend = useCallback(async () => {
    const content = input.trim()
    if (!content || streaming) return

    const userMsg: Message = { role: 'user', content, timestamp: Date.now() }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setStreaming(true)

    // Clean up any previous listeners
    cleanupListeners()

    const unsubProgress = window.miqi.chat.onProgress((data: ChatProgress) => {
      setMessages((prev) => [...prev, {
        role: 'progress',
        content: data.text,
        toolHint: data.tool_hint,
        timestamp: Date.now(),
      }])
    })

    const unsubFinal = window.miqi.chat.onFinal((data: ChatFinal) => {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: data.content,
        timestamp: Date.now(),
      }])
      setStreaming(false)
      cleanupListeners()
    })

    const unsubError = window.miqi.chat.onError((data: ChatError) => {
      setMessages((prev) => [...prev, {
        role: 'error',
        content: data.message,
        timestamp: Date.now(),
      }])
      setStreaming(false)
      cleanupListeners()
    })

    const unsubAborted = window.miqi.chat.onAborted((_data: ChatAborted) => {
      setStreaming(false)
      setMessages((prev) => [...prev, {
        role: 'progress',
        content: 'Chat aborted by user.',
        timestamp: Date.now(),
      }])
      cleanupListeners()
    })

    unsubsRef.current = [unsubProgress, unsubFinal, unsubError, unsubAborted]

    try {
      await window.miqi.chat.send(content)
    } catch (e: any) {
      setMessages((prev) => [...prev, {
        role: 'error',
        content: e.message ?? String(e),
        timestamp: Date.now(),
      }])
      setStreaming(false)
      cleanupListeners()
    }
  }, [input, streaming, cleanupListeners])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleCopy = (text: string, idx: number) => {
    navigator.clipboard.writeText(text)
    setCopiedIdx(idx)
    setTimeout(() => setCopiedIdx(null), 2000)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="max-w-[820px] mx-auto px-6 py-4 flex flex-col gap-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center gap-3">
              <div className="w-12 h-12 rounded-full bg-[var(--accent-soft)] flex items-center justify-center">
                <Bot size={24} className="text-[var(--accent)]" />
              </div>
              <p className="text-sm text-[var(--text-muted)]">
                Send a message to start chatting with MiQi.
              </p>
            </div>
          )}

          {messages.map((msg, i) => (
            <MessageBubble
              key={`${msg.timestamp}-${i}`}
              msg={msg}
              isLast={i === messages.length - 1}
              onCopy={(text) => handleCopy(text, i)}
              isCopied={copiedIdx === i}
            />
          ))}

          {streaming && messages.length > 0 && messages[messages.length - 1].role === 'progress' && (
            <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] px-1">
              <Loader2 size={12} className="animate-spin" />
              Thinking...
            </div>
          )}
        </div>
      </div>

      {/* Composer */}
      <div className="shrink-0 px-6 pb-4 pt-2">
        <div className="max-w-[820px] mx-auto">
          <div className="flex items-end gap-2 bg-[var(--surface)] border border-[var(--border)] rounded-xl px-4 py-3 focus-within:border-[var(--accent)] focus-within:ring-2 focus-within:ring-[var(--accent)]/20 transition-all">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type a message..."
              rows={1}
              className="flex-1 border-0 bg-transparent p-0 focus:ring-0 focus:border-0 min-h-0 resize-none"
              disabled={streaming}
            />
            {streaming ? (
              <Button size="icon" variant="ghost" onClick={handleAbort} className="shrink-0">
                <Square size={16} />
              </Button>
            ) : (
              <Button
                size="icon"
                onClick={handleSend}
                disabled={!input.trim()}
                className="shrink-0"
              >
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
      <div className={cn(
        'flex items-center gap-2 text-xs py-1 px-1',
        msg.toolHint ? 'text-[var(--info)]' : 'text-[var(--text-muted)]',
      )}>
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
        <div className="text-sm text-[var(--danger)] bg-[var(--danger)]/5 rounded-lg px-3 py-2">
          Error: {msg.content}
        </div>
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

      <div className={cn(
        'group flex flex-col gap-1 max-w-[75%]',
        isUser && 'items-end',
      )}>
        <div className={cn(
          'text-sm leading-relaxed rounded-xl px-4 py-2.5',
          isUser
            ? 'bg-[var(--accent-soft)] text-[var(--text)]'
            : 'bg-[var(--surface)] border border-[var(--border-subtle)] text-[var(--text)]',
        )}>
          {renderContent(msg.content)}
        </div>

        {!isUser && (
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

function renderContent(text: string) {
  // Simple markdown-like rendering: detect code blocks and format
  const parts = text.split(/(```[\s\S]*?```)/g)
  return parts.map((part, i) => {
    if (part.startsWith('```') && part.endsWith('```')) {
      const inner = part.slice(3, -3)
      const langEnd = inner.indexOf('\n')
      const code = langEnd > 0 ? inner.slice(langEnd + 1) : inner
      return (
        <pre key={i} className="my-2 text-xs">
          <code>{code}</code>
        </pre>
      )
    }
    // Handle inline code
    const segments = part.split(/(`[^`]+`)/g)
    return (
      <span key={i}>
        {segments.map((seg, j) =>
          seg.startsWith('`') && seg.endsWith('`') ? (
            <code key={j} className="text-xs">{seg.slice(1, -1)}</code>
          ) : (
            <span key={j}>{seg}</span>
          ),
        )}
      </span>
    )
  })
}
