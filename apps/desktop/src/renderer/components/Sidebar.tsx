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
  RefreshCw,
  Loader2,
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
  { id: 'sessions', label: '会话', icon: FolderOpen },
  { id: 'providers', label: 'Provider', icon: Cpu },
  { id: 'channels', label: '渠道', icon: Radio },
  { id: 'approvals', label: '命令审批', icon: ShieldAlert },
  { id: 'cron', label: '定时任务', icon: Clock },
  { id: 'memory', label: '记忆', icon: BookOpen },
  { id: 'skills', label: '技能', icon: Wrench },
  { id: 'workspace', label: '工作区', icon: FolderOpen },
  { id: 'settings', label: '设置', icon: Settings },
]

interface SidebarProps {
  activeNav: string
  onNavChange: (id: string) => void
  currentSession?: string
  onSessionSelect?: (key: string) => void
}

export function Sidebar({ activeNav, onNavChange, currentSession, onSessionSelect }: SidebarProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [loading, setLoading] = useState(false)

  const loadSessions = useCallback(async () => {
    setLoading(true)
    try {
      const r = await window.miqi.sessions.list()
      setSessions(r.sessions ?? [])
    } catch {
      // Bridge not available
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    loadSessions()
  }, [loadSessions])

  const formatTime = (iso?: string) => {
    if (!iso) return ''
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div className="flex flex-col w-[280px] shrink-0 border-r border-[var(--border-subtle)] bg-[var(--surface)]">
      {/* App title */}
      <div className="flex items-center gap-2 h-12 px-4 border-b border-[var(--border-subtle)]">
        <div className="w-6 h-6 rounded-md bg-[var(--accent)] flex items-center justify-center text-white text-xs font-bold">
          M
        </div>
        <span className="text-sm font-semibold text-[var(--text)]">MiQi</span>
      </div>

      {/* Navigation */}
      <nav className="p-2 border-b border-[var(--border-subtle)] flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => {
          const isActive = activeNav === item.id
          const Icon = item.icon
          return (
            <button
              key={item.id}
              onClick={() => onNavChange(item.id)}
              className={cn(
                'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors text-left w-full',
                isActive
                  ? 'bg-[var(--accent-soft)] text-[var(--accent)] font-medium'
                  : 'text-[var(--text-muted)] hover:bg-[var(--surface-muted)] hover:text-[var(--text)]',
              )}
            >
              <Icon size={18} />
              {item.label}
            </button>
          )
        })}
      </nav>

      {/* Session list */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--border-subtle)]">
          <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">会话</h3>
          <button
            onClick={loadSessions}
            disabled={loading}
            className="p-1 rounded hover:bg-[var(--surface-muted)] transition-colors"
            title="刷新会话"
          >
            <RefreshCw size={12} className={cn('text-[var(--text-faint)]', loading && 'animate-spin')} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 size={14} className="animate-spin text-[var(--text-muted)]" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-6 text-center px-4">
              <MessageSquare size={18} className="text-[var(--text-faint)]" />
              <p className="text-xs text-[var(--text-faint)]">暂无会话</p>
            </div>
          ) : (
            <div className="p-2 space-y-1">
              {sessions.map((s) => (
                <button
                  key={s.key}
                  onClick={() => {
                    onNavChange('chat')
                    onSessionSelect?.(s.key)
                  }}
                  className={cn(
                    'w-full flex items-start gap-2 px-3 py-2 rounded-lg text-left transition-colors',
                    currentSession === s.key ? 'bg-[var(--accent-soft)]/50' : 'hover:bg-[var(--surface-muted)]',
                  )}
                >
                  <FolderOpen size={14} className="text-[var(--text-faint)] shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-[var(--text)] truncate">{s.key}</div>
                    {s.updated_at && (
                      <div className="text-[10px] text-[var(--text-faint)] mt-0.5">{formatTime(s.updated_at)}</div>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
