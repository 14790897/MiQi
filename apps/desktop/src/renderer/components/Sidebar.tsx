import { useState, useEffect, useCallback } from 'react'
import { cn } from '../lib/utils'
import {
  MessageSquare,
  FolderOpen,
  BookOpen,
  Wrench,
  Settings,
  Plus,
  Plug,
  type LucideIcon,
} from 'lucide-react'
import type { SessionInfo } from '../../shared/ipc'

interface NavItem {
  id: string
  label: string
  icon: LucideIcon
}

const NAV_ITEMS: NavItem[] = [
  { id: 'chat',      label: '对话',   icon: MessageSquare },
  { id: 'mcps',      label: 'MCPs',   icon: Plug },
  { id: 'experience', label: '经验', icon: BookOpen },
  { id: 'skills',    label: '技能',   icon: Wrench },
  { id: 'workspace', label: '工作区', icon: FolderOpen },
  { id: 'settings',  label: '设置',   icon: Settings },
]

function formatTimestampKey(key: string): string {
  const ts = parseInt(key, 10)
  if (isNaN(ts)) return key
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(ts))
}

function relativeTime(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 60_000) return 'Just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} mins ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} hours ago`
  if (diff < 2 * 86_400_000) return 'Yesterday'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

interface SidebarProps {
  activeNav: string
  onNavChange: (id: string) => void
  currentSession?: string
  onSessionSelect?: (key: string) => void
  refreshKey?: number
  onNewSession?: () => void
}

export function Sidebar({
  activeNav,
  onNavChange,
  currentSession,
  onSessionSelect,
  refreshKey,
  onNewSession,
}: SidebarProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [loading, setLoading] = useState(false)

  const loadSessions = useCallback(async () => {
    setLoading(true)
    try {
      const r = await window.miqi.sessions.list()
      setSessions(r.sessions ?? [])
    } catch {
      /* Bridge not available */
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    loadSessions()
  }, [loadSessions, refreshKey])

  return (
    <div
      className="flex flex-col shrink-0 border-r"
      style={{
        width: 240,
        background: 'var(--sidebar-bg)',
        borderColor: 'var(--sidebar-border)',
      }}
    >
      {/* Logo + title */}
      <div
        className="flex items-center gap-2.5 px-4 h-12 border-b shrink-0"
        style={{ borderColor: 'var(--sidebar-border)' }}
      >
        <div
          className="w-7 h-7 rounded-md flex items-center justify-center text-white text-sm font-bold shrink-0"
          style={{ background: 'var(--topbar-bg)' }}
        >
          M
        </div>
        <span
          className="text-sm font-semibold"
          style={{ color: 'var(--text)' }}
        >
          MiQi Workbench
        </span>
      </div>

      {/* Nav items */}
      <nav
        className="px-2 py-2 flex flex-col gap-0.5 border-b shrink-0"
        style={{ borderColor: 'var(--sidebar-border)' }}
      >
        {NAV_ITEMS.map((item) => {
          const isActive = activeNav === item.id
          const Icon = item.icon
          return (
            <button
              key={item.id}
              onClick={() => onNavChange(item.id)}
              className={cn(
                'flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-sm transition-colors text-left w-full',
                isActive ? 'font-medium' : 'hover:bg-[var(--surface-muted)]',
              )}
              style={{
                background: isActive ? 'var(--surface-muted)' : undefined,
                color: isActive ? 'var(--text)' : 'var(--text-muted)',
              }}
            >
              <Icon size={15} />
              {item.label}
            </button>
          )
        })}
      </nav>

      {/* Sessions header */}
      <div className="flex items-center justify-between px-4 pt-3 pb-2 shrink-0">
        <span
          className="text-xs font-semibold uppercase tracking-wider"
          style={{ color: 'var(--text-muted)' }}
        >
          Tasks
        </span>
        <button
          onClick={onNewSession}
          className="w-5 h-5 rounded flex items-center justify-center transition-colors hover:bg-[var(--surface-muted)]"
          title="New Session"
        >
          <Plus size={13} style={{ color: 'var(--text-faint)' }} />
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {loading ? (
          <div className="flex items-center justify-center py-6">
            <div className="w-4 h-4 border-2 border-[var(--border)] border-t-[var(--accent)] rounded-full animate-spin" />
          </div>
        ) : sessions.length === 0 ? (
          <div
            className="text-xs text-center py-6"
            style={{ color: 'var(--text-faint)' }}
          >
            No sessions
          </div>
        ) : (
          <div className="space-y-1">
            {sessions.map((s) => {
              const isActive = currentSession === s.key
              const displayName = s.title || formatTimestampKey(s.key)
              return (
                <button
                  key={s.key}
                  onClick={() => {
                    onNavChange('chat')
                    onSessionSelect?.(s.key)
                  }}
                  className="w-full flex items-start gap-2 px-2 py-1.5 rounded hover:bg-zinc-800 text-left"
                  style={{
                    background: isActive ? 'var(--surface-muted)' : 'transparent',
                  }}
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-zinc-500 flex-shrink-0 mt-1.5" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-zinc-200 truncate">{displayName}</p>
                    <p className="text-xs text-zinc-500">{relativeTime(s.updated_at)}</p>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>

    </div>
  )
}
