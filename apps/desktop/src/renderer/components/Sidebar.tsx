import { useState, useEffect, useCallback } from 'react'
import { cn } from '../lib/utils'
import {
  MessageSquare,
  FolderOpen,
  Cpu,
  Radio,
  ShieldAlert,
  Clock,
  BookOpen,
  Wrench,
  Settings,
  Plus,
  type LucideIcon,
} from 'lucide-react'
import type { SessionInfo } from '../../shared/ipc'

interface NavItem {
  id: string
  label: string
  icon: LucideIcon
}

const NAV_ITEMS: NavItem[] = [
  { id: 'chat', label: '对话', icon: MessageSquare },
  { id: 'providers', label: 'Provider', icon: Cpu },
  { id: 'channels', label: '渠道', icon: Radio },
  { id: 'approvals', label: '命令审批', icon: ShieldAlert },
  { id: 'cron', label: '定时任务', icon: Clock },
  { id: 'memory', label: '记忆', icon: BookOpen },
  { id: 'skills', label: '技能', icon: Wrench },
  { id: 'workspace', label: '工作区', icon: FolderOpen },
  { id: 'settings', label: '设置', icon: Settings },
]

/* session status label helpers */
function sessionStatusTag(key: string): 'inprogress' | 'review' | 'completed' {
  const h = key.charCodeAt(key.length - 1) % 3
  if (h === 0) return 'review'
  if (h === 1) return 'inprogress'
  return 'completed'
}

const STATUS_LABELS: Record<string, string> = {
  inprogress: 'IN PROGRESS',
  review: 'REVIEW',
  completed: 'COMPLETED',
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
  const [statusFilter, setStatusFilter] = useState<
    'all' | 'inprogress' | 'review' | 'completed'
  >('all')

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

  const formatTime = (iso?: string) => {
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

  const filteredSessions = sessions.filter((s) => {
    if (statusFilter === 'all') return true
    return sessionStatusTag(s.key) === statusFilter
  })

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

      {/* Status filter tabs */}
      <div className="flex items-center gap-1 px-3 pb-2 shrink-0">
        {(['all', 'inprogress', 'review', 'completed'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setStatusFilter(f)}
            className={cn(
              'px-2 py-0.5 rounded text-[10px] font-semibold transition-colors uppercase tracking-wide',
              statusFilter === f
                ? 'text-[var(--text)]'
                : 'text-[var(--text-faint)] hover:text-[var(--text-muted)]',
            )}
            style={{
              background:
                statusFilter === f ? 'var(--surface-muted)' : 'transparent',
            }}
          >
            {f === 'all'
              ? 'ALL'
              : f === 'inprogress'
                ? 'IN PROG'
                : f === 'review'
                  ? 'REVIEW'
                  : 'COMPL'}
          </button>
        ))}
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {loading ? (
          <div className="flex items-center justify-center py-6">
            <div className="w-4 h-4 border-2 border-[var(--border)] border-t-[var(--accent)] rounded-full animate-spin" />
          </div>
        ) : filteredSessions.length === 0 ? (
          <div
            className="text-xs text-center py-6"
            style={{ color: 'var(--text-faint)' }}
          >
            No sessions
          </div>
        ) : (
          <div className="space-y-1">
            {filteredSessions.map((s) => {
              const tag = sessionStatusTag(s.key)
              const isActive = currentSession === s.key
              return (
                <button
                  key={s.key}
                  onClick={() => {
                    onNavChange('chat')
                    onSessionSelect?.(s.key)
                  }}
                  className="w-full text-left px-3 py-2.5 rounded-lg transition-colors"
                  style={{
                    background: isActive
                      ? 'var(--surface-muted)'
                      : 'transparent',
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive)
                      (e.currentTarget as HTMLElement).style.background =
                        'var(--surface-muted)'
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive)
                      (e.currentTarget as HTMLElement).style.background =
                        'transparent'
                  }}
                >
                  <div className="flex items-start justify-between gap-1 mb-1">
                    <span className={`tag-${tag} shrink-0`}>
                      {STATUS_LABELS[tag]}
                    </span>
                    <span
                      className="text-[10px] shrink-0"
                      style={{ color: 'var(--text-faint)' }}
                    >
                      {formatTime(s.updated_at)}
                    </span>
                  </div>
                  <div
                    className="text-xs font-medium truncate"
                    style={{ color: 'var(--text)' }}
                  >
                    {s.key.replace(/^desktop:/, '').replace(/_/g, ' ')}
                  </div>
                  {(s as any).preview && (
                    <div
                      className="text-[11px] mt-0.5 line-clamp-2"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      {(s as any).preview}
                    </div>
                  )}
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Settings footer */}
      <div
        className="flex items-center gap-2 px-3 py-2.5 border-t shrink-0"
        style={{ borderColor: 'var(--sidebar-border)' }}
      >
        <button
          onClick={() => onNavChange('settings')}
          className="flex items-center gap-2 w-full px-2 py-1.5 rounded-lg transition-colors hover:bg-[var(--surface-muted)]"
          style={{
            color:
              activeNav === 'settings' ? 'var(--text)' : 'var(--text-muted)',
          }}
        >
          <Settings size={14} />
          <span className="text-xs">Settings</span>
        </button>
      </div>
    </div>
  )
}
